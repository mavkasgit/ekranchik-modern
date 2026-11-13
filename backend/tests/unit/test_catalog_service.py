"""Каталог профилей: ответ считает версию фото по файлу на диске.

Контракт под тестом: файл фото могли заменить мимо приложения (синк
каталога, ручное копирование в storage), а браузер и nginx держат
``/static/`` в долгом кэше. Поэтому версия в ответе каталога считается из
``mtime`` и размера файла, а не запоминается в БД при загрузке.
"""

import os

import pytest

from app.core.config import settings
from app.db.models import Profile
from app.services.catalog_service import catalog_service


@pytest.fixture
def images_dir(tmp_path, monkeypatch):
    path = tmp_path / "images"
    path.mkdir()
    monkeypatch.setattr(settings, "IMAGES_DIR", str(path))
    return path


async def test_profile_response_version_follows_file_on_disk(images_dir, db_session):
    """Версия в ответе каталога меняется вместе с файлом, а не с записью в БД."""
    (images_dir / "1010-thumb.jpg").write_bytes(b"thumb")
    (images_dir / "1010.jpg").write_bytes(b"full")
    db_session.add(
        Profile(name="1010", photo_thumb="images/1010-thumb.jpg", photo_full="images/1010.jpg")
    )
    await db_session.flush()

    before = await catalog_service.get_profile("1010", session=db_session)
    assert before is not None
    assert before.photo_full_version is not None
    assert before.photo_thumb_version is not None

    full = images_dir / "1010.jpg"
    os.utime(full, ns=(1_700_000_000_000_000_000, 1_700_000_000_000_000_000))

    after = await catalog_service.get_profile("1010", session=db_session)
    assert after is not None
    assert after.photo_full_version != before.photo_full_version

    listed = await catalog_service.get_all_profiles(session=db_session)
    assert listed[0].photo_full_version == after.photo_full_version


async def test_profile_response_has_no_version_for_missing_photo(images_dir, db_session):
    """Фото нет на диске — версии нет, ответ при этом не падает."""
    db_session.add(Profile(name="2020", photo_thumb="images/2020-thumb.jpg", photo_full="images/2020.jpg"))
    await db_session.flush()

    profile = await catalog_service.get_profile("2020", session=db_session)

    assert profile is not None
    assert profile.photo_thumb_version is None
    assert profile.photo_full_version is None
