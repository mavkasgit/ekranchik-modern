# 0015 — API каталога: только чтение и примечание

Спека: [0002](../specs/0002-catalog.md). Решение:
[ADR 0010](../adr/0010-catalog-is-read-only-showcase.md).

## Задача

Закрыть каталог на запись: данные артикула принадлежат каталогу-источнику,
локально меняется только примечание. Добавить `description` (наименование) в
ответ и миграцию под него. Убрать из ответа мёртвые `usage_count` и
`similarity`.

## Объём

### Модель и миграция

`backend/app/db/models.py` — `Profile.description: str | None`,
`String(500)`, nullable.

`backend/alembic/versions/002_add_profile_description.py` — `add_column`;
downgrade — `drop_column` через `batch_alter_table` (SQLite).

`backend/app/schemas/profile.py` — `description` в `ProfileResponse`;
`usage_count` из ответа убрать. `ProfileSearchResult` без изменений
(эндпоинт поиска остаётся как API).

### Маршруты

`backend/app/api/routes/catalog.py`:

- удалить `POST /catalog`, `PUT /catalog/{id}`, `DELETE /catalog/{id}`,
  `POST /catalog/{name}/photo`, `PUT /catalog/{name}/thumbnail`,
  `DELETE /catalog/{name}/photo`, `DELETE /catalog/{name}/photo/full`,
  `DELETE /catalog/{name}/photo/thumbnail`, `GET /catalog/export/zip`;
- добавить `PATCH /catalog/{profile_id}/notes` (`ProfileNotesUpdate`,
  `notes` ≤ 2000, `None`/`""` очищает);
- `GET /catalog`, `GET /catalog/all`, `GET /catalog/{name}` не меняются по
  смыслу; `description` добавляется в ответ.

`backend/app/services/catalog_service.py` — метод `update_notes`, удаление
`create_or_update_profile`, `update_profile`, `delete_profile`, работы с
фото и ZIP (мёртвые помощники дочищаются в [0019](0019-remove-catalog-writes.md)).
`increment_usage` удалить: вызовов нет.

### Тесты

- `backend/tests/integration/test_catalog_api.py`:
  - `GET /all` отдаёт `description`, не отдаёт `usage_count`;
  - write-маршруты отвечают 404/405;
  - `PATCH /notes` — 200, 404 (нет артикула), 422 (> 2000);
  - `PATCH /notes` не меняет `length`, `quantity_per_hanger`, `description`,
    фото и `name`.
- Проверить, что `alembic upgrade head` на копии dev-БД добавляет колонку и
  приложение стартует.

## Проверка

1. `mise run check` и `mise run test`.
2. Запустить стенд, открыть `/docs`: из каталога остались чтение и
   `PATCH /notes`.
3. `curl` по удалённым маршрутам — 404/405, примечание сохраняется и видно в
   `GET /catalog/{name}`.
