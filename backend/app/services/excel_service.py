"""
Excel Service - handles Excel file parsing, caching, and data extraction.
"""
import time
import json
import logging
import re
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, List, Dict, Any

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


def share_tail(path_text: str) -> Optional[List[str]]:
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
        """Path to save persistent configuration"""
        static_dir = Path(settings.STATIC_DIR)
        filename = "active_excel_sim.json" if settings.SIMULATION_ENABLED else "active_excel.json"
        if static_dir.exists():
            return static_dir / filename
        # Full mode (ADR 0002): static нет — хранить выбор в каталоге данных,
        # чтобы пережил обновление (раньше падал в CWD рядом с кодом).
        return settings.data_dir_path / filename

    def _load_persisted_active_file(self) -> Optional[str]:
        """Load the active file name from persistent JSON file"""
        try:
            path = self._persistence_path
            if path.exists():
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    val = data.get("active_file")
                    if val:
                        return val
        except Exception as e:
            logger.error(f"Failed to load active file from persistence: {e}")
        return None

    def _save_persisted_active_file(self, file_name: str) -> None:
        """Save the active file name to persistent JSON file"""
        try:
            path = self._persistence_path
            path.parent.mkdir(parents=True, exist_ok=True)
            with open(path, "w", encoding="utf-8") as f:
                json.dump({"active_file": file_name}, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"Failed to save active file to persistence: {e}")

    def __init__(self):
        self._cache: Optional[pd.DataFrame] = None
        self._cache_mtime: Optional[float] = None
        self._cache_path: Optional[Path] = None
        self._active_file_name: Optional[str] = self._load_persisted_active_file()
        # О каком выборе уже сказали в лог: свойство спрашивают на каждый
        # запрос статуса, повторять одно предупреждение незачем.
        self._warned_about: Optional[str] = None

    def _resolved_active(self) -> Optional[Path]:
        """Выбор из интерфейса → путь: имя достраивается до каталога книги.

        Имя без пути — старый формат записи (``Учет КПЗ 2026.xlsm``), его
        достраивают каталогом книги. Путь с корнем (``/app/excel/…``,
        ``\\\\host\\share\\…``, ``Z:\\…``) отдаётся как есть: приклеивать его к
        каталогу нельзя — из ``/app/excel/…`` так получается чужой путь
        ``\\\\host\\share\\app\\excel\\…``, которого нет. Путь к сетевой шаре
        распознаётся и на Linux, где он не абсолютный: там он тоже чужой.
        """
        if not self._active_file_name:
            return None
        path = Path(self._active_file_name)
        if path.is_absolute() or path.root or share_tail(self._active_file_name):
            return path
        if not settings.excel_path:
            return None
        return settings.excel_path.parent / path

    @property
    def current_path(self) -> Optional[Path]:
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
            return settings.excel_path
        if path_exists(chosen):
            return chosen

        configured = settings.excel_path
        if configured is not None and path_exists(configured):
            if self._warned_about != self._active_file_name:
                self._warned_about = self._active_file_name
                logger.warning(
                    f"[Excel] Выбор {chosen} на этой машине не существует — "
                    f"книга берётся из конфигурации: {configured}"
                )
            return configured
        return chosen

    @property
    def directory(self) -> Optional[Path]:
        """Каталог книги: у сервера — смонтированная сетевая папка.

        Один владелец правила для списка файлов, выбора по пути и подсказки в
        ошибке: сначала каталог активной книги, затем каталог из конфигурации.
        """
        for candidate in (self.current_path, settings.excel_path):
            if candidate and path_exists(candidate.parent):
                return candidate.parent
        return None

    def set_active_file(self, file_path: str) -> None:
        """Set active Excel file path/name and invalidate cache"""
        self._active_file_name = file_path
        self._save_persisted_active_file(file_path)
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
    
    @property
    def cache_mtime(self) -> Optional[float]:
        """Get current cache modification time (for cache invalidation tracking)."""
        return self._cache_mtime

    def invalidate_cache(self) -> None:
        """Force cache invalidation."""
        self._cache = None
        self._cache_mtime = None
        self._cache_path = None
    
    def _is_cache_valid(self, file_path: Path) -> bool:
        """Check if cached data is still valid."""
        if self._cache is None:
            return False
        if self._cache_path != file_path:
            return False
        try:
            current_mtime = file_path.stat().st_mtime
            return self._cache_mtime == current_mtime
        except OSError:
            return False
    
    def get_dataframe(
        self,
        file_path: Optional[Path] = None,
        sheet_name: str = "Подвесы",
        full_dataset: bool = False
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

        # Check cache validity
        if self._is_cache_valid(path):
            logger.info(f"[CACHE HIT] Using cached data: {len(self._cache)} rows")
            df = self._cache.copy()
        else:
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
                df = self._read_dataframe_by_header(path, sheet_name)
                read_time = time.time() - start_time
                logger.info(f"[EXCEL READ] {len(df)} rows in {read_time:.2f}s from {path.name} (calamine)")

                # Remove completely empty rows
                df = df.dropna(how='all')
                
                # Filter: keep rows where date OR number is present
                df = df[(pd.notna(df['date'])) | (pd.notna(df['number']))]
                
                logger.info(f"[EXCEL FILTERED] {len(df)} valid rows after filtering")
                
                self._cache = df
                self._cache_mtime = path.stat().st_mtime
                self._cache_path = path
            except Exception as e:
                logger.error(f"[EXCEL ERROR] Failed to read Excel file: {e}")
                if self._cache is not None:
                    return self._cache.copy()
                return pd.DataFrame()
        
        if full_dataset:
            return df
        
        # Filter to recent data (last 7 days by default)
        if 'date' in df.columns:
            try:
                df['date'] = pd.to_datetime(df['date'], errors='coerce')
                cutoff = datetime.now() - timedelta(days=7)
                df = df[df['date'] >= cutoff]
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
            engine='calamine',
        )
        if header_df.empty:
            logger.warning(f"[EXCEL COLUMNS] Empty header row in {path.name}")
            return pd.DataFrame()

        header_row = header_df.iloc[0]
        resolution = resolve_columns(header_row)

        if not resolution.found_by_name:
            logger.warning(
                f"[EXCEL COLUMNS] No columns matched by header name in {path.name}; "
                "using legacy positional mapping"
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
            engine='calamine',
        )
        df.columns = names
        return df

    def get_products(
        self,
        limit: int = 100,
        days: int = 7,
        filters: Optional[Dict[str, Any]] = None,
        from_end: bool = True,
        loading_only: bool = False
    ) -> List[HangerRow]:
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
        if not from_end and 'date' in df.columns:
            try:
                df['date'] = pd.to_datetime(df['date'], errors='coerce')
                cutoff = datetime.now() - timedelta(days=days)
                df = df[df['date'] >= cutoff]
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
                return pd.isna(v) or str(v).strip() in ('', EMPTY, 'nan', 'NaT')
            
            mask = ~(df.apply(lambda row: _is_empty_val(row.get('profile')) 
                              and _is_empty_val(row.get('material_type'))
                              and _is_empty_val(row.get('time')), axis=1))
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
    
    def _process_dataframe(self, df: pd.DataFrame, loading_only: bool = False) -> List[HangerRow]:
        """
        Process DataFrame and return rows in the declared HangerRow form.
        Handles date/time formatting and lamels parsing.
        
        Args:
            loading_only: If True, only include loading rows (date+material filled, time empty)
        """
        products: List[HangerRow] = []
        
        # Filter by date - last 2 weeks for loading_only mode
        if loading_only and 'date' in df.columns:
            try:
                logger.info(f"[FILTER] Before date filter: {len(df)} rows")
                # Convert date column to datetime
                df['date'] = pd.to_datetime(df['date'], errors='coerce')
                # Filter last 2 weeks
                cutoff = datetime.now() - timedelta(days=14)
                df = df[df['date'] >= cutoff]
                logger.info(f"[FILTER] After date filter (last 2 weeks, cutoff={cutoff.strftime('%Y-%m-%d')}): {len(df)} rows")
            except Exception as e:
                logger.warning(f"[FILTER] Could not filter by date: {e}")
        
        for _, row in df.iterrows():
            date_val = row.get('date')
            material_type = row.get('material_type')
            time_val = row.get('time')
            number_val = row.get('number')
            profile_val = row.get('profile')
            
            # Skip rows whose key fields are all empty
            def _is_empty(v):
                return pd.isna(v) or str(v).strip() in ('', EMPTY, 'nan', 'NaT')
            
            if _is_empty(number_val) and _is_empty(profile_val) and _is_empty(material_type):
                continue
            
            # For loading_only mode: strict filtering
            if loading_only:
                # Date must be filled
                if pd.isna(date_val) or not date_val:
                    continue
                # Material type must be filled
                if pd.isna(material_type) or not material_type or str(material_type).strip() in ('', EMPTY):
                    continue
                # Time must be EMPTY (this indicates a loading row, not unloading)
                if pd.notna(time_val) and str(time_val).strip() not in ('', EMPTY, 'nan', 'NaT'):
                    continue
            
            # Handle lamels (can be "30+30" or number)
            lamels = row.get('lamels_qty')
            if pd.notna(lamels):
                try:
                    lamels_display = int(float(lamels))
                except (ValueError, TypeError):
                    lamels_display = str(lamels)
            else:
                lamels_display = 0
            
            # Format time (remove seconds)
            time_str = EMPTY
            time_val = row.get('time')
            if pd.notna(time_val):
                if hasattr(time_val, 'strftime'):
                    time_str = time_val.strftime('%H:%M')
                else:
                    time_val_str = str(time_val)
                    if ':' in time_val_str:
                        parts = time_val_str.split(':')
                        time_str = f"{parts[0]}:{parts[1]}"
                    else:
                        time_str = time_val_str
            
            # Format date
            date_str = EMPTY
            date_val = row.get('date')
            if pd.notna(date_val):
                try:
                    if hasattr(date_val, 'strftime'):
                        date_str = date_val.strftime('%d.%m.%y')
                    else:
                        date_str = str(date_val)
                except Exception:
                    date_str = str(date_val)
            
            profile_name = row.get('profile', EMPTY)
            if pd.isna(profile_name) or not profile_name:
                profile_name = EMPTY
            
            # Check for defect (брак)
            defect_val = row.get('defect')
            is_defect = False
            if pd.notna(defect_val):
                defect_str = str(defect_val).lower().strip()
                is_defect = 'брак' in defect_str
            
            # Format number (convert float to int to avoid 10.0 format)
            number_val = row.get('number')
            if pd.notna(number_val):
                try:
                    number_display = int(float(number_val))
                except (ValueError, TypeError):
                    number_display = str(number_val)
            else:
                number_display = EMPTY
            
            products.append(HangerRow(
                number=number_display,
                # Лист читается с пропуском трёх строк (две инструкции и
                # заголовки), поэтому первая строка данных имеет индекс 0,
                # а в листе, где нумерация с единицы, идёт под номером 4.
                # Проверено сверкой с листом: индекс + 4 попадает в ту же
                # строку, на единицу меньше — уже соседняя.
                sheet_row=int(row.name) + DATA_ROWS_SKIPPED + 1,
                date=date_str,
                time=time_str,
                client=row.get('client') if pd.notna(row.get('client')) else EMPTY,
                profile=str(profile_name).strip(),
                color=row.get('color') if pd.notna(row.get('color')) else EMPTY,
                lamels_qty=lamels_display,
                kpz_number=row.get('kpz_number') if pd.notna(row.get('kpz_number')) else EMPTY,
                material_type=row.get('material_type') if pd.notna(row.get('material_type')) else EMPTY,
                is_defect=is_defect,
            ))
        
        logger.info(f"[FILTER] Final products after all filters: {len(products)}")
        return products
    
    def update_simulation_mode(self) -> None:
        """Обновляет активный файл и сбрасывает кэш при смене режима симуляции."""
        self._active_file_name = self._load_persisted_active_file()
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
