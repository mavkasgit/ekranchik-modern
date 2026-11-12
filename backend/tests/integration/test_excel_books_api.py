"""Роли книг учёта через API (тикет 0008, спека 0001).

Диалог «Ввести путь» задаёт две книги: основную и запасную. Какую читать
сейчас, оператор не выбирает — это решает правило (``standby_book``). Поэтому
``POST /api/dashboard/excel/books`` сохраняет только роли, а все поверхности
(строка статуса, настройки, файл выбора) обязаны называть одни и те же книги.

Ничего не читается с настоящей шары: книги — файлы в ``tmp_path``, запись
выбора — в ``tmp_path/static``.
"""

import json
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient

from app.services.excel_service import excel_service
from app.services.standby_book import standby_book


@pytest.fixture
def no_share(monkeypatch):
    """Сетевой шары для теста нет: UNC не уходит в сеть на Windows-хосте."""
    real_exists = Path.exists

    def exists(self):
        if str(self).startswith("\\\\") or str(self).startswith("Z:"):
            return False
        return real_exists(self)

    monkeypatch.setattr(Path, "exists", exists)


@pytest.fixture
def books(tmp_path, monkeypatch):
    """Две книги и свой файл выбора; синглтоны возвращаются как были."""
    from app.core.config import settings

    static_dir = tmp_path / "static"
    static_dir.mkdir()
    excel_dir = tmp_path / "excel"
    excel_dir.mkdir()
    main = excel_dir / "Учет КПЗ 2026.xlsm"
    main.write_bytes(b"xlsm")
    reserve = excel_dir / "Учет КПЗ 2026 запасная.xlsm"
    reserve.write_bytes(b"xlsm")
    record = static_dir / "active_excel.json"

    monkeypatch.setattr(settings, "STATIC_DIR", str(static_dir))
    monkeypatch.setattr(settings, "EXCEL_ACTIVE_FILE_NAME", "active_excel.json")
    monkeypatch.setattr(settings, "SIMULATION_ENABLED", False)
    monkeypatch.setattr(settings, "EXCEL_REAL_FILE_PATH", str(main))
    monkeypatch.setattr(excel_service, "_active_file_name", None)
    monkeypatch.setattr(excel_service, "_main_file_name", None)
    monkeypatch.setattr(excel_service, "_reserve_file_name", None)
    # Путь оператора для показа хранится рядом с ролью: чужой тест не должен
    # оставлять его следующему.
    monkeypatch.setattr(excel_service, "_main_entered", None)
    monkeypatch.setattr(excel_service, "_reserve_entered", None)
    monkeypatch.setattr(excel_service, "_recent_files", [])
    standby_book.reset()

    yield main, reserve, record

    standby_book.reset()


def _body(response) -> dict:
    try:
        return response.json()
    except ValueError:
        return {}


async def _post(path: str, payload: dict) -> tuple[int, dict]:
    from app.main import app

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(path, json=payload)
    return response.status_code, _body(response)


async def _get(path: str) -> dict:
    from app.main import app

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get(path)
    assert response.status_code == 200, response.text
    return response.json()


async def test_roles_are_saved_and_all_surfaces_name_the_same_book(books):
    """Сохранение ролей: файл выбора, статус и настройки — про одни книги."""
    main, reserve, record = books

    status_code, saved = await _post(
        "/api/dashboard/excel/books",
        {"main_path": str(main), "reserve_path": str(reserve)},
    )

    expected_main = str(main.resolve())
    expected_reserve = str(reserve.resolve())
    assert status_code == 200, saved
    assert saved == {
        "success": True,
        "main": expected_main,
        "reserve": expected_reserve,
        "active": expected_main,
    }

    # Файл выбора хранит выбор, роли и историю путей одной записью.
    saved_record = json.loads(record.read_text(encoding="utf-8"))
    assert saved_record["active_file"] == expected_main
    assert saved_record["main_file"] == expected_main
    assert saved_record["reserve_file"] == expected_reserve
    assert [item["path"] for item in saved_record["recent_files"]] == [
        expected_main,
        expected_reserve,
    ]

    status = await _get("/api/dashboard/status/file")
    assert status["role"] == "main"
    assert status["main_file_path"] == expected_main
    assert status["reserve_file_path"] == expected_reserve
    assert "main_last_growth" in status

    settings_response = await _get("/api/dashboard/settings")
    assert settings_response["excel_path"] == expected_main
    assert settings_response["excel_reserve_path"] == expected_reserve
    assert settings_response["excel_role"] == "main"


