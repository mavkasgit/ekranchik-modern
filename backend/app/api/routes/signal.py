"""
Signal API routes - external event triggers.
"""
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.services.ftp_poller import ftp_poller
from app.services.excel_service import excel_service
from app.services.websocket_manager import websocket_manager
from app.schemas.websocket import WebSocketMessage

router = APIRouter(prefix="/signal", tags=["signal"])


class SignalRequest(BaseModel):
    """Request body for signal endpoint."""
    source: str
    event: str
    data: Optional[dict] = None


class SignalResponse(BaseModel):
    """Response for signal endpoint."""
    success: bool
    message: str


@router.post("", response_model=SignalResponse)
async def receive_signal(request: SignalRequest):
    """
    Receive external signals/events.
    
    Used for:
    - FTP event notifications from external systems
    - Manual refresh triggers
    - Integration with other services
    """
    if request.source == "ftp":
        # Trigger immediate FTP poll
        await ftp_poller.poll_now()
        return SignalResponse(
            success=True,
            message="FTP poll triggered"
        )
    
    elif request.source == "excel":
        # Invalidate Excel cache and broadcast
        excel_service.invalidate_cache()
        
        message = WebSocketMessage(
            type="data_update",
            payload={
                "source": "excel",
                "event": request.event,
                "message": "Excel data refreshed"
            },
            timestamp=datetime.now()
        )
        await websocket_manager.broadcast(message)
        
        return SignalResponse(
            success=True,
            message="Excel cache invalidated and broadcast sent"
        )
    
    elif request.source == "broadcast":
        # Generic broadcast
        message = WebSocketMessage(
            type="status",
            payload=request.data or {"event": request.event},
            timestamp=datetime.now()
        )
        sent = await websocket_manager.broadcast(message)
        
        return SignalResponse(
            success=True,
            message=f"Broadcast sent to {sent} clients"
        )
    
    else:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown signal source: {request.source}"
        )


@router.post("/refresh")
async def refresh_all():
    """
    Trigger full refresh of all data sources.
    """
    # Invalidate Excel cache
    excel_service.invalidate_cache()
    
    # Poll FTP
    await ftp_poller.poll_now()
    
    # Broadcast refresh
    message = WebSocketMessage(
        type="data_update",
        payload={
            "source": "system",
            "event": "full_refresh",
            "message": "All data sources refreshed"
        },
        timestamp=datetime.now()
    )
    sent = await websocket_manager.broadcast(message)
    
    return SignalResponse(
        success=True,
        message=f"Full refresh completed, broadcast to {sent} clients"
    )
