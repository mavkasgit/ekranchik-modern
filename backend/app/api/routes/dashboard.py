"""
Dashboard API routes.
"""
import re
from datetime import datetime
from typing import Optional, Tuple, List

from fastapi import APIRouter, Query, HTTPException

from app.services.excel_service import excel_service
from app.services.ftp_service import ftp_service
from app.services.catalog_service import catalog_service
from app.schemas.dashboard import (
    DashboardResponse,
    HangerData,
    FileStatus,
    FTPStatus,
    UnloadEvent
)
from app.schemas.profile import ProfileInfo

router = APIRouter(prefix="/dashboard", tags=["dashboard"])

# Processing keywords to extract from profile names
PROCESSING_KEYWORDS = ['окно', 'греб', 'гребенка', 'сверло', 'фреза', 'паз']


def parse_profile_name(name: str) -> Tuple[str, List[str]]:
    """
    Parse profile name and extract processing keywords.
    
    "СРП228 окно" → ("СРП228", ["окно"])
    "юп-3233 греб + сверло" → ("юп-3233", ["греб", "сверло"])
    """
    if not name:
        return "", []
    
    found_processing = []
    clean_name = name
    
    for keyword in PROCESSING_KEYWORDS:
        pattern = r'\b' + re.escape(keyword) + r'\b'
        if re.search(pattern, clean_name, re.IGNORECASE):
            # Normalize "гребенка" to "греб"
            if keyword == 'гребенка':
                found_processing.append('греб')
            else:
                found_processing.append(keyword)
            # Remove keyword from name
            clean_name = re.sub(pattern, '', clean_name, flags=re.IGNORECASE)
    
    # Clean up the name
    clean_name = re.sub(r'\s+', ' ', clean_name).strip()
    clean_name = clean_name.rstrip('+,;').strip()
    
    return clean_name, found_processing


@router.get("", response_model=DashboardResponse)
async def get_dashboard(
    days: Optional[int] = Query(default=7, ge=1, le=365, description="Days to look back"),
    limit: Optional[int] = Query(default=100, ge=1, le=1000, description="Max records")
):
    """
    Get dashboard data with production records.
    
    Returns recent production data from Excel file with profile photos from catalog.
    """
    try:
        products = excel_service.get_products(limit=limit, days=days)
        
        # Collect all unique profile names for batch lookup
        profile_names = set()
        for product in products:
            profile = str(product.get('profile', ''))
            if profile and profile != '—':
                # Handle multiple profiles separated by +
                for p in profile.replace('+', ',').split(','):
                    p = p.strip()
                    if p:
                        profile_names.add(p)
        
        # Batch lookup photos from catalog
        photos_map = await catalog_service.get_profiles_photos_batch(list(profile_names))
        
        # Convert to HangerData format with photos
        hanger_data = []
        for i, product in enumerate(products):
            profile_str = str(product.get('profile', product.get('Профиль', '—')))
            
            # Build profiles_info with photos and processing keywords
            profiles_info = []
            if profile_str and profile_str != '—':
                for p in profile_str.replace('+', ',').split(','):
                    p = p.strip()
                    if p:
                        # Extract processing keywords from profile name
                        clean_name, processing = parse_profile_name(p)
                        
                        # Look up photo by original name first, then clean name
                        photo_info = photos_map.get(p, {})
                        if not photo_info and clean_name != p:
                            photo_info = photos_map.get(clean_name, {})
                        
                        profiles_info.append(ProfileInfo(
                            name=p,
                            canonical_name=photo_info.get('name', clean_name or p),
                            has_photo=bool(photo_info.get('thumb')),
                            photo_thumb=photo_info.get('thumb'),
                            photo_full=photo_info.get('full'),
                            processing=processing
                        ))
            
            hanger = HangerData(
                number=str(product.get('number', product.get('№', i + 1))),
                date=str(product.get('date', product.get('Дата', ''))),
                time=str(product.get('time', product.get('Время', ''))),
                client=str(product.get('client', product.get('Клиент', '—'))),
                profile=profile_str,
                profiles_info=profiles_info,
                color=str(product.get('color', product.get('Цвет', '—'))),
                lamels_qty=product.get('lamels_qty', product.get('Кол-во ламелей', 0)),
                kpz_number=str(product.get('kpz_number', product.get('КПЗ', '—'))),
                material_type=str(product.get('material_type', product.get('Тип материала', '—')))
            )
            hanger_data.append(hanger)
        
        return DashboardResponse(
            success=True,
            products=hanger_data,
            total=len(hanger_data),
            total_all=len(products),
            days_filter=days
        )
    except Exception as e:
        return DashboardResponse(
            success=False,
            error=str(e)
        )


@router.get("/status/file", response_model=FileStatus)
async def get_file_status():
    """
    Get Excel file status.
    Detects if file is open by checking for Excel temp file (~$filename).
    """
    from app.core.config import settings
    
    try:
        path = settings.excel_path
        
        # Check if path is configured
        if not path:
            return FileStatus(
                is_open=False,
                status_text="Путь не настроен",
                error="EXCEL_FILE_PATH не указан в .env"
            )
        
        # Check if file exists
        if not path.exists():
            return FileStatus(
                is_open=False,
                file_name=path.name,
                status_text="Файл не найден",
                error=f"Файл не найден: {path}"
            )
        
        stat = path.stat()
        
        # Check if Excel has the file open by looking for temp file
        # Excel creates ~$filename.xlsm when file is open
        temp_file = path.parent / f"~${path.name}"
        is_open = temp_file.exists()
        
        status_text = "Открыт в Excel" if is_open else "Закрыт"
        
        return FileStatus(
            is_open=is_open,
            last_modified=datetime.fromtimestamp(stat.st_mtime),
            file_name=path.name,
            status_text=status_text
        )
    except Exception as e:
        return FileStatus(
            status_text="Ошибка",
            error=str(e)
        )


@router.get("/status/ftp", response_model=FTPStatus)
async def get_ftp_status():
    """
    Get FTP connection status.
    """
    try:
        # Try to connect
        client = await ftp_service.connect()
        connected = client is not None
        
        if client:
            await client.quit()
        
        return FTPStatus(
            connected=connected,
            last_check=datetime.now()
        )
    except Exception as e:
        return FTPStatus(
            connected=False,
            last_check=datetime.now(),
            error=str(e)
        )


@router.get("/events", response_model=list[UnloadEvent])
async def get_today_events():
    """
    Get today's unload events from FTP.
    """
    try:
        content = await ftp_service.read_today_log()
        events = ftp_service.parse_unload_events(content)
        return events
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
