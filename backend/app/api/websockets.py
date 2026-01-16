"""
WebSocket API endpoint for real-time updates.
"""
from datetime import datetime
import logging
import asyncio

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.services.websocket_manager import websocket_manager
from app.schemas.websocket import WebSocketMessage

logger = logging.getLogger(__name__)
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
    - Server sends heartbeat every 30 seconds to keep connection alive
    
    Features:
    - Handles multiple concurrent connections
    - Exponential backoff for reconnection
    - Connection timeout handling
    - Graceful disconnection
    - Heartbeat to prevent connection drops
    """
    client_id = None
    heartbeat_task = None
    
    try:
        await websocket_manager.connect(websocket)
        client_id = id(websocket)
        
        logger.info(f"[WS] Client {client_id} connected. Total clients: {websocket_manager.connection_count}")
        
        # Send welcome message
        welcome = WebSocketMessage(
            type="status",
            payload={
                "message": "Connected to Ekranchik WebSocket",
                "clients": websocket_manager.connection_count,
                "client_id": client_id
            },
            timestamp=datetime.now()
        )
        await websocket_manager.send_personal(websocket, welcome)
        
        # Start heartbeat task
        async def send_heartbeat():
            """Send heartbeat every 30 seconds to keep connection alive"""
            try:
                while True:
                    await asyncio.sleep(30)
                    if websocket.client_state.name == 'CONNECTED':
                        heartbeat = WebSocketMessage(
                            type="heartbeat",
                            payload={"timestamp": datetime.now().isoformat()},
                            timestamp=datetime.now()
                        )
                        await websocket_manager.send_personal(websocket, heartbeat)
            except Exception as e:
                logger.debug(f"[WS] Heartbeat error for client {client_id}: {e}")
        
        heartbeat_task = asyncio.create_task(send_heartbeat())
        
        try:
            while True:
                # Wait for client messages (ping/pong, etc.)
                data = await websocket.receive_json()
                
                # Handle ping
                if data.get("type") == "ping":
                    pong = WebSocketMessage(
                        type="pong",
                        payload={"timestamp": datetime.now().isoformat()},
                        timestamp=datetime.now()
                    )
                    await websocket_manager.send_personal(websocket, pong)
        
        except WebSocketDisconnect:
            logger.info(f"[WS] Client {client_id} disconnected normally")
            await websocket_manager.disconnect(websocket)
        except Exception as e:
            logger.error(f"[WS] Error with client {client_id}: {e}")
            await websocket_manager.disconnect(websocket)
    
    except Exception as e:
        logger.error(f"[WS] Connection error: {e}")
        try:
            await websocket.close(code=1011, reason="Internal server error")
        except Exception:
            pass
    
    finally:
        # Cancel heartbeat task
        if heartbeat_task:
            heartbeat_task.cancel()
            try:
                await heartbeat_task
            except asyncio.CancelledError:
                pass
