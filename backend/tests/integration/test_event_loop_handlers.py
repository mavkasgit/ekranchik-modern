"""Блокирующие вызовы хендлеров идут в потоке, а не в event loop (issue #76).

FastAPI обслуживает все запросы в одном event loop. Чтение книги по CIFS,
разбор журнала и синхронный ``socket.create_connection`` останавливают и
WebSocket, и секундный опрос монитора, и ``/health``. Поэтому такие вызовы
уходят в ``asyncio.to_thread``, и контракт проверяется по потоку: событие
считается исправленным, только если блокирующая функция выполняется не в том
потоке, где крутится loop.

Второй контракт — отзывчивость: пока медленная книга читается в потоке,
тикер (``/health``) продолжает тикать. Здесь тикером служит
``asyncio.sleep``: он показывает, что loop не занят чужим вызовом.
"""

import asyncio
import sqlite3
import threading
import time
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient

from app.services.hanger_journal import JournalStore


def _client() -> AsyncClient:
    from app.main import app

    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


def _record() -> dict:
    return {
        "recorded_at": "2026-09-29T20:16:03",
        "cycle_id": 42,
        "hanger": 5,
        "code": "",
        "exit_at": "2026-09-29T20:16:03",
        "profile": "10104",
    }


@pytest.fixture
def journal(tmp_path: Path, monkeypatch):
    """Журнал во временном каталоге, подменённый в роутере."""
    from app.api.routes import journal as journal_route

    store = JournalStore(tmp_path / "journal")
    store.append(_record())
    monkeypatch.setattr(journal_route, "journal_store", lambda: store)
    return store


async def test_journal_read_runs_off_the_event_loop_thread(journal, monkeypatch):
    """``store.query`` и ``store.files`` (диск) — не в потоке loop'а."""
    loop_thread = threading.get_ident()
    seen: list[int] = []

    original_query = journal.query
    original_files = journal.files

    def query(**kwargs):
        seen.append(threading.get_ident())
        return original_query(**kwargs)

    def files():
        seen.append(threading.get_ident())
        return original_files()

    monkeypatch.setattr(journal, "query", query)
    monkeypatch.setattr(journal, "files", files)

    async with _client() as client:
        response = await client.get("/api/journal/passes")

    assert response.status_code == 200, response.text
    assert seen, "журнал вообще не читался"
    assert loop_thread not in seen, "чтение журнала осталось в потоке event loop"


async def test_dashboard_reads_the_book_off_the_event_loop_thread(monkeypatch):
    """Чтение Excel для дашборда — в потоке, а не в обработчике запроса."""
    from app.services.excel_service import excel_service

    loop_thread = threading.get_ident()
    seen: list[int] = []

    def fake_products(*args, **kwargs):
        seen.append(threading.get_ident())
        return []

    monkeypatch.setattr(excel_service, "get_products", fake_products)

    async with _client() as client:
        response = await client.get("/api/dashboard")

    assert response.status_code == 200, response.text
    assert seen, "книга вообще не читалась"
    assert loop_thread not in seen, "чтение книги осталось в потоке event loop"


async def test_file_status_reads_the_book_off_the_event_loop_thread(tmp_path, monkeypatch):
    """Статус файла (stat + zipfile) — в потоке."""
    from app.api.routes import dashboard as dashboard_route
    from app.services.excel_service import excel_service

    book = tmp_path / "Учет КПЗ 2026.xlsx"
    book.write_bytes(b"xlsx")
    loop_thread = threading.get_ident()
    seen: list[int] = []

    monkeypatch.setattr(type(excel_service), "current_path", property(lambda self: book))

    def fake_internal_mtime(path):
        seen.append(threading.get_ident())
        return None

    monkeypatch.setattr(dashboard_route, "get_excel_internal_modified_time", fake_internal_mtime)

    async with _client() as client:
        response = await client.get("/api/dashboard/status/file")

    assert response.status_code == 200, response.text
    assert seen, "книга вообще не читалась"
    assert loop_thread not in seen, "stat/zipfile остались в потоке event loop"


