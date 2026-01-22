"""
Catalog Service - handles profile search, CRUD operations, and photo management.
"""
import io
import os
import re
import uuid
from datetime import datetime, timezone
from difflib import SequenceMatcher
from pathlib import Path
from typing import Optional, List, Tuple

from PIL import Image
from sqlalchemy import select, or_, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Profile
from app.db.session import get_session
from app.schemas.profile import ProfileCreate, ProfileUpdate, ProfileResponse, ProfileSearchResult
from app.core.text_utils import normalize_text, safe_filename
from app.core.config import settings


class CatalogService:
    """
    Service for managing the profile catalog.
    
    Provides:
    - Profile search with Latin/Cyrillic normalization
    - CRUD operations for profiles
    - Photo management
    - Analysis queries (profiles without photos)
    """
    
    async def search_profiles(
        self,
        query: str,
        limit: int = 50,
        session: Optional[AsyncSession] = None
    ) -> List[ProfileSearchResult]:
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
        
        async def _search(sess: AsyncSession) -> List[ProfileSearchResult]:
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

    
    def _calculate_match_priority(
        self,
        profile: Profile,
        normalized_query: str
    ) -> Optional[int]:
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
        query_digits = ''.join(c for c in normalized_query if c.isdigit())
        if query_digits:
            if profile.quantity_per_hanger is not None:
                if query_digits in str(profile.quantity_per_hanger):
                    return 4
            if profile.length is not None:
                if query_digits in str(int(profile.length)):
                    return 4
        
        return None
    
    async def get_profile(
        self,
        name: str,
        session: Optional[AsyncSession] = None
    ) -> Optional[ProfileResponse]:
        """
        Get a profile by exact name.
        
        Args:
            name: Profile name
            session: Optional database session
        
        Returns:
            Profile if found, None otherwise
        """
        async def _get(sess: AsyncSession) -> Optional[ProfileResponse]:
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
    
    async def get_profile_by_id(
        self,
        profile_id: int,
        session: Optional[AsyncSession] = None
    ) -> Optional[ProfileResponse]:
        """
        Get a profile by ID.
        
        Args:
            profile_id: Profile ID
            session: Optional database session
        
        Returns:
            Profile if found, None otherwise
        """
        async def _get(sess: AsyncSession) -> Optional[ProfileResponse]:
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
        self,
        data: ProfileCreate,
        session: Optional[AsyncSession] = None
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
        self,
        profile_id: int,
        data: ProfileUpdate,
        session: Optional[AsyncSession] = None
    ) -> Optional[ProfileResponse]:
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
        async def _update(sess: AsyncSession) -> Optional[ProfileResponse]:
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
                    profile.photo_thumb,
                    profile.photo_full,
                    new_name
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
        self,
        old_thumb_path: Optional[str],
        old_full_path: Optional[str],
        new_name: str
    ) -> Tuple[Optional[str], Optional[str]]:
        """
        Rename photo files when profile name changes.
        
        Uses format: {name}.jpg and {name}-thumb.jpg
        
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
        
        # Rename thumbnail: {name}-thumb.jpg
        if old_thumb_path:
            old_thumb_file = images_dir.parent / old_thumb_path
            if old_thumb_file.exists():
                new_thumb_filename = f"{new_name}-thumb.jpg"
                new_thumb_file = images_dir / new_thumb_filename
                old_thumb_file.rename(new_thumb_file)
                new_thumb_path = f"images/{new_thumb_filename}"
        
        # Rename full photo: {name}.jpg
        if old_full_path:
            old_full_file = images_dir.parent / old_full_path
            if old_full_file.exists():
                new_full_filename = f"{new_name}.jpg"
                new_full_file = images_dir / new_full_filename
                old_full_file.rename(new_full_file)
                new_full_path = f"images/{new_full_filename}"
        
        return new_thumb_path, new_full_path
    
    async def increment_usage(
        self,
        name: str,
        session: Optional[AsyncSession] = None
    ) -> None:
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
    
    async def get_profiles_without_photos(
        self,
        limit: int = 100,
        session: Optional[AsyncSession] = None
    ) -> List[ProfileResponse]:
        """
        Get profiles that don't have photos, sorted by usage frequency.
        
        Used for the analysis page to identify missing documentation.
        
        Args:
            limit: Maximum number of results
            session: Optional database session
        
        Returns:
            List of profiles without photos, sorted by usage_count descending
        """
        async def _get(sess: AsyncSession) -> List[ProfileResponse]:
            stmt = (
                select(Profile)
                .where(
                    or_(
                        Profile.photo_thumb.is_(None),
                        Profile.photo_thumb == '',
                        Profile.photo_full.is_(None),
                        Profile.photo_full == ''
                    )
                )
                .order_by(Profile.usage_count.desc())
                .limit(limit)
            )
            result = await sess.execute(stmt)
            profiles = result.scalars().all()
            return [ProfileResponse.model_validate(p) for p in profiles]
        
        if session:
            return await _get(session)
        else:
            async with get_session() as sess:
                return await _get(sess)
    
    async def get_all_profiles(
        self,
        limit: int = 500,
        session: Optional[AsyncSession] = None
    ) -> List[ProfileResponse]:
        """
        Get all profiles.
        
        Args:
            limit: Maximum number of results
            session: Optional database session
        
        Returns:
            List of all profiles
        """
        async def _get(sess: AsyncSession) -> List[ProfileResponse]:
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
        thumbnail_data: Optional[bytes] = None,
        session: Optional[AsyncSession] = None
    ) -> Tuple[str, str]:
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
            raise ValueError(f"Image exceeds maximum size of {settings.MAX_UPLOAD_SIZE // (1024*1024)}MB")
        
        # Create images directory if needed
        images_dir = settings.images_path
        images_dir.mkdir(parents=True, exist_ok=True)
        
        import logging
        logger = logging.getLogger(__name__)
        logger.info(f"[upload_photo] images_dir: {images_dir}, exists: {images_dir.exists()}, absolute: {images_dir.absolute()}")
        
        # Generate safe filename
        # Use profile name directly (keep original format: name.jpg, name-thumb.jpg)
        # safe_filename handles transliteration for Latin-only names
        base_name = profile_name
        ext = '.jpg'  # Always save as jpg for consistency
        
        full_filename = f"{base_name}{ext}"
        thumb_filename = f"{base_name}-thumb{ext}"
        
        full_path = images_dir / full_filename
        thumb_path = images_dir / thumb_filename
        
        logger.info(f"[upload_photo] Saving to full_path: {full_path.absolute()}, thumb_path: {thumb_path.absolute()}")
        
        # Save full-size image
        with open(full_path, 'wb') as f:
            f.write(image_data)
        
        logger.info(f"[upload_photo] Full image saved, size: {full_path.stat().st_size if full_path.exists() else 'NOT FOUND'}")
        
        # Generate or save thumbnail
        try:
            if thumbnail_data:
                # Use custom thumbnail provided by user (cropped area)
                with Image.open(io.BytesIO(thumbnail_data)) as img:
                    if img.mode in ('RGBA', 'P'):
                        img = img.convert('RGB')
                    # Resize to thumbnail size if larger
                    if img.width > settings.THUMBNAIL_SIZE[0] or img.height > settings.THUMBNAIL_SIZE[1]:
                        img.thumbnail(settings.THUMBNAIL_SIZE, Image.Resampling.LANCZOS)
                    img.save(thumb_path, 'JPEG', quality=85, optimize=True)
            else:
                # Auto-generate thumbnail from full image
                with Image.open(full_path) as img:
                    if img.mode in ('RGBA', 'P'):
                        img = img.convert('RGB')
                    img.thumbnail(settings.THUMBNAIL_SIZE, Image.Resampling.LANCZOS)
                    img.save(thumb_path, 'JPEG', quality=85, optimize=True)
        except Exception as e:
            # Clean up full image if thumbnail fails
            if full_path.exists():
                full_path.unlink()
            raise ValueError(f"Failed to process image: {e}")
        
        # Relative paths for storage in DB
        rel_thumb = f"images/{thumb_filename}"
        rel_full = f"images/{full_filename}"
        
        # Update profile in database
        async def _update(sess: AsyncSession) -> None:
            stmt = select(Profile).where(Profile.name == profile_name)
            result = await sess.execute(stmt)
            profile = result.scalar_one_or_none()
            
            if profile:
                # Delete old photos if they exist
                if profile.photo_thumb:
                    old_thumb = settings.images_path.parent / profile.photo_thumb
                    if old_thumb.exists():
                        old_thumb.unlink()
                if profile.photo_full:
                    old_full = settings.images_path.parent / profile.photo_full
                    if old_full.exists():
                        old_full.unlink()
                
                profile.photo_thumb = rel_thumb
                profile.photo_full = rel_full
            else:
                # Create new profile with photo
                new_profile = Profile(
                    name=profile_name,
                    photo_thumb=rel_thumb,
                    photo_full=rel_full
                )
                sess.add(new_profile)
            
            await sess.flush()
        
        if session:
            await _update(session)
        else:
            async with get_session() as sess:
                await _update(sess)
        
        return rel_thumb, rel_full
    
    async def update_thumbnail(
        self,
        profile_name: str,
        thumbnail_data: bytes,
        session: Optional[AsyncSession] = None
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
        
        thumb_filename = f"{profile_name}-thumb.jpg"
        thumb_path = images_dir / thumb_filename
        rel_thumb = f"images/{thumb_filename}"
        
        # Save new thumbnail
        try:
            with Image.open(io.BytesIO(thumbnail_data)) as img:
                if img.mode in ('RGBA', 'P'):
                    img = img.convert('RGB')
                if img.width > settings.THUMBNAIL_SIZE[0] or img.height > settings.THUMBNAIL_SIZE[1]:
                    img.thumbnail(settings.THUMBNAIL_SIZE, Image.Resampling.LANCZOS)
                img.save(thumb_path, 'JPEG', quality=85, optimize=True)
        except Exception as e:
            raise ValueError(f"Failed to process thumbnail: {e}")
        
        # Update profile in database
        async def _update(sess: AsyncSession) -> None:
            stmt = select(Profile).where(Profile.name == profile_name)
            result = await sess.execute(stmt)
            profile = result.scalar_one_or_none()
            
            if not profile:
                raise ValueError(f"Profile '{profile_name}' not found")
            
            profile.photo_thumb = rel_thumb
            profile.updated_at = datetime.now(timezone.utc)  # Force update timestamp
            await sess.flush()
        
        if session:
            await _update(session)
        else:
            async with get_session() as sess:
                await _update(sess)
        
        return rel_thumb

    async def delete_photo(
        self,
        profile_name: str,
        session: Optional[AsyncSession] = None
    ) -> bool:
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
            if profile.photo_thumb:
                thumb_path = settings.images_path.parent / profile.photo_thumb
                if thumb_path.exists():
                    thumb_path.unlink()
            
            if profile.photo_full:
                full_path = settings.images_path.parent / profile.photo_full
                if full_path.exists():
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
    
    async def delete_full_photo(
        self,
        profile_name: str,
        session: Optional[AsyncSession] = None
    ) -> bool:
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
            if profile.photo_full:
                full_path = settings.images_path.parent / profile.photo_full
                if full_path.exists():
                    full_path.unlink()
            
            # Clear DB field
            profile.photo_full = None
            profile.updated_at = datetime.now(timezone.utc)
            await sess.flush()
            
            return True
        
        if session:
            return await _delete(session)
        else:
            async with get_session() as sess:
                return await _delete(sess)
    
    async def delete_thumbnail(
        self,
        profile_name: str,
        session: Optional[AsyncSession] = None
    ) -> bool:
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
            if profile.photo_thumb:
                thumb_path = settings.images_path.parent / profile.photo_thumb
                if thumb_path.exists():
                    thumb_path.unlink()
            
            # Clear DB field
            profile.photo_thumb = None
            profile.updated_at = datetime.now(timezone.utc)
            await sess.flush()
            
            return True
        
        if session:
            return await _delete(session)
        else:
            async with get_session() as sess:
                return await _delete(sess)
    
    def _calculate_similarity(self, s1: str, s2: str) -> float:
        """
        Calculate similarity ratio between two strings using SequenceMatcher.
        
        Args:
            s1: First string
            s2: Second string
        
        Returns:
            Similarity ratio between 0.0 and 1.0
        """
        if not s1 or not s2:
            return 0.0
        return SequenceMatcher(None, s1.lower(), s2.lower()).ratio()
    
    async def delete_profile(
        self,
        profile_id: int,
        session: Optional[AsyncSession] = None
    ) -> bool:
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
            
            # Delete photo files
            if profile.photo_thumb:
                thumb_path = settings.images_path.parent / profile.photo_thumb
                if thumb_path.exists():
                    thumb_path.unlink()
            
            if profile.photo_full:
                full_path = settings.images_path.parent / profile.photo_full
                if full_path.exists():
                    full_path.unlink()
            
            await sess.delete(profile)
            await sess.flush()
            return True
        
        if session:
            return await _delete(session)
        else:
            async with get_session() as sess:
                return await _delete(sess)

    async def search_duplicates(
        self,
        query: str,
        threshold: float = 0.6,
        limit: int = 20,
        session: Optional[AsyncSession] = None
    ) -> List[ProfileSearchResult]:
        """
        Find profiles with similar names using fuzzy matching.
        
        Uses SequenceMatcher for similarity scoring. Results are ordered
        by similarity score (highest first).
        
        Args:
            query: Search query
            threshold: Minimum similarity score (0.0 to 1.0)
            limit: Maximum number of results
            session: Optional database session
        
        Returns:
            List of profiles with similarity scores above threshold
        """
        if not query or not query.strip():
            return []
        
        normalized_query = normalize_text(query)
        
        async def _search(sess: AsyncSession) -> List[ProfileSearchResult]:
            stmt = select(Profile).limit(1000)
            result = await sess.execute(stmt)
            profiles = result.scalars().all()
            
            matches = []
            for profile in profiles:
                normalized_name = normalize_text(profile.name)
                similarity = self._calculate_similarity(normalized_query, normalized_name)
                
                if similarity >= threshold:
                    matches.append((profile, similarity))
            
            # Sort by similarity descending
            matches.sort(key=lambda x: -x[1])
            
            # Convert to response schema
            results = []
            for profile, similarity in matches[:limit]:
                result = ProfileSearchResult.model_validate(profile)
                result.similarity = round(similarity, 3)
                results.append(result)
            
            return results
        
        if session:
            return await _search(session)
        else:
            async with get_session() as sess:
                return await _search(sess)


    def _extract_profile_name(self, text: str) -> str:
        """
        Extract clean profile name by removing processing keywords.
        
        "СРП228 окно" → "СРП228"
        "юп-3233 греб + сверло" → "юп-3233"
        """
        import re
        if not text:
            return ""
        
        text = str(text).strip()
        
        # Remove processing keywords
        for keyword in ['окно', 'греб', 'гребенка', 'сверло', 'фреза', 'паз']:
            pattern = r'\b' + re.escape(keyword) + r'\b'
            text = re.sub(pattern, '', text, flags=re.IGNORECASE)
        
        # Clean up
        text = re.sub(r'\s+', ' ', text).strip()
        text = text.rstrip('+,;').strip()
        
        return text
    
    def _extract_digits(self, text: str) -> str:
        """Extract all digits from text."""
        import re
        return ''.join(re.findall(r'\d', str(text)))

    async def get_profiles_photos_batch(
        self,
        profile_names: List[str],
        session: Optional[AsyncSession] = None
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
                    'thumb': profile.photo_thumb,
                    'full': profile.photo_full,
                    'name': profile.name,
                    'updated_at': profile.updated_at.isoformat() if profile.updated_at else None,
                }
                
                # Exact (lowercase)
                exact_lookup[profile.name.lower()] = photo_info
                
                # Normalized
                norm_name = normalize_text(profile.name)
                normalized_lookup[norm_name] = photo_info
                
                # Extract prefix and digits for prefix+digits matching
                # e.g., "СРЛ80" → prefix="срл", digits="80"
                match = re.match(r'^([А-Яа-яA-Za-z]+)(\d+)', profile.name)
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
                if not name or name == '—':
                    continue
                
                # Extract clean name (remove "окно", "греб", etc.)
                clean_name = self._extract_profile_name(name)
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
                match = re.match(r'^([А-Яа-яA-Za-z]+)(\d+)', clean_name)
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
