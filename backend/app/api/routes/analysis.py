"""
Analysis API routes - missing photos, duplicates, recent profiles.
"""
from typing import Optional

from fastapi import APIRouter, Query

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
    return excel_service.get_recent_profiles(limit=limit)


@router.get("/recent-missing")
async def get_recent_missing_profiles(
    limit: int = Query(default=50, ge=1, le=200, description="Max results")
):
    """
    Get recent unique profiles that don't have photos.
    
    Combines Excel data with profile database to find
    recently used profiles that need documentation.
    """
    # Create checker function
    async def has_photo(name: str) -> bool:
        profile = await catalog_service.get_profile(name)
        return profile is not None and bool(profile.photo_thumb)
    
    # Note: This is sync version for now
    return excel_service.get_recent_missing_profiles(limit=limit)


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
