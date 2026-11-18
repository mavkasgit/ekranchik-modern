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


async def test_search_profiles_matches_description(images_dir, db_session):
    """Наименование участвует в поиске наравне с артикулом и примечанием."""
    db_session.add(Profile(name="АРТ-100", description="Крючок латунный"))
    await db_session.flush()

    results = await catalog_service.search_profiles("латун", session=db_session)

    assert [result.name for result in results] == ["АРТ-100"]
    assert results[0].match_priority == 3


async def test_search_profiles_breaks_ties_by_name_not_usage_count(images_dir, db_session):
    """Одинаковый приоритет сортируется по артикулу: usage_count мёртв и не решает."""
    db_session.add(Profile(name="ЮП-200", quantity_per_hanger=1, usage_count=100))
    db_session.add(Profile(name="ЮП-100", quantity_per_hanger=1, usage_count=0))
    await db_session.flush()

    results = await catalog_service.search_profiles("юп", session=db_session)

    assert [result.name for result in results] == ["ЮП-100", "ЮП-200"]


async def test_photo_lookup_finds_article_with_size_note(images_dir, db_session):
    """Размер рядом с артикулом не мешает фото: «ЮП-2083 2,75 метра» → «ЮП-2083».

    В книге учёта размер пишут в той же ячейке, что и артикул. Каталог хранит
    артикул без размера, поэтому фото искалось по полной строке и не находилось:
    дашборд показывал заглушку вместо снимка профиля.
    """
    (images_dir / "ЮП-2083-thumb.jpg").write_bytes(b"thumb")
    db_session.add(
        Profile(
            name="ЮП-2083",
            photo_thumb="images/ЮП-2083-thumb.jpg",
            photo_full="images/ЮП-2083.jpg",
        )
    )
    await db_session.flush()

    photos = await catalog_service.get_profiles_photos_batch(
        ["ЮП-2083 2,75 метра", "ЮП-2083 1,8 метра"], session=db_session
    )

    assert set(photos) == {"ЮП-2083 2,75 метра", "ЮП-2083 1,8 метра"}
    assert {photo["name"] for photo in photos.values()} == {"ЮП-2083"}


async def test_photo_lookup_prefers_exact_multiword_name(images_dir, db_session):
    """Артикул с пробелом находится целиком: запасной путь по слову его не подменяет."""
    (images_dir / "Кр.труба-10мм-thumb.jpg").write_bytes(b"thumb")
    db_session.add(
        Profile(
            name="Кр.труба 10мм",
            photo_thumb="images/Кр.труба-10мм-thumb.jpg",
            photo_full="images/Кр.труба-10мм.jpg",
        )
    )
    await db_session.flush()

    photos = await catalog_service.get_profiles_photos_batch(["Кр.труба 10мм"], session=db_session)

    assert photos["Кр.труба 10мм"]["name"] == "Кр.труба 10мм"


async def test_photo_lookup_real_book_cells(images_dir, db_session):
    """Живые написания ячейки «Профиль»: размер и пометки не мешают артикулу."""
    articles = ["ЮП-1880", "ЮП-2083", "ЮП-1401", "ЮП-2900"]
    for article in articles:
        (images_dir / f"{article}-thumb.jpg").write_bytes(b"thumb")
        db_session.add(
            Profile(
                name=article,
                photo_thumb=f"images/{article}-thumb.jpg",
                photo_full=f"images/{article}.jpg",
            )
        )
    await db_session.flush()

    cells = {
        "ЮП-1880 2.5м": "ЮП-1880",
        "ЮП-2083 (1.8)": "ЮП-2083",
        "ЮП-2083 2,75 метра": "ЮП-2083",
        "юп-2083 1,85м": "ЮП-2083",
        "ЮП-1401 (3.05м)": "ЮП-1401",
        "ЮП-2900 окно (381)": "ЮП-2900",
    }
    photos = await catalog_service.get_profiles_photos_batch(list(cells), session=db_session)

    assert {cell: photos[cell]["name"] for cell in cells} == cells


async def test_photo_lookup_finds_article_after_length_is_removed(images_dir, db_session):
    """Длина ушла из имени (ADR 0012) — фото ищется по чистому артикулу.

    Многословный артикул доказывает именно точное совпадение: у
    ``Профиль RE7444 3м`` после снятия длины имя ровно ``Профиль RE7444``, а
    запасной проход по ведущему слову ``Профиль`` не нашёл бы ничего. Остальные
    ячейки — реальные записи книги; они подтверждают, что длина не мешает
    поиску, но не все проходят именно точной ступенью.
    """
    (images_dir / "ЮП-2083-thumb.jpg").write_bytes(b"thumb")
    db_session.add(
        Profile(
            name="ЮП-2083",
            photo_thumb="images/ЮП-2083-thumb.jpg",
            photo_full="images/ЮП-2083.jpg",
        )
    )
    (images_dir / "RE7444-thumb.jpg").write_bytes(b"thumb")
    db_session.add(
        Profile(
            name="Профиль RE7444",
            photo_thumb="images/RE7444-thumb.jpg",
            photo_full="images/RE7444.jpg",
        )
    )
    await db_session.flush()

    cells = {
        "ЮП-2083 2,75 метра": "ЮП-2083",
        "ЮП-2083(1.8м)": "ЮП-2083",
        "профиль ЮП-2083 (2.7)": "ЮП-2083",
        "Профиль RE7444 3м": "Профиль RE7444",
    }
    photos = await catalog_service.get_profiles_photos_batch(list(cells), session=db_session)

    assert {cell: photos[cell]["name"] for cell in cells} == cells


async def test_photo_lookup_keeps_fallback_for_other_tails(images_dir, db_session):
    """Запасной проход остаётся: «381 (ЮП-2900 окно)» — артикул «381».

    Ячейка начинается с номера, а не с артикула: после снятия обработки
    («окно») и длины имя не совпадает с каталогом, и фото находит только
    поиск по ведущему слову.
    """
    (images_dir / "381-thumb.jpg").write_bytes(b"thumb")
    db_session.add(
        Profile(name="381", photo_thumb="images/381-thumb.jpg", photo_full="images/381.jpg")
    )
    await db_session.flush()

    photos = await catalog_service.get_profiles_photos_batch(
        ["381 (ЮП-2900 окно)"], session=db_session
    )

    assert photos["381 (ЮП-2900 окно)"]["name"] == "381"
