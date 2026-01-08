"""
Unload Service - отслеживание выгрузки подвесов из Bath[34].
Bath[34] - контрольная точка выхода из линии.
Когда подвес выходит из Bath[34], это событие выгрузки.
"""
import logging
from datetime import datetime
from typing import Dict, List, Optional, Set
from dataclasses import dataclass, asdict
import json
from pathlib import Path

from app.services.opcua_service import opcua_service
from app.schemas.dashboard import UnloadEvent

logger = logging.getLogger(__name__)

CONTROL_BATH = 34  # Контрольная точка - выход из линии


@dataclass
class UnloadRecord:
    """Запись о выгрузке подвеса."""
    hanger_number: int
    pallete: int
    exit_time: str  # Время выхода из Bath[34]
    exit_date: str  # Дата выхода
    total_time_sec: float  # Общее время в линии
    baths_visited: List[int]  # Список посещённых ванн
    timestamp: str  # ISO timestamp
    
    def to_dict(self):
        return asdict(self)
    
    def to_unload_event(self) -> UnloadEvent:
        """Конвертировать в UnloadEvent для совместимости с dashboard."""
        return UnloadEvent(
            time=self.exit_time,
            hanger=self.hanger_number,
            date=self.exit_date,
            timestamp=datetime.fromisoformat(self.timestamp) if self.timestamp else None
        )


