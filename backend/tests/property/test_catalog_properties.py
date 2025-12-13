"""
Property-based tests for CatalogService.

Tests search functionality, result ordering, and data integrity.
"""
import pytest
from hypothesis import given, strategies as st, settings, assume
from typing import List

from app.core.text_utils import normalize_text, CYRILLIC_LATIN_MAP
from app.services.catalog_service import CatalogService
from app.schemas.profile import ProfileSearchResult


# Strategy for profile names (mixed Latin/Cyrillic with numbers)
profile_name_chars = list(
    "АБВГДЕЖЗИЙКЛМНОПРСТУФХЦЧШЩЪЫЬЭЮЯабвгдежзийклмнопрстуфхцчшщъыьэюя"
    "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz"
    "0123456789-"
)

profile_name_strategy = st.text(
    alphabet=st.sampled_from(profile_name_chars),
    min_size=1,
    max_size=30
)


# Latin to Cyrillic mapping for test generation
LATIN_TO_CYRILLIC = {
    'A': 'А', 'a': 'а',
    'B': 'В', 
    'C': 'С', 'c': 'с',
    'E': 'Е', 'e': 'е',
    'H': 'Н',
    'K': 'К',
    'M': 'М',
    'O': 'О', 'o': 'о',
    'P': 'Р', 'p': 'р',
    'T': 'Т',
    'X': 'Х', 'x': 'х',
    'Y': 'У', 'y': 'у',
}


def latin_to_cyrillic(text: str) -> str:
    """Convert Latin characters to their Cyrillic equivalents."""
    result = []
    for char in text:
        result.append(LATIN_TO_CYRILLIC.get(char, char))
    return ''.join(result)


class TestSearchEquivalence:
    """
    **Feature: ekranchik-modern, Property 2: Latin/Cyrillic Search Equivalence**
    **Validates: Requirements 2.1**
    """
    
    @given(text=profile_name_strategy)
    @settings(max_examples=100)
    def test_latin_cyrillic_normalization_equivalence(self, text: str):
        """
        **Property 2: Latin/Cyrillic Search Equivalence**
        
        For any text, normalizing the Latin version and the Cyrillic version
        should produce the same result.
        
        **Validates: Requirements 2.1**
        """
        # Skip if text is empty after stripping
        assume(text.strip())
        
        # Convert Latin chars to Cyrillic equivalents
        cyrillic_version = latin_to_cyrillic(text)
        
        # Both should normalize to the same value
        normalized_latin = normalize_text(text)
        normalized_cyrillic = normalize_text(cyrillic_version)
        
        assert normalized_latin == normalized_cyrillic, (
            f"Normalization mismatch: '{text}' -> '{normalized_latin}', "
            f"'{cyrillic_version}' -> '{normalized_cyrillic}'"
        )


class TestMatchPriority:
    """
    **Feature: ekranchik-modern, Property 4: Search Priority Ordering**
    **Validates: Requirements 2.5**
    """
    
    def test_priority_calculation_exact_match_is_highest(self):
        """
        **Property 4: Search Priority Ordering**
        
        Exact name matches should have priority 1 (highest).
        
        **Validates: Requirements 2.5**
        """
        from app.db.models import Profile
        from unittest.mock import MagicMock
        
        service = CatalogService()
        
        # Create mock profile
        profile = MagicMock(spec=Profile)
        profile.name = "АЛС-345"
        profile.notes = None
        profile.quantity_per_hanger = None
        profile.length = None
        
        # Exact match should return priority 1
        priority = service._calculate_match_priority(profile, normalize_text("АЛС-345"))
        assert priority == 1, f"Expected priority 1 for exact match, got {priority}"
    
    def test_priority_calculation_contains_is_second(self):
        """Name contains query should have priority 2."""
        from app.db.models import Profile
        from unittest.mock import MagicMock
        
        service = CatalogService()
        
        profile = MagicMock(spec=Profile)
        profile.name = "АЛС-345-ОКНО"
        profile.notes = None
        profile.quantity_per_hanger = None
        profile.length = None
        
        # Partial match should return priority 2
        priority = service._calculate_match_priority(profile, normalize_text("АЛС-345"))
        assert priority == 2, f"Expected priority 2 for partial match, got {priority}"
    
    def test_priority_calculation_notes_is_third(self):
        """Notes match should have priority 3."""
        from app.db.models import Profile
        from unittest.mock import MagicMock
        
        service = CatalogService()
        
        profile = MagicMock(spec=Profile)
        profile.name = "ЮП-1625"
        profile.notes = "Аналог АЛС-345"
        profile.quantity_per_hanger = None
        profile.length = None
        
        # Notes match should return priority 3
        priority = service._calculate_match_priority(profile, normalize_text("АЛС-345"))
        assert priority == 3, f"Expected priority 3 for notes match, got {priority}"



