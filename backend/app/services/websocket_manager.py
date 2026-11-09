"""
WebSocket Manager - handles WebSocket connections and broadcasting.
Optimized for high throughput with timeout protection.
"""

import asyncio
import contextlib

from fastapi import WebSocket
from starlette.websockets import WebSocketState

from app.schemas.websocket import WebSocketMessage


class WebSocketManager:
    """
    Manager for WebSocket connections.
    Non-blocking, optimized for high throughput.
    """

    def __init__(self):
        # Используем set напрямую — операции add/discard атомарны в Python
        self._connections: set[WebSocket] = set()

    @property
    def connection_count(self) -> int:
        """Get number of active connections."""
        return len(self._connections)

    async def connect(self, websocket: WebSocket) -> None:
        """Accept and register a new WebSocket connection."""
        await websocket.accept()
        self._connections.add(websocket)

    async def disconnect(self, websocket: WebSocket) -> None:
        """Remove a WebSocket connection."""
        self._connections.discard(websocket)

    async def send_personal(self, websocket: WebSocket, message: WebSocketMessage) -> bool:
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
                await websocket.send_json(message.model_dump(mode="json"))
                return True
            else:
                # Connection not ready, remove it
                await self.disconnect(websocket)
        except Exception as e:
            import logging

            logger = logging.getLogger(__name__)
            logger.debug(f"[WS] Failed to send personal message: {e}")
            await self.disconnect(websocket)
        return False

    async def broadcast(self, message: WebSocketMessage, exclude: WebSocket | None = None) -> int:
        """
        Broadcast a message to all connected clients.
        Non-blocking with timeout protection.
        """
        if not self._connections:
            return 0

        # Get snapshot of connections (без лока для скорости)
        connections = list(self._connections)

        sent_count = 0
        disconnected = []

        data = message.model_dump(mode="json")

        async def send_with_timeout(ws: WebSocket) -> bool:
            """Отправка с таймаутом 1 сек."""
            try:
                if ws.client_state == WebSocketState.CONNECTED:
                    await asyncio.wait_for(ws.send_json(data), timeout=1.0)
                    return True
            except (TimeoutError, Exception):
                return False
            return False

        # Отправляем всем параллельно с таймаутом
        tasks = []
        for ws in connections:
            if ws != exclude:
                tasks.append((ws, asyncio.create_task(send_with_timeout(ws))))

        if not tasks:
            return 0

        # Ждём все задачи (они уже с таймаутом внутри)
        for ws, task in tasks:
            try:
                success = await task
                if success:
                    sent_count += 1
                else:
                    disconnected.append(ws)
            except Exception:
                disconnected.append(ws)

        # Чистим отключённых (без лока — atomic операция)
        for ws in disconnected:
            self._connections.discard(ws)

        return sent_count

    async def close_all(self) -> None:
        """Close all active connections."""
        connections = list(self._connections)
        self._connections.clear()

        for websocket in connections:
            with contextlib.suppress(Exception):
                await asyncio.wait_for(websocket.close(), timeout=1.0)


# Singleton instance
websocket_manager = WebSocketManager()
