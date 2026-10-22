"""Фоновая запись проходов в журнал (issue #34).

Проход пишет в журнал САМ сервер, а не страница: раньше запись шла из
роута ``/opcua-unload-matched`` по запросу фронтенда, поэтому с закрытым
браузером (а на заводской машине он закрыт почти всегда) в журнале было
пусто, и ``docker logs`` оставался единственным источником.

Писатель опрашивает монитор линии, а не подписан на событие: у события
нет гарантии доставки, а потерянный проход в журнале невосстановима.
Дедупликация — по ``cycle_id`` (у аварийного события, у которого прохода
нет, — по номеру и времени выхода), поэтому повторный опрос того же
прохода не создаёт второй записи.
"""
import asyncio
import logging
from collections import OrderedDict
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Callable, Dict, List

from app.services.hanger_journal import (
    MAX_PAGE_SIZE,
    JournalStore,
    journal_store,
)
from app.services.matching import (
    CycleMatch,
    match_cycles_to_rows,
    match_log_line,
    parse_excel_date,
    parse_excel_time,
)

logger = logging.getLogger(__name__)


def _book_entry_at(row) -> str | None:
    """Момент загрузки в линию по книге учёта как ISO-метка.

    Это ЕДИНСТВЕННОЕ время, которое ведёт книга учёта: колонка «Время»,
    то есть фактический момент загрузки в линию. Выгрузку книга не
    записывает и записывать не будет, поэтому поля «выход по книге» в
    записи журнала нет — подставлять туда линию нельзя, сверка
    превратилась бы в сравнение источника с самим собой.

    Дату берём у строки книги, а не у прохода: загрузка всегда была ДО
    того, как монитор увидел подвес, то есть накануне (ночная смена).
    """
    if row is None:
        return None
    year, month, day = parse_excel_date(str(row.date))
    hour, minute, second = parse_excel_time(str(row.time))
    if not (year and month and day):
        return None
    return datetime(year, month, day, hour, minute, second).isoformat(
        timespec="seconds"
    )


# Как часто фоновая задача смотрит, не появились ли новые проходы, задаётся
# настройкой JOURNAL_FLUSH_INTERVAL.
# Сколько последних проходов монитора разбираем за один опрос — ровно столько,
# сколько монитор вообще помнит (``line_monitor.MAX_UNLOAD_EVENTS``). Меньше
# нельзя: проход, отложенный из-за недоступной книги учёта, выпал бы из окна
# и потерялся бы, а не дождался книги.
LOOKBACK_EVENTS = 500
# Сколько последних проходов поднимаем из журнала в память монитора при
# старте: панель «Выход» иначе пуста до первой новой выгрузки. Оператору
# нужен последний десяток; полная история — в Hanger Tracking.
RESTORE_EVENTS = 10
# Сколько уже записанных проходов помним. Держим всё окно flush и ещё
# столько же: пока проход виден монитору, его ключ обязан помниться, иначе
# он запишется в файл второй раз (см. JournalWriter._remember).
RECENT_KEYS_MAX = 2 * LOOKBACK_EVENTS
# Как часто убираются файлы старше срока хранения, секунд. Раз в сутки
# достаточно: суточный файл и так создаётся по одному.
PRUNE_INTERVAL_SECONDS = 24 * 3600


def record_from_match(match: CycleMatch) -> Dict[str, Any]:
    """Запись журнала по проходу и результату сопоставления.

    Поля — те же, что у строки сопоставления (``matching.match_log_line``),
    плюс поля строки книги: из них собираются колонки таблицы журнала.
    Пустая книга учёта записывается как ``None``, а не как ``—``: в файле
    «нет значения», и так его читает и ``grep``, и разбор.

    Моменты прохода лежат рядом и под именами по источнику: по линии
    (``line_*``) и по книге учёта (``book_entry_at``). Оператор сверяет
    проход с записью оператора, и без общего списка этих времён он читает
    вход и выход из разных колонок таблицы, где легко перепутать
    «загрузили» с «замерили». Выхода по книге нет и не будет: книга ведёт
    только загрузку в линию.
    """
    cycle = match.cycle
    row = match.row
    return {
        "recorded_at": datetime.now().isoformat(timespec="seconds"),
        "cycle_id": cycle.get("cycle_id"),
        "hanger": cycle.get("hanger"),
        "code": match.code,
        "source": cycle.get("first_seen_source"),
        "entry_bath": cycle.get("entry_bath"),
        "line_entry_at": cycle.get("first_seen_at"),
        "line_exit_at": cycle.get("exit_at"),
        "book_entry_at": _book_entry_at(row),
        "first_seen_at": cycle.get("first_seen_at"),
        "exit_at": cycle.get("exit_at"),
        "total_time_sec": cycle.get("total_time_sec"),
        "type": cycle.get("type"),
        "reason": cycle.get("reason"),
        "baths_visited": cycle.get("baths_visited"),
        "path": cycle.get("path") or [],
        "row_date": str(row.date) if row else None,
        "row_time": str(row.time) if row else None,
        "row_number": str(row.number) if row else None,
        # Номер строки ЛИСТА в книге: по нему оператор встаёт на строку
        # прямо в книге. ``row_number`` выше — это «№ по порядку» из
        # самой строки, другое число и другое назначение.
        "sheet_row": row.sheet_row if row else None,
        "profile": str(row.profile) if row else None,
        "color": str(row.color) if row else None,
        "kpz_number": str(row.kpz_number) if row else None,
        "lamels_qty": row.lamels_qty if row else None,
        "client": str(row.client) if row else None,
        "material_type": str(row.material_type) if row else None,
        "is_defect": bool(row.is_defect) if row else None,
        "entry_delta_sec": match.entry_delta_sec,
        "rows_after_exit": match.rows_after_exit,
        "note": match.suspect_reason,
    }


