"""Публичный интерфейс кэша OPC UA.

Контракт под тестом (``OPCUAService``):
- значения узлов кладутся и читаются открытыми методами: route, симулятор и
  тесты не должны знать про приватный словарь;
- кэш очищается одной операцией — при смене режима и на стенде;
- размер кэша — публичное свойство: ``GET /api/opcua/data`` отдаёт его наружу.
"""

from app.services.opcua_service import OPCUAService


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
