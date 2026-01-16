"""
OPC UA Service - подключение к OMRON PLC через OPC UA.
Асинхронное чтение данных с кешированием.
Использует best practices из asyncua документации для стабильного соединения.
"""
import asyncio
import logging
import time
import socket
from datetime import datetime
from typing import Optional, Dict, Any, List
from enum import Enum
from collections import deque

from app.core.config import settings

logger = logging.getLogger(__name__)

try:
    from asyncua import Client, ua
    OPCUA_AVAILABLE = True
except ImportError:
    OPCUA_AVAILABLE = False
    logger.warning("[OPC UA] asyncua not installed. Run: pip install asyncua")


class OPCUAState(Enum):
    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    ERROR = "error"


class ConnectionMetrics:
    """Метрики подключения для диагностики проблем."""
    
    def __init__(self, history_size: int = 100):
        self.history_size = history_size
        
        # Время операций (последние N значений)
        self.connect_times: deque = deque(maxlen=history_size)
        self.read_times: deque = deque(maxlen=history_size)
        self.health_check_times: deque = deque(maxlen=history_size)
        
        # Счетчики
        self.total_connects = 0
        self.total_disconnects = 0
        self.total_reads = 0
        self.total_errors = 0
        self.total_timeouts = 0
        self.total_session_errors = 0
        
        # Время работы
        self.last_connect_time: Optional[datetime] = None
        self.last_disconnect_time: Optional[datetime] = None
        self.last_error_time: Optional[datetime] = None
        self.last_error_message: Optional[str] = None
        
        # Uptime tracking
        self.session_start: Optional[datetime] = None
        self.longest_session_seconds: float = 0
        self.current_session_seconds: float = 0
        
        # Network latency
        self.last_ping_ms: Optional[float] = None
        self.ping_history: deque = deque(maxlen=history_size)
    
    def record_connect(self, duration_ms: float):
        self.connect_times.append(duration_ms)
        self.total_connects += 1
        self.last_connect_time = datetime.now()
        self.session_start = datetime.now()
        logger.info(f"[OPC UA Metrics] Connect took {duration_ms:.0f}ms")
    
    def record_disconnect(self, reason: str = "unknown"):
        self.total_disconnects += 1
        self.last_disconnect_time = datetime.now()
        
        # Calculate session duration
        if self.session_start:
            session_duration = (datetime.now() - self.session_start).total_seconds()
            self.current_session_seconds = session_duration
            if session_duration > self.longest_session_seconds:
                self.longest_session_seconds = session_duration
            logger.info(f"[OPC UA Metrics] Session ended after {session_duration:.1f}s, reason: {reason}")
        
        self.session_start = None
    
    def record_read(self, duration_ms: float):
        self.read_times.append(duration_ms)
        self.total_reads += 1
    
    def record_health_check(self, duration_ms: float):
        self.health_check_times.append(duration_ms)
    
    def record_error(self, error_type: str, message: str):
        self.total_errors += 1
        self.last_error_time = datetime.now()
        self.last_error_message = f"{error_type}: {message}"
        
        if "timeout" in error_type.lower() or "timeout" in message.lower():
            self.total_timeouts += 1
        if "session" in message.lower():
            self.total_session_errors += 1
        
        logger.warning(f"[OPC UA Metrics] Error recorded: {error_type}")
    
    def record_ping(self, latency_ms: float):
        self.last_ping_ms = latency_ms
        self.ping_history.append(latency_ms)
    
    def get_stats(self) -> dict:
        """Получить статистику метрик."""
        def avg(values) -> Optional[float]:
            if not values:
                return None
            return sum(values) / len(values)
        
        def percentile(values, p) -> Optional[float]:
            if not values:
                return None
            sorted_vals = sorted(values)
            idx = int(len(sorted_vals) * p / 100)
            return sorted_vals[min(idx, len(sorted_vals) - 1)]
        
        # Current session uptime
        current_uptime = 0
        if self.session_start:
            current_uptime = (datetime.now() - self.session_start).total_seconds()
        
        return {
            "connects": {
                "total": self.total_connects,
                "avg_ms": round(avg(self.connect_times) or 0, 1),
                "p95_ms": round(percentile(self.connect_times, 95) or 0, 1),
                "last": self.last_connect_time.isoformat() if self.last_connect_time else None,
            },
            "disconnects": {
                "total": self.total_disconnects,
                "last": self.last_disconnect_time.isoformat() if self.last_disconnect_time else None,
            },
            "reads": {
                "total": self.total_reads,
                "avg_ms": round(avg(self.read_times) or 0, 1),
                "p95_ms": round(percentile(self.read_times, 95) or 0, 1),
            },
            "health_checks": {
                "avg_ms": round(avg(self.health_check_times) or 0, 1),
                "p95_ms": round(percentile(self.health_check_times, 95) or 0, 1),
            },
            "errors": {
                "total": self.total_errors,
                "timeouts": self.total_timeouts,
                "session_errors": self.total_session_errors,
                "last_error": self.last_error_message,
                "last_error_time": self.last_error_time.isoformat() if self.last_error_time else None,
            },
            "session": {
                "current_uptime_seconds": round(current_uptime, 1),
                "longest_session_seconds": round(self.longest_session_seconds, 1),
            },
            "network": {
                "last_ping_ms": round(self.last_ping_ms, 1) if self.last_ping_ms else None,
                "avg_ping_ms": round(avg(self.ping_history) or 0, 1),
                "p95_ping_ms": round(percentile(self.ping_history, 95) or 0, 1),
            }
        }


