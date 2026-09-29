"""Журнал подвесов: файл с историей проходов по линии (issue #34).

Логи пишут сервисы, журнал пишет само приложение — и одинаково в трёх
режимах запуска: dev, контейнер и exe. Каталог журнала выводится из
``settings.data_dir_path`` рядом с БД, то есть в контейнере это
примонтированный том, а на заводской машине — каталог данных.

Формат — JSONL: одна строка на один проход. Набор полей тот же, что у
строки сопоставления (``matching.match_log_line``), но разобранный на поля:
таблицу в интерфейсе можно фильтровать и сортировать без регулярных
выражений, а файл по-прежнему грепается.

Ротация и хранение:
- сутки на файл, плюс потолок размера: файл той же сутки докатывается
  следующим (``-2``, ``-3``), чтобы один затормозивший день не съел диск;
- срок хранения (по умолчанию 30 дней) и удаление старых файлов — с записью
  в лог: молчаливое удаление хуже отсутствия удаления, потому что оператор
  потом не находит историю и не понимает, куда она делась.
"""
import json
import logging
import re
from collections import OrderedDict
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

FILE_PREFIX = "hanger-passes-"
FILE_SUFFIX = ".jsonl"
# Имя файла разбирается обратно в дату: ``hanger-passes-2026-09-29-2.jsonl``
# — второй файл за 29 сентября.
_FILE_RE = re.compile(r"^hanger-passes-(\d{4}-\d{2}-\d{2})(?:-(\d+))?\.jsonl$")

DEFAULT_RETENTION_DAYS = 30
DEFAULT_MAX_FILE_BYTES = 32 * 1024 * 1024
# Сколько записей отдавать за раз по умолчанию: журнал за месяц — десятки
# тысяч строк, и тянуть их все в ответ нельзя.
DEFAULT_PAGE_SIZE = 100
MAX_PAGE_SIZE = 500
# Сколько файлов журнала держим разобранными в памяти. Сутки хранится 30,
# плюс докатки по размеру — запас втрое перекрывает худший случай.
CACHE_FILES_MAX = 90

# Колонки, по которым разрешена сортировка. Ключ — имя поля записи,
# значение — функция, достающая из записи ключ сравнения. Сортировка по
# неразрешённой колонке молча падает на сортировку по времени выхода,
# а не на 500.
SORT_FIELDS = {
    "exit_at": lambda r: r.get("exit_at") or "",
    "first_seen_at": lambda r: r.get("first_seen_at") or "",
    "hanger": lambda r: _number_key(r.get("hanger")),
    "cycle_id": lambda r: _number_key(r.get("cycle_id")),
    "entry_delta_sec": lambda r: _number_key(r.get("entry_delta_sec")),
    "code": lambda r: r.get("code") or "",
    "profile": lambda r: r.get("profile") or "",
}
DEFAULT_SORT = "exit_at"


def _number_key(value: Any) -> float:
    """Числовой ключ сортировки; нечисло (нет расхождения, нет прохода)
    уходит в конец при обоих направлениях — см. ``query``."""
    try:
        return float(value)
    except (TypeError, ValueError):
        return float("-inf")


def _record_day(record: Dict[str, Any]) -> str:
    """Сутки прохода по его времени выхода (``YYYY-MM-DD``).

    Время выхода — единственное поле, по которому проход относятся к
    суткам; ``recorded_at`` может отставать на докатку файла, а книга
    учёта о сутках прохода ничего не говорит.
    """
    raw = str(record.get("exit_at") or "")
    return raw[:10] if len(raw) >= 10 else datetime.now().strftime("%Y-%m-%d")


@dataclass(frozen=True)
class JournalFile:
    """Файл журнала на диске — для интерфейса (имя, размер, записей)."""

    name: str
    path: Path
    size_bytes: int
    modified_at: datetime

    @property
    def day(self) -> str:
        """Сутки из имени файла (пусто у незнакомого имени)."""
        match = _FILE_RE.match(self.name)
        return match.group(1) if match else ""

    @property
    def part(self) -> int:
        """Номер файла внутри суток: 1 — основной, 2 и дальше — докатки."""
        match = _FILE_RE.match(self.name)
        return int(match.group(2)) if match and match.group(2) else 1

@dataclass
class JournalPage:
    """Страница выборки вместе с общим числом подходящих записей."""

    items: List[Dict[str, Any]] = field(default_factory=list)
    total: int = 0
    limit: int = DEFAULT_PAGE_SIZE
    offset: int = 0

    @property
    def has_more(self) -> bool:
        return self.offset + len(self.items) < self.total


