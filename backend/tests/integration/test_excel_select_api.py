"""Выбор книги учёта по пути (``POST /api/dashboard/excel/select``).

Оператор набирает сетевую книгу так, как её видит его машина
(``\\\\ktm-disk\\Оператор\\Учет КПЗ 2026.xlsm`` или ``Z:\\…``), а сервер держит
шару смонтированной в каталог книги — в контейнере такой путь не разрешается.
Контракт: хвост после шары ищется в каталоге книги; каталог пуст — ошибка
говорит про несмонтированный диск, а не только «Файл не найден».
"""

from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient


@pytest.fixture
def no_share(monkeypatch):
    """Сетевой шары для теста нет.

    На Windows-хосте ``\\\\ktm-disk\\Оператор\\…`` действительно существует (это
    та же шара, что и у боевого сервера), и проверка «файл есть» ушла бы в
    сеть. Тест обязан проверять запасной путь — разрешение внутри каталога
    книги, поэтому UNC и диск ``Z:`` объявлены несуществующими.
    """
    real_exists = Path.exists

    def exists(self):
        text = str(self)
        if text.startswith("\\\\") or text.startswith("Z:"):
            return False
        return real_exists(self)

    monkeypatch.setattr(Path, "exists", exists)


@pytest.fixture
def book(tmp_path: Path, monkeypatch):
    """Каталог книги (смонтированная шара) без записи выбора на диск.

    Выбор идёт через настоящий ``set_main_file``: ответ ввода пути обязан
    называть ту же книгу, что и строка статуса, а это свойство сервиса, не
    роута.
    """
    from app.core.config import settings
    from app.services.excel_service import excel_service

    book_dir = tmp_path / "excel"
    book_dir.mkdir()
    book = book_dir / "Учет КПЗ 2026.xlsm"
    book.write_bytes(b"xlsm")
    (book_dir / "excel").mkdir()  # подпапка внутри шары

    monkeypatch.setattr(settings, "SIMULATION_ENABLED", False)
    monkeypatch.setattr(settings, "EXCEL_REAL_FILE_PATH", str(book))
    monkeypatch.setattr(excel_service, "_active_file_name", None)
    monkeypatch.setattr(excel_service, "_main_file_name", None)
    monkeypatch.setattr(excel_service, "_reserve_file_name", None)
    # Путь оператора для показа хранится рядом с ролью: чужой тест не должен
    # оставлять его следующему.
    monkeypatch.setattr(excel_service, "_main_entered", None)
    monkeypatch.setattr(excel_service, "_reserve_entered", None)
    monkeypatch.setattr(excel_service, "_recent_files", [])
    # Запись выбора переживает перезапуск — в тесте это лишнее состояние.
    monkeypatch.setattr(excel_service, "_save_persisted_books", lambda: None)
    return book


async def _select(path: str):
    from app.main import app

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        return await client.post("/api/dashboard/excel/select", json={"file_path": path})


async def test_unc_path_of_operator_resolves_inside_the_mount(book, no_share):
    """``\\\\ktm-disk\\Оператор\\…`` — путь, который оператор видит у себя.

    Сервер находит книгу в смонтированном каталоге, но отвечает путём
    оператора: ``/app/excel/…`` на его машине не существует.
    """
    from app.services.excel_service import excel_service

    typed = "\\\\ktm-disk\\Оператор\\Учет КПЗ 2026.xlsm"

    response = await _select(typed)

    assert response.status_code == 200, response.text
    assert response.json() == {"success": True, "active": typed}
    assert excel_service.main_path == book.resolve()
    assert excel_service.main_entered_path == typed


async def test_share_path_with_subfolder_keeps_the_tail(book, no_share):
    nested = book.parent / "excel" / "Учет КПЗ 2026.xlsm"
    nested.write_bytes(b"xlsm")
    typed = "\\\\172.17.11.7\\Оператор\\excel\\Учет КПЗ 2026.xlsm"

    response = await _select(typed)

    assert response.status_code == 200, response.text
    assert response.json()["active"] == typed


