"""Полный режим (ADR 0002, issue #5): разрешение путей данных, EKRANCHIK_*,
каталоги и миграции при старте."""
import sqlite3

import pytest

from app.core import config as config_module
from app.core.config import Settings


@pytest.fixture()
def clean_env(monkeypatch):
    for name in (
        "DATABASE_URL", "IMAGES_DIR", "STATIC_DIR", "FRONTEND_DIST_DIR",
        "SIMULATION_ENABLED", "OPCUA_ENDPOINT", "EXCEL_REAL_FILE_PATH",
        "LOCALAPPDATA", "EKRANCHIK_DATA_DIR", "EKRANCHIK_EXCEL_PATH",
        "EKRANCHIK_OPCUA_ENDPOINT", "EKRANCHIK_SIMULATION",
    ):
        monkeypatch.delenv(name, raising=False)


def test_localappdata_is_default_data_home(clean_env, monkeypatch):
    monkeypatch.setenv("LOCALAPPDATA", r"C:\Users\op\AppData\Local")
    s = Settings(_env_file=None)
    assert s.DATABASE_URL == (
        "sqlite+aiosqlite:///C:/Users/op/AppData/Local/Ekranchik/data/ekranchik.db"
    )
    assert s.IMAGES_DIR == r"C:\Users\op\AppData\Local\Ekranchik\data\images".replace("\\", "/")
    assert s.data_dir_path.name == "data"


def test_explicit_database_url_and_images_win(clean_env, monkeypatch):
    """Docker/compose и dev-.env не ломаются: явные значения всегда win."""
    monkeypatch.setenv("LOCALAPPDATA", r"C:\Users\op\AppData\Local")
    monkeypatch.setenv("DATABASE_URL", "sqlite+aiosqlite:////app/static/ekranchik.db")
    monkeypatch.setenv("IMAGES_DIR", "/app/static/images")
    s = Settings(_env_file=None)
    assert s.DATABASE_URL == "sqlite+aiosqlite:////app/static/ekranchik.db"
    assert s.IMAGES_DIR == "/app/static/images"


def test_ekranchik_data_dir_override(clean_env, monkeypatch):
    monkeypatch.setenv("LOCALAPPDATA", r"C:\Users\op\AppData\Local")
    monkeypatch.setenv("EKRANCHIK_DATA_DIR", "D:/factory/ekranchik-data")
    s = Settings(_env_file=None)
    assert s.DATABASE_URL == "sqlite+aiosqlite:///D:/factory/ekranchik-data/ekranchik.db"
    assert s.IMAGES_DIR == "D:/factory/ekranchik-data/images"


def test_no_localappdata_keeps_dev_defaults(clean_env):
    s = Settings(_env_file=None)
    assert s.DATABASE_URL == "sqlite+aiosqlite:///./data/ekranchik.db"
    assert s.IMAGES_DIR == "../static/images"


def test_ekranchik_aliases_apply_with_factory_defaults(clean_env, monkeypatch):
    monkeypatch.setenv("EKRANCHIK_EXCEL_PATH", r"D:\share\Учет КПЗ 2026.xlsm")
    monkeypatch.setenv("EKRANCHIK_OPCUA_ENDPOINT", "opc.tcp://10.0.0.5:4840/")
    monkeypatch.setenv("EKRANCHIK_SIMULATION", "true")
    s = Settings(_env_file=None)
    assert s.EXCEL_REAL_FILE_PATH == r"D:\share\Учет КПЗ 2026.xlsm"
    assert s.OPCUA_ENDPOINT == "opc.tcp://10.0.0.5:4840/"
    assert s.SIMULATION_ENABLED is True
    assert s.excel_path is not None


