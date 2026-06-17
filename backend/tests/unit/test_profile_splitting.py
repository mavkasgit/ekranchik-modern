import pytest
import re
from unittest.mock import patch, MagicMock, AsyncMock
from contextlib import asynccontextmanager

from app.api.routes.dashboard import parse_profile_name
from app.api.routes.analysis import get_recent_profiles, get_recent_missing_profiles
from app.db.models import Profile

def test_parse_profile_name_basic():
    """Test parse_profile_name helper function"""
    name, processing = parse_profile_name("СРП228 окно")
    assert name == "СРП228"
    assert processing == ["окно"]

def test_parse_profile_name_complex():
    """Test parse_profile_name with multiple processing types"""
    name, processing = parse_profile_name("юп-3233 греб + сверло")
    assert name == "юп-3233"
    # Order is determined by order of PROCESSING_KEYWORDS in dashboard.py
    assert "греб" in processing
    assert "сверло" in processing

def test_split_by_plus_and_slash():
    """Verify regex splits profiles by both + and / correctly"""
    input_str = "3473/2902/2016/2077/048/081/2616/2604/137/4892/7314/6844"
    parts = [p.strip() for p in re.split(r'[+/]', input_str) if p.strip()]
    expected = [
        "3473", "2902", "2016", "2077", "048", "081",
        "2616", "2604", "137", "4892", "7314", "6844"
    ]
    assert parts == expected

    mixed_input = "3473 + 2902 / 2016"
    mixed_parts = [p.strip() for p in re.split(r'[+/]', mixed_input) if p.strip()]
    assert mixed_parts == ["3473", "2902", "2016"]

@pytest.mark.asyncio
async def test_get_recent_profiles_has_photo_logic():
    """Test get_recent_profiles route and its has_photo logic with slash separation"""
    mock_recent = [
        {"profile": "3473/2902", "date": "17.06.26", "number": "1"},
        {"profile": "2016", "date": "17.06.26", "number": "2"},
        {"profile": "—", "date": "17.06.26", "number": "3"},
    ]
    
    mock_photos_map = {
        "3473": {"thumb": "photo_3473.jpg"},
        "2902": {"thumb": "photo_2902.jpg"},
        "2016": {}, # Missing photo
    }
    
    with patch("app.api.routes.analysis.excel_service.get_recent_profiles", return_value=mock_recent), \
         patch("app.api.routes.analysis.catalog_service.get_profiles_photos_batch", new_callable=AsyncMock, return_value=mock_photos_map):
        
        result = await get_recent_profiles(limit=10)
        
        # 3473/2902: both have photos -> has_photo = True
        assert result[0]["has_photo"] is True
        
        # 2016: missing photo -> has_photo = False
        assert result[1]["has_photo"] is False
        
        # —: empty -> has_photo = False
        assert result[2]["has_photo"] is False

@pytest.mark.asyncio
async def test_get_recent_missing_profiles_checker_logic(db_session):
    """Test get_recent_missing_profiles checker logic using SQLite in-memory db"""
    # 1. Populate DB with profiles with and without photos
    # Profile 3473 has photo
    p1 = Profile(name="3473", photo_thumb="photo_3473.jpg", usage_count=1)
    # Profile 2902 has photo
    p2 = Profile(name="2902", photo_thumb="photo_2902.jpg", usage_count=1)
    # Profile 2016 has NO photo
    p3 = Profile(name="2016", photo_thumb="", usage_count=1)
    
    db_session.add_all([p1, p2, p3])
    await db_session.commit()
    
    @asynccontextmanager
    async def mock_get_session():
        yield db_session
        
    mock_excel_data = [
        {"profile": "3473/2902", "date": "17.06.26", "number": "1"},  # Both have photos, should be skipped
        {"profile": "3473/2016", "date": "17.06.26", "number": "2"},  # 2016 is missing photo, should be included
        {"profile": "2077", "date": "17.06.26", "number": "3"},       # Not in DB (missing), should be included
    ]
    
    # We will capture the checker passed to get_recent_missing_profiles
    captured_checker = None
    
    def mock_get_recent_missing(limit, profile_checker=None):
        nonlocal captured_checker
        captured_checker = profile_checker
        # Filter mock data using checker
        filtered = []
        for item in mock_excel_data:
            if profile_checker and profile_checker(item["profile"]):
                continue
            filtered.append(item)
        return filtered

    with patch("app.api.routes.analysis.get_session", mock_get_session), \
         patch("app.api.routes.analysis.excel_service.get_recent_missing_profiles", side_effect=mock_get_recent_missing):
        
        result = await get_recent_missing_profiles(limit=10)
        
        assert captured_checker is not None
        # Verify checker behaves correctly
        assert captured_checker("3473/2902") is True  # Both in DB with photos
        assert captured_checker("3473/2016") is False # 2016 has no photo
        assert captured_checker("2077") is False      # 2077 not in DB
        
        # Verify the returned list contains only the missing items
        assert len(result) == 2
        assert result[0]["profile"] == "3473/2016"
        assert result[0]["has_photo"] is False
        assert result[1]["profile"] == "2077"
        assert result[1]["has_photo"] is False
