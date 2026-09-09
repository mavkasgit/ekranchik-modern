# Разовый перенос данных: Docker-прод → заводская машина (All-in-One)

Разовая процедура переноса накопленных данных с текущего Docker-прода
на заводскую машину с полным режимом All-in-One без Docker (ADR 0002:
`docs/adr/0002-full-mode-all-in-one-without-docker.md`, issue #7).

После переноса машины живут независимо — **дальнейшей синхронизации нет**.
Повторный перенос (если понадобится) = повторить эту же процедуру,
он перезапишет данные на заводской машине. От настроек All-in-One
(#4, `launcher/...AllInOne`) процедура не зависит.

## 1. Что переносим, а что — нет

| Артефакт | Переносим | Почему |
|---|---|---|
| `ekranchik.db` (SQLite) | Да | Все учётные данные |
| `images/` (фото профилей + `*-thumb.jpg`) | Да | Без них дашборд без картинок |
| `active_excel*.json`, `app_settings.json` | Нет | Содержат пути исходной машины (контейнерные `/app/excel/...`, dev-пути); на заводской машине Excel и настройки задаются через All-in-One (#4) |
| `profiles.db` | Нет | Legacy-файл, бэкендом не используется |
| `backend/.env` | Нет | Dev-конфиг, в пакет не входит (см. `scripts/build-full-package.ps1`) |

## 2. Где взять файлы на сервере (сверено с compose/env)

`infra/compose/docker-compose.prod.yml` монтирует хост-каталог в контейнер
и перекрывает dev-значения `backend/.env` своим `environment`:

```yaml
environment:
  - DATABASE_URL=sqlite+aiosqlite:////app/static/ekranchik.db  # стр. 18
  - STATIC_DIR=/app/static                                      # стр. 19
  - IMAGES_DIR=/app/static/images                               # стр. 20
volumes:
  - ../../static:/app/static                                    # стр. 28
```

Значения `backend/.env` (`DATABASE_URL=sqlite+aiosqlite:///../static/ekranchik.db`,
`IMAGES_DIR=../static/images`) в проде **не действуют** — их перекрывает
`environment` compose-файла (env-файл подключается через `env_file`, но
`environment` имеет приоритет). Итог: данные лежат в хост-каталоге репозитория
на сервере (пути относительно корня checkout'а):

- БД: `<repo>/static/ekranchik.db` (в контейнере `/app/static/ekranchik.db`)
- Фото: `<repo>/static/images/` (в контейнере `/app/static/images`)

## 3. Куда положить на заводской машине

`backend/app/core/config.py` (`default_data_dir` + `_apply_full_mode_defaults`):
без явных `DATABASE_URL`/`IMAGES_DIR` данные уходят в каталог полного режима —
`%LOCALAPPDATA%\Ekranchik\data` (порту `8083` пакет `scripts/build-full-package.ps1`
`.env` не содержит, так что действуют именно дефолты). Каталоги создаются сами
при старте (`ensure_data_dirs`), миграции — `alembic upgrade head` из lifespan.
Раскладка после переноса:

- `%LOCALAPPDATA%\Ekranchik\data\ekranchik.db`
- `%LOCALAPPDATA%\Ekranchik\data\images\`

## 4. Порядок действий

На **сервере** (каталог checkout'а репозитория):

1. Остановить прод-бэкенд, чтобы SQLite-копия была консистентной
   (копировать БД под записью нельзя):
   `docker compose -f infra/compose/docker-compose.prod.yml stop backend`
2. Скопировать `<repo>/static/ekranchik.db` и `<repo>/static/images/`
   на заводскую машину (любым способом: USB, сеть).
   Удобно скриптом из п. 5 — он же делает проверки.
3. Поднять прод обратно:
   `docker compose -f infra/compose/docker-compose.prod.yml up -d backend`

На **заводской машине**:

4. Убедиться, что All-in-One / бэкенд остановлены (не класть БД поверх
   запущенного процесса — скрипт без `-Force` откажется это делать).
5. Разложить файлы:
   `powershell -ExecutionPolicy Bypass -File scripts/copy-prod-data.ps1
     -SourceDb <путь>\ekranchik.db -SourceImages <путь>\images`
   (без параметров скрипт берёт `static/ekranchik.db` и `static/images`
   рядом с репозиторием и кладёт в `%LOCALAPPDATA%\Ekranchik\data`).
6. Запустить All-in-One. Миграции применятся автоматически при старте.

## 5. Скрипт

`scripts/copy-prod-data.ps1` — рядом со `scripts/build-full-package.ps1`.
Проверяет: источник БД и `images/` существуют, целевой каталог создаётся,
цель не занята запущенным процессом (`EkranchikAllInOne` запущен или файл
целевой БД заблокирован — без `-Force` отказ с требованием остановить
бэкенд). Поддерживает `-WhatIf` для сухого прогона. `backend/.env`
скрипт никогда не копирует.

## 6. Проверка после переноса

1. Дашборд открывается: `http://localhost:8083`, данные (подвесы, смены,
   остатки) совпадают с продом на момент остановки из п. 1.
2. Картинки видны: фото профилей на дашборде грузятся (признак, что легли
   `%LOCALAPPDATA%\Ekranchik\data\images\`, а не только БД).
3. Перезапуск All-in-One не теряет данные (лежат вне пакета, переживают
   переустановку).
