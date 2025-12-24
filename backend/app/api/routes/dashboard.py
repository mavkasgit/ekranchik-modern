"""
Dashboard API routes.
"""
import re
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional, Tuple, List

from fastapi import APIRouter, Query, HTTPException, BackgroundTasks

logger = logging.getLogger(__name__)
from pydantic import BaseModel

from app.core.config import settings
from app.services.excel_service import excel_service
from app.services.ftp_service import ftp_service
from app.services.ftp_poller import ftp_poller
from app.services.catalog_service import catalog_service
from app.schemas.dashboard import (
    DashboardResponse,
    HangerData,
    FileStatus,
    FTPStatus,
    UnloadEvent,
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


@router.get("/unload-matched", response_model=list[MatchedUnloadEvent])
async def get_matched_unload_events(
    limit: int = Query(default=100, ge=1, le=500, description="Max events to return")
):
    """
    Get unload events matched with Excel data.
    
    Uses cached events from FTP poller (or simulation).
    Matches each event with Excel data by hanger number.
    Returns events with entry/exit times and product info.
    """
    try:
        # Get unload events from cache (poller) or simulation
        if ftp_service.is_simulation:
            # Get ALL simulation events at once
            events = ftp_service.get_all_simulation_events()
            event_date = ftp_service._simulation_date
        else:
            # Use cached events from poller (already read from FTP)
            events = ftp_poller.cached_events
            event_date = None
            logger.debug(f"[API] Using {len(events)} cached events from poller")
        
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
                parse_date(e.date or event_date or ""),
                parse_time(e.time)
            )
        )
        
        # Match events with products (greedy: oldest exit first)
        matched = []
        for event in events_to_match:
            hanger_num = str(event.hanger)
            candidates = products_by_hanger.get(hanger_num, [])
            
            # Find best match: closest entry to exit (in both directions within 2 days)
            exit_date_tuple = parse_date(event.date or event_date or "")
            exit_time_tuple = parse_time(event.time)
            exit_seconds = datetime_to_seconds(exit_date_tuple, exit_time_tuple)
            
            product = None
            best_diff = None
            
            for p in candidates:
                # Skip already used entries
                p_key = make_product_key(p)
                if p_key in used_entries:
                    continue
                
                entry_date_tuple = parse_date(str(p.get('date', '')))
                entry_time_tuple = parse_time(str(p.get('time', '')))
                entry_seconds = datetime_to_seconds(entry_date_tuple, entry_time_tuple)
                
                # Calculate absolute difference in seconds
                diff = abs(exit_seconds - entry_seconds)
                
                # Skip if more than 2 days apart
                if diff > 2 * 86400:
                    continue
                
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
                exit_date=event.date or event_date or datetime.now().strftime("%d.%m.%Y"),
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


# ==================== SIMULATION ENDPOINTS ====================

class SimulationRequest(BaseModel):
    """Request to start FTP simulation."""
    file_path: Optional[str] = None  # If None, uses default testdata file


class SimulationStatus(BaseModel):
    """Simulation status response."""
    active: bool
    file_path: Optional[str] = None
    current_event: int = 0
    total_events: int = 0
    progress_percent: int = 0


@router.post("/simulation/start", response_model=SimulationStatus)
async def start_simulation(request: SimulationRequest = None):
    """
    Start FTP simulation mode using a local log file.
    
    This reads a test log file line by line to simulate real-time FTP events.
    Events are broadcast via WebSocket to the "Выгрузка" table.
    """
    # Default to testdata file
    if request and request.file_path:
        file_path = Path(request.file_path)
        if not file_path.exists():
            raise HTTPException(status_code=404, detail=f"File not found: {file_path}")
    else:
        # Try multiple paths for Docker and local development
        possible_paths = [
            Path("/app/testdata/ftp/2025-11-29.txt"),  # Docker
            Path(__file__).parent.parent.parent.parent.parent / "testdata/ftp/2025-11-29.txt",  # Local dev
        ]
        file_path = None
        for p in possible_paths:
            if p.exists():
                file_path = p
                break
        
        if not file_path:
            raise HTTPException(status_code=404, detail=f"Simulation file not found. Tried: {[str(p) for p in possible_paths]}")
    
    # Start simulation - loads ALL events immediately
    success = ftp_service.start_simulation(file_path)
    if not success:
        raise HTTPException(status_code=500, detail="Failed to start simulation")
    
    total = ftp_service.simulation_events_count
    
    return SimulationStatus(
        active=True,
        file_path=str(file_path),
        current_event=total,
        total_events=total,
        progress_percent=100
    )


