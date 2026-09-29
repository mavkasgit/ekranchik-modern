"""
Dashboard API routes.
"""
import logging
from collections import OrderedDict
from datetime import datetime
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Query, HTTPException, BackgroundTasks, UploadFile, File
from pydantic import BaseModel

logger = logging.getLogger(__name__)

from app.core.config import settings
from app.services.excel_service import excel_service
from app.services.catalog_service import catalog_service
from app.services.hanger_row import EMPTY, HangerRow, to_hanger_data
from app.services.profile_name import split_profiles
from app.services.matching import (
    CODE_CYCLE_ERROR,
    CODE_NO_ROW,
    CODE_SUSPECT,
    CycleMatch,
    match_cycles_to_rows,
    normalize_hanger_key,
    parse_iso_seconds,
    product_entry_seconds,
)

# Аномально долгий проход по линии — предупреждение, подбор не меняет.
DELAY_LIMIT_SECONDS = 6 * 3600

# Событие выгрузки неизменяемо, а страница опрашивает подбор каждые
# несколько секунд. Без этого ключи повторялись бы в журнале десятки раз за
# минуту на каждое событие, и настоящая причина тонула бы в шуме.
_reported_matches: "OrderedDict[tuple, None]" = OrderedDict()
_REPORTED_MATCHES_MAX = 1000


def _log_match_once(key: tuple, cycle: dict, hanger_num: str, code: str,
                    row: Optional[HangerRow]) -> None:
    """Написать в журнал причину подбора ровно один раз на событие."""
    if key in _reported_matches:
        return
    _reported_matches[key] = None
    while len(_reported_matches) > _REPORTED_MATCHES_MAX:
        _reported_matches.popitem(last=False)
    logger.warning(
        "[Matching] cycle %s hanger %s: %s (row %s)",
        cycle.get("cycle_id"), hanger_num, code,
        f"{row.date} {row.time}" if row else "—",
    )


from app.schemas.dashboard import (
    DashboardResponse,
    FileStatus,
    MatchedUnloadEvent,
    ExcelFileListResponse,
    ExcelFileSelectRequest,
    ExcelFileInfo
)
from app.schemas.profile import ProfileInfo

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


def _collect_profile_names(products: list[HangerRow]) -> list[str]:
    """Чистые имена Профилей всех строк — для пакетного поиска фото."""
    names: list[str] = []
    for product in products:
        for parsed in split_profiles(product.profile):
            if parsed.name not in names:
                names.append(parsed.name)
    return names


