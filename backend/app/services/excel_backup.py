"""Автобэкап книги учёта КПЗ (тикет 0007).

Сервер раз в два часа снимает копию САМОГО Excel-файла в папку
``<имя книги>_backup``. Это не журнал подвесов: журнал — история проходов,
здесь — снимок книги. Копия нужна, когда книгу испортили или она потерялась,
а открытого дашборда на боевой машине почти никогда нет, поэтому копирование
живёт в фоновой задаче, а не в роуте.

Источник — ``excel_service.current_path``, а не путь из конфигурации:
оператор может сменить книгу через «Ввести путь», и копия обязана следовать
за ней. Ротация выполняется сразу после каждой попытки: лимиты соблюдаются и
после простоя, и после того, как в папку вручную положили файлы.

Политика хранения зафиксирована этим тикетом и потому является константами
модуля, а не настройками: настройка, которую никто не помнит, живёт дольше
своего смысла.
"""

import asyncio
import logging
import os
import re
import shutil
import tempfile
import time
from collections.abc import Callable
from datetime import datetime, timedelta
from enum import StrEnum
from pathlib import Path
from typing import NamedTuple

from app.core.config import settings
from app.services.excel_service import excel_service, path_exists

logger = logging.getLogger(__name__)

# Политика хранения (тикет 0007).
KEEP_2H = 24  # двухчасовых копий
KEEP_2H_HOURS = 48  # столько часов они покрывают
KEEP_DAILY = 7  # по одной копии за каждый из последних 7 дней
KEEP_WEEKLY = 7  # по одной за каждую из последних 7 ISO-недель
# Месячные копии не удаляются никогда — отдельной константы-лимита нет.

# Расписание: цикл просыпается часто, а попытка идёт не чаще интервала.
# Так рестарт и перевод часов не сбивают расписание — с «ровно в 00:00, 02:00»
# после рестарта появлялись бы пропуски.
POLL_SECONDS = 30
# После ошибки (шара отвалилась, книга занята) повтор через 5 минут.
RETRY_SECONDS = 5 * 60
# Перед копированием книга должна «успокоиться»: два stat с паузой.
SETTLE_SECONDS = 1.0
# Занятый файл: 3 попытки с паузой 5 секунд, затем ошибка и повтор через 5 минут.
COPY_ATTEMPTS = 3
COPY_RETRY_DELAY_SECONDS = 5.0
# SMB/CIFS может округлять mtime: сравниваем с допуском.
MTIME_TOLERANCE_SECONDS = 2.0

# Символы, запрещённые в именах Windows: имя папки строится из имени книги.
_FORBIDDEN_NAME_CHARS = '<>:"/\\|?*'
_TMP_PREFIX = ".tmp-"
_SUFFIXES = ("xlsm", "xlsx", "xls")


class BackupStatus(StrEnum):
    """Результат одной попытки — для тестов, логов и расписания."""

    CREATED = "created"
    SKIPPED_UNCHANGED = "skipped_unchanged"
    SKIPPED_MISSING = "skipped_missing"
    FAILED = "failed"


class BackupEntry(NamedTuple):
    """Своя копия в папке: время из имени, суффикс минуты и путь."""

    moment: datetime
    minute_ordinal: int
    path: Path


# Последнее состояние, о котором уже сказали в лог. Ошибка повторяется каждые
# 5 минут, а сообщение о ней — один раз на состояние: иначе лог превращается
# в поток одинаковых строк и настоящая причина в нём теряется.
_last_warn_key: str | None = None


def sanitize_name(name: str) -> str:
    """Имя, безопасное для Windows: запрещённые символы → ``_``.

    Хвостовые точки и пробелы срезаются: Windows молча не создаёт каталог,
    имя которого ими заканчивается.
    """
    cleaned = "".join("_" if char in _FORBIDDEN_NAME_CHARS or ord(char) < 32 else char for char in name)
    cleaned = cleaned.rstrip(" .")
    return cleaned or "_"


def backup_dir_for(book_path: Path) -> Path:
    """Папка копий для книги: ``<корень>/<имя книги без расширения>_backup``.

    Корень — ``EXCEL_BACKUP_ROOT``; пусто — каталог самой книги. Dev-хост и
    прод смотрят на одну шару, поэтому у dev корень свой (backend/.env), и
    копии двух сред не смешиваются.
    """
    base = Path(settings.EXCEL_BACKUP_ROOT) if settings.EXCEL_BACKUP_ROOT else book_path.parent
    return base / f"{sanitize_name(book_path.stem)}_backup"


