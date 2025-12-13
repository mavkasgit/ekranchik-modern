"""
Pydantic schemas for WebSocket messages
"""
from datetime import datetime
from typing import Literal, Any, Dict, Optional

from pydantic import BaseModel, Field


class WebSocketMessage(BaseModel):
    """Base WebSocket message"""
    type: Literal["data_update", "unload_event", "status", "error", "ping", "pong"]
    payload: Dict[str, Any] = Field(default_factory=dict)
    timestamp: datetime = Field(default_factory=datetime.now)


class DataUpdateMessage(WebSocketMessage):
    """Message for data updates (Excel changes)"""
    type: Literal["data_update"] = "data_update"


class UnloadEventMessage(WebSocketMessage):
    """Message for FTP unload events"""
    type: Literal["unload_event"] = "unload_event"


class StatusMessage(WebSocketMessage):
    """Message for status updates"""
    type: Literal["status"] = "status"


class ErrorMessage(WebSocketMessage):
    """Message for errors"""
    type: Literal["error"] = "error"
    error_code: Optional[str] = None
    error_detail: Optional[str] = None
