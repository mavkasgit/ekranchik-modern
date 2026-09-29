"""Чтение журнала подвесов из интерфейса (issue #34).

Отдельный роутер, а не ещё один эндпоинт дашборда: журнал — файл на
диске, а не состояние монитора, и его читают и таблица в интерфейсе, и
разбор вручную. В ответе вместе с проходами идёт путь к каталогу и имена
файлов — на заводской машине это единственное место, где видно, что
запись вообще идёт.
"""
import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Query
from pydantic import BaseModel, ValidationError

from app.services.hanger_journal import (
    DEFAULT_PAGE_SIZE,
    MAX_PAGE_SIZE,
    JournalFile,
    journal_store,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/journal", tags=["journal"])


class JournalPass(BaseModel):
    """Один проход подвеса в том виде, в каком он лежит в журнале.

    Поля повторяют запись JSONL: интерфейс показывает то, что записано,
    без пересчётов на своей стороне.
    """

    recorded_at: Optional[str] = None
    cycle_id: Optional[int] = None
    hanger: Optional[int] = None
    code: str = ""
    source: Optional[str] = None
    entry_bath: Optional[int] = None
    first_seen_at: Optional[str] = None
    exit_at: Optional[str] = None
    total_time_sec: Optional[float] = None
    type: Optional[str] = None
    reason: Optional[str] = None
    path: List[Dict[str, Any]] = []
    baths_visited: List[str] = []
    row_date: Optional[str] = None
    row_time: Optional[str] = None
    row_number: Optional[str] = None
    profile: Optional[str] = None
    color: Optional[str] = None
    kpz_number: Optional[str] = None
    lamels_qty: Optional[Any] = None
    client: Optional[str] = None
    material_type: Optional[str] = None
    is_defect: Optional[bool] = None
    entry_delta_sec: Optional[float] = None
    rows_after_exit: int = 0
    note: Optional[str] = None


class JournalFileInfo(BaseModel):
    """Файл журнала на диске: имя, размер, когда менялся."""

    name: str
    size_bytes: int
    modified_at: str


class JournalResponse(BaseModel):
    """Страница проходов вместе с тем, где лежит журнал."""

    items: List[JournalPass] = []
    total: int = 0
    limit: int = DEFAULT_PAGE_SIZE
    offset: int = 0
    directory: str = ""
    files: List[JournalFileInfo] = []
    retention_days: int = 0


@router.get("/passes", response_model=JournalResponse)
async def get_journal_passes(
    search: str = Query(default="", description="Номер подвеса, cycle_id, код, строка книги"),
    date_from: str = Query(default="", description="Сутки от (YYYY-MM-DD)"),
    date_to: str = Query(default="", description="Сутки по (YYYY-MM-DD)"),
    sort: str = Query(default="exit_at", description="Колонка сортировки"),
    direction: str = Query(default="desc", description="asc или desc"),
    limit: int = Query(default=DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE),
    offset: int = Query(default=0, ge=0),
):
    """Проходы подвесов из файла журнала: поиск, даты, сортировка, страница.

    Недоступный каталог отдаёт пустую страницу: вкладка журнала не должна
    ронять приложение из-за диска, а пустая таблица читается сама.
    """
    store = journal_store()
    try:
        page = store.query(
            search=search,
            date_from=date_from,
            date_to=date_to,
            sort=sort,
            direction=direction,
            limit=limit,
            offset=offset,
        )
        files = [_file_info(f) for f in store.files()]
        directory = str(store.directory)
        retention = store.retention_days
    except OSError as error:
        logger.error(f"[Journal] Read failed: {error}", exc_info=True)
        return JournalResponse(items=[], total=0, limit=limit, offset=offset)

    return JournalResponse(
        items=_passes(page.items),
        total=page.total,
        limit=page.limit,
        offset=page.offset,
        directory=directory,
        files=files,
        retention_days=retention,
    )


def _passes(records: list[dict]) -> list[JournalPass]:
    """Записи страницы в форме ответа; негодные пропускаются.

    Файл журнала лежит на диске: его может поправить человек, он может
    остаться от прежней версии приложения или там может оказаться мусор.
    Запись без времени выхода проходом не является — иначе она молча
    превратилась бы в пустую строку таблицы, где оператор ищет проход.
    Лишние поля, наоборот, терпятся: запись от более новой версии
    приложения показывается теми полями, что эта версия знает.
    """
    passes: list[JournalPass] = []
    for record in records:
        if not record.get("exit_at"):
            logger.warning(
                "[Journal] Skipped record without exit_at — это не проход: "
                f"{str(record)[:120]}"
            )
            continue
        try:
            passes.append(JournalPass(**record))
        except ValidationError as error:
            logger.warning(f"[Journal] Skipped record with unexpected fields: {error}")
    return passes


def _file_info(journal_file: JournalFile) -> JournalFileInfo:
    return JournalFileInfo(
        name=journal_file.name,
        size_bytes=journal_file.size_bytes,
        modified_at=journal_file.modified_at.isoformat(timespec="seconds"),
    )
