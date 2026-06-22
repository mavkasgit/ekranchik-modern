"""
Catalog API routes - profile search and photo management.
"""
from typing import Optional
import io
import zipfile
import sqlite3
from pathlib import Path
from tempfile import TemporaryDirectory

from fastapi import APIRouter, Query, UploadFile, File, Form, HTTPException
from fastapi.responses import StreamingResponse

from app.services.catalog_service import catalog_service
from app.core.config import settings
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


@router.delete("/{name}/photo/full")
async def delete_full_photo(name: str):
    """
    Delete only the full photo for a profile (keeps thumbnail).
    """
    deleted = await catalog_service.delete_full_photo(profile_name=name)
    if not deleted:
        raise HTTPException(status_code=404, detail="Profile not found")
    
    return {"success": True, "message": "Full photo deleted"}


@router.delete("/{name}/photo/thumbnail")
async def delete_thumbnail(name: str):
    """
    Delete only the thumbnail for a profile (keeps full photo).
    """
    deleted = await catalog_service.delete_thumbnail(profile_name=name)
    if not deleted:
        raise HTTPException(status_code=404, detail="Profile not found")
    
    return {"success": True, "message": "Thumbnail deleted"}


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


@router.get("/export/zip")
async def export_catalog_zip():
    """
    Export the profile catalog as a ZIP archive containing:
    1. ekranchik.db database renamed to profiles.db (using sqlite3 backup to ensure integrity)
    2. images/ directory with all profile photos
    """
    import logging
    logger = logging.getLogger(__name__)
    
    # Resolve the database path from settings.DATABASE_URL
    db_url = settings.DATABASE_URL
    if db_url.startswith("sqlite+aiosqlite:///"):
        db_path_str = db_url.replace("sqlite+aiosqlite:///", "")
    elif db_url.startswith("sqlite:///"):
        db_path_str = db_url.replace("sqlite:///", "")
    else:
        db_path_str = "../static/ekranchik.db"
        
    backend_dir = Path(__file__).resolve().parent.parent.parent.parent
    db_path = (backend_dir / db_path_str).resolve()
    
    if not db_path.exists():
        db_path = (Path(settings.STATIC_DIR) / "ekranchik.db").resolve()
        
    logger.info(f"[export_catalog_zip] db_path={db_path}, exists={db_path.exists()}")
    
    images_dir = Path(settings.IMAGES_DIR).resolve()
    logger.info(f"[export_catalog_zip] images_dir={images_dir}, exists={images_dir.exists()}")
    
    if not db_path.exists():
        raise HTTPException(status_code=404, detail="Database file not found")
        
    try:
        zip_buffer = io.BytesIO()
        
        with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
            # 1. Create a safe backup of the sqlite database using sqlite3 backup API
            with TemporaryDirectory() as tmpdir:
                temp_db_path = Path(tmpdir) / "profiles.db"
                
                src_conn = sqlite3.connect(str(db_path))
                dst_conn = sqlite3.connect(str(temp_db_path))
                
                # Run the backup synchronously
                src_conn.backup(dst_conn)
                
                dst_conn.close()
                src_conn.close()
                
                # Read backup bytes and write to ZIP
                db_bytes = temp_db_path.read_bytes()
                zf.writestr("profiles.db", db_bytes)
                logger.info(f"[export_catalog_zip] Added profiles.db to ZIP, size={len(db_bytes)} bytes")
            
            # 2. Add images to the ZIP archive
            if images_dir.exists() and images_dir.is_dir():
                image_count = 0
                for file_path in images_dir.rglob("*"):
                    if file_path.is_file() and file_path.suffix.lower() in ['.jpg', '.jpeg', '.png', '.webp', '.gif']:
                        arcname = Path("images") / file_path.name
                        zf.write(str(file_path), str(arcname))
                        image_count += 1
                logger.info(f"[export_catalog_zip] Added {image_count} images to ZIP")
                
        zip_buffer.seek(0)
        
        return StreamingResponse(
            zip_buffer,
            media_type="application/x-zip-compressed",
            headers={"Content-Disposition": "attachment; filename=ekranchik_catalog.zip"}
        )
    except Exception as e:
        logger.error(f"[export_catalog_zip] Error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to generate export zip: {str(e)}")
