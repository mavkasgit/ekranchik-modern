"""
Dashboard API routes.
"""
import re
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional, Tuple, List

from fastapi import APIRouter, Query, HTTPException, BackgroundTasks, UploadFile, File
from pydantic import BaseModel

logger = logging.getLogger(__name__)

from app.core.config import settings
from app.services.excel_service import excel_service
from app.services.catalog_service import catalog_service
from app.schemas.dashboard import (
    DashboardResponse,
    HangerData,
    FileStatus,
    MatchedUnloadEvent,
    ExcelFileListResponse,
    ExcelFileSelectRequest,
    ExcelFileInfo
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
    loading_only: bool = Query(default=True, description="Only show rows that are loading (time is empty)")
):
    """
    Get dashboard data with production records.

    Returns recent production data from Excel file with profile photos from catalog.
    """
    try:
        products = excel_service.get_products(limit=limit, days=days, loading_only=loading_only)

        # Collect all unique profile names for batch lookup
        profile_names = set()
        for product in products:
            profile = str(product.get('profile', ''))
            if profile and profile != '—':
                # Handle multiple profiles separated by +
                for p in profile.split('+'):
                    p = p.strip()
                    if p:
                        profile_names.add(p)
        
        # Batch lookup photos from catalog
        photos_map = {}
        try:
            photos_map = await catalog_service.get_profiles_photos_batch(list(profile_names))
        except Exception as e:
            logger.warning(f"[DASHBOARD API] Could not load photos from catalog: {e}")
            # Continue without photos
        
        # Convert to HangerData format with photos
        hanger_data = []
        for i, product in enumerate(products):
            profile_str = str(product.get('profile', product.get('Профиль', '—')))
            
            # Build profiles_info with photos and processing keywords
            profiles_info = []
            if profile_str and profile_str != '—':
                for p in profile_str.split('+'):
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
                            processing=processing,
                            updated_at=photo_info.get('updated_at')
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


def get_excel_internal_modified_time(file_path: Path) -> Optional[datetime]:
    """
    Try to read the internal modified time from the Excel file's docProps/core.xml.
    Returns datetime in local timezone if found, otherwise None.
    """
    import zipfile
    import xml.etree.ElementTree as ET
    
    try:
        with zipfile.ZipFile(file_path, 'r') as z:
            core_xml = z.read('docProps/core.xml')
            root = ET.fromstring(core_xml)
            for elem in root.iter():
                if elem.tag.endswith('}modified'):
                    val = elem.text
                    if val:
                        if val.endswith('Z'):
                            val = val[:-1] + '+00:00'
                        dt = datetime.fromisoformat(val)
                        return dt.astimezone()
    except Exception as e:
        logger.warning(f"Could not read internal modified time from {file_path}: {e}")
    return None


@router.get("/status/file", response_model=FileStatus)
async def get_file_status():
    """
    Get Excel file status.
    Detects if file is open by checking for Excel temp file (~$filename).
    """
    from app.core.config import settings
    import time
    
    try:
        path = excel_service.current_path
        
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
        
        # Try to get internal modified time (actual save time)
        internal_mtime = get_excel_internal_modified_time(path)
        if internal_mtime:
            mtime_dt = internal_mtime
            mtime_timestamp = internal_mtime.timestamp()
        else:
            mtime_timestamp = stat.st_mtime
            mtime_dt = datetime.fromtimestamp(mtime_timestamp).astimezone()
            
        seconds_since_modified = max(0.0, time.time() - mtime_timestamp)
        
        return FileStatus(
            is_open=is_open,
            last_modified=mtime_dt,
            file_name=path.name,
            status_text=status_text,
            seconds_since_modified=seconds_since_modified
        )
    except Exception as e:
        return FileStatus(
            status_text="Ошибка",
            error=str(e)
        )


def format_size(bytes_size: int) -> str:
    """Format file size in human readable units"""
    for unit in ['Б', 'КБ', 'МБ', 'ГБ']:
        if bytes_size < 1024:
            return f"{bytes_size:.1f} {unit}"
        bytes_size /= 1024
    return f"{bytes_size:.1f} ТБ"


