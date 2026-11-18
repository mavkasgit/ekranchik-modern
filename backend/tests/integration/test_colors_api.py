"""Справочник цветов: засев миграцией, чтение и локальная правка.

Контракт под тестом (спека 0003, тикеты 0022 и 0023):
- миграция ``003`` создаёт ``colors`` и засевает 22 цвета: десять текущих
  названий и двенадцать кодов веера ClassicELOX;
- ``GET /api/colors`` отдаёт весь справочник без служебных полей БД,
  пустой справочник — пустой массив;
- ``PATCH /api/colors/{id}`` меняет только ``name``/``hex``, ставит
  ``updated_at`` в текущее UTC-время и ``source=local``; создания и удаления
  через API нет.
"""

from datetime import UTC, datetime
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

# Поля ответа из тикета 0022 плюс abbreviation: id/code/name/hex/operation_code/source/updated_at.
COLOR_FIELDS = {"id", "code", "name", "hex", "abbreviation", "operation_code", "source", "updated_at"}

# Двенадцать кодов веера — каждый должен прийти из засева.
FAN_CODES = {"C0", "C35", "S120-0", "S120-2", "C31", "C32", "C33", "C34", "C41", "C44", "C51", "C54"}


def _client() -> AsyncClient:
    from app.main import app

    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


def _migrate_to_temp_db(tmp_path, monkeypatch) -> str:
    """Направить приложение на временную БД (путь и сессии)."""
    from app.core import config as config_module

    db_file = tmp_path / "colors.db"
    url = "sqlite+aiosqlite:///" + db_file.as_posix()
    monkeypatch.setattr(config_module.settings, "DATABASE_URL", url)
    return url


@pytest.fixture
async def colors_db(tmp_path, monkeypatch):
    """Временная база после ``alembic upgrade head``: 22 цвета из засева."""
    from app.db import session as session_module
    from app.db.startup import run_startup_migrations

    url = _migrate_to_temp_db(tmp_path, monkeypatch)
    await run_startup_migrations()

    engine = create_async_engine(url)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    monkeypatch.setattr(session_module, "async_session_maker", maker)

    yield maker

    await engine.dispose()


@pytest.fixture
async def empty_colors_db(tmp_path, monkeypatch):
    """Таблица цветов есть, строк нет: пустой справочник — не 404."""
    from app.db import session as session_module
    from app.db.base import Base
    from app.db.models import Color  # noqa: F401 — регистрирует таблицу в metadata

    url = _migrate_to_temp_db(tmp_path, monkeypatch)

    engine = create_async_engine(url)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    maker = async_sessionmaker(engine, expire_on_commit=False)
    monkeypatch.setattr(session_module, "async_session_maker", maker)

    yield maker

    await engine.dispose()


async def _get_colors() -> list[dict]:
    async with _client() as client:
        response = await client.get("/api/colors")
    assert response.status_code == 200, response.text
    return response.json()


async def _color_id(code: str) -> int:
    for color in await _get_colors():
        if color["code"] == code:
            return color["id"]
    raise AssertionError(f"в справочнике нет кода {code}")


async def _patch(color_id: int, payload: dict) -> tuple[int, dict]:
    async with _client() as client:
        response = await client.patch(f"/api/colors/{color_id}", json=payload)
    return response.status_code, response.json()


async def test_migration_seeds_full_color_dictionary(tmp_path, monkeypatch):
    """Миграция создаёт таблицу и засевает 22 цвета: названия, коды, hex."""
    import sqlite3

    from app.db.startup import run_startup_migrations

    _migrate_to_temp_db(tmp_path, monkeypatch)
    await run_startup_migrations()

    with sqlite3.connect(tmp_path / "colors.db") as conn:
        conn.row_factory = sqlite3.Row
        rows = [dict(row) for row in conn.execute("SELECT * FROM colors")]

    assert len(rows) == 22
    by_code = {row["code"]: row for row in rows if row["code"]}
    assert set(by_code) >= FAN_CODES

    # Приёмка 0022: C32 — тёмная шампань с непустым hex.
    assert by_code["C32"]["name"] == "Тёмная шампань"
    assert by_code["C32"]["hex"]

    # У локальных кодов кода нет только у старых названий; у RG/RB/RST есть.
    by_name = {row["name"]: row for row in rows}
    assert by_name["серебро"]["code"] is None
    for name, expected_code in (("Rose Gold", "RG"), ("Rose Bronze", "RB"), ("растрав", "RST")):
        assert by_name[name]["code"] == expected_code

    # Старые названия живут за старыми операциями KTM: синк найдёт их по ключу.
    assert by_name["серебро"]["operation_code"] == "ANOD_01"
    assert by_name["черный"]["operation_code"] == "ANOD_05"

    # Веер до первого синка — локальный, ключ синка равен коду.
    assert by_code["C32"]["source"] == "local"
    assert by_code["C32"]["operation_code"] == "C32"

    # Аббревиатура — подпись, привычная оператору: правило «первые буквы»
    # ломало бы «брз» и «рст», поэтому она приходит из засева.
    assert by_name["бронза"]["abbreviation"] == "брз"
    assert by_name["растрав"]["abbreviation"] == "рст"
    assert by_name["Rose Gold"]["abbreviation"] == "RG"
    assert by_code["C32"]["abbreviation"] == "C32"
    assert all(row["abbreviation"] for row in rows), "у каждой строки засева есть аббревиатура"


