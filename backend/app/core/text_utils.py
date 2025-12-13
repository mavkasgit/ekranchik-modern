"""
Text normalization utilities for Latin/Cyrillic character mapping.

Provides functions for:
- Normalizing text for search (Latin ↔ Cyrillic equivalence)
- Transliterating Cyrillic to Latin for safe filenames
"""

# Mapping of similar characters to unified lowercase Cyrillic form
# Latin and Cyrillic versions normalize to the same Cyrillic character
CYRILLIC_LATIN_MAP = {
    # Cyrillic UPPERCASE → lowercase (ALL Cyrillic letters)
    'А': 'а', 'Б': 'б', 'В': 'в', 'Г': 'г', 'Д': 'д', 'Е': 'е',
    'Ё': 'ё', 'Ж': 'ж', 'З': 'з', 'И': 'и', 'Й': 'й', 'К': 'к',
    'Л': 'л', 'М': 'м', 'Н': 'н', 'О': 'о', 'П': 'п', 'Р': 'р',
    'С': 'с', 'Т': 'т', 'У': 'у', 'Ф': 'ф', 'Х': 'х', 'Ц': 'ц',
    'Ч': 'ч', 'Ш': 'ш', 'Щ': 'щ', 'Ъ': 'ъ', 'Ы': 'ы', 'Ь': 'ь',
    'Э': 'э', 'Ю': 'ю', 'Я': 'я',
    # Latin UPPERCASE → lowercase Cyrillic (visually similar or common substitutes)
    'A': 'а', 'B': 'в', 'C': 'с', 'E': 'е', 'H': 'н', 'K': 'к',
    'L': 'л', 'M': 'м', 'O': 'о', 'P': 'р', 'S': 'с', 'T': 'т',
    'X': 'х', 'Y': 'у',
    # Latin lowercase → lowercase Cyrillic (visually similar or common substitutes)
    'a': 'а', 'c': 'с', 'e': 'е', 'l': 'л', 'o': 'о', 'p': 'р',
    's': 'с', 'x': 'х', 'y': 'у',
}

# Transliteration table: Cyrillic → Latin
TRANSLITERATION_MAP = {
    'а': 'a', 'б': 'b', 'в': 'v', 'г': 'g', 'д': 'd',
    'е': 'e', 'ё': 'yo', 'ж': 'zh', 'з': 'z', 'и': 'i',
    'й': 'y', 'к': 'k', 'л': 'l', 'м': 'm', 'н': 'n',
    'о': 'o', 'п': 'p', 'р': 'r', 'с': 's', 'т': 't',
    'у': 'u', 'ф': 'f', 'х': 'h', 'ц': 'ts', 'ч': 'ch',
    'ш': 'sh', 'щ': 'sch', 'ъ': '', 'ы': 'y', 'ь': '',
    'э': 'e', 'ю': 'yu', 'я': 'ya',
    # Uppercase
    'А': 'A', 'Б': 'B', 'В': 'V', 'Г': 'G', 'Д': 'D',
    'Е': 'E', 'Ё': 'Yo', 'Ж': 'Zh', 'З': 'Z', 'И': 'I',
    'Й': 'Y', 'К': 'K', 'Л': 'L', 'М': 'M', 'Н': 'N',
    'О': 'O', 'П': 'P', 'Р': 'R', 'С': 'S', 'Т': 'T',
    'У': 'U', 'Ф': 'F', 'Х': 'H', 'Ц': 'Ts', 'Ч': 'Ch',
    'Ш': 'Sh', 'Щ': 'Sch', 'Ъ': '', 'Ы': 'Y', 'Ь': '',
    'Э': 'E', 'Ю': 'Yu', 'Я': 'Ya',
}


def normalize_text(text: str | None) -> str:
    """
    Normalize text for search by converting to unified lowercase Cyrillic form.
    
    - Converts Latin characters to their Cyrillic equivalents
    - Removes dashes, spaces, dots, underscores for flexible matching
    - Converts to lowercase
    
    Examples:
        'С' (Cyrillic) → 'с'
        'C' (Latin) → 'с'
        'ALS-345' → 'алс345'
        'als 345' → 'алс345'
        'ЮП-1625' → 'юп1625'
    
    Args:
        text: Input text (may contain Cyrillic or Latin)
    
    Returns:
        Normalized text (lowercase Cyrillic without special characters)
    """
    if not text:
        return ''
    
    text = str(text)
    result = []
    
    for char in text:
        # Skip separators for flexible matching
        if char in ('-', ' ', '.', '_', '/', '\\'):
            continue
        # Map through table (Latin→Cyrillic, Cyrillic→lowercase)
        mapped = CYRILLIC_LATIN_MAP.get(char, char.lower())
        result.append(mapped)
    
    return ''.join(result)


def transliterate_cyrillic(text: str | None) -> str:
    """
    Transliterate Cyrillic text to Latin for safe filenames.
    
    Examples:
        'ЮП-1625' → 'YuP-1625'
        'АЛС-345' → 'ALS-345'
        'Корпус' → 'Korpus'
    
    Args:
        text: Input text with Cyrillic characters
    
    Returns:
        Text with Cyrillic replaced by Latin equivalents
    """
    if not text:
        return ''
    
    text = str(text)
    result = []
    
    for char in text:
        result.append(TRANSLITERATION_MAP.get(char, char))
    
    return ''.join(result)


def safe_filename(text: str | None) -> str:
    """
    Convert text to a safe filename by transliterating and removing unsafe chars.
    
    Args:
        text: Input text
    
    Returns:
        Safe filename string
    """
    if not text:
        return ''
    
    # First transliterate
    transliterated = transliterate_cyrillic(text)
    
    # Remove or replace unsafe characters
    safe_chars = []
    for char in transliterated:
        if char.isalnum() or char in ('-', '_', '.'):
            safe_chars.append(char)
        elif char in (' ', '/'):
            safe_chars.append('-')
    
    return ''.join(safe_chars)


def extract_digits(text: str | None) -> str:
    """
    Extract all digits from text.
    
    Args:
        text: Input text
    
    Returns:
        String containing only digits
    """
    if not text:
        return ''
    return ''.join(c for c in str(text) if c.isdigit())
