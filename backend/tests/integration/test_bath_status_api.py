"""Статус ванн из кэша OPC UA (``GET /api/opcua/line/*``).

Контракт (#82): признак ``free`` из API убран совсем. Тег PLC ``Bath[n].Free``
на живой линии отдаёт ``False`` и у занятых, и у части свободных ванн, а UI его
не использовал. Вместо двусмысленного флага ответ несёт только ``in_use`` —
фактическое значение тега ``InUse``; неизвестное значение читается как
«не занята», а не как «свободна».
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


async def _line_status() -> dict:
    from app.main import app

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/api/opcua/line/status")
        assert response.status_code == 200, response.text
        return response.json()


async def test_bath_does_not_expose_free(plc):
    """Тег Free больше не читается и не попадает в ответ ванны."""
    plc["ns=4;s=Bath[5].Free"] = False

    assert "free" not in (await _bath(5))


async def test_line_status_does_not_expose_free(plc):
    """И в общем статусе линии поля free тоже нет (#82)."""
    plc["ns=4;s=Bath[5].Free"] = True

    body = await _line_status()
    assert body["baths"], "статус линии должен содержать ванны"
    assert all("free" not in bath for bath in body["baths"])


async def test_in_use_still_comes_from_plc(plc):
    """InUse остаётся фактическим значением тега, без подмены умолчанием."""
    plc["ns=4;s=Bath[5].InUse"] = True
    assert (await _bath(5))["in_use"] is True

    plc["ns=4;s=Bath[5].InUse"] = False
    assert (await _bath(5))["in_use"] is False

    plc.pop("ns=4;s=Bath[5].InUse")
    assert (await _bath(5))["in_use"] is False
