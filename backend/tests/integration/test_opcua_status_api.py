"""Статус OPC UA для дашборда — мгновенное чтение кэша.

Контракт ``GET /api/dashboard/status/opcua``:

- ответ отдаётся сразу из памяти, без ожидания подключения;
- соединением владеет фоновый ``_worker``, поэтому статусный роут не имеет
  права звать ``connect()``: при лежащем PLC каждый тик дашборда (раз в 10 с)
  висел бы на цикле переподключения;
- ``is_open`` — текущее значение ``opcua_service.is_connected``;
- ``status_text`` — текст по ``opcua_service.state``;
- форма ответа прежняя: ``is_open``, ``status_text``, ``last_modified``, ``error``.
"""

import time

import pytest
from httpx import ASGITransport, AsyncClient

from app.services.opcua_service import OPCUAState, opcua_service


@pytest.fixture
def no_connect(monkeypatch):
    """Соединение «лежит», а вызов ``connect()`` валит тест."""

    async def fail_if_called(*args, **kwargs):
        raise AssertionError("GET /api/dashboard/status/opcua не должен вызывать connect()")

    monkeypatch.setattr(opcua_service, "connect", fail_if_called)
    return monkeypatch


def _set_state(monkeypatch, *, connected: bool, state: OPCUAState) -> None:
    monkeypatch.setattr(type(opcua_service), "is_connected", property(lambda self: connected))
    monkeypatch.setattr(type(opcua_service), "state", property(lambda self: state))


async def _status() -> tuple[dict, float]:
    from app.main import app

    started = time.monotonic()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/api/dashboard/status/opcua")
    elapsed = time.monotonic() - started
    assert response.status_code == 200, response.text
    return response.json(), elapsed


async def test_status_does_not_wait_for_connect(no_connect):
    """PLC недоступен — ответ 200 сразу, без вызова ``connect()``."""
    _set_state(no_connect, connected=False, state=OPCUAState.DISCONNECTED)

    body, elapsed = await _status()

    assert body["is_open"] is False
    assert body["status_text"] == "Отключено"
    assert body["error"] is None
    assert elapsed < 1.0, f"статус ждал подключения {elapsed:.1f} с"


@pytest.mark.parametrize(
    ("connected", "state", "expected"),
    [
        (True, OPCUAState.CONNECTED, "Подключено"),
        (False, OPCUAState.CONNECTING, "Подключение..."),
        (False, OPCUAState.DISCONNECTED, "Отключено"),
        (False, OPCUAState.ERROR, "Ошибка"),
    ],
)
async def test_status_text_comes_from_cached_state(no_connect, connected, state, expected):
    """Текст статуса — перевод текущего ``state``, а не результат нового коннекта."""
    _set_state(no_connect, connected=connected, state=state)

    body, _ = await _status()

    assert body["is_open"] is connected
    assert body["status_text"] == expected
