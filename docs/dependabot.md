# Dependabot и зелёность CI

Правило проекта: **`main` всегда зелёный, красный PR не мержится** — ни свой,
ни Dependabot. «Зелёный» значит: `check.yml` прошёл целиком, включая
`npm run build` фронтенда.

## Команды

```bash
gh pr list --json number,title,statusCheckRollup          # что открыто и как проверено
gh pr checks <N>                                          # джобы конкретного PR
gh pr merge <N> --squash --delete-branch                  # зелёный PR
gh pr comment <N> --body "@dependabot rebase"             # устаревшая ветка
gh run list --workflow=check.yml --limit 5                # последние прогоны
gh run watch <run-id> --exit-status                       # дождаться и получить код
```

Локальная проверка перед push:

```bash
mise run check
cd backend && .venv/Scripts/python -m pytest -q
cd frontend && npx vitest run && npm run build
```

## Почему PR падают по одному

Dependabot двигает по одному пакету, а версии в стеке связаны peer-
зависимостями. Одиночный PR ломает `npm ci` (`ERESOLVE`) или CI, хотя
**пара** обновлений проходит. Такие пакеты обновляются вместе, одной веткой
от свежего `main`:

| Связка                                                      | Почему вместе                                            |
| ----------------------------------------------------------- | -------------------------------------------------------- |
| `react` + `react-dom` + `@types/react` + `@types/react-dom` | типы 19 требуют React 19, иначе `ERESOLVE`               |
| `vite` + `@vitejs/plugin-react` (+ `vitest`)                | plugin-react 6 требует `vite ^8`; vitest 5 идёт с Vite 8 |
| `typescript` + `frontend/tsconfig.json`                     | TS 7 убрал `baseUrl`; `paths` должны начинаться с `./`   |
| `pandas` + `python-dateutil`                                | pandas 3 требует dateutil 3, pandas 2 — нет              |
| `pytest` + `pytest-asyncio`                                 | pytest 9 несовместим со старым pytest-asyncio            |
| `pydantic` + `pydantic-settings`                            | settings 2.16 требует pydantic 2.15+                     |
| `tailwindcss` + `postcss.config.js` + `index.css`           | Tailwind 4 меняет PostCSS-плагин и директивы CSS         |

## Порядок разбора очереди

1. Сначала мержатся зелёные PR (`--squash`), по одному. После каждого —
   дождаться зелёного push-прогона в `main`: следующий PR может стать
   конфликтным.
2. Устаревшие ветки (созданы до фиксов в `main`) — `@dependabot rebase`.
   Если rebase конфликтует в lock-файле, PR пересоздаётся вручную.
3. Связанные красные PR — одна ветка от `main`, оба пакета сразу, локальные
   проверки, PR. После мержа исходные PR Dependabot закрываются ссылкой на
   новый PR.
4. Мажоры, которые требуют миграции кода, — тоже отдельная ветка. Закрывать
   PR можно только с причиной и записью в `docs/quality-gates.md`.

## Что именно проверяет CI

`check.yml`:

- `quality gates` — `mise run check` (ruff, oxlint, oxfmt, knip, tsc,
  betterleaks, shellcheck, hadolint, jactionlint) + commitlint;
- `tests` — backend pytest, frontend vitest, **frontend `npm run build`**;
- OSV — по понедельникам, не блокирует PR.

E2E в CI пока нет: `live_demo.spec.mts` требует симулятор и отдельный job.
Локально: `npm run dev:sim`, затем `npm run chrome:debug` и `npm run test:e2e`;
без CDP — `E2E_BROWSER_MODE=headless` и `CHROME_PATH`.

## Если PR всё равно красный

Смотреть не название джобы, а первый упавший шаг:

```bash
gh pr checks <N>
gh run view --job <job-id> --log | grep -E "npm error|FAILED|error TS|✖"
```

Типичные ошибки:

- `ERESOLVE` — не хватает парного обновления (см. таблицу);
- `Missing @emnapi/* from lock file` — ветка старая, нужен rebase;
- `TS5102: Option 'baseUrl' has been removed` — миграция tsconfig под TS 7;
- `FAILED tests/unit/test_excel_sheet_row.py` — тест зависел от локальной
  книги Excel, уже исправлено; на старой ветке лечится rebase.
