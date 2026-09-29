"""Чтение журнала подвесов из интерфейса (issue #34).

Контракт под тестом (``GET /api/journal/passes``):
- ответ отдаёт страницу проходов и общее их число, а не весь файл;
- вместе с проходами отдаётся путь к каталогу журнала и имена файлов:
  оператор должен знать, куда смотреть на диске и в контейнере;
- сбой чтения каталога — пустая страница, а не 500: вкладка журнала не
  должна ронять приложение из-за недоступного диска.
"""
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient

from app.services.hanger_journal import JournalStore


def _record(hanger=5, cycle_id=42, exit_at="2026-09-29T20:16:03", profile="10104"):
    return {
        "recorded_at": exit_at,
        "cycle_id": cycle_id,
        "hanger": hanger,
        "code": "",
        "source": "watched",
        "entry_bath": 3,
        "first_seen_at": "2026-09-29T17:04:00",
        "exit_at": exit_at,
        "total_time_sec": 11523.0,
        "row_date": "28.09.2026",
        "row_time": "18:31",
        "row_number": str(hanger),
        "profile": profile,
        "color": "серебро",
        "kpz_number": "151",
        "lamels_qty": 86,
        "client": "РП",
        "material_type": "Пороги",
        "is_defect": False,
        "entry_delta_sec": -1800.0,
        "rows_after_exit": 0,
        "note": "",
        "path": [{"bath": "3", "in": "2026-09-29T17:04:00", "out": "2026-09-29T18:10:00"}],
        "type": "unload",
        "reason": None,
    }


@pytest.fixture
def journal(tmp_path: Path, monkeypatch):
    """Журнал во временном каталоге, подменённый в приложении."""
    from app.api.routes import journal as journal_route

    store = JournalStore(tmp_path / "journal")
    for index in range(7):
        store.append(
            _record(
                hanger=index,
                cycle_id=100 + index,
                profile="1010{}".format(index),
                exit_at="2026-09-29T1{}:00:00".format(index),
            )
        )
    monkeypatch.setattr(journal_route, "journal_store", lambda: store)
    return store


async def _get(params: dict) -> dict:
    from app.main import app

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.get("/api/journal/passes", params=params)
        assert response.status_code == 200, response.text
        return response.json()


async def test_passes_endpoint_returns_a_page_and_total(journal):
    body = await _get({"limit": 3})

    assert body["total"] == 7
    assert [p["hanger"] for p in body["items"]] == [6, 5, 4], "новые сверху"
    assert body["items"][0]["profile"] == "10106"
    assert body["items"][0]["exit_at"] == "2026-09-29T16:00:00"


async def test_passes_endpoint_applies_search_and_sort(journal):
    body = await _get({"search": "10103", "sort": "hanger", "direction": "asc"})

    assert [p["hanger"] for p in body["items"]] == [3]


async def test_passes_endpoint_tells_where_the_files_live(journal):
    body = await _get({"limit": 1})

    assert body["directory"] == str(journal.directory)
    assert [f["name"] for f in body["files"]] == ["hanger-passes-2026-09-29.jsonl"]
    assert body["retention_days"] == journal.retention_days
    assert body["files"][0]["size_bytes"] > 0


async def test_passes_endpoint_reports_unreadable_journal_as_empty(monkeypatch):
    """Недоступный диск — пустая вкладка, а не падение приложения."""
    from app.api.routes import journal as journal_route

    class _Broken(JournalStore):
        def files(self):
            raise OSError("диск недоступен")

    monkeypatch.setattr(
        journal_route, "journal_store", lambda: _Broken(Path("Z:/нет/такого"))
    )

    body = await _get({})

    assert body["items"] == []
    assert body["total"] == 0
