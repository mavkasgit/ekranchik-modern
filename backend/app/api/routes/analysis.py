"""
Analysis API routes - missing photos, duplicates, recent profiles.
"""
from typing import Optional
import re

from fastapi import APIRouter, Query
from sqlalchemy import select

from app.db.models import Profile
from app.db.session import get_session
from app.core.text_utils import normalize_text
from app.services.catalog_service import catalog_service
from app.services.excel_service import excel_service
from app.schemas.profile import ProfileResponse, ProfileSearchResult

router = APIRouter(prefix="/profiles", tags=["analysis"])


@router.get("/missing", response_model=list[ProfileResponse])
async def get_profiles_missing_photos(
    limit: int = Query(default=100, ge=1, le=500, description="Max results")
):
    """
    Get profiles without photos, sorted by usage frequency.
    
    Returns profiles that need documentation, prioritized by
    how often they appear in production data.
    """
    return await catalog_service.get_profiles_without_photos(limit=limit)


@router.get("/recent")
async def get_recent_profiles(
    limit: int = Query(default=50, ge=1, le=200, description="Max results")
):
    """
    Get recent profile records from Excel.
    """
    recent = excel_service.get_recent_profiles(limit=limit)
    
    # Collect all individual profile names to batch fetch photos
    profile_names = set()
    for item in recent:
        profile_str = item.get("profile", "")
        if profile_str and profile_str != "—":
            for name in re.split(r'[+/]', profile_str):
                name = name.strip()
                if name:
                    profile_names.add(name)
                    
    # Batch fetch photos from catalog
    photos_map = {}
    if profile_names:
        try:
            photos_map = await catalog_service.get_profiles_photos_batch(list(profile_names))
        except Exception:
            pass
            
    # Set has_photo = True only if all profiles in the combination have photos
    for item in recent:
        profile_str = item.get("profile", "")
        if not profile_str or profile_str == "—":
            item["has_photo"] = False
        else:
            parts = [p.strip() for p in re.split(r'[+/]', profile_str) if p.strip()]
            if not parts:
                item["has_photo"] = False
            else:
                item["has_photo"] = all(bool(photos_map.get(part, {}).get("thumb")) for part in parts)
                
    return recent


@router.get("/recent-missing")
async def get_recent_missing_profiles(
    limit: int = Query(default=50, ge=1, le=200, description="Max results")
):
    """
    Get recent unique profiles that don't have photos.
    
    Combines Excel data with profile database to find
    recently used profiles that need documentation.
    """
    # Fetch all profiles with photos from DB
    async with get_session() as sess:
        stmt = select(Profile).where(Profile.photo_thumb.isnot(None), Profile.photo_thumb != '')
        result = await sess.execute(stmt)
        profiles_with_photos = result.scalars().all()
        
    db_names_with_photos = {p.name.lower() for p in profiles_with_photos}
    db_norm_with_photos = {normalize_text(p.name) for p in profiles_with_photos}
    
    def has_photo_sync(profile_str: str) -> bool:
        if not profile_str or profile_str == "—":
            return False
            
        parts = [p.strip() for p in re.split(r'[+/]', profile_str) if p.strip()]
        if not parts:
            return False
            
        # Return True only if ALL parts have photos (so the combination has photos)
        for name in parts:
            if name.lower() in db_names_with_photos:
                continue
            norm = normalize_text(name)
            if norm in db_norm_with_photos:
                continue
            return False
        return True
        
    # Get recent missing profiles using the sync checker
    missing = excel_service.get_recent_missing_profiles(limit=limit, profile_checker=has_photo_sync)
    
    # Mark has_photo = False for all missing profiles
    for item in missing:
        item["has_photo"] = False
        
    return missing


@router.get("/search-duplicates", response_model=list[ProfileSearchResult])
async def search_duplicates(
    q: str = Query(..., min_length=1, description="Search query"),
    threshold: float = Query(default=0.6, ge=0.0, le=1.0, description="Similarity threshold"),
    limit: int = Query(default=20, ge=1, le=100, description="Max results")
):
    """
    Find profiles with similar names using fuzzy matching.
    
    Useful for finding potential duplicates or variations
    of the same profile name.
    """
    return await catalog_service.search_duplicates(
        query=q,
        threshold=threshold,
        limit=limit
    )
