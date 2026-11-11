"""
Dashboard API routes.
"""

import asyncio
import logging
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from app.core.config import settings
from app.schemas.dashboard import (
    DashboardResponse,
    ExcelBooksRequest,
    ExcelBooksState,
    ExcelFileSelectRequest,
    FileStatus,
    MatchedUnloadEvent,
    RecentBookPath,
)
from app.schemas.profile import ProfileInfo
from app.services.book_rows import get_book_rows
from app.services.catalog_service import catalog_service
from app.services.excel_service import (
    excel_service,
    normalize_path_input,
    path_exists,
    share_tail,
)
from app.services.hanger_row import EMPTY, HangerRow, to_hanger_data
from app.services.matching import (
    CODE_CYCLE_ERROR,
    CODE_NO_ROW,
    CycleMatch,
    match_cycles_to_rows,
    parse_iso_seconds,
    product_entry_seconds,
)
from app.services.profile_name import split_profiles
from app.services.standby_book import standby_book

logger = logging.getLogger(__name__)

# Аномально долгий проход по линии — предупреждение, подбор не меняет.
DELAY_LIMIT_SECONDS = 6 * 3600

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
        info.append(
            ProfileInfo(
                name=parsed.raw,
                canonical_name=photo.get("name") or parsed.name,
                has_photo=bool(photo.get("thumb")),
                photo_thumb=photo.get("thumb"),
                photo_full=photo.get("full"),
                processing=parsed.processing,
                updated_at=photo.get("updated_at"),
            )
        )
    return info


@router.get("", response_model=DashboardResponse)
async def get_dashboard(
    days: int | None = Query(default=7, ge=1, le=365, description="Days to look back"),
    limit: int | None = Query(default=100, ge=1, le=1000, description="Max records"),
    loading_only: bool = Query(default=True, description="Only show rows that are loading (time is empty)"),
):
    """
    Get dashboard data with production records.

    Returns recent production data from Excel file with profile photos from catalog.
    """
    try:
        products = await asyncio.to_thread(
            excel_service.get_products, limit=limit, days=days, loading_only=loading_only
        )

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
            to_hanger_data(product, _build_profiles_info(product.profile, photos_map)) for product in products
        ]

        return DashboardResponse(
            success=True, products=hanger_data, total=len(hanger_data), total_all=len(products), days_filter=days
        )
    except Exception as e:
        return DashboardResponse(success=False, error=str(e))


def get_excel_internal_modified_time(file_path: Path) -> datetime | None:
    """
    Try to read the internal modified time from the Excel file's docProps/core.xml.
    Returns datetime in local timezone if found, otherwise None.
    """
    import xml.etree.ElementTree as ET
    import zipfile

    try:
        with zipfile.ZipFile(file_path, "r") as z:
            core_xml = z.read("docProps/core.xml")
            root = ET.fromstring(core_xml)
            for elem in root.iter():
                if elem.tag.endswith("}modified"):
                    val = elem.text
                    if val:
                        if val.endswith("Z"):
                            val = val[:-1] + "+00:00"
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
    return await asyncio.to_thread(_file_status)


def _display_path(path: Path | None) -> str | None:
    """Путь для ответа API; ``resolve`` на недоступной шаре не должен ронять статус."""
    if path is None:
        return None
    try:
        return str(path.resolve())
    except OSError:
        return str(path)


def _standby_fields() -> dict:
    """Поля режима запасной книги для строки статуса (ADR 0009)."""
    return {
        "role": excel_service.current_role,
        "main_file_path": _display_path(excel_service.main_path),
        "reserve_file_path": _display_path(excel_service.reserve_path),
        **standby_book.status(),
    }


