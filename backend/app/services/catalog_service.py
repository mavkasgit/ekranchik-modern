"""
Catalog Service - read-only catalog showcase and the local profile note.

Данные артикула принадлежат каталогу-источнику (спека 0002, ADR 0010):
сервис читает профили, ищет их и обновляет одно примечание. Помощники
записи фото остаются мёртвыми до выпила (тикет 0019).
"""

import asyncio
import hashlib
import io
import logging
import os
import re
from pathlib import Path

from PIL import Image
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.text_utils import normalize_text
from app.db.models import Profile
from app.db.session import get_session
from app.schemas.profile import ProfileResponse, ProfileSearchResult
from app.services.photo_version import photo_file_versions
from app.services.profile_name import parse_profile

logger = logging.getLogger(__name__)

# Символы, запрещённые в именах файлов Windows. Имя файла фото строится из
# имени профиля, а оно приходит снаружи: из адреса запроса и из книги учёта.
_FORBIDDEN_FILENAME_CHARS = '<>:"/\\|?*'

# Имена, которые Windows не разрешает использовать даже с расширением.
_RESERVED_FILENAME_STEMS = {
    "CON",
    "PRN",
    "AUX",
    "NUL",
    *(f"COM{number}" for number in range(1, 10)),
    *(f"LPT{number}" for number in range(1, 10)),
}

# Запас под ``-thumb.jpg`` и суффикс: длинное имя не должно упираться в
# ограничение файловой системы (255 символов на компонент пути).
_MAX_PHOTO_STEM = 80


def _photo_file_stem(profile_name: str) -> str:
    """Имя файла фото из имени профиля, безопасное для каталога images.

    ``/`` и ``\\`` в имени профиля — не редкость (несколько артикулов через
    ``/``), но в имени файла они означают подкаталог или выход за пределы
    images. Заменяем запрещённые символы на ``_``, как это делает автобэкап
    книги для имён папок; буквы (в том числе кириллица) не трогаем, чтобы
    имя файла оставалось узнаваемым. Старые фото находятся по пути из БД,
    а не по имени профиля.

    К имени добавляется короткий хеш исходного имени. Без него ``A/B`` и
    ``A_B`` давали один и тот же файл, и фото одного профиля затирало фото
    другого. Хеш считается от исходной строки, поэтому одинаковое имя
    профиля всегда даёт одно имя файла, а разные — разные (в том числе если
    они различаются только регистром: на NTFS/CIFS это один файл).
    """
    stem = "".join("_" if char in _FORBIDDEN_FILENAME_CHARS or ord(char) < 32 else char for char in profile_name)
    stem = stem.rstrip(" .")
    if not stem:
        stem = "_"
    if len(stem) > _MAX_PHOTO_STEM:
        stem = stem[:_MAX_PHOTO_STEM].rstrip(" .") or "_"
    if stem.upper() in _RESERVED_FILENAME_STEMS:
        stem = f"_{stem}"
    digest = hashlib.sha1(profile_name.encode("utf-8")).hexdigest()[:12]
    return f"{stem}-{digest}"


def _resolve_photo_path(images_dir: Path, filename: str) -> Path:
    """Путь к файлу фото с проверкой, что он остался внутри images.

    Имя строится из внешней строки, поэтому проверка на выход за каталог
    нужна на выходе, а не только при замене разделителей: ``..``, точка или
    пробел в конце не должны превратить запись в файл где-то ещё.
    """
    path = (images_dir / filename).resolve()
    if not path.is_relative_to(images_dir.resolve()):
        raise ValueError(f"Photo path escapes images directory: {filename!r}")
    return path


def _write_thumbnail(source: bytes | Path, thumb_path: Path) -> None:
    """Пережать картинку в превью JPEG: PIL, зовётся только из потока.

    ``source`` — байты присланного превью или путь к полному фото. Правило
    одно для обоих входов: цветовой режим, размер и качество превью не
    должны зависеть от того, откуда взялась картинка.
    """
    if isinstance(source, bytes):
        with io.BytesIO(source) as buffer, Image.open(buffer) as img:
            _save_jpeg_thumbnail(img, thumb_path)
        return
    with Image.open(source) as img:
        _save_jpeg_thumbnail(img, thumb_path)