def _build_profiles_info(profile_text, photos_map: dict) -> list[ProfileInfo]:
    """Профили строки с фото и обработками — один маппинг на оба пути дашборда."""
    info: list[ProfileInfo] = []
    for parsed in split_profiles(profile_text):
        photo = photos_map.get(parsed.name, {})
        info.append(ProfileInfo(
            name=parsed.raw,
            canonical_name=photo.get('name') or parsed.name,
            has_photo=bool(photo.get('thumb')),
            photo_thumb=photo.get('thumb'),
            photo_full=photo.get('full'),
            processing=parsed.processing,
            updated_at=photo.get('updated_at'),
        ))
    return info


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

        profile_names = _collect_profile_names(products)
        
        # Batch lookup photos from catalog
        photos_map = {}
        try:
            photos_map = await catalog_service.get_profiles_photos_batch(profile_names)
        except Exception as e:
            logger.warning(f"[DASHBOARD API] Could not load photos from catalog: {e}")
            # Continue without photos
        
        # Convert to HangerData format with photos
        hanger_data = [
            to_hanger_data(product, _build_profiles_info(product.profile, photos_map))
            for product in products
        ]

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
    """Проходы подвесов по линии, сопоставленные со строками книги учёта.

    Источник проходов — line_monitor: каждый проход имеет свой cycle_id,
    номер подвеса повторяется от смены к смены и проход не идентифицирует.
    Строку книги подбирает app.services.matching по близости к first_seen_at.
    """
    try:
        from app.services.line_monitor import line_monitor

        cycles = line_monitor.get_unload_events(limit=limit)
        if not cycles:
            return []

        products = excel_service.get_products(limit=1000, days=30, from_end=True, loading_only=False)

        rows_by_hanger: dict[str, list[HangerRow]] = {}
        for p in products:
            key = normalize_hanger_key(p.number)
            if key:
                rows_by_hanger.setdefault(key, []).append(p)

        photos_map = await catalog_service.get_profiles_photos_batch(_collect_profile_names(products))

        matches = match_cycles_to_rows(cycles, rows_by_hanger)
        matched: list[MatchedUnloadEvent] = []
        for m in matches:
            cycle, row = m.cycle, m.row
            hanger_num = str(cycle.get("hanger"))
            code, warning = _warning_for(m)
            if m.code:
                # Диагностика в лог идёт по всем причинам, включая NO_ROW,
                # у которого на экране пометки нет: пустая строка читается сама.
                _log_match_once(
                    (cycle.get("cycle_id"), cycle.get("timestamp"), m.code),
                    cycle, hanger_num, m.code, row,
                )

            profiles_info = _build_profiles_info(row.profile if row else '', photos_map)
            matched.append(MatchedUnloadEvent(
                cycle_id=cycle.get("cycle_id"),
                first_seen_at=cycle.get("first_seen_at"),
                entry_bath=cycle.get("entry_bath"),
                entry_date=str(row.date) if row else None,
                entry_time=str(row.time) if row else None,
                entry_delta_sec=m.entry_delta_sec,
                exit_date=cycle.get("date") or datetime.now().strftime("%d.%m.%Y"),
                exit_time=cycle.get("time") or EMPTY,
                hanger=int(hanger_num or 0),
                client=str(row.client) if row else EMPTY,
                profile=str(row.profile) if row else EMPTY,
                profiles_info=profiles_info,
                color=str(row.color) if row else EMPTY,
                lamels_qty=row.lamels_qty if row else 0,
                kpz_number=str(row.kpz_number) if row else EMPTY,
                material_type=str(row.material_type) if row else EMPTY,
                is_defect=bool(row.is_defect) if row else False,
                time_warning_code=code or None,
                time_warning=warning,
            ))

        # === Прогноз по ваннам для подвесов, которые сейчас на линии ===
        try:
            for event in matched:
                hanger_state = line_monitor.get_hanger_state(event.hanger)
                if not hanger_state or not hanger_state.current_bath:
                    continue
                bath_num = int(hanger_state.current_bath)
                if not 30 <= bath_num <= 33:
                    continue
                event.current_bath = bath_num
                if hanger_state.entry_time:
                    event.bath_entry_time = hanger_state.entry_time.strftime("%H:%M:%S")
                try:
                    from app.services.opcua_service import opcua_service
                    dtime = opcua_service.get_value(f"ns=4;s=Bath[{bath_num}].dTime")
                    if dtime and isinstance(dtime, (int, float)):
                        event.bath_processing_time = int(dtime)
                except Exception as e:
                    logger.warning(f"Could not get dTime for bath {bath_num}: {e}")
        except Exception as e:
            logger.warning(f"[OPC UA Unload] Could not populate forecast info: {e}", exc_info=True)

        return matched
    except Exception as e:
        logger.error(f"[OPC UA Unload] Error matching events: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


def _warning_for(m: CycleMatch):
    """Код бейджа и текст-тултип для результата подбора."""
    if m.code == CODE_CYCLE_ERROR:
        return CODE_CYCLE_ERROR, "line_monitor не нашёл открытого цикла для этого выхода"
    if m.code == CODE_NO_ROW:
        # Пустая строка читается сама: подвес сошёл, а в книге его нет.
        # Бейдж не нужен — на экране и так видно, что данных нет.
        return None, None
    if m.code == CODE_SUSPECT:
        row = m.row
        line_in = m.cycle.get("first_seen_at") or EMPTY
        if m.suspect_reason == "later_run":
            return CODE_SUSPECT, (
                f"Вход линии: {_hhmm(line_in)}, найденная строка: {row.time} {row.date} — "
                "строка позже выхода, вероятно от другого прогона"
            )
        delta = m.entry_delta_sec or 0
        return CODE_SUSPECT, (
            f"Вход линии: {_hhmm(line_in)}, в книге: {row.time} {row.date} — "
            f"расхождение {abs(delta) / 60:.0f} мин"
        )

    # Уверенное попадание: помечаем только аномально долгий проход.
    row = m.row
    if row is not None and m.entry_delta_sec is not None:
        on_line = parse_iso_seconds(m.cycle.get("exit_at")) - product_entry_seconds(row)
        if on_line > DELAY_LIMIT_SECONDS:
            return "DELAY", f"На линии {on_line / 3600:.1f}ч при пороге 6ч"
    return "", None


def _hhmm(iso: str) -> str:
    try:
        return datetime.fromisoformat(iso).strftime("%H:%M")
    except (ValueError, TypeError):
        return EMPTY


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
