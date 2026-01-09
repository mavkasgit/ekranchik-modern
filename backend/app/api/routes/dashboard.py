"""
Dashboard API routes.
"""
import re
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional, Tuple, List

from fastapi import APIRouter, Query, HTTPException, BackgroundTasks
from pydantic import BaseModel

logger = logging.getLogger(__name__)

from app.core.config import settings
from app.services.excel_service import excel_service
from app.services.catalog_service import catalog_service
from app.schemas.dashboard import (
    DashboardResponse,
    HangerData,
    FileStatus,
    MatchedUnloadEvent
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
    limit: Optional[int] = Query(default=100, ge=1, le=1000, description="Max records"),
    unloading_limit: Optional[int] = Query(default=10, ge=1, le=500, description="Max unloading records")
):
    """
    Get dashboard data with production records.
    
    Returns recent production data from Excel file with profile photos from catalog.
    Also returns unloading_products - rows where time is filled (product unloaded).
    """
    try:
        products = excel_service.get_products(limit=limit, days=days, loading_only=True)
        unloading_raw = excel_service.get_unloading_products(limit=unloading_limit)
        
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
                material_type=str(product.get('material_type', product.get('Тип материала', '—'))),
                is_defect=product.get('is_defect', False)
            )
            hanger_data.append(hanger)
        
        # Process unloading products (rows with time filled)
        # Collect profile names from unloading for photo lookup
        for product in unloading_raw:
            profile = str(product.get('profile', ''))
            if profile and profile != '—':
                for p in profile.replace('+', ',').split(','):
                    p = p.strip()
                    if p:
                        profile_names.add(p)
        
        # Re-fetch photos if new profiles found
        if unloading_raw:
            photos_map = await catalog_service.get_profiles_photos_batch(list(profile_names))
        
        unloading_data = []
        for i, product in enumerate(unloading_raw):
            profile_str = str(product.get('profile', product.get('Профиль', '—')))
            
            profiles_info = []
            if profile_str and profile_str != '—':
                for p in profile_str.replace('+', ',').split(','):
                    p = p.strip()
                    if p:
                        clean_name, processing = parse_profile_name(p)
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
                material_type=str(product.get('material_type', product.get('Тип материала', '—'))),
                is_defect=product.get('is_defect', False)
            )
            unloading_data.append(hanger)
        
        return DashboardResponse(
            success=True,
            products=hanger_data,
            unloading_products=unloading_data,
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


@router.get("/status/opcua", response_model=FileStatus)
async def get_opcua_status():
    """
    Get OPC UA connection status.
    """
    try:
        from app.services.opcua_service import opcua_service
        
        # Check if OPC UA is connected
        connected = opcua_service.is_connected
        
        # Try to connect if not connected
        if not connected:
            connected = await opcua_service.connect()
        
        return FileStatus(
            is_open=connected,
            status_text="Подключено" if connected else "Отключено"
        )
    except Exception as e:
        return FileStatus(
            is_open=False,
            status_text="Ошибка",
            error=str(e)
        )



@router.get("/unload-matched", response_model=list[MatchedUnloadEvent])
async def get_matched_unload_events(
    limit: int = Query(default=100, ge=1, le=500, description="Max events to return")
):
    """
    Get unload events matched with Excel data.
    
    Uses OPC UA unload service to get events.
    Matches each event with Excel data by hanger number.
    Returns events with entry/exit times and product info.
    """
    try:
        from app.services.unload_service import unload_service
        
        # Get unload events from OPC UA service
        events = unload_service.get_unload_events(limit=limit)
        
        if not events:
            return []
        
        # Get all products from Excel for matching
        products = excel_service.get_products(limit=1000, days=30)
        
        # Build lookup by hanger number - store ALL products for each hanger
        products_by_hanger: dict[str, list] = {}
        for p in products:
            num = str(p.get('number', ''))
            if num:
                if num not in products_by_hanger:
                    products_by_hanger[num] = []
                products_by_hanger[num].append(p)
        
        # Get photos for profiles
        profile_names = set()
        for p in products:
            profile = str(p.get('profile', ''))
            if profile and profile != '—':
                for name in profile.replace('+', ',').split(','):
                    name = name.strip()
                    if name:
                        profile_names.add(name)
        
        photos_map = await catalog_service.get_profiles_photos_batch(list(profile_names))
        
        # Helper to parse date string to comparable format
        def parse_date(date_str: str) -> tuple:
            """Parse DD.MM.YYYY or DD.MM.YY to (year, month, day) tuple for comparison."""
            if not date_str:
                return (0, 0, 0)
            try:
                parts = date_str.split('.')
                if len(parts) == 3:
                    day, month, year = int(parts[0]), int(parts[1]), int(parts[2])
                    if year < 100:
                        year += 2000
                    return (year, month, day)
            except:
                pass
            return (0, 0, 0)
        
        def parse_time(time_str: str) -> tuple:
            """Parse HH:MM:SS or HH:MM to (hour, minute, second) tuple."""
            if not time_str:
                return (0, 0, 0)
            try:
                parts = time_str.split(':')
                hour = int(parts[0]) if len(parts) > 0 else 0
                minute = int(parts[1]) if len(parts) > 1 else 0
                second = int(parts[2]) if len(parts) > 2 else 0
                return (hour, minute, second)
            except:
                pass
            return (0, 0, 0)
        
        def date_to_days(date_tuple: tuple) -> int:
            """Convert date tuple to days for comparison."""
            year, month, day = date_tuple
            return year * 365 + month * 30 + day
        
        def datetime_to_seconds(date_tuple: tuple, time_tuple: tuple) -> float:
            """Convert date+time to total seconds for comparison."""
            days = date_to_days(date_tuple)
            secs = time_tuple[0] * 3600 + time_tuple[1] * 60 + time_tuple[2]
            return days * 86400 + secs
        
        def make_product_key(p: dict) -> str:
            """Create unique key for product to track used entries."""
            return f"{p.get('date', '')}|{p.get('time', '')}|{p.get('number', '')}"
        
        # Track used entries to avoid matching same entry twice
        used_entries: set = set()
        
        # Sort events by time (oldest first) for greedy matching
        events_to_match = sorted(
            events[-limit:],
            key=lambda e: datetime_to_seconds(
                parse_date(e.date or ""),
                parse_time(e.time)
            )
        )
        
        # Match events with products (greedy: oldest exit first)
        matched = []
        for event in events_to_match:
            hanger_num = str(event.hanger)
            candidates = products_by_hanger.get(hanger_num, [])
            
            # Find best match: entry must be BEFORE exit, closest to exit
            exit_date_tuple = parse_date(event.date or "")
            exit_time_tuple = parse_time(event.time)
            exit_seconds = datetime_to_seconds(exit_date_tuple, exit_time_tuple)
            
            product = None
            best_diff = None
            
            for p in candidates:
                # Skip already used entries
                p_key = make_product_key(p)
                if p_key in used_entries:
                    continue
                
                entry_date = str(p.get('date', ''))
                entry_time = str(p.get('time', ''))
                
                # Skip entries without time (not yet started)
                if not entry_time or entry_time == '—':
                    continue
                
                entry_date_tuple = parse_date(entry_date)
                entry_time_tuple = parse_time(entry_time)
                entry_seconds = datetime_to_seconds(entry_date_tuple, entry_time_tuple)
                
                # Entry must be BEFORE exit (подвес не может выйти раньше чем вошёл)
                if entry_seconds >= exit_seconds:
                    continue
                
                # Calculate difference (exit - entry, always positive now)
                diff = exit_seconds - entry_seconds
                
                # Skip if more than 2 days apart
                if diff > 2 * 86400:
                    continue
                
                # Take the closest entry (smallest diff)
                if best_diff is None or diff < best_diff:
                    best_diff = diff
                    product = p
            
            # Mark entry as used
            if product:
                used_entries.add(make_product_key(product))
            
            # Build profiles_info
            profiles_info = []
            if product:
                profile_str = str(product.get('profile', ''))
                if profile_str and profile_str != '—':
                    for p in profile_str.replace('+', ',').split(','):
                        p = p.strip()
                        if p:
                            clean_name, processing = parse_profile_name(p)
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
            
            matched.append(MatchedUnloadEvent(
                exit_date=event.date or datetime.now().strftime("%d.%m.%Y"),
                exit_time=event.time,
                hanger=event.hanger,
                entry_date=str(product.get('date', '')) if product else None,
                entry_time=str(product.get('time', '')) if product else None,
                client=str(product.get('client', '—')) if product else '—',
                profile=str(product.get('profile', '—')) if product else '—',
                profiles_info=profiles_info,
                color=str(product.get('color', '—')) if product else '—',
                lamels_qty=product.get('lamels_qty', 0) if product else 0,
                kpz_number=str(product.get('kpz_number', '—')) if product else '—',
                material_type=str(product.get('material_type', '—')) if product else '—',
            ))
        
        # Return newest first
        matched.reverse()
        return matched
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))





