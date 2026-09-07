"""
Startup helpers for full mode (ADR 0002): data dirs + migrations.

- ensure_data_dirs(): создаёт каталог sqlite-файла и images при старте.
  Идемпотентно, dev/Docker не затрагивает (их пути уже существуют/заданы).
- run_startup_migrations(): `alembic upgrade head` в отдельном потоке
  (у alembic свой asyncio.run — в running loop его вызывать нельзя);
  если alembic недоступен или миграция упала — идемпотентный init_db()
  (Base.metadata.create_all) + stamp head для свежей БД без версии,
  чтобы бэкенд всё равно стартовал и не реплеил 001.
"""
import asyncio
import logging
from pathlib import Path

from app.core.config import settings

logger = logging.getLogger(__name__)


def ensure_data_dirs() -> None:
    """Создать каталог данных и images, если их нет."""
    settings.data_dir_path.mkdir(parents=True, exist_ok=True)
    settings.images_path.mkdir(parents=True, exist_ok=True)


def _make_alembic_config():
    """Alembic Config с абсолютными путями (без завязки на CWD)."""
    from alembic.config import Config

    backend_dir = Path(__file__).resolve().parents[2]
    cfg = Config()
    cfg.set_main_option("script_location", str(backend_dir / "alembic"))
    cfg.set_main_option("sqlalchemy.url", settings.DATABASE_URL)
    return cfg


def _alembic_upgrade_head() -> None:
    """Синхронный `alembic upgrade head` (свой loop — вызывать в потоке)."""
    from alembic import command

    command.upgrade(_make_alembic_config(), "head")


async def run_startup_migrations() -> None:
    """Применить миграции при старте; фолбэк — идемпотентный init_db()."""
    try:
        await asyncio.to_thread(_alembic_upgrade_head)
        logger.info("[STARTUP] Alembic migrations applied (head)")
    except ImportError:
        logger.warning("[STARTUP] Alembic not installed, using init_db() instead")
        await _init_db_fallback()
    except Exception as e:
        logger.error(f"[STARTUP] Alembic upgrade failed ({e}); using init_db() fallback")
        await _init_db_fallback()

async def _init_db_fallback() -> None:
    # Свежий engine из ТЕКУЩЕГО settings (import-time engine в base.py
    # защёлкнул URL при импорте и может указывать на другую базу).
    from sqlalchemy import inspect
    from sqlalchemy.ext.asyncio import create_async_engine

    from app.db.base import Base

    engine = create_async_engine(settings.DATABASE_URL, echo=False, future=True)
    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
            has_version = await conn.run_sync(
                lambda c: "alembic_version" in inspect(c).get_table_names()
            )
        if not has_version:
            # Свежая БД без версии вечно реплеила бы 001 и глушила будущие
            # миграции — штампуем head. Чужая версия (частичный upgrade):
            # не врём, оставляем как есть.
            await _stamp_head()
    finally:
        await engine.dispose()
    logger.info("[STARTUP] Database initialized via init_db()")


async def _stamp_head() -> None:
    """Отметить БД как head без применения миграций (только для свежей БД)."""
    try:
        from alembic import command

        await asyncio.to_thread(command.stamp, _make_alembic_config(), "head")
        logger.info("[STARTUP] Database stamped to alembic head")
    except ImportError:
        logger.warning("[STARTUP] Alembic not installed, skipping stamp")
    except Exception as e:
        logger.warning(f"[STARTUP] Alembic stamp failed ({e}), continuing unstamped")
