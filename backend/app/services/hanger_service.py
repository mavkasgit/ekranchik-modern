"""
Hanger Service - отслеживание подвесов по номерам через ванны.
Подвес проходит через разные ванны (Bath[0]...Bath[47]).
Отслеживаем путь каждого подвеса по его номеру через ванны.
"""
import logging
from datetime import datetime
from typing import Dict, Optional, List
from dataclasses import dataclass, asdict, field
import json
from pathlib import Path

from app.services.opcua_service import opcua_service

logger = logging.getLogger(__name__)


@dataclass
class BathRecord:
    """Запись о подвесе в ванне."""
    bath_number: int
    in_time: Optional[str] = None
    out_time: Optional[str] = None
    duration: Optional[str] = None


@dataclass
class Hanger:
    """Подвес с историей прохождения через ванны."""
    hanger_number: int  # Номер подвеса (основной идентификатор)
    pallete_data: Optional[str] = None  # Данные из Bath[N].Pallete
    baths_history: List[BathRecord] = field(default_factory=list)  # История прохождения через ванны
    first_seen: str = ""
    last_updated: str = ""
    current_bath: Optional[int] = None  # Текущая ванна (заполняется сервисом)
    
    def to_dict(self):
        return {
            "hanger_number": self.hanger_number,
            "pallete_data": self.pallete_data,
            "baths_history": [asdict(b) for b in self.baths_history],
            "first_seen": self.first_seen,
            "last_updated": self.last_updated,
            "total_baths": len(self.baths_history),
            "current_bath": self.current_bath
        }


class HangerService:
    """Отслеживание подвесов по номерам через ванны."""
    
    def __init__(self, cache_file: str = None):
        # Используем папку backend для кеша
        if cache_file is None:
            cache_file = Path(__file__).parent.parent.parent / "hangers_cache.json"
        self.cache_file = Path(cache_file)
        self.hangers: Dict[int, Hanger] = {}  # Ключ - номер подвеса
        self.bath_to_hanger: Dict[int, int] = {}  # Какой подвес в какой ванне
        self.load_cache()
    
    def load_cache(self):
        """Загрузить кеш из файла."""
        if self.cache_file.exists():
            try:
                with open(self.cache_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    for hanger_num_str, hanger_data in data.items():
                        try:
                            hanger_num = int(hanger_num_str)
                            baths = [BathRecord(**b) for b in hanger_data.get('baths_history', [])]
                            hanger = Hanger(
                                hanger_number=hanger_num,
                                pallete_data=hanger_data.get('pallete_data'),
                                baths_history=baths,
                                first_seen=hanger_data.get('first_seen', ''),
                                last_updated=hanger_data.get('last_updated', '')
                            )
                            self.hangers[hanger_num] = hanger
                        except (ValueError, KeyError):
                            continue
                logger.info(f"[Hanger Service] Loaded {len(self.hangers)} hangers from cache")
            except Exception as e:
                logger.error(f"[Hanger Service] Error loading cache: {e}")
    
    def save_cache(self):
        """Сохранить кеш в файл."""
        try:
            data = {str(hnum): h.to_dict() for hnum, h in self.hangers.items()}
            with open(self.cache_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
        except Exception as e:
            logger.error(f"[Hanger Service] Error saving cache: {e}")
    
    async def scan_baths(self):
        """Сканировать все ванны и обновить информацию о подвесах."""
        try:
            # Сначала сбрасываем current_bath у всех подвесов
            for hanger in self.hangers.values():
                hanger.current_bath = None
            
            for bath_num in range(1, 40):  # Bath[1] to Bath[39]
                in_use = await opcua_service.read_node(f"ns=4;s=Bath[{bath_num}].InUse")
                
                if in_use:
                    # Ванна используется, читаем данные подвеса
                    # Pallete содержит номер подвеса (0 = пусто)
                    pallete = await opcua_service.read_node(f"ns=4;s=Bath[{bath_num}].Pallete")
                    in_time = await opcua_service.read_node(f"ns=4;s=Bath[{bath_num}].InTime")
                    out_time = await opcua_service.read_node(f"ns=4;s=Bath[{bath_num}].OutTime")
                    d_time = await opcua_service.read_node(f"ns=4;s=Bath[{bath_num}].dTime")
                    
                    # Используем Pallete как номер подвеса
                    if pallete is None or pallete == 0:
                        continue
                    
                    try:
                        hanger_num = int(pallete)
                    except (ValueError, TypeError):
                        continue
                    
                    # Создаём или обновляем подвес
                    if hanger_num not in self.hangers:
                        self.hangers[hanger_num] = Hanger(
                            hanger_number=hanger_num,
                            pallete_data=str(pallete),
                            first_seen=datetime.now().isoformat()
                        )
                    
                    hanger = self.hangers[hanger_num]
                    hanger.pallete_data = str(pallete)
                    hanger.last_updated = datetime.now().isoformat()
                    hanger.current_bath = bath_num  # Устанавливаем текущую ванну
                    
                    # Добавляем запись о ванне если её ещё нет
                    bath_exists = any(b.bath_number == bath_num for b in hanger.baths_history)
                    if not bath_exists:
                        hanger.baths_history.append(BathRecord(
                            bath_number=bath_num,
                            in_time=str(in_time) if in_time else None,
                            out_time=str(out_time) if out_time else None,
                            duration=str(d_time) if d_time else None
                        ))
                    else:
                        # Обновляем существующую запись
                        for record in hanger.baths_history:
                            if record.bath_number == bath_num:
                                record.out_time = str(out_time) if out_time else None
                                record.duration = str(d_time) if d_time else None
                    
                    self.bath_to_hanger[bath_num] = hanger_num
                else:
                    # Ванна свободна
                    if bath_num in self.bath_to_hanger:
                        del self.bath_to_hanger[bath_num]
            
            self.save_cache()
            logger.debug(f"[Hanger Service] Scanned all baths, tracking {len(self.hangers)} hangers")
            
        except Exception as e:
            logger.error(f"[Hanger Service] Error scanning baths: {e}")
    
    def get_hanger(self, hanger_number: int) -> Optional[Hanger]:
        """Получить данные подвеса по номеру."""
        return self.hangers.get(hanger_number)
    
    def get_all_hangers(self) -> List[Hanger]:
        """Получить все подвесы."""
        return sorted(self.hangers.values(), key=lambda h: h.hanger_number)
    
    def get_active_hangers(self) -> List[Hanger]:
        """Получить активные подвесы (сейчас в какой-то ванне)."""
        return sorted(
            [h for h in self.hangers.values() if h.current_bath is not None],
            key=lambda h: h.hanger_number
        )
    
    def get_hanger_in_bath(self, bath_number: int) -> Optional[Hanger]:
        """Получить подвес который сейчас в ванне."""
        hanger_num = self.bath_to_hanger.get(bath_number)
        if hanger_num is not None:
            return self.hangers.get(hanger_num)
        return None
    
    def clear_cache(self):
        """Очистить кеш."""
        self.hangers.clear()
        self.bath_to_hanger.clear()
        self.save_cache()
        logger.info("[Hanger Service] Cache cleared")


# Singleton instance
hanger_service = HangerService()