class UnloadService:
    """
    Сервис отслеживания выгрузки подвесов.
    Мониторит Bath[34] и фиксирует выход подвесов из линии.
    """
    
    def __init__(self, cache_file: str = None):
        # Используем папку backend для кеша
        if cache_file is None:
            cache_file = Path(__file__).parent.parent.parent / "unload_events.json"
        self.cache_file = Path(cache_file)
        self.events: List[UnloadRecord] = []
        self.today_events: List[UnloadRecord] = []
        
        # Отслеживание состояния Bath[34]
        # Инициализируем как None чтобы первый poll установил начальное значение
        self._bath34_pallete: Optional[int] = None
        self._bath34_in_time: float = 0
        self._initialized: bool = False
        
        # Отслеживание активных подвесов в линии
        self._active_hangers: Dict[int, dict] = {}  # hanger_num -> {start_time, baths}
        
        # Уже обработанные выгрузки (чтобы не дублировать)
        self._processed_exits: Set[str] = set()
        
        self.load_cache()
    
    def load_cache(self):
        """Загрузить кеш событий."""
        if self.cache_file.exists():
            try:
                with open(self.cache_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    self.events = [UnloadRecord(**e) for e in data.get('events', [])]
                    
                    # Загружаем processed_exits
                    self._processed_exits = set(data.get('processed_exits', []))
                    
                    # Фильтруем события за сегодня
                    today = datetime.now().strftime("%d.%m.%Y")
                    self.today_events = [e for e in self.events if e.exit_date == today]
                    
                logger.info(f"[Unload Service] Loaded {len(self.events)} events, {len(self.today_events)} today")
            except Exception as e:
                logger.error(f"[Unload Service] Error loading cache: {e}")
    
    def save_cache(self):
        """Сохранить кеш событий."""
        try:
            # Храним только последние 1000 событий
            events_to_save = self.events[-1000:]
            
            data = {
                'events': [e.to_dict() for e in events_to_save],
                'processed_exits': list(self._processed_exits)[-500:],  # Последние 500
                'last_updated': datetime.now().isoformat()
            }
            
            with open(self.cache_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
        except Exception as e:
            logger.error(f"[Unload Service] Error saving cache: {e}")
    
    async def check_bath34(self) -> Optional[UnloadRecord]:
        """
        Проверить Bath[34] на ВХОД подвеса.
        Возвращает UnloadRecord когда подвес ВХОДИТ в ванну 34 (выгрузка).
        Детекция: Pallete меняется с 0 на ненулевое значение.
        """
        try:
            # Читаем текущее состояние Bath[34]
            pallete_raw = await opcua_service.read_node(f"ns=4;s=Bath[{CONTROL_BATH}].Pallete")
            in_time_raw = await opcua_service.read_node(f"ns=4;s=Bath[{CONTROL_BATH}].InTime")
            
            # Логируем сырые значения для отладки
            logger.debug(f"[Unload Service] Bath[{CONTROL_BATH}] raw: Pallete={pallete_raw}, InTime={in_time_raw}")
            
            current_pallete = int(pallete_raw) if pallete_raw is not None else 0
            current_in_time = float(in_time_raw) if in_time_raw is not None else 0
            
            result = None
            
            # Первый poll - просто запоминаем состояние, не создаём событие
            if self._bath34_pallete is None:
                logger.info(f"[Unload Service] Initial state: Bath[{CONTROL_BATH}] Pallete = {current_pallete}")
                self._bath34_pallete = current_pallete
                self._bath34_in_time = current_in_time
                return None
            
            # Логируем каждое изменение
            if current_pallete != self._bath34_pallete:
                logger.info(f"[Unload Service] Bath[{CONTROL_BATH}] Pallete changed: {self._bath34_pallete} -> {current_pallete}")
            
            # Детектируем ВХОД: Pallete было 0, стало > 0
            # Это означает что подвес ОПУСТИЛСЯ в ванну 34
            if self._bath34_pallete == 0 and current_pallete > 0:
                # Подвес ВОШЁЛ в Bath[34] - это выгрузка!
                now = datetime.now()
                entry_key = f"{current_pallete}_{now.strftime('%Y%m%d_%H%M')}"
                
                logger.info(f"[Unload Service] 🎯 Detected ENTRY! Pallete {current_pallete}, entry_key={entry_key}")
                
                # Проверяем что не обрабатывали этот вход
                if entry_key not in self._processed_exits:
                    self._processed_exits.add(entry_key)
                    
                    # Создаём событие выгрузки
                    record = UnloadRecord(
                        hanger_number=current_pallete,
                        pallete=current_pallete,
                        exit_time=now.strftime("%H:%M:%S"),
                        exit_date=now.strftime("%d.%m.%Y"),
                        total_time_sec=current_in_time,
                        baths_visited=self._get_hanger_baths(current_pallete),
                        timestamp=now.isoformat()
                    )
                    
                    self.events.append(record)
                    self.today_events.append(record)
                    self.save_cache()
                    
                    logger.info(f"[Unload Service] ✅ UNLOAD EVENT CREATED: Pallete {current_pallete} entered Bath[{CONTROL_BATH}]")
                    result = record
                else:
                    logger.info(f"[Unload Service] ⚠️ Entry already processed: {entry_key}")
            
            # Обновляем состояние
            self._bath34_pallete = current_pallete
            self._bath34_in_time = current_in_time
            
            return result
            
        except Exception as e:
            logger.error(f"[Unload Service] Error checking Bath[{CONTROL_BATH}]: {e}", exc_info=True)
            return None
    
    def _get_hanger_baths(self, hanger_number: int) -> List[int]:
        """Получить список ванн которые посетил подвес."""
        from app.services.hanger_service import hanger_service
        
        hanger = hanger_service.get_hanger(hanger_number)
        if hanger and hanger.baths_history:
            return [b.bath_number for b in hanger.baths_history]
        return []
    
    def get_today_events(self) -> List[UnloadRecord]:
        """Получить события выгрузки за сегодня."""
        today = datetime.now().strftime("%d.%m.%Y")
        return [e for e in self.events if e.exit_date == today]
    
    def get_events(self, limit: int = 100, date: Optional[str] = None) -> List[UnloadRecord]:
        """Получить события выгрузки."""
        if date:
            filtered = [e for e in self.events if e.exit_date == date]
            return filtered[-limit:]
        return self.events[-limit:]
    
    def get_unload_events(self, limit: int = 100) -> List[UnloadEvent]:
        """Получить события в формате UnloadEvent для совместимости с dashboard."""
        records = self.get_events(limit)
        return [r.to_unload_event() for r in reversed(records)]  # Newest first
    
    def clear_today(self):
        """Очистить события за сегодня."""
        today = datetime.now().strftime("%d.%m.%Y")
        self.events = [e for e in self.events if e.exit_date != today]
        self.today_events = []
        self.save_cache()
        logger.info("[Unload Service] Today's events cleared")


# Singleton instance
unload_service = UnloadService()
