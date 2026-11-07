"""
Pytest configuration and fixtures
"""

import sys
from pathlib import Path

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

# Add backend to path for imports
backend_path = Path(__file__).parent.parent
sys.path.insert(0, str(backend_path))

from app.db.base import Base


@pytest.fixture(autouse=True)
def _disable_excel_backup(monkeypatch):
    """Выключить фоновый автобэкап книги во всех тестах.

    Тест, открывший ``TestClient`` через ``with``, поднимает ``lifespan``:
    боевая шара на машине разработчика существует, и включённая задача
    сняла бы настоящую копию книги. Правило расписания проверяется отдельно,
    на ``tmp_path``.
    """
    from app.core.config import settings

    monkeypatch.setattr(settings, "EXCEL_BACKUP_ENABLED", False)


@pytest_asyncio.fixture
async def db_session():
    """Create a test database session."""
    # Use in-memory SQLite for tests
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)

    # Create tables
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    # Create session
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with async_session() as session:
        yield session

    await engine.dispose()
