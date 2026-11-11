"""История введённых путей книги учёта.

Раньше память о путях жила только в браузере (``localStorage``, три пути) и
исчезала вместе с профилем киоска. Теперь её держит сервер: оператор должен
видеть, какие книги вводили раньше, с какой машины он ни зайди.

Автоматическое переключение источника историю не пополняет — она отвечает на
вопрос «какие пути выбирал человек», а не «куда правило увело чтение».
"""

import json

import pytest

from app.services.excel_service import RECENT_FILES_LIMIT, ExcelService


@pytest.fixture
def service(tmp_path, monkeypatch):
    """Свой каталог static и книга; watcher не поднимаем."""
    from app.core.config import settings

    static_dir = tmp_path / "static"
    static_dir.mkdir()
    monkeypatch.setattr(settings, "STATIC_DIR", str(static_dir))
    monkeypatch.setattr(settings, "EXCEL_ACTIVE_FILE_NAME", "active_excel.json")

    excel_service = ExcelService()
    excel_service._active_file_name = None
    excel_service._main_file_name = None
    excel_service._reserve_file_name = None
    excel_service._recent_files = []
    # Запись выбора проверяем, перезапуск watcher — нет.
    monkeypatch.setattr(excel_service, "_persist_and_watch", lambda: excel_service._save_persisted_books())
    return excel_service, static_dir / "active_excel.json"


def test_saved_roles_put_both_paths_in_history(service):
    excel_service, record = service

    excel_service.set_book_roles("\\\\srv\\main.xlsm", "\\\\srv\\reserve.xlsm")

    paths = [item["path"] for item in excel_service.recent_files]
    assert paths == ["\\\\srv\\main.xlsm", "\\\\srv\\reserve.xlsm"]
    assert all(item["used_at"] for item in excel_service.recent_files)

    saved = json.loads(record.read_text(encoding="utf-8"))
    assert [item["path"] for item in saved["recent_files"]] == paths


def test_repeated_path_moves_to_top_without_duplicates(service):
    excel_service, _record = service
    excel_service.set_book_roles("a", "b")

    excel_service.set_book_roles("b", None)

    assert [item["path"] for item in excel_service.recent_files] == ["b", "a"]


def test_history_is_capped_and_newest_first(service):
    excel_service, _record = service

    for index in range(RECENT_FILES_LIMIT + 5):
        excel_service.set_main_file(f"path-{index}")

    assert len(excel_service.recent_files) == RECENT_FILES_LIMIT
    assert excel_service.recent_files[0]["path"] == f"path-{RECENT_FILES_LIMIT + 4}"


def test_automatic_switch_does_not_touch_history(service):
    excel_service, _record = service
    excel_service.set_book_roles("main", "reserve")
    before = excel_service.recent_files

    excel_service.set_active_file("reserve")

    assert excel_service.recent_files == before


def test_history_survives_reload(service):
    excel_service, _record = service
    excel_service.set_book_roles("a", "b")

    reloaded = ExcelService()

    assert [item["path"] for item in reloaded.recent_files] == ["a", "b"]
    assert reloaded.main_file_name == "a"
    assert reloaded.reserve_file_name == "b"