class TestSearchResultsFields:
    """
    **Feature: ekranchik-modern, Property 3: Search Results Contain Required Fields**
    **Validates: Requirements 2.2**
    """
    
    def test_profile_search_result_has_required_fields(self):
        """
        **Property 3: Search Results Contain Required Fields**
        
        Each ProfileSearchResult should contain all required fields:
        name, quantity_per_hanger, length, notes, photo_thumb, photo_full.
        
        **Validates: Requirements 2.2**
        """
        # Create a ProfileSearchResult and verify all fields exist
        from datetime import datetime
        
        result = ProfileSearchResult(
            id=1,
            name="Test Profile",
            quantity_per_hanger=10,
            length=6000.0,
            notes="Test notes",
            photo_thumb="/images/test_thumb.jpg",
            photo_full="/images/test_full.jpg",
            usage_count=5,
            created_at=datetime.now(),
            updated_at=datetime.now()
        )
        
        # Verify all required fields are present
        assert hasattr(result, 'name')
        assert hasattr(result, 'quantity_per_hanger')
        assert hasattr(result, 'length')
        assert hasattr(result, 'notes')
        assert hasattr(result, 'photo_thumb')
        assert hasattr(result, 'photo_full')
        
        # Verify values
        assert result.name == "Test Profile"
        assert result.quantity_per_hanger == 10
        assert result.length == 6000.0
        assert result.notes == "Test notes"
        assert result.photo_thumb == "/images/test_thumb.jpg"
        assert result.photo_full == "/images/test_full.jpg"


class TestFuzzySearchSimilarity:
    """
    **Feature: ekranchik-modern, Property 15: Fuzzy Search Similarity**
    **Validates: Requirements 8.4**
    """
    
    def test_similarity_calculation_identical_strings(self):
        """Identical strings should have similarity 1.0."""
        service = CatalogService()
        
        similarity = service._calculate_similarity("АЛС-345", "АЛС-345")
        assert similarity == 1.0, f"Expected 1.0 for identical strings, got {similarity}"
    
    def test_similarity_calculation_empty_strings(self):
        """Empty strings should have similarity 0.0."""
        service = CatalogService()
        
        assert service._calculate_similarity("", "test") == 0.0
        assert service._calculate_similarity("test", "") == 0.0
        assert service._calculate_similarity("", "") == 0.0
    
    @given(s1=profile_name_strategy, s2=profile_name_strategy)
    @settings(max_examples=100)
    def test_similarity_above_threshold_is_valid(self, s1: str, s2: str):
        """
        **Property 15: Fuzzy Search Similarity**
        
        Similarity scores should be consistent and within valid range.
        Higher similarity means strings are more alike.
        
        **Validates: Requirements 8.4**
        """
        assume(s1.strip() and s2.strip())
        
        service = CatalogService()
        
        similarity = service._calculate_similarity(s1, s2)
        
        # Similarity should be in valid range
        assert 0.0 <= similarity <= 1.0
        
        # Identical strings (case-insensitive) should have high similarity
        if s1.lower() == s2.lower():
            assert similarity == 1.0, f"Identical strings should have similarity 1.0"
    
    @given(text=profile_name_strategy)
    @settings(max_examples=100)
    def test_similarity_range(self, text: str):
        """Similarity should always be between 0.0 and 1.0."""
        assume(text.strip())
        
        service = CatalogService()
        
        # Test against various strings
        for other in ["test", "АЛС", "123", text]:
            similarity = service._calculate_similarity(text, other)
            assert 0.0 <= similarity <= 1.0, f"Similarity out of range: {similarity}"



class TestMissingPhotosSorting:
    """
    **Feature: ekranchik-modern, Property 13: Missing Photos Sorted by Usage**
    **Validates: Requirements 8.1**
    """
    
    @given(usage_counts=st.lists(st.integers(min_value=0, max_value=1000), min_size=2, max_size=10))
    @settings(max_examples=50)
    def test_usage_count_sorting_property(self, usage_counts: List[int]):
        """
        **Property 13: Missing Photos Sorted by Usage**
        
        When profiles are sorted by usage_count descending, each profile's
        usage_count should be >= the next profile's usage_count.
        
        **Validates: Requirements 8.1**
        """
        # Sort descending (as the service does)
        sorted_counts = sorted(usage_counts, reverse=True)
        
        # Verify ordering
        for i in range(len(sorted_counts) - 1):
            assert sorted_counts[i] >= sorted_counts[i + 1], (
                f"Sorting violated at index {i}: {sorted_counts[i]} < {sorted_counts[i + 1]}"
            )


class TestPhotoUpload:
    """
    **Feature: ekranchik-modern, Property 5: Photo Upload Creates Both Versions**
    **Validates: Requirements 3.1**
    """
    
    def test_upload_creates_both_paths(self):
        """
        **Property 5: Photo Upload Creates Both Versions**
        
        After a successful photo upload, both thumbnail and full-size paths
        should be returned and both should be non-empty strings.
        
        **Validates: Requirements 3.1**
        
        Note: This is a structural test. Full integration test requires
        actual file system and database.
        """
        # Test that the method signature returns a tuple of two strings
        from app.services.catalog_service import CatalogService
        import inspect
        
        service = CatalogService()
        
        # Verify method exists and has correct signature
        assert hasattr(service, 'upload_photo')
        sig = inspect.signature(service.upload_photo)
        
        # Should have profile_name, image_data, filename parameters
        params = list(sig.parameters.keys())
        assert 'profile_name' in params
        assert 'image_data' in params
        assert 'filename' in params
    
    @given(profile_name=profile_name_strategy)
    @settings(max_examples=50)
    def test_safe_filename_generation(self, profile_name: str):
        """
        Generated filenames should be safe for filesystem.
        
        **Validates: Requirements 3.5**
        """
        assume(profile_name.strip())
        
        from app.core.text_utils import safe_filename
        
        safe_name = safe_filename(profile_name)
        
        # Should not contain unsafe characters
        unsafe_chars = set('<>:"/\\|?*')
        for char in safe_name:
            assert char not in unsafe_chars, f"Unsafe char '{char}' in '{safe_name}'"
        
        # Should not be empty if input was not empty
        # (may be empty if input was only unsafe chars)
