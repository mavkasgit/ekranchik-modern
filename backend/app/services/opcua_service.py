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
        self._cache_ttl: int = 5  # Секунды
        
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
        
        if self._connected:
            return True
        
        async with self._lock:
            try:
                self._state = OPCUAState.CONNECTING
                
                client = Client(settings.OPCUA_ENDPOINT, timeout=10)
                await client.connect()
                
                self._client = client
                self._connected = True
                self._state = OPCUAState.CONNECTED
                self._stats['connections'] += 1
                self._node_cache.clear()
                self._cache_time.clear()
                
                logger.info(f"[OPC UA] Connected to {settings.OPCUA_ENDPOINT}")
                return True
                
            except Exception as e:
                logger.error(f"[OPC UA] Connection failed: {e}")
                self._connected = False
                self._state = OPCUAState.ERROR
                self._stats['errors'] += 1
                return False
    
    async def disconnect(self) -> None:
        """Отключиться от OPC UA сервера."""
        if self._client:
            try:
                await self._client.disconnect()
            except Exception as e:
                logger.warning(f"[OPC UA] Disconnect error: {e}")
            self._client = None
        
        self._connected = False
        self._state = OPCUAState.DISCONNECTED
        self._node_cache.clear()
        self._cache_time.clear()
    
    async def read_node(self, node_id: str) -> Optional[Any]:
        """Прочитать значение узла с кешированием."""
        if not self._connected:
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
            # Логируем только критические ошибки, не спам про несуществующие ноды
            error_str = str(e).lower()
            if "badnodeidunknown" not in error_str and "badattributeidinvalid" not in error_str:
                logger.error(f"[OPC UA] Read error for {node_id}: {e}")
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