@router.post("/simulation/stop", response_model=SimulationStatus)
async def stop_simulation():
    """Stop FTP simulation mode."""
    try:
        ftp_service.stop_simulation()
    except Exception as e:
        logger.error(f"Error stopping simulation: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to stop simulation: {str(e)}")
    
    return SimulationStatus(
        active=False,
        current_event=0,
        total_events=0,
        progress_percent=0
    )


@router.get("/simulation/status", response_model=SimulationStatus)
async def get_simulation_status():
    """Get current simulation status."""
    if not ftp_service.is_simulation:
        return SimulationStatus(active=False)
    
    total = ftp_service.simulation_events_count
    
    return SimulationStatus(
        active=True,
        file_path=str(ftp_service._simulation_file) if ftp_service._simulation_file else None,
        current_event=total,
        total_events=total,
        progress_percent=100
    )


# === FTP Poller Control ===

class PollerStatus(BaseModel):
    """FTP Poller status response."""
    running: bool
    interval: int = settings.FTP_POLL_INTERVAL


@router.get("/poller/status", response_model=PollerStatus)
async def get_poller_status():
    """Get FTP poller status."""
    return PollerStatus(
        running=ftp_poller.is_running,
        interval=ftp_poller._poll_interval
    )


@router.post("/poller/start", response_model=PollerStatus)
async def start_poller():
    """Start FTP poller."""
    if not ftp_poller.is_running:
        await ftp_poller.start()
        logger.info("[FTP] Poller started via API")
    return PollerStatus(
        running=ftp_poller.is_running,
        interval=ftp_poller._poll_interval
    )


@router.post("/poller/stop", response_model=PollerStatus)
async def stop_poller():
    """Stop FTP poller."""
    if ftp_poller.is_running:
        await ftp_poller.stop()
        logger.info("[FTP] Poller stopped via API")
    return PollerStatus(
        running=ftp_poller.is_running,
        interval=ftp_poller._poll_interval
    )


@router.post("/poller/poll-now")
async def poll_now(background_tasks: BackgroundTasks):
    """Trigger immediate FTP poll (non-blocking)."""
    import asyncio
    
    async def do_poll():
        await ftp_poller.poll_now()
    
    # Запускаем в фоне, не ждём
    asyncio.create_task(do_poll())
    logger.info("[FTP] Manual poll triggered via API")
    return {"status": "ok", "message": "Poll triggered"}


# ==================== DEBUG ENDPOINTS ====================

@router.get("/debug/raw-data")
async def get_debug_raw_data(
    limit: int = Query(default=100, ge=1, le=500, description="Number of records")
):
    """
    DEBUG: Get raw FTP events and Excel data for comparison.
    Shows last N records from both sources sorted by date/time (newest first).
    """
    from datetime import date
    
    # Get FTP events (from cache or simulation)
    if ftp_service.is_simulation:
        ftp_events = ftp_service.get_all_simulation_events()
        ftp_source = "simulation"
    else:
        ftp_events = ftp_poller.cached_events
        ftp_source = "ftp_cache"
    
    # Get Excel products
    excel_products = excel_service.get_products(limit=limit, days=7)
    
    # Format FTP events (newest first)
    ftp_data = []
    for e in reversed(ftp_events[-limit:]):
        ftp_data.append({
            "date": e.date,
            "time": e.time,
            "hanger": e.hanger,
            "timestamp": e.timestamp.isoformat() if e.timestamp else None
        })
    
    # Format Excel data (already sorted by date desc in service)
    excel_data = []
    for p in excel_products[:limit]:
        excel_data.append({
            "date": p.get('date', ''),
            "time": p.get('time', ''),
            "number": p.get('number', ''),
            "client": p.get('client', ''),
            "profile": p.get('profile', ''),
            "color": p.get('color', ''),
        })
    
    return {
        "ftp": {
            "source": ftp_source,
            "total_cached": len(ftp_events),
            "showing": len(ftp_data),
            "events": ftp_data
        },
        "excel": {
            "total": len(excel_products),
            "showing": len(excel_data),
            "products": excel_data
        },
        "today": date.today().strftime("%d.%m.%Y"),
        "note": "FTP events sorted newest first, Excel products sorted by date desc"
    }


