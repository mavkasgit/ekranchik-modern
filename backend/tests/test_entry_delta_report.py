"""Пересчёт распределения расхождения входа: ``scripts/entry-delta-stats.py``.

Скрипт операционный и живёт вне backend, поэтому проверяется запуском, а не
импортом: его контракт — формат вывода, которым пользуются при калибровке
``MAX_ENTRY_DELTA_SECONDS`` (ADR 0005). Записи журнала берутся в том виде,
в каком их пишет ``journal_writer``, включая ``source`` и ``entry_delta_sec``.

Скрипт не зависит от dev-каталога: путь к журналу передаётся аргументом,
здесь это временный каталог pytest.
"""

import json
import subprocess
import sys
from pathlib import Path

from app.services.matching import MAX_ENTRY_DELTA_SECONDS

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "entry-delta-stats.py"


def _record(delta, source="watched", cycle_id=1):
    return {
        "cycle_id": cycle_id,
        "source": source,
        "entry_delta_sec": delta,
        "recorded_at": "2026-11-03T10:00:00",
    }


def _run(tmp_path, records, *args):
    journal = tmp_path / "hanger-passes-2026-11-03.jsonl"
    journal.write_text(
        "\n".join(json.dumps(record, ensure_ascii=False) for record in records) + "\n",
        encoding="utf-8",
    )
    return subprocess.run(
        [sys.executable, str(SCRIPT), str(journal), *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
    )


def test_reports_quantiles_of_watched_deltas_only(tmp_path):
    """Квантили считаются по |delta| проходов watched, остальное отброшено."""
    records = [_record(value, cycle_id=value) for value in range(1, 11)]
    records.append(_record(99999, source="start", cycle_id=90))
    records.append(_record(None, cycle_id=91))

    done = _run(tmp_path, records)

    assert done.returncode == 0, done.stderr
    out = done.stdout
    assert "записей: 12" in out
    assert "с дельтой (source=watched): 10" in out
    assert "min 1.0" in out
    assert "медиана 5.5" in out
    assert "p90 9.1" in out
    assert "max 10.0" in out


def test_counts_anomalies_above_tolerance(tmp_path):
    """Порог по умолчанию — тот, что стоит в matching.py (30 минут)."""
    boundary = MAX_ENTRY_DELTA_SECONDS
    records = [_record(boundary - 1, cycle_id=1), _record(-(boundary + 1), cycle_id=2)]

    done = _run(tmp_path, records)

    assert done.returncode == 0, done.stderr
    assert f"аномалий (> {boundary:.0f} с): 1" in done.stdout, "по модулю выше допуска — одна запись"


def test_tolerance_is_overridable(tmp_path):
    """Другой порог — для проверки, какой границе соответствует хвост."""
    records = [_record(600, cycle_id=1), _record(2700, cycle_id=2)]

    done = _run(tmp_path, records, "--tolerance", "3000")

    assert done.returncode == 0, done.stderr
    assert "аномалий (> 3000 с): 0" in done.stdout
