"""Сверка фото каталога по последним строкам книги учёта.

Скрипт отвечает на один вопрос: у каких строк книги на дашборде будет снимок
Профиля, а у каких — серая заглушка. Профиль берётся из той же ячейки книги,
что и на дашборде (``excel_service``), фото ищет тот же сервис каталога
(``catalog_service.get_profiles_photos_batch``), поэтому отчёт не расходится
с экраном.

Сравнение «до/после» — через ``--compare-ref``: код каталога берётся из
указанного коммита (``git show``), а строки книги читаются один раз, так что
оба прогона видят одни и те же данные.

Запуск из корня репозитория (нужен backend/.venv и доступ к книге):

    npm run report:photos
    npm run report:photos -- --limit 10000 --compare-ref bac166f
    npm run report:photos -- --out .scratch/photo-match-report.html --json .scratch/photo.json

Отчёт — самодостаточный HTML (поиск по профилям работает без сети).
"""

import argparse
import asyncio
import html
import importlib.util
import json
import logging
import os
import subprocess
import sys
import tempfile
from datetime import datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
BACKEND_DIR = REPO_ROOT / "backend"

DEFAULT_LIMIT = 10_000
DEFAULT_OUT = Path(".scratch/photo-match-report.html")


def bootstrap() -> None:
    """Каталог книги, .env и импорты приложения живут относительно backend/."""
    os.chdir(BACKEND_DIR)
    sys.path.insert(0, str(BACKEND_DIR))
    quiet_sqlalchemy()


def quiet_sqlalchemy() -> None:
    """``DEBUG=true`` включает echo движка; отчёт не должен тонуть в SQL.

    Одного ``setLevel`` мало: echo ставит на логгер движка свой обработчик и
    пишет через него. Поэтому обработчики снимаются, а запись выше не идёт.
    """
    for name in ("sqlalchemy", "sqlalchemy.engine", "sqlalchemy.engine.Engine", "sqlalchemy.pool"):
        logger = logging.getLogger(name)
        logger.setLevel(logging.WARNING)
        for handler in list(logger.handlers):
            logger.removeHandler(handler)
        logger.propagate = False


def resolve_output(value: str | Path) -> Path:
    """Путь отчёта трактуется от корня репозитория, а не от backend/."""
    path = Path(value)
    return path if path.is_absolute() else (REPO_ROOT / path)


def read_book_rows(limit: int):
    from app.services.excel_service import excel_service

    rows = excel_service.get_products(limit=limit, from_end=True, loading_only=False)
    book = getattr(excel_service, "current_path", None)
    return rows, (getattr(book, "name", None) or "—")


def collect_profiles(rows) -> dict[str, dict]:
    """Профили ячеек книги: сколько строк, как записаны, где лежат в листе."""
    from app.services.profile_name import split_profiles

    profiles: dict[str, dict] = {}
    for row in rows:
        for parsed in split_profiles(row.profile):
            entry = profiles.setdefault(
                parsed.name,
                {"rows": 0, "cells": set(), "processing": set(), "sheet_rows": []},
            )
            entry["rows"] += 1
            entry["cells"].add(parsed.raw)
            entry["processing"].update(parsed.processing)
            if len(entry["sheet_rows"]) < 5:
                entry["sheet_rows"].append([row.sheet_row, row.date, str(row.number)])
    return profiles


async def catalog_flags() -> dict[str, dict]:
    """Что вообще есть в каталоге и у чего есть файл фото — для причин пропуска."""
    from app.core.text_utils import normalize_text
    from app.db.models import Profile
    from app.db.session import get_session
    from sqlalchemy import select

    async with get_session() as session:
        profiles = (await session.execute(select(Profile))).scalars().all()

    flags: dict[str, dict] = {}
    for profile in profiles:
        item = {"name": profile.name, "has_photo": bool(profile.photo_thumb or profile.photo_full)}
        flags[profile.name.lower()] = item
        flags.setdefault(normalize_text(profile.name), item)
    return flags


def flag_for(flags: dict[str, dict], name: str) -> dict | None:
    """Запись каталога по имени ячейки: точное совпадение, затем нормализация."""
    return flags.get(name.lower()) or flags.get(name)


async def photo_status(service, names: list[str]) -> dict[str, dict]:
    """Имена с фото по версии сервиса: та же функция, что зовёт дашборд."""
    if not hasattr(service, "get_profiles_photos_batch"):
        raise RuntimeError("в выбранном коммите ещё нет пакетного поиска фото")
    photos = await service.get_profiles_photos_batch(names)
    return {
        name: {
            "has_photo": name in photos,
            "article": photos[name].get("name") if name in photos else None,
            "thumb": photos[name].get("thumb") if name in photos else None,
        }
        for name in names
    }


