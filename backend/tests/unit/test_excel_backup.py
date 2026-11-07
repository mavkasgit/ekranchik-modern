"""Автобэкап книги учёта (тикет 0007).

Копия снимается с АКТИВНОЙ книги (``excel_service.current_path``), а не с
пути из конфигурации: оператор меняет книгу через «Ввести путь», и бэкап
обязан следовать за ней. Все тесты — на ``tmp_path`` и фейковом ``.xlsm``:
ни реального Excel, ни сетевой шары.
"""

import asyncio
import os
import time
from contextlib import suppress
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from app.services import excel_backup
from app.services.excel_backup import (
    BackupStatus,
    backup_dir_for,
    backup_once,
    prune,
)

BOOK_NAME = "Учет КПЗ 2026.xlsm"
NOW = datetime(2026, 11, 7, 14, 0)


def make_backup(folder: Path, moment: datetime, book_name: str = BOOK_NAME, content: bytes = b"x") -> Path:
    """Создать файл, похожий на резервную копию, с временем в имени."""
    folder.mkdir(parents=True, exist_ok=True)
    stamp = moment.strftime("%Y-%m-%d_%H-%M")
    path = folder / f"{stamp}_{book_name}"
    path.write_bytes(content)
    return path


def own_files(folder: Path) -> list[str]:
    return sorted(p.name for p in folder.iterdir() if p.is_file())


@pytest.fixture
def book(tmp_path, monkeypatch):
    """Активная книга в «шаре» и настройки, безопасные для тестов."""
    from app.core.config import settings
    from app.services.excel_service import excel_service

    share = tmp_path / "share"
    share.mkdir()
    path = share / BOOK_NAME
    path.write_bytes(b"book-v1")

    monkeypatch.setattr(settings, "EXCEL_BACKUP_ROOT", None)
    # Боевая шара на dev-машине реально существует: тест не имеет права
    # читать её и тем более копировать. Конфигурационный путь уводим в
    # заведомо отсутствующий файл.
    monkeypatch.setattr(settings, "SIMULATION_ENABLED", False)
    monkeypatch.setattr(settings, "EXCEL_REAL_FILE_PATH", str(tmp_path / "configured-missing" / BOOK_NAME))
    monkeypatch.setattr(excel_service, "_active_file_name", str(path))
    # Паузы боевого режима в тестах не нужны: они только замедляют прогон.
    monkeypatch.setattr(excel_backup, "SETTLE_SECONDS", 0)
    monkeypatch.setattr(excel_backup, "COPY_RETRY_DELAY_SECONDS", 0)
    return path


# --- backup_once: копия, содержимое, mtime ---------------------------------


def test_creates_backup_folder_and_copy(book):
    folder = book.parent / "Учет КПЗ 2026_backup"

    result = backup_once(now=NOW)

    assert result == BackupStatus.CREATED
    assert result == "created"
    assert own_files(folder) == ["2026-11-07_14-00_Учет КПЗ 2026.xlsm"]
    copy = folder / "2026-11-07_14-00_Учет КПЗ 2026.xlsm"
    assert copy.read_bytes() == book.read_bytes()
    # copy2 сохраняет метку источника: по ней потом решается «не менялась».
    assert copy.stat().st_mtime == pytest.approx(book.stat().st_mtime, abs=0.001)


def test_second_run_without_changes_skips(book):
    backup_once(now=NOW)
    folder = book.parent / "Учет КПЗ 2026_backup"

    result = backup_once(now=NOW + timedelta(hours=2))

    assert result == BackupStatus.SKIPPED_UNCHANGED
    assert len(own_files(folder)) == 1


def test_changed_book_creates_second_copy(book):
    backup_once(now=NOW)
    book.write_bytes(b"book-v2-longer")
    stamp = (NOW + timedelta(seconds=10)).timestamp()
    os.utime(book, (stamp, stamp))

    result = backup_once(now=NOW + timedelta(hours=2))

    assert result == BackupStatus.CREATED
    folder = book.parent / "Учет КПЗ 2026_backup"
    assert own_files(folder) == [
        "2026-11-07_14-00_Учет КПЗ 2026.xlsm",
        "2026-11-07_16-00_Учет КПЗ 2026.xlsm",
    ]


