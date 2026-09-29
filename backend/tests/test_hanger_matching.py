"""Тесты привязки строки книги к физическому проходу подвеса (matching).

Контракт под тестом (app.services.matching):
- проход определяется cycle_id, а не номером подвеса: номера повторяются
  от смены к смены;
- строка подбирается по близости к first_seen_at, а не ко времени выхода;
- строка книги не достаётся двум проходам;
- проход без открытого цикла в line_monitor даёт CYCLE_ERROR и не получает
  строку (в том числе никакой строки с total_time = 0 «задним числом»);
- отсутствие строк по номеру даёт NO_ROW;
- строка позже выхода прохода помечается SUSPECT, но показывается.
"""
from datetime import datetime, timedelta

from app.services.hanger_row import HangerRow
from app.services.matching import (
    CODE_CYCLE_ERROR,
    CODE_NO_ROW,
    CODE_OK,
    CODE_SUSPECT,
    MAX_ENTRY_DELTA_SECONDS,
    match_cycles_to_rows,
)

DAY_1 = "28.09.2026"
NIGHT = "29.09.2026"
DAY_2 = "30.09.2026"


def _row(number, date, time, profile):
    return HangerRow(
        number=str(number), date=date, time=time, profile=profile,
        client="РП", color="серебро", lamels_qty=86, kpz_number="151",
        material_type="Пороги", is_defect=False,
    )


def _cycle(hanger, first_seen, exit_at, cycle_id=1, type_="unload"):
    return {
        "type": type_,
        "reason": None,
        "cycle_id": cycle_id,
        "hanger": hanger,
        "first_seen_at": first_seen,
        "entry_bath": 3,
        "exit_at": exit_at,
        "total_time_sec": None,
        "baths_visited": None,
    }


def _iso(day, hhmm):
    return datetime.strptime(f"{day} {hhmm}", "%d.%m.%Y %H:%M:%S").isoformat()


def test_closest_row_to_line_entry_wins():
    """Берётся строка, ближайшая к моменту входа в линию, а не позднейшая."""
    rows = {
        "1": [
            _row(1, NIGHT, "20:00:00", "СМЕНА-1"),
            _row(1, NIGHT, "22:40:00", "СМЕНА-2"),
        ]
    }
    cycles = [_cycle(1, _iso(NIGHT, "20:01:00"), _iso(NIGHT, "22:50:00"), cycle_id=11)]

    [m] = match_cycles_to_rows(cycles, rows)

    assert m.row.profile == "СМЕНА-1"
    assert m.code == CODE_OK
    assert abs(m.entry_delta_sec) < MAX_ENTRY_DELTA_SECONDS


def test_repeated_number_cycles_take_their_own_rows():
    """Два прохода одного номера забирают две разные строки — по порядку.

    Реальная ночная смена: №1 первой смены вышел в 22:50, когда строка №1
    второй смены (22:40) уже была в книге. Номер подвеса идентификатором
    прохода не является.
    """
    rows = {
        "1": [
            _row(1, NIGHT, "20:00:00", "ПРОГОН-1"),
            _row(1, NIGHT, "22:40:00", "ПРОГОН-2"),
        ]
    }
    cycles = [
        _cycle(1, _iso(NIGHT, "20:00:00"), _iso(NIGHT, "22:50:00"), cycle_id=1),
        _cycle(1, _iso(NIGHT, "22:40:00"), _iso(DAY_2, "01:00:00"), cycle_id=2),
    ]

    matches = match_cycles_to_rows(cycles, rows)

    by_cycle = {m.cycle["cycle_id"]: m for m in matches}
    assert by_cycle[1].row.profile == "ПРОГОН-1"
    assert by_cycle[2].row.profile == "ПРОГОН-2"
    assert all(m.code == CODE_OK for m in matches)


def test_cycle_without_open_cycle_yields_no_row():
    """Ошибка line_monitor: строки не подбираем вовсе, cycle_id не создаём."""
    rows = {"4": [_row(4, NIGHT, "20:00:00", "ЧУЖАЯ")]}
    broken = _cycle(4, None, _iso(NIGHT, "22:50:00"), cycle_id=None, type_="cycle_error")
    broken["reason"] = "unload_without_open_cycle"

    [m] = match_cycles_to_rows([broken], rows)

    assert m.code == CODE_CYCLE_ERROR
    assert m.row is None


def test_no_rows_for_hanger_yields_no_row_code():
    """Подвес сошёл, а по его номеру в книге нет ни одной строки."""
    cycles = [_cycle(2, _iso(NIGHT, "20:29:00"), _iso(NIGHT, "22:40:00"), cycle_id=5)]

    [m] = match_cycles_to_rows(cycles, {})

    assert m.code == CODE_NO_ROW
    assert m.row is None


def test_row_after_exit_is_suspect_but_shown():
    """Единственная строка номера позже выхода: показываем, но помечаем."""
    rows = {"6": [_row(6, NIGHT, "21:55:00", "СЛЕДУЮЩИЙ-ПРОГОН")]}
    cycles = [_cycle(6, _iso(NIGHT, "18:47:00"), _iso(NIGHT, "20:51:00"), cycle_id=7)]

    [m] = match_cycles_to_rows(cycles, rows)

    assert m.row is not None
    assert m.code == CODE_SUSPECT
    assert m.suspect_reason == "later_run"


def test_far_from_line_entry_is_suspect():
    """Расхождение больше допуска — причина неизвестна, решает оператор."""
    rows = {"7": [_row(7, NIGHT, "23:10:00", "ДАЛЕКО")]}
    cycles = [_cycle(7, _iso(NIGHT, "22:00:00"), _iso(DAY_2, "01:00:00"), cycle_id=8)]
    [m] = match_cycles_to_rows(cycles, rows)

    assert m.code == CODE_SUSPECT
    assert m.suspect_reason == "entry_delta"


def test_row_without_time_is_not_a_candidate():
    """Черновик (пустая ячейка «Время») проходом не подбирается."""
    rows = {"9": [_row(9, NIGHT, "—", "ЧЕРНОВИК")]}
    cycles = [_cycle(9, _iso(NIGHT, "20:00:00"), _iso(NIGHT, "22:00:00"), cycle_id=9)]

    [m] = match_cycles_to_rows(cycles, rows)

    assert m.code == CODE_NO_ROW
    assert m.row is None


def test_same_row_never_served_to_two_cycles():
    """Один проход на строку: если строк меньше, чем проходов, второй без строки."""
    rows = {"3": [_row(3, NIGHT, "20:00:00", "ЕДИНСТВЕННАЯ")]}
    cycles = [
        _cycle(3, _iso(NIGHT, "20:00:00"), _iso(NIGHT, "22:00:00"), cycle_id=1),
        _cycle(3, _iso(NIGHT, "22:30:00"), _iso(DAY_2, "00:30:00"), cycle_id=2),
    ]

    first, second = match_cycles_to_rows(cycles, rows)

    assert first.row is not None
    assert second.row is None
    assert second.code == CODE_NO_ROW
