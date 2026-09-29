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
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, List

from app.services.hanger_journal import JournalStore, journal_store
from app.services.matching import CycleMatch, match_cycles_to_rows, match_log_line

logger = logging.getLogger(__name__)

# Как часто фоновая задача смотрит, не появились ли новые проходы.
FLUSH_INTERVAL_SECONDS = 5
# Сколько последних проходов монитора разбираем за один опрос. Хватает с
# запасом: между опросами линия успевает отработать несколько выходов, а
# разбор месяца строк каждый раз — это работа ради пустого результата.
LOOKBACK_EVENTS = 200
# Сколько уже записанных проходов помним, чтобы не принять старый проход
# за новый после перезапуска.
RECENT_KEYS_MAX = 2000


def record_from_match(match: CycleMatch) -> Dict[str, Any]:
    """Запись журнала по проходу и результату сопоставления.

    Поля — те же, что у строки сопоставления (``matching.match_log_line``),
    плюс поля строки книги: из них собираются колонки таблицы журнала.
    Пустая книга учёта записывается как ``None``, а не как ``—``: в файле
    «нет значения», и так его читает и ``grep``, и разбор.
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


def _event_key(cycle: Dict[str, Any]) -> tuple:
    """Ключ прохода для дедупликации.

    У нормального прохода он есть — ``cycle_id`` монотонен и не
    переиспользуется. У аварийного события (``cycle_error``) прохода нет,
    и ключом служит номер подвеса с временем выхода.
    """
    cycle_id = cycle.get("cycle_id")
    if cycle_id is not None:
        return ("cycle", cycle_id)
    return ("event", cycle.get("hanger"), cycle.get("exit_at"))


class JournalWriter:
    """Пишет новые проходы в журнал и поднимает их в лог контейнера.

    Наружу смотрит тремя операциями: ``flush`` (записать всё новое — её
    зовёт фоновая задача), ``run_forever`` (собственно задача) и
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
        # Ключи уже записанных проходов. Наполняется чтением журнала при
        # старте — иначе после перезапуска последние проходы записались бы
        # в файл повторно.
        self._written: set = set()

    def load_written_keys(self, days: int = 2) -> None:
        """Пометить уже записанные проходы как записанные.

        Читаются последние сутки журнала: старше монитор всё равно не
        показывает, а читать месяц файлов ради handful ключей незачем.
        """
        today = datetime.now().strftime("%Y-%m-%d")
        for record in self.store.query(date_from=today, date_to=today, limit=500).items:
            self._remember(_record_key(record))

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
        self._written.add(key)
        while len(self._written) > RECENT_KEYS_MAX:
            self._written.pop()

    def prune(self) -> List[Path]:
        """Удалить файлы старше срока хранения (с записью в лог)."""
        return self.store.prune()

    async def run_forever(
        self, line_monitor, interval: int = FLUSH_INTERVAL_SECONDS
    ) -> None:
        """Фоновая задача: раз в ``interval`` секунд дописывает новые проходы.

        Ошибка одного прохода не роняет задачу: иначе одна битая запись
        молча прекращала бы журнал до перезапуска сервера.
        """
        while True:
            try:
                await self.flush(line_monitor)
            except asyncio.CancelledError:
                raise
            except Exception as error:
                logger.error(f"[Journal] Flush failed: {error}", exc_info=True)
            await asyncio.sleep(interval)


def _record_key(record: Dict[str, Any]) -> tuple:
    """Ключ прохода из уже записанной записи журнала."""
    if record.get("cycle_id") is not None:
        return ("cycle", record["cycle_id"])
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
