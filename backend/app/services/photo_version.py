"""Версия файла фото для cache-busting URL.

Фото профилей лежат в ``settings.images_path`` и отдаются по стабильному
``/static/images/<файл>``, а nginx ставит на ``/static/`` долгий
``Cache-Control: immutable``. ``updated_at`` профиля меняется только при
записи через API: файл, заменённый мимо (синк каталога, ручное копирование
в storage), оставался бы в кэше браузера и nginx со старым URL. Поэтому URL
конкретного фото получает ``?v=<версия>``, а версия считается из файла при
сериализации ответа, а не запоминается в БД при загрузке.

``mtime_ns + size`` — дешёвая пара без чтения содержимого: списки профилей
сериализуются часто, а хэш каждого файла на каждый запрос был бы дороже
самого ответа. Ограничение известно и принято: замена с сохранением и mtime,
и размера версию не сдвинет.
"""

from __future__ import annotations

import logging
import re
import stat as stat_module
from collections.abc import Iterable
from pathlib import Path
from typing import NamedTuple

from app.core.config import settings

logger = logging.getLogger(__name__)

_WINDOWS_ABSOLUTE = re.compile(r"^[A-Za-z]:/")


class PhotoVersions(NamedTuple):
    """Версии пары фото одного профиля: превью и основной файл."""

    thumb: str | None
    full: str | None


def _resolve_image_path(path: str) -> Path | None:
    """Путь файла внутри ``images_path`` или ``None`` для недопустимого пути.

    Путь в БД — внешние данные: он мог остаться от старой версии, быть
    поправленным вручную или прийти из импортированной базы. Допустимы только
    два вида: ``images/<файл>`` и старый ``/static/images/<файл>``. Прочий
    абсолютный путь (``C:\\...``, ``/app/...``) не резолвится: он зависит от
    машины/контейнера и может указать мимо корня. ``..`` и выход за ``images``
    отсекаются до ``stat``.
    """
    raw = path.strip().replace("\\", "/")
    if not raw or "://" in raw:
        # Внешний URL — не файл storage. Его версию источник не отдаёт.
        return None

    if _WINDOWS_ABSOLUTE.match(raw):
        logger.warning("photo path is absolute, expected images-relative path: %r", path)
        return None

    if raw.startswith("/static/"):
        relative_text = raw[len("/static/") :]
    elif raw.startswith("/images/"):
        relative_text = raw[1:]
    elif raw.startswith("/"):
        logger.warning("photo path is absolute, expected images-relative path: %r", path)
        return None
    elif raw.startswith("static/"):
        relative_text = raw[len("static/") :]
    else:
        relative_text = raw

    relative = Path(relative_text)
    if relative.is_absolute() or any(part == ".." for part in relative.parts):
        logger.warning("photo path escapes images root: %r", path)
        return None

    images_root = settings.images_path.resolve()
    candidate = (settings.images_path.parent / relative).resolve()
    if not candidate.is_relative_to(images_root):
        logger.warning("photo path escapes images root: %r", path)
        return None
    return candidate


def photo_file_version(path: str | None) -> str | None:
    """Версия файла фото или ``None``, если пути нет или файл недоступен.

    Версия — ``mtime_ns-size`` в hex, чтобы URL оставался коротким.
    """
    if not path:
        return None

    candidate = _resolve_image_path(path)
    if candidate is None:
        return None

    try:
        file_stat = candidate.stat()
    except OSError as exc:
        # Отдельного 500 из-за отсутствующей картинки быть не должно: фронт
        # просто не добавит `?v=`. Это штатная ситуация (фото ещё не
        # загружено/удалено), поэтому только debug: предупреждение на каждый
        # файл в каждом списке — шум.
        logger.debug("photo file is unavailable: path=%r (%s)", path, exc)
        return None

    if not stat_module.S_ISREG(file_stat.st_mode):
        logger.debug("photo path is not a regular file: path=%r", path)
        return None

    return f"{file_stat.st_mtime_ns:x}-{file_stat.st_size:x}"


def photo_versions_for(thumb: str | None, full: str | None) -> PhotoVersions:
    """Версии пары ``(thumb, full)`` одного профиля."""
    return PhotoVersions(photo_file_version(thumb), photo_file_version(full))


def photo_file_versions(
    pairs: Iterable[tuple[str | None, str | None]],
) -> list[PhotoVersions]:
    """Версии для пар ``(thumb_path, full_path)`` одним вызовом.

    Синхронная функция: route-слой зовёт её через ``asyncio.to_thread``, чтобы
    ``stat`` не блокировал event loop. Для списка это один переход в поток на
    весь ответ, а не по два ``stat`` на каждый профиль в цикле.
    """
    return [photo_versions_for(thumb, full) for thumb, full in pairs]
