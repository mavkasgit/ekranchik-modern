"""
FTP Service - handles FTP connection to Omron PLC and log parsing.
"""
import re
from datetime import datetime, date
from typing import Optional, List, Tuple
from pathlib import Path

import aioftp

from app.core.config import settings
from app.schemas.dashboard import UnloadEvent


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
    
    @property
    def is_connected(self) -> bool:
        """Check if last connection attempt was successful."""
        return self._connected
    
    def _get_log_filename(self, for_date: Optional[date] = None) -> str:
        """
        Get log filename for a specific date.
        
        Format: YYMMDD.txt (e.g., 241213.txt for Dec 13, 2024)
        """
        target_date = for_date or date.today()
        return target_date.strftime("%y%m%d.txt")
    
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
        
        # Check for date rollover
        if self._last_date and self._last_date != today:
            self._last_position = 0
            date_changed = True
        
        self._last_date = today
        
        client = await self.connect()
        if not client:
            return [], date_changed
        
        try:
            log_path = self._get_log_path()
            
            # Check if file exists and get size
            try:
                stat = await client.stat(log_path)
                file_size = int(stat.get('size', 0))
            except (aioftp.StatusCodeError, KeyError):
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


# Singleton instance
ftp_service = FTPService()
