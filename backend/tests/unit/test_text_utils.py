"""
Unit tests for text normalization utilities
"""
import pytest
from app.core.text_utils import (
    normalize_text,
    transliterate_cyrillic,
    safe_filename,
    extract_digits,
)


class TestNormalizeText:
    """Tests for normalize_text function"""
    
    def test_empty_input(self):
        """Empty string returns empty string"""
        assert normalize_text("") == ""
        assert normalize_text(None) == ""
    
    def test_cyrillic_lowercase(self):
        """Cyrillic text normalizes to lowercase"""
        assert normalize_text("АБВ") == "абв"
        assert normalize_text("абв") == "абв"
    
    def test_latin_to_cyrillic(self):
        """Latin characters map to Cyrillic equivalents"""
        # C (Latin) → с (Cyrillic)
        assert normalize_text("C") == "с"
        assert normalize_text("c") == "с"
        # A (Latin) → а (Cyrillic)
        assert normalize_text("A") == "а"
    
    def test_removes_separators(self):
        """Dashes, spaces, dots are removed"""
        assert normalize_text("ALS-345") == "алс345"
        assert normalize_text("als 345") == "алс345"
        assert normalize_text("als.345") == "алс345"
        assert normalize_text("als_345") == "алс345"
    
    def test_mixed_latin_cyrillic(self):
        """Mixed Latin/Cyrillic normalizes correctly"""
        # ЮП with Latin P
        assert normalize_text("ЮP-1625") == "юр1625"
        # СП with Latin C and P
        assert normalize_text("CP-100") == "ср100"
    
    def test_profile_names(self):
        """Real profile names normalize correctly"""
        assert normalize_text("ЮП-1625") == "юп1625"
        assert normalize_text("юп-3233") == "юп3233"
        assert normalize_text("ALS-345") == "алс345"


class TestTransliterateCyrillic:
    """Tests for transliterate_cyrillic function"""
    
    def test_empty_input(self):
        """Empty string returns empty string"""
        assert transliterate_cyrillic("") == ""
        assert transliterate_cyrillic(None) == ""
    
    def test_basic_transliteration(self):
        """Basic Cyrillic letters transliterate correctly"""
        assert transliterate_cyrillic("а") == "a"
        assert transliterate_cyrillic("б") == "b"
        assert transliterate_cyrillic("в") == "v"
    
    def test_complex_letters(self):
        """Complex Cyrillic letters (ж, ш, щ, etc.) transliterate correctly"""
        assert transliterate_cyrillic("ж") == "zh"
        assert transliterate_cyrillic("ш") == "sh"
        assert transliterate_cyrillic("щ") == "sch"
        assert transliterate_cyrillic("ю") == "yu"
        assert transliterate_cyrillic("я") == "ya"
    
    def test_uppercase_preserved(self):
        """Uppercase letters transliterate to uppercase"""
        assert transliterate_cyrillic("А") == "A"
        assert transliterate_cyrillic("Ю") == "Yu"
    
    def test_profile_names(self):
        """Real profile names transliterate correctly"""
        assert transliterate_cyrillic("ЮП-1625") == "YuP-1625"
        assert transliterate_cyrillic("Корпус") == "Korpus"
    
    def test_preserves_non_cyrillic(self):
        """Non-Cyrillic characters are preserved"""
        assert transliterate_cyrillic("ALS-345") == "ALS-345"
        assert transliterate_cyrillic("123") == "123"


class TestSafeFilename:
    """Tests for safe_filename function"""
    
    def test_empty_input(self):
        """Empty string returns empty string"""
        assert safe_filename("") == ""
        assert safe_filename(None) == ""
    
    def test_removes_unsafe_chars(self):
        """Unsafe characters are removed or replaced"""
        assert safe_filename("file/name") == "file-name"
        assert safe_filename("file name") == "file-name"
    
    def test_preserves_safe_chars(self):
        """Safe characters are preserved"""
        assert safe_filename("file-name_123.jpg") == "file-name_123.jpg"
    
    def test_cyrillic_transliterated(self):
        """Cyrillic is transliterated"""
        assert safe_filename("ЮП-1625") == "YuP-1625"


class TestExtractDigits:
    """Tests for extract_digits function"""
    
    def test_empty_input(self):
        """Empty string returns empty string"""
        assert extract_digits("") == ""
        assert extract_digits(None) == ""
    
    def test_extracts_digits(self):
        """Digits are extracted correctly"""
        assert extract_digits("ALS-345") == "345"
        assert extract_digits("ЮП-1625") == "1625"
        assert extract_digits("abc123def456") == "123456"
    
    def test_no_digits(self):
        """String without digits returns empty"""
        assert extract_digits("abc") == ""
