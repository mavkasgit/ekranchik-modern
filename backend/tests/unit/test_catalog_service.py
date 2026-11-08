"""Каталог профилей: файлы фото на диске.

Контракт под тестом: имя профиля приходит снаружи (адрес запроса, книга
учёта), поэтому оно не должно выводить запись файла за каталог images;
повторная загрузка фото заменяет файл, а не удаляет его как «старый».
"""

import io
from datetime import UTC, datetime

import pytest
from PIL import Image
from sqlalchemy import select

from app.core.config import settings
from app.db.models import Profile
from app.services.catalog_service import catalog_service


def _jpeg(color: tuple[int, int, int] = (192, 0, 0)) -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (32, 32), color).save(buffer, format="JPEG")
    return buffer.getvalue()


@pytest.fixture
def images_dir(tmp_path, monkeypatch):
    path = tmp_path / "images"
    monkeypatch.setattr(settings, "IMAGES_DIR", str(path))
    return path


async def test_repeated_upload_keeps_the_new_photo(images_dir, db_session):
    """Вторая загрузка заменяет фото, а не стирает только что записанное."""
    await catalog_service.upload_photo("1010", _jpeg(), "first.jpg", session=db_session)
    full = images_dir / "1010.jpg"
    thumb = images_dir / "1010-thumb.jpg"
    assert full.exists() and thumb.exists()

    await catalog_service.upload_photo("1010", _jpeg((0, 160, 0)), "second.jpg", session=db_session)

    assert full.exists(), "старый файл совпал с новым и был удалён"
    assert thumb.exists(), "новый эскиз не должен удаляться как старый"
    assert full.read_bytes() == _jpeg((0, 160, 0))


async def test_repeated_upload_refreshes_photo_version(images_dir, db_session):
    """Повторная загрузка двигает updated_at — по нему сбрасывается кэш фото.

    Путь к файлу при повторной загрузке тот же, поэтому без явной метки
    SQLAlchemy не увидела бы изменений и браузер показал бы старое фото.
    """
    await catalog_service.upload_photo("1010", _jpeg(), "first.jpg", session=db_session)
    row = (await db_session.execute(select(Profile).where(Profile.name == "1010"))).scalar_one()
    row.updated_at = datetime(2020, 1, 1, tzinfo=UTC)
    await db_session.flush()

    await catalog_service.upload_photo("1010", _jpeg((0, 160, 0)), "second.jpg", session=db_session)
    await db_session.refresh(row)

    assert row.updated_at.year >= 2026


async def test_separators_in_profile_name_do_not_escape_images_dir(images_dir, db_session, tmp_path):
    """Имя профиля с ``\\`` или ``/`` не пишет файл за пределы images.

    Имя приходит из адреса запроса; ``..\\\\..\\\\evil`` в нём раньше
    означал путь за каталогом фото, то есть запись файла в чужое место.
    Теперь разделители заменяются, а файл остаётся внутри images.
    """
    _, full = await catalog_service.upload_photo(
        "..\\..\\evil/1010", _jpeg(), "photo.jpg", session=db_session
    )

    assert full == "images/.._.._evil_1010.jpg"
    assert (images_dir / ".._.._evil_1010.jpg").exists()
    assert not (tmp_path / "evil").exists()
    assert not (tmp_path / ".._.._evil_1010.jpg").exists()


async def test_slash_between_articles_gets_a_safe_photo_name(images_dir, db_session):
    """Профиль из двух артикулов через ``/`` тоже может иметь фото."""
    _, full = await catalog_service.upload_photo("2020/1010", _jpeg(), "photo.jpg", session=db_session)

    assert full == "images/2020_1010.jpg"
    assert (images_dir / "2020_1010.jpg").exists()


async def test_delete_profile_removes_legacy_photo_paths(images_dir, db_session):
    """Старый путь «/static/images/…» при удалении профиля тоже удаляется.

    Остальные операции с фото давно нормализуют путь из БД, а удаление
    профиля брало его как есть: файл оставался на диске сиротой.
    """
    images_dir.mkdir()
    legacy_thumb = images_dir / "legacy-thumb.jpg"
    legacy_full = images_dir / "legacy.jpg"
    legacy_thumb.write_bytes(b"thumb")
    legacy_full.write_bytes(b"full")
    profile = Profile(
        name="legacy",
        photo_thumb="/static/images/legacy-thumb.jpg",
        photo_full="images/legacy.jpg",
    )
    db_session.add(profile)
    await db_session.flush()

    assert await catalog_service.delete_profile(profile.id, session=db_session)

    assert not legacy_thumb.exists()
    assert not legacy_full.exists()