@router.get("/debug/matching")
async def get_debug_matching(
    limit: int = Query(default=30, ge=1, le=100, description="Number of events to match")
):
    """
    DEBUG: Show matching process step by step.
    For each FTP event shows all candidates and why one was chosen.
    """
    from datetime import date
    
    try:
        # Get FTP events
        if ftp_service.is_simulation:
            events = ftp_service.get_all_simulation_events()
            event_date = ftp_service._simulation_date
        else:
            events = ftp_poller.cached_events
            event_date = date.today().strftime("%d.%m.%Y")
        
        if not events:
            return {
                "today": date.today().strftime("%d.%m.%Y"),
                "total_ftp_events": 0,
                "total_excel_products": 0,
                "showing": 0,
                "matches": [],
                "error": "No FTP events in cache"
            }
        
        # Get Excel products
        products = excel_service.get_products(limit=1000, days=30)
        
        if not products:
            return {
                "today": date.today().strftime("%d.%m.%Y"),
                "total_ftp_events": len(events),
                "total_excel_products": 0,
                "showing": 0,
                "matches": [],
                "error": "No Excel products"
            }
        
        # Build lookup by hanger
        products_by_hanger: dict[str, list] = {}
        for p in products:
            num = str(p.get('number', ''))
            if num:
                if num not in products_by_hanger:
                    products_by_hanger[num] = []
                products_by_hanger[num].append(p)
        
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
        
        # Sort events by time (oldest first)
        events_to_match = sorted(
            events[-limit:],
            key=lambda e: datetime_to_seconds(
                parse_date(e.date or event_date or ""),
                parse_time(e.time)
            )
        )
        
        matches = []
        for event in events_to_match:
            hanger_num = str(event.hanger)
            candidates = products_by_hanger.get(hanger_num, [])
            
            exit_date = event.date or event_date or ""
            exit_date_tuple = parse_date(exit_date)
            exit_time_tuple = parse_time(event.time)
            exit_seconds = datetime_to_seconds(exit_date_tuple, exit_time_tuple)
            
            # Evaluate all candidates
            candidate_info = []
            best_product = None
            best_diff = None
            
            for p in candidates:
                p_key = make_product_key(p)
                entry_date = str(p.get('date', ''))
                entry_time = str(p.get('time', ''))
                entry_date_tuple = parse_date(entry_date)
                entry_time_tuple = parse_time(entry_time)
                entry_seconds = datetime_to_seconds(entry_date_tuple, entry_time_tuple)
                
                diff = abs(exit_seconds - entry_seconds)
                diff_hours = diff / 3600
                
                is_used = p_key in used_entries
                is_too_far = diff > 2 * 86400
                
                status = "OK"
                if is_used:
                    status = "USED"
                elif is_too_far:
                    status = "TOO_FAR"
                
                candidate_info.append({
                    "entry_date": entry_date,
                    "entry_time": entry_time,
                    "client": p.get('client', ''),
                    "profile": p.get('profile', ''),
                    "diff_hours": round(diff_hours, 2),
                    "status": status,
                })
                
                if not is_used and not is_too_far:
                    if best_diff is None or diff < best_diff:
                        best_diff = diff
                        best_product = p
            
            # Mark as used
            if best_product:
                used_entries.add(make_product_key(best_product))
            
            matches.append({
                "ftp_event": {
                    "date": exit_date,
                    "time": event.time,
                    "hanger": event.hanger,
                },
                "candidates_count": len(candidates),
                "candidates": candidate_info[:10],  # Limit to 10 candidates
                "matched": {
                    "entry_date": str(best_product.get('date', '')) if best_product else None,
                    "entry_time": str(best_product.get('time', '')) if best_product else None,
                    "client": best_product.get('client', '') if best_product else None,
                    "profile": best_product.get('profile', '') if best_product else None,
                    "diff_hours": round(best_diff / 3600, 2) if best_diff else None,
                } if best_product else None,
            })
        
        # Reverse to show newest first
        matches.reverse()
        
        return {
            "today": date.today().strftime("%d.%m.%Y"),
            "total_ftp_events": len(events),
            "total_excel_products": len(products),
            "showing": len(matches),
            "matches": matches,
        }
    except Exception as e:
        logger.error(f"[DEBUG] Matching error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
