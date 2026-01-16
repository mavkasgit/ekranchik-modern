"""
Line Monitor Service - unified OPC UA monitoring for production line.
Combines hanger tracking, unload detection, and real-time polling.
"""
import asyncio
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional
from dataclasses import dataclass, field
from collections import deque

from app.services.opcua_service import opcua_service
from app.services.websocket_manager import websocket_manager
from app.schemas.websocket import WebSocketMessage

logger = logging.getLogger(__name__)

# --- Constants ---
CONTROL_BATH = 34  # Unload point bath number
HANGER_TTL = timedelta(minutes=30)  # Time to keep inactive hanger data before cleanup
CLEANUP_INTERVAL = timedelta(minutes=5)  # How often to run the cleanup task


# --- Data Classes ---
@dataclass
class HangerPathEntry:
    """Represents a hanger's time in a single bath."""
    bath_name: str
    entry_time: datetime
    exit_time: Optional[datetime] = None
    duration: Optional[float] = None  # in seconds


@dataclass
class HangerState:
    """Current state of a hanger in the line, tracking its current cycle."""
    id: int
    current_bath: Optional[str] = None
    entry_time: Optional[datetime] = None
    last_seen: datetime = field(default_factory=datetime.now)
    path: List[HangerPathEntry] = field(default_factory=list)


