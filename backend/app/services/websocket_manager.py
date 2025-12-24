"""
WebSocket Manager - handles WebSocket connections and broadcasting.
"""
import asyncio
import json
from typing import Dict, Set, Any, Optional
from datetime import datetime

from fastapi import WebSocket
from starlette.websockets import WebSocketState

from app.schemas.websocket import WebSocketMessage


class WebSocketManager:
    """
    Manager for WebSocket connections.
    
    Features:
    - Connection tracking
    - Broadcast to all connected clients
    - Individual message sending
    - Connection health monitoring
    """
    
    def __init__(self):
        self._connections: Set[WebSocket] = set()
        self._lock = asyncio.Lock()
    
    @property
    def connection_count(self) -> int:
        """Get number of active connections."""
        return len(self._connections)
    
    @property
    def connections(self) -> Set[WebSocket]:
        """Get set of active connections (read-only copy)."""
        return self._connections.copy()
    
    async def connect(self, websocket: WebSocket) -> None:
        """
        Accept and register a new WebSocket connection.
        
        Args:
            websocket: WebSocket connection to register
        """
        await websocket.accept()
        async with self._lock:
            self._connections.add(websocket)
    
    async def disconnect(self, websocket: WebSocket) -> None:
        """
        Remove a WebSocket connection.
        
        Args:
            websocket: WebSocket connection to remove
        """
        async with self._lock:
            self._connections.discard(websocket)
    
    async def send_personal(
        self,
        websocket: WebSocket,
        message: WebSocketMessage
    ) -> bool:
        """
        Send a message to a specific client.
        
        Args:
            websocket: Target WebSocket connection
            message: Message to send
        
        Returns:
            True if sent successfully, False otherwise
        """
        try:
            if websocket.client_state == WebSocketState.CONNECTED:
                await websocket.send_json(message.model_dump(mode='json'))
                return True
        except Exception:
            await self.disconnect(websocket)
        return False
    
    async def broadcast(
        self,
        message: WebSocketMessage,
        exclude: Optional[WebSocket] = None
    ) -> int:
        """
        Broadcast a message to all connected clients.
        
        Args:
            message: Message to broadcast
            exclude: Optional WebSocket to exclude from broadcast
        
        Returns:
            Number of clients that received the message
        """
        import logging
        logger = logging.getLogger(__name__)
        
        if not self._connections:
            logger.debug(f"[WS] No connections to broadcast to (type={message.type})")
            return 0
        
        # Get snapshot of connections
        async with self._lock:
            connections = self._connections.copy()
        
        sent_count = 0
        disconnected = []
        
        data = message.model_dump(mode='json')
        logger.info(f"[WS] Broadcasting {message.type} to {len(connections)} clients")
        
        for websocket in connections:
            if websocket == exclude:
                continue
            
            try:
                if websocket.client_state == WebSocketState.CONNECTED:
                    await websocket.send_json(data)
                    sent_count += 1
                else:
                    disconnected.append(websocket)
            except Exception as e:
                logger.warning(f"[WS] Failed to send to client: {e}")
                disconnected.append(websocket)
        
        # Clean up disconnected clients
        if disconnected:
            async with self._lock:
                for ws in disconnected:
                    self._connections.discard(ws)
        
        logger.info(f"[WS] Broadcast complete: sent to {sent_count}/{len(connections)} clients")
        return sent_count
    
    async def broadcast_dict(
        self,
        data: Dict[str, Any],
        msg_type: str = "data_update"
    ) -> int:
        """
        Broadcast a dictionary as a WebSocket message.
        
        Convenience method that wraps data in WebSocketMessage.
        
        Args:
            data: Data to broadcast
            msg_type: Message type (data_update, unload_event, status, error, ping, pong)
        
        Returns:
            Number of clients that received the message
        """
        message = WebSocketMessage(
            type=msg_type,
            payload=data,
            timestamp=datetime.now()
        )
        return await self.broadcast(message)
    
    async def close_all(self) -> None:
        """Close all active connections."""
        async with self._lock:
            connections = self._connections.copy()
            self._connections.clear()
        
        for websocket in connections:
            try:
                await websocket.close()
            except Exception:
                pass


# Singleton instance
websocket_manager = WebSocketManager()