@pytest.fixture
def ping_probe(monkeypatch):
    """Сокет PLC «лежит»; каждый замер записывает свой поток."""
    import app.services.opcua_service as opcua_module
    from app.core.config import settings
    from app.services.opcua_service import opcua_service

    seen: list[int] = []

    def fake_create_connection(address, timeout=None):
        seen.append(threading.get_ident())
        raise OSError("PLC недоступен")

    monkeypatch.setattr(opcua_module.socket, "create_connection", fake_create_connection)
    monkeypatch.setattr(settings, "OPCUA_ENDPOINT", "opc.tcp://127.0.0.1:4840")
    monkeypatch.setattr(opcua_service, "_url", "opc.tcp://127.0.0.1:4840")
    # Кэш последнего замера с TTL: тесту нужен именно новый замер.
    monkeypatch.setattr(opcua_service, "_last_ping_ms", None, raising=False)
    monkeypatch.setattr(opcua_service, "_ping_measured_at", None, raising=False)
    return seen


@pytest.fixture
def ping_ok(monkeypatch):
    """Сокет PLC отвечает; каждый замер записывает свой поток."""
    import app.services.opcua_service as opcua_module
    from app.services.opcua_service import opcua_service

    seen: list[int] = []

    class _Socket:
        def close(self):
            pass

    def fake_create_connection(address, timeout=None):
        seen.append(threading.get_ident())
        return _Socket()

    monkeypatch.setattr(opcua_module.socket, "create_connection", fake_create_connection)
    monkeypatch.setattr(opcua_service, "_url", "opc.tcp://127.0.0.1:4840")
    monkeypatch.setattr(opcua_service, "_last_ping_ms", None, raising=False)
    monkeypatch.setattr(opcua_service, "_ping_measured_at", None, raising=False)
    return seen


async def test_diagnose_probes_the_socket_off_the_event_loop_thread(ping_probe):
    """/diagnose не ждёт ``socket.create_connection`` в потоке loop'а."""
    loop_thread = threading.get_ident()

    async with _client() as client:
        response = await client.get("/api/opcua/diagnose")

    body = response.json()
    assert response.status_code == 200, response.text
    assert body["host_reachable"] is False
    assert len(ping_probe) == 1, "диагностика должна делать один socket-замер, а не два"
    assert loop_thread not in ping_probe, "socket-замер остался в потоке event loop"


async def test_metrics_probes_the_socket_off_the_event_loop_thread(ping_probe):
    """То же для /metrics."""
    loop_thread = threading.get_ident()

    async with _client() as client:
        response = await client.get("/api/opcua/metrics")

    assert response.status_code == 200, response.text
    assert response.json()["current_ping_ms"] is None
    assert len(ping_probe) == 1
    assert loop_thread not in ping_probe, "socket-замер остался в потоке event loop"


async def test_diagnose_names_the_endpoint_it_actually_probed(ping_probe, monkeypatch):
    """Host/port в ответе — того эндпоинта, до которого шёл сокет.

    Настройка ``OPCUA_ENDPOINT`` и фактический ``_url`` расходятся в режиме
    симуляции: ответ и лог не должны называть реальный PLC, который не
    опрашивали.
    """
    from app.core.config import settings
    from app.services.opcua_service import opcua_service

    monkeypatch.setattr(settings, "OPCUA_ENDPOINT", "opc.tcp://real-plc:4840")
    monkeypatch.setattr(opcua_service, "_url", "opc.tcp://simulator:4841")

    async with _client() as client:
        response = await client.get("/api/opcua/diagnose")

    body = response.json()
    assert response.status_code == 200, response.text
    assert body["endpoint"] == "opc.tcp://simulator:4841"
    assert body["host"] == "simulator"
    assert body["port"] == 4841


