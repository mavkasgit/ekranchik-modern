"""
WebSocket API endpoint for real-time updates.
"""
from datetime import datetime

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.services.websocket_manager import websocket_manager
from app.schemas.websocket import WebSocketMessage

router = APIRouter()


@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """
    WebSocket endpoint for real-time dashboard updates.
    
    Clients connect here to receive:
    - Excel file updates (when production data changes)
    - FTP events (unload events from PLC)
    - Status updates (connection status, errors)
    
    Protocol:
    - Server sends JSON messages with type, data, timestamp
    - Client can send ping messages to keep connection alive
    """
    await websocket_manager.connect(websocket)
    
    # Send welcome message
    welcome = WebSocketMessage(
        type="status",
        payload={
            "message": "Connected to Ekranchik WebSocket",
            "clients": websocket_manager.connection_count
        },
        timestamp=datetime.now()
    )
    await websocket_manager.send_personal(websocket, welcome)
    
    try:
        while True:
            # Wait for client messages (ping/pong, etc.)
            data = await websocket.receive_json()
            
            # Handle ping
            if data.get("type") == "ping":
                pong = WebSocketMessage(
                    type="pong",
                    payload={},
                    timestamp=datetime.now()
                )
                await websocket_manager.send_personal(websocket, pong)
    
    except WebSocketDisconnect:
        await websocket_manager.disconnect(websocket)
    except Exception:
        await websocket_manager.disconnect(websocket)
