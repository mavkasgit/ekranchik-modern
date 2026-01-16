"""
OPC UA Service - подключение к OMRON PLC через OPC UA.
Пакетное чтение данных с защитой от "зомби-сессий".

Оптимизировано для Omron NX контроллеров.
"""
import asyncio
import logging
import time
from datetime import datetime
from typing import Any, Dict, List, Set, Optional
from enum import Enum

from app.core.config import settings

# Настройка логгера
logger = logging.getLogger("OPCUA")
# Убираем спам от библиотеки asyncua (оставляем только ошибки)
logging.getLogger("asyncua").setLevel(logging.WARNING)

# Проверка наличия библиотеки
try:
    from asyncua import Client, ua
    from asyncua.ua.uaerrors import BadTooManySessions, BadSessionIdInvalid
    OPCUA_AVAILABLE = True
except ImportError:
    OPCUA_AVAILABLE = False
    logger.warning("[OPC UA] asyncua not installed. Run: pip install asyncua")


class OPCUAState(Enum):
    """Состояния подключения OPC UA."""
    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    ERROR = "error"


class OPCUAService:
    """
    OPC UA сервис с пакетным чтением и защитой от зомби-сессий.
    
    Особенности:
    - Короткий session_timeout (15 сек) для быстрого освобождения слотов
    - Пакетное чтение по 100 узлов за раз
    - Автоматическое добавление узлов в мониторинг при первом запросе
    - Черный список для битых адресов
    """
    
    def __init__(self):
        self._url = settings.OPCUA_ENDPOINT
        self._running = False
        self._connected = False
        self._state = OPCUAState.DISCONNECTED
        self._last_update = datetime.min
        
        # --- НАСТРОЙКИ ---
        # 15 сек - чтобы Omron быстро убивал зависшие сессии
        self._session_timeout = 15000
        # 0.5 сек - частота обновления данных (2 раза в секунду)
        self._poll_interval = 0.5
        # Размер пачки для чтения (безопасно для Omron NX)
        self._batch_size = 100
        
        # Кэш: { "ns=4;s=Name": value }
        self._cache: Dict[str, Any] = {}
        # Список переменных для постоянного чтения
        self._monitored_nodes: Set[str] = set()
        # Черный список (битые адреса)
        self._blacklist: Set[str] = set()
        
        # Статистика
        self._stats = {
            'connections': 0,
            'reads': 0,
            'errors': 0,
            'cache_hits': 0,
        }
    
    @property
    def is_available(self) -> bool:
        return OPCUA_AVAILABLE
    
    @property
    def is_connected(self) -> bool:
        return self._connected
    
    @property
    def state(self) -> OPCUAState:
        return self._state
    
    @property
    def stats(self) -> dict:
        return self._stats.copy()
    
    @property
    def last_update(self) -> datetime:
        return self._last_update
    
    def get_diagnostics(self) -> dict:
        """Получить диагностическую информацию (совместимость с API)."""
        return {
            'available': OPCUA_AVAILABLE,
            'enabled': settings.OPCUA_ENABLED,
            'connected': self._connected,
            'state': self._state.value,
            'endpoint': self._url,
            'stats': self._stats.copy(),
            'monitored_nodes': len(self._monitored_nodes),
            'blacklisted_nodes': len(self._blacklist),
        }
    
    async def ping_server(self) -> Optional[float]:
        """Измерить ping до сервера (совместимость с API)."""
        import socket
        from urllib.parse import urlparse
        
        try:
            parsed = urlparse(self._url)
            host = parsed.hostname
            port = parsed.port or 4840
            
            start = time.time()
            sock = socket.create_connection((host, port), timeout=5)
            sock.close()
            return (time.time() - start) * 1000
        except:
            return None
    
    async def browse_node(self, node_id: str) -> List[Dict[str, str]]:
        """Получить дочерние узлы (совместимость с API)."""
        # Эта функция требует активного клиента, возвращаем пустой список
        # так как worker управляет клиентом
        return []
    
    async def browse_recursive(self, node_id: str, max_depth: int = 3) -> List[dict]:
        """Рекурсивный обход узлов (совместимость с API)."""
        return []
    
    async def read_nodes_batch(self, node_ids: List[str]) -> Dict[str, Any]:
        """Пакетное чтение узлов из кэша (совместимость с API)."""
        # Добавляем все узлы в мониторинг
        for node_id in node_ids:
            if node_id not in self._monitored_nodes and node_id not in self._blacklist:
                self._monitored_nodes.add(node_id)
        
        # Возвращаем значения из кэша
        return {node_id: self._cache.get(node_id) for node_id in node_ids}
    
    async def start(self):
        """Запуск фоновой задачи опроса."""
        if not OPCUA_AVAILABLE:
            logger.error("[OPC UA] Библиотека asyncua не установлена! pip install asyncua")
            return
        
        if self._running:
            return
        
        self._running = True
        # Запускаем worker как фоновую задачу
        asyncio.create_task(self._worker())
        logger.info(f"[OPC UA] Сервис запущен. Endpoint: {self._url}")
    
    async def stop(self):
        """Остановка сервиса."""
        self._running = False
        self._connected = False
        self._state = OPCUAState.DISCONNECTED
        logger.info("[OPC UA] Остановка сервиса...")
    
    def get_value(self, node_id: str) -> Any:
        """
        Мгновенно вернуть значение из памяти.
        Если переменной нет в списке опроса - добавляем её.
        """
        # Автоматическое добавление в мониторинг
        if node_id not in self._monitored_nodes and node_id not in self._blacklist:
            self._monitored_nodes.add(node_id)
        
        self._stats['cache_hits'] += 1
        return self._cache.get(node_id)
    
    async def read_node(self, node_id: str) -> Optional[Any]:
        """
        Прочитать значение узла (совместимость с line_monitor).
        Возвращает значение из кэша, автоматически добавляя узел в мониторинг.
        """
        return self.get_value(node_id)
    
    async def read_nodes(self, node_ids: List[str]) -> Dict[str, Any]:
        """Прочитать несколько узлов (совместимость с line_monitor)."""
        return {node_id: self.get_value(node_id) for node_id in node_ids}
    
    async def connect(self) -> bool:
        """Ожидание подключения (совместимость с line_monitor)."""
        # Ждём до 10 секунд пока worker подключится
        for _ in range(20):
            if self._connected:
                return True
            await asyncio.sleep(0.5)
        return self._connected
    
    async def ensure_connected(self) -> bool:
        """Проверка подключения (совместимость с line_monitor)."""
        # Если уже подключены - сразу возвращаем
        if self._connected:
            return True
        # Иначе ждём немного (worker может быть в процессе реконнекта)
        for _ in range(6):  # 3 секунды максимум
            if self._connected:
                return True
            await asyncio.sleep(0.5)
        return self._connected
    
    async def disconnect(self) -> None:
        """Отключение (совместимость с line_monitor)."""
        # Worker сам управляет подключением, просто очищаем кэш
        self._cache.clear()
        self._monitored_nodes.clear()
        self._blacklist.clear()
        logger.info("[OPC UA] Кэш очищен")
    
    async def _flush_error_batch(self) -> None:
        """Заглушка для совместимости с line_monitor."""
        pass
    
    async def _worker(self):
        """Вечный цикл подключения и опроса."""
        logger.info(f"[OPC UA] Worker started, URL: {self._url}")
        
        while self._running:
            client = None
            try:
                # 1. Создаем клиента
                logger.debug(f"[OPC UA] Creating client for {self._url}")
                client = Client(url=self._url, timeout=10)  # 10 сек таймаут на операции
                # Важно: короткий таймаут сессии для борьбы с "зомби"
                client.session_timeout = self._session_timeout
                
                logger.info(f"[OPC UA] Подключение к {self._url}...")
                self._state = OPCUAState.CONNECTING
                
                # 2. Подключаемся с таймаутом
                try:
                    await asyncio.wait_for(client.connect(), timeout=15.0)
                except asyncio.TimeoutError:
                    logger.error("[OPC UA] Таймаут подключения (15 сек)")
                    self._stats['errors'] += 1
                    await asyncio.sleep(5)
                    continue
                
                logger.info("[OPC UA] Успешно подключено! Начинаем опрос.")
                self._connected = True
                self._state = OPCUAState.CONNECTED
                self._stats['connections'] += 1
                
                # 3. Внутренний цикл опроса (пока есть связь)
                try:
                    while self._running:
                        start_time = time.time()
                        
                        # Читаем данные пачками
                        await self._poll_data_batched(client)
                        
                        # Вычисляем время сна для стабильного ритма
                        elapsed = time.time() - start_time
                        sleep_time = max(0, self._poll_interval - elapsed)
                        await asyncio.sleep(sleep_time)
                finally:
                    # Гарантируем отключение
                    try:
                        await asyncio.wait_for(client.disconnect(), timeout=5.0)
                    except:
                        pass
            
            except BadTooManySessions:
                self._connected = False
                self._state = OPCUAState.ERROR
                self._stats['errors'] += 1
                logger.error("[OPC UA] Ошибка: Нет свободных слотов! Ждем 20 сек очистки...")
                # Ждем дольше таймаута, чтобы контроллер сбросил старую сессию
                await asyncio.sleep(20)
            
            except (OSError, asyncio.TimeoutError) as e:
                self._connected = False
                self._state = OPCUAState.ERROR
                self._stats['errors'] += 1
                logger.warning(f"[OPC UA] Ошибка сети: {type(e).__name__}: {e}. Реконнект через 5 сек...")
                await asyncio.sleep(5)
            
            except Exception as e:
                self._connected = False
                self._state = OPCUAState.ERROR
                self._stats['errors'] += 1
                logger.error(f"[OPC UA] Критическая ошибка: {type(e).__name__}: {e}", exc_info=True)
                await asyncio.sleep(5)
            
            finally:
                self._connected = False
                self._state = OPCUAState.DISCONNECTED
                self._last_update = datetime.min
                logger.debug("[OPC UA] Connection closed, will retry...")
    
    async def _poll_data_batched(self, client: Client):
        """Читает данные, разбивая их на пачки по 100 штук."""
        if not self._monitored_nodes:
            return
        
        # Исключаем битые узлы
        valid_nodes = [n for n in self._monitored_nodes if n not in self._blacklist]
        if not valid_nodes:
            return
        
        # Разбиваем на чанки (по 100 штук)
        chunks = [valid_nodes[i:i + self._batch_size] 
                  for i in range(0, len(valid_nodes), self._batch_size)]
        
        updated_count = 0
        now = datetime.now()
        
        for chunk in chunks:
            try:
                # Получаем объекты Node (локальная операция, быстро)
                ua_nodes = [client.get_node(nid) for nid in chunk]
                
                # СЕТЕВОЙ ЗАПРОС: Читаем пачку значений
                values = await client.read_values(ua_nodes)
                
                # Обновляем кэш
                for node_id, val in zip(chunk, values):
                    self._cache[node_id] = val
                
                updated_count += len(values)
                self._stats['reads'] += len(values)
            
            except Exception as e:
                # Если ошибка связи - пробрасываем выше для реконнекта
                error_str = str(e).lower()
                if any(err in error_str for err in ["badsession", "oserror", "timeout", "closed"]):
                    raise e
                
                logger.warning(f"[OPC UA] Ошибка чтения пачки: {e}")
                self._stats['errors'] += 1
        
        if updated_count > 0:
            self._last_update = now


# Singleton - импортируй этот объект в другие файлы
opcua_service = OPCUAService()