async def test_repeated_probes_use_the_cached_ping(ping_ok):
    """Повторный опрос в пределах TTL не открывает сокет заново."""
    async with _client() as client:
        await client.get("/api/opcua/metrics")
        await client.get("/api/opcua/diagnose")

    assert len(ping_ok) == 1, "удачный замер ping обязан переживать повторный запрос"


async def test_failed_probe_is_probed_again(ping_probe):
    """Неудача не кэшируется на TTL: PLC мог вернуться сразу после пробы."""
    async with _client() as client:
        metrics = await client.get("/api/opcua/metrics")
        diagnose = await client.get("/api/opcua/diagnose")

    assert metrics.json()["current_ping_ms"] is None
    assert diagnose.json()["host_reachable"] is False
    assert len(ping_probe) == 2, "неудачный замер не должен залипать на десять секунд"


@pytest.mark.parametrize(
    ("path", "payload"),
    [
        ("/api/signal/refresh", None),
        ("/api/signal", {"source": "excel", "event": "refresh"}),
    ],
)
async def test_signal_invalidates_excel_cache_off_the_event_loop_thread(path, payload, monkeypatch):
    """Сброс кэша книги ждёт ``_lock`` сервиса — значит, не в event loop.

    Пока книга перечитывается по CIFS, ``_lock`` занят; синхронный
    ``invalidate_cache`` в обработчике остановил бы API на всё чтение.
    """
    from app.services.excel_service import excel_service

    loop_thread = threading.get_ident()
    seen: list[int] = []

    def slow_invalidate():
        time.sleep(0.3)
        seen.append(threading.get_ident())

    monkeypatch.setattr(excel_service, "invalidate_cache", slow_invalidate)

    async with _client() as client:
        started = time.monotonic()
        request = asyncio.create_task(client.post(path, json=payload))
        await asyncio.sleep(0.05)
        tick_after = time.monotonic() - started
        response = await request

    assert response.status_code == 200, response.text
    assert seen, "сброс кэша вообще не выполнялся"
    assert loop_thread not in seen, "сброс кэша остался в потоке event loop"
    assert tick_after < 0.2, f"loop стоял {tick_after:.2f} с на сбросе кэша"


async def test_settings_toggle_goes_off_the_event_loop_thread(monkeypatch):
    """Запись .env и сброс книги при смене режима — в потоке."""
    from app.core.config import settings
    from app.services.excel_service import excel_service
    from app.services.opcua_service import opcua_service

    loop_thread = threading.get_ident()
    seen: list[int] = []

    monkeypatch.setattr(settings, "SIMULATION_ENABLED", False)
    monkeypatch.setattr(
        type(settings),
        "update_simulation_mode_in_env",
        lambda self, mode: seen.append(threading.get_ident()),
    )
    monkeypatch.setattr(excel_service, "update_simulation_mode", lambda: seen.append(threading.get_ident()))

    async def fake_update(mode):
        return None

    monkeypatch.setattr(opcua_service, "update_simulation_mode", fake_update)

    async with _client() as client:
        response = await client.post("/api/dashboard/settings", json={"simulation_enabled": True})

    assert response.status_code == 200, response.text
    assert len(seen) == 2, "ожидались записи .env и сброс книги через поток"
    assert loop_thread not in seen, "запись .env осталась в потоке event loop"


async def test_excel_file_switch_goes_off_the_event_loop_thread(tmp_path, monkeypatch):
    """Смена активной книги (запись файла выбора) — в потоке."""
    from app.services.excel_service import excel_service

    book = tmp_path / "Учет КПЗ 2026.xlsx"
    book.write_bytes(b"xlsx")
    loop_thread = threading.get_ident()
    seen: list[int] = []

    monkeypatch.setattr(excel_service, "set_main_file", lambda path: seen.append(threading.get_ident()))

    async with _client() as client:
        response = await client.post("/api/dashboard/excel/select", json={"file_path": str(book)})

    assert response.status_code == 200, response.text
    assert seen, "смена книги вообще не выполнялась"
    assert loop_thread not in seen, "смена книги осталась в потоке event loop"


