"""
Catalog API routes dispatcher - redirects calls to local SQLite or KTM-2000 API implementation.
"""
from typing import Optional
from fastapi import APIRouter, Query, UploadFile, File, Form, HTTPException

from app.core.config import settings
from app.api.routes import catalog_local, catalog_ktm
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
    if settings.USE_KTM_API:
        return await catalog_ktm.search_profiles(q=q, limit=limit)
    return await catalog_local.search_profiles(q=q, limit=limit)


@router.get("/all", response_model=list[ProfileResponse])
async def get_all_profiles(
    limit: int = Query(default=500, ge=1, le=1000, description="Max results")
):
    if settings.USE_KTM_API:
        return await catalog_ktm.get_all_profiles(limit=limit)
    return await catalog_local.get_all_profiles(limit=limit)


@router.get("/{name}", response_model=ProfileResponse)
async def get_profile(name: str):
    if settings.USE_KTM_API:
        return await catalog_ktm.get_profile(name=name)
    return await catalog_local.get_profile(name=name)


@router.post("", response_model=ProfileResponse)
async def create_or_update_profile(data: ProfileCreate):
    if settings.USE_KTM_API:
        return await catalog_ktm.create_or_update_profile(data=data)
    return await catalog_local.create_or_update_profile(data=data)


@router.post("/{name}/photo")
async def upload_photo(
    name: str,
    file: UploadFile = File(..., description="Full-size image file"),
    thumbnail: UploadFile = File(None, description="Custom thumbnail (optional)")
):
    if settings.USE_KTM_API:
        return await catalog_ktm.upload_photo(name=name, file=file, thumbnail=thumbnail)
    return await catalog_local.upload_photo(name=name, file=file, thumbnail=thumbnail)


@router.put("/{name}/thumbnail")
async def update_thumbnail(
    name: str,
    file: UploadFile = File(..., description="New thumbnail image")
):
    if settings.USE_KTM_API:
        return await catalog_ktm.update_thumbnail(name=name, file=file)
    return await catalog_local.update_thumbnail(name=name, file=file)


@router.delete("/{name}/photo")
async def delete_photo(name: str):
    if settings.USE_KTM_API:
        return await catalog_ktm.delete_photo(name=name)
    return await catalog_local.delete_photo(name=name)


@router.delete("/{name}/photo/full")
async def delete_full_photo(name: str):
    if settings.USE_KTM_API:
        return await catalog_ktm.delete_full_photo(name=name)
    return await catalog_local.delete_full_photo(name=name)


@router.delete("/{name}/photo/thumbnail")
async def delete_thumbnail(name: str):
    if settings.USE_KTM_API:
        return await catalog_ktm.delete_thumbnail(name=name)
    return await catalog_local.delete_thumbnail(name=name)


@router.put("/{profile_id}", response_model=ProfileResponse)
async def update_profile(profile_id: int, data: ProfileCreate):
    if settings.USE_KTM_API:
        return await catalog_ktm.update_profile(profile_id=profile_id, data=data)
    return await catalog_local.update_profile(profile_id=profile_id, data=data)


@router.delete("/{profile_id}")
async def delete_profile(profile_id: int):
    if settings.USE_KTM_API:
        return await catalog_ktm.delete_profile(profile_id=profile_id)
    return await catalog_local.delete_profile(profile_id=profile_id)
