"""Статус одной ванны из кэша OPC UA (``GET /api/opcua/line/bath/{n}``).

Контракт: признаки ``in_use`` и ``free`` — это значения PLC. Значение,
которого ещё нет в кэше, не должно превращать «занята» в «свободна» на
экране: такие поля читаются как булевы, а не как «нет данных».
"""

import pytest
from httpx import ASGITransport, AsyncClient


@pytest.fixture
def plc(monkeypatch):
    """Подменить кэш OPC UA словарём значений."""
    from app.api.routes import opcua as opcua_route

    values: dict[str, object] = {}
    monkeypatch.setattr(opcua_route.opcua_service, "get_value", lambda node: values.get(node))
    return values


async def _bath(number: int = 5) -> dict:
    from app.main import app

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get(f"/api/opcua/line/bath/{number}")
        assert response.status_code == 200, response.text
        return response.json()


async def test_free_from_plc_is_not_lost(plc):
    """PLC сказал «занята» — в ответе ``free: false``, а не всегда ``true``."""
    plc["ns=4;s=Bath[5].Free"] = False
    assert (await _bath(5))["free"] is False

    plc["ns=4;s=Bath[5].Free"] = True
    assert (await _bath(5))["free"] is True

    plc.pop("ns=4;s=Bath[5].Free")
    assert (await _bath(5))["free"] is True, "нет значения — свободна по умолчанию"