def _save_jpeg_thumbnail(img: Image.Image, thumb_path: Path) -> None:
    """Записать открытую картинку превью: RGB и ``thumbnail`` не увеличивают."""
    if img.mode in ("RGBA", "P"):
        img = img.convert("RGB")
    img.thumbnail(settings.THUMBNAIL_SIZE, Image.Resampling.LANCZOS)
    img.save(thumb_path, "JPEG", quality=85, optimize=True)


def _save_photo(
    images_dir: Path,
    stem: str,
    image_data: bytes,
    thumbnail_data: bytes | None = None,
) -> tuple[Path, Path]:
    """Записать фото и превью: I/O и PIL, поэтому зовётся только из потока.

    Декодирование и пережатие JPEG занимает десятки миллисекунд, а запись на
    диск — ещё больше; в event loop это останавливало бы опрос линии.
    """
    ext = ".jpg"  # Always save as jpg for consistency
    full_path = _resolve_photo_path(images_dir, f"{stem}{ext}")
    thumb_path = _resolve_photo_path(images_dir, f"{stem}-thumb{ext}")

    with open(full_path, "wb") as f:
        f.write(image_data)

    try:
        if thumbnail_data:
            # Use custom thumbnail provided by user (cropped area)
            _write_thumbnail(thumbnail_data, thumb_path)
        else:
            # Auto-generate thumbnail from full image
            _write_thumbnail(full_path, thumb_path)
    except Exception as e:
        # Clean up full image if thumbnail fails
        if full_path.exists():
            full_path.unlink()
        raise ValueError(f"Failed to process image: {e}") from e

    return full_path, thumb_path


def _save_thumbnail(thumb_path: Path, thumbnail_data: bytes) -> None:
    """Пережать и записать превью: PIL, зовётся из потока."""
    try:
        _write_thumbnail(thumbnail_data, thumb_path)
    except Exception as e:
        raise ValueError(f"Failed to process thumbnail: {e}") from e


async def _responses_with_photo_versions(profiles: list[Profile]) -> list[ProfileResponse]:
    """Ответы каталога с версиями файлов фото.

    ``stat`` файлов — блокирующий вызов, поэтому версии считаются в потоке
    одним пакетом на весь ответ, а не по два ``stat`` в event loop на каждый
    профиль. Версия уходит в ``?v=`` URL: замена файла мимо API (синк
    каталога, ручное копирование) тоже должна сбрасывать кэш ``/static/``.
    """
    if not profiles:
        return []

    versions = await asyncio.to_thread(
        photo_file_versions, [(profile.photo_thumb, profile.photo_full) for profile in profiles]
    )
    responses = [ProfileResponse.model_validate(profile) for profile in profiles]
    for response, version in zip(responses, versions, strict=True):
        response.photo_thumb_version = version.thumb
        response.photo_full_version = version.full
    return responses


