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

# Проверка наличия библиотеки asyncua
OPCUA_AVAILABLE = True
try:
    from asyncua import Client, ua
    from asyncua.ua.uaerrors import BadTooManySessions, BadSessionIdInvalid
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
        self._running = False
        self._connected = False
        self._state = OPCUAState.DISCONNECTED
        self._last_update = datetime.min
        self._batch_size = 100
        self._client: Optional[Client] = None

        if settings.SIMULATION_ENABLED:
            self._url = settings.OPCUA_SIM_ENDPOINT
            self._poll_interval = settings.OPCUA_SIM_POLL_INTERVAL
            logger.info(f"[OPC UA] Активирован режим симуляции. Эндпоинт: {self._url}")
        else:
            self._url = settings.OPCUA_ENDPOINT
            self._poll_interval = settings.OPCUA_POLL_INTERVAL
            logger.info(f"[OPC UA] Активирован режим реального OPC UA сервера. Эндпоинт: {self._url}")

        
        # Кэш: { "ns=4;s=Name": value }
        self._cache: Dict[str, Any] = {}
        # Список переменных для постоянного чтения
        self._monitored_nodes: Set[str] = set()
        # Черный список (битые адреса)
        self._blacklist: Set[str] = set()
        
        # Статистика (с защитой от переполнения)
        self._stats = {
            'connections': 0,
            'reads': 0,
            'errors': 0,
            'cache_hits': 0,
        }
        self._stats_max = 1_000_000_000  # Сброс после 1 млрд
        self._client: Optional[Client] = None
    
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
        import sys
        
        # Размер кэша в памяти (приблизительно)
        cache_size_bytes = sys.getsizeof(self._cache)
        for k, v in self._cache.items():
            cache_size_bytes += sys.getsizeof(k) + sys.getsizeof(v)
        
        return {
            'available': OPCUA_AVAILABLE,
            'enabled': settings.OPCUA_ENABLED,
            'connected': self._connected,
            'state': self._state.value,
            'endpoint': self._url,
            'stats': self._stats.copy(),
            'monitored_nodes': len(self._monitored_nodes),
            'blacklisted_nodes': len(self._blacklist),
            'cache_entries': len(self._cache),
            'cache_size_kb': round(cache_size_bytes / 1024, 2),
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
        if not self._client or not self._connected:
            return []
        
        try:
            node = self._client.get_node(node_id)
            children = await node.get_children()
            results = []
            for child in children:
                # Получаем имя и ID
                name = await child.read_display_name()
                child_node_id = child.nodeid.to_string()
                results.append({"name": name.Text, "id": child_node_id})
            return results
        except Exception as e:
            logger.error(f"Browse error: {e}")
            return []

    
    async def browse_recursive(self, node_id: str, max_depth: int = 3) -> List[dict]:
        """Рекурсивный обход узлов (совместимость с API)."""
        return []
    
    async def read_nodes_batch(self, node_ids: List[str]) -> Dict[str, Any]:
        """Пакетное чтение узлов из кэша (совместимость с API)."""
        # Возвращаем значения из кэша
        return {node_id: self._cache.get(node_id) for node_id in node_ids}
    
    async def start(self):
        """Запуск фоновой задачи опроса."""
        if not settings.OPCUA_ENABLED:
            logger.info("[OPC UA] Сервис OPC UA отключен в настройках.")
            return
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
        Мгновенно вернуть значение из памяти (RAM).
        НЕ делает сетевых запросов к ПЛК!
        Если узла нет в кэше — возвращает None.
        """
        self._stats['cache_hits'] += 1
        # Защита от переполнения счётчика
        if self._stats['cache_hits'] > self._stats_max:
            self._stats['cache_hits'] = 0
            logger.info("[OPC UA] Stats counter reset (cache_hits)")
        return self._cache.get(node_id)
    
    async def read_node(self, node_id: str) -> Optional[Any]:
        """
        Прочитать значение узла из кэша (совместимость с line_monitor).
        НЕ делает сетевых запросов — только чтение из RAM.
        """
        return self.get_value(node_id)
    
    def register_nodes(self, node_ids: List[str]) -> None:
        """
        Зарегистрировать узлы для постоянного опроса.
        Worker будет читать эти узлы каждый цикл и обновлять кэш.
        Вызывать при старте line_monitor.
        """
        before = len(self._monitored_nodes)
        self._monitored_nodes.update(node_ids)
        added = len(self._monitored_nodes) - before
        if added > 0:
            logger.info(f"[OPC UA] Registered {added} new nodes for polling (total: {len(self._monitored_nodes)})")
    
    def unregister_nodes(self, node_ids: List[str]) -> None:
        """Убрать узлы из списка опроса."""
        for node_id in node_ids:
            self._monitored_nodes.discard(node_id)
            self._cache.pop(node_id, None)
    
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
            try:
                # 1. Создаем клиента
                logger.debug(f"[OPC UA] Creating client for {self._url}")
                self._client = Client(url=self._url, timeout=10)
                
                # === ВАЖНЫЕ НАСТРОЙКИ ДЛЯ OMRON ===
                # Таймаут сессии 1 час - если опрашиваем постоянно, она не умрет
                self._client.session_timeout = 3600000
                
                # ОТКЛЮЧАЕМ ВСТРОЕННЫЙ WATCHDOG/KEEP-ALIVE
                # 0 = не слать пустые пакеты фоном
                # Наш опрос (_poll_data_batched) держит сессию живой
                self._client.keepalive_interval = 0
                
                # Увеличиваем таймаут канала безопасности (реже обновляет ключи)
                self._client.secure_channel_timeout = 3600000
                # ===================================
                
                logger.info(f"[OPC UA] Подключение к {self._url}...")
                self._state = OPCUAState.CONNECTING
                
                # 2. Подключаемся с таймаутом (чуть больше времени на старт)
                try:
                    await asyncio.wait_for(self._client.connect(), timeout=20.0)
                except asyncio.TimeoutError:
                    logger.error("[OPC UA] Таймаут подключения (20 сек)")
                    self._stats['errors'] += 1
                    await asyncio.sleep(10)  # Даем ПЛК время сбросить слот
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
                        await self._poll_data_batched(self._client)
                        
                        # Вычисляем время сна для стабильного ритма
                        elapsed = time.time() - start_time
                        sleep_time = max(0, self._poll_interval - elapsed)
                        await asyncio.sleep(sleep_time)
                finally:
                    # Гарантируем корректное отключение
                    try:
                        await asyncio.wait_for(self._client.disconnect(), timeout=2.0)
                    except:
                        pass
            
            except BadSessionIdInvalid as e:
                # Сессия "испортилась" - ПЛК её убил
                self._connected = False
                self._state = OPCUAState.ERROR
                self._stats['errors'] += 1
                logger.error(f"[OPC UA] BadSessionIdInvalid: {e}. Ждем 10 сек очистки слота на ПЛК...")
                # ВАЖНО ДЛЯ OMRON: даем время сбросить зомби-сессию
                await asyncio.sleep(10)
            
            except BadTooManySessions:
                self._connected = False
                self._state = OPCUAState.ERROR
                self._stats['errors'] += 1
                logger.error("[OPC UA] Ошибка: Нет свободных слотов! Ждем 20 сек очистки...")
                await asyncio.sleep(20)
            
            except (OSError, asyncio.TimeoutError) as e:
                self._connected = False
                self._state = OPCUAState.ERROR
                self._stats['errors'] += 1
                logger.warning(f"[OPC UA] Ошибка сети: {type(e).__name__}: {e}. Ждем 10 сек...")
                # Omron держит порт занятым (TIME_WAIT), нужна пауза
                await asyncio.sleep(10)
            
            except Exception as e:
                self._connected = False
                self._state = OPCUAState.ERROR
                self._stats['errors'] += 1
                logger.error(f"[OPC UA] Критическая ошибка: {type(e).__name__}: {e}", exc_info=True)
                
                # Если слишком много ошибок подряд - перезапускаем бекенд
                if self._stats['errors'] > 10:
                    logger.critical("[OPC UA] Слишком много ошибок! Перезапуск бекенда...")
                    import os
                    os._exit(1)  # Принудительный выход, launcher перезапустит
                
                await asyncio.sleep(5)
            
            finally:
                self._connected = False
                self._state = OPCUAState.DISCONNECTED
                self._last_update = datetime.min
                self._client = None
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
                # Используем read_values() вместо несуществующего read_attributes()
                data_values = await client.read_values(ua_nodes)
                
                # Обновляем кэш, проверяя каждое значение
                for node_id, value in zip(chunk, data_values):
                    if value is not None:
                        self._cache[node_id] = value
                    else:
                        logger.warning(f"Null value for node {node_id}")
                        # Можно добавить логику добавления в blacklist здесь, если нужно
                        # self._blacklist.add(node_id)
                
                updated_count += len(data_values)
                self._stats['reads'] += len(data_values)
                # Защита от переполнения счётчика
                if self._stats['reads'] > self._stats_max:
                    self._stats['reads'] = 0
                    logger.info("[OPC UA] Stats counter reset (reads)")
            
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
