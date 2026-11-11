"""Активная книга учёта и выбор, сделанный на другой машине.

Файл выбора лежит в общем каталоге `static`: на машине, где рядом живут dev и
прод-контейнер, в него попадает путь соседней среды
(``/app/excel/…`` против ``\\\\172.17.11.7\\Оператор\\…``). Такой выбор не должен
подменять книгу на этой машине и не должен превращаться в чужой путь, а имя
файла выбора у сред своё (``EXCEL_ACTIVE_FILE_NAME``) — тогда чужой путь туда
и не попадает.
"""

import json
import logging
from pathlib import Path

import pytest

from app.services.excel_service import ExcelService


@pytest.fixture
def machine(tmp_path, monkeypatch):
    """Книга этой машины; наличие пути определяется только по tmp-каталогу."""
    from app.core.config import settings

    book = tmp_path / "excel" / "Учет КПЗ 2026.xlsm"
    book.parent.mkdir(parents=True)
    book.write_bytes(b"xlsm")
    (book.parent / "Ещё книга.xlsm").write_bytes(b"xlsm")

    monkeypatch.setattr(settings, "SIMULATION_ENABLED", False)
    monkeypatch.setattr(settings, "EXCEL_REAL_FILE_PATH", str(book))

    real_exists = Path.exists
    monkeypatch.setattr(
        Path,
        "exists",
        lambda self: real_exists(self) if str(self).startswith(str(tmp_path)) else False,
    )
    return book


def _service(active_file: str | None) -> ExcelService:
    service = ExcelService()
    service._active_file_name = active_file
    return service


@pytest.mark.parametrize(
    "foreign",
    [
        "/app/excel/Учет КПЗ 2026.xlsm",  # путь контейнера на dev-машине
        "\\\\172.17.11.7\\Оператор\\Учет КПЗ 2026.xlsm",  # путь dev-машины в контейнере
        "Z:\\Учет КПЗ 2026.xlsm",  # диск, которого здесь нет
    ],
)
def test_selection_from_another_machine_falls_back_to_config(machine, foreign, caplog):
    service = _service(foreign)

    with caplog.at_level(logging.WARNING, logger="app.services.excel_service"):
        assert service.current_path == machine

    assert "книга берётся из конфигурации" in caplog.text
    # Статус спрашивают постоянно — предупреждение должно быть одно на выбор.
    caplog.clear()
    with caplog.at_level(logging.WARNING, logger="app.services.excel_service"):
        result1 = service.current_path
        result2 = service.current_path
    assert result1 == result2 == machine
    assert caplog.text == ""


def test_foreign_path_is_not_glued_to_the_book_folder(machine):
    """``/app/excel/…`` не превращается в ``<шара>/app/excel/…``."""
    service = _service("/app/excel/Учет КПЗ 2026.xlsm")

    assert service._resolved_active() == Path("/app/excel/Учет КПЗ 2026.xlsm")
    assert service.current_path == machine


def test_share_path_is_not_glued_to_the_book_folder(machine):
    """Путь шары не достраивается каталогом книги (на Linux он не абсолютный)."""
    unc = "\\\\172.17.11.7\\Оператор\\Учет КПЗ 2026.xlsm"
    service = _service(unc)

    assert service._resolved_active() == Path(unc)


def test_existing_selection_wins_over_config(machine):
    selected = machine.parent / "Ещё книга.xlsm"

    service = _service(str(selected))

    assert service.current_path == selected


def test_bare_file_name_is_resolved_inside_the_book_folder(machine):
    """Старый формат записи — одно имя файла без пути."""
    service = _service("Ещё книга.xlsm")

    assert service.current_path == machine.parent / "Ещё книга.xlsm"


def test_missing_selection_and_missing_config_keeps_the_selection(machine):
    """Книги нет ни по выбору, ни по конфигурации: показываем выбор как есть."""
    from app.core.config import settings

    settings.EXCEL_REAL_FILE_PATH = str(machine.parent / "Нет книги.xlsm")
    service = _service("/app/excel/Учет КПЗ 2026.xlsm")

    assert service.current_path == Path("/app/excel/Учет КПЗ 2026.xlsm")


def test_no_selection_uses_config(machine):
    assert _service(None).current_path == machine


