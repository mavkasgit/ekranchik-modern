"""Чтение журнала подвесов из интерфейса (issue #34).

Отдельный роутер, а не ещё один эндпоинт дашборда: журнал — файл на
диске, а не состояние монитора, и его читают и таблица в интерфейсе, и
разбор вручную. В ответе вместе с проходами идёт путь к каталогу и имена
файлов — на заводской машине это единственное место, где видно, что
запись вообще идёт.
"""

import asyncio
import logging
from typing import Any, NamedTuple

from fastapi import APIRouter, Query
from pydantic import BaseModel, ValidationError

from app.services.hanger_journal import (
    DEFAULT_PAGE_SIZE,
    MAX_PAGE_SIZE,
    JournalFile,
    JournalPage,
    JournalStore,
    journal_store,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/journal", tags=["journal"])


class JournalPass(BaseModel):
    """Один проход подвеса в том виде, в каком он лежит в журнале.

    Поля повторяют запись JSONL: интерфейс показывает то, что записано,
    без пересчётов на своей стороне.
    """

    recorded_at: str | None = None
    cycle_id: int | None = None
    hanger: int | None = None
    code: str = ""
    source: str | None = None
    entry_bath: int | None = None
    first_seen_at: str | None = None
    exit_at: str | None = None
    # Моменты прохода рядом: по линии и по книге учёта. Интерфейс
    # показывает их вместе, ничего не дособирая у себя. Выхода по книге
    # нет и не будет: книга ведёт только загрузку в линию.
    line_entry_at: str | None = None
    line_exit_at: str | None = None
    book_entry_at: str | None = None
    total_time_sec: float | None = None
    type: str | None = None
    reason: str | None = None
    path: list[dict[str, Any]] = []
    # У записей, сделанных до этой правки, поле было null у аварийного
    # события. Читаем их как «список неизвестен», а не выбрасываем запись.
    baths_visited: list[str] | None = []
    row_date: str | None = None
    row_time: str | None = None
    row_number: str | None = None
    # Номер строки ЛИСТА в книге учёта: оператор встаёт на неё прямо в
    # книге. Не путать с row_number — это «№ по порядку» из самой строки.
    sheet_row: int | None = None
    profile: str | None = None
    color: str | None = None
    kpz_number: str | None = None
    lamels_qty: Any | None = None
    client: str | None = None
    material_type: str | None = None
    is_defect: bool | None = None
    entry_delta_sec: float | None = None
    rows_after_exit: int = 0
    note: str | None = None


class JournalFileInfo(BaseModel):
    """Файл журнала на диске: имя, размер, когда менялся."""

    name: str
    size_bytes: int
    modified_at: str


class JournalResponse(BaseModel):
    """Страница проходов вместе с тем, где лежит журнал."""

    items: list[JournalPass] = []
    total: int = 0
    limit: int = DEFAULT_PAGE_SIZE
    offset: int = 0
    directory: str = ""
    files: list[JournalFileInfo] = []
    retention_days: int = 0


class JournalView(NamedTuple):
    """Всё, что даёт одно чтение журнала в потоке: страница и место на диске.

    Четыре значения ходят вместе (их собирает ``_read_store`` и разбирает
    роут), но по отдельности они безымянны: ``page[3]`` не говорит, срок
    хранения это или каталог.
    """

    page: JournalPage
    files: list[JournalFileInfo]
    directory: str
    retention_days: int


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
        view = await asyncio.to_thread(
            _read_store,
            store,
            search=search,
            date_from=date_from,
            date_to=date_to,
            sort=sort,
            direction=direction,
            limit=limit,
            offset=offset,
        )
    except OSError as error:
        logger.error(f"[Journal] Read failed: {error}", exc_info=True)
        return JournalResponse(items=[], total=0, limit=limit, offset=offset)

    return JournalResponse(
        items=_passes(view.page.items),
        total=view.page.total,
        limit=view.page.limit,
        offset=view.page.offset,
        directory=view.directory,
        files=view.files,
        retention_days=view.retention_days,
    )


def _read_store(
    store: JournalStore,
    *,
    search: str,
    date_from: str,
    date_to: str,
    sort: str,
    direction: str,
    limit: int,
    offset: int,
) -> JournalView:
    """Страница, файлы и каталог журнала — одним чтением в потоке.

    ``store.query`` и ``store.files`` ходят на диск; в event loop они
    останавливали бы и WebSocket, и секундный опрос линии. Файлы читаются
    тем же вызовом, что и страница: между ними ответ всё равно несогласован.
    """
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
    return JournalView(
        page=page,
        files=files,
        directory=str(store.directory),
        retention_days=store.retention_days,
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
                f"cycle_id={record.get('cycle_id')} hanger={record.get('hanger')} "
                f"recorded_at={record.get('recorded_at')}"
            )
            continue
        try:
            passes.append(JournalPass(**record))
        except ValidationError as error:
            logger.warning(
                "[Journal] Skipped record with unexpected fields: "
                f"cycle_id={record.get('cycle_id')} hanger={record.get('hanger')} "
                f"exit_at={record.get('exit_at')}: {error}"
            )
    return passes


def _file_info(journal_file: JournalFile) -> JournalFileInfo:
    return JournalFileInfo(
        name=journal_file.name,
        size_bytes=journal_file.size_bytes,
        modified_at=journal_file.modified_at.isoformat(timespec="seconds"),
    )