async def test_slow_book_read_keeps_the_event_loop_ticking(monkeypatch):
    """Медленная книга не съедает loop: тикер продолжает тикать."""
    from app.services.excel_service import excel_service

    def slow_products(*args, **kwargs):
        time.sleep(0.6)
        return []

    monkeypatch.setattr(excel_service, "get_products", slow_products)

    async with _client() as client:
        started = time.monotonic()
        dashboard = asyncio.create_task(client.get("/api/dashboard"))
        await asyncio.sleep(0.05)
        tick_after = time.monotonic() - started

        health = await client.get("/health")
        await dashboard

    assert tick_after < 0.3, f"loop стоял {tick_after:.2f} с на чтении книги"
    assert health.status_code == 200, health.text


async def test_zip_export_runs_off_the_event_loop_thread(tmp_path, monkeypatch):
    """Сборка ZIP каталога (sqlite + фото) — в потоке."""
    from app.api.routes import catalog as catalog_route
    from app.core.config import settings

    db = tmp_path / "catalog.db"
    sqlite3.connect(db).close()
    images = tmp_path / "images"
    images.mkdir()
    (images / "photo.jpg").write_bytes(b"jpeg")

    monkeypatch.setattr(settings, "DATABASE_URL", f"sqlite:///{db.as_posix()}")
    monkeypatch.setattr(settings, "IMAGES_DIR", str(images))

    loop_thread = threading.get_ident()
    seen: list[int] = []
    original_zip = catalog_route.zipfile.ZipFile

    def recording_zip(*args, **kwargs):
        seen.append(threading.get_ident())
        return original_zip(*args, **kwargs)

    monkeypatch.setattr(catalog_route.zipfile, "ZipFile", recording_zip)

    async with _client() as client:
        response = await client.get("/api/catalog/export/zip")

    assert response.status_code == 200, response.text
    assert response.content, "архив пуст"
    assert seen, "ZIP вообще не собирался"
    assert loop_thread not in seen, "сборка ZIP осталась в потоке event loop"


async def test_startup_journal_reads_off_the_event_loop_thread(monkeypatch):
    """Чтение журнала при старте — в потоке, до старта монитора."""
    import app.main as main_module
    from app.services.excel_watcher import excel_watcher
    from app.services.journal_writer import journal_writer
    from app.services.line_monitor import line_monitor
    from app.services.opcua_service import opcua_service

    loop_thread = threading.get_ident()
    seen: list[int] = []

    monkeypatch.setattr(main_module, "ensure_data_dirs", lambda: None)

    async def no_migrations():
        return None

    monkeypatch.setattr(main_module, "run_startup_migrations", no_migrations)
    monkeypatch.setattr(excel_watcher, "start", lambda *args, **kwargs: True)

    monkeypatch.setattr(
        journal_writer.store, "max_cycle_id", lambda: seen.append(threading.get_ident()) or 0
    )
    monkeypatch.setattr(journal_writer, "load_written_keys", lambda: seen.append(threading.get_ident()))
    monkeypatch.setattr(
        journal_writer, "restore_recent", lambda monitor: seen.append(threading.get_ident()) or 0
    )
    async def noop_prune():
        return []

    monkeypatch.setattr(journal_writer, "prune", noop_prune)
    monkeypatch.setattr(line_monitor, "resume_cycle_counter", lambda value: None)

    async def noop_start():
        return None

    monkeypatch.setattr(opcua_service, "start", noop_start)
    monkeypatch.setattr(line_monitor, "start", noop_start)

    async def noop_writer(monitor, interval):
        return None

    monkeypatch.setattr(journal_writer, "run_forever", noop_writer)

    async with main_module.lifespan(main_module.app):
        pass

    assert len(seen) == 3, "ожидались три чтения журнала на старте"
    assert loop_thread not in seen, "чтение журнала на старте осталось в потоке event loop"
