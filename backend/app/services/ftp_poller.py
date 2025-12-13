"""
FTP Poller Service - polls FTP server for new unload events.
"""
import asyncio
import logging
from typing import Optional
from datetime import datetime

from app.core.config import settings
from app.services.ftp_service import ftp_service
from app.services.websocket_manager import websocket_manager
from app.schemas.websocket import WebSocketMessage

logger = logging.getLogger(__name__)


class FTPPoller:
    """
    Service for polling FTP server for new events.
    
    Runs an async polling loop that checks for new unload events
    and broadcasts them via WebSocket.
    """
    
    def __init__(self):
        self._running = False
        self._task: Optional[asyncio.Task] = None
        self._poll_interval = settings.FTP_POLL_INTERVAL
    
    @property
    def is_running(self) -> bool:
        """Check if poller is running."""
        return self._running
    
    async def _poll_loop(self) -> None:
        """Main polling loop."""
        logger.info(f"FTP polling loop started, interval: {self._poll_interval}s")
        
        while self._running:
            try:
                await self._poll_once()
            except Exception as e:
                logger.error(f"FTP poll error: {e}")
            
            # Wait for next poll
            await asyncio.sleep(self._poll_interval)
    
    async def _poll_once(self) -> None:
        """Perform a single poll."""
        events, date_changed = await ftp_service.poll_incremental()
        
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
        
        if events:
            # Broadcast each event
            for event in events:
                message = WebSocketMessage(
                    type="unload_event",
                    payload={
                        "time": event.time,
                        "hanger": event.hanger,
                        "timestamp": event.timestamp.isoformat() if event.timestamp else None
                    },
                    timestamp=datetime.now()
                )
                await websocket_manager.broadcast(message)
            
            logger.info(f"Broadcast {len(events)} FTP events")
        
        # Update connection status
        if ftp_service.is_connected:
            await self._broadcast_status("connected")
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


# Singleton instance
ftp_poller = FTPPoller()