async def test_status_names_the_reserve_book_that_is_being_read(books):
    """Правило переключило чтение — статус называет запасную, а не основную."""
    main, reserve, _ = books
    await _post("/api/dashboard/excel/books", {"main_path": str(main), "reserve_path": str(reserve)})

    # Так переключает фоновая задача: через владельца активной книги.
    excel_service.set_active_file(str(reserve))

    status = await _get("/api/dashboard/status/file")
    assert status["role"] == "reserve"
    assert status["file_path"] == str(reserve.resolve())
    assert status["main_file_path"] == str(main.resolve())

    settings_response = await _get("/api/dashboard/settings")
    assert settings_response["excel_role"] == "reserve"


async def test_typed_share_path_is_shown_while_the_server_reads_its_own(books, no_share):
    """Оператор видит свой путь, сервер читает свой.

    ``\\\\ktm-disk\\Оператор\\Учет КПЗ 2026.xlsm`` в контейнере не разрешается, и
    книга находится в смонтированном каталоге. Показывать вместо ввода
    ``/app/excel/…`` нельзя: такого пути на машине оператора нет.
    """
    main, _, record = books
    typed = "\\\\ktm-disk\\Оператор\\" + main.name

    status_code, saved = await _post("/api/dashboard/excel/books", {"main_path": typed})

    assert status_code == 200, saved
    assert saved["main"] == typed
    assert saved["active"] == typed

    # В файле выбора — путь, по которому сервер реально читает книгу, и ввод
    # оператора отдельно: он нужен строке статуса и диалогу книг.
    stored = json.loads(record.read_text(encoding="utf-8"))
    assert stored["main_file"] == str(main.resolve())
    assert stored["main_entered"] == typed

    state = await _get("/api/dashboard/excel/books")
    assert state["main"] == typed
    assert state["active"] == typed
    assert state["recent"][0]["path"] == typed, "история помнит ввод, а не путь сервера"

    status = await _get("/api/dashboard/status/file")
    assert status["main_file_path"] == typed
    assert status["file_path"] == typed


async def test_books_endpoint_returns_path_history(books):
    """История введённых путей: какие книги были раньше и когда вводились."""
    main, reserve, _ = books
    await _post("/api/dashboard/excel/books", {"main_path": str(main), "reserve_path": str(reserve)})

    state = await _get("/api/dashboard/excel/books")

    assert state["main"] == str(main.resolve())
    assert state["reserve"] == str(reserve.resolve())
    assert state["active"] == str(main.resolve())
    assert [item["path"] for item in state["recent"][:2]] == [
        str(main.resolve()),
        str(reserve.resolve()),
    ]
    assert state["recent"][0]["used_at"], "у пути должна быть дата ввода"


async def test_equal_book_paths_are_rejected(books):
    """Одна книга в двух ролях — это не запасная книга, а ошибка ввода."""
    main, _, record = books

    status_code, body = await _post(
        "/api/dashboard/excel/books",
        {"main_path": str(main), "reserve_path": str(main)},
    )

    assert status_code == 400
    assert "совпадает" in body["detail"]
    assert not record.exists(), "ошибочный ввод не сохраняет роли"


async def test_empty_main_is_rejected(books):
    """Без основной книги роли не задать; пустая строка — тот же отказ."""
    _, _, record = books

    status_code, body = await _post("/api/dashboard/excel/books", {"main_path": "   "})

    assert status_code == 400
    assert "основной" in body["detail"].lower()
    assert not record.exists()


async def test_missing_book_is_rejected_with_its_path(tmp_path, books):
    """Книги нет — 404 с путём: оператор должен видеть, что именно не нашлось."""
    main, _, record = books
    missing = tmp_path / "excel" / "Нет книги.xlsm"

    status_code, body = await _post(
        "/api/dashboard/excel/books",
        {"main_path": str(main), "reserve_path": str(missing)},
    )

    assert status_code == 404, body
    assert "не найден" in body["detail"]
    assert missing.name in body["detail"]
    assert not record.exists()


@pytest.mark.parametrize("reserve", [None, ""], ids=["not-set", "empty"])
async def test_empty_reserve_turns_the_mode_off(books, reserve):
    """Пустая запасная — выключенный режим, и в файле выбора её нет."""
    main, saved_reserve, record = books
    await _post("/api/dashboard/excel/books", {"main_path": str(main), "reserve_path": str(saved_reserve)})

    payload: dict = {"main_path": str(main)}
    if reserve is not None:
        payload["reserve_path"] = reserve
    status_code, body = await _post("/api/dashboard/excel/books", payload)

    assert status_code == 200, body
    assert body["reserve"] is None
    assert body["active"] == str(main.resolve())
    assert json.loads(record.read_text(encoding="utf-8"))["reserve_file"] is None

    settings_response = await _get("/api/dashboard/settings")
    assert settings_response["excel_reserve_path"] == ""
    assert excel_service.reserve_path is None