async def test_seed_has_old_updated_at_and_ktm_fan_hex(tmp_path, monkeypatch):
    """Засев не новее KTM: метка старая, hex веера совпадает с T-378."""
    import sqlite3

    from app.db.startup import run_startup_migrations

    _migrate_to_temp_db(tmp_path, monkeypatch)
    await run_startup_migrations()

    with sqlite3.connect(tmp_path / "colors.db") as conn:
        conn.row_factory = sqlite3.Row
        rows = [dict(row) for row in conn.execute("SELECT * FROM colors")]

    now = datetime.now(UTC)
    for row in rows:
        stamp = datetime.fromisoformat(row["updated_at"])
        if stamp.tzinfo is None:
            stamp = stamp.replace(tzinfo=UTC)
        # CURRENT_TIMESTAMP сделал бы засев новее KTM, и первый синк бы проиграл.
        assert stamp <= datetime(2000, 1, 1, tzinfo=UTC), row
        assert stamp < now, row

    by_code = {row["code"]: row for row in rows if row["code"]}
    assert by_code["C31"]["hex"] == "#CFD4D5"
    assert by_code["C32"]["hex"] == "#AEA895"


def _upgrade_db(url: str, revision: str) -> None:
    """Применить миграции до указанной ревизии на временной базе."""
    from alembic.config import Config

    from alembic import command

    backend_dir = Path(__file__).resolve().parents[2]
    cfg = Config()
    cfg.set_main_option("script_location", str(backend_dir / "alembic"))
    cfg.set_main_option("sqlalchemy.url", url)
    command.upgrade(cfg, revision)


def test_migration_005_fixes_only_untouched_seed_rows(tmp_path, monkeypatch):
    """На уже засеянной базе 005 меняет hex и метку, но не затирает правку."""
    import sqlite3

    url = _migrate_to_temp_db(tmp_path, monkeypatch)
    _upgrade_db(url, "004")

    db_file = tmp_path / "colors.db"
    with sqlite3.connect(db_file) as conn:
        # Так выглядит локальная правка после PATCH: updated_at ушёл от created_at.
        conn.execute("UPDATE colors SET hex = '#111111', updated_at = '2026-01-01 00:00:00' WHERE code = 'C31'")
        conn.commit()

    _upgrade_db(url, "head")

    with sqlite3.connect(db_file) as conn:
        conn.row_factory = sqlite3.Row
        rows = {row["code"]: dict(row) for row in conn.execute("SELECT * FROM colors") if row["code"]}

    assert rows["C32"]["hex"] == "#AEA895"
    assert rows["C32"]["updated_at"] == "2000-01-01 00:00:00.000000"
    assert rows["C31"]["hex"] == "#111111"
    assert rows["C31"]["updated_at"] == "2026-01-01 00:00:00"


async def test_repeated_startup_does_not_duplicate_seed(tmp_path, monkeypatch):
    """Повторный запуск миграций не плодит дубли в справочнике."""
    import sqlite3

    from app.db.startup import run_startup_migrations

    _migrate_to_temp_db(tmp_path, monkeypatch)
    await run_startup_migrations()
    await run_startup_migrations()

    with sqlite3.connect(tmp_path / "colors.db") as conn:
        count = conn.execute("SELECT COUNT(*) FROM colors").fetchone()[0]

    assert count == 22


async def test_colors_list_returns_whole_dictionary_without_db_fields(colors_db):
    """GET отдаёт 22 цвета с кодом, названием и hex; служебных полей нет."""
    listing = await _get_colors()

    assert len(listing) == 22
    for item in listing:
        assert set(item) == COLOR_FIELDS, item

    by_code = {item["code"]: item for item in listing if item["code"]}
    assert set(by_code) >= FAN_CODES
    assert by_code["C31"]["name"] == "Светлая шампань"
    assert by_code["C41"]["name"] == "Медь"
    assert by_code["C51"]["name"] == "Нержавеющая сталь"

    # Привычные подписи старых цветов не должны меняться: «брз» и «рст» из засева.
    by_name = {item["name"]: item for item in listing}
    assert by_name["бронза"]["abbreviation"] == "брз"
    assert by_name["растрав"]["abbreviation"] == "рст"

    # Стабильный порядок: коды идут по возрастанию, повторный запрос совпадает.
    codes = [item["code"] for item in listing if item["code"]]
    assert codes == sorted(codes)
    assert listing == await _get_colors()