@router.get("/excel/files", response_model=ExcelFileListResponse)
async def get_excel_files(folder_path: Optional[str] = Query(default=None, description="Absolute folder path to list files in")):
    """
    Get list of available Excel files and directories in the requested or default path,
    along with directory metadata and the active file absolute path.
    """
    try:
        # Determine the target directory to scan
        if folder_path:
            current_dir = Path(folder_path).resolve()
        else:
            active_path = excel_service.current_path
            if active_path and active_path.parent.exists():
                current_dir = active_path.parent.resolve()
            elif settings.excel_path and settings.excel_path.parent.exists():
                current_dir = settings.excel_path.parent.resolve()
            else:
                current_dir = Path.cwd().resolve()
                
        if not current_dir.exists():
            raise HTTPException(status_code=400, detail=f"Путь не существует: {current_dir}")
        if not current_dir.is_dir():
            raise HTTPException(status_code=400, detail=f"Путь не является папкой: {current_dir}")

        files = []
        try:
            for item in current_dir.iterdir():
                # Skip hidden folders / files starting with dot
                if item.name.startswith('.'):
                    continue
                
                if item.is_dir():
                    try:
                        stat = item.stat()
                        mtime = datetime.fromtimestamp(stat.st_mtime)
                    except Exception:
                        mtime = datetime.now()
                    files.append(ExcelFileInfo(
                        name=item.name,
                        path=str(item.resolve()),
                        size_bytes=0,
                        size_formatted="",
                        last_modified=mtime,
                        is_dir=True
                    ))
                elif item.is_file() and item.suffix.lower() in ('.xlsx', '.xls', '.xlsm') and not item.name.startswith('~$'):
                    try:
                        stat = item.stat()
                        size = stat.st_size
                        mtime = datetime.fromtimestamp(stat.st_mtime)
                    except Exception:
                        size = 0
                        mtime = datetime.now()
                    files.append(ExcelFileInfo(
                        name=item.name,
                        path=str(item.resolve()),
                        size_bytes=size,
                        size_formatted=format_size(size),
                        last_modified=mtime,
                        is_dir=False
                    ))
        except PermissionError:
            raise HTTPException(status_code=403, detail=f"Нет доступа к папке: {current_dir}")
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Ошибка при чтении папки {current_dir}: {str(e)}")

        # Sort: directories first (alphabetically), then files (alphabetically)
        files.sort(key=lambda x: (not x.is_dir, x.name.lower()))

        active_path = str(excel_service.current_path.resolve()) if excel_service.current_path else ""
        parent_dir = current_dir.parent
        parent_directory = str(parent_dir.resolve()) if parent_dir != current_dir else None

        return ExcelFileListResponse(
            success=True,
            files=files,
            active=active_path,
            current_directory=str(current_dir.resolve()),
            parent_directory=parent_directory
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[DASHBOARD API] Failed to scan Excel files: {e}", exc_info=True)
        fallback_active = str(excel_service.current_path.resolve()) if excel_service.current_path else ""
        return ExcelFileListResponse(
            success=False,
            error=str(e),
            files=[],
            active=fallback_active,
            current_directory=str(Path.cwd().resolve()),
            parent_directory=None
        )


@router.post("/excel/select")
async def select_excel_file(request: ExcelFileSelectRequest):
    """
    Select active Excel file.
    """
    try:
        # Support both file_path (for custom paths) and file_name (for backward compatibility)
        if request.file_path:
            file_path = request.file_path.strip().strip('"\'')
        elif request.file_name:
            # Backward compatibility
            path = settings.excel_path
            if not path:
                raise HTTPException(status_code=400, detail="Путь к Excel-файлу не настроен")
            file_path = str((path.parent / request.file_name).resolve())
        else:
            raise HTTPException(status_code=400, detail="Не указан путь к файлу (file_path) или его имя (file_name)")

        target_file = Path(file_path)
        if not target_file.is_absolute():
            if settings.excel_path:
                target_file = (settings.excel_path.parent / target_file).resolve()
            else:
                raise HTTPException(status_code=400, detail="Невозможно разрешить относительный путь")

        target_file = target_file.resolve()
        
        if not target_file.exists():
            raise HTTPException(status_code=404, detail=f"Файл {target_file} не найден")
            
        if not target_file.is_file():
            raise HTTPException(status_code=400, detail=f"Указанный путь не является файлом: {target_file}")
            
        if target_file.suffix.lower() not in ('.xlsx', '.xls', '.xlsm'):
            raise HTTPException(status_code=400, detail=f"Недопустимое расширение файла: {target_file.suffix}")

        excel_service.set_active_file(str(target_file))
        logger.info(f"[DASHBOARD API] Switched active Excel file to: {target_file}")
        
        # Invalidate watcher cache if running
        try:
            from app.services.websocket_manager import websocket_manager
            from app.schemas.websocket import WebSocketMessage
            message = WebSocketMessage(
                type="data_update",
                payload={
                    "source": "excel",
                    "file": target_file.name,
                    "file_path": str(target_file),
                    "message": f"Активный файл Excel изменен на {target_file.name}"
                },
                timestamp=datetime.now()
            )
            await websocket_manager.broadcast(message)
        except Exception as ws_err:
            logger.warning(f"Could not broadcast websocket update for file switch: {ws_err}")
            
        return {
            "success": True,
            "active": str(target_file)
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[DASHBOARD API] Failed to select Excel file: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/excel/upload")
async def upload_excel_file(file: UploadFile = File(...)):
    """
    Upload an Excel file to the server and set it as the active Excel file.
    """
    try:
        # Check file extension
        suffix = Path(file.filename).suffix.lower()
        if suffix not in ('.xlsx', '.xls', '.xlsm'):
            raise HTTPException(
                status_code=400,
                detail=f"Неподдерживаемый формат файла: {suffix}. Допустимы только .xlsx, .xls, .xlsm"
            )
            
        path = settings.excel_path
        if path:
            target_dir = path.parent
        else:
            target_dir = Path(settings.STATIC_DIR) / "uploads"
            
        target_dir.mkdir(parents=True, exist_ok=True)
        target_file = target_dir / file.filename
        
        # Save file contents
        content = await file.read()
        with open(target_file, "wb") as f:
            f.write(content)
            
        # Set this file as the active Excel file
        excel_service.set_active_file(str(target_file.resolve()))
        logger.info(f"[DASHBOARD API] Uploaded and selected Excel file: {target_file}")
        
        # Invalidate watcher cache if running, and notify via WS
        try:
            from app.services.websocket_manager import websocket_manager
            from app.schemas.websocket import WebSocketMessage
            message = WebSocketMessage(
                type="data_update",
                payload={
                    "source": "excel",
                    "file": target_file.name,
                    "file_path": str(target_file.resolve()),
                    "message": f"Активный файл Excel изменен на {target_file.name}"
                },
                timestamp=datetime.now()
            )
            await websocket_manager.broadcast(message)
        except Exception as ws_err:
            logger.warning(f"Could not broadcast websocket update for file switch: {ws_err}")
            
        return {
            "success": True,
            "active": str(target_file.resolve())
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[DASHBOARD API] Failed to upload Excel file: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))



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
            status_text="Подключено" if connected else "Отключено",
            last_modified=datetime.now()
        )
    except Exception as e:
        return FileStatus(
            is_open=False,
            status_text="Ошибка",
            error=str(e),
            last_modified=datetime.now()
        )