def load_baseline_service(ref: str):
    """Сервис каталога из коммита: живой git show, без checkout и stash.

    Модуль исполняется под отдельным именем, чтобы не подменить рабочий
    ``app.services.catalog_service`` в этом процессе.
    """
    try:
        source = subprocess.run(
            ["git", "-C", str(REPO_ROOT), "show", f"{ref}:backend/app/services/catalog_service.py"],
            check=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
        ).stdout
    except subprocess.CalledProcessError as error:
        raise SystemExit(f"не удалось прочитать catalog_service.py из {ref}: {error.stderr.strip()}") from error

    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "catalog_service.py"
        path.write_text(source, encoding="utf-8")
        spec = importlib.util.spec_from_file_location("app.services._catalog_baseline", path)
        if spec is None or spec.loader is None:
            raise SystemExit(f"не удалось загрузить catalog_service.py из {ref}")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
    return module.catalog_service


def row_metrics(rows, photo_names: set[str]) -> dict[str, int]:
    """Строки книги: все профили с фото / часть / ничего / без профиля.

    Ячейка может нести несколько артикулов через ``+`` или ``/``. Считать
    «строку с фото» по числу профилей нельзя: такая строка попала бы в
    числитель и знаменатель дважды. Поэтому метрика считается по строкам.
    """
    from app.services.profile_name import split_profiles

    metrics = {"total": len(rows), "full": 0, "partial": 0, "none": 0, "no_profile": 0}
    for row in rows:
        parsed = split_profiles(row.profile)
        if not parsed:
            metrics["no_profile"] += 1
            continue
        hits = sum(1 for profile in parsed if profile.name in photo_names)
        if hits == len(parsed):
            metrics["full"] += 1
        elif hits:
            metrics["partial"] += 1
        else:
            metrics["none"] += 1
    return metrics


def esc(value) -> str:
    return html.escape(str(value))


def profile_table(names: list[str], profiles: dict[str, dict], status: dict[str, dict], flags: dict[str, dict]) -> str:
    """Таблица профилей: ячейки книги, артикул каталога и причина заглушки."""
    rows = []
    for name in names:
        meta, entry = profiles[name], status[name]
        known = flag_for(flags, name)
        if entry["has_photo"]:
            article = entry["article"] or (known["name"] if known else "—")
            reason = ""
            css = "gain" if not entry.get("was", True) else "ok"
            pill = "<span class='pill gain'>+ фото</span>" if css == "gain" else "<span class='pill ok'>фото</span>"
        else:
            article = known["name"] if known else "—"
            reason = "нет снимка" if known else "нет артикула"
            css = "no"
            pill = "<span class='pill no'>заглушка</span>"

        cells = " / ".join(esc(cell) for cell in sorted(meta["cells"])[:2])
        sheets = ", ".join(esc(f"{sheet} ({date})") for sheet, date, _ in meta["sheet_rows"][:3])
        rows.append(
            "<tr class='{css}'>"
            "<td class='mono'>{name}</td>"
            "<td class='num'>{rows}</td>"
            "<td>{pill}</td>"
            "<td class='mono'>{article}</td>"
            "<td class='mono dim'>{reason}</td>"
            "<td class='cells'>{cells}</td>"
            "<td class='mono dim'>{sheets}</td>"
            "</tr>".format(
                css=css,
                name=esc(name),
                rows=meta["rows"],
                pill=pill,
                article=esc(article),
                reason=esc(reason),
                cells=cells,
                sheets=sheets,
            )
        )
    return "\n".join(rows)


def table(names: list[str], profiles: dict[str, dict], status: dict[str, dict], flags: dict[str, dict]) -> str:
    if not names:
        return "<p class='note'>Таких нет.</p>"
    return (
        "<table class='grid'><thead><tr>"
        "<th>Профиль (чистое имя)</th><th class='num'>Строк</th><th>Статус</th>"
        "<th>Артикул каталога</th><th>Причина</th><th>Ячейки в книге</th><th>Строки листа</th>"
        "</tr></thead><tbody>"
        + profile_table(names, profiles, status, flags)
        + "</tbody></table>"
    )


def bars(old: dict[str, int], new: dict[str, int]) -> str:
    def one(label: str, metrics: dict[str, int], css: str) -> str:
        base = metrics["total"] - metrics["no_profile"]
        share = metrics["full"] / base * 100 if base else 0
        return (
            '<div class="bar-row">'
            f'<span class="bar-label">{label}</span>'
            f'<div class="bar"><div class="fill {css}" style="width:{share:.1f}%"></div></div>'
            f'<span class="bar-num">{metrics["full"]} из {base} строк · {share:.1f}%</span>'
            "</div>"
        )

    return one("Было", old, "old") + one("Стало", new, "new")


