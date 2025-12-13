"""
Unit tests for Pydantic schemas
"""
import pytest
from datetime import datetime
from pydantic import ValidationError

from app.schemas.profile import (
    ProfileBase,
    ProfileCreate,
    ProfileUpdate,
    ProfileResponse,
)
from app.schemas.dashboard import HangerData, UnloadEvent
from app.schemas.websocket import WebSocketMessage


class TestProfileSchemas:
    """Tests for Profile schemas"""
    
    def test_profile_base_valid(self):
        """Valid ProfileBase creates successfully"""
        profile = ProfileBase(name="ЮП-1625")
        assert profile.name == "ЮП-1625"
        assert profile.quantity_per_hanger is None
    
    def test_profile_base_with_all_fields(self):
        """ProfileBase with all optional fields"""
        profile = ProfileBase(
            name="ALS-345",
            quantity_per_hanger=10,
            length=6000.5,
            notes="Test notes"
        )
        assert profile.name == "ALS-345"
        assert profile.quantity_per_hanger == 10
        assert profile.length == 6000.5
        assert profile.notes == "Test notes"
    
    def test_profile_base_empty_name_fails(self):
        """Empty name should fail validation"""
        with pytest.raises(ValidationError):
            ProfileBase(name="")
    
    def test_profile_base_negative_quantity_fails(self):
        """Negative quantity should fail validation"""
        with pytest.raises(ValidationError):
            ProfileBase(name="Test", quantity_per_hanger=-1)
    
    def test_profile_create(self):
        """ProfileCreate works like ProfileBase"""
        profile = ProfileCreate(name="Test Profile")
        assert profile.name == "Test Profile"

    def test_profile_response_from_dict(self):
        """ProfileResponse can be created from dict (simulating ORM)"""
        data = {
            "id": 1,
            "name": "ЮП-1625",
            "quantity_per_hanger": 10,
            "length": 6000.0,
            "notes": "Test",
            "photo_thumb": "/static/images/test-thumb.jpg",
            "photo_full": "/static/images/test.jpg",
            "usage_count": 5,
            "created_at": datetime.now(),
            "updated_at": datetime.now(),
        }
        profile = ProfileResponse(**data)
        assert profile.id == 1
        assert profile.name == "ЮП-1625"
        assert profile.has_photo is True


class TestDashboardSchemas:
    """Tests for Dashboard schemas"""
    
    def test_hanger_data_minimal(self):
        """HangerData with minimal required fields"""
        hanger = HangerData(number="123", date="01.01.2024", time="10:00")
        assert hanger.number == "123"
        assert hanger.client == "—"
        assert hanger.profile == "—"
    
    def test_unload_event(self):
        """UnloadEvent creates correctly"""
        event = UnloadEvent(time="10:30:45", hanger=42)
        assert event.time == "10:30:45"
        assert event.hanger == 42
    
    def test_unload_event_negative_hanger_fails(self):
        """Negative hanger number should fail"""
        with pytest.raises(ValidationError):
            UnloadEvent(time="10:00:00", hanger=-1)


class TestWebSocketSchemas:
    """Tests for WebSocket schemas"""
    
    def test_websocket_message(self):
        """WebSocketMessage creates correctly"""
        msg = WebSocketMessage(type="data_update", payload={"test": "data"})
        assert msg.type == "data_update"
        assert msg.payload == {"test": "data"}
        assert msg.timestamp is not None
    
    def test_websocket_message_invalid_type_fails(self):
        """Invalid message type should fail"""
        with pytest.raises(ValidationError):
            WebSocketMessage(type="invalid_type", payload={})