def is_unchanged(book_path: Path, latest_backup: Path | None) -> bool:
    """Источник не менялся с самой новой копии: размер и ``mtime`` совпали.

    ``shutil.copy2`` сохраняет ``mtime``, а ``_copy_with_retries``
    восстанавливает его после ``os.replace``: CIFS теряет метку при rename.
    Сравнение с копией дешевле хеширования книги каждые два часа и достаточно
    для файла, который сохраняет человек. Допуск 2 секунды — SMB/CIFS может
    округлять метку.
    """
    if latest_backup is None:
        return False
    try:
        source = book_path.stat()
        backup = latest_backup.stat()
    except OSError:
        return False
    return source.st_size == backup.st_size and abs(source.st_mtime - backup.st_mtime) <= MTIME_TOLERANCE_SECONDS


def _own_pattern(book_stem: str, suffix: str | None) -> re.Pattern[str]:
    """Свои файлы папки: время, имя книги и расширение.

    ``-01``, ``-02`` стоят после имени книги перед расширением — так их
    строит ``_unique_target`` для копий, попавших в ту же минуту. Чужие файлы,
    ``.tmp`` и копии других книг под шаблон не попадают.
    """
    extension = re.escape(suffix) if suffix else rf"\.(?:{'|'.join(_SUFFIXES)})"
    return re.compile(rf"^(\d{{4}}-\d{{2}}-\d{{2}}_\d{{2}}-\d{{2}})_{re.escape(book_stem)}(?:-(\d{{2}}))?{extension}$")


def _own_entries(backup_dir: Path, book_stem: str, suffix: str | None) -> list[BackupEntry]:
    """Свои копии папки, новые сверху."""
    if not backup_dir.is_dir():
        return []
    pattern = _own_pattern(book_stem, suffix)
    entries: list[BackupEntry] = []
    try:
        children = list(backup_dir.iterdir())
    except OSError:
        return []
    for child in children:
        if not child.is_file():
            continue
        match = pattern.match(child.name)
        if match is None:
            continue
        try:
            moment = datetime.strptime(match.group(1), "%Y-%m-%d_%H-%M")
        except ValueError:
            continue
        minute_ordinal = int(match.group(2)) if match.group(2) else 0
        entries.append(BackupEntry(moment, minute_ordinal, child))
    entries.sort(key=lambda entry: (entry.moment, entry.minute_ordinal), reverse=True)
    return entries


def _dir_book_stem(backup_dir: Path) -> str:
    """Имя книги из имени папки копий (``<имя>_backup``)."""
    name = backup_dir.name
    return name[: -len("_backup")] if name.endswith("_backup") else name


def _first_per(
    entries: list[BackupEntry],
    key: Callable[[datetime], object],
    allowed: Callable[[datetime], bool] | None = None,
) -> set[Path]:
    """Первая (самая новая) запись на каждое значение ключа.

    ``entries`` уже отсортированы новыми сверху. ``allowed`` отсекает записи,
    которые уровень не рассматривает (например, старее 7 дней).
    """
    kept: set[Path] = set()
    seen: set[object] = set()
    for entry in entries:
        if allowed is not None and not allowed(entry.moment):
            continue
        value = key(entry.moment)
        if value in seen:
            continue
        seen.add(value)
        kept.add(entry.path)
    return kept


def _keep_paths(entries: list[BackupEntry], now: datetime) -> set[Path]:
    """Какие копии оставить по ступенчатой политике.

    Уровни пересекаются: копия за последние двое суток одновременно дневная,
    а копия текущей недели — недельная. Это одна и та же копия, не дубль.
    """
    keep: set[Path] = set()

    # Двухчасовой уровень: 24 новейших не старше 48 часов.
    recent_cutoff = now - timedelta(hours=KEEP_2H_HOURS)
    recent: list[BackupEntry] = []
    for entry in entries:
        if entry.moment < recent_cutoff:
            continue
        if len(recent) >= KEEP_2H:
            break
        recent.append(entry)
    keep.update(entry.path for entry in recent)

    # Дневной уровень: по одной (самой новой) за каждый из последних 7 дней.
    oldest_day = now.date() - timedelta(days=KEEP_DAILY - 1)
    keep |= _first_per(
        entries,
        key=lambda moment: moment.date(),
        allowed=lambda moment: moment.date() >= oldest_day,
    )

    # Недельный уровень: по одной за каждую из последних 7 ISO-недель.
    week_start = now.date() - timedelta(days=now.weekday())
    weeks = {tuple((week_start - timedelta(weeks=index)).isocalendar()[:2]) for index in range(KEEP_WEEKLY)}
    keep |= _first_per(
        entries,
        key=lambda moment: tuple(moment.isocalendar()[:2]),
        allowed=lambda moment: tuple(moment.isocalendar()[:2]) in weeks,
    )

    # Месячный уровень: по одной за каждый месяц, бессрочно.
    keep |= _first_per(entries, key=lambda moment: (moment.year, moment.month))

    return keep