@router.get("/opcua-unload-matched", response_model=list[MatchedUnloadEvent])
async def get_opcua_matched_unload_events(
    limit: int = Query(default=100, ge=1, le=500, description="Max events to return")
):
    """
    Get OPC UA unload events (from Bath[34]) matched with Excel data.
    
    Uses unload_service to get events from Bath[34] exit detection.
    Matches each event with Excel data by hanger number.
    Returns events with entry/exit times and product info.
    """
    try:
        from app.services.unload_service import unload_service
        from app.services.opcua_poller import opcua_poller
        
        # Get unload events from OPC UA service
        events = unload_service.get_unload_events(limit=limit)
        
        # Also check poller cache
        if not events:
            events = opcua_poller.cached_events[-limit:]
        
        if not events:
            return []
        
        # Get all products from Excel for matching
        products = excel_service.get_products(limit=1000, days=30)
        
        # Build lookup by hanger number
        products_by_hanger: dict[str, list] = {}
        for p in products:
            num = str(p.get('number', ''))
            if num:
                if num not in products_by_hanger:
                    products_by_hanger[num] = []
                products_by_hanger[num].append(p)
        
        # Get photos for profiles
        profile_names = set()
        for p in products:
            profile = str(p.get('profile', ''))
            if profile and profile != '—':
                for name in profile.replace('+', ',').split(','):
                    name = name.strip()
                    if name:
                        profile_names.add(name)
        
        photos_map = await catalog_service.get_profiles_photos_batch(list(profile_names))
        
        # Helper functions
        def parse_date(date_str: str) -> tuple:
            if not date_str:
                return (0, 0, 0)
            try:
                parts = date_str.split('.')
                if len(parts) == 3:
                    day, month, year = int(parts[0]), int(parts[1]), int(parts[2])
                    if year < 100:
                        year += 2000
                    return (year, month, day)
            except:
                pass
            return (0, 0, 0)
        
        def parse_time(time_str: str) -> tuple:
            if not time_str:
                return (0, 0, 0)
            try:
                parts = time_str.split(':')
                hour = int(parts[0]) if len(parts) > 0 else 0
                minute = int(parts[1]) if len(parts) > 1 else 0
                second = int(parts[2]) if len(parts) > 2 else 0
                return (hour, minute, second)
            except:
                pass
            return (0, 0, 0)
        
        def date_to_days(date_tuple: tuple) -> int:
            year, month, day = date_tuple
            return year * 365 + month * 30 + day
        
        def datetime_to_seconds(date_tuple: tuple, time_tuple: tuple) -> float:
            days = date_to_days(date_tuple)
            secs = time_tuple[0] * 3600 + time_tuple[1] * 60 + time_tuple[2]
            return days * 86400 + secs
        
        def make_product_key(p: dict) -> str:
            return f"{p.get('date', '')}|{p.get('time', '')}|{p.get('number', '')}"
        
        # Track used entries
        used_entries: set = set()
        
        # Sort events by time (oldest first) for greedy matching
        events_to_match = sorted(
            events,
            key=lambda e: datetime_to_seconds(
                parse_date(e.date or ""),
                parse_time(e.time)
            )
        )
        
        # Match events with products
        matched = []
        for event in events_to_match:
            hanger_num = str(event.hanger)
            candidates = products_by_hanger.get(hanger_num, [])
            
            exit_date_tuple = parse_date(event.date or "")
            exit_time_tuple = parse_time(event.time)
            exit_seconds = datetime_to_seconds(exit_date_tuple, exit_time_tuple)
            
            product = None
            best_diff = None
            
            for p in candidates:
                p_key = make_product_key(p)
                if p_key in used_entries:
                    continue
                
                entry_date = str(p.get('date', ''))
                entry_time = str(p.get('time', ''))
                
                if not entry_time or entry_time == '—':
                    continue
                
                entry_date_tuple = parse_date(entry_date)
                entry_time_tuple = parse_time(entry_time)
                entry_seconds = datetime_to_seconds(entry_date_tuple, entry_time_tuple)
                
                # Entry must be BEFORE exit
                if entry_seconds >= exit_seconds:
                    continue
                
                diff = exit_seconds - entry_seconds
                
                # Skip if more than 2 days apart
                if diff > 2 * 86400:
                    continue
                
                if best_diff is None or diff < best_diff:
                    best_diff = diff
                    product = p
            
            if product:
                used_entries.add(make_product_key(product))
            
            # Build profiles_info
            profiles_info = []
            if product:
                profile_str = str(product.get('profile', ''))
                if profile_str and profile_str != '—':
                    for p in profile_str.replace('+', ',').split(','):
                        p = p.strip()
                        if p:
                            clean_name, processing = parse_profile_name(p)
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
            
            matched.append(MatchedUnloadEvent(
                exit_date=event.date or datetime.now().strftime("%d.%m.%Y"),
                exit_time=event.time,
                hanger=event.hanger,
                entry_date=str(product.get('date', '')) if product else None,
                entry_time=str(product.get('time', '')) if product else None,
                client=str(product.get('client', '—')) if product else '—',
                profile=str(product.get('profile', '—')) if product else '—',
                profiles_info=profiles_info,
                color=str(product.get('color', '—')) if product else '—',
                lamels_qty=product.get('lamels_qty', 0) if product else 0,
                kpz_number=str(product.get('kpz_number', '—')) if product else '—',
                material_type=str(product.get('material_type', '—')) if product else '—',
            ))
        
        # Return newest first
        matched.reverse()
        return matched
    except Exception as e:
        logger.error(f"[OPC UA Unload] Error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/opcua-unload-events")
async def get_opcua_unload_events(
    limit: int = Query(default=100, ge=1, le=500, description="Max events to return")
):
    """
    Get raw OPC UA unload events from Bath[34].
    """
    try:
        from app.services.unload_service import unload_service
        
        events = unload_service.get_events(limit=limit)
        
        return {
            "total": len(events),
            "events": [e.to_dict() for e in reversed(events)]  # Newest first
        }
    except Exception as e:
        logger.error(f"[OPC UA Unload] Error: {e}")
        raise HTTPException(status_code=500, detail=str(e))
