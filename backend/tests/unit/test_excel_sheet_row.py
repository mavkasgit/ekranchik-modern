"""Номер строки листа книги учёта: по нему оператор находит подвес.

Оператор сверяет проход с записью в книге и должен встать на нужную строку
прямо в листе «Подвесы». Поэтому ``HangerRow`` несёт номер строки ЛИСТА, а
не индексу датафрейма: между ними три строки инструкций и заголовков, и
забыть про это — значит показать оператору соседнюю строку с чужим
подвесом.
"""
import pandas as pd
import pytest

from app.services.excel_service import DATA_ROWS_SKIPPED, ExcelService


def _frame(rows: list[dict]) -> pd.DataFrame:
    return pd.DataFrame(rows)


def _service(monkeypatch, df: pd.DataFrame) -> ExcelService:
    service = ExcelService()
    service._cache = df
    monkeypatch.setattr(service, "_is_cache_valid", lambda path: True)
    return service


def test_sheet_row_points_at_the_same_line_in_the_book(monkeypatch):
    """Номер строки листа совпадает с той же строкой при перечитывании листа.

    Читаем книгу, берём строку, затем читаем ЛИСТ ЦЕЛИКОМ и ищем то же
    время загрузки: индекс найденной строки и есть ожидаемый номер.
    """
    df = _frame([
        {"date": "2026-09-29", "number": 5, "time": "08:00", "profile": "ЮП-1001"},
        {"date": "2026-09-29", "number": 6, "time": "09:30", "profile": "рейка"},
        {"date": "2026-09-29", "number": 7, "time": "11:15", "profile": "Урны"},
    ])
    rows = _service(monkeypatch, df).get_products(limit=10)

    # Лист целиком: те же строки, но индексы с нуля и без пропуска шапки.
    whole_sheet = pd.DataFrame([
        ["инструкция"],
        ["инструкция"],
        ["заголовки"],
        ["2026-09-29", 5, "08:00", "ЮП-1001"],
        ["2026-09-29", 6, "09:30", "рейка"],
        ["2026-09-29", 7, "11:15", "Урны"],
    ])
    found = whole_sheet.index[whole_sheet[2] == "11:15"][0]
    expected = found + 1  # нумерация листа с единицы

    last = [r for r in rows if r.time == "11:15"][0]
    assert last.sheet_row == expected == 6, "третья строка данных идёт шестой"


def test_sheet_row_is_not_off_by_one_on_the_neighbour(monkeypatch):
    """Соседняя строка — уже чужой подвес, поэтому смещение на единицу нельзя.

    Ошибка на единицу не бросается в глаза: книга большая, и рядом всегда
    есть другая строка. Ловим её сравнением с СОСЕДНИМИ строками листа.
    """
    df = _frame([
        {"date": "2026-09-29", "number": 5, "time": "08:00", "profile": "ЮП-1001"},
        {"date": "2026-09-29", "number": 6, "time": "09:30", "profile": "рейка"},
    ])
    rows = _service(monkeypatch, df).get_products(limit=10)
    by_time = {r.time: r for r in rows}

    assert by_time["08:00"].sheet_row == 4, "первая строка данных идёт под номером 4"
    assert by_time["09:30"].sheet_row == 5, "следующая — на единицу больше"
    assert by_time["09:30"].sheet_row != by_time["08:00"].sheet_row


def test_row_number_is_the_number_written_in_the_row_not_the_sheet_row(monkeypatch):
    """«№ по порядку» из строки и номер строки ЛИСТА — разные числа."""
    df = _frame([
        {"date": "2026-09-29", "number": 57, "time": "19:33", "profile": "361"},
    ])
    row = _service(monkeypatch, df).get_products(limit=10)[0]

    assert row.number == 57, "это написано в самой строке"
    assert row.sheet_row == 4, "это адрес строки в листе"


def test_data_rows_skipped_matches_the_header_layout():
    """Константа пропуска совпадает с реальной шапкой листа.

    При layout «две инструкции + заголовки» первая строка данных — четвёртая.
    Сломается только вместе с правкой чтения, поэтому зафиксировано явно.
    """
    assert DATA_ROWS_SKIPPED == 3