def render_html(payload: dict, tables: dict[str, str]) -> str:
    rows, old, new = payload["rows"], payload["old"], payload["new"]
    return f"""<!doctype html>
<html lang="ru">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Фото каталога: сверка по книге учёта</title>
<style>
  :root {{
    --bg:#f7f8fa; --card:#fff; --ink:#1b2430; --dim:#6b7785; --line:#e3e7ed;
    --ok:#0f7b3f; --ok-bg:#e8f7ee; --no:#b42318; --no-bg:#fdecea;
    --gain:#8a5a00; --gain-bg:#fff5db; --accent:#2f6fed;
  }}
  * {{ box-sizing:border-box }}
  body {{ margin:0; background:var(--bg); color:var(--ink);
    font:14px/1.45 "Segoe UI", system-ui, -apple-system, sans-serif; }}
  .wrap {{ max-width:1500px; margin:0 auto; padding:28px 24px 60px; }}
  h1 {{ font-size:22px; margin:0 0 4px; }}
  h2 {{ font-size:16px; margin:34px 0 8px; }}
  .sub {{ color:var(--dim); margin:0 0 20px; }}
  .cards {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(170px,1fr)); gap:12px; }}
  .card {{ background:var(--card); border:1px solid var(--line); border-radius:10px; padding:14px 16px; }}
  .card .k {{ color:var(--dim); font-size:12px; text-transform:uppercase; letter-spacing:.04em; }}
  .card .v {{ font-size:26px; font-weight:700; margin-top:6px; }}
  .card .d {{ color:var(--dim); font-size:12px; margin-top:2px; }}
  .bars {{ background:var(--card); border:1px solid var(--line); border-radius:10px;
    padding:14px 16px; margin-top:12px; }}
  .bar-row {{ display:grid; grid-template-columns:60px 1fr 240px; align-items:center; gap:12px; padding:5px 0; }}
  .bar {{ height:14px; background:#eef1f5; border-radius:7px; overflow:hidden; }}
  .fill {{ height:100%; border-radius:7px; }}
  .fill.old {{ background:#9aa7b8; }}
  .fill.new {{ background:var(--ok); }}
  .bar-num {{ color:var(--dim); font-variant-numeric:tabular-nums; }}
  .grid {{ width:100%; border-collapse:collapse; background:var(--card);
    border:1px solid var(--line); border-radius:10px; overflow:hidden; }}
  .grid th {{ text-align:left; font-size:12px; color:var(--dim); font-weight:600;
    text-transform:uppercase; letter-spacing:.03em; padding:9px 10px; border-bottom:1px solid var(--line);
    position:sticky; top:0; background:var(--card); }}
  .grid td {{ padding:7px 10px; border-bottom:1px solid var(--line); vertical-align:top; }}
  .grid tr:last-child td {{ border-bottom:0; }}
  .grid tbody tr.ok td:first-child {{ border-left:3px solid var(--ok); }}
  .grid tbody tr.gain td:first-child {{ border-left:3px solid #e0a300; }}
  .grid tbody tr.no td:first-child {{ border-left:3px solid #e6b3ae; }}
  .grid tbody tr:hover {{ background:#fafbfc; }}
  .num {{ text-align:right; font-variant-numeric:tabular-nums; white-space:nowrap; }}
  .mono {{ font-family:Consolas, "Cascadia Mono", monospace; font-size:12.5px; }}
  .dim {{ color:var(--dim); }}
  .cells {{ max-width:340px; font-size:12px; }}
  .pill {{ display:inline-block; padding:1px 8px; border-radius:999px; font-size:12px; font-weight:600; white-space:nowrap; }}
  .pill.ok {{ color:var(--ok); background:var(--ok-bg); }}
  .pill.gain {{ color:var(--gain); background:var(--gain-bg); }}
  .pill.no {{ color:var(--no); background:var(--no-bg); }}
  .toolbar {{ display:flex; flex-wrap:wrap; gap:10px; align-items:center; margin:0 0 10px; }}
  #q {{ flex:1 1 320px; min-width:240px; padding:8px 11px; border:1px solid var(--line);
    border-radius:8px; font-size:14px; background:var(--card); }}
  .count {{ color:var(--dim); font-size:13px; }}
  .note {{ color:var(--dim); font-size:12.5px; margin:6px 0 0; }}
  code {{ background:#eef1f5; padding:1px 5px; border-radius:4px; font-size:12px; }}
</style>
</head>
<body>
<div class="wrap">
  <h1>Фото каталога: сверка по книге учёта</h1>
  <p class="sub">
    Книга: <b>{esc(payload["book"])}</b> · последние {rows["total"]} строк · {esc(payload["period"])}
    · уникальных профилей: {payload["profiles"]}
  </p>

  <div class="cards">
    <div class="card"><div class="k">Строк с полным фото</div><div class="v">{new["full"]}</div>
      <div class="d">было {old["full"]} · {new["full"] - old["full"]:+d}</div></div>
    <div class="card"><div class="k">Строк без полного фото</div><div class="v">{new["partial"] + new["none"]}</div>
      <div class="d">частично {new["partial"]} · совсем без фото {new["none"]}</div></div>
    <div class="card"><div class="k">Профилей без фото</div><div class="v">{payload["no_article"] + payload["no_snapshot"]}</div>
      <div class="d">нет артикула {payload["no_article"]} · нет снимка {payload["no_snapshot"]}</div></div>
    <div class="card"><div class="k">Добавилось профилей</div><div class="v">{len(payload["gained"])}</div>
      <div class="d">потеряно: {len(payload["lost"])}</div></div>
  </div>

  <div class="bars">
    {bars(old, new)}
    <p class="note">
      Строка считается «с полным фото», когда снимок есть у каждого профиля её ячейки;
      строки без Профиля (рейки, панели, оснастка) в знаменатель не входят.
      Статус считает тот же код, что и дашборд: <code>catalog_service.get_profiles_photos_batch</code>.
      {payload["baseline"]}
    </p>
  </div>

  <h2>Что добавилось после правки</h2>
  <p class="note">В ячейке книги рядом с артикулом стоит размер или пометка: «ЮП-2083 2,75 метра»,
    «ЮП-1880 2.5м», «ЮП-2083 (1.8)». Каталог знает артикул без хвоста, поэтому раньше фото не находилось.</p>
  {tables["gained"]}

  <h2>Остались без фото: артикул в каталоге есть, снимка нет</h2>
  <p class="note">Это данные источника, а не матчинг: файл нужно привезти синком каталога.</p>
  {tables["no_snapshot"]}

  <h2>Остались без фото: артикула нет в каталоге</h2>
  <p class="note">Профилями каталога эти позиции не являются (заготовки, рейки, панели, оснастка) —
    снимка у них и не будет.</p>
  {tables["no_article"]}

  <h2>Все профили выборки</h2>
  <div class="toolbar">
    <input id="q" type="search" placeholder="Поиск по профилю, артикулу, ячейке…" autocomplete="off">
    <span id="count" class="count"></span>
  </div>
  {tables["all"]}

  <p class="note">Сформировано {esc(payload["generated_at"])}. Повтор:
    <code>npm run report:photos -- --limit {rows["total"]}{esc(payload["compare_hint"])}</code></p>
</div>
<script>
  const q = document.getElementById('q');
  const count = document.getElementById('count');
  const rows = [...document.querySelectorAll('#all tbody tr')];
  function apply() {{
    const text = q.value.trim().toLowerCase();
    let shown = 0;
    for (const row of rows) {{
      const visible = !text || row.textContent.toLowerCase().includes(text);
      row.style.display = visible ? '' : 'none';
      if (visible) shown++;
    }}
    count.textContent = `показано ${{shown}} из ${{rows.length}}`;
  }}
  q.addEventListener('input', apply);
  apply();
</script>
</body>
</html>
"""


