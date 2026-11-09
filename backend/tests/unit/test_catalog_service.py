"""Каталог профилей: файлы фото на диске.

Контракт под тестом: имя профиля приходит снаружи (адрес запроса, книга
учёта), поэтому оно не должно выводить запись файла за каталог images;
повторная загрузка фото заменяет файл, а не удаляет его как «старый».
"""

import io
import os
from datetime import UTC, datetime
from pathlib import Path

import pytest
from PIL import Image
from sqlalchemy import select

from app.core.config import settings
from app.db.models import Profile
from app.services.catalog_service import (
    _FORBIDDEN_FILENAME_CHARS,
    _RESERVED_FILENAME_STEMS,
    _photo_file_stem,
    catalog_service,
)


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
    stem = _photo_file_stem("1010")
    await catalog_service.upload_photo("1010", _jpeg(), "first.jpg", session=db_session)
    full = images_dir / f"{stem}.jpg"
    thumb = images_dir / f"{stem}-thumb.jpg"
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
    profile_name = "..\\..\\evil/1010"
    _, full = await catalog_service.upload_photo(profile_name, _jpeg(), "photo.jpg", session=db_session)

    assert full == f"images/{_photo_file_stem(profile_name)}.jpg"
    assert "/" not in Path(full).name and "\\" not in Path(full).name
    saved = (images_dir / Path(full).name).resolve()
    assert saved.is_relative_to(images_dir.resolve())
    assert saved.exists()
    assert not (tmp_path / "evil").exists()
    assert not (tmp_path / ".._.._evil_1010.jpg").exists()


async def test_slash_between_articles_gets_a_safe_photo_name(images_dir, db_session):
    """Профиль из двух артикулов через ``/`` тоже может иметь фото."""
    _, full = await catalog_service.upload_photo("2020/1010", _jpeg(), "photo.jpg", session=db_session)

    assert full == f"images/{_photo_file_stem('2020/1010')}.jpg"
    assert (images_dir / Path(full).name).exists()


async def test_colliding_sanitized_names_keep_their_own_photos(images_dir, db_session):
    """``A/B`` и ``A_B`` дают разные файлы: одно фото не затирает другое."""
    red, green = _jpeg((192, 0, 0)), _jpeg((0, 160, 0))
    _, full_a = await catalog_service.upload_photo("A/B", red, "a.jpg", session=db_session)
    _, full_b = await catalog_service.upload_photo("A_B", green, "b.jpg", session=db_session)

    assert full_a != full_b
    assert (images_dir / Path(full_a).name).read_bytes() == red
    assert (images_dir / Path(full_b).name).read_bytes() == green


async def test_reserved_and_long_names_stay_inside_images(images_dir, db_session):
    """Зарезервированные и слишком длинные имена не ломают запись файла."""
    for profile_name in ("CON", "..", "x" * 200):
        _, full = await catalog_service.upload_photo(
            profile_name, _jpeg(), "photo.jpg", session=db_session
        )
        saved = (images_dir / Path(full).name).resolve()
        assert saved.is_relative_to(images_dir.resolve()), profile_name
        assert saved.exists(), profile_name


def test_photo_stem_is_unique_for_sanitized_names():
    """Разные имена не сливаются в один файл после замены запрещённых символов."""
    assert _photo_file_stem("A/B") != _photo_file_stem("A_B")
    assert _photo_file_stem("A/B") != _photo_file_stem("A\\B")
    assert _photo_file_stem("Test") != _photo_file_stem("test")


def test_photo_stem_is_bounded_and_has_no_trailing_dot_or_space():
    """Хвостовые точка/пробел убираются, длина не упирается в лимит ФС."""
    long_stem = _photo_file_stem("x" * 300)
    assert len(long_stem) <= 100
    assert len(f"{long_stem}-thumb.jpg") < 255

    for name in ("name.", "name ", ".", "..", ""):
        stem = _photo_file_stem(name)
        assert stem and stem not in {".", ".."}
        assert not stem.endswith((" ", "."))
        assert not any(char in _FORBIDDEN_FILENAME_CHARS for char in stem)


def test_photo_stem_avoids_windows_reserved_names():
    """CON/NUL/COM1 не остаются именем файла: Windows такое не создаёт."""
    for name in ("CON", "con", "NUL", "COM1", "LPT9"):
        stem = _photo_file_stem(name)
        assert stem.upper() not in _RESERVED_FILENAME_STEMS
        assert stem != name


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


def test_same_photo_file_is_not_crashed_by_missing_file(tmp_path):
    """``samefile`` на пропавшем старом файле — не исключение, а «разные»."""
    existing = tmp_path / "existing.jpg"
    existing.write_bytes(b"photo")
    missing = tmp_path / "missing.jpg"

    assert catalog_service._same_photo_file(existing, missing) is False
    assert catalog_service._same_photo_file(missing, missing) is True


async def test_delete_profile_does_not_delete_outside_images(images_dir, db_session, tmp_path):
    """Путь из БД с ``..`` не удаляет файл за пределами каталога images."""
    outside = tmp_path.parent / f"outside-{tmp_path.name}.jpg"
    outside.write_bytes(b"keep")
    profile = Profile(name="outside", photo_thumb=None, photo_full="../" + outside.name)
    db_session.add(profile)
    await db_session.flush()

    assert await catalog_service.delete_profile(profile.id, session=db_session)

    assert outside.exists(), "файл за пределами images не должен удаляться"


@pytest.mark.skipif(
    os.path.normcase("A") != os.path.normcase("a"),
    reason="регистр в путях различается только на NTFS/CIFS",
)
async def test_repeated_upload_with_case_different_db_path_keeps_new_photo(
    images_dir, db_session, monkeypatch
):
    """Путь из БД в другом регистре — тот же файл, а не «старый».

    ``Path.resolve`` на NTFS сам приводит регистр к фактическому, поэтому
    подменяем его на «сохраняющий регистр»: так ведёт себя не каждая
    сетевая шара. Проверяется именно сравнение файлов, а не удача NTFS.
    """
    stem = _photo_file_stem("CasePhoto")
    await catalog_service.upload_photo("CasePhoto", _jpeg(), "first.jpg", session=db_session)
    row = (await db_session.execute(select(Profile).where(Profile.name == "CasePhoto"))).scalar_one()
    row.photo_thumb = f"images/{stem.lower()}-thumb.jpg"
    row.photo_full = f"images/{stem.lower()}.jpg"
    await db_session.flush()

    monkeypatch.setattr(Path, "resolve", lambda self, *args, **kwargs: Path(os.path.abspath(self)))

    await catalog_service.upload_photo("CasePhoto", _jpeg((0, 160, 0)), "second.jpg", session=db_session)

    assert (images_dir / f"{stem}.jpg").exists()
    assert (images_dir / f"{stem}.jpg").read_bytes() == _jpeg((0, 160, 0))