def event_from_record(record: Dict[str, Any]) -> Dict[str, Any]:
    """Событие монитора из записи журнала — для восстановления после старта.

    Поля события и записи называются по-разному (``source`` против
    ``first_seen_source``), а ``date``/``time`` события — уже разобранные
    локальные значения. Восстанавливаем ровно тот вид, который
    ``line_monitor`` кладёт в кэш, чтобы роут выгрузок не различал старые
    и новые проходы.
    """
    exit_at = record.get("exit_at")
    moment = _iso_datetime(exit_at) or _iso_datetime(record.get("recorded_at"))
    return {
        "type": record.get("type"),
        "reason": record.get("reason"),
        "cycle_id": record.get("cycle_id"),
        "hanger": record.get("hanger"),
        "first_seen_at": record.get("first_seen_at"),
        "first_seen_source": record.get("source"),
        "entry_bath": record.get("entry_bath"),
        "baths_visited": record.get("baths_visited"),
        "path": record.get("path") or [],
        "exit_at": exit_at,
        "total_time_sec": record.get("total_time_sec"),
        "time": moment.strftime("%H:%M:%S") if moment else "",
        "date": moment.strftime("%d.%m.%Y") if moment else "",
        "timestamp": exit_at or record.get("recorded_at"),
    }


def _iso_datetime(value: Any) -> datetime | None:
    """Разобрать ISO-метку события; None — поле пустое или битое."""
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value))
    except ValueError:
        return None


def _event_key(cycle: Dict[str, Any]) -> tuple:
    """Ключ прохода для дедупликации.

    Ключ — пара «номер прохода + момент выхода», а не один номер. Счётчик
    проходов живёт в памяти монитора и после перезапуска сервера начинается
    заново с единицы, а журнал живёт 30 суток: новый проход получает номер,
    который в файле за сегодня уже есть, и по одному номеру писатель счёл бы
    его записанным — молча потерял бы проход. Время выхода у одного и того же
    прохода не меняется, поэтому от дрожания датчика защита остаётся.

    У аварийного события (``cycle_error``) прохода нет: ключом служит номер
    подвеса с временем выхода.
    """
    cycle_id = cycle.get("cycle_id")
    exit_at = cycle.get("exit_at")
    if cycle_id is not None:
        return ("cycle", cycle_id, exit_at)
    return ("event", cycle.get("hanger"), exit_at)