@pytest.mark.parametrize(
    "file_name, simulation, expected",
    [
        # Контейнер: свой файл, dev его не видит и не переписывает.
        ("active_excel_prod.json", False, "active_excel_prod.json"),
        ("active_excel_prod.json", True, "active_excel_prod_sim.json"),
        # dev по умолчанию — как было: общий файл и _sim-вариант для витрины.
        ("active_excel.json", False, "active_excel.json"),
        ("active_excel.json", True, "active_excel_sim.json"),
    ],
)
def test_selection_file_name_comes_from_settings(tmp_path, monkeypatch, file_name, simulation, expected):
    """Выбор пишется в файл из ``EXCEL_ACTIVE_FILE_NAME``, а общего не касается."""
    from app.core.config import settings

    static_dir = tmp_path / "static"
    static_dir.mkdir()
    # Книга этой машины: без неё set_active_file ушёл бы проверять путь на
    # боевую шару (в .env он UNC-ный и на Windows-хосте существует).
    book = tmp_path / "book.xlsm"
    book.write_bytes(b"xlsm")
    monkeypatch.setattr(settings, "STATIC_DIR", str(static_dir))
    monkeypatch.setattr(settings, "EXCEL_REAL_FILE_PATH", str(book))
    monkeypatch.setattr(settings, "EXCEL_TEST_FILE_PATH", str(book))
    monkeypatch.setattr(settings, "EXCEL_ACTIVE_FILE_NAME", file_name)
    monkeypatch.setattr(settings, "SIMULATION_ENABLED", simulation)

    ExcelService().set_active_file("/app/excel/Учет КПЗ 2026.xlsm")

    written = static_dir / expected
    saved = json.loads(written.read_text(encoding="utf-8"))
    assert saved["active_file"] == "/app/excel/Учет КПЗ 2026.xlsm"
    assert saved["main_file"] is None
    assert saved["reserve_file"] is None
    # Автоматическое переключение историю путей не пополняет.
    assert saved["recent_files"] == []
    # Единственный файл в каталоге — целевой: общий выбор dev не создан.
    assert [p.name for p in static_dir.iterdir()] == [expected]


# --- Роли книг в файле выбора (тикет 0008) ----------------------------------


@pytest.fixture
def role_files(tmp_path, monkeypatch):
    """Две книги и свой файл выбора; роли сохраняются в ``tmp_path/static``."""
    from app.core.config import settings

    static_dir = tmp_path / "static"
    static_dir.mkdir()
    excel_dir = tmp_path / "excel"
    excel_dir.mkdir()
    main = excel_dir / "Учет КПЗ 2026.xlsm"
    main.write_bytes(b"xlsm")
    reserve = excel_dir / "Учет КПЗ 2026 запасная.xlsm"
    reserve.write_bytes(b"xlsm")

    monkeypatch.setattr(settings, "STATIC_DIR", str(static_dir))
    monkeypatch.setattr(settings, "EXCEL_ACTIVE_FILE_NAME", "active_excel.json")
    monkeypatch.setattr(settings, "SIMULATION_ENABLED", False)
    monkeypatch.setattr(settings, "EXCEL_REAL_FILE_PATH", str(main))
    return main, reserve, static_dir / "active_excel.json"


def test_roles_are_saved_in_one_selection_record(role_files):
    """Выбор и роли — одна запись: второго источника истины нет."""
    main, reserve, record = role_files

    ExcelService().set_book_roles(str(main), str(reserve))

    saved = json.loads(record.read_text(encoding="utf-8"))
    assert saved["active_file"] == str(main)
    assert saved["main_file"] == str(main)
    assert saved["reserve_file"] == str(reserve)
    assert [item["path"] for item in saved["recent_files"]] == [str(main), str(reserve)]


def test_old_selection_without_roles_reads_active_as_main(role_files):
    """Старый формат (только ``active_file``): основная — она же, запасной нет."""
    main, _, record = role_files
    record.write_text(json.dumps({"active_file": str(main)}), encoding="utf-8")

    service = ExcelService()

    assert service.main_file_name == str(main)
    assert service.main_path == main
    assert service.reserve_path is None
    assert service.current_path == main
    assert service.current_role == "main"


def test_saving_the_same_roles_keeps_the_reserve_reading(role_files):
    """«Применить» с теми же ролями не отменяет переключение правила."""
    main, reserve, _ = role_files
    service = ExcelService()
    service.set_book_roles(str(main), str(reserve))
    service.set_active_file(str(reserve))

    service.set_book_roles(str(main), str(reserve))

    assert service.current_path == reserve
    assert service.current_role == "reserve"


def test_selection_outside_the_roles_falls_back_to_main(role_files):
    """Убрали запасную, а читалась она — активной снова становится основная."""
    main, reserve, _ = role_files
    service = ExcelService()
    service.set_book_roles(str(main), str(reserve))
    service.set_active_file(str(reserve))

    service.set_book_roles(str(main), None)

    assert service.current_path == main
    assert service.current_role == "main"


def test_set_main_file_clears_the_reserve_that_matches(role_files):
    """Книга не может быть сразу и основной, и запасной."""
    main, reserve, _ = role_files
    service = ExcelService()
    service.set_book_roles(str(main), str(reserve))

    service.set_main_file(str(reserve))

    assert service.main_path == reserve
    assert service.reserve_path is None
    assert service.current_path == reserve
    assert service.current_role == "main", "роль читаемой книги — основная"