def _file_status() -> FileStatus:
    """``stat`` книги и чтение docProps/core.xml — синхронные, для потока."""
    import time

    try:
        path = excel_service.current_path

        # Check if path is configured
        if not path:
            return FileStatus(
                is_open=False,
                status_text="Путь не настроен",
                error="EXCEL_FILE_PATH не указан в .env",
                **_standby_fields(),
            )

        # Тот же текст, что в /settings и в ответе выбора: иначе относительный
        # путь из конфигурации (``../testdata/…``) уходил бы в статус как есть,
        # а остальные поверхности показывали разрешённый.
        path = path.resolve()

        # Check if file exists
        if not path.exists():
            return FileStatus(
                is_open=False,
                file_name=path.name,
                file_path=str(path),
                status_text="Файл не найден",
                error=f"Файл не найден: {path}",
                **_standby_fields(),
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
            seconds_since_modified=seconds_since_modified,
            **_standby_fields(),
        )
    except Exception as e:
        return FileStatus(status_text="Ошибка", error=str(e))


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

    Существующий на этой машине путь важнее подстановки в каталог книги:
    Windows-сервер читает шару сам. Иначе устаревшая запись выбора
    (``active_excel.json`` от другой среды или тестов) уводила бы реальный
    путь внутрь своего каталога — ровно так книга из pytest-времянки
    подменяла рабочую.
    """
    book_dir = excel_service.directory
    path = Path(raw_path)

    tail = share_tail(raw_path)
    if tail and book_dir is not None:
        if path.is_absolute() and path_exists(path):
            return path.resolve()
        # В контейнере путь оператора не разрешается: хвост ищется в каталоге
        # книги. Если и там нет — в ошибке должно стоять место поиска.
        return book_dir.joinpath(*tail).resolve()

    if not path.is_absolute() and not path.root:
        if book_dir is None:
            raise HTTPException(
                status_code=400,
                detail="Невозможно разрешить относительный путь: каталог книги неизвестен",
            )
        path = book_dir / path
    return path.resolve()


def _validate_book_file(target_file: Path) -> Path:
    """Книга существует, является файлом и имеет расширение Excel."""
    if not path_exists(target_file):
        raise HTTPException(status_code=404, detail=_not_found_detail(target_file))
    if not target_file.is_file():
        raise HTTPException(status_code=400, detail=f"Указанный путь не является файлом: {target_file}")
    if target_file.suffix.lower() not in (".xlsx", ".xls", ".xlsm"):
        raise HTTPException(status_code=400, detail=f"Недопустимое расширение файла: {target_file.suffix}")
    return target_file


async def _announce_book_change(payload: dict, message: str) -> None:
    """Разослать открытым экранам, что читается другая книга."""
    try:
        from app.schemas.websocket import WebSocketMessage
        from app.services.websocket_manager import websocket_manager

        await websocket_manager.broadcast(
            WebSocketMessage(type="data_update", payload={**payload, "message": message}, timestamp=datetime.now())
        )
    except Exception as ws_err:
        logger.warning(f"Could not broadcast websocket update for file switch: {ws_err}")


@router.post("/excel/select")
async def select_excel_file(request: ExcelFileSelectRequest):
    """Выбрать основную книгу и читать её.

    Прежний вход «Ввести путь»: оператор указал книгу — она заведомо основная.
    Роли запасной книги задаются отдельно (``/excel/books``).
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

        target_file = _validate_book_file(_resolve_book_file(file_path))

        await asyncio.to_thread(excel_service.set_main_file, str(target_file))
        standby_book.reset()
        logger.info(f"[DASHBOARD API] Switched active Excel file to: {target_file}")

        await _announce_book_change(
            {"source": "excel", "file": target_file.name, "file_path": str(target_file)},
            f"Активный файл Excel изменен на {target_file.name}",
        )

        return {"success": True, "active": str(target_file)}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[DASHBOARD API] Failed to select Excel file: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.get("/excel/books", response_model=ExcelBooksState)
async def get_excel_books():
    """Текущие книги и история введённых путей.

    История живёт на сервере, а не в браузере: киоск меняется, профиль
    чистится, а «какие книги были раньше» должно остаться.
    """
    return ExcelBooksState(
        main=_display_path(excel_service.main_path),
        reserve=_display_path(excel_service.reserve_path),
        active=_display_path(excel_service.current_path),
        recent=[
            RecentBookPath(path=item["path"], used_at=item["used_at"] or None)
            for item in excel_service.recent_files
        ],
    )


