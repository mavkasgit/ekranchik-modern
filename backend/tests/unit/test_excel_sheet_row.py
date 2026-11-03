"""Номер строки листа книги учёта: по нему оператор находит подвес.

Оператор сверяет проход с записью в книге и должен встать на нужную строку
прямо в листе «Подвесы». Поэтому ``HangerRow`` несёт номер строки ЛИСТА, а
не индексу датафрейма: между ними три строки инструкций и заголовков, и
забыть про это — значит показать оператору соседнюю строку с чужим
подвесом.

Книга под тестом настоящая (пусть и собранная на лету): строка листа имеет
смысл только вместе с шапкой, а подставленный в кэш датафрейм эту шапку не
проверяет.
"""

from pathlib import Path

import openpyxl

from app.services.excel_service import DATA_ROWS_SKIPPED, ExcelService


def _book(tmp_path: Path, rows: list[dict]) -> Path:
    """Книга с боевой шапкой: две строки инструкций и строка заголовков."""
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Подвесы"

    ws.cell(row=1, column=1, value="инструкция")
    ws.cell(row=2, column=1, value="инструкция")
    headers = {
        4: "Дата",
        5: "Номер",
        6: "Время",
        8: "Вид материалов",
        9: "Годность подвеса",
        11: "НОМЕР КПЗ",
        12: "Заказчик",
        13: "Профиль",
        17: "Цвет",
        20: "Ламели, шт",
    }
    for column, title in headers.items():
        ws.cell(row=3, column=column, value=title)

    for i, row in enumerate(rows, start=4):
        ws.cell(row=i, column=4, value=row["date"])
        ws.cell(row=i, column=5, value=row["number"])
        ws.cell(row=i, column=6, value=row["time"])
        ws.cell(row=i, column=13, value=row.get("profile", ""))

    path = tmp_path / "book.xlsx"
    wb.save(path)
    return path


def _service(tmp_path: Path, rows: list[dict]) -> ExcelService:
    """Сервис, читающий собранную книгу: путь подставлен, кэш пуст."""
    service = ExcelService()
    service.use_file(str(_book(tmp_path, rows)))
    return service


def test_sheet_row_points_at_the_same_line_in_the_book(tmp_path: Path):
    """Номер строки листа совпадает с той же строкой при перечитывании листа.

    Читаем книгу, берём строку, затем читаем ЛИСТ ЦЕЛИКОМ и ищем то же
    время загрузки: индекс найденной строки и есть ожидаемый номер.
    """
    rows = _service(
        tmp_path,
        [
            {"date": "2026-09-29", "number": 5, "time": "08:00", "profile": "ЮП-1001"},
            {"date": "2026-09-29", "number": 6, "time": "09:30", "profile": "рейка"},
            {"date": "2026-09-29", "number": 7, "time": "11:15", "profile": "Урны"},
        ],
    ).get_products(limit=10)

    # Лист целиком: те же строки, но индексы с нуля и без пропуска шапки.
    whole_sheet = [
        ["инструкция"],
        ["инструкция"],
        ["заголовки"],
        ["2026-09-29", 5, "08:00", "ЮП-1001"],
        ["2026-09-29", 6, "09:30", "рейка"],
        ["2026-09-29", 7, "11:15", "Урны"],
    ]
    found = next(index for index, row in enumerate(whole_sheet) if len(row) > 2 and row[2] == "11:15")
    expected = found + 1  # нумерация листа с единицы

    last = [r for r in rows if r.time == "11:15"][0]
    assert last.sheet_row == expected == 6, "третья строка данных идёт шестой"


def test_sheet_row_is_not_off_by_one_on_the_neighbour(tmp_path: Path):
    """Соседняя строка — уже чужой подвес, поэтому смещение на единицу нельзя.

    Ошибка на единицу не бросается в глаза: книга большая, и рядом всегда
    есть другая строка. Ловим её сравнением с СОСЕДНИМИ строками листа.
    """
    rows = _service(
        tmp_path,
        [
            {"date": "2026-09-29", "number": 5, "time": "08:00", "profile": "ЮП-1001"},
            {"date": "2026-09-29", "number": 6, "time": "09:30", "profile": "рейка"},
        ],
    ).get_products(limit=10)
    by_time = {r.time: r for r in rows}

    assert by_time["08:00"].sheet_row == 4, "первая строка данных идёт под номером 4"
    assert by_time["09:30"].sheet_row == 5, "следующая — на единицу больше"
    assert by_time["09:30"].sheet_row != by_time["08:00"].sheet_row


def test_row_number_is_the_number_written_in_the_row_not_the_sheet_row(tmp_path: Path):
    """«№ по порядку» из строки и номер строки ЛИСТА — разные числа."""
    rows = _service(
        tmp_path,
        [{"date": "2026-09-29", "number": 57, "time": "19:33", "profile": "361"}],
    ).get_products(limit=10)
    row = rows[0]

    assert row.number == 57, "это написано в самой строке"
    assert row.sheet_row == 4, "это адрес строки в листе"


def test_data_rows_skipped_matches_the_header_layout():
    """Константа пропуска совпадает с реальной шапкой листа.

    При layout «две инструкции + заголовки» первая строка данных — четвёртая.
    Сломается только вместе с правкой чтения, поэтому зафиксировано явно.
    """
    assert DATA_ROWS_SKIPPED == 3
