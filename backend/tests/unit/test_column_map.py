"""
Unit tests for column_map: header-name resolution with legacy fallback.

Covers the three resolution modes the parser can hit:
- full name-mode (all 10 fields found by header name, e.g. real file with «Фамилия»)
- hybrid (only some headers present, rest fall back to legacy positions)
- full legacy-mode (no headers matched at all -> pure positional)
"""
import pandas as pd
import pytest

from app.services.column_map import (
    COLUMN_FIELDS,
    FIELDS,
    LEGACY_POSITIONS,
    normalize_header,
    find_column,
    resolve_columns,
)

# Real file layout (after «Фамилия» inserted at H): headers on row index 2.
REAL_HEADERS = pd.Series({
    0: '№ по порядку',
    1: 'Дата и время',
    2: 'Комментарий',
    3: 'Дата',
    4: '№ по порядку',
    5: 'Время',
    6: 'Смена',
    7: 'Фамилия',
    8: 'Вид материалов',
    9: 'Годность подвеса',
    10: 'Ответственный менеджер',
    11: 'НОМЕР КПЗ \n',
    12: 'Заказчик',
    13: 'Профиль',
    14: 'Тип завески',
    15: 'Вид обработки',
    16: 'Толщина мкм',
    17: 'Цвет',
    18: 'Подвесы, шт',
    19: 'УСЛОВНЫЕ ПОДВЕСЫ, шт',
    20: 'Ламели, шт',
})

# Legacy fixture layout (no Фамилия) — headers only for date/number/time at
# 0-based positions 3,4,5 (columns D/E/F), as the integration-test fixture writes.
LEGACY_HEADERS = pd.Series({
    0: None, 1: None, 2: None,
    3: 'Дата',
    4: 'Номер',
    5: 'Время',
    6: None,
})


def test_normalize_header():
    assert normalize_header('  НОМЕР КПЗ \n') == 'номер кпз'
    assert normalize_header('\tВид материалов ') == 'вид материалов'
    assert normalize_header('Ламели, шт') == 'ламели, шт'  # interior space kept
    assert normalize_header(None) == ''
    assert normalize_header(123) == '123'


def test_find_column_returns_last_match():
    # «№ по порядку» appears in both A(0) and E(4) — real data column is E.
    assert find_column(REAL_HEADERS, '№ по порядку') == 4
    assert find_column(REAL_HEADERS, 'Номер') == -1  # alias not in real file
    assert find_column(LEGACY_HEADERS, 'Номер') == 4  # alias matches in fixture


def test_find_column_missing():
    assert find_column(REAL_HEADERS, 'Несуществующая колонка') == -1
    assert find_column(REAL_HEADERS, '') == -1


def test_resolve_real_file_layout_full_name_mode():
    """Real file with «Фамилия»: every field found by name on shifted positions."""
    res = resolve_columns(REAL_HEADERS)
    assert res.found_by_name == set(FIELDS)
    assert res.missing == set()
    assert res.positions == {
        'date': 3, 'number': 4, 'time': 5,
        'material_type': 8, 'defect': 9,
        'kpz_number': 11, 'client': 12, 'profile': 13,
        'color': 17, 'lamels_qty': 20,
    }


def test_resolve_hybrid_fallback():
    """Legacy fixture without Фамилия: only date/number/time found by name."""
    res = resolve_columns(LEGACY_HEADERS)
    assert res.found_by_name == {'date', 'number', 'time'}
    assert res.missing == set(FIELDS) - {'date', 'number', 'time'}
    assert res.positions == LEGACY_POSITIONS


def test_resolve_full_legacy_fallback():
    """No headers at all -> pure positional mapping, nothing found by name."""
    res = resolve_columns(pd.Series({0: '', 1: None, 2: ''}))
    assert res.found_by_name == set()
    assert res.positions == LEGACY_POSITIONS


def test_legacy_positions_derived_from_column_fields():
    """FIELDS / LEGACY_POSITIONS must not drift from the single source of truth."""
    assert FIELDS == tuple(f.field for f in COLUMN_FIELDS)
    assert LEGACY_POSITIONS == {
        f.field: f.legacy_position for f in COLUMN_FIELDS
    }