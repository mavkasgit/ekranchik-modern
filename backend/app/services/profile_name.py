"""Единый разбор ячейки «Профиль»: чистое имя и список обработок.

Одна таблица ключевых слов и одно место, где строка книги учёта становится
Профилями. Ячейка может содержать несколько Профилей через ``+`` или ``/``;
сегмент, состоящий только из слова-обработки («ЮП-460 гребенка+окно»),
присоединяет свои обработки к соседнему Профилю и отдельной записью не
становится.

Модуль используют оба пути дашборда (``get_dashboard`` и matched) и поиск фото
(``catalog_service.get_profiles_photos_batch``) — чтобы чистое имя Профиля было
одинаковым везде.
"""
import re
from dataclasses import dataclass, field
from typing import Any, List, Tuple

# Ключевые слова обработок: (как записано в книге, каноническое обозначение).
# Порядок таблицы задаёт порядок в ``ParsedProfile.processing``.
PROCESSING_KEYWORDS: Tuple[Tuple[str, str], ...] = (
    ("окно", "окно"),
    ("греб", "греб"),
    ("гребенка", "греб"),  # запись оператора для «греб»
    ("сверло", "сверло"),
    ("фреза", "фреза"),
    ("паз", "паз"),
    ("отв", "отв"),
)

# Пустая ячейка: сентинел продюсера и то, чем pandas отдаёт пустые значения.
_EMPTY_TOKENS = frozenset({"", "—", "nan", "NaT", "None"})

_SEPARATORS = re.compile(r"[+/]")


@dataclass(frozen=True)
class ParsedProfile:
    """Один Профиль из ячейки: как записан, чистое имя, список обработок."""

    raw: str
    name: str
    processing: List[str] = field(default_factory=list)


def _is_empty(value: Any) -> bool:
    return value is None or str(value).strip() in _EMPTY_TOKENS


def parse_profile(text: Any) -> ParsedProfile:
    """Разобрать один сегмент ячейки: убрать обработки, вернуть чистое имя."""
    raw = "" if _is_empty(text) else str(text).strip()
    name = raw
    processing: List[str] = []

    for keyword, canonical in PROCESSING_KEYWORDS:
        pattern = r"\b" + re.escape(keyword) + r"\b"
        if re.search(pattern, name, re.IGNORECASE):
            processing.append(canonical)
            name = re.sub(pattern, "", name, flags=re.IGNORECASE)

    name = re.sub(r"\s+", " ", name).strip()
    name = name.rstrip("+,;").strip()

    return ParsedProfile(raw=raw, name=name, processing=processing)


def split_profiles(text: Any) -> List[ParsedProfile]:
    """Ячейка → Профили. Обработки без имени присоединяются к соседу."""
    if _is_empty(text):
        return []

    segments = [part.strip() for part in _SEPARATORS.split(str(text)) if part.strip()]

    profiles: List[ParsedProfile] = []
    leading: List[str] = []  # обработки до первого Профиля
    for segment in segments:
        parsed = parse_profile(segment)
        if parsed.name:
            profiles.append(
                ParsedProfile(
                    raw=parsed.raw,
                    name=parsed.name,
                    processing=[*leading, *parsed.processing],
                )
            )
            leading = []
        elif profiles:
            profiles[-1].processing.extend(parsed.processing)
        else:
            leading.extend(parsed.processing)

    return profiles
