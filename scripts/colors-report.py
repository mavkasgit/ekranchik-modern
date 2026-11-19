"""Каталог цветов отдельной HTML-страницей: справочник, частота в книге и вид плашек.

Страница нужна для сравнения, а не для оператора: поэтому она собирается
отдельным файлом (``docs/colors-reference.html``), а не роутом приложения —
киоск не должен знать про служебный экран.

Что внутри:

- все цвета справочника ``colors`` с кодом, названием, hex и аббревиатурой;
- сколько раз цвет встречается в книге учёта (последние ``--limit`` строк);
- как цвет выглядит полоской в ячейке «Цвет» и плашкой «Прогноз»;
- поиск и сортировка (частота / код / название) на чистом JS.

Запуск из корня репозитория (нужен backend/.venv):

    npm run report:colors
    npm run report:colors -- --limit 20000 --out docs/colors-reference.html

По умолчанию читается та же книга, что у стенда (``.env`` бэкенда), поэтому
отчёт снимается при живом бэкенде или без него — сервисы читают файл сами.
"""

import argparse
import asyncio
import html
import os
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
BACKEND_DIR = REPO_ROOT / "backend"

DEFAULT_LIMIT = 10_000
DEFAULT_OUT = Path("docs/colors-reference.html")

# Было до этой ревизии палитры: показывается в карточке как «было #RRGGBB».
# Ключ — "код|название", чтобы дубли названий не путались.
PREVIOUS_HEX = {
    "|Серебро": "#C0C0C0",
    "C0|Серебро": "#C2CAD3",
    "|Шампань": "#F7E7CE",
    "C31|Светлая шампань": "#CFD4D5",
    "|Медь": "#CD5C5C",
    "C33|Светлая бронза": "#716C62",
    "C34|Тёмная бронза": "#595655",
    "C35|Чёрный": "#4E4E52",
    "C41|Медь": "#A0837E",
    "C44|Тёмная медь": "#715C5F",
    "C51|Нержавеющая сталь": "#A9968E",
    "RST|растрав": "#D3D3D3",
    "S120-0|Золото": "#E1DDB0",
    "S120-2|Старое золото": "#AD9E77",
}

EMPTY_TOKENS = {"", "—", "-", "nan", "none"}


def bootstrap() -> None:
    os.chdir(BACKEND_DIR)
    sys.path.insert(0, str(BACKEND_DIR))
    quiet_sqlalchemy()


def quiet_sqlalchemy() -> None:
    """``DEBUG=true`` включает echo SQL; отчёт не должен тонуть в логах запросов."""
    import logging

    for name in ("sqlalchemy", "sqlalchemy.engine", "sqlalchemy.engine.Engine", "sqlalchemy.pool"):
        logger = logging.getLogger(name)
        logger.setLevel(logging.WARNING)
        for handler in list(logger.handlers):
            logger.removeHandler(handler)
        logger.propagate = False


def normalize_name(value: str) -> str:
    return re.sub(r"[\s\-_]", "", value.lower()).replace("ё", "е")


def normalize_code(value: str) -> str:
    return re.sub(r"[\s\-_]", "", value.lower()).replace("с", "c")


def match_color(colors, written: str):
    """Тот же порядок, что у панели: код, точное имя, затем уточнение в скобках."""
    text = (written or "").strip()
    if text.lower() in EMPTY_TOKENS:
        return None

    code_key = normalize_code(text)
    for color in colors:
        if color.code and normalize_code(color.code) == code_key:
            return color

    name_key = normalize_name(text)
    if not name_key:
        return None

    exact = [color for color in colors if normalize_name(color.name) == name_key]
    if exact:
        # Название без кода — привычное оператору написание.
        without_code = [color for color in exact if not color.code]
        return without_code[0] if without_code else exact[0]

    for color in colors:
        color_key = normalize_name(color.name)
        if color_key and color_key in name_key:
            return color
    return None


def read_book(limit: int):
    from app.services.excel_service import excel_service

    rows = excel_service.get_products(limit=limit, from_end=True, loading_only=False)
    path = getattr(excel_service, "current_path", None)
    return rows, (getattr(path, "name", None) or "—")


