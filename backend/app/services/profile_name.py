"""Единый разбор ячейки «Профиль»: артикул, обработки и длина.

Одна таблица ключевых слов и одно место, где строка книги учёта становится
Профилями. Ячейка может содержать несколько Профилей через ``+`` или ``/``;
сегмент, состоящий только из слова-обработки («ЮП-460 гребенка+окно»),
присоединяет свои обработки к соседнему Профилю и отдельной записью не
становится.

Длина — отдельный признак строки книги (``2,75 метра``, ``(1.8)``, ``3м``),
а не часть артикула: она уходит из имени в ``length_m``/``length_text``
(ADR 0012). Миллиметры и размеры листов остаются в имени.

Модуль используют оба пути дашборда (``get_dashboard`` и matched) и поиск фото
(``catalog_service.get_profiles_photos_batch``) — чтобы чистое имя Профиля было
одинаковым везде.
"""

import re
from dataclasses import dataclass, field
from typing import Any

# Ключевые слова обработок: (как записано в книге, каноническое обозначение).
# Порядок таблицы задаёт порядок в ``ParsedProfile.processing``.
PROCESSING_KEYWORDS: tuple[tuple[str, str], ...] = (
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

# Длина в скобках и длина с единицей «м». Скобка — первая: она точнее и
# отделяет длину от прочих чисел артикула. Дробная часть обязательна: «(381)» —
# это номер/партия, а не метры. Вторая форма не берёт «мм» (следующая буква
# делает единицу миллиметром) и не начинает число с середины другого числа или
# слова: в марках «А5М» и «АМг2М» буква перед цифрой — не начало длины.
_LENGTH_IN_PARENS = re.compile(
    r"\(\s*(\d+[.,]\d+)\s*(?:м(?:етр(?:а|ов)?)?\.?)?\s*\)", re.IGNORECASE
)
_LENGTH_WITH_UNIT = re.compile(
    r"(?<![а-яa-z\d.,])(\d+(?:[.,]\d+)?)\s*м(?:етр(?:а|ов)?)?\.?(?![а-яa-z])",
    re.IGNORECASE,
)
_EMPTY_PARENS = re.compile(r"\(\s*\)")


@dataclass(frozen=True)
class ParsedProfile:
    """Один Профиль из ячейки: как записан, артикул, обработки и длина."""

    raw: str
    name: str
    processing: list[str] = field(default_factory=list)
    length_m: float | None = None
    length_text: str | None = None


def _is_empty(value: Any) -> bool:
    return value is None or str(value).strip() in _EMPTY_TOKENS


def _length_text(value: float) -> str:
    """Показ длины: запятая, без лишних нулей, пробел перед «м» (``2,75 м``)."""
    text = f"{value:.2f}".rstrip("0").rstrip(".")
    return text.replace(".", ",") + " м"


def _take_length(name: str) -> tuple[str, float | None]:
    """Вырезать длину из имени: остаток — артикул, число — метры."""
    for pattern in (_LENGTH_IN_PARENS, _LENGTH_WITH_UNIT):
        match = pattern.search(name)
        if match:
            value = float(match.group(1).replace(",", "."))
            return f"{name[: match.start()]} {name[match.end() :]}", value
    return name, None


def parse_profile(text: Any) -> ParsedProfile:
    """Разобрать один сегмент ячейки: убрать обработки и длину, вернуть артикул."""
    raw = "" if _is_empty(text) else str(text).strip()
    name = raw
    processing: list[str] = []

    for keyword, canonical in PROCESSING_KEYWORDS:
        pattern = r"\b" + re.escape(keyword) + r"\b"
        if re.search(pattern, name, re.IGNORECASE):
            processing.append(canonical)
            name = re.sub(pattern, "", name, flags=re.IGNORECASE)

    name, length_m = _take_length(name)

    # Пустые скобки остаются от обработки (``314(Гребенка)``) или от длины без
    # десятичной части в скобках (``(3м)``); в артикуле им делать нечего.
    name = _EMPTY_PARENS.sub(" ", name)
    name = re.sub(r"\s+", " ", name).strip()
    name = name.rstrip("+,;").strip()

    return ParsedProfile(
        raw=raw,
        name=name,
        processing=processing,
        length_m=length_m,
        length_text=_length_text(length_m) if length_m is not None else None,
    )


def split_profiles(text: Any) -> list[ParsedProfile]:
    """Ячейка → Профили. Обработки без имени присоединяются к соседу."""
    if _is_empty(text):
        return []

    segments = [part.strip() for part in _SEPARATORS.split(str(text)) if part.strip()]

    profiles: list[ParsedProfile] = []
    leading: list[str] = []  # обработки до первого Профиля
    for segment in segments:
        parsed = parse_profile(segment)
        if parsed.name:
            profiles.append(
                ParsedProfile(
                    raw=parsed.raw,
                    name=parsed.name,
                    processing=[*leading, *parsed.processing],
                    length_m=parsed.length_m,
                    length_text=parsed.length_text,
                )
            )
            leading = []
        elif profiles:
            profiles[-1].processing.extend(parsed.processing)
        else:
            leading.extend(parsed.processing)

    return profiles
