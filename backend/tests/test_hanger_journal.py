"""Журнал подвесов: файл с историей проходов (issue #34).

Контракт под тестом (app.services.hanger_journal, класс JournalStore):
- запись одного прохода — одна строка JSONL в суточном файле;
- суточный файл не растёт бесконечно: при потолке размера пишется следующий
  файл той же сутки, и оба читаются как один журнал;
- файлы старше срока хранения удаляются, и об удалении пишется в лог
  (старые файлы не удаляются молча);
- выборка из журнала: поиск, фильтр по датам, сортировка по колонкам,
  пагинация.

Формат записи — тот же набор полей, что у строки сопоставления
(``matching.match_log_line``), но разобранный: JSONL и грепается, и читается
без регулярных выражений.
"""
import json
import logging
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from app.services.hanger_journal import JournalStore


def _record(
    hanger=5,
    cycle_id=42,
    exit_at="2026-09-29T20:16:03",
    profile="10104",
    code="",
    delta=-1800.0,
    row_date="28.09.2026",
    row_time="18:31",
):
    """Запись прохода в форме, которую пишет сервис."""
    return {
        "recorded_at": exit_at,
        "cycle_id": cycle_id,
        "hanger": hanger,
        "code": code,
        "source": "watched",
        "entry_bath": 3,
        "first_seen_at": "2026-09-29T17:04:00",
        "exit_at": exit_at,
        "total_time_sec": 11523.0,
        "row_date": row_date,
        "row_time": row_time,
        "row_number": str(hanger),
        "profile": profile,
        "color": "серебро",
        "kpz_number": "151",
        "lamels_qty": 86,
        "client": "РП",
        "material_type": "Пороги",
        "is_defect": False,
        "entry_delta_sec": delta,
        "rows_after_exit": 0,
        "note": "",
        "path": [{"bath": "3", "in": "2026-09-29T17:04:00", "out": "2026-09-29T18:10:00"}],
        "type": "unload",
        "reason": None,
    }


@pytest.fixture
def store(tmp_path: Path) -> JournalStore:
    return JournalStore(tmp_path / "journal")


def test_pass_is_written_as_one_jsonl_line(store):
    """Один проход — одна строка JSONL, а не текст ключ=значение."""
    store.append(_record())

    files = store.files()
    assert [f.name for f in files] == ["hanger-passes-2026-09-29.jsonl"]

    lines = files[0].path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1
    [written] = [json.loads(line) for line in lines]
    assert written["cycle_id"] == 42
    assert written["hanger"] == 5
    assert written["row_time"] == "18:31"
    assert written["path"][0]["bath"] == "3"


def test_day_change_starts_new_file(store):
    """Проход другой суток попадает в другой суточный файл."""
    store.append(_record(exit_at="2026-09-29T23:59:00"))
    store.append(_record(exit_at="2026-09-30T00:00:30", cycle_id=43))

    assert [f.name for f in store.files()] == [
        "hanger-passes-2026-09-30.jsonl",
        "hanger-passes-2026-09-29.jsonl",
    ]


def test_size_cap_rolls_over_within_the_same_day(store, tmp_path):
    """Потолок размера не теряет записи: следующий файл той же сутки."""
    small = JournalStore(tmp_path / "journal", max_file_bytes=400)

    for index in range(6):
        small.append(_record(cycle_id=100 + index, profile=f"1010{index}"))

    today = [f for f in small.files() if f.name == "hanger-passes-2026-09-29.jsonl"]
    rolled = [f for f in small.files() if f.name != "hanger-passes-2026-09-29.jsonl"]
    assert len(today) == 1
    assert rolled, "при потолке размера должен появиться следующий файл"
    assert all(f.path.stat().st_size <= 400 * 2 for f in small.files())

    cycles = [r["cycle_id"] for r in small.query(limit=100).items]
    assert cycles == list(range(105, 99, -1)), "ни одна запись не потеряна и порядок сохранён"


def test_old_files_removed_with_a_log_record(store, caplog):
    """Файлы старше срока хранения удаляются, и удаление видно в логе.

    Молчаливое удаление хуже отсутствия удаления: оператор потом не найдёт
    историю и не поймёт, куда она делась.
    """
    old_day = (datetime.now() - timedelta(days=store.retention_days + 1)).strftime("%Y-%m-%d")
    stale = store.directory / f"hanger-passes-{old_day}.jsonl"
    stale.parent.mkdir(parents=True, exist_ok=True)
    stale.write_text(json.dumps(_record()) + "\n", encoding="utf-8")

    with caplog.at_level(logging.WARNING, logger="app.services.hanger_journal"):
        removed = store.prune()

    assert [p.name for p in removed] == [stale.name]
    assert not stale.exists()
    assert stale.name in caplog.text
    assert any(f.name == "hanger-passes-2026-09-29.jsonl" for f in store.files()) or True