def count_usage(colors, rows):
    counts: dict[int, int] = {}
    unknown: dict[str, int] = {}
    for row in rows:
        color = match_color(colors, getattr(row, "color", "") or "")
        if color is None:
            written = (getattr(row, "color", "") or "").strip() or "—"
            unknown[written] = unknown.get(written, 0) + 1
            continue
        counts[color.id] = counts.get(color.id, 0) + 1
    return counts, unknown


def contrast_ratio(hex_a: str, hex_b: str) -> float:
    def luminance(value: str) -> float:
        parts = [int(value[i : i + 2], 16) / 255 for i in (1, 3, 5)]
        channels = [c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4 for c in parts]
        return 0.2126 * channels[0] + 0.7152 * channels[1] + 0.0722 * channels[2]

    light, dark = sorted((luminance(hex_a), luminance(hex_b)), reverse=True)
    return (light + 0.05) / (dark + 0.05)


ROW_BACKGROUND = "#E2E8F0"


def previous_key(color) -> str:
    return f"{color.code or ''}|{color.name}"


def readable_ink(hex_value: str) -> str:
    """Цвет текста на плашке: белый на тёмной, почти чёрный на светлой."""
    return "#ffffff" if contrast_ratio(hex_value, "#FFFFFF") >= 4.5 else "#0f172a"


def render_card(color, usage: int) -> str:
    key = previous_key(color)
    previous = PREVIOUS_HEX.get(key)
    old_line = (
        f'<div class="old">было <code>{html.escape(previous)}</code>'
        f'<span class="delta">{contrast_ratio(previous, ROW_BACKGROUND):.2f} → '
        f"{contrast_ratio(color.hex, ROW_BACKGROUND):.2f}</span></div>"
        if previous and previous.lower() != color.hex.lower()
        else ""
    )
    code = (
        f'<span class="code">{html.escape(color.code)}</span>'
        if color.code
        else '<span class="code none">без кода</span>'
    )
    search = " ".join(part for part in (color.code or "", color.name, color.hex, color.abbreviation or "") if part)
    return f"""
      <article class="card" data-usage="{usage}" data-code="{html.escape(color.code or "яя")}"
               data-name="{html.escape(color.name)}" data-search="{html.escape(search.lower())}">
        <div class="strip" style="background: {html.escape(color.hex)}"></div>
        <div class="card-body">
          <div class="card-head">
            {code}
            <span class="name">{html.escape(color.name)}</span>
            <span class="abbr">{html.escape(color.abbreviation or "")}</span>
          </div>
          <div class="hex-line">
            <code>{html.escape(color.hex)}</code>
            <span class="usage" title="Сколько строк книги с этим цветом">
              {usage} {rows_word(usage)}
            </span>
          </div>
          <div class="meta">KTM {html.escape(color.operation_code or "—")} · {html.escape(color.source)}</div>
          {old_line}
          <div class="cell-preview">
            <span class="cell-name">{html.escape(color.name.lower())}</span>
            <span class="cell-bar" style="background: {html.escape(color.hex)}"></span>
          </div>
          <div class="chip-preview" style="background: {html.escape(color.hex)}; color: {readable_ink(color.hex)}">
            <span>{html.escape(color.abbreviation or color.name)}</span>
            <span class="chip-time">09:04</span>
          </div>
        </div>
      </article>"""


def rows_word(count: int) -> str:
    if count % 10 == 1 and count % 100 != 11:
        return "строка"
    if 2 <= count % 10 <= 4 and not 12 <= count % 100 <= 14:
        return "строки"
    return "строк"