class JournalStore:
    """Чтение и запись файлов журнала подвесов.

    Наружу смотрит четырьмя операциями: ``append`` (записать проход),
    ``query`` (выборка для таблицы), ``files`` (что лежит на диске) и
    ``prune`` (удалить старые файлы). Всё остальное — детали формата.
    """

    def __init__(
        self,
        directory: Path,
        retention_days: int = DEFAULT_RETENTION_DAYS,
        max_file_bytes: int = DEFAULT_MAX_FILE_BYTES,
    ):
        self.directory = Path(directory)
        self.retention_days = retention_days
        self.max_file_bytes = max_file_bytes
        self._today: Optional[str] = None
        self._current: Optional[Path] = None
        self._current_size = 0
        # Разобранные записи файлов, помеченные размером и временем, на
        # которых они прочитаны. Таблица опрашивается каждые 10 секунд, а
        # журнал за месяц — десятки тысяч строк: без этого каждый опрос
        # заново разбирал бы весь каталог. Файл меняется только дописыванием,
        # поэтому «размер не изменился» достаточно для признака актуальности.
        self._cache: "OrderedDict[str, tuple]" = OrderedDict()

    # --- Запись ---
    def append(self, record: Dict[str, Any]) -> Path:
        """Дописать запись прохода в суточный файл. Возвращает файл.

        Сутки файла — сутки САМОГО ПРОХОДА (его выхода), а не момента
        записи: иначе проход, вышедший за полночь, попал бы в чужой файл,
        и фильтр по датам вёл бы себя неожиданно.

        Запись целиком в память и одним ``write``: обрыв на середине строки
        оставил бы битый JSON, который выборка потом не прочитает.
        """
        path = self._current_path(_record_day(record))
        line = json.dumps(record, ensure_ascii=False) + "\n"
        self.directory.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(line)
        self._current_size = path.stat().st_size
        return path

    def _current_path(self, day: str) -> Path:
        """Файл, в который пишется запись за сутки ``day``.

        Потолок размера проверяется ДО записи: файл, который уже переполнен,
        докатывается следующим номером той же суток. Запись, которая сама
        переполнит потолок, всё равно пишется — иначе проход потерялся бы.
        """
        if self._current is None or day != self._today:
            self._today = day
            self._current = self._pick_latest_file(day)
            self._current_size = self._current.stat().st_size if self._current.exists() else 0
        if self._current_size >= self.max_file_bytes:
            self._current = self._next_file(day)
            self._current_size = 0
        return self._current

    def _pick_latest_file(self, day: str) -> Path:
        """Последний непустой файл за ``day`` — к нему дописываем."""
        parts = self._day_parts(day)
        if not parts:
            return self.directory / f"{FILE_PREFIX}{day}{FILE_SUFFIX}"
        return self.directory / f"{FILE_PREFIX}{day}-{parts[-1]}{FILE_SUFFIX}"

    def _next_file(self, day: str) -> Path:
        parts = self._day_parts(day)
        index = (parts[-1] + 1) if parts else 2
        return self.directory / f"{FILE_PREFIX}{day}-{index}{FILE_SUFFIX}"

    def _day_parts(self, day: str) -> List[int]:
        """Номера файлов за ``day``, по возрастанию."""
        parts: List[int] = []
        for path in self.directory.glob(f"{FILE_PREFIX}{day}-*{FILE_SUFFIX}"):
            match = _FILE_RE.match(path.name)
            if match and match.group(2):
                parts.append(int(match.group(2)))
        return sorted(parts)

    # --- Чтение ---
    def files(self) -> List[JournalFile]:
        """Файлы журнала, новые сверху (как таблица выхода)."""
        found: List[JournalFile] = []
        if not self.directory.exists():
            return found
        for path in self.directory.glob(f"{FILE_PREFIX}*{FILE_SUFFIX}"):
            if not path.is_file():
                continue
            stat = path.stat()
            found.append(
                JournalFile(
                    name=path.name,
                    path=path,
                    size_bytes=stat.st_size,
                    modified_at=datetime.fromtimestamp(stat.st_mtime),
                )
            )
        # Порядок по суткам и номеру файла внутри суток: в имени файла
        # зашиты и то и другое, поэтому сортировка не требует Stat.
        found.sort(key=lambda f: (f.day, f.part), reverse=True)
        return found

    def _files_for_range(self, date_from: str, date_to: str) -> List[JournalFile]:
        """Файлы, чьи сутки попадают в диапазон дат.

        Отсев по ИМЕНИ файла, а не по содержимому: на месяце это отсекает
        лишние файлы до чтения, а не после.
        """
        return [f for f in self.files() if date_from <= f.day <= date_to]

    def query(
        self,
        search: str = "",
        date_from: str = "",
        date_to: str = "",
        sort: str = DEFAULT_SORT,
        direction: str = "desc",
        limit: int = DEFAULT_PAGE_SIZE,
        offset: int = 0,
    ) -> JournalPage:
        """Выборка записей журнала: поиск, даты, сортировка, страница.

        Поиск идёт по номеру подвеса, ``cycle_id``, коду сопоставления и
        строке книги (профиль, КПЗ, время) одной строкой регистронезависимо.
        """
        limit = max(1, min(int(limit), MAX_PAGE_SIZE))
        offset = max(0, int(offset))
        key_fn = SORT_FIELDS.get(sort, SORT_FIELDS[DEFAULT_SORT])
        # Расхождение есть не у всех записей (нет строки книги — нет и
        # расхождения). Такие уходят в конец при обоих направлениях, иначе
        # «от большего к меньшему» на −inf оказывалось бы в начале.
        missing_last = sort == "entry_delta_sec"

        needle = search.strip().lower()
        records: List[Dict[str, Any]] = []
        for journal_file in self._files_for_range(date_from or "", date_to or "￿"):
            parsed = self._file_records(journal_file)
            if needle:
                parsed = [record for record in parsed if needle in _haystack(record)]
            records.extend(parsed)

        if missing_last:
            # Записи без расхождения всегда в конце, а порядок между
            # «больше» и «меньше» — по направлению сортировки.
            present = [r for r in records if key_fn(r) != float("-inf")]
            absent = [r for r in records if key_fn(r) == float("-inf")]
            present.sort(key=key_fn, reverse=direction == "desc")
            records = present + absent
        else:
            records.sort(key=key_fn, reverse=direction == "desc")

        return JournalPage(
            items=records[offset : offset + limit],
            total=len(records),
            limit=limit,
            offset=offset,
        )

    def _file_records(self, journal_file: JournalFile) -> List[Dict[str, Any]]:
        """Разобранные записи файла; при неизменном размере — из кэша.

        Кэш живёт в памяти процесса и сбрасывается по размеру файла: запись
        только дописывает, поэтому изменился размер — изменилось содержимое.
        Без кэша каждый опрос таблицы (раз в 10 секунд) разбирал бы весь
        месяц журнала заново.

        Битая строка пропускается с записью в лог: файл мог дописаться при
        обрыве питания, и одна такая строка не должна ронять выборку.
        """
        cached = self._cache.get(journal_file.name)
        if cached and cached[0] == journal_file.size_bytes:
            self._cache.move_to_end(journal_file.name)
            return cached[1]

        records: List[Dict[str, Any]] = []
        try:
            with journal_file.path.open("r", encoding="utf-8") as handle:
                for number, line in enumerate(handle, start=1):
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        records.append(json.loads(line))
                    except json.JSONDecodeError as error:
                        logger.warning(
                            f"[Journal] Skipped unreadable line {number} of "
                            f"{journal_file.name}: {error}"
                        )
        except OSError as error:
            logger.warning(f"[Journal] Could not read {journal_file.name}: {error}")
            return records

        self._cache[journal_file.name] = (journal_file.size_bytes, records)
        self._cache.move_to_end(journal_file.name)
        while len(self._cache) > CACHE_FILES_MAX:
            self._cache.popitem(last=False)
        return records

    def prune(self) -> List[Path]:
        """Удалить файлы старше срока хранения. Возвращает удалённые.

        Удаление пишется в лог списком: файл, исчезнувший без следа,
        неотличим от файла, который никогда не было.
        """
        cutoff = (datetime.now() - timedelta(days=self.retention_days)).strftime("%Y-%m-%d")
        removed: List[Path] = []
        for journal_file in self.files():
            if journal_file.day and journal_file.day < cutoff:
                try:
                    journal_file.path.unlink()
                except OSError as error:
                    logger.warning(
                        f"[Journal] Could not remove {journal_file.name}: {error}"
                    )
                    continue
                removed.append(journal_file.path)
        if removed:
            logger.warning(
                f"[Journal] Removed {len(removed)} file(s) older than "
                f"{self.retention_days} days: {', '.join(p.name for p in removed)}"
            )
        return removed


def _haystack(record: Dict[str, Any]) -> str:
    """Строка записи, по которой идёт поиск в таблице журнала."""
    parts = [
        record.get("hanger"),
        record.get("cycle_id"),
        record.get("code"),
        record.get("row_date"),
        record.get("row_time"),
        record.get("row_number"),
        record.get("profile"),
        record.get("kpz_number"),
        record.get("material_type"),
        record.get("note"),
    ]
    return " ".join(str(part) for part in parts if part not in (None, "")).lower()


# --- Каталог журнала ---
def journal_dir() -> Path:
    """Каталог файлов журнала: рядом с БД, то есть во всех режимах один.

    В контейнере это примонтированный том, поэтому файл переживает
    пересоздание контейнера; в exe — каталог данных из ADR 0002.
    """
    from app.core.config import settings

    return settings.journal_dir_path


def journal_store() -> JournalStore:
    """Экземпляр журнала под текущие настройки."""
    from app.core.config import settings

    return JournalStore(
        journal_dir(),
        retention_days=settings.JOURNAL_RETENTION_DAYS,
        max_file_bytes=settings.JOURNAL_MAX_FILE_BYTES,
    )