def test_missing_book_creates_no_folder(tmp_path, monkeypatch):
    from app.core.config import settings
    from app.services.excel_service import excel_service

    root = tmp_path / "backups"
    monkeypatch.setattr(settings, "EXCEL_BACKUP_ROOT", str(root))
    monkeypatch.setattr(settings, "EXCEL_REAL_FILE_PATH", str(tmp_path / "configured-missing" / BOOK_NAME))
    monkeypatch.setattr(excel_service, "_active_file_name", str(tmp_path / "share" / BOOK_NAME))

    result = backup_once(now=NOW)

    assert result == BackupStatus.SKIPPED_MISSING
    assert not (root / "Учет КПЗ 2026_backup").exists()


def test_configured_root_keeps_backups_away_from_book(book, tmp_path, monkeypatch):
    from app.core.config import settings

    root = tmp_path / "backups"
    monkeypatch.setattr(settings, "EXCEL_BACKUP_ROOT", str(root))

    result = backup_once(now=NOW)

    assert result == BackupStatus.CREATED
    assert own_files(root / "Учет КПЗ 2026_backup") == ["2026-11-07_14-00_Учет КПЗ 2026.xlsm"]
    assert not (book.parent / "Учет КПЗ 2026_backup").exists()


def test_unsafe_book_name_gets_safe_folder(tmp_path):
    assert backup_dir_for(tmp_path / 'Учет:КПЗ?*"|<>book.xlsm').name == "Учет_КПЗ______book_backup"
    assert backup_dir_for(tmp_path / "book. .xlsm").name == "book_backup"


def test_copy_error_leaves_no_tmp_and_no_backup(book, monkeypatch):
    def broken_copy(*args, **kwargs):
        raise PermissionError("file is locked")

    monkeypatch.setattr(excel_backup.shutil, "copy2", broken_copy)

    result = backup_once(now=NOW)

    assert result == BackupStatus.FAILED
    folder = book.parent / "Учет КПЗ 2026_backup"
    assert folder.exists()
    assert list(folder.iterdir()) == []


def test_mkdir_is_retried_three_times(book, monkeypatch):
    """На read-only шаре падает именно mkdir — он входит в те же 3 попытки."""
    calls: list[Path] = []

    def failing_mkdir(self, *args, **kwargs):
        calls.append(self)
        raise PermissionError("read-only share")

    monkeypatch.setattr(Path, "mkdir", failing_mkdir)

    result = backup_once(now=NOW)

    assert result == BackupStatus.FAILED
    assert len(calls) == excel_backup.COPY_ATTEMPTS


def test_same_minute_gets_suffix_and_keeps_existing(book):
    folder = book.parent / "Учет КПЗ 2026_backup"
    existing = make_backup(folder, NOW, content=b"old")

    result = backup_once(now=NOW)

    assert result == BackupStatus.CREATED
    assert existing.read_bytes() == b"old"
    assert own_files(folder) == [
        "2026-11-07_14-00_Учет КПЗ 2026-01.xlsm",
        "2026-11-07_14-00_Учет КПЗ 2026.xlsm",
    ]
    assert (folder / "2026-11-07_14-00_Учет КПЗ 2026-01.xlsm").read_bytes() == book.read_bytes()


def test_prune_sees_minute_suffix_as_own(tmp_path):
    """`-01` стоит после имени книги — ротация обязана видеть его своим."""
    folder = tmp_path / "Учет КПЗ 2026_backup"
    folder.mkdir()
    old = NOW - timedelta(days=400)
    stamp = old.strftime("%Y-%m-%d_%H-%M")
    base = folder / f"{stamp}_{BOOK_NAME}"
    suffixed = folder / f"{stamp}_Учет КПЗ 2026-01.xlsm"
    base.write_bytes(b"base")
    suffixed.write_bytes(b"suffixed")
    # Месячный представитель: держит месяц, значит оба старых файла лишние.
    keeper = make_backup(folder, old + timedelta(days=1))

    deleted = prune(folder, now=NOW)

    assert sorted(p.name for p in deleted) == sorted([base.name, suffixed.name])
    assert not base.exists()
    assert not suffixed.exists()
    assert keeper.exists()


