"""Запись проходов в журнал без участия интерфейса (issue #34).

Контракт под тестом (app.services.journal_writer, класс JournalWriter):
- проход попадает в журнал сам, без HTTP-запроса: журнал не должен
  зависеть от того, открыт ли дашборд;
- один и тот же проход в журнал попадает один раз, сколько бы раз его ни
  увидели (фоновая задача опрашивает монитор, а не событие);
- в запись идёт весь проход и вердикт сопоставления — из них собираются
  и строка сопоставления в лог, и колонки таблицы журнала.
"""
import asyncio
import json
from pathlib import Path

import pytest

from app.services.hanger_row import HangerRow
from app.services.hanger_journal import JournalStore
from app.services.journal_writer import JournalWriter, record_from_match
from app.services.matching import CODE_NO_ROW, CycleMatch, TRUSTED_FIRST_SEEN


def _row(number=5, date="28.09.2026", time="18:31", profile="10104") -> HangerRow:
    return HangerRow(
        number=str(number), date=date, time=time, profile=profile,
        client="РП", color="серебро", lamels_qty=86, kpz_number="151",
        material_type="Пороги", is_defect=False,
    )


def _cycle(hanger=5, cycle_id=42, exit_at="2026-09-29T20:16:03", type_="unload"):
    return {
        "type": type_,
        "reason": None,
        "cycle_id": cycle_id,
        "hanger": hanger,
        "first_seen_at": "2026-09-29T17:04:00",
        "first_seen_source": TRUSTED_FIRST_SEEN,
        "entry_bath": 3,
        "exit_at": exit_at,
        "total_time_sec": 11523.0,
        "baths_visited": ["3", "4", "34"],
        "path": [{"bath": "3", "in": "2026-09-29T17:04:00", "out": "2026-09-29T18:10:00"}],
        "date": "29.09.2026",
        "time": "20:16:03",
    }


def _match(cycle=None, row=_row(), code="", delta=-1800.0, note="", rows_after_exit=0):
    return CycleMatch(
        cycle=cycle if cycle is not None else _cycle(),
        row=row,
        code=code,
        entry_delta_sec=delta,
        suspect_reason=note,
        rows_after_exit=rows_after_exit,
    )


@pytest.fixture
def writer(tmp_path: Path) -> JournalWriter:
    return JournalWriter(
        JournalStore(tmp_path / "journal"), rows_provider=lambda: {"5": [_row()]}
    )


def test_pass_record_carries_path_and_verdict():
    """Запись журнала — это проход целиком плюс вердикт сопоставления."""
    record = record_from_match(_match())

    assert record["cycle_id"] == 42
    assert record["hanger"] == 5
    assert record["exit_at"] == "2026-09-29T20:16:03"
    assert record["total_time_sec"] == 11523.0
    assert [step["bath"] for step in record["path"]] == ["3"]
    assert record["entry_delta_sec"] == -1800.0
    assert record["row_date"] == "28.09.2026"
    assert record["row_time"] == "18:31"
    assert record["profile"] == "10104"
    assert record["kpz_number"] == "151"



def test_record_keeps_line_and_book_times_side_by_side():
    """В записи лежат оба времени входа и оба выхода — рядом, а не вперемешку.

    Оператор сверяет проход по линии с записью оператора, и для этого нужны
    четыре момента в одной строке: вход по линии (первый замер), выход по
    линии (выгрузка), вход по книге (фактическое время загрузки в линию)
    и выход по книге. Последнего в книге нет — колонки выгрузки в ней не
    существует, — поэтому он остаётся пустым, а не выдумывается.
    """
    record = record_from_match(_match())

    assert record["line_entry_at"] == "2026-09-29T17:04:00", "вход по линии"
    assert record["line_exit_at"] == "2026-09-29T20:16:03", "выход по линии"
    assert record["book_entry_at"] == "2026-09-28T18:31:00", "вход по книге"
    assert record["book_exit_at"] is None, "выхода в книге нет — выдумывать нельзя"


def test_book_entry_time_keeps_the_day_the_row_names():
    """Дату входа по книге берём у строки, а не у прохода.

    Строка книги — это когда подвес ЗАГРУЗИЛИ, то есть до того, как монитор
    его увидел: это всегда предыдущие сутки ночной смены. Если взять дату
    прохода, вход по книге и вход по линии совпали бы в записях, где
    проход длится через полночь, а разойтись — там, где разница важна.
    """
    row = _row(date="28.09.2026", time="23:55")
    record = record_from_match(_match(row=row))

    assert record["book_entry_at"].startswith("2026-09-28T23:55")
    assert record["line_entry_at"].startswith("2026-09-29T")


def test_record_without_book_row_has_no_book_times():
    """Проходу без строки книги неоткуда взять время загрузки в линию."""
    record = record_from_match(_match(row=None, code=CODE_NO_ROW, delta=None))

    assert record["line_entry_at"] is not None, "линия знает и вход, и выход"
    assert record["book_entry_at"] is None
    assert record["book_exit_at"] is None

def test_pass_without_book_row_records_the_code_only():
    """Прохода без строки книги в книге нет: пустые поля, а не выдуманные."""
    record = record_from_match(_match(row=None, code=CODE_NO_ROW, delta=None))

    assert record["code"] == CODE_NO_ROW
    assert record["row_date"] is None
    assert record["entry_delta_sec"] is None
    assert record["profile"] is None


