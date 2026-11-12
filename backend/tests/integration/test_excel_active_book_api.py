"""Активная книга учёта имеет одного владельца — и все ответы это подтверждают.

Путь к книге отдают три поверхности: ``GET /api/dashboard/status/file`` (строка
статуса), ``GET /api/dashboard/settings`` (вкладка настроек) и
``POST /api/dashboard/excel/select`` (ввод пути). Для одной ситуации они обязаны
называть один и тот же файл: расхождение — это второй источник истины, который
рано или поздно покажет оператору не ту книгу.
"""

import pytest
from httpx import ASGITransport, AsyncClient


@pytest.fixture
def books(tmp_path, monkeypatch):
    """Две книги в одном каталоге; конфиг задан относительно, как в .env."""
    from app.core.config import settings
    from app.services.excel_service import excel_service

    excel_dir = tmp_path / "excel"
    excel_dir.mkdir()
    first = excel_dir / "Учет КПЗ 2026.xlsm"
    first.write_bytes(b"xlsm")
    second = excel_dir / "Другая книга.xlsm"
    second.write_bytes(b"xlsm")

    # Конфигурация по умолчанию относительная (``../testdata/…``): проверяем,
    # что ответы не зависят от того, как путь записан.
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(settings, "SIMULATION_ENABLED", False)
    monkeypatch.setattr(settings, "EXCEL_REAL_FILE_PATH", "excel/Учет КПЗ 2026.xlsm")
    # Выбор книги — через публичный вход сервиса, без записи в файл на диске.
    excel_service.use_file(None)
    monkeypatch.setattr(excel_service, "_main_file_name", None)
    monkeypatch.setattr(excel_service, "_reserve_file_name", None)
    # Путь оператора для показа — часть выбора: чужой тест не должен
    # оставлять его следующему.
    monkeypatch.setattr(excel_service, "_main_entered", None)
    monkeypatch.setattr(excel_service, "_reserve_entered", None)
    # Выбор и роли пишутся в файл на диске — в тесте это лишнее состояние.
    monkeypatch.setattr(excel_service, "_save_persisted_books", lambda: None)
    return first, second


async def test_status_settings_and_select_name_the_same_book(books):
    from app.main import app
    from app.services.excel_service import excel_service

    first, second = books

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        status = await client.get("/api/dashboard/status/file")
        settings = await client.get("/api/dashboard/settings")

        # Книга из конфигурации: выбор ещё не сделан.
        expected = str(first.resolve())
        assert status.json()["file_path"] == expected
        assert settings.json()["excel_path"] == expected
        assert str(excel_service.current_path.resolve()) == expected

        selected = await client.post("/api/dashboard/excel/select", json={"file_path": str(second)})
        assert selected.status_code == 200, selected.text

        # Книга выбрана оператором: тот же путь во всех ответах.
        expected = str(second.resolve())
        status = await client.get("/api/dashboard/status/file")
        settings = await client.get("/api/dashboard/settings")

        assert selected.json()["active"] == expected
        assert status.json()["file_path"] == expected
        assert settings.json()["excel_path"] == expected
        assert str(excel_service.current_path.resolve()) == expected