class CatalogService:
    """
    Service for reading the profile catalog and storing its local notes.

    Provides:
    - Profile search with Latin/Cyrillic normalization
    - Read-only access to profiles
    - Note update (the only catalog write)
    """

    def _normalize_db_path(self, path: str | None) -> str | None:
        """
        Normalize image path from DB to be relative to static directory without leading slashes.
        e.g. '/static/images/123.jpg' -> 'images/123.jpg'
             'images/123.jpg' -> 'images/123.jpg'
        """
        if not path:
            return None

        # Remove leading slashes and backslashes
        clean_path = path.replace("\\", "/").lstrip("/")

        # Remove 'static/' if it exists
        if clean_path.startswith("static/"):
            clean_path = clean_path[7:]

        return clean_path

    def _db_photo_path(self, path: str | None) -> Path | None:
        """Абсолютный путь к фото из БД, но только внутри каталога images.

        Путь в БД — тоже внешние данные: он мог остаться от старой версии,
        быть поправленным вручную или прийти из импортированной базы. Без
        проверки ``../../x`` удалял бы файл за пределами images.
        """
        normalized = self._normalize_db_path(path)
        if not normalized:
            return None

        images_root = settings.images_path.resolve()
        resolved = (settings.images_path.parent / normalized).resolve()
        if not resolved.is_relative_to(images_root):
            logger.warning(f"[Catalog] Refusing photo path outside images: {path!r}")
            return None
        return resolved

    @staticmethod
    def _same_photo_file(first: Path, second: Path) -> bool:
        """Один ли это файл: на NTFS/CIFS регистр в пути не различается.

        Сравнение строк пути без учёта регистра считало ``A.jpg`` и
        ``a.jpg`` разными и удаляло только что записанный файл как
        «старый». ``samefile`` спрашивает файловую систему и не зависит от
        того, канонизирует ли ``resolve()`` регистр на конкретной шаре.
        """
        try:
            return os.path.samefile(first, second)
        except OSError:
            return os.path.normcase(str(first)) == os.path.normcase(str(second))

    async def search_profiles(
        self, query: str, limit: int = 50, session: AsyncSession | None = None
    ) -> list[ProfileSearchResult]:
        """
        Search profiles using normalized text comparison.

        Supports Latin/Cyrillic equivalence - searching for 'ALS' will find 'АЛС'.
        Results are prioritized: name matches first, then notes, then quantity/length.

        Args:
            query: Search query (can be Latin or Cyrillic)
            limit: Maximum number of results
            session: Optional database session

        Returns:
            List of matching profiles with search metadata
        """
        if not query or not query.strip():
            return []

        normalized_query = normalize_text(query)

        async def _search(sess: AsyncSession) -> list[ProfileSearchResult]:
            # Get all profiles and filter in Python for normalized comparison
            stmt = select(Profile).limit(500)  # Reasonable limit for in-memory filtering
            result = await sess.execute(stmt)
            profiles = result.scalars().all()

            matches = []
            for profile in profiles:
                match_priority = self._calculate_match_priority(profile, normalized_query)
                if match_priority is not None:
                    matches.append((profile, match_priority))

            # Sort by priority (lower is better), then by usage_count (higher is better)
            matches.sort(key=lambda x: (x[1], -x[0].usage_count))

            # Convert to response schema with metadata
            selected = matches[:limit]
            versions = await asyncio.to_thread(
                photo_file_versions,
                [(profile.photo_thumb, profile.photo_full) for profile, _ in selected],
            )
            results = []
            for (profile, priority), version in zip(selected, versions, strict=True):
                result = ProfileSearchResult.model_validate(profile)
                result.match_priority = priority
                result.photo_thumb_version = version.thumb
                result.photo_full_version = version.full
                results.append(result)

            return results

        if session:
            return await _search(session)
        else:
            async with get_session() as sess:
                return await _search(sess)

    def _calculate_match_priority(self, profile: Profile, normalized_query: str) -> int | None:
        """
        Calculate match priority for a profile against a query.

        Priority levels:
        - 1: Exact name match
        - 2: Name contains query
        - 3: Notes contain query
        - 4: Quantity or length match

        Returns None if no match.
        """
        normalized_name = normalize_text(profile.name)

        # Priority 1: Exact name match
        if normalized_name == normalized_query:
            return 1

        # Priority 2: Name contains query
        if normalized_query in normalized_name:
            return 2

        # Priority 3: Notes contain query
        if profile.notes:
            normalized_notes = normalize_text(profile.notes)
            if normalized_query in normalized_notes:
                return 3

        # Priority 4: Quantity or length match (numeric search)
        query_digits = "".join(c for c in normalized_query if c.isdigit())
        if query_digits:
            if profile.quantity_per_hanger is not None and query_digits in str(profile.quantity_per_hanger):
                return 4
            if profile.length is not None and query_digits in str(int(profile.length)):
                return 4

        return None

    async def get_profile(self, name: str, session: AsyncSession | None = None) -> ProfileResponse | None:
        """
        Get a profile by exact name.

        Args:
            name: Profile name
            session: Optional database session

        Returns:
            Profile if found, None otherwise
        """

        async def _get(sess: AsyncSession) -> ProfileResponse | None:
            stmt = select(Profile).where(Profile.name == name)
            result = await sess.execute(stmt)
            profile = result.scalar_one_or_none()
            if profile:
                return (await _responses_with_photo_versions([profile]))[0]
            return None

        if session:
            return await _get(session)
        else:
            async with get_session() as sess:
                return await _get(sess)

    async def get_all_profiles(self, limit: int = 500, session: AsyncSession | None = None) -> list[ProfileResponse]:
        """
        Get all profiles.

        Args:
            limit: Maximum number of results
            session: Optional database session

        Returns:
            List of all profiles
        """

        async def _get(sess: AsyncSession) -> list[ProfileResponse]:
            stmt = select(Profile).order_by(Profile.name).limit(limit)
            result = await sess.execute(stmt)
            profiles = result.scalars().all()
            return await _responses_with_photo_versions(list(profiles))

        if session:
            return await _get(session)
        else:
            async with get_session() as sess:
                return await _get(sess)

    async def update_notes(
        self, profile_id: int, notes: str | None, session: AsyncSession | None = None
    ) -> ProfileResponse | None:
        """Обновить примечание профиля — единственную локальную запись каталога.

        Поля артикула принадлежат каталогу-источнику, поэтому здесь меняется
        только примечание: обработчик PATCH не должен уметь править остальное.
        Пустая строка и ``None`` очищают примечание, чтобы в базе не жили два
        разных «пусто».

        Args:
            profile_id: Profile ID
            notes: New note; ``None`` or blank clears it
            session: Optional database session

        Returns:
            Updated profile if found, None otherwise
        """

        async def _update(sess: AsyncSession) -> ProfileResponse | None:
            stmt = select(Profile).where(Profile.id == profile_id)
            result = await sess.execute(stmt)
            profile = result.scalar_one_or_none()

            if not profile:
                return None

            profile.notes = notes or None
            await sess.flush()
            await sess.refresh(profile)
            return (await _responses_with_photo_versions([profile]))[0]

        if session:
            return await _update(session)
        else:
            async with get_session() as sess:
                return await _update(sess)

    def _extract_digits(self, text: str) -> str:
        """Extract all digits from text."""
        import re

        return "".join(re.findall(r"\d", str(text)))

    async def get_profiles_photos_batch(
        self, profile_names: list[str], session: AsyncSession | None = None
    ) -> dict[str, dict]:
        """
        Get photo URLs for multiple profiles at once (batch lookup).

        Uses 3-stage matching like original app.py:
        1. Exact match (case-insensitive)
        2. Normalized match (Latin→Cyrillic)
        3. Digits-only match (if unique)

        Args:
            profile_names: List of profile names from Excel
            session: Optional database session

        Returns:
            Dict mapping profile name to photo info
        """
        if not profile_names:
            return {}

        async def _get_batch(sess: AsyncSession) -> dict[str, dict]:
            # Get ALL profiles (with and without photos) to know which ones exist
            stmt_all = select(Profile)
            result_all = await sess.execute(stmt_all)
            all_profiles = result_all.scalars().all()

            # Get only profiles with photos for photo lookup
            stmt_photos = select(Profile).where(Profile.photo_thumb.isnot(None))
            result_photos = await sess.execute(stmt_photos)
            profiles_with_photos = result_photos.scalars().all()

            # Build lookup dicts
            exact_lookup = {}  # lowercase name → photo_info
            normalized_lookup = {}  # normalized name → photo_info
            prefix_digits_lookup = {}  # (prefix, digits) → photo_info
            digits_lookup = {}  # digits → [photo_info, ...]

            # Track all profile names that exist in DB (with or without photos)
            all_profile_names = {p.name.lower() for p in all_profiles}
            all_profile_names_normalized = {normalize_text(p.name) for p in all_profiles}

            # Track how many profiles (with or without photos) have each digit sequence
            # This prevents "80" from matching when multiple profiles have "80" (ПТ80, СРЛ80, etc.)
            all_digits_count = {}  # digits → count of ALL profiles with these digits
            for profile in all_profiles:
                digits = self._extract_digits(profile.name)
                if digits:
                    all_digits_count[digits] = all_digits_count.get(digits, 0) + 1

            versions = await asyncio.to_thread(
                photo_file_versions,
                [(profile.photo_thumb, profile.photo_full) for profile in profiles_with_photos],
            )

            for profile, version in zip(profiles_with_photos, versions, strict=True):
                photo_info = {
                    "thumb": profile.photo_thumb,
                    "full": profile.photo_full,
                    "name": profile.name,
                    "photo_thumb_version": version.thumb,
                    "photo_full_version": version.full,
                    "updated_at": profile.updated_at.isoformat() if profile.updated_at else None,
                }

                # Exact (lowercase)
                exact_lookup[profile.name.lower()] = photo_info

                # Normalized
                norm_name = normalize_text(profile.name)
                normalized_lookup[norm_name] = photo_info

                # Extract prefix and digits for prefix+digits matching
                # e.g., "СРЛ80" → prefix="срл", digits="80"
                match = re.match(r"^([А-Яа-яA-Za-z]+)(\d+)", profile.name)
                if match:
                    prefix = normalize_text(match.group(1))  # Normalize prefix
                    digits = match.group(2)
                    prefix_digits_lookup[(prefix, digits)] = photo_info

                # Digits only (for last resort fallback)
                digits = self._extract_digits(profile.name)
                if digits:
                    if digits not in digits_lookup:
                        digits_lookup[digits] = []
                    digits_lookup[digits].append(photo_info)

            # Match input names to profiles using 4-stage search
            result_dict = {}
            for name in profile_names:
                if not name or name == "—":
                    continue

                # Чистое имя — единый разбор (app.services.profile_name)
                clean_name = parse_profile(name).name
                if not clean_name:
                    continue

                # Stage 1: Exact match
                if clean_name.lower() in exact_lookup:
                    result_dict[name] = exact_lookup[clean_name.lower()]
                    continue

                # Stage 2: Normalized match
                norm_input = normalize_text(clean_name)
                if norm_input in normalized_lookup:
                    result_dict[name] = normalized_lookup[norm_input]
                    continue

                # Stage 3: Prefix + digits match (most specific)
                match = re.match(r"^([А-Яа-яA-Za-z]+)(\d+)", clean_name)
                if match:
                    prefix = normalize_text(match.group(1))  # Normalize prefix
                    digits = match.group(2)
                    if (prefix, digits) in prefix_digits_lookup:
                        result_dict[name] = prefix_digits_lookup[(prefix, digits)]
                        continue

                # Stage 4: Digits match (LAST RESORT - only if unique AND profile doesn't exist in DB)
                # This prevents false positives: if ПТ80 exists in DB, don't match it to СРЛ80
                # Also prevents "80" from matching when multiple profiles have "80" (ПТ80, СРЛ80, СРМ480, etc.)
                digits = self._extract_digits(clean_name)
                if digits and digits in digits_lookup:
                    matches = digits_lookup[digits]
                    # Only use digits matching if:
                    # 1. There's exactly one profile WITH PHOTOS with these digits
                    # 2. There's exactly one profile IN TOTAL (with or without photos) with these digits
                    # 3. The input name doesn't exist in DB (so it's not a known profile)
                    if len(matches) == 1 and all_digits_count.get(digits, 0) == 1:
                        input_lower = clean_name.lower()
                        input_norm = normalize_text(clean_name)
                        # Check if this exact profile name exists in DB
                        if input_lower not in all_profile_names and input_norm not in all_profile_names_normalized:
                            result_dict[name] = matches[0]

            return result_dict

        if session:
            return await _get_batch(session)
        else:
            async with get_session() as sess:
                return await _get_batch(sess)


# Singleton instance
catalog_service = CatalogService()