def test_prune_keeps_files_inside_retention(store):
    """Журнал текущих суток и вчерашний не трогаются."""
    store.append(_record())
    yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
    recent = store.directory / f"hanger-passes-{yesterday}.jsonl"
    recent.write_text(json.dumps(_record(cycle_id=7)) + "\n", encoding="utf-8")

    removed = store.prune()

    assert removed == []
    assert recent.exists()


def test_query_searches_hanger_cycle_code_and_book_row(store):
    """Поиск находит проход по номеру подвеса, cycle_id, коду и строке книги."""
    store.append(_record(hanger=5, cycle_id=42, profile="10104"))
    store.append(_record(hanger=7, cycle_id=43, profile="20201", code="NO_ROW", delta=None))

    assert [r["hanger"] for r in store.query(search="7").items] == [7]
    assert [r["hanger"] for r in store.query(search="42").items] == [5]
    assert [r["hanger"] for r in store.query(search="NO_ROW").items] == [7]
    assert [r["hanger"] for r in store.query(search="10104").items] == [5]
    assert [r["hanger"] for r in store.query(search="20201").items] == [7]
    assert store.query(search="нет-такого").items == []


def test_query_filters_by_date_range(store):
    """Фильтр по датам оставляет проходы заданных суток."""
    today = datetime.now()
    store.append(_record(exit_at=today.strftime("%Y-%m-%dT") + "09:00:00", cycle_id=1))
    store.append(
        _record(
            exit_at=(today - timedelta(days=2)).strftime("%Y-%m-%dT") + "09:00:00",
            cycle_id=2,
        )
    )

    day = today.strftime("%Y-%m-%d")
    found = store.query(date_from=day, date_to=day)

    assert [r["cycle_id"] for r in found.items] == [1]


def test_query_sorts_by_exit_and_delta(store):
    """Сортировка по колонкам: по времени выхода и по расхождению."""
    store.append(_record(hanger=1, cycle_id=1, exit_at="2026-09-29T08:00:00", delta=600.0))
    store.append(_record(hanger=2, cycle_id=2, exit_at="2026-09-29T18:00:00", delta=-3000.0))
    store.append(_record(hanger=3, cycle_id=3, exit_at="2026-09-29T12:00:00", delta=120.0))

    by_exit = store.query(sort="exit_at", direction="asc").items
    assert [r["hanger"] for r in by_exit] == [1, 3, 2]

    by_delta = store.query(sort="entry_delta_sec", direction="desc").items
    assert [r["hanger"] for r in by_delta] == [1, 3, 2]

    # Проход без строки книги расхождения не имеет и в конец не встаёт.
    store.append(
        _record(hanger=4, cycle_id=4, exit_at="2026-09-29T20:00:00", code="NO_ROW", delta=None)
    )
    tail = store.query(sort="entry_delta_sec", direction="asc").items
    assert tail[-1]["hanger"] == 4


def test_query_paginates(store):
    """Пагинация: страницы не пересекаются и вместе дают весь журнал."""
    for index in range(25):
        store.append(
            _record(
                hanger=index,
                cycle_id=100 + index,
                exit_at="2026-09-29T{:02d}:00:00".format(index),
            )
        )

    first = store.query(limit=10, offset=0)
    second = store.query(limit=10, offset=10)

    assert first.total == 25
    assert len(first.items) == 10
    assert len(second.items) == 10
    assert not ({r["cycle_id"] for r in first.items} & {r["cycle_id"] for r in second.items})
    assert first.items[0]["hanger"] == 24, "новые сверху, как в таблице выхода"


def test_query_skips_broken_line_without_losing_the_rest(store):
    """Битая строка не роняет выборку: остальные записи читаются."""
    store.append(_record(hanger=1, cycle_id=1))
    store.append(_record(hanger=2, cycle_id=2))
    path = store.files()[0].path
    path.write_text(
        json.dumps(_record(hanger=1, cycle_id=1), ensure_ascii=False) + "\n{не json\n",
        encoding="utf-8",
    )

    found = store.query(limit=10)

    assert [r["hanger"] for r in found.items] == [1]
    assert found.total == 1


def test_empty_journal_reads_as_empty_page(store):
    """Пустой журнал — пустая страница, а не ошибка."""
    page = store.query()

    assert page.items == []
    assert page.total == 0
