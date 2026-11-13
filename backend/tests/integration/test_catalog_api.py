"""API каталога — витрина: чтение и примечание, остальное удалено.

Контракт под тестом (спека 0002, ADR 0010):
- поля артикула принадлежат каталогу-источнику, поэтому в ответе есть
  наименование (``description``), а мёртвого ``usage_count`` нет;
- создание, правка, удаление, работа с фото и ZIP удалены: такие маршруты
  отвечают 404/405;
- ``PATCH /catalog/{id}/notes`` — единственная запись: меняет только
  примечание и отвечает 200/404/422;
- миграция ``002`` добавляет ``profiles.description`` на чистой базе.
"""

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

ARTICLES = {"name": "ЮП-1625", "description": "Профиль ЮП-1625", "notes": "Аналог-ЮП-3168"}

# Поля витрины из спеки 0002: описание есть, usage_count нет.
PROFILE_FIELDS = {
    "id",
    "name",
    "description",
    "quantity_per_hanger",
    "length",
    "notes",
    "photo_thumb",
    "photo_full",
    "photo_thumb_version",
    "photo_full_version",
    "created_at",
    "updated_at",
}

REMOVED_WRITES = [
    ("POST", "/api/catalog"),
    ("PUT", "/api/catalog/1"),
    ("DELETE", "/api/catalog/1"),
    ("POST", f"/api/catalog/{ARTICLES['name']}/photo"),
    ("PUT", f"/api/catalog/{ARTICLES['name']}/thumbnail"),
    ("DELETE", f"/api/catalog/{ARTICLES['name']}/photo"),
    ("DELETE", f"/api/catalog/{ARTICLES['name']}/photo/full"),
    ("DELETE", f"/api/catalog/{ARTICLES['name']}/photo/thumbnail"),
    ("GET", "/api/catalog/export/zip"),
]


def _client() -> AsyncClient:
    from app.main import app

    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


@pytest.fixture
async def catalog(tmp_path, monkeypatch):
    """Каталог в свежей sqlite-базе и пустом каталоге фото."""
    from app.core.config import settings
    from app.db import session as session_module
    from app.db.base import Base
    from app.db.models import Profile

    images = tmp_path / "images"
    images.mkdir()
    monkeypatch.setattr(settings, "IMAGES_DIR", str(images))

    engine = create_async_engine(f"sqlite+aiosqlite:///{(tmp_path / 'catalog.db').as_posix()}")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    maker = async_sessionmaker(engine, expire_on_commit=False)
    monkeypatch.setattr(session_module, "async_session_maker", maker)

    async with maker() as session:
        session.add(
            Profile(
                name=ARTICLES["name"],
                description=ARTICLES["description"],
                length=6000.0,
                quantity_per_hanger=10,
                notes=ARTICLES["notes"],
                photo_thumb="images/yp-1625-thumb.jpg",
                photo_full="images/yp-1625.jpg",
            )
        )
        await session.commit()

    yield maker

    await engine.dispose()


async def _get(path: str) -> dict:
    async with _client() as client:
        response = await client.get(path)
    assert response.status_code == 200, response.text
    return response.json()


async def _profile_id() -> int:
    listing = await _get("/api/catalog/all")
    return listing[0]["id"]


async def _patch_notes(profile_id: int, notes: str | None) -> tuple[int, dict]:
    async with _client() as client:
        response = await client.patch(f"/api/catalog/{profile_id}/notes", json={"notes": notes})
    return response.status_code, response.json()


async def test_all_catalog_returns_description_and_no_usage_count(catalog):
    """Полный список витрины: наименование есть, счётчика использований нет."""
    listing = await _get("/api/catalog/all")

    assert len(listing) == 1
    item = listing[0]
    assert set(item) == PROFILE_FIELDS
    assert item["description"] == ARTICLES["description"]
    assert "usage_count" not in item


async def test_profile_card_returns_description_and_no_usage_count(catalog):
    """Карточка артикула по имени отдаёт то же наименование."""
    item = await _get(f"/api/catalog/{ARTICLES['name']}")

    assert set(item) == PROFILE_FIELDS
    assert item["description"] == ARTICLES["description"]
    assert "usage_count" not in item


@pytest.mark.parametrize(("method", "path"), REMOVED_WRITES)
async def test_removed_write_routes_are_gone(catalog, method, path):
    """Каталог закрыт на запись: удалённые маршруты не обслуживаются."""
    async with _client() as client:
        response = await client.request(method, path)

    assert response.status_code in (404, 405), f"{method} {path} → {response.status_code}"


async def test_notes_patch_saves_note_and_changes_nothing_else(catalog):
    """PATCH /notes меняет только примечание: поля источника и фото на месте."""
    profile_id = await _profile_id()
    before = await _get(f"/api/catalog/{ARTICLES['name']}")

    status, updated = await _patch_notes(profile_id, "Аналог-ЮП-3169")

    assert status == 200
    assert updated["notes"] == "Аналог-ЮП-3169"
    assert (await _get(f"/api/catalog/{ARTICLES['name']}"))["notes"] == "Аналог-ЮП-3169"

    after = await _get(f"/api/catalog/{ARTICLES['name']}")
    for field in PROFILE_FIELDS - {"notes", "updated_at"}:
        assert after[field] == before[field], field


@pytest.mark.parametrize("empty", [None, ""])
async def test_notes_patch_clears_note(catalog, empty):
    """``null`` и пустая строка очищают примечание."""
    profile_id = await _profile_id()

    status, updated = await _patch_notes(profile_id, empty)

    assert status == 200
    assert updated["notes"] is None


async def test_notes_patch_reports_missing_article(catalog):
    """Несуществующий артикул — 404, а не молчаливое создание."""
    status, _ = await _patch_notes(999_999, "примечание")

    assert status == 404


async def test_notes_patch_rejects_note_longer_than_limit(catalog):
    """Примечание длиннее 2000 символов — 422."""
    profile_id = await _profile_id()

    status, _ = await _patch_notes(profile_id, "я" * 2001)

    assert status == 422


async def test_migration_adds_description_column(tmp_path, monkeypatch):
    """``alembic upgrade head`` на чистой базе создаёт колонку описания."""
    import sqlite3

    from app.core import config as config_module
    from app.db import startup

    db_file = tmp_path / "migrated.db"
    monkeypatch.setattr(config_module.settings, "DATABASE_URL", "sqlite+aiosqlite:///" + db_file.as_posix())

    await startup.run_startup_migrations()

    with sqlite3.connect(db_file) as conn:
        columns = {row[1]: row for row in conn.execute("PRAGMA table_info(profiles)")}

    assert "description" in columns, "миграция 002 не добавила profiles.description"
    assert columns["description"][3] == 0, "description должен быть nullable"
