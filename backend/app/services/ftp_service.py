"""
FTP Service - handles FTP connection to Omron PLC and log parsing.
Includes simulation mode for testing with local files.

Использует синхронный ftplib через asyncio executor для стабильности.
"""
import re
import asyncio
import logging
import io
import time
from datetime import datetime, date, timedelta
from typing import Optional, List, Tuple
from pathlib import Path
from enum import Enum
from ftplib import FTP, error_temp, error_perm
from concurrent.futures import ThreadPoolExecutor

from app.core.config import settings
from app.schemas.dashboard import UnloadEvent

logger = logging.getLogger(__name__)

# Thread pool для синхронных FTP операций
_ftp_executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="ftp_")


class FTPConnectionState(Enum):
    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    ERROR = "error"
    BUSY = "busy"


class FTPService:
    """
    FTP Service с использованием синхронного ftplib.
    Все операции выполняются в thread pool executor.
    Переиспользует соединение для уменьшения нагрузки на сервер.
    """
    
    MAX_RETRIES = 3
    RETRY_BASE_DELAY = 3.0  # PLC needs more time between retries
    CONNECTION_TIMEOUT = 15
    ENCODINGS = ['utf-8', 'cp1251', 'cp866', 'latin-1']
    CONNECTION_REUSE_TIME = 60  # Держим соединение открытым 60 секунд
    
    def __init__(self):
        self._last_position: int = 0
        self._last_date: Optional[date] = None
        self._connected: bool = False
        self._state: FTPConnectionState = FTPConnectionState.DISCONNECTED
        self._lock = asyncio.Lock()
        self._ftp: Optional[FTP] = None
        self._ftp_last_used: float = 0
        self._ftp_lock = asyncio.Lock()
        
        # Кеш для прошлых дней (они не меняются)
        # {date: List[UnloadEvent]}
        self._past_days_cache: dict[date, List[UnloadEvent]] = {}
        
        self._stats = {
            'connections': 0,
            'reconnects': 0,
            'retries': 0,
            'errors_550': 0,
            'errors_timeout': 0,
            'errors_other': 0,
            'bytes_read': 0,
        }
        
        # Simulation mode
        self._simulation_mode: bool = False
        self._simulation_file: Optional[Path] = None
        self._simulation_events: List[UnloadEvent] = []
        self._simulation_date: Optional[date] = None
    
    @property
    def is_connected(self) -> bool:
        return self._connected
    
    @property
    def state(self) -> FTPConnectionState:
        return self._state
    
    @property
    def stats(self) -> dict:
        return self._stats.copy()
    
    def _get_log_filename(self, for_date: Optional[date] = None) -> str:
        target_date = for_date or date.today()
        return target_date.strftime("%Y-%m-%d.txt")
    
    def _get_log_path(self, for_date: Optional[date] = None) -> str:
        filename = self._get_log_filename(for_date)
        base_path = settings.FTP_BASE_PATH.rstrip('/')
        if base_path:
            return f"{base_path}/{filename}"
        return filename
    
    def _decode_content(self, data: bytes) -> str:
        for encoding in self.ENCODINGS:
            try:
                return data.decode(encoding)
            except UnicodeDecodeError:
                continue
        return data.decode('utf-8', errors='ignore')
    
    def _sync_connect(self) -> Optional[FTP]:
        """Синхронное подключение к FTP (вызывается в executor)."""
        # Проверяем существующее соединение
        if self._ftp:
            try:
                self._ftp.voidcmd("NOOP")  # Проверка что соединение живое
                self._ftp_last_used = time.time()
                return self._ftp
            except Exception:
                # Соединение умерло, закрываем
                try:
                    self._ftp.quit()
                except Exception:
                    pass
                self._ftp = None
        
        for attempt in range(self.MAX_RETRIES):
            try:
                ftp = FTP()
                ftp.connect(settings.FTP_HOST, settings.FTP_PORT, timeout=self.CONNECTION_TIMEOUT)
                ftp.login(settings.FTP_USER, settings.FTP_PASSWORD)
                ftp.set_pasv(True)
                
                # Переходим в базовую директорию если указана
                if settings.FTP_BASE_PATH and settings.FTP_BASE_PATH != '/':
                    try:
                        ftp.cwd(settings.FTP_BASE_PATH)
                    except Exception:
                        pass  # Директория может не существовать
                
                self._connected = True
                self._state = FTPConnectionState.CONNECTED
                self._stats['connections'] += 1
                self._ftp = ftp
                self._ftp_last_used = time.time()
                logger.info(f"[FTP] Connected to {settings.FTP_HOST}")
                return ftp
                
            except (error_temp, error_perm) as e:
                error_str = str(e)
                if "550" in error_str or "421" in error_str or "busy" in error_str.lower():
                    self._stats['errors_550'] += 1
                    delay = self.RETRY_BASE_DELAY * (2 ** attempt)
                    logger.warning(f"[FTP] Server busy, retry {attempt + 1}/{self.MAX_RETRIES} in {delay}s")
                    time.sleep(delay)
                    continue
                self._stats['errors_other'] += 1
                logger.error(f"[FTP] Connection error: {e}")
                break
            except Exception as e:
                self._stats['errors_other'] += 1
                logger.error(f"[FTP] Connection failed: {e}")
                break
        
        self._connected = False
        self._state = FTPConnectionState.ERROR
        self._ftp = None
        return None
    
    def _sync_disconnect(self) -> None:
        """Закрыть FTP соединение."""
        if self._ftp:
            try:
                self._ftp.quit()
            except Exception:
                pass
            self._ftp = None
            self._connected = False
    
    def _sync_read_file_with_size_check(self, filename: str) -> bytes:
        """
        Чтение файла с предварительной проверкой SIZE.
        Если SIZE работает - файл доступен для чтения.
        """
        ftp = self._sync_connect()
        if not ftp:
            return b""
        
        try:
            # Сначала проверяем SIZE - если работает, файл доступен
            try:
                size = ftp.size(filename)
                if size is None or size == 0:
                    logger.warning(f"[FTP] File {filename} has size 0 or unavailable")
                    return b""
                logger.debug(f"[FTP] File {filename} size: {size} bytes")
            except Exception as e:
                # SIZE не работает - файл может быть занят
                logger.warning(f"[FTP] SIZE failed for {filename}: {e}")
                self._sync_disconnect()
                return b""
            
            # SIZE прошёл - читаем файл
            buffer = io.BytesIO()
            ftp.retrbinary(f'RETR {filename}', buffer.write)
            content = buffer.getvalue()
            self._stats['bytes_read'] += len(content)
            self._ftp_last_used = time.time()
            return content
            
        except (error_temp, error_perm) as e:
            error_str = str(e)
            if "550" in error_str:
                if "busy" in error_str.lower():
                    self._stats['errors_550'] += 1
                    logger.warning(f"[FTP] Server busy reading {filename}")
                else:
                    logger.warning(f"[FTP] File not found: {filename}")
            else:
                logger.error(f"[FTP] Read error: {e}")
            self._sync_disconnect()
            return b""
        except Exception as e:
            logger.error(f"[FTP] Read error: {e}")
            self._sync_disconnect()
            return b""

    def _sync_read_file(self, filename: str) -> bytes:
        """Синхронное чтение файла с SIZE проверкой."""
        return self._sync_read_file_with_size_check(filename)
    
    async def read_log_for_date(self, for_date: date) -> str:
        """Асинхронное чтение лога за дату."""
        async with self._lock:
            filename = self._get_log_filename(for_date)
            loop = asyncio.get_event_loop()
            content = await loop.run_in_executor(_ftp_executor, self._sync_read_file, filename)
            return self._decode_content(content)
    
    async def read_today_log(self) -> str:
        """Чтение сегодняшнего лога."""
        return await self.read_log_for_date(date.today())

    async def poll_multiday(self, days: int = 2) -> Tuple[List[UnloadEvent], bool]:
        """
        Читает логи за N дней и возвращает все события.
        Прошлые дни кешируются (они не меняются).
        Только сегодняшний файл читается каждый раз.
        
        Агрессивный retry: 5 попыток с увеличивающимися паузами.
        """
        today = date.today()
        date_changed = False
        
        if self._last_date and self._last_date != today:
            logger.info(f"[FTP] Date changed: {self._last_date} -> {today}")
            date_changed = True
            self._past_days_cache.clear()
        
        self._last_date = today
        all_events = []
        
        # Retry delays: 2, 3, 4, 5, 6 seconds (increasing)
        RETRY_DELAYS = [2.0, 3.0, 4.0, 5.0, 6.0]
        MAX_ATTEMPTS = len(RETRY_DELAYS) + 1  # 6 attempts total
        
        for day_offset in range(days):
            file_date = today - timedelta(days=day_offset)
            
            # Прошлые дни берём из кеша
            if file_date < today and file_date in self._past_days_cache:
                cached_events = self._past_days_cache[file_date]
                all_events.extend(cached_events)
                continue
            
            # Читаем файл с агрессивным retry
            success = False
            for attempt in range(MAX_ATTEMPTS):
                try:
                    # Disconnect before each attempt for fresh connection
                    await self.disconnect()
                    
                    # Wait before retry (except first attempt)
                    if attempt > 0:
                        delay = RETRY_DELAYS[attempt - 1]
                        logger.info(f"[FTP] Retry {attempt}/{MAX_ATTEMPTS-1} for {file_date}, waiting {delay}s...")
                        await asyncio.sleep(delay)
                    
                    content = await self.read_log_for_date(file_date)
                    if content:
                        self._current_parse_date = file_date.strftime("%d.%m.%Y")
                        events = self.parse_unload_events_cj2m(content)
                        all_events.extend(events)
                        
                        if file_date < today:
                            self._past_days_cache[file_date] = events
                            logger.info(f"[FTP] Cached {len(events)} events for {file_date}")
                        else:
                            logger.info(f"[FTP] Read {len(events)} events for {file_date} (today)")
                        success = True
                        break
                    else:
                        logger.warning(f"[FTP] Empty content for {file_date} (attempt {attempt + 1}/{MAX_ATTEMPTS})")
                except Exception as e:
                    logger.error(f"[FTP] Error reading {file_date}: {e}")
            
            if not success:
                logger.error(f"[FTP] Failed to read {file_date} after {MAX_ATTEMPTS} attempts")
            
            # Disconnect after each file
            await self.disconnect()
        
        if all_events:
            logger.info(f"[FTP] Total: {len(all_events)} events from {days} days")
        
        return all_events, date_changed
    
    async def poll_incremental(self) -> Tuple[List[UnloadEvent], bool]:
        """Инкрементальный polling (для совместимости)."""
        return await self.poll_multiday(days=1)
    
    def reset_position(self) -> None:
        self._last_position = 0
        self._last_date = None
    
    async def disconnect(self) -> None:
        """Закрыть FTP соединение асинхронно."""
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(_ftp_executor, self._sync_disconnect)
    
    def get_diagnostics(self) -> dict:
        return {
            'state': self._state.value,
            'connected': self._connected,
            'last_date': str(self._last_date) if self._last_date else None,
            'simulation_mode': self._simulation_mode,
            'stats': self._stats.copy(),
            'cached_days': list(str(d) for d in self._past_days_cache.keys()),
            'cached_events': sum(len(e) for e in self._past_days_cache.values()),
        }
    
    def clear_cache(self) -> None:
        """Очистить кеш прошлых дней."""
        self._past_days_cache.clear()
        logger.info("[FTP] Cache cleared")
    
    def parse_unload_events_cj2m(self, content: str) -> List[UnloadEvent]:
        """Парсинг событий из лога CJ2M."""
        events = []
        if not content:
            return events
        
        pattern = r'(\d{2}):(\d{2}):(\d{2})\.\d+\s+L#\s+Команда\s+от\s+CJ2M:\s+Разгрузка\s+подвеса\s+-\s+(\d+)\s+в\s+поз\.\s*34\.?'
        
        event_date = getattr(self, '_current_parse_date', None) or date.today().strftime("%d.%m.%Y")
        
        for line in content.split('\n'):
            line = line.strip()
            if not line:
                continue
            
            match = re.search(pattern, line)
            if match:
                hours = int(match.group(1))
                minutes = int(match.group(2))
                seconds = int(match.group(3))
                hanger_num = int(match.group(4))
                
                time_str = f"{hours:02d}:{minutes:02d}:{seconds:02d}"
                
                today = date.today()
                try:
                    timestamp = datetime(today.year, today.month, today.day, hours, minutes, seconds)
                except ValueError:
                    timestamp = datetime.now()
                
                events.append(UnloadEvent(
                    time=time_str,
                    hanger=hanger_num,
                    date=event_date,
                    timestamp=timestamp
                ))
        
        return events
    
    def parse_unload_events(self, content: str) -> List[UnloadEvent]:
        """Алиас для совместимости."""
        return self.parse_unload_events_cj2m(content)
    
    # ==================== SIMULATION MODE ====================
    
    @property
    def is_simulation(self) -> bool:
        return self._simulation_mode
    
    @property
    def simulation_events_count(self) -> int:
        return len(self._simulation_events)
    
    def start_simulation(self, file_path: Path) -> bool:
        if not file_path.exists():
            logger.error(f"Simulation file not found: {file_path}")
            return False
        
        try:
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()
            
            # Parse date from filename
            filename = file_path.stem
            date_match = re.match(r'(\d{4})-(\d{2})-(\d{2})', filename)
            if date_match:
                year, month, day = date_match.groups()
                self._simulation_date = f"{day}.{month}.{year}"
                self._current_parse_date = self._simulation_date
            
            self._simulation_events = self.parse_unload_events_cj2m(content)
            self._simulation_mode = True
            self._simulation_file = file_path
            self._connected = True
            
            logger.info(f"[SIMULATION] Loaded {len(self._simulation_events)} events from {file_path}")
            return True
        except Exception as e:
            logger.error(f"Failed to start simulation: {e}")
            return False
    
    def stop_simulation(self) -> None:
        self._simulation_mode = False
        self._simulation_file = None
        self._simulation_events = []
        logger.info("[SIMULATION] Stopped")
    
    def get_all_simulation_events(self) -> List[UnloadEvent]:
        if not self._simulation_mode:
            return []
        return self._simulation_events


# Singleton instance
ftp_service = FTPService()