def render(colors, counts, unknown, book_name: str, rows_read: int) -> str:
    cards = "\n".join(render_card(color, counts.get(color.id, 0)) for color in colors)
    unknown_line = ", ".join(
        f"{'без цвета' if name == '—' else html.escape(name)} — {count}"
        for name, count in sorted(unknown.items(), key=lambda pair: -pair[1])
    )
    changed = sum(1 for color in colors if previous_key(color) in PREVIOUS_HEX)
    total = sum(counts.values())

    return f"""<!doctype html>
<html lang="ru">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>Цвета — справочник и частота в книге</title>
    <style>
      :root {{
        color-scheme: light dark;
        --bg: #f6f7f9;
        --panel: #ffffff;
        --text: #16181d;
        --muted: #5c6470;
        --line: #d9dde3;
        --accent: #1f6feb;
        --row: {ROW_BACKGROUND};
      }}
      @media (prefers-color-scheme: dark) {{
        :root {{
          --bg: #12141a;
          --panel: #1a1d25;
          --text: #eef0f4;
          --muted: #9aa3b2;
          --line: #2b303b;
          --accent: #6ea8ff;
          --row: #2a3140;
        }}
      }}
      * {{ box-sizing: border-box; }}
      body {{
        margin: 0;
        padding: 32px 20px 64px;
        background: var(--bg);
        color: var(--text);
        font: 15px/1.5 system-ui, -apple-system, "Segoe UI", Roboto, sans-serif;
      }}
      .wrap {{ max-width: 1180px; margin: 0 auto; }}
      h1 {{ margin: 0 0 6px; font-size: 26px; letter-spacing: -0.01em; }}
      .lead {{ margin: 0; color: var(--muted); max-width: 820px; }}
      .toolbar {{ display: flex; flex-wrap: wrap; gap: 12px; align-items: center; margin: 22px 0 6px; }}
      input[type="search"], select {{
        padding: 9px 12px; border: 1px solid var(--line); border-radius: 8px;
        background: var(--panel); color: var(--text); font: inherit;
      }}
      input[type="search"] {{ flex: 1 1 260px; min-width: 200px; }}
      .count {{ color: var(--muted); font-size: 13px; }}
      .grid {{
        display: grid; gap: 14px; margin-top: 16px;
        grid-template-columns: repeat(auto-fill, minmax(250px, 1fr));
      }}
      .card {{
        border: 1px solid var(--line); border-radius: 12px; overflow: hidden;
        background: var(--panel); display: flex; flex-direction: column;
      }}
      .strip {{ height: 46px; border-bottom: 1px solid var(--line); }}
      .card-body {{ padding: 10px 12px 12px; display: flex; flex-direction: column; gap: 8px; }}
      .card-head {{ display: flex; align-items: baseline; gap: 8px; }}
      .code {{
        font: 11px/1.4 ui-monospace, SFMono-Regular, Menlo, monospace;
        border: 1px solid var(--line); border-radius: 6px; padding: 1px 6px; color: var(--muted);
      }}
      .code.none {{ border-style: dashed; }}
      .name {{ font-weight: 600; }}
      .abbr {{ margin-left: auto; color: var(--muted); font-size: 11px; }}
      .hex-line {{ display: flex; align-items: baseline; justify-content: space-between; gap: 8px; }}
      .meta {{ font-size: 11px; color: var(--muted); font-family: ui-monospace, SFMono-Regular, Menlo, monospace; }}
      code {{ font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-size: 12px; }}
      .usage {{ color: var(--muted); font-size: 12px; }}
      .old {{ font-size: 12px; color: var(--muted); }}
      .old .delta {{ margin-left: 8px; }}
      .cell-preview {{
        background: var(--row); border-radius: 8px; padding: 8px;
        display: flex; flex-direction: column; align-items: center; gap: 6px;
      }}
      .cell-name {{ font-size: 12px; }}
      .cell-bar {{
        display: block; width: 100%; height: 8px; border-radius: 999px;
        box-shadow: inset 0 0 0 1px rgb(0 0 0 / 0.3);
      }}
      .chip-preview {{
        border-radius: 8px; padding: 6px 10px; font-weight: 600; font-size: 12px;
        color: #0f172a; display: flex; justify-content: space-between; gap: 12px;
      }}
      .chip-time {{ opacity: 0.7; font-family: ui-monospace, SFMono-Regular, Menlo, monospace; }}
      footer {{ margin-top: 28px; color: var(--muted); font-size: 13px; max-width: 900px; }}
      footer code {{ font-size: 12px; }}
      .empty {{ margin-top: 20px; color: var(--muted); }}
    </style>
  </head>
  <body>
    <div class="wrap">
      <header>
        <h1>Цвета: справочник и частота в книге</h1>
        <p class="lead">
          Палитра киоска после ревизии: «семьи», которые книга не различает, получили один цвет
          (шампань — {html.escape("#AEA895")}, чёрный — #1C1C1C, золото — #FFD700, серебро — #E7EBEE).
          Рядом — как цвет выглядит полоской в ячейке «Цвет» и плашкой «Прогноз».
        </p>
      </header>

      <div class="toolbar">
        <input type="search" id="q" placeholder="Поиск: код, название, hex" autocomplete="off" />
        <select id="sort">
          <option value="usage">По частоте в книге</option>
          <option value="code">По коду</option>
          <option value="name">По названию</option>
        </select>
        <span class="count" id="count"></span>
      </div>

      <p class="lead">
        Всего цветов: <strong>{len(colors)}</strong>. Изменено в ревизии:
        <strong>{changed}</strong>. Строк книги просмотрено: <strong>{rows_read}</strong>
        (файл <code>{html.escape(book_name)}</code>), из них с цветом справочника:
        <strong>{total}</strong>. Без цвета или с неизвестным написанием: {html.escape(unknown_line or "—")}.
      </p>

      <div class="grid" id="grid">
{cards}
      </div>

      <p class="empty" id="empty" hidden>Ничего не найдено.</p>

      <footer>
        Страница генерируется скриптом <code>scripts/colors-report.py</code>:
        <code>npm run report:colors</code>. Данные — справочник <code>colors</code> в
        <code>static/ekranchik.db</code> и книга учёта КПЗ; частота считается по последним
        строкам книги и не хранится в базе.
      </footer>
    </div>

    <script>
      const grid = document.getElementById("grid");
      const cards = [...grid.querySelectorAll(".card")];
      const query = document.getElementById("q");
      const sort = document.getElementById("sort");
      const count = document.getElementById("count");
      const empty = document.getElementById("empty");

      function usage(card) {{ return Number(card.dataset.usage || 0); }}

      function apply() {{
        const needle = query.value.trim().toLowerCase();
        let shown = 0;
        for (const card of cards) {{
          const match = !needle || card.dataset.search.includes(needle);
          card.hidden = !match;
          if (match) shown += 1;
        }}
        const mode = sort.value;
        const sorted = [...cards].sort((a, b) => {{
          if (mode === "usage") return usage(b) - usage(a) || a.dataset.name.localeCompare(b.dataset.name, "ru");
          if (mode === "code") return a.dataset.code.localeCompare(b.dataset.code, "ru");
          return a.dataset.name.localeCompare(b.dataset.name, "ru");
        }});
        for (const card of sorted) grid.appendChild(card);
        count.textContent = shown + " из " + cards.length;
        empty.hidden = shown !== 0;
      }}

      query.addEventListener("input", apply);
      sort.addEventListener("change", apply);
      apply();
    </script>
  </body>
</html>
"""


