"""Тесты привязки строки книги к физическому проходу подвеса (matching).

Контракт под тестом (app.services.matching):
- проход определяется cycle_id, а не номером подвеса: номера повторяются
  от смены к смены;
- строка подбирается по близости к first_seen_at, а не ко времени выхода;
- строка книги не достаётся двум проходам;
- проход без открытого цикла в line_monitor даёт CYCLE_ERROR и не получает
  строку (в том числе никакой строки с total_time = 0 «задним числом»);
- отсутствие строк по номеру даёт NO_ROW;
- строка позже выхода прохода кандидатом не становится: она описывает другой
  прогон, и сколько таких строк отброшено — видно в rows_after_exit;
- расхождение входа больше допуска — пометка в журнале (suspect_reason),
  а не на экране;
- первый замер недостоверен (монитор застал подвес уже стоящим) — строка
  подбирается, но entry_delta_sec не считается.
"""
from datetime import datetime, timedelta

from app.services.hanger_row import HangerRow
from app.services.matching import (
    CODE_CYCLE_ERROR,
    CODE_NO_ROW,
    CODE_OK,
    MAX_ENTRY_DELTA_SECONDS,
    TRUSTED_FIRST_SEEN,
    match_cycles_to_rows,
    match_log_line,
)

DAY_1 = "28.09.2026"
NIGHT = "29.09.2026"
DAY_2 = "30.09.2026"


def _row(number, date, time, profile):
    return HangerRow(
        number=str(number), date=date, time=time, profile=profile,
        client="РП", color="серебро", lamels_qty=86, kpz_number="151",
        material_type="Пороги", is_defect=False, sheet_row=1,
    )