async def test_mapped_drive_path_resolves_inside_the_mount(book, no_share):
    typed = "Z:\\Учет КПЗ 2026.xlsm"

    response = await _select(typed)

    assert response.status_code == 200, response.text
    assert response.json()["active"] == typed


async def test_server_path_keeps_working(book):
    """Путь сервера (то, что показывает статус-строка) — как есть."""
    response = await _select(str(book))

    assert response.status_code == 200, response.text
    assert response.json()["active"] == str(book.resolve())


@pytest.mark.parametrize(
    "quoted",
    [
        '"\\\\ktm-disk\\Оператор\\Учет КПЗ 2026.xlsm"',
        "'\\\\ktm-disk\\Оператор\\Учет КПЗ 2026.xlsm'",
        '" \\\\ktm-disk\\Оператор\\Учет КПЗ 2026.xlsm "',
        "«\\\\ktm-disk\\Оператор\\Учет КПЗ 2026.xlsm»",
        "“\\\\ktm-disk\\Оператор\\Учет КПЗ 2026.xlsm”",
        '""\\\\ktm-disk\\Оператор\\Учет КПЗ 2026.xlsm""',
        '  "\\\\ktm-disk\\Оператор\\Учет КПЗ 2026.xlsm"  ',
    ],
)
async def test_path_in_quotes_is_accepted(book, no_share, quoted):
    """Копия пути из проводника или письма: кавычки любого вида по краям."""
    typed = "\\\\ktm-disk\\Оператор\\Учет КПЗ 2026.xlsm"

    response = await _select(quoted)

    assert response.status_code == 200, response.text
    assert response.json()["active"] == typed


async def test_missing_file_is_reported_with_the_path(book, no_share):
    response = await _select("\\\\ktm-disk\\Оператор\\Другая книга.xlsm")

    assert response.status_code == 404
    detail = response.json()["detail"]
    assert "не найден" in detail
    assert "Другая книга.xlsm" in detail
    assert "не смонтирован" not in detail, "каталог книги не пуст — подсказка лишняя"


async def test_empty_mount_is_reported_as_unmounted(tmp_path, monkeypatch, no_share):
    """Пустой каталог книги — это несмонтированный диск, и он назван в ошибке."""
    from app.core.config import settings
    from app.services.excel_service import excel_service

    empty = tmp_path / "empty"
    empty.mkdir()
    monkeypatch.setattr(settings, "SIMULATION_ENABLED", False)
    monkeypatch.setattr(settings, "EXCEL_REAL_FILE_PATH", str(empty / "Учет КПЗ 2026.xlsm"))
    monkeypatch.setattr(excel_service, "_active_file_name", None)

    response = await _select("\\\\ktm-disk\\Оператор\\Учет КПЗ 2026.xlsm")

    assert response.status_code == 404
    detail = response.json()["detail"]
    assert str(empty) in detail
    assert "сетевой диск не смонтирован" in detail


async def test_broken_path_is_not_found_not_a_crash(book, monkeypatch, no_share):
    """Windows-путь в Linux-контейнере: stat отвечает EINVAL — это 404, не 500."""
    real_exists = Path.exists

    def exists(self):
        if str(self).startswith("\\\\"):
            raise OSError(22, "Invalid argument", str(self))
        return real_exists(self)

    monkeypatch.setattr(Path, "exists", exists)

    response = await _select("\\\\ktm-disk\\Оператор\\Нет такой книги.xlsm")

    assert response.status_code == 404
    assert "не найден" in response.json()["detail"]


async def test_files_list_endpoint_is_gone():
    """Пикер убран: списка файлов нет, выбор книги — только вводом пути."""
    from app.main import app

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/api/dashboard/excel/files")

    assert response.status_code == 404