@router.get("/opcua-unload-matched", response_model=list[MatchedUnloadEvent])
async def get_opcua_matched_unload_events(
    limit: int = Query(default=100, ge=1, le=500, description="Max events to return")
):
    """
    Get OPC UA unload events (from Bath[34]) matched with Excel data.
    
    Uses line_monitor to get events from Bath[34] exit detection.
    Matches each event with Excel data by hanger number.
    Returns events with entry/exit times and product info.
    """
    try:
        from app.services.line_monitor import line_monitor
        
        # Get unload events from the line monitor service
        events = line_monitor.get_unload_events(limit=limit)
        
        if not events:
            return []
        
        # Get all products from Excel for matching
        products = excel_service.get_products(limit=1000, days=30, from_end=True, loading_only=False)
        
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
                for name in profile.split('+'):
                    name = name.strip()
                    if name:
                        profile_names.add(name)
        
        photos_map = await catalog_service.get_profiles_photos_batch(list(profile_names))
        
        # Helper to parse date string to comparable format
        def parse_date(date_str: str) -> tuple:
            """Parse DD.MM.YYYY or DD.MM.YY to (year, month, day) tuple for comparison."""
            if not date_str or date_str == '—':
                return (0, 0, 0)
            try:
                # Remove any whitespace
                date_str = date_str.strip()
                parts = date_str.split('.')
                if len(parts) == 3:
                    day, month, year = int(parts[0]), int(parts[1]), int(parts[2])
                    # Handle 2-digit years: 00-49 → 2000-2049, 50-99 → 1950-1999
                    if year < 50:
                        year += 2000
                    elif year < 100:
                        year += 1900
                    return (year, month, day)
            except (ValueError, IndexError):
                pass
            return (0, 0, 0)
        
        def parse_time(time_str: str) -> tuple:
            """Parse HH:MM:SS or HH:MM to (hour, minute, second) tuple."""
            if not time_str or time_str == '—':
                return (0, 0, 0)
            try:
                # Remove any whitespace
                time_str = time_str.strip()
                parts = time_str.split(':')
                hour = int(parts[0]) if len(parts) > 0 else 0
                minute = int(parts[1]) if len(parts) > 1 else 0
                second = int(parts[2]) if len(parts) > 2 else 0
                return (hour, minute, second)
            except (ValueError, IndexError):
                pass
            return (0, 0, 0)
        
        def datetime_to_seconds(date_tuple: tuple, time_tuple: tuple) -> float:
            """Convert date+time to total seconds for comparison using proper datetime."""
            try:
                year, month, day = date_tuple
                hour, minute, second = time_tuple
                
                if year == 0 or month == 0 or day == 0:
                    return 0
                
                # Use proper datetime for accurate conversion
                dt = datetime(year, month, day, hour, minute, second)
                # Convert to timestamp (seconds since epoch)
                return dt.timestamp()
            except (ValueError, OverflowError):
                # Fallback to simple calculation if datetime fails
                year_days = date_tuple[0] * 365
                month_days = date_tuple[1] * 30
                day = date_tuple[2]
                
                total_days = year_days + month_days + day
                total_seconds = time_tuple[0] * 3600 + time_tuple[1] * 60 + time_tuple[2]
                
                return total_days * 86400 + total_seconds

        def make_product_key(p: dict) -> str:
            """Create unique key for product to track used entries."""
            return f"{p.get('date', '')}|{p.get('time', '')}|{p.get('number', '')}"
        
        # Track used entries to avoid matching same entry twice
        used_entries: set = set()
        
        # Sort events by time (oldest first) for greedy matching
        events_to_match = sorted(
            events,
            key=lambda e: datetime_to_seconds(
                parse_date(e.get("date") or ""),
                parse_time(e.get("time") or "")
            )
        )
        
        # Match events with products (greedy: oldest exit first)
        matched = []
        for event in events_to_match:
            hanger_num = str(event.get('hanger'))
            candidates = products_by_hanger.get(hanger_num, [])
            
            exit_date_tuple = parse_date(event.get("date") or "")
            exit_time_tuple = parse_time(event.get("time") or "")
            exit_seconds = datetime_to_seconds(exit_date_tuple, exit_time_tuple)
            
            product = None
            best_diff = None
            product_exceeds_limit = None  # Track product that exceeds time limit
            time_diff_hours = None  # Track time difference for warning
            
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
                
                if entry_seconds >= exit_seconds:
                    continue
                
                diff = exit_seconds - entry_seconds
                
                # Maximum time between entry and exit: 6 hours
                if diff > 6 * 3600:  # 6 hours = 21600 seconds
                    # Save this product as exceeding limit, but keep looking for better match
                    if product_exceeds_limit is None or diff < best_diff:
                        product_exceeds_limit = p
                        best_diff = diff
                        time_diff_hours = diff / 3600
                    continue
                
                if best_diff is None or diff < best_diff:
                    best_diff = diff
                    product = p
            
            # If no product within time limit, use the one that exceeds limit
            warning_message = None
            if not product and product_exceeds_limit:
                product = product_exceeds_limit
                warning_message = f"⚠ Время между входом и выходом: {time_diff_hours:.1f}ч (превышает лимит 6ч)"
            
            if product:
                used_entries.add(make_product_key(product))
            
            profiles_info = []
            if product:
                profile_str = str(product.get('profile', ''))
                if profile_str and profile_str != '—':
                    for prof_name in profile_str.split('+'):
                        prof_name = prof_name.strip()
                        if prof_name:
                            clean_name, processing = parse_profile_name(prof_name)
                            photo_info = photos_map.get(prof_name, {})
                            if not photo_info and clean_name != prof_name:
                                photo_info = photos_map.get(clean_name, {})
                            
                            profiles_info.append(ProfileInfo(
                                name=prof_name,
                                canonical_name=photo_info.get('name', clean_name or prof_name),
                                has_photo=bool(photo_info.get('thumb')),
                                photo_thumb=photo_info.get('thumb'),
                                photo_full=photo_info.get('full'),
                                processing=processing,
                                updated_at=photo_info.get('updated_at')
                            ))
            
            matched.append(MatchedUnloadEvent(
                exit_date=event.get("date") or datetime.now().strftime("%d.%m.%Y"),
                exit_time=event.get("time"),
                hanger=int(hanger_num),
                entry_date=str(product.get('date', '')) if product else None,
                entry_time=str(product.get('time', '')) if product else None,
                client=str(product.get('client', '—')) if product else '—',
                profile=str(product.get('profile', '—')) if product else '—',
                profiles_info=profiles_info,
                color=str(product.get('color', '—')) if product else '—',
                lamels_qty=product.get('lamels_qty', 0) if product else 0,
                kpz_number=str(product.get('kpz_number', '—')) if product else '—',
                material_type=str(product.get('material_type', '—')) if product else '—',
                time_warning=warning_message,  # Add warning if time exceeds limit
                # Forecast info - will be populated below
                current_bath=None,
                bath_entry_time=None,
                bath_processing_time=None,
            ))
        
        matched.reverse()
        
        # === Populate forecast info (current bath and processing time) ===
        try:
            from app.services.line_monitor import line_monitor
            
            logger.info(f"[OPC UA Unload] Populating forecast for {len(matched)} events")
            
            for event in matched:
                hanger_id = event.hanger
                hanger_state = line_monitor.get_hanger_state(hanger_id)
                
                logger.debug(f"[OPC UA Unload] Hanger {hanger_id}: state={hanger_state}, bath={hanger_state.current_bath if hanger_state else None}")
                
                if hanger_state and hanger_state.current_bath:
                    current_bath_num = int(hanger_state.current_bath)
                    
                    # Only show forecast for baths 30-33
                    if 30 <= current_bath_num <= 33:
                        event.current_bath = current_bath_num
                        
                        # Get entry time in current bath
                        if hanger_state.entry_time:
                            event.bath_entry_time = hanger_state.entry_time.strftime("%H:%M:%S")
                        
                        # Get processing time from OPC UA (dTime field)
                        try:
                            from app.services.opcua_service import opcua_service
                            dtime = opcua_service.get_value(f"ns=4;s=Bath[{current_bath_num}].dTime")
                            if dtime and isinstance(dtime, (int, float)):
                                event.bath_processing_time = int(dtime)
                            logger.debug(f"[OPC UA Unload] Hanger {hanger_id} in bath {current_bath_num}: dTime={dtime}, entry_time={event.bath_entry_time}")
                        except Exception as e:
                            logger.warning(f"Could not get dTime for bath {current_bath_num}: {e}")
        except Exception as e:
            logger.warning(f"[OPC UA Unload] Could not populate forecast info: {e}", exc_info=True)
        
        return matched
    except Exception as e:
        logger.error(f"[OPC UA Unload] Error matching events: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


# This endpoint is redundant now as the logic is in /opcua-unload-matched
# I'll remove it to avoid confusion
# @router.get("/opcua-unload-events") ...


class SettingsResponse(BaseModel):
    simulation_enabled: bool
    excel_path: str
    opcua_endpoint: str


class SettingsUpdateRequest(BaseModel):
    simulation_enabled: bool


@router.get("/settings", response_model=SettingsResponse)
async def get_settings():
    """Get current simulation settings."""
    from app.services.opcua_service import opcua_service
    return SettingsResponse(
        simulation_enabled=settings.SIMULATION_ENABLED,
        excel_path=str(excel_service.current_path.resolve()) if excel_service.current_path else "",
        opcua_endpoint=opcua_service._url
    )


@router.post("/settings", response_model=SettingsResponse)
async def update_settings(request: SettingsUpdateRequest):
    """Dynamically toggle simulation settings."""
    from app.services.opcua_service import opcua_service
    try:
        new_mode = request.simulation_enabled
        if new_mode != settings.SIMULATION_ENABLED:
            # 1. Update settings in-memory
            settings.SIMULATION_ENABLED = new_mode
            
            # 2. Update settings in .env
            settings.update_simulation_mode_in_env(new_mode)
            
            # 3. Update OPC UA service
            await opcua_service.update_simulation_mode(new_mode)
            
            # 4. Update Excel service
            excel_service.update_simulation_mode()
            
            logger.info(f"[DASHBOARD API] Dynamically toggled simulation_enabled to: {new_mode}")
            
            # 5. Broadcast dynamic WS settings update
            try:
                from app.services.websocket_manager import websocket_manager
                from app.schemas.websocket import WebSocketMessage
                message = WebSocketMessage(
                    type="data_update",
                    payload={
                        "source": "settings",
                        "simulation_enabled": new_mode,
                        "message": f"Режим работы переключен на {'ТЕСТОВЫЙ' if new_mode else 'РАБОЧИЙ'}"
                    },
                    timestamp=datetime.now()
                )
                await websocket_manager.broadcast(message)
            except Exception as ws_err:
                logger.warning(f"Could not broadcast websocket update for mode switch: {ws_err}")
                
        return SettingsResponse(
            simulation_enabled=settings.SIMULATION_ENABLED,
            excel_path=str(excel_service.current_path.resolve()) if excel_service.current_path else "",
            opcua_endpoint=opcua_service._url
        )
    except Exception as e:
        logger.error(f"[DASHBOARD API] Failed to update settings: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
