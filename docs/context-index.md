# Индекс контекста документации (Context Index)

В этом разделе собрана вся ключевая документация проекта **Ekranchik-Modern**. Используйте эту таблицу для быстрой навигации по архитектуре, установке, развертыванию и тестированию системы.

## Список документов

| Файл | Описание | Основные разделы |
| :--- | :--- | :--- |
| [project-overview.md](file:///c:/Users/user/VibeCoding/ekranchik-modern/docs/project-overview.md) | Общий обзор архитектуры проекта | Архитектура FastAPI бэкенда, React фронтенда, интеграция с OPC UA симулятором и реестр сетевых портов. |
| [GETTING_STARTED.md](file:///c:/Users/user/VibeCoding/ekranchik-modern/docs/GETTING_STARTED.md) | Руководство по быстрому старту для разработчиков | Установка зависимостей, настройка окружения, запуск в режиме разработки, скрипты `package.json`. |
| [deployment.md](file:///c:/Users/user/VibeCoding/ekranchik-modern/docs/deployment.md) | Руководство по развертыванию на сервере | Переменные окружения, настройка systemd-сервисов, запуск GUI-симулятора через Xvfb в безэкраном режиме. |
| [testing-guide.md](file:///c:/Users/user/VibeCoding/ekranchik-modern/docs/testing-guide.md) | Руководство по тестированию системы | Запуск бэкенд-тестов (pytest), фронтенд-тестов (vitest) и сквозных тестов (Playwright с CDP). |
| [agents.md](file:///c:/Users/user/VibeCoding/ekranchik-modern/docs/agents.md) | Руководство для AI-субагентов | Список доступных субагентов, таблица портов, правила делегирования и управление симулятором OPC UA. |

## Связанные системные файлы и конфигурации
* [package.json](file:///c:/Users/user/VibeCoding/ekranchik-modern/package.json) — корневой конфигурационный файл npm и скрипты запуска.
* [backend/.env.example](file:///c:/Users/user/VibeCoding/ekranchik-modern/backend/.env.example) — пример конфигурации переменных окружения для бэкенда.
* [playwright.config.ts](file:///c:/Users/user/VibeCoding/ekranchik-modern/playwright.config.ts) — конфигурация Playwright для сквозного тестирования.