def _cycle(hanger, first_seen, exit_at, cycle_id=1, type_="unload", source=TRUSTED_FIRST_SEEN):
    return {
        "type": type_,
        "reason": None,
        "cycle_id": cycle_id,
        "hanger": hanger,
        "first_seen_at": first_seen,
        "first_seen_source": source,
        "entry_bath": 3,
        "exit_at": exit_at,
        "total_time_sec": None,
        "baths_visited": None,
        "path": None,
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


def test_result_order_follows_caller_not_matching_order():
    """Ответ сохраняет порядок вызывающего, а не порядок подбора строк.

    Подбор обязан разбирать проходы от ранних к поздним, иначе ранний
    проход заберёт строку более позднего прогона. Но вызывающий передаёт
    выходы новыми сверху (таблица читается сверху вниз), и этот порядок
    обязан дойти до ответа — иначе свежий выход оказывался внизу.
    """
    rows = {
        "1": [_row(1, NIGHT, "20:00:00", "ПРОГОН-1")],
        "2": [_row(2, NIGHT, "20:10:00", "ПРОГОН-2")],
    }
    # Вызывающий отдал новые сверху: проход 2 (поздний) идёт первым.
    cycles = [
        _cycle(2, _iso(NIGHT, "20:10:00"), _iso(NIGHT, "23:00:00"), cycle_id=2),
        _cycle(1, _iso(NIGHT, "20:00:00"), _iso(NIGHT, "22:50:00"), cycle_id=1),
    ]

    matches = match_cycles_to_rows(cycles, rows)

    assert [m.cycle["cycle_id"] for m in matches] == [2, 1], "порядок вызывающего"
    by_cycle = {m.cycle["cycle_id"]: m for m in matches}
    assert by_cycle[1].row.profile == "ПРОГОН-1", "подбор всё равно верный"
    assert by_cycle[2].row.profile == "ПРОГОН-2"


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


def test_row_after_exit_is_not_a_candidate():
    """Единственная строка номера позже выхода — не кандидат: подмены нет."""
    rows = {"6": [_row(6, NIGHT, "21:55:00", "СЛЕДУЮЩИЙ-ПРОГОН")]}
    cycles = [_cycle(6, _iso(NIGHT, "18:47:00"), _iso(NIGHT, "20:51:00"), cycle_id=7)]

    [m] = match_cycles_to_rows(cycles, rows)

    assert m.row is None
    assert m.code == CODE_NO_ROW
    assert m.rows_after_exit == 1


def test_earlier_row_wins_when_later_row_is_after_exit():
    """Из двух строк берётся своя: та, что позже выхода, отброшена."""
    rows = {
        "6": [
            _row(6, NIGHT, "18:50:00", "СВОЯ"),
            _row(6, NIGHT, "21:55:00", "СЛЕДУЮЩИЙ-ПРОГОН"),
        ]
    }
    cycles = [_cycle(6, _iso(NIGHT, "18:47:00"), _iso(NIGHT, "20:51:00"), cycle_id=7)]

    [m] = match_cycles_to_rows(cycles, rows)

    assert m.row.profile == "СВОЯ"
    assert m.code == CODE_OK
    assert m.rows_after_exit == 1


def test_row_far_beyond_tolerance_is_flagged_in_journal():
    """Строка соседней смены: расхождение больше допуска — пометка в журнале.

    На экран она не идёт: допуск не откалиброван, а ложная метка хуже
    пропущенной. Строка при этом показывается.
    """
    first_seen = datetime(2026, 9, 29, 22, 0, 0)
    # Заведомо за пределами допуска: на линии подвес проводит около трёх
    # часов, а такая строка принадлежит другой смене.
    book_time = first_seen + timedelta(seconds=MAX_ENTRY_DELTA_SECONDS + 3600)
    rows = {"7": [_row(7, DAY_2, book_time.strftime("%H:%M:%S"), "ДАЛЕКО")]}
    cycles = [_cycle(7, first_seen.isoformat(), _iso(DAY_2, "05:00:00"), cycle_id=8)]

    [m] = match_cycles_to_rows(cycles, rows)

    assert m.row is not None
    assert m.code == CODE_OK
    assert m.suspect_reason == "entry_delta"


def test_untrusted_first_seen_gives_row_without_delta():
    """Монитор застал подвес уже стоящим: строка своя, дельта не считается.

    После старта монитора и после разрыва связи первый замер равен моменту,
    когда монитор посмотрел, а не появлению подвеса — расхождение по нему
    ничего не значит (см. line_monitor.FIRST_SEEN_*).
    """
    rows = {"8": [_row(8, NIGHT, "13:14:00", "СВОЯ")]}
    cycles = [
        _cycle(8, _iso(NIGHT, "16:17:36"), _iso(NIGHT, "16:31:18"), cycle_id=9, source="start")
    ]

    [m] = match_cycles_to_rows(cycles, rows)

    assert m.row is not None
    assert m.entry_delta_sec is None
    assert m.suspect_reason == ""


def test_log_line_carries_cycle_history_and_verdict():
    """Строка журнала: проход целиком (ванны с временами), строка книги, дельта."""
    rows = {"21": [_row(21, NIGHT, "13:14:00", "ЮП-3658")]}
    cycle = _cycle(21, _iso(NIGHT, "13:11:00"), _iso(NIGHT, "16:31:18"), cycle_id=8)
    cycle["path"] = [
        {"bath": "30", "in": _iso(NIGHT, "13:11:00"), "out": _iso(NIGHT, "14:02:00")},
        {"bath": "31", "in": _iso(NIGHT, "14:05:00"), "out": None},
    ]

    [m] = match_cycles_to_rows([cycle], rows)
    line = match_log_line(m, "21")

    assert "cycle=8" in line
    assert "hanger=21" in line
    assert f"source={TRUSTED_FIRST_SEEN}" in line
    assert "row=29.09.2026 13:14:00" in line
    assert "delta=+180s(+3m)" in line
    assert "path=30@13:11:00->14:02:00 31@14:05:00->—" in line


def test_line_length_delta_is_not_suspect():
    """Расхождение размером с проход по линии — это норма, а не подозрение."""
    first_seen = datetime(2026, 9, 29, 10, 51, 0)
    rows = {"2": [_row(2, NIGHT, "08:33:00", "ПОСЛЕДНИЕ-2-ЧАСА")]}
    cycles = [_cycle(2, first_seen.isoformat(), _iso(NIGHT, "11:14:02"), cycle_id=8)]

    [m] = match_cycles_to_rows(cycles, rows)

    assert m.row is not None
    assert m.code == CODE_OK, "подвес на линии около трёх часов — бейдж не нужен"


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
