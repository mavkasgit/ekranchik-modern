"""Строки книги: одно окно и один кэш на всех потребителей (issue #14).

Панель «Выход», карточки OPC UA и журнал читали книгу с разными лимитами
(1000 и 3000) и каждый держал свой кэш. Здесь проверяется, что окно одно,
разбор один и повторный запрос не перечитывает книгу.
"""

import pytest

from app.services import book_rows
from app.services.book_rows import BOOK_ROWS_LIMIT, get_book_rows, reset_book_rows_cache
from app.services.excel_service import ExcelService
from app.services.hanger_row import HangerRow


def _row(number: str, time: str, profile: str) -> HangerRow:
    return HangerRow(
        number=number,
        date="03.11.2026",
        time=time,
        client="РП",
        profile=profile,
        color="серебро",
        lamels_qty=86,
        kpz_number="151",
        material_type="Пороги",
        sheet_row=1,
        is_defect=False,
    )


@pytest.fixture(autouse=True)
def _clean_cache():
    reset_book_rows_cache()
    yield
    reset_book_rows_cache()


def test_book_rows_read_the_book_once_and_share_the_result(monkeypatch):
    """Второй потребитель получает тот же разбор, а не второй поход в Excel."""
    calls: list[dict] = []
    products = [_row("7", "10:00:00", "ПЕРВЫЙ"), _row("7", "18:00:00", "ВТОРОЙ")]
    state = {"version": ("book.xlsm", 1.0, 1)}

    monkeypatch.setattr(ExcelService, "data_version", property(lambda self: state["version"]))
    monkeypatch.setattr(
        book_rows.excel_service,
        "get_products",
        lambda **kwargs: calls.append(kwargs) or products,
    )

    first = get_book_rows()
    second = get_book_rows()

    assert first is second
    assert len(calls) == 1
    assert calls[0]["limit"] == BOOK_ROWS_LIMIT
    assert [row.profile for row in first.by_hanger["7"]] == ["ПЕРВЫЙ", "ВТОРОЙ"]
    assert first.latest_by_hanger["7"] == {"article": "ВТОРОЙ", "color": "серебро"}


def test_book_rows_rebuild_when_the_book_changes(monkeypatch):
    """Новая версия книги — новый разбор, старый кэш не отдаётся."""
    calls: list[dict] = []
    state = {"version": ("book.xlsm", 1.0, 1), "products": [_row("7", "10:00:00", "ПЕРВЫЙ")]}

    monkeypatch.setattr(ExcelService, "data_version", property(lambda self: state["version"]))
    monkeypatch.setattr(
        book_rows.excel_service,
        "get_products",
        lambda **kwargs: calls.append(kwargs) or state["products"],
    )

    assert get_book_rows().latest_by_hanger["7"]["article"] == "ПЕРВЫЙ"

    state["version"] = ("book.xlsm", 2.0, 2)
    state["products"] = [_row("7", "10:00:00", "НОВЫЙ")]

    assert get_book_rows().latest_by_hanger["7"]["article"] == "НОВЫЙ"
    assert len(calls) == 2
