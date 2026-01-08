"""
OPC UA Poller Service - polls OPC UA server for hanger events.
Monitors Bath[34] for unload events and broadcasts them via WebSocket.
"""
import asyncio
import logging
from typing import Optional, List
from datetime import datetime

from app.core.config import settings
from app.services.opcua_service import opcua_service
from app.services.hanger_service import hanger_service
from app.services.websocket_manager import websocket_manager
from app.schemas.websocket import WebSocketMessage
from app.schemas.dashboard import UnloadEvent

logger = logging.getLogger(__name__)


class OPCUAPoller:
    """
    Service for polling OPC UA server for hanger events.
    Monitors Bath[34] (control point) for unload events.
    """
    
    def __init__(self):
        self._running = False
        self._task: Optional[asyncio.Task] = None
        self._poll_interval = 2  # Poll every 2 seconds for faster detection
        self._wake_event: Optional[asyncio.Event] = None
        
        # Cached events for API access
        self._events_cache: List[UnloadEvent] = []
    
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
    
    async def _poll_loop(self) -> None:
        """Main polling loop."""
        logger.info(f"[OPC UA Poller] Started, interval: {self._poll_interval}s")
        self._wake_event = asyncio.Event()
        
        while self._running:
            try:
                await self._poll_once()
            except Exception as e:
                logger.error(f"[OPC UA Poller] Poll error: {e}")
            
            # Wait for interval
            self._wake_event.clear()
            try:
                await asyncio.wait_for(self._wake_event.wait(), timeout=self._poll_interval)
            except asyncio.TimeoutError:
                pass
    
    async def _poll_once(self) -> None:
        """Perform a single poll - scan baths and check for unload events."""
        try:
            # Ensure OPC UA connection
            if not opcua_service.is_connected:
                if not await opcua_service.connect():
                    logger.warning("[OPC UA Poller] Cannot connect to OPC UA server")
                    return
            
            # Scan all baths for hanger data
            await hanger_service.scan_baths()
            
            # Check Bath[34] for unload events
            from app.services.unload_service import unload_service
            unload_record = await unload_service.check_bath34()
            
            if unload_record:
                # New unload event detected!
                event = unload_record.to_unload_event()
                self._events_cache.append(event)
                
                # Keep only last 500 events in cache
                if len(self._events_cache) > 500:
                    self._events_cache = self._events_cache[-500:]
                
                # Broadcast via WebSocket
                message = WebSocketMessage(
                    type="unload_event",
                    payload={
                        "time": event.time,
                        "hanger": event.hanger,
                        "date": event.date,
                        "timestamp": event.timestamp.isoformat() if event.timestamp else None,
                        "total_time_sec": unload_record.total_time_sec,
                        "baths_visited": unload_record.baths_visited
                    },
                    timestamp=datetime.now()
                )
                await websocket_manager.broadcast(message)
                
                logger.info(f"[OPC UA Poller] Broadcast unload event: Pallete {event.hanger}")
            
            # Broadcast status periodically
            await self._broadcast_status("connected")
            
        except Exception as e:
            logger.error(f"[OPC UA Poller] Poll error: {e}")
            await self._broadcast_status("error")
    
    async def _broadcast_status(self, status: str) -> None:
        """Broadcast OPC UA connection status."""
        message = WebSocketMessage(
            type="status",
            payload={
                "source": "opcua",
                "status": status
            },
            timestamp=datetime.now()
        )
        await websocket_manager.broadcast(message)
    
    async def start(self) -> bool:
        """Start the OPC UA polling loop."""
        if self._running:
            logger.warning("OPCUAPoller already running")
            return False
        
        self._running = True
        self._task = asyncio.create_task(self._poll_loop())
        logger.info("OPCUAPoller started")
        return True
    
    async def stop(self) -> None:
        """Stop the OPC UA polling loop."""
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
        
        logger.info("OPCUAPoller stopped")
    
    async def poll_now(self) -> None:
        """Trigger an immediate poll."""
        await self._poll_once()
        if self._wake_event:
            self._wake_event.set()
    
    def load_events_from_unload_service(self):
        """Load cached events from unload service on startup."""
        from app.services.unload_service import unload_service
        self._events_cache = unload_service.get_unload_events(limit=500)
        logger.info(f"[OPC UA Poller] Loaded {len(self._events_cache)} events from unload service")


# Singleton instance
opcua_poller = OPCUAPoller()
