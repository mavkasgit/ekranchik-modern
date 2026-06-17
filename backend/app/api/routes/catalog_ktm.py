"""
Catalog API routes - KTM-2000 API integration implementation.
"""
from typing import Optional
from fastapi import APIRouter, Query, UploadFile, File, HTTPException

from app.services.ktm_api_service import ktm_api_service
from app.schemas.profile import (
    ProfileResponse,
    ProfileCreate,
    ProfileSearchResult
)

router = APIRouter(prefix="/catalog", tags=["catalog"])


@router.get("", response_model=list[ProfileSearchResult])
async def search_profiles(
    q: str = Query(..., min_length=1, description="Search query"),
    limit: int = Query(default=50, ge=1, le=200, description="Max results")
):
    results = await ktm_api_service.search_profiles(query=q)
    return [ProfileSearchResult(**r) for r in results[:limit]]


@router.get("/all", response_model=list[ProfileResponse])
async def get_all_profiles(
    limit: int = Query(default=500, ge=1, le=1000, description="Max results")
):
    results = await ktm_api_service.get_all_profiles()
    return [ProfileResponse(**r) for r in results[:limit]]


@router.get("/{name}", response_model=ProfileResponse)
async def get_profile(name: str):
    profile = await ktm_api_service.get_profile(name=name)
    if not profile:
        raise HTTPException(status_code=404, detail="Profile not found")
    return ProfileResponse(**profile)


@router.post("", response_model=ProfileResponse)
async def create_or_update_profile(data: ProfileCreate):
    raise HTTPException(status_code=403, detail="Редактирование запрещено в режиме API KTM-2000")


@router.post("/{name}/photo")
async def upload_photo(name: str, file: UploadFile = File(...), thumbnail: UploadFile = File(None)):
    raise HTTPException(status_code=403, detail="Редактирование запрещено в режиме API KTM-2000")


@router.put("/{name}/thumbnail")
async def update_thumbnail(name: str, file: UploadFile = File(...)):
    raise HTTPException(status_code=403, detail="Редактирование запрещено в режиме API KTM-2000")


@router.delete("/{name}/photo")
async def delete_photo(name: str):
    raise HTTPException(status_code=403, detail="Редактирование запрещено в режиме API KTM-2000")


@router.delete("/{name}/photo/full")
async def delete_full_photo(name: str):
    raise HTTPException(status_code=403, detail="Редактирование запрещено в режиме API KTM-2000")


@router.delete("/{name}/photo/thumbnail")
async def delete_thumbnail(name: str):
    raise HTTPException(status_code=403, detail="Редактирование запрещено в режиме API KTM-2000")


@router.put("/{profile_id}", response_model=ProfileResponse)
async def update_profile(profile_id: int, data: ProfileCreate):
    raise HTTPException(status_code=403, detail="Редактирование запрещено в режиме API KTM-2000")


@router.delete("/{profile_id}")
async def delete_profile(profile_id: int):
    raise HTTPException(status_code=403, detail="Редактирование запрещено в режиме API KTM-2000")
