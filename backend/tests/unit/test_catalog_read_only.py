"""Витрина каталога не пишет и не тянет обработку картинок.

Контракт под тестом (спека 0002, ADR 0010): локальная запись каталога —
примечание и только оно. Помощники загрузки, кропа, переименования и удаления
фото удалены вместе с маршрутами (тикет 0019), поэтому их возврат — регрессия,
а не «мёртвый код»: вместе с ними возвращаются Pillow и второй владелец полей
артикула.
"""

from __future__ import annotations

import importlib
import re
from pathlib import Path

from app.services.catalog_service import catalog_service

catalog_module = importlib.import_module("app.services.catalog_service")
APP_DIR = Path(catalog_module.__file__).resolve().parents[1]

REMOVED_SERVICE_METHODS = [
    "save_photo",
    "generate_thumbnail",
    "update_thumbnail",
    "delete_photo",
    "delete_full_photo",
    "delete_thumbnail",
    "create_or_update_profile",
    "update_profile",
    "delete_profile",
    "increment_usage",
]

REMOVED_MODULE_HELPERS = [
    "_photo_file_stem",
    "_resolve_photo_path",
    "_write_thumbnail",
    "_save_jpeg_thumbnail",
    "_save_photo",
    "_save_thumbnail",
    "_db_photo_path",
    "_same_photo_file",
]

PILLOW_IMPORT = re.compile(r"^\s*(?:from|import)\s+PIL\b", re.MULTILINE)


def test_service_exposes_no_write_methods() -> None:
    """У сервиса нет методов записи: каталог-источник владеет полями артикула."""
    assert [name for name in REMOVED_SERVICE_METHODS if hasattr(catalog_service, name)] == []


def test_module_keeps_no_photo_helpers() -> None:
    """Помощники записи и удаления фото удалены, а не оставлены мёртвыми."""
    assert [name for name in REMOVED_MODULE_HELPERS if hasattr(catalog_module, name)] == []


def test_backend_app_does_not_import_pillow() -> None:
    """Обработки картинок в бэкенде нет: превью приходит из каталога-источника."""
    offenders = [
        path.relative_to(APP_DIR).as_posix()
        for path in APP_DIR.rglob("*.py")
        if PILLOW_IMPORT.search(path.read_text(encoding="utf-8"))
    ]

    assert offenders == []


def test_catalog_routes_in_openapi_are_read_only() -> None:
    """В OpenAPI у каталога только чтение и PATCH примечания."""
    from app.main import app

    operations = {
        (method, path)
        for path, item in app.openapi()["paths"].items()
        if path.startswith("/api/catalog")
        for method in item
        if method in {"get", "post", "put", "patch", "delete"}
    }

    assert operations == {
        ("get", "/api/catalog"),
        ("get", "/api/catalog/all"),
        ("get", "/api/catalog/{name}"),
        ("patch", "/api/catalog/{profile_id}/notes"),
    }