def prune(backup_dir: Path, now: datetime | None = None) -> list[Path]:
    """Ротация: удалить копии, не попавшие в политику хранения.

    Возвращает удалённые файлы. Каждое удаление — строкой в лог: файл,
    исчезнувший без следа, неотличим от файла, которого не было.
    """
    now = now or datetime.now()
    # Имя книги — из имени папки (<имя>_backup). Расширение не уточняем:
    # приложение поддерживает .xlsm/.xlsx/.xls, и шаблон допускает все три.
    entries = _own_entries(backup_dir, _dir_book_stem(backup_dir), suffix=None)
    if not entries:
        return []

    keep = _keep_paths(entries, now)
    deleted: list[Path] = []
    for _moment, _minute_ordinal, path in entries:
        if path in keep:
            continue
        try:
            path.unlink()
        except OSError as error:
            logger.warning(f"[ExcelBackup] Не удалось удалить старую копию {path.name}: {error}")
            continue
        deleted.append(path)
        logger.info(f"[ExcelBackup] Удалена старая копия: {path.name}")
    return deleted


def _warn_once(key: str, message: str) -> None:
    """Записать ошибку в лог один раз на состояние."""
    global _last_warn_key
    if _last_warn_key == key:
        return
    _last_warn_key = key
    logger.warning(message)


def _reset_warn_state() -> None:
    global _last_warn_key
    _last_warn_key = None


# Предупреждение о неудачном ``utime`` — свойство монтирования, а не
# состояние копии: успешная копия не должна сбрасывать его и повторять
# строку каждые 2 часа. Ключ — папка копий.
_utime_warned: set[str] = set()


def _warn_utime_once(backup_dir: Path, message: str) -> None:
    key = str(backup_dir)
    if key in _utime_warned:
        return
    _utime_warned.add(key)
    logger.warning(message)


def _is_settled(book_path: Path) -> bool | None:
    """Книга не дописывается прямо сейчас: два ``stat`` с паузой совпали.

    ``None`` — ``stat`` не удался (книга недоступна, нет прав): это не то же
    самое, что «файл меняется», и в лог должно попасть своей причиной.
    """
    try:
        first = book_path.stat()
        if SETTLE_SECONDS:
            time.sleep(SETTLE_SECONDS)
        second = book_path.stat()
    except OSError:
        return None
    return first.st_size == second.st_size and first.st_mtime_ns == second.st_mtime_ns


def _unique_target(backup_dir: Path, stem: str, suffix: str, moment: datetime) -> Path:
    """Свободное имя копии: существующее имя не выбирается.

    Проверка стоит непосредственно перед ``os.replace``, поэтому окно гонки с
    другим писателем мало; второй сервер на ту же папку не запускается.
    """
    stamp = moment.strftime("%Y-%m-%d_%H-%M")
    candidate = backup_dir / f"{stamp}_{stem}{suffix}"
    ordinal = 1
    while candidate.exists():
        candidate = backup_dir / f"{stamp}_{stem}-{ordinal:02d}{suffix}"
        ordinal += 1
    return candidate


def _copy_with_retries(
    book_path: Path,
    backup_dir: Path,
    stem: str,
    suffix: str,
    moment: datetime,
) -> Path:
    """Создать папку и снять копию: до трёх попыток с паузой.

    ``mkdir`` — в той же попытке, что и копирование: на read-only шаре падает
    именно она, и повторять её отдельно от копии нечего. Копия идёт через
    скрытый ``.tmp`` и ``os.replace``, поэтому недописанный файл не выглядит
    как настоящая резервная копия; временный файл удаляется при любой ошибке.
    """
    last_error: OSError | None = None
    for attempt in range(1, COPY_ATTEMPTS + 1):
        tmp: Path | None = None
        try:
            backup_dir.mkdir(parents=True, exist_ok=True)
            # Временный файл создаётся заранее и получает случайное имя:
            # итоговое имя выбирается непосредственно перед replace, поэтому
            # окно «кто-то успел создать такое же имя» минимально.
            fd, tmp_name = tempfile.mkstemp(prefix=_TMP_PREFIX, dir=backup_dir)
            tmp = Path(tmp_name)
            os.close(fd)
            shutil.copy2(book_path, tmp)
            # CIFS-том в контейнере теряет mtime при rename: os.replace
            # ставит файлу время переименования, и is_unchanged перестаёт
            # видеть «книга не менялась». Метку, которую copy2 взял у
            # книги, переносим на итоговый файл явно.
            copied = tmp.stat()
            target = _unique_target(backup_dir, stem, suffix, moment)
            os.replace(tmp, target)
            try:
                os.utime(target, ns=(copied.st_atime_ns, copied.st_mtime_ns))
                _utime_warned.discard(str(backup_dir))
            except OSError as error:
                _warn_utime_once(
                    backup_dir,
                    f"[ExcelBackup] Не удалось сохранить mtime копии {target.name}: {error}",
                )
            return target
        except OSError as error:
            last_error = error
            if attempt < COPY_ATTEMPTS and COPY_RETRY_DELAY_SECONDS:
                time.sleep(COPY_RETRY_DELAY_SECONDS)
        finally:
            if tmp is not None:
                tmp.unlink(missing_ok=True)
    if last_error is not None:
        raise last_error
    raise RuntimeError("копирование не выполнило ни одной попытки")