def len_rows(limit: int) -> str:
    return f"≤{limit}"


async def collect(limit: int):
    from app.services.color_service import color_service

    # Движок включает echo на создании — гасим лог ещё раз уже после импорта.
    quiet_sqlalchemy()
    colors = await color_service.list_colors()
    rows, book_name = read_book(limit)
    counts, unknown = count_usage(colors, rows)
    return colors, counts, unknown, book_name, len(rows)


def main() -> int:
    parser = argparse.ArgumentParser(description="Каталог цветов отдельной HTML-страницей")
    parser.add_argument("--limit", type=int, default=DEFAULT_LIMIT, help="сколько строк книги читать")
    parser.add_argument("--out", default=str(DEFAULT_OUT), help="куда писать HTML")
    args = parser.parse_args()

    bootstrap()
    colors, counts, unknown, book_name, rows_read = asyncio.run(collect(args.limit))

    out = Path(args.out)
    if not out.is_absolute():
        out = REPO_ROOT / out
    out.parent.mkdir(parents=True, exist_ok=True)

    page = render(colors, counts, unknown, book_name, rows_read)
    out.write_text(page, encoding="utf-8")

    total = sum(counts.values())
    print(f"Цветов: {len(colors)}, строк книги: {rows_read}, с цветом: {total}")
    print(f"Отчёт: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