async def run(args) -> int:
    from app.services.catalog_service import catalog_service

    quiet_sqlalchemy()
    try:
        rows, book = read_book_rows(args.limit)
    except Exception as error:  # сеть/шара: оператору нужен текст, а не стек
        print(f"не удалось прочитать книгу учёта: {error}", file=sys.stderr)
        return 2
    if not rows:
        print("книга не дала строк: проверь путь и доступ к файлу", file=sys.stderr)
        return 2

    profiles = collect_profiles(rows)
    names = list(profiles)
    flags = await catalog_flags()

    current = await photo_status(catalog_service, names)
    if args.compare_ref:
        baseline_service = load_baseline_service(args.compare_ref)
        try:
            baseline = await photo_status(baseline_service, names)
        except RuntimeError as error:
            print(f"{error}: {args.compare_ref}", file=sys.stderr)
            return 2
        baseline_note = f"«Было» — код каталога из <code>{esc(args.compare_ref)}</code>."
        compare_hint = f" --compare-ref {args.compare_ref}"
    else:
        baseline = current
        baseline_note = "«Было» не задано: сравнение с кодом из коммита включается флагом <code>--compare-ref</code>."
        compare_hint = ""

    photo_now = {name for name, item in current.items() if item["has_photo"]}
    photo_old = {name for name, item in baseline.items() if item["has_photo"]}
    metrics_old = row_metrics(rows, photo_old)
    metrics_new = row_metrics(rows, photo_now)

    for name in names:
        profiles[name].update(current[name])
        profiles[name]["was"] = name in photo_old

    gained = sorted(
        (name for name in names if current[name]["has_photo"] and not baseline[name]["has_photo"]),
        key=lambda name: (-profiles[name]["rows"], name.lower()),
    )
    lost = sorted(name for name in names if not current[name]["has_photo"] and baseline[name]["has_photo"])
    no_article = sorted(
        (name for name in names if not current[name]["has_photo"] and flag_for(flags, name) is None),
        key=lambda name: (-profiles[name]["rows"], name.lower()),
    )
    no_snapshot = sorted(
        (
            name
            for name in names
            if not current[name]["has_photo"]
            and flag_for(flags, name) is not None
            and not flag_for(flags, name)["has_photo"]
        ),
        key=lambda name: (-profiles[name]["rows"], name.lower()),
    )

    dates = [row.date for row in rows if row.date and row.date != "—"]
    payload = {
        "generated_at": datetime.now().strftime("%d.%m.%Y %H:%M"),
        "book": book,
        "limit": args.limit,
        "period": f"{dates[-1]} — {dates[0]}" if dates else "—",
        "rows": metrics_new,
        "old": metrics_old,
        "new": metrics_new,
        "profiles": len(names),
        "old_profiles": len(photo_old),
        "new_profiles": len(photo_now),
        "gained": gained,
        "lost": lost,
        "no_article": len(no_article),
        "no_snapshot": len(no_snapshot),
        "baseline": baseline_note,
        "compare_hint": compare_hint,
        "items": {
            name: {
                "rows": profiles[name]["rows"],
                "cells": sorted(profiles[name]["cells"]),
                "processing": sorted(profiles[name]["processing"]),
                "sheet_rows": profiles[name]["sheet_rows"],
                "has_photo": current[name]["has_photo"],
                "was": profiles[name]["was"],
                "article": current[name]["article"],
                "thumb": current[name]["thumb"],
                "in_catalog": flag_for(flags, name) is not None,
                "catalog_has_photo": bool((flag_for(flags, name) or {}).get("has_photo")),
            }
            for name in names
        },
    }

    tables = {
        "gained": table(gained, profiles, current, flags),
        "no_snapshot": table(no_snapshot, profiles, current, flags),
        "no_article": table(no_article, profiles, current, flags),
        "all": table(names, profiles, current, flags),
    }

    out = resolve_output(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(render_html(payload, tables), encoding="utf-8")

    if args.json:
        json_out = resolve_output(args.json)
        json_out.parent.mkdir(parents=True, exist_ok=True)
        json_out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    base = metrics_new["total"] - metrics_new["no_profile"]
    old_share = metrics_old["full"] / base * 100 if base else 0
    new_share = metrics_new["full"] / base * 100 if base else 0
    print(f"книга: {book}")
    print(f"строк: {metrics_new['total']} ({payload['period']}), профилей: {len(names)}")
    print(
        f"строк с полным фото: {metrics_old['full']} -> {metrics_new['full']} "
        f"({old_share:.1f}% -> {new_share:.1f}%)"
    )
    print(f"профилей с фото: {len(photo_old)} -> {len(photo_now)} (+{len(gained)} / -{len(lost)})")
    print(f"без фото: нет артикула {len(no_article)}, артикул без снимка {len(no_snapshot)}")
    if no_snapshot:
        preview = ", ".join(f"{name} ({profiles[name]['rows']})" for name in no_snapshot[:8])
        print(f"  нет снимка: {preview}")
    print(f"отчёт: {out}")
    if args.json:
        print(f"json: {resolve_output(args.json)}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Сверка фото каталога по строкам книги учёта")
    parser.add_argument("--limit", type=int, default=DEFAULT_LIMIT, help="сколько последних строк книги взять")
    parser.add_argument("--out", default=str(DEFAULT_OUT), help="HTML-отчёт (путь от корня репозитория)")
    parser.add_argument("--json", default=None, help="JSON с теми же данными (необязательно)")
    parser.add_argument(
        "--compare-ref",
        default=None,
        help="коммит с прежним catalog_service.py для сравнения «до/после»",
    )
    args = parser.parse_args(argv)

    bootstrap()
    return asyncio.run(run(args))


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    sys.exit(main())
