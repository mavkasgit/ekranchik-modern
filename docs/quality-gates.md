# Проверки качества (quality gates)

Что и где проверяется, как это запустить и какие исключения уже зафиксированы.
Список инструментов взят из [dev-quality-gates](https://github.com/mokevnin/dev-quality-gates)
(adopt, 2026-11-03); версии пинятся в `mise.toml` + `mise.lock`.

## Команды

```bash
mise install        # поставить инструменты из mise.toml (та же версия, что в CI)
mise run install    # npm ci + frontend ci + backend/.venv
mise run hooks      # один раз на клон: поставить git-хуки hk

npm run gate:fast   # ярус fast: статика по всему репозиторию, офлайн (бюджет 60 с)
npm run gate        # полный гейт: fast + pytest + vitest + vite build + ратчеты; ровно это запускает CI
npm run gate:e2e    # полный гейт + Playwright; нужен живой стенд и Chrome с CDP :9222
npm run doctor      # PATH, инструменты, docs-sync, чистота рабочего дерева
npm run check:docs  # только сверка карты защит с шагами гейта
npm run fix         # безопасные автофиксы (ruff, oxfmt, jactionlint); дифф перечитать
```

`npm run gate` — один вход: его вызывает CI, на него же смотрит агент перед
ответом «готово». Быстрый ярус — отдельная команда `npm run gate:fast`; `gate`
и `gate:e2e` накопительные. `mise run check` / `mise run gate` — тонкие алиасы
этих команд, чтобы привычка не расходилась с контрактом.

## Три уровня

| Уровень | Команда             | Когда                         | Что запускается                                                                                        | Бюджет          |
| ------- | ------------------- | ----------------------------- | ------------------------------------------------------------------------------------------------------ | --------------- |
| `fast`  | `npm run gate:fast` | быстрый цикл, `pre-push`      | ruff, oxfmt, oxlint, betterleaks, shellcheck, hadolint, jactionlint, knip, tsc, docs-sync — всё офлайн | ≤ 60 с          |
| `gate`  | `npm run gate`      | CI на push/PR, перед «готово» | `fast` + modern-web, reactuse-diff, pytest, vitest, `vite build`                                       | минуты          |
| `e2e`   | `npm run gate:e2e`  | вручную или ночью             | `gate` + Playwright (нужен стенд :8013/:5173 и Chrome CDP :9222)                                       | отдельный стенд |

Список статических шагов не дублируется в JS: хозяин — `hk.pkl`, а `gate.mjs`
запускает `hk check --all --step <имя>`. Поэтому новый линтер добавляется в
`hk.pkl`, а в `STEPS` — только строка с его именем.

Без `mise install` инструменты (`hk`, `ruff`, `oxlint`…) не в PATH: шаг с
ненайденным инструментом печатается как `missing` с подсказкой, а не падает
«команда не найдена». `missing` — видимое «не проверено»; краснеет он только с
`--strict`. В `gate` нет шагов, которым нужен инструмент, отсутствующий на
чистой машине после `mise install`, кроме `modern-web` (сеть) и
`reactuse-diff` (нужен `origin/main`).

Хуки — удобство, а не гейт: `pre-commit` (`hk`) проверяет staged-файлы и умеет
`--fix` — это допустимо как ускоритель обратной связи; гейт же только читает.
`pre-push` гоняет набор `hk` целиком (включая `modern-web`/`reactuse-diff`),
`commit-msg` — `commitlint`. CI вызывает `npm run gate`, а не свою копию
шагов. `commitlint` в PR проверяет весь диапазон `base..head`, при push в
`main` — последний коммит: история до внедрения гейта (2026-11-03) не
переписана и служит бейзлайном.

## Карта шагов

Список между маркерами сверяется с `STEPS` из [`scripts/gate.mjs`](../scripts/gate.mjs)
машинно (`npm run check:docs`, шаг `docs-sync`): имя, ярус, CI и колонка
«Доказано падает». Добавили шаг — внесите строку; убрали — уберите.

<!-- gate-steps:start -->

| Шаг              | Ярус | Что ловит                                                        | CI                                                      | Блокирует                                                    | Доказано падает                                  |
| ---------------- | ---- | ---------------------------------------------------------------- | ------------------------------------------------------- | ------------------------------------------------------------ | ------------------------------------------------ |
| `docs-sync`      | fast | шаг в коде без строки в карте и наоборот, шаг без доказательства | check.yml                                               | да                                                           | `proven-checks.json#docs-sync`                   |
| `ruff`           | fast | ошибки Python (E4/E7/E9/F/I/UP/B/C4/SIM)                         | check.yml                                               | да                                                           | `proven-checks.json#ruff`                        |
| `oxfmt`          | fast | расхождение формата js/ts/md/yaml/toml/json/html/css             | check.yml                                               | да                                                           | `proven-checks.json#oxfmt`                       |
| `oxlint`         | fast | категория correctness и `no-unused-vars` в JS/TS                 | check.yml                                               | да                                                           | exempt: рецепт и исполнитель — следующий заход   |
| `betterleaks`    | fast | закоммиченный секрет                                             | check.yml                                               | да                                                           | `proven-checks.json#betterleaks`                 |
| `shellcheck`     | fast | ошибки и переносимость shell                                     | check.yml                                               | да                                                           | exempt: в репозитории нет своих `*.sh`           |
| `hadolint`       | fast | практики Dockerfile                                              | check.yml                                               | да                                                           | exempt: Dockerfile живёт в релизном пайплайне    |
| `jactionlint`    | fast | корректность, security и policy GitHub Actions                   | check.yml                                               | да                                                           | `proven-checks.json#jactionlint`                 |
| `knip`           | fast | неиспользуемые файлы, экспорты и dev-зависимости                 | check.yml                                               | да                                                           | exempt: рецепт и исполнитель — следующий заход   |
| `tsc`            | fast | ошибка типов TypeScript (`--noEmit`, strict)                     | check.yml                                               | да                                                           | `proven-checks.json#tsc`                         |
| `modern-web`     | gate | новый legacy-паттерн веб-платформы сверх бейзлайна               | check.yml                                               | да; `missing` (сканер/сеть недоступны) — только с `--strict` | exempt: нужен сетевой сканер                     |
| `reactuse-diff`  | gate | новый ручной `matchMedia`/observers/clipboard вместо ReactUse    | check.yml                                               | да; `missing` (нет `origin/main`) — только с `--strict`      | exempt: нужен дифф с `origin/main`               |
| `backend-tests`  | gate | регрессия backend (pytest, in-memory sqlite)                     | check.yml                                               | да                                                           | exempt: 363 теста, красный ход — следующий заход |
| `frontend-unit`  | gate | регрессия frontend (vitest run)                                  | check.yml                                               | да                                                           | exempt: красный ход — следующий заход            |
| `frontend-build` | gate | production-сборка (`vite build`, без повторного `tsc -b`)        | check.yml                                               | да                                                           | exempt: рецепт — порча entry в `index.html`      |
| `e2e-playwright` | e2e  | сломан пользовательский путь (smoke, catalog, live_demo)         | missing: e2e требует живого стенда и Chrome с CDP :9222 | да, если стенд жив; `missing` — только с `--strict`          | exempt: нужен живой стенд                        |

<!-- gate-steps:end -->

Колонка «CI» — не проза: `docs-sync` сверяет её с полем `ci` в `STEPS`.
`check.yml` значит «шаг живёт в CI-прогоне `npm run gate`»; `missing: причина`
— шаг в CI намеренно не выполняется, пока нет стенда.

Доказательства и исключения — [`docs/quality/proven-checks.json`](quality/proven-checks.json):
`reviewed` — когда рецепт проверяли, `expires` — когда его надо пересмотреть.
Рецепты в `steps` перенесены из раздела «Как проверить, что гейт падает»
(проверены 2026-11-03) и будут автоматизированы `prove-checks.mjs`.

## Что проверяется

| Инструмент  | Область                                     | Конфиг                                                                | Что ловит                                      |
| ----------- | ------------------------------------------- | --------------------------------------------------------------------- | ---------------------------------------------- |
| Ruff        | `backend/**/*.py`, `scripts/**/*.py`        | `backend/ruff.toml` (backend), `ruff.toml` (scripts, extends backend) | E4/E7/E9/F/I/UP/B/C4/SIM + формат              |
| Oxlint      | JS/TS/MTS                                   | `.oxlintrc.json`                                                      | категория correctness, `no-unused-vars`        |
| oxfmt       | js/ts/md/yaml/toml/json/html/css            | `.oxfmtrc.json`                                                       | формат (Prettier-совместимый)                  |
| Knip        | JS/TS                                       | `knip.json`                                                           | неиспользуемые файлы, экспорты, зависимости    |
| TypeScript  | `frontend/**/*.{ts,tsx}`                    | `frontend/tsconfig.json`                                              | `tsc --noEmit`, `strict`                       |
| betterleaks | весь репозиторий                            | —                                                                     | закоммиченные секреты                          |
| ShellCheck  | `**/*.sh`                                   | —                                                                     | ошибки и переносимость shell                   |
| Hadolint    | `**/Dockerfile*`                            | `.hadolint.yaml`                                                      | практики Dockerfile                            |
| jactionlint | `.github/workflows/*.yml`, `dependabot.yml` | `.github/jactionlint.yaml`                                            | корректность, security и policy GitHub Actions |
| commitlint  | сообщения коммитов                          | `commitlint.config.js`                                                | Conventional Commits                           |
| OSV-Scanner | lock-файлы                                  | —                                                                     | известные уязвимости (только по расписанию)    |

## Бейзлайны и исключения

Правило проекта: сначала бейзлайн, а не выключение проверки. Исключение — один
файл и одно правило, с причиной; для рисков (безопасность, инфраструктура)
ещё и с датой ревизии.

| Где                        | Что скрыто                                                                                                                                                                                 | Почему                                                                                              | Ревизия      |
| -------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ | --------------------------------------------------------------------------------------------------- | ------------ |
| `.github/jactionlint.yaml` | 8 правил для `release-full-installer.yml`: concurrency-limits, excessive-permissions, missing-timeout, unpinned-uses, artipacked, cache-poisoning, template-injection, superfluous-actions | файл в активной правке хозяина; `check.yml` уже написан без исключений                              | `2027-05-01` |
| `.hadolint.yaml`           | DL3008 (pin apt-версий), DL3015 (`--no-install-recommends`)                                                                                                                                | пин версий замедляет сборку, а `--no-install-recommends` меняет состав пакетов; решение за хозяином | `2027-05-01` |
| `.oxlintrc.json`           | 19 срабатываний `react/*` и `react-hooks/exhaustive-deps` в 7 старых файлах                                                                                                                | правила React Compiler требуют отдельного рефакторинга экранов; новые файлы проверяются             | `2027-05-01` |
| `knip.json`                | `frontend/src/components/ui/**`, `src/hooks/use-toast.ts`                                                                                                                                  | сгенерированные компоненты shadcn/ui, неиспользуемость — норма библиотеки                           | —            |
| `backend/ruff.toml`        | E402 в `alembic/**` и конфестах pytest                                                                                                                                                     | импорты намеренно идут после настройки `sys.path`                                                   | —            |
| OSV-скан                   | 51 уязвимость в 10 пакетах (на 2026-11-03)                                                                                                                                                 | после миграции зависимостей; скан идёт по расписанию и обновляет картину                            | `2027-05-01` |

OSV-скан намеренно не блокирует PR: новая advisory не должна красить сборку без
изменений в коде. Он запускается по понедельникам и артефактом отдаёт отчёт.

## Что не внедрено

Категории ниже есть в списке рекомендаций, но для этого репозитория пока не
взяты — с причиной, а не «забыли»:

- **.NET SDK analyzers** — `EkranchikKiosk` и `EkranchikServer` собираются под
  Windows (WinForms), их сборка и так идёт в релизном пайплайне; отдельный
  линтер на ubuntu-CI сломал бы Matrix.
- **ty / deptry / import-linter** — следующий этап для backend: сначала
  зелёный Ruff, потом типы и контракты импортов.
- **dependency-cruiser** — границы модулей фронтенда пока держатся структурой
  `src/api`, `src/lib`, `src/realtime`; правило появится, когда границы начнут
  нарушаться.
- **Stylelint / axe-core / size-limit** — CSS и доступность не проверяются,
  пока нет бюджета и правил; добавлять линтер без них — шум.
- **diff-cover** — покрытие тестами не гейтится: backend-тесты уже есть,
  но порог не выбран.
- **check-jsonschema / conftest** — JSON/YAML-конфиги валидируются самими
  инструментами (mise, hk, jactionlint, Dependabot).
- **agnix** — линтер `AGENTS.md`; правила для агентов появились позже, кандидат
  на следующий заход.
- **lychee / typos / rumdl** — ссылки и опечатки в документации пока не гейтятся.
- **oasdiff / vacuum** — OpenAPI-схема не публикуется как контракт.
- **schemalens / squawk** — миграции Alembic + SQLite; squawk только PostgreSQL.
- **syncpack** — workspace-монорепо нет, у корня и `frontend` свои lock-файлы.
- **Renovate** — заменён на Dependabot: он уже настроен с `cooldown` и группами,
  а jactionlint проверяет `dependabot-cooldown`.

## Сгенерированные файлы

Руками не правятся: `.mise/locks/` (обновляется `mise lock`), `dist-exe/`,
`dist-full/`, `frontend/dist/`, `journal/`, `journal-dev/`, `static/` (данные
стенда). Они либо в `.gitignore`, либо пересоздаются установщиком.

## Как проверить, что гейт падает

Проверка, которую не видели падающей, не работает. На чистом дереве
`npm run gate:fast` даёт exit 0; по одному нарушению на каждый класс проверок —
exit 1. Быстрее — только упавший шаг: `npm run gate:fast -- --only ruff`.

```bash
# секрет: betterleaks (ключ генерируется на месте, в файле его нет)
KEY=$(python -c 'import secrets; print(secrets.token_urlsafe(24))')
printf 'aws_secret_access_key = "%s"\n' "$KEY" >> VERSION
npm run gate:fast          # betterleaks: leaks found: 1 → exit 1
git checkout -- VERSION

# формат: oxfmt
printf '\n|a|b|\n|-|-|\n|1|2|\n' >> CONTEXT.md
npm run gate:fast          # oxfmt: format issues found → exit 1
git checkout -- CONTEXT.md

# линтер: ruff
printf 'import os\n' >> backend/app/main.py
npm run gate:fast          # ruff: F401 → exit 1
git checkout -- backend/app/main.py

# workflow: jactionlint
printf 'bogus-key: true\n' >> .github/workflows/check.yml
npm run gate:fast          # jactionlint: unexpected key → exit 1
git checkout -- .github/workflows/check.yml

# типы: tsc
printf 'const broken: number = "no";\nconsole.log(broken);\n' >> frontend/src/main.tsx
npm run gate:fast          # tsc: Type 'string' is not assignable to type 'number' → exit 1
git checkout -- frontend/src/main.tsx
```

Эти пять нарушений проверены 2026-11-03 и записаны в
[`docs/quality/proven-checks.json`](quality/proven-checks.json) как рецепты
`steps`; полный прогон каждого — десятки секунд.
