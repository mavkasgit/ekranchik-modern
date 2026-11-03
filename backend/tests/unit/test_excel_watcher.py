"""Каталог наблюдения watcher'а — тот же, что у активной книги.

«Какой файл активен» имеет одного владельца — ``ExcelService.current_path``.
Watcher, запущенный без явного пути, обязан спросить его, а не конфигурацию:
конфиг — только стартовое значение, и при выбранной книге он уже не главный.
Иначе при старте сервер следит за каталогом, который никто не читает, и
правки книги не доезжают до дашборда.
"""

import sys
from pathlib import Path

import pytest

from app.services.excel_watcher import ExcelWatcher

watcher_module = sys.modules["app.services.excel_watcher"]


class _FakeObserver:
    """Заглушка watchdog: записывает каталог и не поднимает поток."""

    instances: list["_FakeObserver"] = []

    def __init__(self):
        self.scheduled: list[str] = []
        self.started = False
        _FakeObserver.instances.append(self)

    def schedule(self, handler, path, recursive=False):
        self.scheduled.append(str(path))

    def start(self):
        self.started = True

    def stop(self):
        pass

    def join(self, timeout=None):
        pass


@pytest.fixture
def active_book(tmp_path, monkeypatch):
    """Активная книга и другая книга из конфига — в разных каталогах."""
    from app.core.config import settings
    from app.services.excel_service import excel_service

    book_dir = tmp_path / "active"
    book_dir.mkdir()
    book = book_dir / "Учет КПЗ 2026.xlsm"
    book.write_bytes(b"xlsm")

    config_dir = tmp_path / "configured"
    config_dir.mkdir()
    configured = config_dir / "Учет КПЗ 2026.xlsm"
    configured.write_bytes(b"xlsm")

    monkeypatch.setattr(settings, "SIMULATION_ENABLED", False)
    monkeypatch.setattr(settings, "EXCEL_REAL_FILE_PATH", str(configured))
    excel_service.use_file(str(book))

    real_exists = Path.exists
    monkeypatch.setattr(
        Path,
        "exists",
        lambda self: real_exists(self) if str(self).startswith(str(tmp_path)) else False,
    )

    _FakeObserver.instances = []
    monkeypatch.setattr(watcher_module, "Observer", _FakeObserver)
    watcher = ExcelWatcher()
    yield watcher, book
    watcher.stop()


def test_start_watches_the_active_book_folder(active_book):
    watcher, book = active_book

    assert watcher.start() is True

    assert _FakeObserver.instances[0].scheduled == [str(book.parent)]
