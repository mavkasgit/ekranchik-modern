"""
Excel Service - handles Excel file parsing, caching, and data extraction.
"""

import json
import logging
import re
import time
from datetime import datetime, timedelta
from pathlib import Path
from threading import Lock
from typing import Any

import pandas as pd

from app.core.config import settings
from app.services.hanger_row import EMPTY, HangerRow

logger = logging.getLogger(__name__)

# Путь к сетевой шаре: \\host\share\… либо диск с буквой Z:\… (после нормализации
# разделителей). Хвост после шары — то, что сохраняется в смонтированном каталоге.
_SHARE_PATH_RE = re.compile(r"^(?:\\\\[^\\]+\\[^\\]+|[A-Za-z]:)(?:\\(.*))?$")

# Кавычки, которыми обрамляют путь при копировании: прямые, типографские,
# угловые. Пара может быть разной («…»), поэтому проверяются оба края.
_PATH_QUOTES = "\"'`“”„‟«»‘’‹›"

# Строки листа, пропускаемые при чтении данных: две инструкции и строка
# заголовков. Индекс первой строки данных в датафрейме равен нулю, а в
# листе (нумерация с единицы) она идёт под номером
# ``DATA_ROWS_SKIPPED + 1``.
DATA_ROWS_SKIPPED = 3

# Сколько введённых путей помним на сервере. Браузерная память (localStorage)
# живёт на одной машине и стирается с профилем; оператор меняет киоск, и
# «какие книги были раньше» должно переживать это. 20 путей — несколько недель
# работы с редкой сменой книги.
RECENT_FILES_LIMIT = 20


def normalize_path_input(path_text: str) -> str:
    """Путь из буфера обмена: пробелы и кавычки по краям, в т.ч. типографские.

    Оператор копирует путь из проводника, письма или строки статуса, и он
    приходит в кавычках любого вида и с пробелами вокруг них. Пробелы внутри
    пути (в имени книги) сохраняются: снимается только рамка.
    """
    value = path_text.strip()
    while len(value) >= 2 and value[0] in _PATH_QUOTES and value[-1] in _PATH_QUOTES:
        value = value[1:-1].strip()
    return value


def path_exists(path: Path) -> bool:
    """``exists()`` по пути, который может быть чужим для этой машины.

    Ядро отвечает на такой путь не только ENOENT: windows-путь с обратными
    слэшами в Linux-контейнере даёт EINVAL, и без перехвата наружу уходил бы
    500 вместо «файл не найден».
    """
    try:
        return path.exists()
    except OSError:
        return False


def share_tail(path_text: str) -> list[str] | None:
    """Части пути после шары или диска: ``\\\\host\\share\\a\\b.xlsm`` → ``['a', 'b.xlsm']``.

    Оператор набирает сетевую книгу так, как её видит его машина
    (``\\\\ktm-disk\\Оператор\\Учет КПЗ 2026.xlsm`` или ``Z:\\…``), а сервер — как
    каталог смонтированной шары. Функция отделяет хвост, который в этом
    каталоге сохраняется. ``None`` — путь не похож на путь к сетевой шаре либо
    хвоста нет (``\\\\host\\share``, ``Z:\\``).
    """
    text = path_text.strip().replace("/", "\\")
    match = _SHARE_PATH_RE.match(text)
    if not match or not match.group(1):
        return None
    parts = [part for part in match.group(1).split("\\") if part]
    return parts or None


