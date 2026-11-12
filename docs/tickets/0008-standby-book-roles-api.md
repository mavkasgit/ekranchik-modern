# 0008 — Роли книг: хранение, API, статус, журнал

Спека: [0001](../specs/0001-standby-book.md). Решение: [ADR 0009](../adr/0009-standby-book-follows-growing-rows.md).
Блокирует: 0009, 0010.

## Задача

Дать книге учёта две роли — основная и запасная — и сделать так, чтобы все
поверхности называли одну читаемую книгу (ADR 0003).

## Объём

### `backend/app/services/excel_service.py`

- Файл выбора хранит `active_file`, `main_file`, `reserve_file` одной записью.
  Старый формат (только `active_file`) читается: основная = `active_file`,
  запасная пуста.
- Свойства: `main_path`, `reserve_path`, `reserve_file_name`, `main_file_name`,
  `current_role` (`main`/`reserve`/`None`), `count_book_rows(path)`.
- `set_book_roles(main, reserve)` — задаёт роли; активную книгу сбрасывает на
  основную только если прежний выбор выпал из ролей.
- `set_main_file(path)` — прежний вход выбора: книга становится основной и
  читается сейчас; запасная, совпавшая с ней, сбрасывается.
- `count_book_rows` считает записанные проходы — строки, где есть время и номер
  подвеса (уточнено в [0014](0014-standby-counts-passes.md): шаблон смены внизу
  книги не в счёт); свой кэш по `(путь, mtime_ns, size)`, чтобы не вытеснять
  основной кэш; `None` — не прочитать.

### `backend/app/api/routes/dashboard.py`, `backend/app/schemas/dashboard.py`

- `POST /api/dashboard/excel/books` по контракту спеки. Проверки книги общие с
  `/excel/select`: существование, файл, расширение, подсказка про шару.
- `/excel/select` переводится на `set_main_file`; запасная, равная новой
  основной, сбрасывается.
- `FileStatus`: `role`, `main_file_path`, `reserve_file_path`,
  `main_last_growth`.
- `SettingsResponse`: `excel_reserve_path`, `excel_role`.
- После сохранения ролей и выбора — сброс памяти правила (0009) и рассылка WS.

### `backend/app/services/journal_writer.py`

- В каждую новую запись добавляются `book_name` и `book_path`; старые записи
  читаются без них.

## Тесты

- `tests/unit/test_excel_active_file.py`: формат файла выбора с ролями; старая
  запись без ролей → основная = `active_file`.
- `tests/integration/test_excel_books_api.py`: сохранение ролей, отказ при
  совпадении путей, отказ при пропавшей книге, сброс запасной пустым
  `reserve_path`, статус и настройки называют ту же книгу.
- `tests/integration/test_excel_active_book_api.py` остаётся зелёным (три
  поверхности называют один файл).
- `tests/test_journal_writer.py`: в записи есть `book_name`/`book_path`.
- `tests/unit/test_excel_backup.py`: при активной запасной книге копия идёт в
  `<имя запасной>_backup` в том же корне, что и копии основной
  (`backup_dir_for` вызывается от активного пути, не от основной роли).

## Приёмка

`cd backend && mise exec -- python -m pytest tests/unit/test_excel_active_file.py tests/integration/test_excel_books_api.py tests/integration/test_excel_active_book_api.py tests/test_journal_writer.py`
зелёный; `ruff check` по изменённым файлам.