def test_rotation_runs_even_when_copy_fails(book, monkeypatch):
    """Неудачная попытка не отменяет ротацию: лимиты соблюдаются всегда."""
    folder = book.parent / "Учет КПЗ 2026_backup"
    stale = make_backup(folder, NOW - timedelta(days=400))
    keeper = make_backup(folder, NOW - timedelta(days=399))

    def broken_copy(*args, **kwargs):
        raise PermissionError("file is locked")

    monkeypatch.setattr(excel_backup.shutil, "copy2", broken_copy)

    result = backup_once(now=NOW)

    assert result == BackupStatus.FAILED
    assert not stale.exists()
    assert keeper.exists()


def test_rotation_runs_when_book_is_missing(book):
    """Книга пропала, но папка копий известна — ротация всё равно идёт."""
    folder = book.parent / "Учет КПЗ 2026_backup"
    stale = make_backup(folder, NOW - timedelta(days=400))
    keeper = make_backup(folder, NOW - timedelta(days=399))
    book.unlink()

    result = backup_once(now=NOW)

    assert result == BackupStatus.SKIPPED_MISSING
    assert not stale.exists()
    assert keeper.exists()


# --- prune: политика хранения ----------------------------------------------


def test_two_hour_level_keeps_24_newest_within_48_hours(tmp_path):
    folder = tmp_path / "Учет КПЗ 2026_backup"
    moments = [NOW - timedelta(hours=2 * i) for i in range(30)]
    for moment in moments:
        make_backup(folder, moment)

    deleted = prune(folder, now=NOW)

    names = own_files(folder)
    expected = sorted(f"{(NOW - timedelta(hours=2 * i)).strftime('%Y-%m-%d_%H-%M')}_{BOOK_NAME}" for i in range(24))
    assert names == expected
    assert len(deleted) == 6
    assert sorted(p.name for p in deleted) == sorted(
        f"{(NOW - timedelta(hours=2 * i)).strftime('%Y-%m-%d_%H-%M')}_{BOOK_NAME}" for i in range(24, 30)
    )


def test_daily_level_keeps_newest_of_each_of_last_7_days(tmp_path):
    folder = tmp_path / "Учет КПЗ 2026_backup"
    for days_ago in range(10):
        day = (NOW - timedelta(days=days_ago)).date()
        for hour in (8, 12, 16):
            make_backup(folder, datetime(day.year, day.month, day.day, hour, 0))

    prune(folder, now=NOW)

    names = own_files(folder)
    for days_ago in range(3, 7):
        day = (NOW - timedelta(days=days_ago)).date()
        prefix = day.strftime("%Y-%m-%d")
        day_files = [name for name in names if name.startswith(prefix)]
        assert day_files == [f"{prefix}_16-00_{BOOK_NAME}"]

    # Дни старше недели остаются только представителями недели/месяца.
    assert not any(name.startswith((NOW - timedelta(days=8)).strftime("%Y-%m-%d")) for name in names)
    assert not any(name.startswith((NOW - timedelta(days=9)).strftime("%Y-%m-%d")) for name in names)
    assert [name for name in names if name.startswith((NOW - timedelta(days=7)).strftime("%Y-%m-%d"))] == [
        f"{(NOW - timedelta(days=7)).strftime('%Y-%m-%d')}_16-00_{BOOK_NAME}"
    ]


