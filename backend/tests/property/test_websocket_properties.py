"""
Property tests for WebSocket Manager.

Tests:
- Property 11: WebSocket Broadcast to All Clients
"""
import asyncio
from datetime import datetime
from typing import List
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from hypothesis import given, strategies as st, settings as hyp_settings
from starlette.websockets import WebSocketState

from app.services.websocket_manager import WebSocketManager
from app.schemas.websocket import WebSocketMessage


# Valid message types from schema
VALID_MSG_TYPES = ["data_update", "unload_event", "status", "error", "ping", "pong"]


class MockWebSocket:
    """Mock WebSocket for testing."""
    
    def __init__(self, connected: bool = True):
        self.client_state = WebSocketState.CONNECTED if connected else WebSocketState.DISCONNECTED
        self.sent_messages: List[dict] = []
        self.accepted = False
        self.closed = False
    
    async def accept(self):
        self.accepted = True
    
    async def send_json(self, data: dict):
        if self.client_state != WebSocketState.CONNECTED:
            raise RuntimeError("WebSocket not connected")
        self.sent_messages.append(data)
    
    async def close(self):
        self.closed = True
        self.client_state = WebSocketState.DISCONNECTED


@pytest.fixture
def manager():
    """Create fresh WebSocketManager for each test."""
    return WebSocketManager()


@pytest.fixture
def mock_websocket():
    """Create a mock WebSocket."""
    return MockWebSocket()


class TestWebSocketBroadcast:
    """Property 11: WebSocket Broadcast to All Clients."""
    
    @given(
        num_clients=st.integers(min_value=1, max_value=20),
        msg_type=st.sampled_from(VALID_MSG_TYPES),
        data_keys=st.lists(st.text(min_size=1, max_size=10, alphabet="abcdefghijklmnopqrstuvwxyz"), min_size=0, max_size=5)
    )
    @hyp_settings(max_examples=50, deadline=None)
    def test_broadcast_reaches_all_connected_clients(
        self,
        num_clients: int,
        msg_type: str,
        data_keys: List[str]
    ):
        """All connected clients should receive broadcast messages."""
        async def run_test():
            manager = WebSocketManager()
            
            # Create mock clients
            clients = [MockWebSocket() for _ in range(num_clients)]
            
            # Connect all clients
            for client in clients:
                await manager.connect(client)
            
            assert manager.connection_count == num_clients
            
            # Create message with generated data
            payload = {key: f"value_{i}" for i, key in enumerate(data_keys)}
            message = WebSocketMessage(
                type=msg_type,
                payload=payload,
                timestamp=datetime.now()
            )
            
            # Broadcast
            sent_count = await manager.broadcast(message)
            
            # Verify all clients received
            assert sent_count == num_clients
            for client in clients:
                assert len(client.sent_messages) == 1
                assert client.sent_messages[0]["type"] == msg_type
        
        asyncio.get_event_loop().run_until_complete(run_test())
    
    @given(
        connected_count=st.integers(min_value=1, max_value=10),
        disconnected_count=st.integers(min_value=0, max_value=5)
    )
    @hyp_settings(max_examples=30, deadline=None)
    def test_broadcast_skips_disconnected_clients(
        self,
        connected_count: int,
        disconnected_count: int
    ):
        """Disconnected clients should not receive messages."""
        async def run_test():
            manager = WebSocketManager()
            
            # Create connected clients
            connected = [MockWebSocket(connected=True) for _ in range(connected_count)]
            disconnected = [MockWebSocket(connected=False) for _ in range(disconnected_count)]
            
            # Add all to manager (simulating they were connected before)
            for client in connected + disconnected:
                # Manually add to bypass accept() for disconnected
                manager._connections.add(client)
            
            message = WebSocketMessage(
                type="status",
                payload={"test": True},
                timestamp=datetime.now()
            )
            
            sent_count = await manager.broadcast(message)
            
            # Only connected clients should receive
            assert sent_count == connected_count
            
            for client in connected:
                assert len(client.sent_messages) == 1
            
            for client in disconnected:
                assert len(client.sent_messages) == 0
        
        asyncio.get_event_loop().run_until_complete(run_test())
    
    @given(
        num_clients=st.integers(min_value=2, max_value=10),
        exclude_index=st.integers(min_value=0, max_value=9)
    )
    @hyp_settings(max_examples=30, deadline=None)
    def test_broadcast_with_exclude(
        self,
        num_clients: int,
        exclude_index: int
    ):
        """Excluded client should not receive broadcast."""
        async def run_test():
            manager = WebSocketManager()
            
            clients = [MockWebSocket() for _ in range(num_clients)]
            for client in clients:
                await manager.connect(client)
            
            # Ensure exclude_index is valid
            exclude_idx = exclude_index % num_clients
            excluded = clients[exclude_idx]
            
            message = WebSocketMessage(
                type="data_update",
                payload={},
                timestamp=datetime.now()
            )
            
            sent_count = await manager.broadcast(message, exclude=excluded)
            
            # All except excluded should receive
            assert sent_count == num_clients - 1
            assert len(excluded.sent_messages) == 0
            
            for i, client in enumerate(clients):
                if i != exclude_idx:
                    assert len(client.sent_messages) == 1
        
        asyncio.get_event_loop().run_until_complete(run_test())


