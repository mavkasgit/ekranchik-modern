"""Поведение воркера OPC UA при потере связи.

Политика сервиса: ошибки соединения не завершают процесс. Воркер закрывает
прежний клиент, создаёт новый и переподключается с паузой; счётчик подряд
идущих ошибок нужен только для лога и статуса, а не для выхода.
"""

import asyncio
import logging

import pytest

import app.services.opcua_service as opcua_module
from app.services.opcua_service import OPCUAService


class FakeClient:
    """Клиент с заранее заданной очередью исходов ``connect()``."""

    instances: list["FakeClient"] = []
    connect_outcomes: list[BaseException | None] = []

    def __init__(self, url, timeout=None):
        self.url = url
        self.timeout = timeout
        self.connected = False
        self.disconnected = False
        self.connect_calls = 0
        self.read_calls = 0
        self.session_timeout = None
        self.keepalive_interval = None
        self.secure_channel_timeout = None
        FakeClient.instances.append(self)

    async def connect(self):
        self.connect_calls += 1
        outcome = FakeClient.connect_outcomes.pop(0) if FakeClient.connect_outcomes else None
        if outcome is not None:
            raise outcome
        self.connected = True
        return True

    async def disconnect(self):
        self.disconnected = True

    def get_node(self, node_id):
        return node_id

    async def read_values(self, nodes):
        self.read_calls += 1
        return [1 for _ in nodes]


class BadBatchClient(FakeClient):
    """Клиент, у которого пачка чтения падает несетевой ошибкой."""

    async def read_values(self, nodes):
        raise ValueError("битый узел")


@pytest.fixture(autouse=True)
def reset_fake_clients():
    FakeClient.instances = []
    FakeClient.connect_outcomes = []
    yield
    FakeClient.instances = []
    FakeClient.connect_outcomes = []


def make_service(*, reconnect_delays=(0.0, 0.0, 0.0, 0.0)) -> OPCUAService:
    service = OPCUAService()
    service._poll_interval = 0
    service._reconnect_delays = reconnect_delays
    service.register_nodes(["ns=4;s=Bath[1].InUse"])
    return service


async def test_worker_reconnects_without_exiting(monkeypatch, caplog):
    """N ошибок подряд, затем успех: процесс жив, счётчик сброшен."""
    monkeypatch.setattr(opcua_module, "Client", FakeClient)
    exited = []
    monkeypatch.setattr("os._exit", lambda code: exited.append(code))
    caplog.set_level(logging.INFO, logger="OPCUA")

    FakeClient.connect_outcomes = [OSError("link down")] * 3
    service = make_service()
    service._error_log_threshold = 2
    observed_on_success = []
    record_success = service._record_success

    def spy_record_success():
        observed_on_success.append(service._consecutive_errors)
        record_success()

    monkeypatch.setattr(service, "_record_success", spy_record_success)
    service._running = True

    task = asyncio.create_task(service._worker())
    try:
        for _ in range(200):
            if len(FakeClient.instances) >= 4 and FakeClient.instances[-1].read_calls:
                break
            await asyncio.sleep(0.01)
    finally:
        service._running = False
        await asyncio.wait_for(task, timeout=5)

    assert exited == []
    # Каждая попытка — отдельный клиент; прежние закрыты.
    assert len(FakeClient.instances) == 4
    assert [client.connect_calls for client in FakeClient.instances] == [1, 1, 1, 1]
    assert all(client.disconnected for client in FakeClient.instances)
    # Счётчик накопился до трёх ошибок и сбросился успешным подключением.
    assert observed_on_success[0] == 3
    assert service._consecutive_errors == 0
    assert service._stats["connections"] == 1
    assert "2 ошибок соединения подряд" in caplog.text
    assert "Связь восстановлена" in caplog.text


def test_reconnect_delay_grows_and_caps():
    """Пауза: 1 → 2 → 5 → 10 с, дальше остаётся 10."""
    service = OPCUAService()
    delays = []
    for errors in range(6):
        service._consecutive_errors = errors
        delays.append(service._reconnect_delay())

    assert delays == [1.0, 1.0, 2.0, 5.0, 10.0, 10.0]


async def test_batch_read_error_does_not_count_as_connection_error():
    """Ошибка одной пачки — не ошибка соединения и не повод к реконнекту."""
    service = make_service()
    client = BadBatchClient(url="opc.tcp://fake", timeout=1)

    await service._poll_data_batched(client)

    assert service._consecutive_errors == 0
    assert service._consecutive_read_errors == 1
    assert service._stats["errors"] == 1
    assert service._stats["connections"] == 0


def test_diagnostics_exposes_consecutive_errors():
    """Счётчик виден снаружи: /status отдаёт его из диагностики."""
    service = make_service()
    service._consecutive_errors = 3

    assert service.get_diagnostics()["consecutive_errors"] == 3