class OPCUAService:
    """OPC UA сервис для подключения к OMRON PLC."""
    
    def __init__(self):
        self._client: Optional[Client] = None
        self._connected: bool = False
        self._state: OPCUAState = OPCUAState.DISCONNECTED
        self._lock = asyncio.Lock()
        
        # Метрики подключения
        self._metrics = ConnectionMetrics()
        
        # Кеш значений узлов
        self._node_cache: Dict[str, Any] = {}
        self._cache_time: Dict[str, datetime] = {}
        self._cache_ttl: int = 10  # Секунды
        
        # Кеш ошибок для предотвращения спама в логах
        self._error_cache: Dict[str, datetime] = {}
        self._error_log_ttl: int = 300  # Логировать ошибку для узла не чаще раза в 5 минут
        
        # Батчинг ошибок - собираем ошибки и логируем группами
        self._error_batch: Dict[str, List[str]] = {}  # error_type -> [node_ids]
        self._error_batch_time: Optional[datetime] = None
        self._error_batch_interval: int = 5  # Логировать батч раз в 5 секунд
        
        # Черный список узлов, которые постоянно дают ошибки
        self._blacklisted_nodes: set = set()
        
        # Экспоненциальная задержка при переподключении
        self._reconnect_attempts: int = 0
        self._last_reconnect_time: Optional[datetime] = None
        self._max_reconnect_delay: int = 60  # Максимум 60 секунд между попытками
        
        self._stats = {
            'connections': 0,
            'reads': 0,
            'errors': 0,
            'cache_hits': 0,
        }
    
    @property
    def metrics(self) -> ConnectionMetrics:
        return self._metrics
    
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
    
    async def connect(self) -> bool:
        """
        Подключиться к OPC UA серверу.
        Использует рекомендованные настройки из asyncua документации.
        """
        if not OPCUA_AVAILABLE:
            logger.error("[OPC UA] Library not available")
            return False
        
        # Проверяем, не идёт ли уже подключение
        if self._state == OPCUAState.CONNECTING:
            return False
        
        if self._connected:
            return True
        
        # Экспоненциальная задержка при переподключении
        if self._last_reconnect_time:
            now = datetime.now()
            elapsed = (now - self._last_reconnect_time).total_seconds()
            
            # Вычисляем задержку: 2^attempts секунд, но не больше max_reconnect_delay
            delay = min(2 ** self._reconnect_attempts, self._max_reconnect_delay)
            
            if elapsed < delay:
                remaining = delay - elapsed
                logger.debug(f"[OPC UA] Waiting {remaining:.1f}s before reconnect attempt")
                return False
        
        async with self._lock:
            # Повторная проверка под локом
            if self._connected:
                return True
            
            connect_start = time.time()
            
            try:
                self._state = OPCUAState.CONNECTING
                self._client = None  # Полностью отбрасываем старый клиент
                self._last_reconnect_time = datetime.now()
                
                logger.info(f"[OPC UA] Attempting connection to {settings.OPCUA_ENDPOINT} (attempt {self._reconnect_attempts + 1})")
                
                # Создаем клиент с рекомендованными настройками
                # Основано на HaConfig из asyncua документации
                client = Client(settings.OPCUA_ENDPOINT, timeout=30)
                
                # Настройки таймаутов (в миллисекундах)
                # Основано на best practices для промышленных систем
                client.session_timeout = 60000  # 60 секунд - session timeout
                client.secure_channel_timeout = 3600000  # 1 час - secure channel lifetime
                
                # Устанавливаем имя сессии для идентификации
                client.name = "Ekranchik_OPC_Client"
                client.description = "Production Line Monitoring System"
                
                # Подключаемся с увеличенным таймаутом (30 секунд вместо 20)
                logger.debug(f"[OPC UA] Connecting with 30s timeout...")
                await asyncio.wait_for(client.connect(), timeout=30.0)
                
                # Проверяем соединение чтением корневого узла
                try:
                    logger.debug(f"[OPC UA] Verifying connection with root node check...")
                    root = client.get_node(ua.ObjectIds.RootFolder)
                    await asyncio.wait_for(root.get_children(), timeout=10.0)
                    logger.debug("[OPC UA] Connection verified with root node check")
                except asyncio.TimeoutError:
                    logger.warning("[OPC UA] Root node check timeout")
                    await client.disconnect()
                    raise
                except Exception as e:
                    logger.warning(f"[OPC UA] Root node check failed: {e}")
                    await client.disconnect()
                    raise
                
                self._client = client
                self._connected = True
                self._state = OPCUAState.CONNECTED
                self._stats['connections'] += 1
                self._node_cache.clear()
                self._cache_time.clear()
                # Очищаем черный список при переподключении
                self._blacklisted_nodes.clear()
                
                # Сбрасываем счетчик попыток при успешном подключении
                self._reconnect_attempts = 0
                
                # Записываем метрику успешного подключения
                connect_duration_ms = (time.time() - connect_start) * 1000
                self._metrics.record_connect(connect_duration_ms)
                
                logger.info(f"[OPC UA] Connected to {settings.OPCUA_ENDPOINT} (session: {client.name})")
                return True
                
            except asyncio.TimeoutError:
                self._reconnect_attempts += 1
                logger.error(f"[OPC UA] Connection timeout (attempt {self._reconnect_attempts}). Server may be unreachable or network is slow.")
                self._connected = False
                self._state = OPCUAState.ERROR
                self._client = None
                self._stats['errors'] += 1
                self._metrics.record_error("TimeoutError", f"Connection timeout (attempt {self._reconnect_attempts})")
                return False
            except Exception as e:
                self._reconnect_attempts += 1
                error_str = str(e).lower()
                
                # Диагностируем типы ошибок
                if "connection refused" in error_str or "refused" in error_str:
                    logger.error(f"[OPC UA] Connection refused (attempt {self._reconnect_attempts}). Check if OPC UA server is running on {settings.OPCUA_ENDPOINT}")
                    self._metrics.record_error("ConnectionRefused", f"Connection refused (attempt {self._reconnect_attempts})")
                elif "timeout" in error_str:
                    logger.error(f"[OPC UA] Connection timeout (attempt {self._reconnect_attempts}). Network may be slow or server unreachable.")
                    self._metrics.record_error("TimeoutError", f"Connection timeout (attempt {self._reconnect_attempts})")
                elif "name or service not known" in error_str or "getaddrinfo failed" in error_str:
                    logger.error(f"[OPC UA] Cannot resolve hostname (attempt {self._reconnect_attempts}). Check endpoint: {settings.OPCUA_ENDPOINT}")
                    self._metrics.record_error("DNSError", f"Cannot resolve hostname (attempt {self._reconnect_attempts})")
                else:
                    logger.error(f"[OPC UA] Connection failed (attempt {self._reconnect_attempts}): {e}")
                    self._metrics.record_error(type(e).__name__, str(e)[:100])
                
                self._connected = False
                self._state = OPCUAState.ERROR
                self._client = None
                self._stats['errors'] += 1
                return False    
    async def ensure_connected(self) -> bool:
        """
        Проверить соединение и переподключиться при необходимости.
        Использует легковесную проверку через корневой узел.
        """
        if not self._connected or not self._client:
            return await self.connect()
        
        # Проверяем живость соединения простым запросом
        health_start = time.time()
        try:
            # Используем ObjectIds из asyncua для стандартного узла
            root = self._client.get_node(ua.ObjectIds.RootFolder)
            await asyncio.wait_for(root.get_children(), timeout=5.0)
            
            # Записываем метрику health check
            health_duration_ms = (time.time() - health_start) * 1000
            self._metrics.record_health_check(health_duration_ms)
            
            return True
        except asyncio.TimeoutError:
            logger.warning("[OPC UA] Health check timeout, reconnecting")
            self._metrics.record_error("TimeoutError", "Health check timeout")
            self._metrics.record_disconnect("health_check_timeout")
            # Жесткий сброс при таймауте
            self._connected = False
            self._state = OPCUAState.DISCONNECTED
            self._client = None
            return await self.connect()
        except Exception as e:
            error_str = str(e).lower()
            error_type = type(e).__name__
            
            # Определяем критические ошибки сессии
            session_invalid = any(err in error_str for err in [
                "badsessionidinvalid",
                "badsessionclosed",
                "badsessionnotactivated"
            ])
            
            if session_invalid:
                logger.info(f"[OPC UA] Session invalid ({error_type}), performing hard reset")
                self._metrics.record_error("SessionError", f"Session invalid: {error_type}")
                self._metrics.record_disconnect("session_invalid")
                # Жесткий сброс - не пытаемся отключаться с невалидной сессией
                self._connected = False
                self._state = OPCUAState.DISCONNECTED
                self._client = None
                return await self.connect()
            
            # Для других ошибок пытаемся корректно отключиться
            logger.warning(f"[OPC UA] Health check failed ({error_type}): {e}")
            self._metrics.record_error(error_type, str(e)[:100])
            self._metrics.record_disconnect(f"health_check_failed_{error_type}")
            
            if self._client:
                try:
                    await asyncio.wait_for(self._client.disconnect(), timeout=2.0)
                except asyncio.TimeoutError:
                    logger.debug("[OPC UA] Disconnect timed out during health check")
                except Exception as ex:
                    # Подавляем ошибки невалидной сессии при отключении
                    ex_str = str(ex).lower()
                    if not any(err in ex_str for err in ["badsessionidinvalid", "badsessionclosed"]):
                        logger.debug(f"[OPC UA] Error during disconnect: {ex}")

            self._connected = False
            self._state = OPCUAState.DISCONNECTED
            self._client = None
            return await self.connect()
    
    async def disconnect(self) -> None:
        """Отключиться от OPC UA сервера."""
        # Логируем накопленные ошибки перед отключением
        await self._flush_error_batch()
        
        # Записываем метрику отключения
        self._metrics.record_disconnect("manual_disconnect")
        
        if self._client:
            try:
                await self._client.disconnect()
            except Exception as e:
                logger.warning(f"[OPC UA] Disconnect error: {e}")
            self._client = None
        
        self._connected = False
        self._state = OPCUAState.DISCONNECTED
        
        # Очищаем все кеши
        self._node_cache.clear()
        self._cache_time.clear()
        self._error_cache.clear()
        self._blacklisted_nodes.clear()
        self._error_batch.clear()
        self._error_batch_time = None
        
        logger.info("[OPC UA] Disconnected and cleared all caches")
    
    async def _batch_error(self, error_type: str, node_id: str) -> None:
        """Добавить ошибку в батч для группового логирования."""
        now = datetime.now()
        
        # Инициализируем батч если нужно
        if self._error_batch_time is None:
            self._error_batch_time = now
        
        # Добавляем ошибку в батч
        if error_type not in self._error_batch:
            self._error_batch[error_type] = []
        
        # Добавляем только если узла еще нет в батче
        if node_id not in self._error_batch[error_type]:
            self._error_batch[error_type].append(node_id)
        
        # Если прошло достаточно времени - логируем батч
        if (now - self._error_batch_time).total_seconds() >= self._error_batch_interval:
            await self._flush_error_batch()
    
    async def _flush_error_batch(self) -> None:
        """Залогировать накопленные ошибки одной строкой для каждого типа."""
        if not self._error_batch:
            return
        
        for error_type, node_ids in self._error_batch.items():
            count = len(node_ids)
            
            # Показываем первые 3 узла как примеры
            examples = node_ids[:3]
            examples_str = ", ".join(examples)
            
            if count > 3:
                examples_str += f" и еще {count - 3}"
            
            # Разные уровни логирования
            if error_type == "TimeoutError":
                logger.warning(f"[OPC UA] {error_type} для {count} узлов: {examples_str}")
            elif "badnodeidunknown" in error_type.lower():
                logger.warning(f"[OPC UA] Узлы не найдены ({count}): {examples_str}")
            elif "badattributeidinvalid" in error_type.lower():
                logger.warning(f"[OPC UA] Неверные атрибуты ({count}): {examples_str}")
            else:
                logger.error(f"[OPC UA] {error_type} для {count} узлов: {examples_str}")
        
        # Очищаем батч
        self._error_batch.clear()
        self._error_batch_time = None
    
    async def read_node(self, node_id: str) -> Optional[Any]:
        """
        Прочитать значение узла с кешированием.
        Использует улучшенную обработку ошибок на основе asyncua best practices.
        """
        # Проверяем черный список
        if node_id in self._blacklisted_nodes:
            return None
        
        if not self._connected or not self._client:
            if not await self.connect():
                return None
        
        # Проверяем кеш
        now = datetime.now()
        if node_id in self._cache_time:
            age = (now - self._cache_time[node_id]).total_seconds()
            if age < self._cache_ttl:
                self._stats['cache_hits'] += 1
                return self._node_cache.get(node_id)
        
        read_start = time.time()
        try:
            node = self._client.get_node(node_id)
            value = await asyncio.wait_for(node.get_value(), timeout=5.0)
            
            # Кешируем значение
            self._node_cache[node_id] = value
            self._cache_time[node_id] = now
            self._stats['reads'] += 1
            
            # Записываем метрику чтения
            read_duration_ms = (time.time() - read_start) * 1000
            self._metrics.record_read(read_duration_ms)
            
            return value
            
        except asyncio.TimeoutError:
            logger.warning(f"[OPC UA] Read timeout for node {node_id}, reconnecting")
            self._metrics.record_error("TimeoutError", f"Read timeout for {node_id}")
            self._metrics.record_disconnect("read_timeout")
            # Жесткий сброс при таймауте
            self._connected = False
            self._state = OPCUAState.DISCONNECTED
            self._client = None
            self._stats['errors'] += 1
            return None
            
        except Exception as e:
            error_str = str(e).lower()
            error_type = type(e).__name__
            
            # Критические ошибки сессии - требуют жесткого сброса
            session_errors = [
                "badsessionidinvalid",
                "badsessionclosed",
                "badsessionnotactivated",
            ]
            
            # Критические ошибки соединения - требуют переподключения
            connection_errors = [
                "failed to send request",
                "badsecurechannelclosed",
                "badconnectionclosed",
                "connection refused",
                "badservernotconnected",
                "badcommunicationerror",
            ]
            
            is_session_error = any(err in error_str for err in session_errors)
            is_connection_error = any(err in error_str for err in connection_errors)
            
            if is_session_error:
                logger.warning(f"[OPC UA] Session error for node {node_id} ({error_type}), hard reset")
                self._metrics.record_error("SessionError", f"Session error for {node_id}")
                self._metrics.record_disconnect("session_error_read")
                # Жесткий сброс - не пытаемся отключаться
                self._connected = False
                self._state = OPCUAState.DISCONNECTED
                self._client = None
                
            elif is_connection_error:
                logger.warning(f"[OPC UA] Connection error for node {node_id}: {e}")
                self._metrics.record_error("ConnectionError", f"Connection error for {node_id}")
                self._metrics.record_disconnect("connection_error_read")
                # Попытка корректного отключения
                if self._client:
                    try:
                        await asyncio.wait_for(self._client.disconnect(), timeout=2.0)
                    except asyncio.TimeoutError:
                        logger.debug("[OPC UA] Disconnect timeout on connection loss")
                    except Exception as ex:
                        # Подавляем ошибки невалидной сессии
                        ex_str = str(ex).lower()
                        if not any(err in ex_str for err in session_errors):
                            logger.debug(f"[OPC UA] Error during disconnect: {ex}")
                
                self._connected = False
                self._state = OPCUAState.DISCONNECTED
                self._client = None
                
            else:
                # Ошибки узла - не требуют переподключения
                # Добавляем в черный список узлы с постоянными ошибками
                if "badattributeidinvalid" in error_str or "badnodeidunknown" in error_str:
                    self._blacklisted_nodes.add(node_id)
                    logger.info(f"[OPC UA] Node {node_id} blacklisted ({error_type})")
                
                # Батчинг ошибок - собираем и логируем группами
                await self._batch_error(error_type, node_id)
            
            self._stats['errors'] += 1
            return None
    
    async def read_nodes(self, node_ids: List[str]) -> Dict[str, Any]:
        """
        Прочитать несколько узлов параллельно.
        Использует asyncio.gather для одновременного чтения.
        
        Рекомендуется для небольшого количества узлов (1-10).
        Для большего количества используйте read_nodes_batch().
        """
        if not node_ids:
            return {}
        
        # Создаем задачи для параллельного чтения
        tasks = [self.read_node(node_id) for node_id in node_ids]
        
        # Выполняем все задачи параллельно
        values = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Формируем результат
        results = {}
        for node_id, value in zip(node_ids, values):
            # Если произошла ошибка, значение будет исключением
            if isinstance(value, Exception):
                results[node_id] = None
            else:
                results[node_id] = value
        
        return results
    
    async def read_nodes_batch(self, node_ids: List[str]) -> Dict[str, Any]:
        """
        Пакетное чтение узлов через параллельные запросы.
        Более эффективно для большого количества узлов (>10).
        
        Преимущества:
        - Все узлы читаются параллельно одним пакетом
        - Автоматическое кеширование результатов
        - Фильтрация узлов из черного списка
        - Обработка ошибок для каждого узла отдельно
        """
        if not node_ids:
            return {}
        
        # Фильтруем узлы из черного списка
        valid_node_ids = [nid for nid in node_ids if nid not in self._blacklisted_nodes]
        
        if not valid_node_ids:
            return {nid: None for nid in node_ids}
        
        if not self._connected or not self._client:
            if not await self.connect():
                return {nid: None for nid in node_ids}
        
        try:
            # Создаем узлы
            nodes = [self._client.get_node(node_id) for node_id in valid_node_ids]
            
            # Читаем все узлы одним запросом через uaclient
            # Это более эффективно чем множественные read_value()
            results_dict = {}
            
            # Используем параллельное чтение с таймаутом
            read_tasks = [
                asyncio.wait_for(node.get_value(), timeout=5.0) 
                for node in nodes
            ]
            values = await asyncio.gather(*read_tasks, return_exceptions=True)
            
            now = datetime.now()
            for node_id, value in zip(valid_node_ids, values):
                if isinstance(value, Exception):
                    results_dict[node_id] = None
                    # Обрабатываем ошибки
                    error_str = str(value).lower()
                    if "badnodeidunknown" in error_str or "badattributeidinvalid" in error_str:
                        self._blacklisted_nodes.add(node_id)
                else:
                    results_dict[node_id] = value
                    # Кешируем успешные значения
                    self._node_cache[node_id] = value
                    self._cache_time[node_id] = now
                    self._stats['reads'] += 1
            
            # Добавляем None для узлов из черного списка
            for node_id in node_ids:
                if node_id not in results_dict:
                    results_dict[node_id] = None
            
            return results_dict
            
        except asyncio.TimeoutError:
            logger.warning(f"[OPC UA] Batch read timeout for {len(node_ids)} nodes")
            self._connected = False
            self._state = OPCUAState.DISCONNECTED
            self._client = None
            return {nid: None for nid in node_ids}
            
        except Exception as e:
            error_str = str(e).lower()
            
            # Проверяем на критические ошибки
            if any(err in error_str for err in ["badsessionidinvalid", "badsessionclosed"]):
                logger.warning(f"[OPC UA] Session error in batch read, hard reset")
                self._connected = False
                self._state = OPCUAState.DISCONNECTED
                self._client = None
            else:
                logger.error(f"[OPC UA] Batch read error: {e}")
            
            return {nid: None for nid in node_ids}
    
    async def browse_node(self, node_id: str) -> List[Dict[str, str]]:
        """Получить дочерние узлы."""
        if not self._connected:
            if not await self.connect():
                return []
        
        try:
            node = self._client.get_node(node_id)
            children = await node.get_children()
            
            result = []
            for child in children:
                try:
                    result.append({
                        'id': child.nodeid.to_string(),
                        'name': str(child.nodeid),
                    })
                except:
                    pass
            
            return result
            
        except Exception as e:
            logger.error(f"[OPC UA] Browse error for {node_id}: {e}")
            return []
    
    async def browse_recursive(self, node_id: str, max_depth: int = 10, depth: int = 0) -> List[Dict[str, Any]]:
        """Рекурсивный просмотр всех узлов (только структура, без чтения значений)."""
        if not self._connected:
            if not await self.connect():
                return []
        
        if depth > max_depth:
            return []
        
        try:
            node = self._client.get_node(node_id)
            children = await node.get_children()
            
            result = []
            for child in children:
                try:
                    child_id = child.nodeid.to_string()
                    child_name = str(child.nodeid)
                    
                    result.append({
                        'id': child_id,
                        'name': child_name,
                        'depth': depth,
                    })
                    
                    # Рекурсивно сканируем дочерние узлы (только на первых 2 уровнях)
                    if depth < 2:
                        try:
                            grandchildren = await child.get_children()
                            if grandchildren:
                                child_results = await self.browse_recursive(child_id, max_depth, depth + 1)
                                result.extend(child_results)
                        except:
                            pass
                except:
                    pass
            
            return result
            
        except Exception as e:
            logger.error(f"[OPC UA] Recursive browse error for {node_id}: {e}")
            return []
    
    def get_diagnostics(self) -> dict:
        """Диагностическая информация."""
        return {
            'available': OPCUA_AVAILABLE,
            'enabled': settings.OPCUA_ENABLED,
            'state': self._state.value,
            'connected': self._connected,
            'endpoint': settings.OPCUA_ENDPOINT if settings.OPCUA_ENABLED else None,
            'stats': self._stats.copy(),
            'cached_nodes': len(self._node_cache),
            'blacklisted_nodes': len(self._blacklisted_nodes),
            'reconnect_attempts': self._reconnect_attempts,
            'metrics': self._metrics.get_stats(),
        }
    
    async def ping_server(self) -> Optional[float]:
        """
        Измерить сетевую задержку до OPC UA сервера.
        Возвращает время в миллисекундах или None при ошибке.
        """
        from urllib.parse import urlparse
        
        parsed = urlparse(settings.OPCUA_ENDPOINT)
        host = parsed.hostname
        port = parsed.port or 4840
        
        try:
            start = time.time()
            # Простое TCP соединение для измерения latency
            reader, writer = await asyncio.wait_for(
                asyncio.open_connection(host, port),
                timeout=5.0
            )
            latency_ms = (time.time() - start) * 1000
            writer.close()
            await writer.wait_closed()
            
            # Записываем метрику
            self._metrics.record_ping(latency_ms)
            
            return latency_ms
        except asyncio.TimeoutError:
            logger.warning(f"[OPC UA] Ping timeout to {host}:{port}")
            return None
        except Exception as e:
            logger.warning(f"[OPC UA] Ping failed to {host}:{port}: {e}")
            return None


# Singleton instance
opcua_service = OPCUAService()
