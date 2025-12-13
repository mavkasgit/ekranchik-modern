"""
Property-based tests for text normalization.

**Feature: ekranchik-modern, Property 1: Text Normalization Idempotence**
**Validates: Requirements 9.4**
"""
import pytest
from hypothesis import given, strategies as st, settings

from app.core.text_utils import normalize_text, transliterate_cyrillic


# Strategy for generating text with mixed Latin/Cyrillic
mixed_text = st.text(
    alphabet=st.sampled_from(
        list("АБВГДЕЖЗИЙКЛМНОПРСТУФХЦЧШЩЪЫЬЭЮЯабвгдежзийклмнопрстуфхцчшщъыьэюя"
             "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz"
             "0123456789-_ ./")
    ),
    min_size=0,
    max_size=100
)


class TestNormalizationProperties:
    """Property-based tests for normalize_text"""
    
    @given(text=mixed_text)
    @settings(max_examples=100)
    def test_idempotence(self, text: str):
        """
        **Property 1: Text Normalization Idempotence**
        
        For any text string, applying normalize_text twice should produce
        the same result as applying it once: normalize(normalize(x)) == normalize(x)
        
        **Validates: Requirements 9.4**
        """
        once = normalize_text(text)
        twice = normalize_text(once)
        assert once == twice, f"Idempotence failed: '{text}' -> '{once}' -> '{twice}'"

    @given(text=mixed_text)
    @settings(max_examples=100)
    def test_result_is_lowercase(self, text: str):
        """
        Normalized text should be lowercase (no uppercase characters).
        """
        result = normalize_text(text)
        # Check that result has no uppercase Latin or Cyrillic
        uppercase_chars = set("АБВГДЕЖЗИЙКЛМНОПРСТУФХЦЧШЩЪЫЬЭЮЯABCDEFGHIJKLMNOPQRSTUVWXYZ")
        for char in result:
            assert char not in uppercase_chars, f"Uppercase found in '{result}'"
    
    @given(text=mixed_text)
    @settings(max_examples=100)
    def test_no_separators_in_result(self, text: str):
        """
        Normalized text should not contain separators (-, space, ., _).
        """
        result = normalize_text(text)
        separators = set("- ._/\\")
        for char in result:
            assert char not in separators, f"Separator '{char}' found in '{result}'"


class TestTransliterationProperties:
    """Property-based tests for transliterate_cyrillic"""
    
    @given(text=st.text(min_size=0, max_size=50))
    @settings(max_examples=100)
    def test_result_is_ascii_compatible(self, text: str):
        """
        **Property 6: Filename Transliteration Consistency**
        
        Transliterated text should contain only ASCII-compatible characters
        (no Cyrillic letters remain).
        
        **Validates: Requirements 3.5**
        """
        result = transliterate_cyrillic(text)
        cyrillic_chars = set("АБВГДЕЖЗИЙКЛМНОПРСТУФХЦЧШЩЪЫЬЭЮЯабвгдежзийклмнопрстуфхцчшщъыьэюя")
        for char in result:
            assert char not in cyrillic_chars, f"Cyrillic '{char}' found in '{result}'"