def test_weekly_level_keeps_newest_of_each_of_last_7_iso_weeks(tmp_path):
    folder = tmp_path / "Учет КПЗ 2026_backup"
    monday = NOW - timedelta(days=NOW.weekday())
    moments: list[datetime] = []
    for weeks_ago in range(10):
        week_monday = monday - timedelta(weeks=weeks_ago)
        for offset in (0, 4):
            moment = datetime.combine((week_monday + timedelta(days=offset)).date(), datetime.min.time()).replace(
                hour=12
            )
            moments.append(moment)
            make_backup(folder, moment)

    prune(folder, now=NOW)

    remaining = {p.name for p in folder.iterdir()}

    # Последние 7 ISO-недель: самая новая копия недели на месте.
    newest: dict[tuple[int, int], datetime] = {}
    for moment in moments:
        key = tuple(moment.isocalendar()[:2])
        newest[key] = max(newest.get(key, moment), moment)
    week_start = NOW.date() - timedelta(days=NOW.weekday())
    for weeks_ago in range(7):
        day = week_start - timedelta(weeks=weeks_ago)
        key = tuple(day.isocalendar()[:2])
        expected = f"{newest[key].strftime('%Y-%m-%d_%H-%M')}_{BOOK_NAME}"
        assert expected in remaining

    # Недели старше 7-й: остаются только новейшие копии своего месяца.
    oldest_month: dict[tuple[int, int], datetime] = {}
    for moment in moments:
        key = (moment.year, moment.month)
        oldest_month[key] = max(oldest_month.get(key, moment), moment)
    for weeks_ago in range(7, 10):
        day = week_start - timedelta(weeks=weeks_ago)
        key = tuple(day.isocalendar()[:2])
        for moment in moments:
            if tuple(moment.isocalendar()[:2]) != key:
                continue
            name = f"{moment.strftime('%Y-%m-%d_%H-%M')}_{BOOK_NAME}"
            if name in remaining:
                month_key = (moment.year, moment.month)
                assert moment == oldest_month[month_key]


def test_monthly_level_keeps_one_per_month_forever(tmp_path):
    folder = tmp_path / "Учет КПЗ 2026_backup"
    months: list[datetime] = []
    year, month = 2025, 10
    for _ in range(14):
        moment = datetime(year, month, 1, 12, 0)
        months.append(moment)
        make_backup(folder, moment)
        month += 1
        if month == 13:
            year, month = year + 1, 1

    prune(folder, now=NOW)

    names = own_files(folder)
    assert names == sorted(f"{m.strftime('%Y-%m-%d_%H-%M')}_{BOOK_NAME}" for m in months)


def test_prune_keeps_foreign_files(tmp_path):
    folder = tmp_path / "Учет КПЗ 2026_backup"
    stale = make_backup(folder, NOW - timedelta(days=400))
    # В том же месяце есть более новая копия: месячный уровень держит её,
    # а не этот файл, и stale обязан исчезнуть.
    make_backup(folder, NOW - timedelta(days=399))
    foreign = [
        folder / "notes.txt",
        folder / "2026-11-01_10-00_Другая книга.xlsm",
        folder / "2026-09-01_10-00_Учет КПЗ 2026.xlsm.tmp",
        folder / ".tmp-2026-09-01_10-00_Учет КПЗ 2026.xlsm",
    ]
    for path in foreign:
        path.write_bytes(b"foreign")

    deleted = prune(folder, now=NOW)

    assert deleted == [stale]
    for path in foreign:
        assert path.exists()
    assert not stale.exists()


# --- run_forever -----------------------------------------------------------


async def test_run_forever_first_tick_immediately_and_not_faster_than_interval(monkeypatch):
    calls: list[float] = []

    def fake_backup(now=None):
        # backup_once исполняется в потоке (asyncio.to_thread): монотонные
        # часы процесса общие, а loop.time() в потоке недоступен.
        calls.append(time.monotonic())
        return BackupStatus.CREATED

    monkeypatch.setattr(excel_backup, "backup_once", fake_backup)
    monkeypatch.setattr(excel_backup, "POLL_SECONDS", 0.01)
    started = time.monotonic()

    task = asyncio.create_task(excel_backup.excel_backup.run_forever(interval_seconds=0.06))
    await asyncio.sleep(0.2)
    task.cancel()
    with suppress(asyncio.CancelledError):
        await task

    assert len(calls) >= 2
    assert calls[0] - started < 0.15  # первый тик — сразу при старте
    gaps = [later - earlier for earlier, later in zip(calls, calls[1:], strict=False)]
    assert all(gap >= 0.05 for gap in gaps)
