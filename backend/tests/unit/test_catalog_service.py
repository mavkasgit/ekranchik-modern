"""Каталог профилей: файлы фото на диске.

Контракт под тестом: имя профиля приходит снаружи (адрес запроса, книга
учёта), поэтому оно не должно выводить запись файла за каталог images;
повторная загрузка фото заменяет файл, а не удаляет его как «старый».
"""

import io

import pytest
from PIL import Image

from app.core.config import settings
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