class TestWebSocketConnectionManagement:
    """Tests for connection tracking."""
    
    @given(num_connections=st.integers(min_value=0, max_value=50))
    @hyp_settings(max_examples=30, deadline=None)
    def test_connection_count_accurate(self, num_connections: int):
        """Connection count should match actual connections."""
        async def run_test():
            manager = WebSocketManager()
            
            clients = []
            for _ in range(num_connections):
                client = MockWebSocket()
                await manager.connect(client)
                clients.append(client)
            
            assert manager.connection_count == num_connections
            
            # Disconnect half
            to_disconnect = num_connections // 2
            for i in range(to_disconnect):
                await manager.disconnect(clients[i])
            
            assert manager.connection_count == num_connections - to_disconnect
        
        asyncio.get_event_loop().run_until_complete(run_test())
    
    def test_disconnect_removes_client(self):
        """Disconnecting should remove client from set."""
        async def run_test():
            manager = WebSocketManager()
            client = MockWebSocket()
            
            await manager.connect(client)
            assert manager.connection_count == 1
            
            await manager.disconnect(client)
            assert manager.connection_count == 0
            assert client not in manager.connections
        
        asyncio.get_event_loop().run_until_complete(run_test())
    
    def test_close_all_clears_connections(self):
        """close_all should disconnect all clients."""
        async def run_test():
            manager = WebSocketManager()
            
            clients = [MockWebSocket() for _ in range(5)]
            for client in clients:
                await manager.connect(client)
            
            assert manager.connection_count == 5
            
            await manager.close_all()
            
            assert manager.connection_count == 0
            for client in clients:
                assert client.closed
        
        asyncio.get_event_loop().run_until_complete(run_test())


class TestWebSocketMessageSending:
    """Tests for message sending functionality."""
    
    @given(
        msg_type=st.sampled_from(VALID_MSG_TYPES),
        data_value=st.text(min_size=0, max_size=100)
    )
    @hyp_settings(max_examples=30, deadline=None)
    def test_send_personal_delivers_message(self, msg_type: str, data_value: str):
        """Personal message should be delivered to specific client."""
        async def run_test():
            manager = WebSocketManager()
            client = MockWebSocket()
            await manager.connect(client)
            
            message = WebSocketMessage(
                type=msg_type,
                payload={"value": data_value},
                timestamp=datetime.now()
            )
            
            success = await manager.send_personal(client, message)
            
            assert success
            assert len(client.sent_messages) == 1
            assert client.sent_messages[0]["type"] == msg_type
            assert client.sent_messages[0]["payload"]["value"] == data_value
        
        asyncio.get_event_loop().run_until_complete(run_test())
    
    def test_send_personal_fails_for_disconnected(self):
        """Sending to disconnected client should fail gracefully."""
        async def run_test():
            manager = WebSocketManager()
            client = MockWebSocket(connected=False)
            manager._connections.add(client)
            
            message = WebSocketMessage(
                type="status",
                payload={},
                timestamp=datetime.now()
            )
            
            success = await manager.send_personal(client, message)
            
            assert not success
            assert len(client.sent_messages) == 0
        
        asyncio.get_event_loop().run_until_complete(run_test())
    
    @given(
        msg_type=st.sampled_from(["data_update", "unload_event", "status"]),
        num_keys=st.integers(min_value=0, max_value=10)
    )
    @hyp_settings(max_examples=20, deadline=None)
    def test_broadcast_dict_convenience_method(self, msg_type: str, num_keys: int):
        """broadcast_dict should wrap data in WebSocketMessage."""
        async def run_test():
            manager = WebSocketManager()
            client = MockWebSocket()
            await manager.connect(client)
            
            data = {f"key_{i}": f"value_{i}" for i in range(num_keys)}
            
            sent_count = await manager.broadcast_dict(data, msg_type)
            
            assert sent_count == 1
            assert len(client.sent_messages) == 1
            assert client.sent_messages[0]["type"] == msg_type
            assert client.sent_messages[0]["payload"] == data
        
        asyncio.get_event_loop().run_until_complete(run_test())