@router.post("/excel/books")
async def set_excel_books(request: ExcelBooksRequest):
    """Задать роли книг: основную и запасную (ADR 0009).

    Диалог ввода пути задаёт только роли — какую книгу читать, решает правило
    ``standby_book`` по наполненности. Пустая запасная выключает режим.
    """
    try:
        main_raw = normalize_path_input(request.main_path or "")
        if not main_raw:
            raise HTTPException(status_code=400, detail="Не указан путь к основной книге (main_path)")
        main_file = _validate_book_file(_resolve_book_file(main_raw))

        reserve_raw = normalize_path_input(request.reserve_path) if request.reserve_path else ""
        reserve_file: Path | None = None
        if reserve_raw:
            reserve_file = _validate_book_file(_resolve_book_file(reserve_raw))
            if reserve_file == main_file:
                raise HTTPException(status_code=400, detail="Запасная книга совпадает с основной")

        await asyncio.to_thread(
            excel_service.set_book_roles,
            str(main_file),
            str(reserve_file) if reserve_file is not None else None,
        )
        # Новые роли — новые книги: прежние замеры к ним не относятся, иначе
        # правило сравнило бы строки разных файлов.
        standby_book.reset()

        active = _display_path(excel_service.current_path)
        await _announce_book_change(
            {
                "source": "excel",
                "file": main_file.name,
                "file_path": active,
                "role": excel_service.current_role,
            },
            f"Книга учёта: основная — {main_file.name}"
            + (f", запасная — {reserve_file.name}" if reserve_file is not None else ", запасной нет"),
        )

        return {
            "success": True,
            "main": str(main_file),
            "reserve": str(reserve_file) if reserve_file is not None else None,
            "active": active,
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[DASHBOARD API] Failed to set Excel book roles: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.get("/status/opcua", response_model=FileStatus)
async def get_opcua_status():
    """
    Get OPC UA connection status from the cached service state.

    Соединением владеет фоновый ``_worker``: статус — мгновенное чтение
    памяти, а не попытка подключиться. Иначе при лежащем PLC каждый опрос
    дашборда ждал бы весь цикл переподключения.
    """
    try:
        from app.services.opcua_service import opcua_service

        # Текст состояния — свойство сервиса: ``CONNECTING`` не должен
        # читаться как «Отключено», и правило одно на все поверхности.
        return FileStatus(
            is_open=opcua_service.is_connected,
            status_text=opcua_service.status_text,
            last_modified=datetime.now(),
        )
    except Exception as e:
        return FileStatus(is_open=False, status_text="Ошибка", error=str(e), last_modified=datetime.now())


@router.get("/opcua-unload-matched", response_model=list[MatchedUnloadEvent])
async def get_opcua_matched_unload_events(
    limit: int = Query(default=100, ge=1, le=500, description="Max events to return"),
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

        book = await asyncio.to_thread(get_book_rows)
        products = book.products
        rows_by_hanger = book.by_hanger

        photos_map = await catalog_service.get_profiles_photos_batch(_collect_profile_names(products))

        matches = match_cycles_to_rows(cycles, rows_by_hanger)
        matched: list[MatchedUnloadEvent] = []
        for m in matches:
            cycle, row = m.cycle, m.row
            hanger_num = str(cycle.get("hanger"))
            code, warning = _warning_for(m)

            profiles_info = _build_profiles_info(row.profile if row else "", photos_map)
            matched.append(
                MatchedUnloadEvent(
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
                )
            )

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
        raise HTTPException(status_code=500, detail=str(e)) from e


def _warning_for(m: CycleMatch):
    """Код бейджа и текст-тултип для результата подбора.

    На экране живут только метки, которые оператор может понять и на которые
    может отреагировать: долгий проход и выгрузка без прохода. Расхождение
    входа на экран не идёт и после калибровки: это вердикт подбора, а не
    состояние прохода, а ложная метка хуже пропущенной; расхождение видно
    в журнале (``match_log_line``).
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
    excel_reserve_path: str
    excel_role: str | None
    opcua_endpoint: str


class SettingsUpdateRequest(BaseModel):
    simulation_enabled: bool


def _settings_response() -> SettingsResponse:
    """Настройки с книгой: активная, запасная и роль читаемой сейчас."""
    from app.services.opcua_service import opcua_service

    return SettingsResponse(
        simulation_enabled=settings.SIMULATION_ENABLED,
        excel_path=_display_path(excel_service.current_path) or "",
        excel_reserve_path=_display_path(excel_service.reserve_path) or "",
        excel_role=excel_service.current_role,
        opcua_endpoint=opcua_service.endpoint,
    )


@router.get("/settings", response_model=SettingsResponse)
async def get_settings():
    """Get current simulation settings."""
    return _settings_response()


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
            await asyncio.to_thread(settings.update_simulation_mode_in_env, new_mode)

            # 3. Update OPC UA service
            await opcua_service.update_simulation_mode(new_mode)

            # 4. Update Excel service
            await asyncio.to_thread(excel_service.update_simulation_mode)

            logger.info(f"[DASHBOARD API] Dynamically toggled simulation_enabled to: {new_mode}")

            # 5. Broadcast dynamic WS settings update
            try:
                from app.schemas.websocket import WebSocketMessage
                from app.services.websocket_manager import websocket_manager

                message = WebSocketMessage(
                    type="data_update",
                    payload={
                        "source": "settings",
                        "simulation_enabled": new_mode,
                        "message": f"Режим работы переключен на {'ТЕСТОВЫЙ' if new_mode else 'РАБОЧИЙ'}",
                    },
                    timestamp=datetime.now(),
                )
                await websocket_manager.broadcast(message)
            except Exception as ws_err:
                logger.warning(f"Could not broadcast websocket update for mode switch: {ws_err}")

        return SettingsResponse(
            simulation_enabled=settings.SIMULATION_ENABLED,
            excel_path=_display_path(excel_service.current_path) or "",
            excel_reserve_path=_display_path(excel_service.reserve_path) or "",
            excel_role=excel_service.current_role,
            opcua_endpoint=opcua_service.endpoint,
        )
    except Exception as e:
        logger.error(f"[DASHBOARD API] Failed to update settings: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e)) from e
