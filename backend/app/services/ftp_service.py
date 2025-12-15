"""
FTP Service - handles FTP connection to Omron PLC and log parsing.
Includes simulation mode for testing with local files.
"""
import re
import asyncio
import logging
from datetime import datetime, date, timedelta
from typing import Optional, List, Tuple
from pathlib import Path

import aioftp

from app.core.config import settings
from app.schemas.dashboard import UnloadEvent

logger = logging.getLogger(__name__)


class FTPService:
    """
    Service for reading FTP logs from Omron PLC.
    
    Features:
    - Async FTP connection
    - Log file reading with incremental polling
    - Unload event parsing
    - Date rollover handling
    """
    
    def __init__(self):
        self._last_position: int = 0
        self._last_date: Optional[date] = None
        self._connected: bool = False
        
        # Simulation mode
        self._simulation_mode: bool = False
        self._simulation_file: Optional[Path] = None
        self._simulation_position: int = 0
        self._simulation_lines: List[str] = []
        self._simulation_line_index: int = 0
        self._simulation_events: List[UnloadEvent] = []
        self._simulation_event_index: int = 0
        self._simulation_date: Optional[date] = None
    
    @property
    def is_connected(self) -> bool:
        """Check if last connection attempt was successful."""
        return self._connected
    
    def _get_log_filename(self, for_date: Optional[date] = None) -> str:
        """
        Get log filename for a specific date.
        
        Format: YYYY-MM-DD.txt (e.g., 2025-12-13.txt for Dec 13, 2025)
        """
        target_date = for_date or date.today()
        return target_date.strftime("%Y-%m-%d.txt")
    
    def _get_log_path(self, for_date: Optional[date] = None) -> str:
        """Get full FTP path to log file."""
        filename = self._get_log_filename(for_date)
        base_path = settings.FTP_BASE_PATH.rstrip('/')
        return f"{base_path}/{filename}"

    async def connect(self) -> Optional[aioftp.Client]:
        """
        Establish async FTP connection.
        
        Returns:
            FTP client if successful, None otherwise
        """
        try:
            client = aioftp.Client()
            await client.connect(
                settings.FTP_HOST,
                settings.FTP_PORT
            )
            await client.login(
                settings.FTP_USER,
                settings.FTP_PASSWORD
            )
            self._connected = True
            return client
        except Exception as e:
            self._connected = False
            return None
    
    async def read_today_log(self) -> str:
        """
        Read today's log file from FTP.
        
        Returns:
            Log file content as string, empty string on error
        """
        client = await self.connect()
        if not client:
            return ""
        
        try:
            log_path = self._get_log_path()
            
            # Check if file exists
            try:
                await client.stat(log_path)
            except aioftp.StatusCodeError:
                return ""
            
            # Read file content
            content = b""
            async with client.download_stream(log_path) as stream:
                async for block in stream.iter_by_block():
                    content += block
            
            return content.decode('utf-8', errors='ignore')
        except Exception as e:
            return ""
        finally:
            await client.quit()
    
    def parse_unload_events(self, content: str) -> List[UnloadEvent]:
        """
        Parse unload events from log content.
        
        Expected log format:
        HH:MM:SS Unload hanger XX
        or similar patterns
        
        Args:
            content: Raw log file content
        
        Returns:
            List of parsed UnloadEvent objects
        """
        events = []
        
        if not content:
            return events
        
        # Pattern for unload events
        # Matches: "HH:MM:SS" followed by unload/разгрузка and hanger number
        patterns = [
            r'(\d{2}:\d{2}:\d{2})\s+[Uu]nload\s+[Hh]anger\s+(\d+)',
            r'(\d{2}:\d{2}:\d{2})\s+разгрузка\s+подвес[а]?\s+(\d+)',
            r'(\d{2}:\d{2}:\d{2})\s+(\d+)\s+разгруз',
        ]
        
        for line in content.split('\n'):
            line = line.strip()
            if not line:
                continue
            
            for pattern in patterns:
                match = re.search(pattern, line, re.IGNORECASE)
                if match:
                    time_str = match.group(1)
                    hanger_num = int(match.group(2))
                    
                    # Create timestamp for today
                    today = date.today()
                    try:
                        time_parts = time_str.split(':')
                        timestamp = datetime(
                            today.year, today.month, today.day,
                            int(time_parts[0]), int(time_parts[1]), int(time_parts[2])
                        )
                    except (ValueError, IndexError):
                        timestamp = datetime.now()
                    
                    events.append(UnloadEvent(
                        time=time_str,
                        hanger=hanger_num,
                        timestamp=timestamp
                    ))
                    break
        
        return events

    async def poll_incremental(self) -> Tuple[List[UnloadEvent], bool]:
        """
        Poll for new events since last read.
        
        Uses byte offset tracking to only read new content.
        Handles date rollover by resetting position.
        
        Returns:
            Tuple of (new events list, date_changed flag)
        """
        today = date.today()
        date_changed = False
        
        # Check for date rollover (new day = new file)
        if self._last_date and self._last_date != today:
            logger.info(f"[FTP] Date changed: {self._last_date} -> {today}. Switching to new log file.")
            self._last_position = 0
            date_changed = True
        
        self._last_date = today
        
        client = await self.connect()
        if not client:
            return [], date_changed
        
        try:
            log_path = self._get_log_path()
            
            # Log file name on date change or first read
            if date_changed or self._last_position == 0:
                logger.info(f"[FTP] Reading log file: {log_path}")
            
            # Check if file exists and get size
            try:
                stat = await client.stat(log_path)
                file_size = int(stat.get('size', 0))
            except (aioftp.StatusCodeError, KeyError):
                logger.warning(f"[FTP] Log file not found: {log_path}")
                return [], date_changed
            
            # No new content
            if file_size <= self._last_position:
                return [], date_changed
            
            # Read from last position
            content = b""
            async with client.download_stream(log_path, offset=self._last_position) as stream:
                async for block in stream.iter_by_block():
                    content += block
            
            # Update position
            self._last_position = file_size
            
            # Parse new content
            text = content.decode('utf-8', errors='ignore')
            events = self.parse_unload_events(text)
            
            return events, date_changed
        except Exception as e:
            return [], date_changed
        finally:
            await client.quit()
    
    def reset_position(self) -> None:
        """Reset read position (for manual reset or testing)."""
        self._last_position = 0
        self._last_date = None
    
    async def poll_multiday(self, days: int = 2) -> Tuple[List[UnloadEvent], bool]:
        """
        Poll for events from multiple days of logs.
        
        Reads N days of log files (today, yesterday, etc.) and returns all events.
        Detects date changes for rollover handling.
        
        Args:
            days: Number of days to read (default: 2)
        
        Returns:
            Tuple of (all events list, date_changed flag)
        """
        today = date.today()
        date_changed = False
        
        # Check for date rollover
        if self._last_date and self._last_date != today:
            logger.info(f"[FTP] Date changed: {self._last_date} -> {today}. Reading new log files.")
            date_changed = True
        
        self._last_date = today
        
        all_events = []
        
        # Read logs for each day
        for day_offset in range(days):
            file_date = today - timedelta(days=day_offset)
            
            try:
                content = await self.read_log_for_date(file_date)
                if content:
                    events = self.parse_unload_events_cj2m(content)
                    all_events.extend(events)
            except Exception as e:
                logger.error(f"[FTP] Error reading log for {file_date}: {e}")
        
        if all_events:
            logger.info(f"[FTP] Read {len(all_events)} events from {days} days")
        
        return all_events, date_changed
    
    async def read_log_for_date(self, for_date: date) -> str:
        """
        Read log file for a specific date from FTP.
        
        Args:
            for_date: Date to read log for
        
        Returns:
            Log file content as string, empty string on error
        """
        client = await self.connect()
        if not client:
            return ""
        
        try:
            log_path = self._get_log_path(for_date)
            
            # Check if file exists
            try:
                await client.stat(log_path)
            except aioftp.StatusCodeError:
                logger.warning(f"[FTP] Log file not found: {log_path}")
                return ""
            
            # Read file content
            content = b""
            async with client.download_stream(log_path) as stream:
                async for block in stream.iter_by_block():
                    content += block
            
            return content.decode('utf-8', errors='ignore')
        except Exception as e:
            logger.error(f"[FTP] Error reading {log_path}: {e}")
            return ""
        finally:
            await client.quit()
    
    # ==================== SIMULATION MODE ====================
    
    def start_simulation(self, file_path: Path) -> bool:
        """
        Start simulation mode - loads ALL events from file immediately.
        
        Args:
            file_path: Path to local log file
        
        Returns:
            True if simulation started successfully
        """
        if not file_path.exists():
            logger.error(f"Simulation file not found: {file_path}")
            return False
        
        try:
            # Read entire file and parse ALL events immediately
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()
            
            # Parse date from filename (e.g., 2025-11-29.txt -> 29.11.2025)
            self._simulation_date: Optional[str] = None
            filename = file_path.stem  # "2025-11-29"
            date_match = re.match(r'(\d{4})-(\d{2})-(\d{2})', filename)
            if date_match:
                year, month, day = date_match.groups()
                self._simulation_date = f"{day}.{month}.{year}"
            
            # Parse all events from file
            all_events = self.parse_unload_events_cj2m(content)
            
            self._simulation_mode = True
            self._simulation_file = file_path
            self._simulation_events = all_events  # Store all parsed events
            self._connected = True
            
            logger.info(f"[SIMULATION] Loaded {len(all_events)} events from {file_path}, date={self._simulation_date}")
            return True
        except Exception as e:
            logger.error(f"Failed to start simulation: {e}")
            return False
    
    def stop_simulation(self) -> None:
        """Stop simulation mode."""
        self._simulation_mode = False
        self._simulation_file = None
        self._simulation_events = []
        self._simulation_event_index = 0
        logger.info("[SIMULATION] Stopped")
    
    @property
    def is_simulation(self) -> bool:
        """Check if running in simulation mode."""
        return self._simulation_mode
    
    @property
    def simulation_events_count(self) -> int:
        """Get total number of simulation events."""
        return len(self._simulation_events) if hasattr(self, '_simulation_events') else 0
    
    def get_all_simulation_events(self) -> List[UnloadEvent]:
        """
        Get ALL simulation events at once.
        
        Returns:
            List of all UnloadEvent objects
        """
        if not self._simulation_mode or not hasattr(self, '_simulation_events'):
            return []
        
        return self._simulation_events
    
    def parse_unload_events_cj2m(self, content: str) -> List[UnloadEvent]:
        """
        Parse unload events from CJ2M log format.
        
        Pattern: HH:MM:SS.mmm L# Команда от CJ2M: Разгрузка подвеса - N в поз. 34
        
        Args:
            content: Raw log content
        
        Returns:
            List of UnloadEvent objects
        """
        events = []
        
        if not content:
            return events
        
        # Pattern for CJ2M unload events (flexible whitespace, optional trailing dot)
        pattern = r'(\d{2}):(\d{2}):(\d{2})\.\d+\s+L#\s+Команда\s+от\s+CJ2M:\s+Разгрузка\s+подвеса\s+-\s+(\d+)\s+в\s+поз\.\s*34\.?'
        
        # Use simulation date if available, otherwise today
        event_date = getattr(self, '_simulation_date', None)
        if not event_date:
            event_date = date.today().strftime("%d.%m.%Y")
        
        for line in content.split('\n'):
            line = line.strip()
            if not line:
                continue
            
            match = re.search(pattern, line)
            if match:
                hours = int(match.group(1))
                minutes = int(match.group(2))
                seconds = int(match.group(3))
                hanger_num = int(match.group(4))
                
                time_str = f"{hours:02d}:{minutes:02d}:{seconds:02d}"
                
                # Create timestamp
                today = date.today()
                try:
                    timestamp = datetime(
                        today.year, today.month, today.day,
                        hours, minutes, seconds
                    )
                except ValueError:
                    timestamp = datetime.now()
                
                events.append(UnloadEvent(
                    time=time_str,
                    hanger=hanger_num,
                    date=event_date,
                    timestamp=timestamp
                ))
        
        return events


# Singleton instance
ftp_service = FTPService()
