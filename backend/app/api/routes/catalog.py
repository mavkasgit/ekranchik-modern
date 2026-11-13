"""
Catalog API routes - read-only showcase and the single local write.

Данные артикула принадлежат каталогу-источнику (спека 0002, ADR 0010):
маршруты каталога только читают, а локально меняется одно примечание.
"""

from fastapi import APIRouter, HTTPException, Query

from app.schemas.profile import ProfileNotesUpdate, ProfileResponse, ProfileSearchResult
from app.services.catalog_service import catalog_service

router = APIRouter(prefix="/catalog", tags=["catalog"])


@router.get("", response_model=list[ProfileSearchResult])
async def search_profiles(
    q: str = Query(..., min_length=1, description="Search query"),
    limit: int = Query(default=50, ge=1, le=200, description="Max results"),
):
    """
    Search profiles by name, notes, or numeric values.

    Supports Latin/Cyrillic equivalence - searching for 'ALS' will find 'АЛС'.
    Results are prioritized: exact matches first, then partial matches.
    """
    results = await catalog_service.search_profiles(query=q, limit=limit)
    return results


@router.get("/all", response_model=list[ProfileResponse])
async def get_all_profiles(limit: int = Query(default=500, ge=1, le=1000, description="Max results")):
    """
    Get all profiles.
    """
    return await catalog_service.get_all_profiles(limit=limit)


@router.get("/{name}", response_model=ProfileResponse)
async def get_profile(name: str):
    """
    Get a profile by exact name.
    """
    profile = await catalog_service.get_profile(name=name)
    if not profile:
        raise HTTPException(status_code=404, detail="Profile not found")
    return profile


@router.patch("/{profile_id}/notes", response_model=ProfileResponse)
async def update_profile_notes(profile_id: int, data: ProfileNotesUpdate):
    """
    Update the note of a profile.

    Примечание — единственные локальные данные каталога: поля артикула
    приходят из каталога-источника и здесь не меняются.
    """
    profile = await catalog_service.update_notes(profile_id=profile_id, notes=data.notes)
    if not profile:
        raise HTTPException(status_code=404, detail="Profile not found")
    return profile
