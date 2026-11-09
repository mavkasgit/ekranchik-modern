"""
Signal API routes - external event triggers.
"""

import asyncio
from datetime import datetime

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.schemas.websocket import WebSocketMessage
from app.services.excel_service import excel_service
from app.services.websocket_manager import websocket_manager

router = APIRouter(prefix="/signal", tags=["signal"])


class SignalRequest(BaseModel):
    """Request body for signal endpoint."""

    source: str
    event: str
    data: dict | None = None


class SignalResponse(BaseModel):
    """Response for signal endpoint."""

    success: bool
    message: str


@router.post("", response_model=SignalResponse)
async def receive_signal(request: SignalRequest):
    """
    Receive external signals/events.

    Used for:
    - Manual refresh triggers
    - Integration with other services
    """
    if request.source == "excel":
        # Invalidate Excel cache and broadcast. Сброс берёт ``_lock`` сервиса,
        # а перечитывание книги держит его на всё время чтения по CIFS:
        # в event loop сигнал ждал бы чужое чтение и останавливал API.
        await asyncio.to_thread(excel_service.invalidate_cache)

        message = WebSocketMessage(
            type="data_update",
            payload={"source": "excel", "event": request.event, "message": "Excel data refreshed"},
            timestamp=datetime.now(),
        )
        await websocket_manager.broadcast(message)

        return SignalResponse(success=True, message="Excel cache invalidated and broadcast sent")

    elif request.source == "broadcast":
        # Generic broadcast
        message = WebSocketMessage(
            type="status", payload=request.data or {"event": request.event}, timestamp=datetime.now()
        )
        sent = await websocket_manager.broadcast(message)

        return SignalResponse(success=True, message=f"Broadcast sent to {sent} clients")

    else:
        raise HTTPException(status_code=400, detail=f"Unknown signal source: {request.source}")


@router.post("/refresh")
async def refresh_all():
    """
    Trigger full refresh of all data sources.
    """
    # Invalidate Excel cache. См. ``receive_signal``: ``invalidate_cache``
    # ждёт ``_lock``, который держит чтение книги в потоке.
    await asyncio.to_thread(excel_service.invalidate_cache)

    # Broadcast refresh
    message = WebSocketMessage(
        type="data_update",
        payload={"source": "system", "event": "full_refresh", "message": "All data sources refreshed"},
        timestamp=datetime.now(),
    )
    sent = await websocket_manager.broadcast(message)

    return SignalResponse(success=True, message=f"Full refresh completed, broadcast to {sent} clients")
