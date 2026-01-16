"""
Catalog API routes - profile search and photo management.
"""
from typing import Optional

from fastapi import APIRouter, Query, UploadFile, File, Form, HTTPException

from app.services.catalog_service import catalog_service
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
    """
    Search profiles by name, notes, or numeric values.
    
    Supports Latin/Cyrillic equivalence - searching for 'ALS' will find 'АЛС'.
    Results are prioritized: exact matches first, then partial matches.
    """
    results = await catalog_service.search_profiles(query=q, limit=limit)
    return results


@router.get("/all", response_model=list[ProfileResponse])
async def get_all_profiles(
    limit: int = Query(default=500, ge=1, le=1000, description="Max results")
):
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


@router.post("", response_model=ProfileResponse)
async def create_or_update_profile(data: ProfileCreate):
    """
    Create a new profile or update existing one.
    """
    return await catalog_service.create_or_update_profile(data=data)


@router.post("/{name}/photo")
async def upload_photo(
    name: str,
    file: UploadFile = File(..., description="Full-size image file"),
    thumbnail: UploadFile = File(None, description="Custom thumbnail (optional)")
):
    """
    Upload a photo for a profile.
    
    If thumbnail is provided, it will be used as-is.
    Otherwise, thumbnail is auto-generated from full image.
    
    Supported formats: JPEG, PNG, GIF, WebP.
    Max size: 10MB.
    """
    import logging
    logger = logging.getLogger(__name__)
    logger.info(f"[upload_photo API] name={name}, file={file.filename}, thumbnail={thumbnail.filename if thumbnail else None}")
    
    # Validate file type
    if not file.content_type or not file.content_type.startswith('image/'):
        raise HTTPException(status_code=400, detail="File must be an image")
    
    # Read file content
    full_content = await file.read()
    thumb_content = None
    
    logger.info(f"[upload_photo API] Read {len(full_content)} bytes from file")
    
    if thumbnail:
        if not thumbnail.content_type or not thumbnail.content_type.startswith('image/'):
            raise HTTPException(status_code=400, detail="Thumbnail must be an image")
        thumb_content = await thumbnail.read()
        logger.info(f"[upload_photo API] Read {len(thumb_content)} bytes from thumbnail")
    
    try:
        thumb_path, full_path = await catalog_service.upload_photo(
            profile_name=name,
            image_data=full_content,
            filename=file.filename or "photo.jpg",
            thumbnail_data=thumb_content
        )
        
        logger.info(f"[upload_photo API] Success! thumb={thumb_path}, full={full_path}")
        
        return {
            "success": True,
            "thumbnail": thumb_path,
            "full": full_path
        }
    except ValueError as e:
        logger.error(f"[upload_photo API] Error: {e}")
        raise HTTPException(status_code=400, detail=str(e))


@router.put("/{name}/thumbnail")
async def update_thumbnail(
    name: str,
    file: UploadFile = File(..., description="New thumbnail image")
):
    """
    Update only the thumbnail for a profile (keeps full image).
    """
    if not file.content_type or not file.content_type.startswith('image/'):
        raise HTTPException(status_code=400, detail="File must be an image")
    
    content = await file.read()
    
    try:
        thumb_path = await catalog_service.update_thumbnail(
            profile_name=name,
            thumbnail_data=content
        )
        return {"success": True, "thumbnail": thumb_path}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.delete("/{name}/photo")
async def delete_photo(name: str):
    """
    Delete photos for a profile.
    """
    deleted = await catalog_service.delete_photo(profile_name=name)
    if not deleted:
        raise HTTPException(status_code=404, detail="Profile not found")
    
    return {"success": True, "message": "Photos deleted"}


@router.put("/{profile_id}", response_model=ProfileResponse)
async def update_profile(profile_id: int, data: ProfileCreate):
    """
    Update an existing profile by ID.
    """
    from app.schemas.profile import ProfileUpdate
    update_data = ProfileUpdate(**data.model_dump())
    result = await catalog_service.update_profile(profile_id=profile_id, data=update_data)
    if not result:
        raise HTTPException(status_code=404, detail="Profile not found")
    return result


@router.delete("/{profile_id}")
async def delete_profile(profile_id: int):
    """
    Delete a profile by ID.
    """
    deleted = await catalog_service.delete_profile(profile_id=profile_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Profile not found")
    
    return {"success": True, "message": "Profile deleted"}
