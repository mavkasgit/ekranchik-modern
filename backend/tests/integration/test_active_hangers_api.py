"""Активные подвесы отдают время входа на линию (issue #34).

Контракт под тестом (``GET /api/opcua/hangers/active``):
- у подвеса, который сейчас в ванне, есть момент первого замера этого
  прохода: без него оператор не видит, сколько подвес уже в линии, и не
  может сравнить проход с записью книги учёта;
- номер прохода обязателен рядом с номером подвеса: номера на линии
  повторяются от смены к смене, и без ``cycle_id`` два прогона одного
  подвеса неразличимы.
"""
from datetime import datetime, timedelta

import pytest
from httpx import ASGITransport, AsyncClient


@pytest.fixture
def monitor_with_active(monkeypatch):
    """Монитор с одним подвесом в ванне и его открытым проходом."""
    from app.api.routes import opcua as opcua_route
    from app.services import line_monitor as lm

    first_seen = datetime.now() - timedelta(minutes=42)
    state = lm.HangerState(id=44, current_bath="12")
    state.entry_time = first_seen
    state.cycle_id = 91
    state.first_seen_at = first_seen
    state.first_seen_source = lm.FIRST_SEEN_WATCHED
    state.entry_bath = 4
    state.path = [lm.HangerPathEntry(bath_name="4", entry_time=first_seen)]

    class _Monitor:
        _hangers = {44: state}

    monkeypatch.setattr(opcua_route, "line_monitor", _Monitor())
    return state


async def _active() -> dict:
    from app.main import app

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.get("/api/opcua/hangers/active")
        assert response.status_code == 200, response.text
        return response.json()


async def test_active_hanger_carries_its_entry_time(monitor_with_active):
    """Подвес в ванне отдаёт, когда он впервые замечен в этом проходе."""
    body = await _active()

    assert body["total"] == 1
    hanger = body["hangers"][0]
    assert hanger["cycle_id"] == 91, "без номера прохода прогоны неразличимы"
    assert hanger["line_entry_at"].startswith(
        monitor_with_active.first_seen_at.strftime("%Y-%m-%dT%H:%M")
    )
    assert hanger["entry_bath"] == 4, "ванна, в которой подвес замечен"
