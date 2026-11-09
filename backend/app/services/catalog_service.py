"""
Catalog Service - handles profile search, CRUD operations, and photo management.
"""

import hashlib
import io
import logging
import os
import re
from datetime import UTC, datetime
from pathlib import Path

from PIL import Image
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.text_utils import normalize_text
from app.db.models import Profile
from app.db.session import get_session
from app.schemas.profile import ProfileCreate, ProfileResponse, ProfileSearchResult, ProfileUpdate
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


class CatalogService:
    """
    Service for managing the profile catalog.

    Provides:
    - Profile search with Latin/Cyrillic normalization
    - CRUD operations for profiles
    - Photo management
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
            results = []
            for profile, priority in matches[:limit]:
                result = ProfileSearchResult.model_validate(profile)
                result.match_priority = priority
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
                return ProfileResponse.model_validate(profile)
            return None

        if session:
            return await _get(session)
        else:
            async with get_session() as sess:
                return await _get(sess)

    async def get_profile_by_id(self, profile_id: int, session: AsyncSession | None = None) -> ProfileResponse | None:
        """
        Get a profile by ID.

        Args:
            profile_id: Profile ID
            session: Optional database session

        Returns:
            Profile if found, None otherwise
        """

        async def _get(sess: AsyncSession) -> ProfileResponse | None:
            stmt = select(Profile).where(Profile.id == profile_id)
            result = await sess.execute(stmt)
            profile = result.scalar_one_or_none()
            if profile:
                return ProfileResponse.model_validate(profile)
            return None

        if session:
            return await _get(session)
        else:
            async with get_session() as sess:
                return await _get(sess)

    async def create_or_update_profile(
        self, data: ProfileCreate, session: AsyncSession | None = None
    ) -> ProfileResponse:
        """
        Create a new profile or update existing one by name.

        Args:
            data: Profile data
            session: Optional database session

        Returns:
            Created or updated profile
        """

        async def _create_or_update(sess: AsyncSession) -> ProfileResponse:
            # Check if profile exists
            stmt = select(Profile).where(Profile.name == data.name)
            result = await sess.execute(stmt)
            profile = result.scalar_one_or_none()

            if profile:
                # Update existing
                for field, value in data.model_dump(exclude_unset=True).items():
                    setattr(profile, field, value)
            else:
                # Create new
                profile = Profile(**data.model_dump())
                sess.add(profile)

            await sess.flush()
            await sess.refresh(profile)
            return ProfileResponse.model_validate(profile)

        if session:
            return await _create_or_update(session)
        else:
            async with get_session() as sess:
                return await _create_or_update(sess)

    async def update_profile(
        self, profile_id: int, data: ProfileUpdate, session: AsyncSession | None = None
    ) -> ProfileResponse | None:
        """
        Update an existing profile by ID.

        If name is changed and profile has photos, the photo files will be
        renamed to match the new profile name.

        Args:
            profile_id: Profile ID
            data: Update data
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

            # Check if name is being changed and profile has photos
            old_name = profile.name
            new_name = data.name if data.name else old_name
            name_changed = new_name != old_name and data.name is not None

            if name_changed and (profile.photo_thumb or profile.photo_full):
                # Rename photo files
                new_thumb_path, new_full_path = self._rename_photo_files(
                    profile.photo_thumb, profile.photo_full, new_name
                )
                profile.photo_thumb = new_thumb_path
                profile.photo_full = new_full_path

            # Update other fields
            for field, value in data.model_dump(exclude_unset=True).items():
                if value is not None:
                    setattr(profile, field, value)

            await sess.flush()
            await sess.refresh(profile)
            return ProfileResponse.model_validate(profile)

        if session:
            return await _update(session)
        else:
            async with get_session() as sess:
                return await _update(sess)

    def _rename_photo_files(
        self, old_thumb_path: str | None, old_full_path: str | None, new_name: str
    ) -> tuple[str | None, str | None]:
        """
        Rename photo files when profile name changes.

        Uses format: {stem}.jpg and {stem}-thumb.jpg, where ``stem`` is
        produced by ``_photo_file_stem``.

        Args:
            old_thumb_path: Current thumbnail path (relative)
            old_full_path: Current full photo path (relative)
            new_name: New profile name

        Returns:
            Tuple of (new_thumb_path, new_full_path)
        """
        images_dir = settings.images_path

        new_thumb_path = old_thumb_path
        new_full_path = old_full_path

        # Rename thumbnail: {stem}-thumb.jpg
        if old_thumb_path:
            old_thumb_file = self._db_photo_path(old_thumb_path)
            if old_thumb_file and old_thumb_file.exists():
                new_thumb_filename = f"{_photo_file_stem(new_name)}-thumb.jpg"
                new_thumb_file = _resolve_photo_path(images_dir, new_thumb_filename)
                old_thumb_file.rename(new_thumb_file)
                new_thumb_path = f"images/{new_thumb_filename}"

        # Rename full photo: {stem}.jpg
        if old_full_path:
            old_full_file = self._db_photo_path(old_full_path)
            if old_full_file and old_full_file.exists():
                new_full_filename = f"{_photo_file_stem(new_name)}.jpg"
                new_full_file = _resolve_photo_path(images_dir, new_full_filename)
                old_full_file.rename(new_full_file)
                new_full_path = f"images/{new_full_filename}"

        return new_thumb_path, new_full_path

    async def increment_usage(self, name: str, session: AsyncSession | None = None) -> None:
        """
        Increment usage count for a profile.

        Args:
            name: Profile name
            session: Optional database session
        """

        async def _increment(sess: AsyncSession) -> None:
            stmt = select(Profile).where(Profile.name == name)
            result = await sess.execute(stmt)
            profile = result.scalar_one_or_none()

            if profile:
                profile.usage_count += 1
                await sess.flush()

        if session:
            await _increment(session)
        else:
            async with get_session() as sess:
                await _increment(sess)

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
            return [ProfileResponse.model_validate(p) for p in profiles]

        if session:
            return await _get(session)
        else:
            async with get_session() as sess:
                return await _get(sess)

    async def upload_photo(
        self,
        profile_name: str,
        image_data: bytes,
        filename: str,
        thumbnail_data: bytes | None = None,
        session: AsyncSession | None = None,
    ) -> tuple[str, str]:
        """
        Upload a photo for a profile, generating both thumbnail and full-size versions.

        Args:
            profile_name: Name of the profile
            image_data: Raw image bytes for full-size photo
            filename: Original filename
            thumbnail_data: Optional custom thumbnail bytes (user-cropped)
            session: Optional database session

        Returns:
            Tuple of (thumbnail_path, full_path) relative to static dir

        Raises:
            ValueError: If image is too large or invalid
        """
        # Validate size
        if len(image_data) > settings.MAX_UPLOAD_SIZE:
            raise ValueError(f"Image exceeds maximum size of {settings.MAX_UPLOAD_SIZE // (1024 * 1024)}MB")

        # Create images directory if needed
        images_dir = settings.images_path
        images_dir.mkdir(parents=True, exist_ok=True)

        logger.info(
            f"[upload_photo] images_dir: {images_dir}, exists: {images_dir.exists()}, absolute: {images_dir.absolute()}"
        )

        # Имя файла из имени профиля: без разделителей пути и запрещённых
        # символов (см. _photo_file_stem). Буквы и дефисы сохраняются.
        base_name = _photo_file_stem(profile_name)
        ext = ".jpg"  # Always save as jpg for consistency

        full_filename = f"{base_name}{ext}"
        thumb_filename = f"{base_name}-thumb{ext}"

        full_path = _resolve_photo_path(images_dir, full_filename)
        thumb_path = _resolve_photo_path(images_dir, thumb_filename)

        logger.info(f"[upload_photo] Saving to full_path: {full_path.absolute()}, thumb_path: {thumb_path.absolute()}")

        # Save full-size image
        with open(full_path, "wb") as f:
            f.write(image_data)

        logger.info(
            f"[upload_photo] Full image saved, size: {full_path.stat().st_size if full_path.exists() else 'NOT FOUND'}"
        )

        # Generate or save thumbnail
        try:
            if thumbnail_data:
                # Use custom thumbnail provided by user (cropped area)
                with Image.open(io.BytesIO(thumbnail_data)) as img:
                    if img.mode in ("RGBA", "P"):
                        img = img.convert("RGB")
                    # Resize to thumbnail size if larger
                    if img.width > settings.THUMBNAIL_SIZE[0] or img.height > settings.THUMBNAIL_SIZE[1]:
                        img.thumbnail(settings.THUMBNAIL_SIZE, Image.Resampling.LANCZOS)
                    img.save(thumb_path, "JPEG", quality=85, optimize=True)
            else:
                # Auto-generate thumbnail from full image
                with Image.open(full_path) as img:
                    if img.mode in ("RGBA", "P"):
                        img = img.convert("RGB")
                    img.thumbnail(settings.THUMBNAIL_SIZE, Image.Resampling.LANCZOS)
                    img.save(thumb_path, "JPEG", quality=85, optimize=True)
        except Exception as e:
            # Clean up full image if thumbnail fails
            if full_path.exists():
                full_path.unlink()
            raise ValueError(f"Failed to process image: {e}") from e

        # Relative paths for storage in DB
        rel_thumb = f"images/{thumb_filename}"
        rel_full = f"images/{full_filename}"

        # Update profile in database
        async def _update(sess: AsyncSession) -> None:
            stmt = select(Profile).where(Profile.name == profile_name)
            result = await sess.execute(stmt)
            profile = result.scalar_one_or_none()

            if profile:
                # Delete old photos that live under a different name. При
                # повторной загрузке того же профиля старый путь совпадает с
                # только что записанным файлом: удалять его нельзя, иначе
                # запись в БД указывает на несуществующий файл. Сравнение
                # без учёта регистра: на NTFS/CIFS ``A.jpg`` и ``a.jpg`` —
                # один файл.
                old_thumb = self._db_photo_path(profile.photo_thumb)
                if old_thumb and not self._same_photo_file(old_thumb, thumb_path) and old_thumb.exists():
                    old_thumb.unlink()
                old_full = self._db_photo_path(profile.photo_full)
                if old_full and not self._same_photo_file(old_full, full_path) and old_full.exists():
                    old_full.unlink()

                profile.photo_thumb = rel_thumb
                profile.photo_full = rel_full
                # Поля могли не измениться: повторная загрузка пишет файл по
                # тому же имени. Явная метка нужна, чтобы updated_at сменился
                # и браузер (cache-buster по нему) показал новое фото.
                profile.updated_at = datetime.now(UTC)
            else:
                # Create new profile with photo
                new_profile = Profile(name=profile_name, photo_thumb=rel_thumb, photo_full=rel_full)
                sess.add(new_profile)

            await sess.flush()

        if session:
            await _update(session)
        else:
            async with get_session() as sess:
                await _update(sess)

        return rel_thumb, rel_full

    async def update_thumbnail(
        self, profile_name: str, thumbnail_data: bytes, session: AsyncSession | None = None
    ) -> str:
        """
        Update only the thumbnail for a profile (keeps full image).

        Args:
            profile_name: Name of the profile
            thumbnail_data: New thumbnail image bytes
            session: Optional database session

        Returns:
            Relative path to new thumbnail

        Raises:
            ValueError: If profile not found or has no photo
        """
        images_dir = settings.images_path
        images_dir.mkdir(parents=True, exist_ok=True)

        thumb_filename = f"{_photo_file_stem(profile_name)}-thumb.jpg"
        thumb_path = _resolve_photo_path(images_dir, thumb_filename)
        rel_thumb = f"images/{thumb_filename}"

        # Save new thumbnail
        try:
            with Image.open(io.BytesIO(thumbnail_data)) as img:
                if img.mode in ("RGBA", "P"):
                    img = img.convert("RGB")
                if img.width > settings.THUMBNAIL_SIZE[0] or img.height > settings.THUMBNAIL_SIZE[1]:
                    img.thumbnail(settings.THUMBNAIL_SIZE, Image.Resampling.LANCZOS)
                img.save(thumb_path, "JPEG", quality=85, optimize=True)
        except Exception as e:
            raise ValueError(f"Failed to process thumbnail: {e}") from e

        # Update profile in database
        async def _update(sess: AsyncSession) -> None:
            stmt = select(Profile).where(Profile.name == profile_name)
            result = await sess.execute(stmt)
            profile = result.scalar_one_or_none()

            if not profile:
                raise ValueError(f"Profile '{profile_name}' not found")

            profile.photo_thumb = rel_thumb
            profile.updated_at = datetime.now(UTC)  # Force update timestamp
            await sess.flush()

        if session:
            await _update(session)
        else:
            async with get_session() as sess:
                await _update(sess)

        return rel_thumb

    async def delete_photo(self, profile_name: str, session: AsyncSession | None = None) -> bool:
        """
        Delete photos for a profile.

        Args:
            profile_name: Name of the profile
            session: Optional database session

        Returns:
            True if photos were deleted, False if profile not found
        """

        async def _delete(sess: AsyncSession) -> bool:
            stmt = select(Profile).where(Profile.name == profile_name)
            result = await sess.execute(stmt)
            profile = result.scalar_one_or_none()

            if not profile:
                return False

            # Delete files
            thumb_path = self._db_photo_path(profile.photo_thumb)
            if thumb_path and thumb_path.exists():
                thumb_path.unlink()

            full_path = self._db_photo_path(profile.photo_full)
            if full_path and full_path.exists():
                full_path.unlink()

            # Clear DB fields
            profile.photo_thumb = None
            profile.photo_full = None
            await sess.flush()

            return True

        if session:
            return await _delete(session)
        else:
            async with get_session() as sess:
                return await _delete(sess)

    async def delete_full_photo(self, profile_name: str, session: AsyncSession | None = None) -> bool:
        """
        Delete only the full photo for a profile (keeps thumbnail).

        Args:
            profile_name: Name of the profile
            session: Optional database session

        Returns:
            True if full photo was deleted, False if profile not found
        """

        async def _delete(sess: AsyncSession) -> bool:
            stmt = select(Profile).where(Profile.name == profile_name)
            result = await sess.execute(stmt)
            profile = result.scalar_one_or_none()

            if not profile:
                return False

            # Delete full photo file
            full_path = self._db_photo_path(profile.photo_full)
            if full_path and full_path.exists():
                full_path.unlink()

            # Clear DB field
            profile.photo_full = None
            profile.updated_at = datetime.now(UTC)
            await sess.flush()

            return True

        if session:
            return await _delete(session)
        else:
            async with get_session() as sess:
                return await _delete(sess)

    async def delete_thumbnail(self, profile_name: str, session: AsyncSession | None = None) -> bool:
        """
        Delete only the thumbnail for a profile (keeps full photo).

        Args:
            profile_name: Name of the profile
            session: Optional database session

        Returns:
            True if thumbnail was deleted, False if profile not found
        """

        async def _delete(sess: AsyncSession) -> bool:
            stmt = select(Profile).where(Profile.name == profile_name)
            result = await sess.execute(stmt)
            profile = result.scalar_one_or_none()

            if not profile:
                return False

            # Delete thumbnail file
            thumb_path = self._db_photo_path(profile.photo_thumb)
            if thumb_path and thumb_path.exists():
                thumb_path.unlink()

            # Clear DB field
            profile.photo_thumb = None
            profile.updated_at = datetime.now(UTC)
            await sess.flush()

            return True

        if session:
            return await _delete(session)
        else:
            async with get_session() as sess:
                return await _delete(sess)

    async def delete_profile(self, profile_id: int, session: AsyncSession | None = None) -> bool:
        """
        Delete a profile by ID, including its photos.

        Args:
            profile_id: Profile ID
            session: Optional database session

        Returns:
            True if deleted, False if not found
        """

        async def _delete(sess: AsyncSession) -> bool:
            stmt = select(Profile).where(Profile.id == profile_id)
            result = await sess.execute(stmt)
            profile = result.scalar_one_or_none()

            if not profile:
                return False

            # Delete photo files. Путь из БД нормализуем, как в остальных
            # операциях с фото: старые записи могли хранить «/static/images/…».
            thumb_path = self._db_photo_path(profile.photo_thumb)
            if thumb_path and thumb_path.exists():
                thumb_path.unlink()

            full_path = self._db_photo_path(profile.photo_full)
            if full_path and full_path.exists():
                full_path.unlink()

            await sess.delete(profile)
            await sess.flush()
            return True

        if session:
            return await _delete(session)
        else:
            async with get_session() as sess:
                return await _delete(sess)

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

            for profile in profiles_with_photos:
                photo_info = {
                    "thumb": profile.photo_thumb,
                    "full": profile.photo_full,
                    "name": profile.name,
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
