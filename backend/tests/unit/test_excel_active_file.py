"""Активная книга учёта и выбор, сделанный на другой машине.

``active_excel.json`` лежит в общем каталоге `static`: на машине, где рядом
живут dev и прод-контейнер, в него попадает путь соседней среды
(``/app/excel/…`` против ``\\\\172.17.11.7\\Оператор\\…``). Такой выбор не должен
подменять книгу на этой машине и не должен превращаться в чужой путь.
"""
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
        service.current_path
        service.current_path
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