def test_bare_names_win_over_ekranchik_aliases(clean_env, monkeypatch):
    monkeypatch.setenv("EXCEL_REAL_FILE_PATH", "/app/excel/Учет КПЗ 2026.xlsm")
    monkeypatch.setenv("OPCUA_ENDPOINT", "opc.tcp://172.17.11.115:4840/")
    monkeypatch.setenv("SIMULATION_ENABLED", "false")
    monkeypatch.setenv("EKRANCHIK_EXCEL_PATH", r"D:\other\file.xlsm")
    monkeypatch.setenv("EKRANCHIK_OPCUA_ENDPOINT", "opc.tcp://10.0.0.5:4840/")
    monkeypatch.setenv("EKRANCHIK_SIMULATION", "true")
    s = Settings(_env_file=None)
    assert s.EXCEL_REAL_FILE_PATH == "/app/excel/Учет КПЗ 2026.xlsm"
    assert s.OPCUA_ENDPOINT == "opc.tcp://172.17.11.115:4840/"
    assert s.SIMULATION_ENABLED is False


def test_ensure_data_dirs_creates_tree(clean_env, tmp_path, monkeypatch):
    from app.db import startup

    db_file = tmp_path / "sub" / "ekranchik.db"
    monkeypatch.setattr(
        config_module.settings, "DATABASE_URL",
        "sqlite+aiosqlite:///" + db_file.as_posix(),
    )
    monkeypatch.setattr(
        config_module.settings, "IMAGES_DIR",
        (tmp_path / "sub" / "images").as_posix(),
    )
    startup.ensure_data_dirs()
    assert db_file.parent.is_dir()
    assert (tmp_path / "sub" / "images").is_dir()
    # Идемпотентно: повторный вызов не падает.
    startup.ensure_data_dirs()


def _db_heads():
    """Актуальные head-ревизии alembic (без пина конкретной ревизии)."""
    from alembic.script import ScriptDirectory

    from app.db import startup

    return set(ScriptDirectory.from_config(startup._make_alembic_config()).get_heads())


@pytest.mark.asyncio()
async def test_startup_migrations_apply_alembic_head(clean_env, tmp_path, monkeypatch):
    """Миграции при старте доводят пустой sqlite до head, таблицы по контракту."""
    from app.db import startup

    db_file = tmp_path / "pkg.db"
    monkeypatch.setattr(
        config_module.settings, "DATABASE_URL",
        "sqlite+aiosqlite:///" + db_file.as_posix(),
    )
    monkeypatch.setattr(
        config_module.settings, "IMAGES_DIR",
        (tmp_path / "images").as_posix(),
    )
    startup.ensure_data_dirs()
    await startup.run_startup_migrations()

    with sqlite3.connect(db_file) as conn:
        tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        assert "profiles" in tables
        version = conn.execute("SELECT version_num FROM alembic_version").fetchone()[0]
        assert version, "alembic_version пуста после upgrade head"
        assert version in _db_heads(), f"{version} не head"


@pytest.mark.asyncio()
async def test_startup_migrations_fallback_to_init_db(clean_env, tmp_path, monkeypatch):
    """Упавший alembic не роняет старт: init через create_all + stamp head."""
    from app.db import startup

    db_file = tmp_path / "fallback.db"
    monkeypatch.setattr(
        config_module.settings, "DATABASE_URL",
        "sqlite+aiosqlite:///" + db_file.as_posix(),
    )
    monkeypatch.setattr(
        config_module.settings, "IMAGES_DIR",
        (tmp_path / "images").as_posix(),
    )
    monkeypatch.setattr(startup, "_alembic_upgrade_head", lambda: (_ for _ in ()).throw(RuntimeError("no alembic")))
    startup.ensure_data_dirs()
    await startup.run_startup_migrations()

    with sqlite3.connect(db_file) as conn:
        tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        assert "profiles" in tables
        version = conn.execute("SELECT version_num FROM alembic_version").fetchone()[0]
        assert version, "свежая БД без stamp вечно реплеила бы 001"
        assert version in _db_heads(), f"{version} не head"
