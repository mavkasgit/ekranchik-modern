# 0004 — Выбор книги учёта: пикер уходит, файл выбора становится своим у каждой среды

Задача: убрать из дашборда список файлов (пикер), оставив выбор только вводом
пути, и развести память о выбранном пути у dev и прод-контейнера. Правки в
путях, сделанные по ходу разбора аварии (чужой путь не подменяет книгу,
корневой путь не приклеивается к каталогу книги), остаются как есть.

## Проблема

1. **Пикер дублировал ввод пути.** «Сменить» → «Выбрать файл на сервере...»
   открывал список папок и файлов (`GET /api/dashboard/excel/files`), а рядом
   была кнопка «Ввести путь» с тем же результатом. Список тянул за собой
   навигацию по папкам, отдельное окно, свои состояния и свой API — ради того,
   что уже умеет одна строка с путём.

2. **`static/active_excel.json` был один на две среды.** Каталог `static`
   у dev-бэкенда (`STATIC_DIR=../static`) и у прод-контейнера
   (`/app/static`) — это один и тот же каталог репозитория. На машине, где
   рядом живут dev и локальный прод, выбранный в одной среде путь попадал в
   другую: контейнер писал `/app/excel/Учет КПЗ 2026.xlsm`, dev читал его и
   показывал склейку с сетевой шарой
   `\\172.17.11.7\Оператор\app\excel\Учет КПЗ 2026.xlsm` — путь, которого нет,
   и «Файл не найден» при живой книге на диске.

## Что остаётся без изменений

- **`POST /api/dashboard/excel/select` и кнопка «Ввести путь»** — единственный
  способ выбрать книгу из интерфейса.
- **`active_excel.json`** — память о последнем введённом пути (имя файла
  задаётся конфигурацией, см. ниже).
- Уже сделанные исправления путей: чужой путь не подменяет книгу (откат на
  путь из конфигурации с предупреждением в лог), корневой путь
  (`/app/excel/…`, `\\host\share\…`, `Z:\…`) не приклеивается к каталогу
  книги, защищённый `path_exists` (EINVAL на чужом пути в Linux — не 500),
  `share_tail`, `normalize_path_input` (кавычки и пробелы вокруг пути).
- Предупреждение о пустом каталоге книги при старте (`app/main.py`): пустой
  каталог — это несмонтированный сетевой диск, а не «файл не найден».
- Тесты `backend/tests/unit/test_excel_paths.py`,
  `backend/tests/unit/test_excel_active_file.py`,
  `backend/tests/integration/test_excel_select_api.py` — из последнего
  убираются только кейсы про `/files`.

## Что убираем (только пикер)

**Бэкенд**

- `GET /api/dashboard/excel/files` (`backend/app/api/routes/dashboard.py`).
- Схемы `ExcelFileInfo`, `ExcelFileListResponse` (`app/schemas/dashboard.py`).
- `ExcelService.directory` (`app/services/excel_service.py`) — **остаётся**:
  кроме списка файлов её используют `_resolve_book_file` и ветка
  `file_name` в выборе пути (`backend/app/api/routes/dashboard.py:320, 343, 381`).
  Уходит только вызов из `/excel/files` (строка 234), свойство остаётся
  владельцем правила «каталог книги».
- `GET /excel/files` из README и из разделов про выбор книги.

**Фронтенд**

- Список папок и файлов (окно «Книга учёта на сервере»), кнопка «Сменить» с
  меню истории и `localStorage` недавних путей.
- `dashboardApi.getExcelFiles` и типы `ExcelFilesResponse`, `ExcelFileInfo`
  (`frontend/src/api/dashboard.ts`, `frontend/src/types/dashboard.ts`) — вместе
  с `ExcelSelectResponse`, если по нему не остаётся вызовов
  (ввод пути использует `selectExcelFile`, он остаётся).
- Кейсы и абзацы про `/files` в `test_excel_select_api.py` и README.

Поле ввода пути, окно «Ввод пути к Excel файлу» и статус-строка (имя книги,
статус, полный путь сервера read-only) остаются как есть.

## Разводим dev и прод по файлам выбора

- Имя файла выбора берётся из переменной окружения
  **`EXCEL_ACTIVE_FILE_NAME`**; по умолчанию `active_excel.json` — dev не
  меняется.
- Суффикс режима симуляции сохраняется: при `SIMULATION_ENABLED=true` в имя
  вставляется `_sim` перед расширением (`active_excel_prod.json` →
  `active_excel_prod_sim.json`).
- `infra/compose/docker-compose.prod.yml` задаёт
  `EXCEL_ACTIVE_FILE_NAME=active_excel_prod.json`: контейнер пишет в свой файл,
  чужой путь туда больше не попадает.
- Правка одна — `ExcelService._persistence_path`
  (`backend/app/services/excel_service.py`); имя берётся из настроек, а не
  хардкодится.
- `active_excel_prod.json` добавить в `.gitignore` рядом с
  `static/active_excel.json`.

## Тесты

- Новый: при заданном `EXCEL_ACTIVE_FILE_NAME` выбор пишется в файл с этим
  именем и не трогает `active_excel.json`; при симуляции — в `_sim`-вариант.
- Существующие `test_excel_paths.py` и `test_excel_active_file.py` остаются
  зелёными.
- `test_excel_select_api.py` — без кейса про `/files`; добавить, что
  `GET /api/dashboard/excel/files` отдаёт 404.

## Проверка

1. `pytest` (весь `backend/tests`), `tsc -b`, `vitest`.
2. Пересборка контейнера:
   `docker compose -f docker-compose.prod.yml -f docker-compose.prod.local.yml up -d --build backend`.
3. В прод-дашборде (`http://172.17.11.9:8083`): ввести путь в «Ввести путь»,
   перезапустить контейнер и убедиться, что путь сохранился — в
   `static/active_excel_prod.json`; `static/active_excel.json` при этом не
   меняется.
4. Кнопки «Сменить» в дашборде нет, `GET /api/dashboard/excel/files` → 404.
5. Перезапустить `npm run dev`, чтобы dev-бэкенд подхватил новый код (uvicorn
   без `--reload`).

## Перед началом

Закоммитить или убрать в stash текущие правки `frontend/src/pages/Dashboard.tsx`,
`frontend/src/components/HangerTracking.tsx`,
`frontend/src/components/prototype/ActiveHangersPrototype.tsx`: во фронтенде
трогаем только пикер.

## Что стоит знать до правки

- У прода после разделения нет своего файла выбора, поэтому первым делом он
  берёт книгу из `EXCEL_REAL_FILE_PATH` (в контейнере —
  `/app/excel/Учет КПЗ 2026.xlsm`). Если нужна другая книга — введите путь
  один раз заново.
- Контейнер видит только смонтированную папку `/app/excel`: путь
  `\\172.17.11.7\Оператор\...` он сопоставит с ней, а произвольный
  Windows-диск не откроет.

## Не в объёме

- Полное удаление механизма выбора (файл, `POST /excel/select`, кнопка в
  интерфейсе) — рассмотренный и отклонённый вариант: путь книги менялся бы
  только правкой конфигурации, а оператору пришлось бы ждать перезапуска.
