"""
Pydantic schemas for WebSocket messages
"""

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


class WebSocketMessage(BaseModel):
    """Base WebSocket message"""

    type: Literal[
        "data_update", "unload_event", "status", "error", "ping", "pong", "opcua_status", "heartbeat", "line_update"
    ]
    payload: dict[str, Any] = Field(default_factory=dict)
    timestamp: datetime = Field(default_factory=datetime.now)