class ExcelService:
    """
    Service for reading and parsing Excel files with production data.

    Features:
    - DataFrame caching with file modification detection
    - Profile parsing with processing extraction
    - Product filtering and pagination
    """

    @property
    def _persistence_path(self) -> Path:
        """Путь к файлу с последним введённым путём к книге.

        Имя файла берётся из настроек, а не хардкодится: у dev и прод-контейнера
        оно своё, иначе запись одной среды попадает в выбор другой.
        """
        static_dir = Path(settings.STATIC_DIR)
        filename = settings.excel_active_file_name
        if static_dir.exists():
            return static_dir / filename
        # Заводская машина (ADR 0002): static нет — хранить выбор в каталоге данных,
        # чтобы пережил обновление (раньше падал в CWD рядом с кодом).
        return settings.data_dir_path / filename

    def _load_persisted_books(self) -> dict[str, object]:
        """Выбор, роли книг и история введённых путей из файла выбора.

        Старый формат — только ``active_file``. Тогда основная книга — это
        она же: у оператора ещё нет запасной, и режим выключен.
        """
        empty: dict[str, object] = {
            "active_file": None,
            "main_file": None,
            "reserve_file": None,
            "recent_files": [],
        }
        try:
            path = self._persistence_path
            if path.exists():
                with open(path, encoding="utf-8") as f:
                    data = json.load(f)
                active = data.get("active_file") or None
                recent_files = self._parse_recent_files(data.get("recent_files"))
                if not recent_files and active:
                    # Старая установка: история ещё не писалась. Текущая книга
                    # — точно один из путей, которые оператор вводил.
                    recent_files = [{"path": active, "used_at": ""}]
                return {
                    "active_file": active,
                    "main_file": data.get("main_file") or active,
                    "reserve_file": data.get("reserve_file") or None,
                    "recent_files": recent_files,
                }
        except Exception as e:
            logger.error(f"Failed to load active file from persistence: {e}")
        return empty

    @staticmethod
    def _parse_recent_files(raw: object) -> list[dict[str, str]]:
        """История путей из файла: мусор и дубли наружу не отдаём."""
        if not isinstance(raw, list):
            return []
        result: list[dict[str, str]] = []
        seen: set[str] = set()
        for item in raw:
            if not isinstance(item, dict):
                continue
            path = item.get("path")
            if not isinstance(path, str):
                continue
            path = path.strip()
            if not path or path in seen:
                continue
            seen.add(path)
            used_at = item.get("used_at")
            result.append({"path": path, "used_at": used_at if isinstance(used_at, str) else ""})
            if len(result) >= RECENT_FILES_LIMIT:
                break
        return result

    def _save_persisted_books(self) -> None:
        """Записать выбор, роли и историю путей одной записью."""
        try:
            path = self._persistence_path
            path.parent.mkdir(parents=True, exist_ok=True)
            payload = {
                "active_file": self._active_file_name,
                "main_file": self._main_file_name,
                "reserve_file": self._reserve_file_name,
                "recent_files": self._recent_files,
            }
            with open(path, "w", encoding="utf-8") as f:
                json.dump(payload, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"Failed to save active file to persistence: {e}")

    def __init__(self):
        self._cache: pd.DataFrame | None = None
        self._cache_mtime: float | None = None
        self._cache_path: Path | None = None
        # Кэш читают и пишут потоки ``asyncio.to_thread``: без блокировки один
        # запрос видел бы половину обновления другого, а ждущий запрос не мог
        # бы убедиться, что книгу уже перечитали.
        self._lock = Lock()
        persisted = self._load_persisted_books()
        self._active_file_name = persisted["active_file"]
        # Роли книг: какая книга основная, какая запасная. Владелец решения
        # «какую читать» — по-прежнему этот сервис (ADR 0003); роли лишь
        # задают, между чем выбирает правило (app.services.standby_book).
        self._main_file_name = persisted["main_file"]
        self._reserve_file_name = persisted["reserve_file"]
        # История введённых путей: её спрашивает диалог книг, чтобы оператор
        # видел, какие книги уже были, и не набирал путь заново.
        self._recent_files: list[dict[str, str]] = persisted["recent_files"]
        # Кэш числа строк по каждой книге: фоновая задача сравнивает две книги
        # каждые 30 секунд, и общий кэш разбора перечитывал бы обе попеременно.
        self._row_count_cache: dict[str, tuple[int, int, int]] = {}
        self._row_count_lock = Lock()
        # О каком выборе уже сказали в лог: свойство спрашивают на каждый
        # запрос статуса, повторять одно предупреждение незачем.
        self._warned_about: str | None = None

    def _resolve_name(self, file_name: str | None) -> Path | None:
        """Записанное имя/путь → путь: имя достраивается до каталога книги.

        Имя без пути — старый формат записи (``Учет КПЗ 2026.xlsm``), его
        достраивают каталогом книги. Путь с корнем (``/app/excel/…``,
        ``\\\\host\\share\\…``, ``Z:\\…``) отдаётся как есть: приклеивать его к
        каталогу нельзя — из ``/app/excel/…`` так получается чужой путь
        ``\\\\host\\share\\app\\excel\\…``, которого нет. Путь к сетевой шаре
        распознаётся и на Linux, где он не абсолютный: там он тоже чужой.
        """
        if not file_name:
            return None
        path = Path(file_name)
        if path.is_absolute() or path.root or share_tail(file_name):
            return path
        if not settings.configured_excel_path:
            return None
        return settings.configured_excel_path.parent / path

    def _resolved_active(self) -> Path | None:
        """Выбор из интерфейса → путь (см. ``_resolve_name``)."""
        return self._resolve_name(self._active_file_name)

    @property
    def current_path(self) -> Path | None:
        """Путь к активной книге учёта.

        Выбор из интерфейса перекрывает конфигурацию, но только если файл
        существует здесь. ``active_excel.json`` лежит в общем каталоге `static`,
        и на машине, где рядом живут dev и прод-контейнер, в него попадает
        путь соседней среды (``/app/excel/…`` против
        ``\\\\172.17.11.7\\Оператор\\…``). Чужой путь книгу не подменяет —
        берётся путь из конфигурации, а в лог идёт предупреждение.
        """
        chosen = self._resolved_active()
        if chosen is None:
            return settings.configured_excel_path
        if path_exists(chosen):
            return chosen

        configured = settings.configured_excel_path
        if configured is not None and path_exists(configured):
            if self._warned_about != self._active_file_name:
                self._warned_about = self._active_file_name
                logger.warning(
                    f"[Excel] Выбор {chosen} на этой машине не существует — книга берётся из конфигурации: {configured}"
                )
            return configured
        return chosen

    @property
    def directory(self) -> Path | None:
        """Каталог книги: у сервера — смонтированная сетевая папка.

        Один владелец правила для списка файлов, выбора по пути и подсказки в
        ошибке: сначала каталог активной книги, затем каталог из конфигурации.
        """
        for candidate in (self.current_path, settings.configured_excel_path):
            if candidate and path_exists(candidate.parent):
                return candidate.parent
        return None

    def _persist_and_watch(self) -> None:
        """Записать выбор в файл, сбросить кэш и перевести watcher на книгу."""
        self._save_persisted_books()
        self.invalidate_cache()

        # Restart watcher for new directory if it is running
        try:
            from app.services.excel_watcher import excel_watcher

            if excel_watcher.is_running:
                excel_watcher.stop()
            active_p = self.current_path
            if active_p and active_p.exists():
                excel_watcher.start(watch_path=active_p)
        except Exception as e:
            logger.warning(f"Could not restart ExcelWatcher for new path: {e}")

    def set_active_file(self, file_path: str) -> None:
        """Set active Excel file path/name and invalidate cache"""
        self._active_file_name = file_path
        self._persist_and_watch()

    @property
    def main_file_name(self) -> str | None:
        """Книга, которую правило считает основной."""
        return self._main_file_name

    @property
    def reserve_file_name(self) -> str | None:
        """Запасная книга либо ``None`` — режим выключен."""
        return self._reserve_file_name

    @property
    def main_path(self) -> Path | None:
        """Путь основной книги без подмены конфигурацией."""
        return self._resolve_name(self._main_file_name)

    @property
    def reserve_path(self) -> Path | None:
        """Путь запасной книги; ``None`` — режим выключен."""
        return self._resolve_name(self._reserve_file_name)

    @property
    def current_role(self) -> str | None:
        """Роль активной книги: ``main``, ``reserve`` либо ``None``.

        Сравниваем итоговый путь (``current_path``), а не записанный выбор:
        если выбранная книга исчезла, сервер уже читает книгу из конфигурации,
        и статус обязан называть то, что реально читается.
        """
        current = self.current_path
        if current is None:
            return None
        for role, candidate in (("main", self.main_path), ("reserve", self.reserve_path)):
            if candidate is None:
                continue
            try:
                if current.resolve() == candidate.resolve():
                    return role
            except OSError:
                if current == candidate:
                    return role
        return None

    @property
    def recent_files(self) -> list[dict[str, str]]:
        """История введённых путей, новые сверху: ``[{"path", "used_at"}]``."""
        return list(self._recent_files)

    def _remember_paths(self, paths: list[str | None]) -> None:
        """Запомнить пути, которыми оператор реально сохранил роли.

        Автоматическое переключение (``set_active_file``) историю не трогает:
        иначе правило само себе писало бы «новые пути», и список переставал
        бы отвечать на вопрос, какие книги выбирал человек.
        """
        stamp = datetime.now().astimezone().isoformat(timespec="seconds")
        fresh = list(dict.fromkeys(value.strip() for value in paths if value and value.strip()))
        if not fresh:
            return
        remembered = [{"path": path, "used_at": stamp} for path in fresh]
        remembered += [item for item in self._recent_files if item["path"] not in fresh]
        self._recent_files = remembered[:RECENT_FILES_LIMIT]

    def set_book_roles(self, main_file: str | None, reserve_file: str | None) -> None:
        """Задать роли книг и привести активную книгу к ним.

        Оператор задаёт только роли (ADR 0009): какую книгу читать, решает
        правило. Активную книгу сбрасываем на основную, лишь когда прежний
        выбор выпал из ролей — иначе переключение на запасную потерялось бы
        при каждом сохранении ролей.
        """
        self._main_file_name = main_file
        self._reserve_file_name = reserve_file
        if self._active_file_name not in (main_file, reserve_file):
            self._active_file_name = main_file
        self._remember_paths([main_file, reserve_file])
        self._persist_and_watch()

    def set_main_file(self, file_path: str) -> None:
        """Сделать книгу основной и читать её сейчас.

        Используется старым входом выбора пути: оператор указал книгу — она
        заведомо основная. Запасная, совпавшая с новой основной, сбрасывается:
        две роли на одном файле смысла не имеют.
        """
        reserve = self._reserve_file_name if self._reserve_file_name != file_path else None
        self._main_file_name = file_path
        self._reserve_file_name = reserve
        self._active_file_name = file_path
        self._remember_paths([file_path])
        self._persist_and_watch()

    def count_book_rows(self, file_path: Path | None) -> int | None:
        """Строк с реальными данными в книге либо ``None``, если не прочитать.

        Число считается по тому же листу и тому же признаку, что и данные
        дашборда: непустая строка с датой или номером подвеса. Свой кэш, а не
        общий разбор: замер идёт по двум книгам попеременно, и общий кэш
        перечитывал бы обе каждые 30 секунд.

        ``None`` — книга недоступна или ещё записывается. Это не то же самое,
        что «в книге ничего не пишется», поэтому вызывающий обязан различать
        эти случаи по ``path_exists``.
        """
        if file_path is None:
            return None
        try:
            stat = file_path.stat()
        except OSError:
            return None

        key = str(file_path)
        stamp = (stat.st_mtime_ns, stat.st_size)
        with self._row_count_lock:
            cached = self._row_count_cache.get(key)
        if cached is not None and cached[:2] == stamp:
            return cached[2]

        try:
            df = self._read_dataframe_by_header(file_path, "Подвесы")
            df = df.dropna(how="all")
            df = df[(pd.notna(df["date"])) | (pd.notna(df["number"]))]
            rows = int(len(df))
        except Exception as e:
            logger.warning(f"[Excel] Не удалось посчитать строки книги {file_path}: {e}")
            return None

        with self._row_count_lock:
            self._row_count_cache[key] = (stamp[0], stamp[1], rows)
        return rows

    @property
    def cache_mtime(self) -> float | None:
        """Get current cache modification time (for cache invalidation tracking)."""
        with self._lock:
            return self._cache_mtime

    @property
    def data_version(self) -> tuple:
        """Версия разобранной книги для внешних кэшей.

        Путь и mtime меняются при смене файла и записи в него, а ``id``
        разобранного листа — когда книга перечитана или подменена в тестах.
        Одного mtime мало: тест, подставивший другой лист с тем же именем,
        получил бы ответ из прежнего кэша.
        """
        with self._lock:
            mtime = self._cache_mtime
            cache_id = id(self._cache)
        return (str(self.current_path), mtime, cache_id)

    def invalidate_cache(self) -> None:
        """Force cache invalidation."""
        with self._lock:
            self._cache = None
            self._cache_mtime = None
            self._cache_path = None

    @property
    def active_file_name(self) -> str | None:
        """Книга, выбранная в этой сессии, либо ``None`` — берём из настроек.

        Это выбор, а не итоговый путь: несуществующий на этой машине файл
        ``current_path`` подменяет конфигурацией.
        """
        return self._active_file_name

    def use_file(self, file_path: str | None) -> None:
        """Читать книгу из указанного файла, не запоминая выбор.

        ``set_active_file`` пишет выбор в ``static/active_excel.json`` — он
        переживает перезапуск. Стенду и тестам нужна книга на один прогон:
        иначе подставленный файл переключил бы рабочий стенд.
        """
        self._active_file_name = file_path
        # Новая подстановка — новый выбор: память о предупреждении про прежний
        # выбор к нему не относится.
        self._warned_about = None
        self.invalidate_cache()

    @property
    def has_cached_data(self) -> bool:
        """В памяти лежит разобранный лист книги."""
        with self._lock:
            return self._cache is not None

    def _is_cache_valid(self, file_path: Path) -> bool:
        """Check if cached data is still valid. Вызывать под ``self._lock``."""
        if self._cache is None:
            return False
        if self._cache_path != file_path:
            return False
        try:
            current_mtime = file_path.stat().st_mtime
            return self._cache_mtime == current_mtime
        except OSError:
            return False

    def _cached_dataframe(self, file_path: Path) -> pd.DataFrame | None:
        """Разобранный лист из кэша либо ``None``, если книга изменилась."""
        with self._lock:
            if not self._is_cache_valid(file_path):
                return None
            logger.info(f"[CACHE HIT] Using cached data: {len(self._cache)} rows")
            return self._cache.copy()

    def _refresh_dataframe(self, file_path: Path, sheet_name: str) -> pd.DataFrame | None:
        """Перечитать книгу один раз; ждущие запросы берут готовый результат.

        Проверка mtime и кэша повторяется уже под блокировкой: пока запрос
        ждал, соседний мог перечитать ту же книгу, и второе чтение по CIFS
        было бы лишним.
        """
        with self._lock:
            if self._is_cache_valid(file_path):
                logger.info(f"[CACHE HIT] Using cached data: {len(self._cache)} rows")
                return self._cache.copy()

            # Read Excel file from specific sheet.
            # Columns are resolved by HEADER NAME (see column_map.py, mirrors
            # kpz-uchet/vba/ColRef.bas), with a legacy positional fallback.
            # This survives manual column insertions in the workbook (e.g. a
            # «Фамилия» column right after «Смена») that would shift positions.
            start_time = time.time()
            try:
                # Two-pass read: first the header row (rows 0-1 are
                # instructions), then only the resolved columns via usecols so
                # the calamine engine stays fast.
                df = self._read_dataframe_by_header(file_path, sheet_name)
                read_time = time.time() - start_time
                logger.info(f"[EXCEL READ] {len(df)} rows in {read_time:.2f}s from {file_path.name} (calamine)")

                # Remove completely empty rows
                df = df.dropna(how="all")

                # Filter: keep rows where date OR number is present
                df = df[(pd.notna(df["date"])) | (pd.notna(df["number"]))]

                logger.info(f"[EXCEL FILTERED] {len(df)} valid rows after filtering")

                self._cache = df
                self._cache_mtime = file_path.stat().st_mtime
                self._cache_path = file_path
                return df.copy()
            except Exception as e:
                logger.error(f"[EXCEL ERROR] Failed to read Excel file: {e}")
                if self._cache is not None:
                    return self._cache.copy()
                return None

    def get_dataframe(
        self, file_path: Path | None = None, sheet_name: str = "Подвесы", full_dataset: bool = False
    ) -> pd.DataFrame:
        """
        Get DataFrame from Excel file with caching.

        Args:
            file_path: Path to Excel file (uses config default if None)
            sheet_name: Name of the sheet to read (default: "Подвесы")
            full_dataset: If True, return all data; if False, filter recent

        Returns:
            DataFrame with production data
        """
        path = file_path or self.current_path
        if not path or not path.exists():
            return pd.DataFrame()

        df = self._cached_dataframe(path)
        if df is None:
            df = self._refresh_dataframe(path, sheet_name)
        if df is None:
            return pd.DataFrame()

        if full_dataset:
            return df

        # Filter to recent data (last 7 days by default)
        if "date" in df.columns:
            try:
                df["date"] = pd.to_datetime(df["date"], errors="coerce")
                cutoff = datetime.now() - timedelta(days=7)
                df = df[df["date"] >= cutoff]
            except Exception:
                pass

        return df

    def _read_dataframe_by_header(self, path: Path, sheet_name: str) -> pd.DataFrame:
        """
        Two-pass read that resolves columns by HEADER NAME (see column_map.py).

        Pass 1: read only the header row (rows 0-1 of the sheet are
        instructions; the real header is row 2).
        Pass 2: read only the resolved columns via usecols so the calamine
        engine stays fast.

        Resolution rule (mirrors kpz-uchet/vba/ColRef.bas):
        - Headers are matched by normalized name (lowercase, edge whitespace
          trimmed, interior preserved); the LAST match wins for duplicates.
        - If at least one field is found by name: use those positions, and
          fall back to legacy positions for the fields that did not match.
        - If NO field is found by name: use the legacy positional mapping
          entirely and log a warning.
        """
        from app.services.column_map import resolve_columns

        # Pass 1: header row only (rows 0-1 are instructions, header is row 2)
        header_df = pd.read_excel(
            path,
            sheet_name=sheet_name,
            header=None,
            skiprows=[0, 1],
            nrows=1,
            engine="calamine",
        )
        if header_df.empty:
            logger.warning(f"[EXCEL COLUMNS] Empty header row in {path.name}")
            return pd.DataFrame()

        header_row = header_df.iloc[0]
        resolution = resolve_columns(header_row)

        if not resolution.found_by_name:
            logger.warning(
                f"[EXCEL COLUMNS] No columns matched by header name in {path.name}; using legacy positional mapping"
            )
        elif resolution.missing:
            logger.warning(
                f"[EXCEL COLUMNS] Fields not found by name in {path.name}, "
                f"falling back to legacy positions: {', '.join(sorted(resolution.missing))}"
            )

        # Build the ordered usecols list and the matching column names.
        positions = resolution.positions
        usecols = sorted(set(positions.values()))
        col_to_field = {idx: field for field, idx in positions.items()}
        names = [col_to_field[idx] for idx in usecols]

        # Pass 2: data rows only (skip 2 instruction rows + 1 header row)
        df = pd.read_excel(
            path,
            sheet_name=sheet_name,
            header=None,
            skiprows=list(range(DATA_ROWS_SKIPPED)),
            usecols=usecols,
            engine="calamine",
        )
        df.columns = names
        return df

    def get_products(
        self,
        limit: int = 100,
        days: int = 7,
        filters: dict[str, Any] | None = None,
        from_end: bool = True,
        loading_only: bool = False,
    ) -> list[HangerRow]:
        """
        Get products from Excel with optional filtering.

        Args:
            limit: Maximum number of records to return (applied AFTER filtering)
            days: Number of days to look back (only used when from_end=False)
            filters: Optional filters (client, profile, etc.)
            from_end: If True, read from end; if False, apply date filter
            loading_only: If True, only return loading rows (date+material filled, time empty)

        Returns:
            List of product dictionaries (limited to 'limit' records)
        """
        df = self.get_dataframe(full_dataset=True)
        if df.empty:
            return []

        # Apply date filter only when not reading from end
        if not from_end and "date" in df.columns:
            try:
                df["date"] = pd.to_datetime(df["date"], errors="coerce")
                cutoff = datetime.now() - timedelta(days=days)
                df = df[df["date"] >= cutoff]
            except Exception:
                pass

        # Apply additional filters
        if filters:
            for key, value in filters.items():
                if key in df.columns and value:
                    df = df[df[key].astype(str).str.contains(str(value), case=False, na=False)]

        # Filter out completely empty rows for non-loading modes
        # This ensures sidebar gets a mix of loading and completed rows
        if not loading_only:

            def _is_empty_val(v):
                return pd.isna(v) or str(v).strip() in ("", EMPTY, "nan", "NaT")

            mask = ~(
                df.apply(
                    lambda row: (
                        _is_empty_val(row.get("profile"))
                        and _is_empty_val(row.get("material_type"))
                        and _is_empty_val(row.get("time"))
                    ),
                    axis=1,
                )
            )
            df = df[mask]
            logger.info(f"[FILTER] After removing empty rows: {len(df)} rows")

        # Process records with filtering
        records = self._process_dataframe(df, loading_only=loading_only)

        # Apply limit and sorting based on user preference
        if loading_only:
            # Special logic for Loading:
            # 1. Take OLDEST X rows (from the top of the spreadsheet)
            # 2. Show them in REVERSE order (newest of those at top)
            # This allows rows to disappear from the TOP when the limit is reduced
            if len(records) > limit:
                records = records[:limit]
            return records[::-1]
        else:
            # Standard logic for other modes (e.g. Last 100):
            # Take NEWEST X rows and show newest at top
            if len(records) > limit:
                records = records[-limit:]
            return records[::-1]

    def _process_dataframe(self, df: pd.DataFrame, loading_only: bool = False) -> list[HangerRow]:
        """
        Process DataFrame and return rows in the declared HangerRow form.
        Handles date/time formatting and lamels parsing.

        Args:
            loading_only: If True, only include loading rows (date+material filled, time empty)
        """
        products: list[HangerRow] = []

        # Filter by date - last 2 weeks for loading_only mode
        if loading_only and "date" in df.columns:
            try:
                logger.info(f"[FILTER] Before date filter: {len(df)} rows")
                # Convert date column to datetime
                df["date"] = pd.to_datetime(df["date"], errors="coerce")
                # Filter last 2 weeks
                cutoff = datetime.now() - timedelta(days=14)
                df = df[df["date"] >= cutoff]
                logger.info(
                    f"[FILTER] After date filter (last 2 weeks, cutoff={cutoff.strftime('%Y-%m-%d')}): {len(df)} rows"
                )
            except Exception as e:
                logger.warning(f"[FILTER] Could not filter by date: {e}")

        for _, row in df.iterrows():
            date_val = row.get("date")
            material_type = row.get("material_type")
            time_val = row.get("time")
            number_val = row.get("number")
            profile_val = row.get("profile")

            # Skip rows whose key fields are all empty
            def _is_empty(v):
                return pd.isna(v) or str(v).strip() in ("", EMPTY, "nan", "NaT")

            if _is_empty(number_val) and _is_empty(profile_val) and _is_empty(material_type):
                continue

            # For loading_only mode: strict filtering
            if loading_only:
                # Date must be filled
                if pd.isna(date_val) or not date_val:
                    continue
                # Material type must be filled
                if pd.isna(material_type) or not material_type or str(material_type).strip() in ("", EMPTY):
                    continue
                # Time must be EMPTY (this indicates a loading row, not unloading)
                if pd.notna(time_val) and str(time_val).strip() not in ("", EMPTY, "nan", "NaT"):
                    continue

            # Handle lamels (can be "30+30" or number)
            lamels = row.get("lamels_qty")
            if pd.notna(lamels):
                try:
                    lamels_display = int(float(lamels))
                except (ValueError, TypeError):
                    lamels_display = str(lamels)
            else:
                lamels_display = 0

            # Format time (remove seconds)
            time_str = EMPTY
            time_val = row.get("time")
            if pd.notna(time_val):
                if hasattr(time_val, "strftime"):
                    time_str = time_val.strftime("%H:%M")
                else:
                    time_val_str = str(time_val)
                    if ":" in time_val_str:
                        parts = time_val_str.split(":")
                        time_str = f"{parts[0]}:{parts[1]}"
                    else:
                        time_str = time_val_str

            # Format date
            date_str = EMPTY
            date_val = row.get("date")
            if pd.notna(date_val):
                try:
                    date_str = date_val.strftime("%d.%m.%y") if hasattr(date_val, "strftime") else str(date_val)
                except Exception:
                    date_str = str(date_val)

            profile_name = row.get("profile", EMPTY)
            if pd.isna(profile_name) or not profile_name:
                profile_name = EMPTY

            # Check for defect (брак)
            defect_val = row.get("defect")
            is_defect = False
            if pd.notna(defect_val):
                defect_str = str(defect_val).lower().strip()
                is_defect = "брак" in defect_str

            # Format number (convert float to int to avoid 10.0 format)
            number_val = row.get("number")
            if pd.notna(number_val):
                try:
                    number_display = int(float(number_val))
                except (ValueError, TypeError):
                    number_display = str(number_val)
            else:
                number_display = EMPTY

            products.append(
                HangerRow(
                    number=number_display,
                    # Лист читается с пропуском трёх строк (две инструкции и
                    # заголовки), поэтому первая строка данных имеет индекс 0,
                    # а в листе, где нумерация с единицы, идёт под номером 4.
                    # Проверено сверкой с листом: индекс + 4 попадает в ту же
                    # строку, на единицу меньше — уже соседняя.
                    sheet_row=int(row.name) + DATA_ROWS_SKIPPED + 1,
                    date=date_str,
                    time=time_str,
                    client=row.get("client") if pd.notna(row.get("client")) else EMPTY,
                    profile=str(profile_name).strip(),
                    color=row.get("color") if pd.notna(row.get("color")) else EMPTY,
                    lamels_qty=lamels_display,
                    kpz_number=row.get("kpz_number") if pd.notna(row.get("kpz_number")) else EMPTY,
                    material_type=row.get("material_type") if pd.notna(row.get("material_type")) else EMPTY,
                    is_defect=is_defect,
                )
            )

        logger.info(f"[FILTER] Final products after all filters: {len(products)}")
        return products

    def update_simulation_mode(self) -> None:
        """Обновляет активный файл и сбрасывает кэш при смене режима симуляции."""
        persisted = self._load_persisted_books()
        self._active_file_name = persisted["active_file"]
        self._main_file_name = persisted["main_file"]
        self._reserve_file_name = persisted["reserve_file"]
        self._recent_files = persisted["recent_files"]
        self.invalidate_cache()

        # Restart watcher for new directory if it is running
        try:
            from app.services.excel_watcher import excel_watcher

            if excel_watcher.is_running:
                excel_watcher.stop()
            active_p = self.current_path
            if active_p and active_p.exists():
                excel_watcher.start(watch_path=active_p)
        except Exception as e:
            logger.warning(f"Could not restart ExcelWatcher after mode switch: {e}")


# Singleton instance
excel_service = ExcelService()
