"""Публичный интерфейс состояния линии.

Контракт под тестом (``LineMonitorService``):
- монитор отдаёт свои подвесы списками и находит их по номеру и по ванне:
  routes не должны знать, как состояние разложено внутри;
- завершённые проходы отдаются новыми сверху и с ограничением — таблица
  выхода читается сверху вниз;
- диагностике нужны счётчики и потолок истории: сколько подвесов в памяти
  и сколько шагов пути накоплено;
- состояние подставляется одним вызовом (``restore_hangers``), а не
  записью в приватный словарь.
"""

from datetime import datetime, timedelta

import pytest

from app.services import line_monitor as lm
from app.services.line_monitor import LineMonitorService


@pytest.fixture
def monitor() -> LineMonitorService:
    return LineMonitorService()


def _hanger(number: int, bath: str | None = None, minutes_ago: int = 0) -> lm.HangerState:
    return lm.HangerState(id=number, current_bath=bath, last_seen=datetime.now() - timedelta(minutes=minutes_ago))


def test_all_hangers_lists_every_tracked_state(monitor):
    """Все подвесы, о которых монитор помнит, отдаются одним списком."""
    idle = _hanger(7)
    in_bath = _hanger(8, bath="12")
    monitor.restore_hangers([idle, in_bath])

    assert {hanger.id for hanger in monitor.get_all_hangers()} == {7, 8}
    assert monitor.get_hanger_state(8) is in_bath
    assert monitor.get_hanger_state(999) is None


def test_hanger_is_found_by_its_bath_number(monitor):
    """Подвес по номеру ванны: экран ванны не перебирает чужие внутренности."""
    in_bath = _hanger(8, bath="12")
    monitor.restore_hangers([_hanger(7), in_bath])

    assert monitor.get_hanger_in_bath(12) is in_bath
    assert monitor.get_hanger_in_bath(13) is None


def test_active_hangers_are_only_those_in_a_bath(monitor):
    """Активен тот, кто стоит в ванне; сошедший с линии — нет."""
    idle = _hanger(7)
    in_bath = _hanger(8, bath="12")
    monitor.restore_hangers([idle, in_bath])

    assert monitor.get_active_hangers() == [in_bath]


def test_completed_cycles_are_newest_first_and_limited(monitor):
    """Завершённые проходы: только сошедшие с линии, новые сверху, с лимитом."""
    older = _hanger(7, minutes_ago=30)
    older.path = [lm.HangerPathEntry("30", datetime.now() - timedelta(minutes=90))]
    newer = _hanger(8, minutes_ago=5)
    newer.path = [lm.HangerPathEntry("31", datetime.now() - timedelta(minutes=60))]
    on_line = _hanger(9, bath="12")
    on_line.path = [lm.HangerPathEntry("12", datetime.now() - timedelta(minutes=10))]
    never_moved = _hanger(10)
    monitor.restore_hangers([older, newer, on_line, never_moved])

    assert monitor.get_completed_cycles() == [newer, older]
    assert monitor.get_completed_cycles(limit=1) == [newer]


def test_hanger_stats_count_tracked_hangers_and_path_history(monitor):
    """Диагностике нужны счётчики и потолок истории одним ответом."""
    assert monitor.get_hanger_stats() == {"tracked": 0, "path_entries": 0, "max_path_length": 0}

    short = _hanger(7, bath="12")
    short.path = [lm.HangerPathEntry("30", datetime.now()), lm.HangerPathEntry("31", datetime.now())]
    long = _hanger(8)
    long.path = [
        lm.HangerPathEntry("30", datetime.now()),
        lm.HangerPathEntry("31", datetime.now()),
        lm.HangerPathEntry("32", datetime.now()),
    ]
    monitor.restore_hangers([short, long])

    assert monitor.get_hanger_stats() == {"tracked": 2, "path_entries": 5, "max_path_length": 3}
