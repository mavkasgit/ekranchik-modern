"""
FTP Poller Service - polls FTP server for new unload events.

Двухдневный режим:
- Всегда читает 2 файла целиком (сегодня + вчера)
- Кэширует события для определения новых
- WebSocket отправляет только новые события
- API отдаёт все события из кэша
"""
import asyncio
import logging
from typing import Optional, Set, List
from datetime import datetime

from app.core.config import settings
from app.services.ftp_service import ftp_service
from app.services.websocket_manager import websocket_manager
from app.schemas.websocket import WebSocketMessage
from app.schemas.dashboard import UnloadEvent

logger = logging.getLogger(__name__)


class FTPPoller:
    """
    Service for polling FTP server for new events.
    
    Двухдневный режим работы:
    - Читает 2 файла целиком каждый poll
    - Хранит кэш всех событий
    - Определяет новые события по уникальному ключу (date+time+hanger)
    - Отправляет через WebSocket только новые
    """
    
    def __init__(self):
        self._running = False
        self._task: Optional[asyncio.Task] = None
        self._poll_interval = settings.FTP_POLL_INTERVAL
        self._wake_event: Optional[asyncio.Event] = None
        
        # Кэш событий для определения новых
        self._events_cache: List[UnloadEvent] = []
        self._seen_keys: Set[str] = set()  # "date|time|hanger"
    
    @property
    def is_running(self) -> bool:
        """Check if poller is running."""
        return self._running
    
    @property
    def cached_events(self) -> List[UnloadEvent]:
        """Get all cached events."""
        return self._events_cache.copy()
    
    @property
    def events_count(self) -> int:
        """Get count of cached events."""
        return len(self._events_cache)
    
    def _make_event_key(self, event: UnloadEvent) -> str:
        """Create unique key for event deduplication."""
        return f"{event.date}|{event.time}|{event.hanger}"
    
    async def _poll_loop(self) -> None:
        """Main polling loop."""
        logger.info(f"[FTP] Polling loop started, interval: {self._poll_interval}s")
        self._wake_event = asyncio.Event()
        
        while self._running:
            try:
                await self._poll_once()
            except Exception as e:
                logger.error(f"[FTP] Poll error: {e}")
            
            # Use configured interval (default: 15 seconds)
            interval = self._poll_interval
            logger.info(f"[FTP] Next poll in {interval}s...")
            
            # Wait for interval OR wake event (whichever comes first)
            self._wake_event.clear()
            try:
                await asyncio.wait_for(self._wake_event.wait(), timeout=interval)
            except asyncio.TimeoutError:
                pass  # Normal timeout, continue polling
    
    async def _poll_once(self) -> None:
        """Perform a single poll."""
        # Skip polling in simulation mode (events loaded all at once)
        if ftp_service.is_simulation:
            logger.debug("[FTP] Skipping poll - simulation mode active")
            return
        
        logger.info(f"[FTP] Polling FTP server {settings.FTP_HOST}...")
        
        # ВСЕГДА читаем 2 дня целиком (сегодня + вчера)
        all_events, date_changed = await ftp_service.poll_multiday(days=settings.FTP_DAYS_TO_READ)
        
        logger.info(f"[FTP] Poll complete: {len(all_events) if all_events else 0} events from {settings.FTP_DAYS_TO_READ} days, connected={ftp_service.is_connected}")
        
        if date_changed:
            # Notify clients about date rollover
            message = WebSocketMessage(
                type="status",
                payload={
                    "source": "ftp",
                    "event": "date_rollover",
                    "message": "New day started, log reset"
                },
                timestamp=datetime.now()
            )
            await websocket_manager.broadcast(message)
            logger.info("FTP date rollover detected")
        
        # Определяем НОВЫЕ события (которых не было в кэше)
        new_events = []
        if all_events:
            for event in all_events:
                key = self._make_event_key(event)
                if key not in self._seen_keys:
                    self._seen_keys.add(key)
                    new_events.append(event)
            
            # Обновляем кэш всеми событиями
            self._events_cache = all_events
        
        # Отправляем через WebSocket только НОВЫЕ события
        if new_events:
            for event in new_events:
                message = WebSocketMessage(
                    type="unload_event",
                    payload={
                        "time": event.time,
                        "hanger": event.hanger,
                        "date": event.date,
                        "timestamp": event.timestamp.isoformat() if event.timestamp else None
                    },
                    timestamp=datetime.now()
                )
                await websocket_manager.broadcast(message)
            
            logger.info(f"[FTP] Broadcast {len(new_events)} NEW events (total cached: {len(self._events_cache)})")
        
        # Update connection status
        if ftp_service.is_connected or ftp_service.is_simulation:
            await self._broadcast_status("connected" if not ftp_service.is_simulation else "simulation")
        else:
            await self._broadcast_status("disconnected")
    
    async def _broadcast_status(self, status: str) -> None:
        """Broadcast FTP connection status."""
        message = WebSocketMessage(
            type="status",
            payload={
                "source": "ftp",
                "status": status
            },
            timestamp=datetime.now()
        )
        await websocket_manager.broadcast(message)
    
    async def start(self) -> bool:
        """
        Start the FTP polling loop.
        
        Returns:
            True if started successfully
        """
        if self._running:
            logger.warning("FTPPoller already running")
            return False
        
        self._running = True
        self._task = asyncio.create_task(self._poll_loop())
        logger.info("FTPPoller started")
        return True
    
    async def stop(self) -> None:
        """Stop the FTP polling loop."""
        if not self._running:
            return
        
        self._running = False
        
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        
        logger.info("FTPPoller stopped")
    
    async def poll_now(self) -> None:
        """Trigger an immediate poll (for manual refresh)."""
        await self._poll_once()
        # Wake up the polling loop to use new interval (e.g., when simulation starts)
        if self._wake_event:
            self._wake_event.set()


# Singleton instance
ftp_poller = FTPPoller()
