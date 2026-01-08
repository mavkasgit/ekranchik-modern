"""
Line Monitor Service - unified OPC UA monitoring for production line.
Combines hanger tracking, unload detection, and real-time polling.
"""
import asyncio
import logging
from datetime import datetime
from typing import Dict, List, Optional
from dataclasses import dataclass

from app.services.opcua_service import opcua_service
from app.services.websocket_manager import websocket_manager
from app.schemas.websocket import WebSocketMessage

logger = logging.getLogger(__name__)

CONTROL_BATH = 34  # Unload point


@dataclass
class HangerState:
    """Current state of a hanger in the line."""
    number: int
    current_bath: Optional[int] = None
    entry_time: Optional[str] = None
    baths_visited: List[int] = None
    
    def __post_init__(self):
        if self.baths_visited is None:
            self.baths_visited = []


class LineMonitorService:
    """
    Unified service for monitoring production line via OPC UA.
    - Tracks hangers through baths
    - Detects unload events at Bath[34]
    - Broadcasts real-time updates via WebSocket
    """
    
    def __init__(self):
        self._running = False
        self._task: Optional[asyncio.Task] = None
        self._poll_interval = 2  # seconds
        
        # State tracking
        self._hangers: Dict[int, HangerState] = {}
        self._bath34_pallete: Optional[int] = None
        self._processed_unloads: set = set()
        
        # Unload events cache
        self._unload_events: List[dict] = []
    
    @property
    def is_running(self) -> bool:
        return self._running
    
    async def start(self) -> bool:
        """Start the line monitoring loop."""
        if self._running:
            logger.warning("[Line Monitor] Already running")
            return False
        
        self._running = True
        self._task = asyncio.create_task(self._monitor_loop())
        logger.info("[Line Monitor] Started")
        return True
    
    async def stop(self) -> None:
        """Stop the line monitoring loop."""
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
        
        logger.info("[Line Monitor] Stopped")
    
    async def _monitor_loop(self) -> None:
        """Main monitoring loop."""
        logger.info(f"[Line Monitor] Loop started, interval: {self._poll_interval}s")
        
        while self._running:
            try:
                await self._poll_once()
            except Exception as e:
                logger.error(f"[Line Monitor] Poll error: {e}")
            
            await asyncio.sleep(self._poll_interval)
    
    async def _poll_once(self) -> None:
        """Single poll cycle: scan baths and detect events."""
        try:
            # Ensure OPC UA connection
            if not opcua_service.is_connected:
                if not await opcua_service.connect():
                    logger.warning("[Line Monitor] Cannot connect to OPC UA")
                    return
            
            # Scan all baths
            await self._scan_baths()
            
            # Check for unload events
            await self._check_unload()
            
        except Exception as e:
            logger.error(f"[Line Monitor] Poll error: {e}")
    
    async def _scan_baths(self) -> None:
        """Scan all baths and update hanger positions."""
        try:
            # Reset current positions
            for hanger in self._hangers.values():
                hanger.current_bath = None
            
            # Scan baths 1-39
            for bath_num in range(1, 40):
                in_use = await opcua_service.read_node(f"ns=4;s=Bath[{bath_num}].InUse")
                
                if not in_use:
                    continue
                
                # Read hanger number from Pallete field
                pallete = await opcua_service.read_node(f"ns=4;s=Bath[{bath_num}].Pallete")
                if not pallete or pallete == 0:
                    continue
                
                hanger_num = int(pallete)
                
                # Create or update hanger
                if hanger_num not in self._hangers:
                    self._hangers[hanger_num] = HangerState(number=hanger_num)
                
                hanger = self._hangers[hanger_num]
                hanger.current_bath = bath_num
                
                # Track bath visit
                if bath_num not in hanger.baths_visited:
                    hanger.baths_visited.append(bath_num)
                    if hanger.entry_time is None:
                        hanger.entry_time = datetime.now().isoformat()
        
        except Exception as e:
            logger.error(f"[Line Monitor] Scan error: {e}")
    
    async def _check_unload(self) -> None:
        """Check Bath[34] for unload events."""
        try:
            pallete = await opcua_service.read_node(f"ns=4;s=Bath[{CONTROL_BATH}].Pallete")
            current_pallete = int(pallete) if pallete else 0
            
            # First poll - just initialize
            if self._bath34_pallete is None:
                self._bath34_pallete = current_pallete
                return
            
            # Detect entry: 0 -> N (hanger enters unload position)
            if self._bath34_pallete == 0 and current_pallete > 0:
                await self._record_unload(current_pallete)
            
            self._bath34_pallete = current_pallete
        
        except Exception as e:
            logger.error(f"[Line Monitor] Unload check error: {e}")
    
    async def _record_unload(self, hanger_num: int) -> None:
        """Record unload event and broadcast."""
        try:
            now = datetime.now()
            event_key = f"{hanger_num}_{now.strftime('%Y%m%d_%H%M')}"
            
            # Avoid duplicates
            if event_key in self._processed_unloads:
                return
            
            self._processed_unloads.add(event_key)
            
            # Get hanger data
            hanger = self._hangers.get(hanger_num)
            in_time = await opcua_service.read_node(f"ns=4;s=Bath[{CONTROL_BATH}].InTime")
            
            event = {
                "hanger": hanger_num,
                "time": now.strftime("%H:%M:%S"),
                "date": now.strftime("%d.%m.%Y"),
                "total_time_sec": float(in_time) if in_time else 0,
                "baths_visited": hanger.baths_visited if hanger else [],
                "timestamp": now.isoformat()
            }
            
            self._unload_events.append(event)
            
            # Keep only last 500 events
            if len(self._unload_events) > 500:
                self._unload_events = self._unload_events[-500:]
            
            # Broadcast via WebSocket
            message = WebSocketMessage(
                type="unload_event",
                payload=event,
                timestamp=now
            )
            await websocket_manager.broadcast(message)
            
            logger.info(f"[Line Monitor] Unload: Hanger {hanger_num} at {now.strftime('%H:%M:%S')}")
        
        except Exception as e:
            logger.error(f"[Line Monitor] Record unload error: {e}")
    
    def get_unload_events(self, limit: int = 100) -> List[dict]:
        """Get recent unload events."""
        return self._unload_events[-limit:]
    
    def get_hanger_state(self, hanger_num: int) -> Optional[HangerState]:
        """Get current state of a hanger."""
        return self._hangers.get(hanger_num)
    
    def get_active_hangers(self) -> List[HangerState]:
        """Get all hangers currently in the line."""
        return [h for h in self._hangers.values() if h.current_bath is not None]


# Singleton instance
line_monitor = LineMonitorService()
