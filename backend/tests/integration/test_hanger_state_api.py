"""Ответы /api/opcua о подвесах и ваннах.

Контракт под тестом:
- ``GET /hangers`` отдаёт все подвесы, включая уже сошедших с линии;
- ``GET /hangers/active`` — только тех, кто стоит в ванне;
- ``GET /hangers/{num}`` — подвес по номеру либо 404;
- ``GET /baths/{num}/hanger`` — подвес в ванне либо ``null``;
- ``GET /line/cycles`` — завершённые проходы новыми сверху.

Это вход экранов линии. Переезд routes на публичный интерфейс монитора не
должен менять в ответах ни одного поля, поэтому ожидаемые словари выписаны
целиком, а не сверены по частям.
"""

from datetime import datetime, timedelta

import pytest
from httpx import ASGITransport, AsyncClient

from app.services import line_monitor as lm


def _hanger(number: int, *, bath: str | None, first_seen: datetime, cycle_id: int, path: list[str]) -> lm.HangerState:
    state = lm.HangerState(id=number, current_bath=bath, last_seen=first_seen + timedelta(minutes=10))
    state.cycle_id = cycle_id
    state.first_seen_at = first_seen
    state.first_seen_source = lm.FIRST_SEEN_WATCHED
    state.entry_bath = int(path[0]) if path else None
    state.entry_time = first_seen
    state.path = [lm.HangerPathEntry(bath_name=bath_name, entry_time=first_seen) for bath_name in path]
    return state


@pytest.fixture
def line(monkeypatch):
    """Монитор с тремя подвесами: один в ванне, два уже сошли с линии."""
    from app.api.routes import opcua as opcua_route

    monitor = lm.LineMonitorService()
    monitor.restore_hangers(
        [
            _hanger(44, bath="12", first_seen=datetime(2026, 9, 29, 13, 11, 5), cycle_id=91, path=["4"]),
            _hanger(7, bath=None, first_seen=datetime(2026, 9, 29, 9, 0, 0), cycle_id=90, path=["3", "4"]),
            _hanger(8, bath=None, first_seen=datetime(2026, 9, 29, 11, 30, 0), cycle_id=92, path=["5", "6", "7"]),
        ]
    )
    monkeypatch.setattr(opcua_route, "line_monitor", monitor)
    return monitor


async def _get(path: str) -> dict:
    from app.main import app

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get(f"/api/opcua{path}")
        assert response.status_code == 200, response.text
        return response.json()


async def _status(path: str) -> int:
    from app.main import app

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get(f"/api/opcua{path}")
        return response.status_code


async def test_all_hangers_include_those_that_left_the_line(line):
    """Карточки подвесов: все, кого монитор помнит, с полями прохода."""
    body = await _get("/hangers")

    assert body["total"] == 3
    by_number = {hanger["number"]: hanger for hanger in body["hangers"]}
    assert by_number[44] == {
        "number": 44,
        "current_bath": 12,
        "baths_visited": [4],
        "cycle_id": 91,
        "line_entry_at": "2026-09-29T13:11:05",
        "entry_bath": 4,
        "first_seen_source": "watched",
    }
    assert by_number[7]["current_bath"] is None, "сошедший с линии остаётся в карточках"


async def test_active_hangers_are_only_those_in_a_bath(line):
    """Активные: ровно те, кто сейчас стоит в ванне."""
    body = await _get("/hangers/active")

    assert body["total"] == 1
    assert [hanger["number"] for hanger in body["hangers"]] == [44]


async def test_hanger_by_number_keeps_its_progress(line):
    """Карточка одного подвеса и 404 на неизвестный номер."""
    assert (await _get("/hangers/44"))["cycle_id"] == 91
    assert await _status("/hangers/999") == 404


async def test_bath_returns_the_hanger_standing_in_it(line):
    """Ванна отдаёт стоящий в ней подвес, а пустая — null."""
    assert await _get("/baths/12/hanger") == {"bath_number": 12, "hanger": {"number": 44, "current_bath": 12}}
    assert await _get("/baths/13/hanger") == {"bath_number": 13, "hanger": None}


async def test_completed_cycles_are_newest_first(line):
    """Завершённые проходы: новые сверху, с полями прохода."""
    body = await _get("/line/cycles")

    assert [cycle["hanger"] for cycle in body["cycles"]] == [8, 7], "новый выход сверху"
    assert body["cycles"][0]["baths_visited"] == ["5", "6", "7"]


async def test_system_health_counts_through_the_monitor_interface(line):
    """Диагностика считает подвесы и историю, не заглядывая в состояние."""
    body = await _get("/system/health")

    assert body["line_monitor"]["hangers_tracked"] == 3
    assert body["line_monitor"]["hangers_active"] == 1
    assert body["line_monitor"]["total_path_entries"] == 6
    assert body["line_monitor"]["max_path_length"] == 3
