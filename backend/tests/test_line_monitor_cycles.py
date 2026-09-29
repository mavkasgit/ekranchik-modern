"""Жизненный цикл прохода подвеса в line_monitor.

Контракт под тестом:
- каждый проход подвеса по линии получает свой cycle_id, first_seen_at и
  entry_bath; номер подвеса проход не идентифицирует, он повторяется;
- path принадлежит ТОЛЬКО текущему проходу и не наследуется следующему
  (иначе path[0] указывал бы на первый проход за всё время);
- выгрузка без открытого прохода даёт cycle_error, а не «нормальный» выход
  с total_time_sec = 0, и cycle_id задним числом не создаётся;
- дедупликация по cycle_id: два выхода одного номера в разных проходах —
  два события, повторная обработка одного прохода отсекается.
"""
import asyncio
from datetime import datetime, timedelta

import pytest

from app.services import line_monitor as lm
from app.services.line_monitor import LineMonitorService


@pytest.fixture
def monitor(monkeypatch):
    svc = LineMonitorService()
    monkeypatch.setattr(lm.opcua_service, "get_value", lambda node: None)
    return svc


def _baths(mapping):
    """Подменить значения OPC UA: {номер ванны: (InUse, Pallete)}."""
    def get_value(node: str):
        for bath, (in_use, pallete) in mapping.items():
            if node == f"ns=4;s=Bath[{bath}].InUse":
                return in_use
            if node == f"ns=4;s=Bath[{bath}].Pallete":
                return pallete
        return None
    return get_value


def test_repeated_number_gets_separate_cycles(monitor, monkeypatch):
    """Номер 1 прогоняют дважды — это два прохода, а не один с накопленным path."""
    monitor._open_cycle_hanger = None  # атрибут не используется, читаем состояние
    first = monitor._open_cycle
    state = lm.HangerState(id=1)
    monitor._hangers[1] = state
    first(state, 3, datetime(2026, 9, 29, 20, 0))
    state.current_bath = "3"
    state.path.append(lm.HangerPathEntry("3", datetime(2026, 9, 29, 20, 0)))
    state.current_bath = None  # подвес сошёл

    second = monitor._open_cycle
    later = datetime(2026, 9, 29, 22, 40)
    second(state, 4, later)

    assert state.cycle_id == 2
    assert state.first_seen_at == later
    assert state.entry_bath == 4
    assert state.path == [], "путь прошлого прохода не должен наследоваться"


def test_unload_closes_cycle_with_its_own_path(monitor, monkeypatch):
    """total_time_sec считается по текущему проходу, а не по первому за всё время."""
    start = datetime.now() - timedelta(minutes=90)
    state = lm.HangerState(id=1)
    monitor._hangers[1] = state
    monitor._open_cycle(state, 3, start)
    state.current_bath = "34"
    state.entry_time = start + timedelta(minutes=89)
    state.path.append(lm.HangerPathEntry("3", start))
    state.path.append(lm.HangerPathEntry("4", start + timedelta(minutes=30)))

    monkeypatch.setattr(lm, "websocket_manager", _SilentWS())
    asyncio.run(monitor._record_unload(1))

    event = monitor.get_unload_events()[-1]
    assert event["type"] == "unload"
    assert event["cycle_id"] == state.cycle_id
    assert 5300 < event["total_time_sec"] < 5500, "считает от первого замера текущего прохода"
    assert event["baths_visited"] == ["3", "4", "34"]


def test_unload_without_open_cycle_is_error(monitor, monkeypatch):
    """Состояние есть, но прохода нет — это ошибка монитора, а не выход."""
    state = lm.HangerState(id=4)
    state.current_bath = None
    state.path = []
    monitor._hangers[4] = state

    monkeypatch.setattr(lm, "websocket_manager", _SilentWS())
    asyncio.run(monitor._record_unload(4))

    event = monitor.get_unload_events()[-1]
    assert event["type"] == "cycle_error"
    assert event["reason"] == "unload_without_open_cycle"
    assert event["cycle_id"] is None, "цикл не создаётся задним числом"
    assert event["total_time_sec"] is None
    assert event["baths_visited"] is None


def test_dedup_by_cycle_id_keeps_both_unloads(monitor, monkeypatch):
    """Два выхода одного номера в разных проходах — два разных события."""
    monkeypatch.setattr(lm, "websocket_manager", _SilentWS())
    now = datetime.now()
    for cycle_start in (now - timedelta(hours=2), now - timedelta(minutes=10)):
        state = lm.HangerState(id=1)
        monitor._hangers[1] = state
        monitor._open_cycle(state, 3, cycle_start)
        state.path.append(lm.HangerPathEntry("3", cycle_start))
        state.current_bath = "34"
        state.entry_time = datetime.now()
        asyncio.run(monitor._record_unload(1))

    events = monitor.get_unload_events()
    assert len(events) == 2
    assert all(e["type"] == "unload" for e in events)
    assert len({e["cycle_id"] for e in events}) == 2, "у проходов разные cycle_id"


def test_duplicate_processing_of_same_cycle_dropped(monitor, monkeypatch):
    """Повторная обработка одного прохода второго события не создаёт."""
    monkeypatch.setattr(lm, "websocket_manager", _SilentWS())
    state = lm.HangerState(id=1)
    monitor._hangers[1] = state
    monitor._open_cycle(state, 3, datetime.now() - timedelta(minutes=30))
    state.path.append(lm.HangerPathEntry("3", datetime.now() - timedelta(minutes=30)))
    state.current_bath = "34"
    state.entry_time = datetime.now()

    asyncio.run(monitor._record_unload(1))
    # Датчик дрогнул 0→N ещё раз для того же прохода: current_bath уже None,
    # но cycle_id тот же — ни дубля выхода, ни второй cycle_error.
    asyncio.run(monitor._record_unload(1))

    events = monitor.get_unload_events()
    assert len(events) == 1
    assert events[0]["type"] == "unload"


def test_duplicate_processing_of_same_cycle_dropped(monitor, monkeypatch):
    """Повторная обработка одного прохода второго события не создаёт."""
    state = lm.HangerState(id=1)
    monitor._hangers[1] = state
    monitor._open_cycle(state, 3, datetime.now() - timedelta(minutes=30))
    state.current_bath = "34"
    state.entry_time = datetime.now()
    state.path.append(lm.HangerPathEntry("3", datetime.now() - timedelta(minutes=30)))
    state.current_bath = None

    monkeypatch.setattr(lm, "websocket_manager", _SilentWS())
    asyncio.run(monitor._record_unload(1))
    # повтор: current_bath уже None, но cycle_id тот же — событие не должно
    # ни появиться, ни превратиться в cycle_error второй раз
    asyncio.run(monitor._record_unload(1))

    assert len(monitor.get_unload_events()) == 1


class _SilentWS:
    connection_count = 0

    async def broadcast(self, message):
        return 0
