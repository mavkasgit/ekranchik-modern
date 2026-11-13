# 0019 — Выпил: кроп, загрузка, создание, удаление и ZIP

Спека: [0002](../specs/0002-catalog.md). Идёт после
[0015](0015-catalog-api-read-only.md) и [0016](0016-catalog-screen-read-only.md).

## Задача

Убрать код, который обслуживал запись каталога. После перехода на витрину он
не вызывается, но тянет зависимости (Pillow), тесты и упоминания в
документации.

## Объём

### Backend

`backend/app/services/catalog_service.py`:

- удалить `generate_thumbnail`, `save_photo`, `update_thumbnail`,
  `delete_photo`, `delete_full_photo`, `delete_thumbnail`,
  `create_or_update_profile`, `update_profile`, `delete_profile`,
  `increment_usage` и мёртвые помощники (санитайзер имени, проверки путей,
  работа с файлами фото), если после удаления маршрутов на них никто не
  ссылается;
- оставить чтение профилей, `update_notes`, `photo_version` и поиск.

`backend/app/core/config.py` — удалить `MAX_UPLOAD_SIZE`, `THUMBNAIL_SIZE`,
если они больше не используются. `backend/requirements.txt` — убрать
`pillow` (единственное использование — генерация превью).

`backend/tests/unit/test_catalog_service.py` — удалить тесты загрузки,
кропа, удаления и переименования фото, которых больше нет; тесты
санитайзера имён уходят вместе с кодом.

### Frontend

`frontend/src/pages/Catalog.tsx`:

- убрать `photoMode`, `CropArea`, кроп мышью/тачем, режим «Редактирование
  превью», загрузку файлов, drag&drop и вставку из буфера, диалог удаления,
  создание/редактирование профиля, экспорт ZIP, плавающую кнопку «+»;
- убрать неиспользуемые импорты (иконки, компоненты формы).

`frontend/src/api/catalog.ts` — методы записи (см. 0016).

### Документация

README и `docs/` — убрать упоминания экспорта каталога, если остались.
`docs/dependabot.md` не трогать.

## Критерии готовности

1. `rg -n "кроп|CropArea|thumbnail|uploadPhoto|export/zip|Экспорт ZIP" frontend/src backend/app` не находит живого кода (совпадения в истории/тестах
   синка допустимы и перечислены в отчёте).
2. `pillow` отсутствует в `backend/requirements.txt`; `pip check` и запуск
   приложения проходят.
3. `mise run check` и `mise run test` зелёные; dev-стенд отдаёт каталог и
   фото.