def test_writer_persists_a_pass_without_any_http_request(writer, monkeypatch):
    """Проход попадает в журнал сам, без запроса от страницы.

    Раньше запись шла из роута ``/opcua-unload-matched``, то есть только
    пока открыт дашборд: с закрытым браузером журнал был пуст.
    """

    def explode(*args, **kwargs):
        raise AssertionError("писатель журнала не должен ходить в HTTP")

    monkeypatch.setattr("httpx.AsyncClient.request", explode)

    written = asyncio.run(writer.flush(line_monitor=_monitor_with([_cycle()])))

    assert written == 1
    page = writer.store.query(limit=10)
    assert [r["hanger"] for r in page.items] == [5]
    assert page.items[0]["profile"] == "10104"


def test_writer_records_each_pass_once(writer):
    """Один проход в журнал попадает один раз: опрос монитора повторяется."""
    monitor = _monitor_with([_cycle()])

    assert asyncio.run(writer.flush(line_monitor=monitor)) == 1
    assert asyncio.run(writer.flush(line_monitor=monitor)) == 0
    assert writer.store.query(limit=10).total == 1


def test_writer_takes_the_pass_it_has_not_seen_yet(writer):
    """Новый проход дописывается, старые не дублируются."""
    monitor = _monitor_with([_cycle(cycle_id=1, hanger=5)])

    assert asyncio.run(writer.flush(line_monitor=monitor)) == 1

    monitor._events.append(
        _cycle(cycle_id=2, hanger=5, exit_at="2026-09-29T21:16:03")
    )
    assert asyncio.run(writer.flush(line_monitor=monitor)) == 1

    page = writer.store.query(limit=10)
    assert page.total == 2
    assert [r["cycle_id"] for r in page.items] == [2, 1]


def test_writer_survives_a_restart_and_keeps_writing(writer, tmp_path):
    """После перезапуска сервера журнал дополняется, а не начинается заново.

    Перезапуск поднимает нового писателя с пустой памятью: без чтения
    журнала при старте проходы последних суток записались бы повторно.
    """
    asyncio.run(writer.flush(line_monitor=_monitor_with([_cycle(cycle_id=1)])))

    restarted = JournalWriter(
        JournalStore(tmp_path / "journal"), rows_provider=lambda: {"5": [_row()]}
    )
    restarted.load_written_keys()
    monitor = _monitor_with(
        [
            _cycle(cycle_id=1),
            _cycle(cycle_id=2, exit_at="2026-09-29T21:16:03"),
        ]
    )

    assert asyncio.run(restarted.flush(line_monitor=monitor)) == 1
    assert [r["cycle_id"] for r in restarted.store.query(limit=10).items] == [2, 1]


def test_writer_logs_the_match_line_once(writer, caplog):
    """Строка сопоставления уходит и в лог контейнера, и в файл.

    Раньше её писал роут по запросу фронта: в ``docker logs`` она была
    только пока открыт дашборд.
    """
    import logging

    with caplog.at_level(logging.INFO, logger="app.services.journal_writer"):
        asyncio.run(writer.flush(line_monitor=_monitor_with([_cycle()])))

    [line] = [r.getMessage() for r in caplog.records if r.name == "app.services.journal_writer"]
    assert "cycle=42" in line
    assert "hanger=5" in line

    records = writer.store.query(limit=10).items
    assert json.dumps(records[0], ensure_ascii=False), "запись читается как JSON"


def test_pass_visible_to_the_monitor_is_never_written_twice(tmp_path):
    """Проход, который монитор ещё показывает, не переписывается за все дни.

    Писатель помнит ограниченное число записанных проходов. Если память
    об этом числе заканчивается, вытеснение должно уносить самые старые
    ключи: вытеснив ключ прохода, который монитор всё ещё показывает,
    писатель записал бы его в файл второй раз.
    """
    from app.services.journal_writer import RECENT_KEYS_MAX

    writer = JournalWriter(
        JournalStore(tmp_path / "journal"), rows_provider=dict
    )
    monitor = _monitor_with([])

    total = RECENT_KEYS_MAX + 50
    for index in range(total):
        monitor._events.append(
            _cycle(cycle_id=1000 + index, hanger=5, exit_at=f"2026-09-29T{index % 24:02d}:{index % 60:02d}:00")
        )
        asyncio.run(writer.flush(line_monitor=monitor))

    lines = [
        line
        for journal_file in writer.store.files()
        for line in journal_file.path.read_text(encoding="utf-8").splitlines()
        if line
    ]
    assert len(lines) == total, "каждый проход записан ровно один раз"


def test_retention_is_applied_while_the_server_runs(tmp_path):
    """Срок хранения наступает и без перезапуска сервера.

    Ротация по сроку только при старте не работает: сервер на заводской
    машине месяцами не перезапускают, и старые файлы копились бы вечно.
    """
    import app.services.journal_writer as writer_module

    store = JournalStore(tmp_path / "journal", retention_days=30)
    writer = JournalWriter(store, rows_provider=dict)
    stale = store.directory / "hanger-passes-2000-01-01.jsonl"
    stale.parent.mkdir(parents=True, exist_ok=True)
    stale.write_text("{}\n", encoding="utf-8")

    async def run_task():
        # Опрос без пауз: писатель убирает старый файл за первый же тик.
        task = asyncio.create_task(writer.run_forever(_monitor_with([]), interval=0))
        await asyncio.sleep(0.05)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

    original = writer_module.PRUNE_INTERVAL_SECONDS
    writer_module.PRUNE_INTERVAL_SECONDS = 0
    try:
        asyncio.run(run_task())
    finally:
        writer_module.PRUNE_INTERVAL_SECONDS = original

    assert not stale.exists()



def _monitor_with(events):
    """Монитор линии, у которого видны заданные проходы."""

    class _Monitor:
        def __init__(self):
            self._events = list(events)

        def get_unload_events(self, limit: int = 100):
            return list(reversed(self._events[-limit:]))

    return _Monitor()