def backup_once(now: datetime | None = None) -> BackupStatus:
    """Одна попытка снять копию активной книги.

    Ошибка не роняет сервер: результат возвращается вызывающему, а расписание
    само решает, когда пробовать снова.
    """
    now = now or datetime.now()
    book_path = excel_service.current_path
    if book_path is None:
        _warn_once("missing:none", "[ExcelBackup] Активная книга не задана — копия отложена")
        return BackupStatus.SKIPPED_MISSING

    backup_dir = backup_dir_for(book_path)
    suffix = book_path.suffix
    stem = sanitize_name(book_path.stem)

    # Ротация — после КАЖДОЙ попытки, в том числе неудачной и при пропавшей
    # книге: лимиты должны соблюдаться и тогда, когда копия не создалась.
    # Папки нет — prune ничего не делает и ничего не создаёт.
    try:
        if not path_exists(book_path):
            _warn_once(f"missing:{book_path}", f"[ExcelBackup] Книга недоступна: {book_path} — копия отложена")
            return BackupStatus.SKIPPED_MISSING

        entries = _own_entries(backup_dir, stem, suffix)
        latest = entries[0].path if entries else None

        if is_unchanged(book_path, latest):
            _reset_warn_state()
            logger.info(f"[ExcelBackup] Книга не менялась с копии {latest.name} — новая не нужна")
            return BackupStatus.SKIPPED_UNCHANGED

        settled = _is_settled(book_path)
        if settled is None:
            _warn_once(
                f"unavailable:{book_path}",
                f"[ExcelBackup] Книга недоступна или нет прав на чтение: {book_path} — повтор через 5 минут",
            )
            return BackupStatus.FAILED
        if not settled:
            _warn_once(
                f"unstable:{book_path}",
                f"[ExcelBackup] Книга ещё записывается: {book_path} — попытка отложена",
            )
            return BackupStatus.FAILED

        try:
            target = _copy_with_retries(book_path, backup_dir, stem, suffix, now)
        except OSError as error:
            _warn_once(
                f"copy:{book_path}:{error}",
                f"[ExcelBackup] Не удалось скопировать книгу {book_path}: {error} — повтор через 5 минут",
            )
            return BackupStatus.FAILED

        _reset_warn_state()
        logger.info(f"[ExcelBackup] Создана копия книги: {target}")
        return BackupStatus.CREATED
    finally:
        prune(backup_dir, now=now)


class ExcelBackup:
    """Фоновая задача автобэкапа: цикл, старт и повтор."""

    async def run_forever(self) -> None:
        """Просыпаться каждые ``POLL_SECONDS`` и делать попытку по расписанию.

        Сразу при старте — немедленная проверка: если книга менялась, пока
        сервер стоял, копия создаётся без ожидания интервала. После успеха и
        пропуска «не менялась» следующий запуск через интервал, после ошибки —
        через 5 минут.
        """
        interval = float(settings.EXCEL_BACKUP_INTERVAL_MINUTES) * 60
        loop = asyncio.get_running_loop()
        next_run = loop.time()
        while True:
            try:
                if loop.time() >= next_run:
                    status = await asyncio.to_thread(backup_once)
                    delay = (
                        interval if status in (BackupStatus.CREATED, BackupStatus.SKIPPED_UNCHANGED) else RETRY_SECONDS
                    )
                    next_run = loop.time() + delay
            except asyncio.CancelledError:
                raise
            except Exception as error:
                logger.error(f"[ExcelBackup] Задача автобэкапа упала: {error}", exc_info=True)
                next_run = loop.time() + RETRY_SECONDS
            await asyncio.sleep(POLL_SECONDS)


# Синглтон для main.py и тестов.
excel_backup = ExcelBackup()
