"""
Dashboard API routes.
"""
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Query, HTTPException, BackgroundTasks
from pydantic import BaseModel

logger = logging.getLogger(__name__)

from app.core.config import settings
from app.services.excel_service import (
    excel_service,
    normalize_path_input,
    path_exists,
    share_tail,
)
from app.services.catalog_service import catalog_service
from app.services.hanger_row import EMPTY, HangerRow, to_hanger_data
from app.services.profile_name import split_profiles
from app.services.matching import (
    CODE_CYCLE_ERROR,
    CODE_NO_ROW,
    CycleMatch,
    match_cycles_to_rows,
    normalize_hanger_key,
    parse_iso_seconds,
    product_entry_seconds,
)

# Аномально долгий проход по линии — предупреждение, подбор не меняет.
DELAY_LIMIT_SECONDS = 6 * 3600


from app.schemas.dashboard import (
    DashboardResponse,
    FileStatus,
    MatchedUnloadEvent,
    ExcelFileSelectRequest,
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
                file_path=str(path),
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
            file_path=str(path),
            status_text=status_text,
            seconds_since_modified=seconds_since_modified
        )
    except Exception as e:
        return FileStatus(
            status_text="Ошибка",
            error=str(e)
        )


def _not_found_detail(target: Path) -> str:
    """Ошибка «файла нет» с подсказкой, если каталог книги пуст.

    Пустой каталог — самый частый случай: сетевой диск не смонтирован в
    контейнер (не заданы EXCEL_VOL_* в infra/compose/.env на Windows).
    Без подсказки оператор видит только «Файл не найден».
    """
    detail = f"Файл {target} не найден"
    book_dir = excel_service.directory
    if book_dir is not None:
        try:
            empty = next(book_dir.iterdir(), None) is None
        except OSError:
            empty = False
        if empty:
            detail += (
                f". Каталог книги {book_dir} пуст — сетевой диск не смонтирован"
                " (проверьте infra/compose/.env: EXCEL_VOL_TYPE=cifs)"
            )
    return detail


def _resolve_book_file(raw_path: str) -> Path:
    """Путь, набранный оператором, → путь, который видит сервер.

    Оператор набирает сетевую книгу так, как её видит его машина
    (``\\\\ktm-disk\\Оператор\\Учет КПЗ 2026.xlsm`` или ``Z:\\…``), а сервер — как
    каталог смонтированной шары: в контейнере такой путь не разрешается.
    Поэтому хвост такого пути ищется в каталоге книги, и только потом путь
    разрешается как есть (на Windows сервер читает шару сам).
    """
    book_dir = excel_service.directory
    path = Path(raw_path)

    tail = share_tail(raw_path)
    if tail and book_dir is not None:
        mapped = book_dir.joinpath(*tail)
        if path_exists(mapped):
            return mapped.resolve()
        # На Windows сервер читает шару сам, и путь мог указывать в другую её
        # папку; в контейнере такой путь не разрешается, и в ошибке должно
        # стоять то место, где сервер искал файл.
        if path.is_absolute() and path_exists(path):
            return path.resolve()
        return mapped.resolve()

    if not path.is_absolute() and not path.root:
        if book_dir is None:
            raise HTTPException(
                status_code=400,
                detail="Невозможно разрешить относительный путь: каталог книги неизвестен",
            )
        path = book_dir / path
    return path.resolve()


@router.post("/excel/select")
async def select_excel_file(request: ExcelFileSelectRequest):
    """
    Select active Excel file.
    """
    try:
        # Support both file_path (for custom paths) and file_name (for backward compatibility)
        if request.file_path:
            # Путь копируют из проводника или письма: кавычки и пробелы по краям
            # снимаются здесь, чтобы клиент не повторял правило.
            file_path = normalize_path_input(request.file_path)
        elif request.file_name:
            # Backward compatibility
            book_dir = excel_service.directory
            if book_dir is None:
                raise HTTPException(status_code=400, detail="Путь к Excel-файлу не настроен")
            file_path = str(book_dir / normalize_path_input(request.file_name))
        else:
            raise HTTPException(status_code=400, detail="Не указан путь к файлу (file_path) или его имя (file_name)")

        target_file = _resolve_book_file(file_path)

        if not path_exists(target_file):
            raise HTTPException(status_code=404, detail=_not_found_detail(target_file))
            
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
    """Код бейджа и текст-тултип для результата подбора.

    На экране живут только метки, которые оператор может понять и на которые
    может отреагировать: долгий проход и выгрузка без прохода. Расхождение
    входа на экран не идёт — допуск не откалиброван, а ложная метка хуже
    пропущенной; расхождение видно в журнале (``match_log_line``).
    """
    if m.code == CODE_CYCLE_ERROR:
        return CODE_CYCLE_ERROR, "line_monitor не нашёл открытого цикла для этого выхода"
    if m.code == CODE_NO_ROW:
        # Пустая строка читается сама: подвес сошёл, а в книге его нет.
        # Бейдж не нужен — на экране и так видно, что данных нет.
        return None, None

    # Строка подобрана: помечаем только аномально долгий проход.
    row = m.row
    if row is not None:
        on_line = parse_iso_seconds(m.cycle.get("exit_at")) - product_entry_seconds(row)
        if on_line > DELAY_LIMIT_SECONDS:
            return "DELAY", f"На линии {on_line / 3600:.1f}ч при пороге 6ч"
    return "", None


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
