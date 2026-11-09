"""Публичный интерфейс кэша OPC UA.

Контракт под тестом (``OPCUAService``):
- значения узлов кладутся и читаются открытыми методами: route, симулятор и
  тесты не должны знать про приватный словарь;
- кэш очищается одной операцией — при смене режима и на стенде;
- размер кэша — публичное свойство: ``GET /api/opcua/data`` отдаёт его наружу;
- текст состояния для дашборда — свойство сервиса, чтобы ``CONNECTING`` не
  читался как «Отключено»;
- кэшируется только удачный замер ping: ``None`` — это «сейчас недоступен»,
  а не значение на весь TTL.
"""

import time

import app.services.opcua_service as opcua_module
from app.services.opcua_service import OPCUAService, OPCUAState


def test_values_put_into_the_cache_are_read_back():
    """Значение узла кладётся в кэш и читается оттуда же, без PLC."""
    service = OPCUAService()

    service.set_value("ns=4;s=Bath[1].InUse", 1)
    service.set_value("ns=4;s=Bath[1].Pallete", 42)

    assert service.get_value("ns=4;s=Bath[1].Pallete") == 42
    assert service.cache_size == 2


def test_clear_cache_forgets_every_node():
    """Очистка кэша возвращает сервис в состояние «ничего не прочитано»."""
    service = OPCUAService()
    service.set_value("ns=4;s=Bath[1].InUse", 1)

    service.clear_cache()

    assert service.cache_size == 0
    assert service.get_value("ns=4;s=Bath[1].InUse") is None


def test_status_text_covers_every_state():
    """Текст состояния — у сервиса, а не у роута: ``CONNECTING`` не «Отключено»."""
    service = OPCUAService()

    for state, expected in [
        (OPCUAState.CONNECTED, "Подключено"),
        (OPCUAState.CONNECTING, "Подключение..."),
        (OPCUAState.DISCONNECTED, "Отключено"),
        (OPCUAState.ERROR, "Ошибка"),
    ]:
        service._state = state
        assert service.status_text == expected


class _Socket:
    """Сокет, который ``_probe_ping`` закрывает сразу после замера."""

    def close(self) -> None:
        pass


async def test_successful_ping_is_cached(monkeypatch):
    """Повторный замер в пределах TTL не открывает второй сокет."""
    service = OPCUAService()
    service._url = "opc.tcp://127.0.0.1:4841"
    calls: list[tuple] = []

    def fake_connect(address, timeout=None):
        calls.append(address)
        return _Socket()

    monkeypatch.setattr(opcua_module.socket, "create_connection", fake_connect)

    first = await service.ping_server()
    second = await service.ping_server()

    assert first is not None
    assert second == first
    assert len(calls) == 1, "удачный замер обязан переживать повторный запрос"


async def test_failed_ping_is_not_cached(monkeypatch):
    """Неудача не залипает на TTL: следующий запрос снова пробует сокет.

    Иначе PLC, вернувшийся через секунду, ещё десять секунд отдавался бы
    диагностикой и дашбордом как недоступный.
    """
    service = OPCUAService()
    service._url = "opc.tcp://127.0.0.1:4841"
    calls: list[tuple] = []

    def fake_connect(address, timeout=None):
        calls.append(address)
        raise OSError("PLC недоступен")

    monkeypatch.setattr(opcua_module.socket, "create_connection", fake_connect)

    assert await service.ping_server() is None
    assert await service.ping_server() is None
    assert len(calls) == 2, "неудачный замер не должен кэшироваться"


async def test_mode_switch_forgets_the_ping_of_the_old_endpoint():
    """Смена режима сбрасывает замер: он сделан до другого эндпоинта."""
    service = OPCUAService()
    service._last_ping_ms = 12.0
    service._ping_measured_at = time.monotonic()

    await service.update_simulation_mode(True)

    assert service._last_ping_ms is None
    assert service._ping_measured_at is None
