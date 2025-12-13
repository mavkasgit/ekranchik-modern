"""
Catalog Service - handles profile search, CRUD operations, and photo management.
"""
import os
import uuid
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
        session: Optional[AsyncSession] = None
    ) -> Tuple[str, str]:
        """
        Upload a photo for a profile, generating both thumbnail and full-size versions.
        
        Args:
            profile_name: Name of the profile
            image_data: Raw image bytes
            filename: Original filename
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
        
        # Generate safe filename
        safe_name = safe_filename(profile_name)
        unique_id = uuid.uuid4().hex[:8]
        ext = Path(filename).suffix.lower() or '.jpg'
        if ext not in ('.jpg', '.jpeg', '.png', '.gif', '.webp'):
            ext = '.jpg'
        
        base_name = f"{safe_name}_{unique_id}"
        full_filename = f"{base_name}_full{ext}"
        thumb_filename = f"{base_name}_thumb{ext}"
        
        full_path = images_dir / full_filename
        thumb_path = images_dir / thumb_filename
        
        # Save full-size image
        with open(full_path, 'wb') as f:
            f.write(image_data)
        
        # Generate thumbnail
        try:
            with Image.open(full_path) as img:
                # Convert to RGB if necessary (for PNG with transparency)
                if img.mode in ('RGBA', 'P'):
                    img = img.convert('RGB')
                
                # Create thumbnail maintaining aspect ratio
                img.thumbnail(settings.THUMBNAIL_SIZE, Image.Resampling.LANCZOS)
                img.save(thumb_path, quality=85, optimize=True)
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


# Singleton instance
catalog_service = CatalogService()