class LineMonitorService:
    """
    Unified service for monitoring production line via OPC UA.
    - Tracks hangers through baths, handling cyclical hanger numbers.
    - Detects unload events at the control bath.
    - Broadcasts real-time updates via WebSocket.
    - Cleans up stale hanger data to prevent memory leaks.
    """
    
    def __init__(self):
        self._running = False
        self._task: Optional[asyncio.Task] = None
        self._poll_interval = 1  # seconds - обновление каждую секунду
        self._heartbeat_interval = 1  # seconds - отправка статуса на фронтенд каждую секунду
        self._health_check_interval = 30  # seconds - проверка здоровья OPC UA соединения
        self._last_heartbeat = datetime.now()
        self._last_health_check = datetime.now()
        self._consecutive_errors = 0
        self._max_consecutive_errors = 5  # После этого делаем полный reconnect
        
        # State tracking
        self._hangers: Dict[int, HangerState] = {}
        self._bath34_pallete: Optional[int] = None
        self._processed_unloads: deque = deque(maxlen=1000)
        self._last_cleanup_time = datetime.now()

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
    
    def clear_data(self) -> None:
        """Очистить все данные мониторинга (подвесы, события)."""
        self._hangers.clear()
        self._bath34_pallete = None
        self._processed_unloads.clear()
        self._unload_events.clear()
        logger.info("[Line Monitor] All data cleared")
    
    async def _monitor_loop(self) -> None:
        """Main monitoring loop."""
        logger.info(f"[Line Monitor] Loop started, interval: {self._poll_interval}s")
        
        while self._running:
            try:
                await self._poll_once()
                
                # Сбрасываем счётчик ошибок при успешном опросе
                self._consecutive_errors = 0

                # Периодический heartbeat для фронтенда
                now = datetime.now()
                if (now - self._last_heartbeat).total_seconds() >= self._heartbeat_interval:
                    await self._send_heartbeat()
                    self._last_heartbeat = now
                
                # Периодическая проверка здоровья OPC UA соединения
                if (now - self._last_health_check).total_seconds() >= self._health_check_interval:
                    health_ok = await opcua_service.ensure_connected()
                    if not health_ok:
                        logger.warning("[Line Monitor] OPC UA health check failed")
                    self._last_health_check = now
                
                # Периодический flush батча ошибок OPC UA
                await opcua_service._flush_error_batch()

                # Periodically clean up old hangers
                if now - self._last_cleanup_time > CLEANUP_INTERVAL:
                    await self._cleanup_hangers()
                    self._last_cleanup_time = now

            except Exception as e:
                self._consecutive_errors += 1
                logger.error(f"[Line Monitor] Error in monitor loop ({self._consecutive_errors}): {e}", exc_info=True)
                
                # При множественных ошибках - принудительный reconnect
                if self._consecutive_errors >= self._max_consecutive_errors:
                    logger.warning("[Line Monitor] Too many errors, forcing OPC UA reconnect")
                    await opcua_service.disconnect()
                    self._consecutive_errors = 0
                    await self._broadcast_connection_status(False)
            
            await asyncio.sleep(self._poll_interval)
    
    async def _send_heartbeat(self) -> None:
        """Send heartbeat with current status and line data to all clients."""
        try:
            active_hangers = self.get_active_hangers()
            
            # Собираем данные о ваннах для визуализации
            baths_data = []
            for bath_num in range(1, 40):
                in_use = opcua_service.get_value(f"ns=4;s=Bath[{bath_num}].InUse")
                pallete = opcua_service.get_value(f"ns=4;s=Bath[{bath_num}].Pallete")
                in_time = opcua_service.get_value(f"ns=4;s=Bath[{bath_num}].InTime")
                out_time = opcua_service.get_value(f"ns=4;s=Bath[{bath_num}].OutTime")
                
                baths_data.append({
                    "bath_number": bath_num,
                    "in_use": bool(in_use) if in_use is not None else False,
                    "pallete": int(pallete) if pallete else 0,
                    "in_time": float(in_time) if in_time else 0,
                    "out_time": float(out_time) if out_time else 0,
                })
            
            heartbeat = WebSocketMessage(
                type="line_update",
                payload={
                    "opcua_connected": opcua_service.is_connected,
                    "opcua_state": opcua_service.state.value,
                    "active_hangers": len(active_hangers),
                    "total_tracked": len(self._hangers),
                    "recent_unloads": len(self._unload_events),
                    "stats": opcua_service.stats,
                    "baths": baths_data,
                    "timestamp": datetime.now().isoformat(),
                },
                timestamp=datetime.now()
            )
            await websocket_manager.broadcast(heartbeat)
        except Exception as e:
            logger.error(f"[Line Monitor] Heartbeat error: {e}")
    
    async def _poll_once(self) -> None:
        """Single poll cycle: scan baths and detect events."""
        # Ensure OPC UA connection with health check
        connected = await opcua_service.ensure_connected()
        if not connected:
            logger.warning("[Line Monitor] Cannot connect to OPC UA. Skipping poll.")
            # Отправляем статус отключения на фронтенд
            await self._broadcast_connection_status(False)
            return
        
        # Если только что переподключились - уведомляем фронтенд
        if not opcua_service.is_connected:
            await self._broadcast_connection_status(False)
            return
        
        # ВАЖНО: Сначала проверяем выгрузку (ванна 34), потом сканируем остальные
        # Это гарантирует что выгрузка будет зафиксирована до того как
        # _scan_baths() создаст "новый цикл" для подвеса
        await self._check_unload()
        
        # Scan all baths to update hanger states
        await self._scan_baths()
    
    async def _broadcast_connection_status(self, connected: bool) -> None:
        """Broadcast OPC UA connection status to all clients."""
        try:
            status_message = WebSocketMessage(
                type="opcua_status",
                payload={
                    "connected": connected,
                    "state": opcua_service.state.value,
                    "stats": opcua_service.stats,
                },
                timestamp=datetime.now()
            )
            await websocket_manager.broadcast(status_message)
        except Exception as e:
            logger.error(f"[Line Monitor] Failed to broadcast status: {e}")

    async def _cleanup_hangers(self) -> None:
        """Remove hanger data that has been inactive for too long."""
        now = datetime.now()
        inactive_hangers = [
            hanger_id
            for hanger_id, state in self._hangers.items()
            if state.current_bath is None and (now - state.last_seen) > HANGER_TTL
        ]
        
        if inactive_hangers:
            for hanger_id in inactive_hangers:
                del self._hangers[hanger_id]
            logger.info(f"[Line Monitor] Cleaned up {len(inactive_hangers)} inactive hangers.")

    async def _scan_baths(self) -> None:
        """Scan all baths and update hanger positions, handling new cycles."""
        now = datetime.now()
        
        # Keep track of all hangers seen in this scan cycle
        hangers_seen_in_scan = set()

        for bath_num in range(1, 40):
            bath_name = str(bath_num)
            try:
                in_use = await opcua_service.read_node(f"ns=4;s=Bath[{bath_num}].InUse")
                if not in_use:
                    continue
                
                pallete = await opcua_service.read_node(f"ns=4;s=Bath[{bath_num}].Pallete")
                if not pallete or pallete == 0:
                    continue

                hanger_id = int(pallete)
                hangers_seen_in_scan.add(hanger_id)
                hanger_state = self._hangers.get(hanger_id)

                # --- New Cycle Detection ---
                # If hanger is not tracked, or was previously unloaded (inactive), it's a new cycle.
                if not hanger_state or hanger_state.current_bath is None:
                    hanger_state = HangerState(id=hanger_id)
                    self._hangers[hanger_id] = hanger_state
                    logger.info(f"Hanger {hanger_id} started a new cycle upon entering bath {bath_name}.")

                # --- State Update ---
                # If hanger moved to a new bath
                if hanger_state.current_bath != bath_name:
                    # Finalize the previous step if it exists
                    if hanger_state.current_bath is not None and hanger_state.entry_time is not None:
                        duration = (now - hanger_state.entry_time).total_seconds()
                        hanger_state.path.append(
                            HangerPathEntry(
                                bath_name=hanger_state.current_bath,
                                entry_time=hanger_state.entry_time,
                                exit_time=now,
                                duration=duration,
                            )
                        )
                    # Record entry into the new bath
                    hanger_state.current_bath = bath_name
                    hanger_state.entry_time = now

                # Always update the last_seen timestamp for any active hanger
                hanger_state.last_seen = now

            except Exception as e:
                logger.error(f"[Line Monitor] Error scanning bath {bath_name}: {e}")

        # --- Handle hangers that are no longer seen ---
        # This logic is tricky. A hanger might disappear due to a transient read error.
        # The definitive signal that a hanger is off the line is the unload event.
        # We will rely on _record_unload to set current_bath to None.
        pass

    async def _check_unload(self) -> None:
        """Check Bath[34] for unload events."""
        try:
            pallete = await opcua_service.read_node(f"ns=4;s=Bath[{CONTROL_BATH}].Pallete")
            current_pallete = int(pallete) if pallete and pallete > 0 else 0
            
            # First poll - just initialize
            if self._bath34_pallete is None:
                self._bath34_pallete = current_pallete
                return
            
            # Detect entry: 0 -> N (hanger enters unload position)
            if self._bath34_pallete == 0 and current_pallete > 0:
                await self._record_unload(current_pallete)
            
            self._bath34_pallete = current_pallete
        
        except Exception as e:
            logger.error(f"[Line Monitor] Unload check error: {e}", exc_info=True)
    
    async def _record_unload(self, hanger_id: int) -> None:
        """Record unload event, update hanger state to inactive, and broadcast."""
        try:
            now = datetime.now()
            # Use a simple key to avoid duplicate events within a short timeframe
            event_key = (hanger_id, now.strftime('%Y%m%d_%H%M'))
            
            if event_key in self._processed_unloads:
                return
            self._processed_unloads.append(event_key)
            
            hanger = self._hangers.get(hanger_id)
            total_time_sec = 0
            path_summary = []

            if hanger:
                # Finalize the last step (the unload bath)
                if hanger.entry_time and hanger.current_bath:
                    duration = (now - hanger.entry_time).total_seconds()
                    hanger.path.append(
                        HangerPathEntry(
                            bath_name=hanger.current_bath,
                            entry_time=hanger.entry_time,
                            exit_time=now,
                            duration=duration
                        )
                    )
                
                # Calculate total time from the first entry in its path
                if hanger.path:
                    first_entry_time = hanger.path[0].entry_time
                    total_time_sec = (now - first_entry_time).total_seconds()

                path_summary = [entry.bath_name for entry in hanger.path]

                # Mark hanger as inactive
                hanger.current_bath = None
                hanger.entry_time = None
                hanger.last_seen = now
                logger.info(f"Hanger {hanger_id} unloaded. State set to inactive.")

            event = {
                "hanger": hanger_id,
                "time": now.strftime("%H:%M:%S"),
                "date": now.strftime("%d.%m.%Y"),
                "total_time_sec": total_time_sec,
                "baths_visited": path_summary,
                "timestamp": now.isoformat()
            }
            
            # Cache event
            self._unload_events.append(event)
            if len(self._unload_events) > 500:
                self._unload_events.pop(0)
            
            # Broadcast via WebSocket
            message = WebSocketMessage(type="unload_event", payload=event, timestamp=now)
            await websocket_manager.broadcast(message)
            
            logger.info(f"[Line Monitor] Unload recorded: Hanger {hanger_id} at {now.strftime('%H:%M:%S')}")
        
        except Exception as e:
            logger.error(f"[Line Monitor] Record unload error for hanger {hanger_id}: {e}", exc_info=True)
    
    def get_unload_events(self, limit: int = 100) -> List[dict]:
        """Get recent unload events."""
        return self._unload_events[-limit:]
    
    def get_hanger_state(self, hanger_num: int) -> Optional[HangerState]:
        """Get current state of a hanger."""
        return self._hangers.get(hanger_num)
    
    def get_active_hangers(self) -> List[HangerState]:
        """Get all hangers currently considered active in the line."""
        return [h for h in self._hangers.values() if h.current_bath is not None]


# Singleton instance
line_monitor = LineMonitorService()