async def test_colors_list_is_empty_array_for_empty_dictionary(empty_colors_db):
    """Пустой справочник — пустой массив, а не 404."""
    assert await _get_colors() == []


async def test_patch_updates_name_and_hex_but_keeps_sync_keys(colors_db):
    """PATCH меняет подпись цвета, но не code и не operation_code."""
    color_id = await _color_id("C32")
    before = next(item for item in await _get_colors() if item["id"] == color_id)

    status, updated = await _patch(color_id, {"name": "Тёмная шампань (правка)", "hex": "#123456"})

    assert status == 200, updated
    assert updated["name"] == "Тёмная шампань (правка)"
    assert updated["hex"] == "#123456"
    assert updated["abbreviation"] == before["abbreviation"]
    assert updated["code"] == before["code"]
    assert updated["operation_code"] == before["operation_code"]

    after = next(item for item in await _get_colors() if item["id"] == color_id)
    assert after["name"] == updated["name"]
    assert after["hex"] == updated["hex"]


async def test_patch_changes_only_the_field_that_was_sent(colors_db):
    """PATCH принимает name и hex по отдельности: второе поле не затирается."""
    color_id = await _color_id("C32")
    before = next(item for item in await _get_colors() if item["id"] == color_id)

    status, renamed = await _patch(color_id, {"name": "Шампань тёмная"})
    assert status == 200, renamed
    assert renamed["name"] == "Шампань тёмная"
    assert renamed["hex"] == before["hex"]

    status, recolored = await _patch(color_id, {"hex": "#AABBCC"})
    assert status == 200, recolored
    assert recolored["hex"] == "#AABBCC"
    assert recolored["name"] == "Шампань тёмная"


async def test_patch_updates_abbreviation(colors_db):
    """PATCH меняет привычную подпись, не трогая название и hex."""
    color_id = await _color_id("C32")
    before = next(item for item in await _get_colors() if item["id"] == color_id)

    status, updated = await _patch(color_id, {"abbreviation": "тш"})

    assert status == 200, updated
    assert updated["abbreviation"] == "тш"
    assert updated["name"] == before["name"]
    assert updated["hex"] == before["hex"]

    after = next(item for item in await _get_colors() if item["id"] == color_id)
    assert after["abbreviation"] == "тш"


async def test_patch_marks_color_local_and_moves_updated_at(colors_db):
    """Успешная правка ставит source=local и текущее UTC-время."""
    from datetime import timedelta

    from sqlalchemy import update

    from app.db.models import Color

    color_id = await _color_id("C32")
    old_stamp = datetime.now(UTC) - timedelta(days=30)

    # Строка пришла из KTM: следующий PATCH обязан снова сделать её локальной.
    async with colors_db() as session:
        await session.execute(update(Color).where(Color.id == color_id).values(source="ktm", updated_at=old_stamp))
        await session.commit()

    status, updated = await _patch(color_id, {"name": "Тёмная шампань"})

    assert status == 200, updated
    assert updated["source"] == "local"
    stamp = datetime.fromisoformat(updated["updated_at"])
    if stamp.tzinfo is None:
        stamp = stamp.replace(tzinfo=UTC)
    assert stamp > old_stamp
    assert abs((stamp - datetime.now(UTC)).total_seconds()) < 60


async def test_patch_reports_missing_color(colors_db):
    """Несуществующий id — 404, а не молчаливое создание."""
    status, _ = await _patch(999_999, {"name": "нет такого"})

    assert status == 404


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"name": None},
        {"name": ""},
        {"name": "   "},
        {"abbreviation": None},
        {"abbreviation": ""},
        {"abbreviation": "   "},
        {"abbreviation": "аббр" * 4 + "а"},
        {"hex": "123456"},
        {"hex": "#12345"},
        {"hex": "#GGGGGG"},
        {"hex": None},
    ],
)
async def test_patch_rejects_empty_or_invalid_body(colors_db, payload):
    """Пустое тело, пустое название и плохой hex — 422."""
    color_id = await _color_id("C32")

    status, _ = await _patch(color_id, payload)

    assert status == 422


@pytest.mark.parametrize("method", ["POST", "PUT", "DELETE"])
async def test_creating_and_deleting_colors_is_not_available(colors_db, method):
    """Создание и удаление цветов через API отсутствуют."""
    async with _client() as client:
        response = await client.request(method, "/api/colors/1")

    assert response.status_code in (404, 405)
