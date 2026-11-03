"""Распределение расхождения входа по журналу проходов — калибровка допуска.

Источник — файлы ``hanger-passes-*.jsonl``, которые пишет ``journal_writer``
на каждую выгрузку. В выборку входят только проходы с ``source=watched``:
у ``start`` и ``gap`` первый замер равен моменту, когда монитор посмотрел на
линию, а не появлению подвеса, поэтому дельта по ним ничего не значит.
Считается модуль дельты: именно он сравнивается с допуском.

Порог по умолчанию — как в ``matching.py`` (30 минут), чтобы сразу видеть,
сколько записей он помечает. Другой порог — ``--tolerance``.

Запуск из корня репозитория (пути можно задавать маской, каталогом или
списком файлов):

    python scripts/entry-delta-stats.py journal/hanger-passes-*.jsonl
    python scripts/entry-delta-stats.py journal-dev --tolerance 3600

Каталог журнала у каждой среды свой (прод — ``journal/``, dev-хост —
``journal-dev/``), поэтому своего представления о том, где лежит журнал, у
скрипта нет: путь всегда приходит аргументом.
"""

import argparse
import glob
import json
import statistics
import sys
from pathlib import Path

# Порог matching.py: скрипт не импортирует backend, чтобы запускаться на
# любом хосте без venv проекта. Значение сверяется тестом.
DEFAULT_TOLERANCE_SECONDS = 30 * 60
WATCHED = "watched"


def expand_paths(patterns: list[str]) -> list[Path]:
    """Файлы журнала по аргументам командной строки, в стабильном порядке.

    Аргумент — файл, каталог или маска: PowerShell отдаёт маску как есть,
    а не раскрывает её, поэтому раскрытие на стороне скрипта.
    """
    files: list[Path] = []
    for pattern in patterns:
        path = Path(pattern)
        if path.is_dir():
            files.extend(sorted(path.glob("hanger-passes-*.jsonl")))
        else:
            matched = sorted(Path(match) for match in glob.glob(pattern))
            if not matched and path.is_file():
                matched = [path]
            files.extend(matched)
    return files


def read_records(files: list[Path]) -> list[dict]:
    """Все записи журнала; битая строка — ошибка, а не тихий пропуск.

    Пропущенная строка сдвинула бы выборку молча, поэтому номер строки и
    файл попадают в сообщение об ошибке.
    """
    records: list[dict] = []
    for file in files:
        with file.open(encoding="utf-8") as stream:
            for number, line in enumerate(stream, start=1):
                line = line.strip()
                if not line:
                    continue
                try:
                    records.append(json.loads(line))
                except json.JSONDecodeError as error:
                    raise SystemExit(f"{file}:{number}: не разобрать запись: {error}") from error
    return records


def watched_deltas(records: list[dict]) -> list[float]:
    """Модули расхождения проходов с достоверным первым замером."""
    deltas: list[float] = []
    for record in records:
        if record.get("source") != WATCHED:
            continue
        delta = record.get("entry_delta_sec")
        if isinstance(delta, bool) or not isinstance(delta, (int, float)):
            continue
        deltas.append(abs(float(delta)))
    return deltas


def percentile(values: list[float], share: float) -> float:
    """Перцентиль линейной интерполяцией — как в numpy и statistics.quantiles."""
    ordered = sorted(values)
    position = share * (len(ordered) - 1)
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    weight = position - lower
    return ordered[lower] + (ordered[upper] - ordered[lower]) * weight


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Распределение entry_delta_sec по журналу проходов")
    parser.add_argument("paths", nargs="+", help="файлы, каталоги или маски hanger-passes-*.jsonl")
    parser.add_argument(
        "--tolerance",
        type=float,
        default=DEFAULT_TOLERANCE_SECONDS,
        help="допуск входа в секундах (по умолчанию 1800 — как MAX_ENTRY_DELTA_SECONDS)",
    )
    args = parser.parse_args(argv)

    files = expand_paths(args.paths)
    if not files:
        print(f"не найдено файлов журнала: {', '.join(args.paths)}", file=sys.stderr)
        return 2

    records = read_records(files)
    deltas = watched_deltas(records)

    print(f"файлов: {len(files)}")
    for file in files:
        print(f"  {file}")
    print(f"записей: {len(records)}")
    print(f"с дельтой (source={WATCHED}): {len(deltas)}")
    if not deltas:
        print("квантили: нет записей с достоверным первым замером")
        return 0

    print(
        f"|delta| сек: min {min(deltas):.1f}, медиана {statistics.median(deltas):.1f}, "
        f"p90 {percentile(deltas, 0.9):.1f}, max {max(deltas):.1f}"
    )
    anomalies = [delta for delta in deltas if delta > args.tolerance]
    print(f"аномалий (> {args.tolerance:.0f} с): {len(anomalies)}")
    for delta in sorted(anomalies):
        print(f"  {delta:.1f} с ({delta / 3600:.1f} ч)")
    return 0


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    sys.exit(main())
