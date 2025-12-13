"""
Excel Watcher Service - monitors Excel file for changes and broadcasts updates.
"""
import asyncio
import logging
from pathlib import Path
from typing import Optional
from datetime import datetime

from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler, FileModifiedEvent

from app.core.config import settings
from app.services.excel_service import excel_service
from app.services.websocket_manager import websocket_manager
from app.schemas.websocket import WebSocketMessage

logger = logging.getLogger(__name__)


class ExcelFileHandler(FileSystemEventHandler):
    """Handler for Excel file modification events."""
    
    def __init__(self, callback):
        self.callback = callback
        self._last_modified = 0
        self._debounce_seconds = 1.0  # Debounce rapid changes
    
    def on_modified(self, event):
        if event.is_directory:
            return
        
        # Check if it's our Excel file
        if not event.src_path.endswith(('.xlsx', '.xls')):
            return
        
        # Debounce - ignore rapid successive changes
        now = datetime.now().timestamp()
        if now - self._last_modified < self._debounce_seconds:
            return
        
        self._last_modified = now
        
        # Schedule async callback
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                asyncio.create_task(self.callback(event.src_path))
            else:
                loop.run_until_complete(self.callback(event.src_path))
        except RuntimeError:
            # No event loop - create new one
            asyncio.run(self.callback(event.src_path))


class ExcelWatcher:
    """
    Service for monitoring Excel file changes.
    
    Uses watchdog to detect file modifications and broadcasts
    updates via WebSocket to connected clients.
    """
    
    def __init__(self):
        self._observer: Optional[Observer] = None
        self._running = False
        self._watch_path: Optional[Path] = None
    
    @property
    def is_running(self) -> bool:
        """Check if watcher is running."""
        return self._running
    
    async def _on_file_changed(self, file_path: str) -> None:
        """Handle file change event."""
        logger.info(f"Excel file changed: {file_path}")
        
        # Invalidate cache
        excel_service.invalidate_cache()
        
        # Broadcast update to all clients
        message = WebSocketMessage(
            type="data_update",
            payload={
                "source": "excel",
                "file": str(file_path),
                "message": "Excel data updated"
            },
            timestamp=datetime.now()
        )
        
        sent = await websocket_manager.broadcast(message)
        logger.info(f"Broadcast Excel update to {sent} clients")
    
    def start(self, watch_path: Optional[Path] = None) -> bool:
        """
        Start watching for Excel file changes.
        
        Args:
            watch_path: Directory to watch (uses config default if None)
        
        Returns:
            True if started successfully
        """
        if self._running:
            logger.warning("ExcelWatcher already running")
            return False
        
        path = watch_path or settings.excel_path
        if not path:
            logger.error("No Excel path configured")
            return False
        
        # Watch the directory containing the Excel file
        if path.is_file():
            watch_dir = path.parent
        else:
            watch_dir = path
        
        if not watch_dir.exists():
            logger.error(f"Watch directory does not exist: {watch_dir}")
            return False
        
        try:
            self._watch_path = watch_dir
            handler = ExcelFileHandler(self._on_file_changed)
            
            self._observer = Observer()
            self._observer.schedule(handler, str(watch_dir), recursive=False)
            self._observer.start()
            
            self._running = True
            logger.info(f"ExcelWatcher started, watching: {watch_dir}")
            return True
        except Exception as e:
            logger.error(f"Failed to start ExcelWatcher: {e}")
            return False
    
    def stop(self) -> None:
        """Stop watching for file changes."""
        if not self._running:
            return
        
        if self._observer:
            self._observer.stop()
            self._observer.join(timeout=5)
            self._observer = None
        
        self._running = False
        logger.info("ExcelWatcher stopped")


# Singleton instance
excel_watcher = ExcelWatcher()
