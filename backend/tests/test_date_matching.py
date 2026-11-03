"""Календарная арифметика книги: переходы месяца, года и двузначный год.

Парсеры берутся из ``app.services.matching`` — те же, что читают строку в
рабочем коде. Собственные копии в тестах расходились с producer'ом: тест
сертифицировал одно поведение, а строка разбиралась другим.

Допуск ``MAX_ENTRY_DELTA_SECONDS`` проверяется там, где он применяется —
``tests/test_hanger_matching.py``.
"""

from app.services.matching import (
    excel_datetime_to_seconds,
    parse_excel_date,
    parse_excel_time,
)


def _seconds(date: str, time: str) -> float:
    return excel_datetime_to_seconds(parse_excel_date(date), parse_excel_time(time))


def test_month_transition():
    """Запись 30.03 и выход 01.04 — следующие сутки, а не «минус месяц»."""
    entry = _seconds("30.03.2026", "22:33:00")
    exit_ = _seconds("01.04.2026", "00:52:10")

    assert entry < exit_
    diff_hours = (exit_ - entry) / 3600
    assert 26.0 < diff_hours < 27.0


def test_year_transition():
    """31.12 → 01.01: разница считается через границу года."""
    entry = _seconds("31.12.2025", "23:00:00")
    exit_ = _seconds("01.01.2026", "01:30:00")

    assert entry < exit_
    diff_hours = (exit_ - entry) / 3600
    assert 2.4 < diff_hours < 2.6


def test_two_digit_year():
    """26 → 2026, 99 → 1999: окно книги переходит через 2000-й."""
    assert parse_excel_date("30.03.26") == (2026, 3, 30)
    assert parse_excel_date("31.12.99") == (1999, 12, 31)


def test_unparseable_cell_is_not_a_date():
    """Пустая и битая ячейка — нулевой отсчёт, а не сегодняшняя дата."""
    assert parse_excel_date("") == (0, 0, 0)
    assert parse_excel_date("—") == (0, 0, 0)
    assert parse_excel_time("") == (0, 0, 0)
    assert _seconds("", "") == 0.0
