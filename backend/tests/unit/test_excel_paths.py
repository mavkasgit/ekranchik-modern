"""Пути к сетевой книге: хвост пути после шары или диска и рамка из кавычек.

Оператор видит книгу как ``\\\\ktm-disk\\Оператор\\…`` или ``Z:\\…``, а сервер —
как каталог смонтированной шары. Функция ``share_tail`` отделяет хвост,
который в этом каталоге сохраняется.
"""
import pytest

from app.services.excel_service import normalize_path_input, share_tail


@pytest.mark.parametrize(
    "path_text, expected",
    [
        ("/app/excel/Учет КПЗ 2026.xlsm", "/app/excel/Учет КПЗ 2026.xlsm"),
        ('"/app/excel/Учет КПЗ 2026.xlsm"', "/app/excel/Учет КПЗ 2026.xlsm"),
        ("'/app/excel/Учет КПЗ 2026.xlsm'", "/app/excel/Учет КПЗ 2026.xlsm"),
        ('"/app/excel/Учет КПЗ 2026.xlsm" ', "/app/excel/Учет КПЗ 2026.xlsm"),
        ('  " /app/excel/Учет КПЗ 2026.xlsm "  ', "/app/excel/Учет КПЗ 2026.xlsm"),
        ('«/app/excel/Учет КПЗ 2026.xlsm»', "/app/excel/Учет КПЗ 2026.xlsm"),
        ('“/app/excel/Учет КПЗ 2026.xlsm”', "/app/excel/Учет КПЗ 2026.xlsm"),
        ('""/app/excel/Учет КПЗ 2026.xlsm""', "/app/excel/Учет КПЗ 2026.xlsm"),
        ("\\\\ktm-disk\\Оператор\\Учет КПЗ 2026.xlsm", "\\\\ktm-disk\\Оператор\\Учет КПЗ 2026.xlsm"),
        ('"\\\\ktm-disk\\Оператор\\Учет КПЗ 2026.xlsm"', "\\\\ktm-disk\\Оператор\\Учет КПЗ 2026.xlsm"),
        ("Учет КПЗ 2026.xlsm", "Учет КПЗ 2026.xlsm"),
        ("", ""),
    ],
)
def test_quotes_and_spaces_are_stripped(path_text, expected):
    assert normalize_path_input(path_text) == expected


@pytest.mark.parametrize(
    "path_text, expected",
    [
        ("\\\\ktm-disk\\Оператор\\Учет КПЗ 2026.xlsm", ["Учет КПЗ 2026.xlsm"]),
        ("\\\\172.17.11.7\\Оператор\\excel\\Учет КПЗ 2026.xlsm", ["excel", "Учет КПЗ 2026.xlsm"]),
        ("//ktm-disk/Оператор/Учет КПЗ 2026.xlsm", ["Учет КПЗ 2026.xlsm"]),
        ("Z:\\Учет КПЗ 2026.xlsm", ["Учет КПЗ 2026.xlsm"]),
        ("z:/Учет КПЗ 2026.xlsm", ["Учет КПЗ 2026.xlsm"]),
        ("  \\\\ktm-disk\\Оператор\\книга.xlsm  ", ["книга.xlsm"]),
    ],
)
def test_share_path_tail(path_text, expected):
    assert share_tail(path_text) == expected


@pytest.mark.parametrize(
    "path_text",
    [
        "\\\\ktm-disk\\Оператор",  # только шара, без файла
        "\\\\ktm-disk\\Оператор\\",
        "Z:\\",
        "Z:",
        "/app/excel/Учет КПЗ 2026.xlsm",  # путь сервера
        "Учет КПЗ 2026.xlsm",  # имя без пути
        "testdata/Учет КПЗ 2026.xlsm",
    ],
)
def test_not_a_share_path(path_text):
    assert share_tail(path_text) is None
