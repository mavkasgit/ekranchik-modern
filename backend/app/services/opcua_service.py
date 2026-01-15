"""
OPC UA Service - подключение к OMRON PLC через OPC UA.
Асинхронное чтение данных с кешированием.
"""
import asyncio
import logging
from datetime import datetime
from typing import Optional, Dict, Any, List
from enum import Enum

from app.core.config import settings

logger = logging.getLogger(__name__)

try:
    from asyncua import Client
    OPCUA_AVAILABLE = True
except ImportError:
    OPCUA_AVAILABLE = False
    logger.warning("[OPC UA] asyncua not installed. Run: pip install asyncua")


class OPCUAState(Enum):
    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    ERROR = "error"


class OPCUAService:
    """OPC UA сервис для подключения к OMRON PLC."""
    
    def __init__(self):
        self._client: Optional[Client] = None
        self._connected: bool = False
        self._state: OPCUAState = OPCUAState.DISCONNECTED
        self._lock = asyncio.Lock()
        
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
    
    async def connect(self) -> bool:
        """Подключиться к OPC UA серверу."""
        if not OPCUA_AVAILABLE:
            logger.error("[OPC UA] Library not available")
            return False
        
        # Проверяем, не идёт ли уже подключение
        if self._state == OPCUAState.CONNECTING:
            return False
        
        if self._connected:
            return True
        
        async with self._lock:
            # Повторная проверка под локом
            if self._connected:
                return True
            
            try:
                self._state = OPCUAState.CONNECTING
                
                # Закрываем старый клиент если есть
                if self._client:
                    try:
                        await self._client.disconnect()
                    except:
                        pass
                    self._client = None
                
                client = Client(settings.OPCUA_ENDPOINT, timeout=10)
                # Устанавливаем параметры сессии для долгого соединения
                client.session_timeout = 3600000  # 1 час в миллисекундах
                await client.connect()
                
                self._client = client
                self._connected = True
                self._state = OPCUAState.CONNECTED
                self._stats['connections'] += 1
                self._node_cache.clear()
                self._cache_time.clear()
                # Очищаем черный список при переподключении - может узлы появились
                self._blacklisted_nodes.clear()
                
                logger.info(f"[OPC UA] Connected to {settings.OPCUA_ENDPOINT}")
                return True
                
            except Exception as e:
                logger.error(f"[OPC UA] Connection failed: {e}")
                self._connected = False
                self._state = OPCUAState.ERROR
                self._client = None
                self._stats['errors'] += 1
                return False
    
    async def ensure_connected(self) -> bool:
        """Проверить соединение и переподключиться при необходимости."""
        if not self._connected or not self._client:
            return await self.connect()
        
        # Проверяем живость соединения простым запросом
        try:
            # Пробуем прочитать корневой узел - это быстрая проверка
            root = self._client.get_node("i=84")  # Root folder
            await root.get_children()
            return True
        except Exception as e:
            error_str = str(e).lower()
            logger.warning(f"[OPC UA] Health check failed ({type(e).__name__}), reconnecting: {e}")
            self._connected = False
            self._state = OPCUAState.DISCONNECTED
            if self._client:
                try:
                    await self._client.disconnect()
                except:
                    pass
                self._client = None
            return await self.connect()
    
    async def disconnect(self) -> None:
        """Отключиться от OPC UA сервера."""
        # Логируем накопленные ошибки перед отключением
        await self._flush_error_batch()
        
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
        """Прочитать значение узла с кешированием."""
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
        
        try:
            node = self._client.get_node(node_id)
            value = await node.get_value()
            
            # Кешируем значение
            self._node_cache[node_id] = value
            self._cache_time[node_id] = now
            self._stats['reads'] += 1
            
            return value
            
        except Exception as e:
            error_str = str(e).lower()
            error_type = type(e).__name__
            
            # Критические ошибки соединения - нужно переподключиться
            connection_errors = [
                "failed to send request",
                "badsessionidinvalid",
                "badsecurechannelclosed",
                "badconnectionclosed",
                "connection refused",
                "timeout",
                "badservernotconnected",
                "badcommunicationerror",
            ]
            
            is_connection_error = any(err in error_str for err in connection_errors)
            
            # Проверяем также на ошибки истекшей сессии и таймауты
            session_errors = ["badsessionclosed", "badsessionidinvalid"]
            is_session_error = any(err in error_str for err in session_errors)
            is_timeout = error_type == "TimeoutError"
            
            if is_connection_error or is_session_error or is_timeout:
                if is_session_error:
                    logger.warning(f"[OPC UA] Session expired, reconnecting: {e}")
                elif is_timeout:
                    logger.warning(f"[OPC UA] Request timeout, reconnecting")
                else:
                    logger.warning(f"[OPC UA] Connection lost, will reconnect: {e}")
                # Сбрасываем состояние соединения для переподключения
                self._connected = False
                self._state = OPCUAState.DISCONNECTED
                if self._client:
                    try:
                        await self._client.disconnect()
                    except:
                        pass
                    self._client = None
            else:
                # Добавляем в черный список узлы с постоянными ошибками атрибутов
                if "badattributeidinvalid" in error_str or "badnodeidunknown" in error_str:
                    self._blacklisted_nodes.add(node_id)
                    logger.info(f"[OPC UA] Узел {node_id} добавлен в черный список (постоянные ошибки)")
                
                # Батчинг ошибок - собираем и логируем группами
                await self._batch_error(error_type, node_id)
            
            self._stats['errors'] += 1
            return None
    
    async def read_nodes(self, node_ids: List[str]) -> Dict[str, Any]:
        """Прочитать несколько узлов."""
        results = {}
        for node_id in node_ids:
            results[node_id] = await self.read_node(node_id)
        return results
    
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
        }


# Singleton instance
opcua_service = OPCUAService()
