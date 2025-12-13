"""
Property-based tests for ExcelService.

Tests caching, data limits, and parsing consistency.
"""
import pytest
from hypothesis import given, strategies as st, settings, assume
from typing import List
from pathlib import Path
from unittest.mock import MagicMock, patch

from app.services.excel_service import ExcelService


class TestCacheInvalidation:
    """
    **Feature: ekranchik-modern, Property 10: Cache Invalidation on File Change**
    **Validates: Requirements 6.3**
    """
    
    def test_cache_invalidation_clears_cache(self):
        """
        **Property 10: Cache Invalidation on File Change**
        
        After calling invalidate_cache(), the cache should be cleared
        and the next read should fetch fresh data.
        
        **Validates: Requirements 6.3**
        """
        service = ExcelService()
        
        # Simulate cached state
        service._cache = MagicMock()
        service._cache_mtime = 12345.0
        service._cache_path = Path("/fake/path.xlsx")
        
        # Invalidate
        service.invalidate_cache()
        
        # Cache should be cleared
        assert service._cache is None
        assert service._cache_mtime is None
        assert service._cache_path is None
    
    def test_cache_validity_check_returns_false_when_empty(self):
        """Cache should be invalid when empty."""
        service = ExcelService()
        
        assert service._is_cache_valid(Path("/any/path.xlsx")) is False
    
    def test_cache_validity_check_returns_false_for_different_path(self):
        """Cache should be invalid for different file path."""
        service = ExcelService()
        
        service._cache = MagicMock()
        service._cache_mtime = 12345.0
        service._cache_path = Path("/path/a.xlsx")
        
        # Different path should invalidate
        assert service._is_cache_valid(Path("/path/b.xlsx")) is False


class TestRecentRecordsLimit:
    """
    **Feature: ekranchik-modern, Property 14: Recent Records Limit**
    **Validates: Requirements 8.2**
    """
    
    @given(limit=st.integers(min_value=1, max_value=100))
    @settings(max_examples=50)
    def test_recent_profiles_respects_limit(self, limit: int):
        """
        **Property 14: Recent Records Limit**
        
        The get_recent_profiles method should return at most `limit` records.
        
        **Validates: Requirements 8.2**
        """
        import pandas as pd
        
        service = ExcelService()
        
        # Create mock DataFrame with more records than limit
        num_records = limit + 50
        mock_df = pd.DataFrame({
            'profile': [f'Profile-{i}' for i in range(num_records)],
            'date': pd.date_range('2024-01-01', periods=num_records)
        })
        
        # Patch get_dataframe to return our mock
        with patch.object(service, 'get_dataframe', return_value=mock_df):
            results = service.get_recent_profiles(limit=limit)
        
        assert len(results) <= limit, f"Expected at most {limit} results, got {len(results)}"
    
    def test_recent_profiles_default_limit_is_50(self):
        """Default limit should be 50."""
        import pandas as pd
        import inspect
        
        service = ExcelService()
        
        # Check default parameter value
        sig = inspect.signature(service.get_recent_profiles)
        limit_param = sig.parameters.get('limit')
        
        assert limit_param is not None
        assert limit_param.default == 50


class TestProfileParsing:
    """Tests for profile parsing functionality."""
    
    @given(text=st.text(min_size=0, max_size=100))
    @settings(max_examples=50)
    def test_parse_profile_returns_dict_structure(self, text: str):
        """Parsed profile should always return expected dict structure."""
        service = ExcelService()
        
        result = service.parse_profile_with_processing(text)
        
        # Should always have these keys
        assert 'name' in result
        assert 'canonical_name' in result
        assert 'processing' in result
        
        # Processing should be a list
        assert isinstance(result['processing'], list)
    
    def test_parse_profile_extracts_processing_types(self):
        """Known processing types should be extracted."""
        service = ExcelService()
        
        # Test with known processing markers
        result = service.parse_profile_with_processing("АЛС-345 окно греб")
        
        assert 'окно' in result['processing']
        assert 'греб' in result['processing']
    
    @given(texts=st.lists(st.text(min_size=1, max_size=20), min_size=1, max_size=5))
    @settings(max_examples=50)
    def test_split_profiles_handles_separators(self, texts: List[str]):
        """Split profiles should handle various separators."""
        assume(all(t.strip() for t in texts))
        
        service = ExcelService()
        
        # Join with different separators
        for sep in [' + ', ', ', ' / ']:
            combined = sep.join(texts)
            results = service.split_profiles(combined)
            
            # Should return at least one result
            assert len(results) >= 1
            
            # Each result should have expected structure
            for r in results:
                assert 'name' in r
                assert 'canonical_name' in r
                assert 'processing' in r
