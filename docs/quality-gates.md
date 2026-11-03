# Проверки качества (quality gates)

Что и где проверяется, как это запустить и какие исключения уже зафиксированы.
Список инструментов взят из [dev-quality-gates](https://github.com/mokevnin/dev-quality-gates)
(adopt, 2026-11-03); версии пинятся в `mise.toml` + `mise.lock`.

## Команды

```bash
mise install       # поставить инструменты из mise.toml (та же версия, что в CI)
mise run hooks     # один раз на клон: поставить git-хуки hk
mise run check     # все проверки по всему проекту — то же, что запускает CI
mise run fix       # безопасные автофиксы (ruff, oxfmt, jactionlint); дифф перечитать
```

`mise run check` — агрегатная команда (`hk check --all`). Другого «полного»
способа нет: CI вызывает ровно её, поэтому хук и CI не расходятся.

## Три уровня

| Уровень      | Когда                             | Что запускается                                                                                                     |
| ------------ | --------------------------------- | ------------------------------------------------------------------------------------------------------------------- |
| `pre-commit` | `git commit`, только staged-файлы | ruff, oxfmt, oxlint, betterleaks, shellcheck, hadolint, jactionlint; форматтеры правят и докладывают файлы в индекс |
| `pre-push`   | `git push`, весь проект           | те же проверки + knip + `tsc --noEmit`                                                                              |
| CI           | push в `main`, PR, понедельник    | `mise run check`, backend pytest, frontend vitest, OSV-скан по расписанию                                           |

Хук — удобство, а не гейт: проверка, которая есть только в хуке, не enforced.
`commitlint` вызывается и из `commit-msg`, и в CI: в PR проверяется весь
диапазон `base..head`, при push в `main` — последний коммит. История до
внедрения гейта (2026-11-03) не переписана и служит бейзлайном.

## Что проверяется

| Инструмент  | Область                                     | Конфиг                     | Что ловит                                      |
| ----------- | ------------------------------------------- | -------------------------- | ---------------------------------------------- |
| Ruff        | `backend/**/*.py`, `scripts/**/*.py`        | `backend/ruff.toml`        | E4/E7/E9/F/I/UP/B/C4/SIM + формат              |
| Oxlint      | JS/TS/MTS                                   | `.oxlintrc.json`           | категория correctness, `no-unused-vars`        |
| oxfmt       | js/ts/md/yaml/toml/json/html/css            | `.oxfmtrc.json`            | формат (Prettier-совместимый)                  |
| Knip        | JS/TS                                       | `knip.json`                | неиспользуемые файлы, экспорты, зависимости    |
| TypeScript  | `frontend/**/*.{ts,tsx}`                    | `frontend/tsconfig.json`   | `tsc --noEmit`, `strict`                       |
| betterleaks | весь репозиторий                            | —                          | закоммиченные секреты                          |
| ShellCheck  | `**/*.sh`                                   | —                          | ошибки и переносимость shell                   |
| Hadolint    | `**/Dockerfile*`                            | `.hadolint.yaml`           | практики Dockerfile                            |
| jactionlint | `.github/workflows/*.yml`, `dependabot.yml` | `.github/jactionlint.yaml` | корректность, security и policy GitHub Actions |
| commitlint  | сообщения коммитов                          | `commitlint.config.js`     | Conventional Commits                           |
| OSV-Scanner | lock-файлы                                  | —                          | известные уязвимости (только по расписанию)    |

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
- **diff-cover** — покрытие тестами не гейтится: 218 backend-тестов уже есть,
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
`mise run check` даёт exit 0; по одному нарушению на каждый класс проверок —
exit 1:

```bash
# секрет: betterleaks (ключ генерируется на месте, в файле его нет)
KEY=$(python -c 'import secrets; print(secrets.token_urlsafe(24))')
printf 'aws_secret_access_key = "%s"\n' "$KEY" >> VERSION
mise run check          # betterleaks: leaks found: 1 → exit 1
git checkout -- VERSION

# формат: oxfmt
printf '\n|a|b|\n|-|-|\n|1|2|\n' >> CONTEXT.md
mise run check          # oxfmt: format issues found → exit 1
git checkout -- CONTEXT.md

# линтер: ruff
printf 'import os\n' >> backend/app/main.py
mise run check          # ruff: E402 → exit 1
git checkout -- backend/app/main.py

# workflow: jactionlint
printf 'bogus-key: true\n' >> .github/workflows/check.yml
mise run check          # jactionlint: unexpected key → exit 1
git checkout -- .github/workflows/check.yml

# типы: tsc
printf 'const broken: number = "no";\nconsole.log(broken);\n' >> frontend/src/main.tsx
mise run check          # tsc: Type 'string' is not assignable to type 'number' → exit 1
git checkout -- frontend/src/main.tsx
```

Эти пять нарушений проверены 2026-11-03; полный прогон каждого занимает
около 20 секунд.