class JournalWriter:
    """Пишет новые проходы в журнал и поднимает их в лог контейнера.

    Наружу смотрит четырьмя операциями: ``flush`` (записать всё новое — её
    зовёт фоновая задача), ``run_forever`` (собственно задача),
    ``restore_recent`` (вернуть последние проходы в память при старте) и
    ``prune`` (удаление старых файлов). Строки книги на входе ``flush``
    не берутся из сервисов, а приходят ``rows_provider``-ом: так
    разбор проходов отвязан от чтения книги и проверяется без Excel.
    """

    def __init__(
        self,
        store: JournalStore,
        rows_provider: Callable[[], Dict[str, List[Any]]],
    ):
        self.store = store
        self.rows_provider = rows_provider
        # Ключи уже записанных проходов, в порядке записи. Наполняется
        # чтением журнала при старте — иначе после перезапуска последние
        # проходы записались бы в файл повторно.
        self._written: "OrderedDict[tuple, None]" = OrderedDict()

    def load_written_keys(self) -> None:
        """Пометить уже записанные проходы как записанные.

        Берутся вчерашние и сегодняшние сутки: файл назван по суткам
        САМОГО прохода, поэтому проход, вышедший в 23:50 вчерашнего дня,
        лежит во вчерашнем файле, а монитор после полуночи его ещё видит.
        Порядок — от ранних к поздним, чтобы вытеснение уносило самые
        старые ключи (см. ``_remember``).
        """
        today = datetime.now()
        yesterday = (today - timedelta(days=1)).strftime("%Y-%m-%d")
        page = self.store.query(
            date_from=yesterday,
            date_to=today.strftime("%Y-%m-%d"),
            sort="exit_at",
            direction="desc",
            limit=MAX_PAGE_SIZE,
        )
        for record in reversed(page.items):
            self._remember(_record_key(record))

    def restore_recent(self, line_monitor) -> int:
        """Поднять последние проходы журнала в память монитора.

        Вызывается при старте после ``load_written_keys``: проходы уже
        лежат в журнале, и без пометки писатель записал бы их второй раз
        (для записей старше вчерашних суток ключей в памяти ещё нет).
        В монитор события возвращаются от старых к новым — в порядке, в
        котором их туда кладёт ``_publish``.
        """
        page = self.store.query(
            sort="exit_at", direction="desc", limit=RESTORE_EVENTS
        )
        if not page.items:
            return 0

        records = list(reversed(page.items))
        line_monitor.restore_unload_events(
            [event_from_record(record) for record in records]
        )
        for record in records:
            self._remember(_record_key(record))
        return len(records)

    async def flush(self, line_monitor) -> int:
        """Записать проходы, которых в журнале ещё нет. Возвращает их число."""
        events = line_monitor.get_unload_events(limit=LOOKBACK_EVENTS)
        # События монитор отдаёт новыми сверху, а сопоставление разбирает
        # проходы от ранних к поздним (одна строка книги достаётся первому).
        pending = [e for e in reversed(events) if _event_key(e) not in self._written]
        if not pending:
            return 0

        try:
            rows_by_hanger = self.rows_provider()
        except Exception as error:
            logger.warning(f"[Journal] Book rows unavailable, pass deferred: {error}")
            return 0

        written = 0
        for match in match_cycles_to_rows(pending, rows_by_hanger):
            key = _event_key(match.cycle)
            if key in self._written:
                continue
            try:
                self.store.append(record_from_match(match))
            except OSError as error:
                logger.error(f"[Journal] Could not write pass {key}: {error}")
                continue
            self._remember(key)
            written += 1
            # Та же строка, что раньше уходила в stdout из роута: в
            # docker logs она появляется независимо от открытого дашборда.
            logger.info(match_log_line(match, str(match.cycle.get("hanger"))))
        return written

    def _remember(self, key: tuple) -> None:
        """Запомнить ключ прохода, вытесняя самый старый.

        Вытеснение строго по порядку записи: проход, который вытеснили
        раньше, чем его перестал показывать монитор, записался бы в файл
        второй раз. Поэтому помнится всё окно ``flush`` и ещё столько же.
        """
        self._written[key] = None
        while len(self._written) > RECENT_KEYS_MAX:
            self._written.popitem(last=False)

    def prune(self) -> List[Path]:
        """Удалить файлы старше срока хранения (с записью в лог)."""
        return self.store.prune()

    async def run_forever(self, line_monitor, interval: int) -> None:
        """Фоновая задача: дописывает новые проходы и убирает старые файлы.

        Ошибка одного прохода не роняет задачу: иначе одна битая запись
        молча прекращала бы журнал до перезапуска сервера. Ротация по сроку
        идёт здесь же, а не только при старте: сервер может не перезапускаться
        месяцами, и срок хранения без неё не наступал бы никогда.
        """
        last_prune = asyncio.get_running_loop().time()
        while True:
            try:
                await self.flush(line_monitor)
                if asyncio.get_running_loop().time() - last_prune >= PRUNE_INTERVAL_SECONDS:
                    self.prune()
                    last_prune = asyncio.get_running_loop().time()
            except asyncio.CancelledError:
                raise
            except Exception as error:
                logger.error(f"[Journal] Journal task failed: {error}", exc_info=True)
            await asyncio.sleep(interval)


def _record_key(record: Dict[str, Any]) -> tuple:
    """Ключ прохода из уже записанной записи журнала.

    Строится по тем же полям, что и ключ события (см. ``_event_key``), иначе
    чтение журнала при старте помечало бы не те проходы и повторная запись
    проходила бы, а потерянные — нет.
    """
    if record.get("cycle_id") is not None:
        return ("cycle", record["cycle_id"], record.get("exit_at"))
    return ("event", record.get("hanger"), record.get("exit_at"))


# --- Экземпляр приложения ---
def _book_rows() -> Dict[str, List[Any]]:
    """Строки книги учёта, сгруппированные по номеру подвеса."""
    from app.services.excel_service import excel_service
    from app.services.matching import normalize_hanger_key

    products = excel_service.get_products(
        limit=1000, days=30, from_end=True, loading_only=False
    )
    rows: Dict[str, List[Any]] = {}
    for product in products:
        key = normalize_hanger_key(product.number)
        if key:
            rows.setdefault(key, []).append(product)
    return rows


journal_writer = JournalWriter(journal_store(), _book_rows)
