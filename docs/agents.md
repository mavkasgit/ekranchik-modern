# Справочник AI-субагентов и Управления (Agents & Ports Registry) — Экранчик

Этот документ предназначен для разработчиков и AI-субагентов, работающих с проектом **Ekranchik-Modern**. Он описывает структуру агентов, сетевые порты и правила взаимодействия с симулятором OPC UA.

## 1. Реестр AI-субагентов

В проекте используется семейство специализированных агентов, чьи инструкции хранятся в каталоге [.agents/](file:///c:/Users/user/VibeCoding/ekranchik-modern/.agents):

| Имя агента | Файл роли | Основная специализация |
| :--- | :--- | :--- |
| **Browser Checker** | [browser-checker.md](file:///c:/Users/user/VibeCoding/ekranchik-modern/.agents/browser-checker.md) | Тестирование верстки в браузере, проверка UI-элементов. |
| **Docs Maintainer** | [docs-maintainer.md](file:///c:/Users/user/VibeCoding/ekranchik-modern/.agents/docs-maintainer.md) | Поддержание актуальности документации и комментариев. |
| **HTML Designer** | [html-designer.md](file:///c:/Users/user/VibeCoding/ekranchik-modern/.agents/html-designer.md) | Верстка, дизайн-система, работа с Tailwind CSS и стилями. |
| **Server Deployer** | [server-deployer.md](file:///c:/Users/user/VibeCoding/ekranchik-modern/.agents/server-deployer.md) | Настройка systemd-сервисов, конфигурирование окружения. |
| **Server Operator** | [server-operator.md](file:///c:/Users/user/VibeCoding/ekranchik-modern/.agents/server-operator.md) | Мониторинг бэкенда, чтение системных журналов и логов. |
| **SFTP Operator** | [sftp-operator.md](file:///c:/Users/user/VibeCoding/ekranchik-modern/.agents/sftp-operator.md) | Загрузка файлов на сервер, синхронизация каталогов. |
| **Test Fixer** | [test-fixer.md](file:///c:/Users/user/VibeCoding/ekranchik-modern/.agents/test-fixer.md) | Поиск ошибок в сломанных unit и integration тестах бэкенда. |
| **Test Runner** | [test-runner.md](file:///c:/Users/user/VibeCoding/ekranchik-modern/.agents/test-runner.md) | Оркестрация и запуск тестов pytest, vitest и Playwright. |

---

## 2. Реестр сетевых портов и сетевые режимы

Приложение поддерживает два параллельных режима доступа к портам:

1. **Режим общей сети (shared_gateway)**: Маршрутизация через порт **80/443**.
2. **Автономный режим**: Прямой доступ по выделенным портам для каждого проекта.

| Порт | Назначение / Окружение | Автономный доступ | Сетевой доступ |
|---|---|---|---|
| **5173** | Frontend (React dev server) | dev | — |
| **8000** | Backend API (FastAPI) | dev | — |
| **4840** | OPC UA Simulator / Server | dev / prod | — |
| **8081** | Nginx entrypoint (HRMS) | `http://localhost:8081` | `http://<domain>/` (порт 80) |
| **8082** | Nginx entrypoint (KTM-2000) | `http://localhost:8082` | `http://<domain>/` (порт 80) |
| **8083** | Nginx entrypoint (Экранчик) | `http://localhost:8083` | `http://<domain>/` (порт 80) |
| **9222** | Chrome CDP (отладка) | dev (тестирование) | — |

---

## 3. Правила делегирования задач субагентам

При распределении задач между субагентами следуйте правилам:
1. **Тестирование UI**: Передавать задачу [Browser Checker](file:///c:/Users/user/VibeCoding/ekranchik-modern/.agents/browser-checker.md) только после успешного запуска бэкенда и фронтенда.
2. **Правка багов в коде**: Если падают pytest-тесты бэкенда, сразу привлекайте [Test Fixer](file:///c:/Users/user/VibeCoding/ekranchik-modern/.agents/test-fixer.md).
3. **Обновление док-файлов**: Любое изменение API или структуры базы данных должно сопровождаться делегированием к [Docs Maintainer](file:///c:/Users/user/VibeCoding/ekranchik-modern/.agents/docs-maintainer.md).
4. **Деплой**: Все скрипты деплоя и настройки systemd поручать [Server Deployer](file:///c:/Users/user/VibeCoding/ekranchik-modern/.agents/server-deployer.md).

---

## 4. Управление симулятором OPC UA

Симулятор [opcua_server_simulator.py](file:///c:/Users/user/VibeCoding/ekranchik-modern/backend/opcua_server_simulator.py) имитирует работу реальных тегов КПЗ:
* **Температура камер** (теги: `Temperature_Chamber1`, `Temperature_Chamber2`)
* **Давление** (тег: `Pressure`)
* **Концевые датчики дверей** (теги: `Door_Closed_1`, `Door_Closed_2`)
* **Статусы вешал** (теги: `Hanger_Attached_1`, `Hanger_Attached_2`)

### Изменение значений тегов вручную через GUI
Для изменения значений вы можете использовать интерфейс Tkinter. Ползунки и кнопки позволяют мгновенно менять числовые или булевы значения тегов в работающем сервере OPC UA.

### Автоматизированное управление тегами из тестов
В интеграционных тестах вы можете подключаться к OPC-серверу на порту `4840` как клиент и перезаписывать значения тегов напрямую:
```python
from asyncua import Client

async with Client("opc.tcp://127.0.0.1:4840/freeopcua/server/") as client:
    temp_node = await client.get_node("ns=2;i=2")
    await temp_node.write_value(85.5)
```
Это позволяет симулировать различные аварийные и рабочие ситуации при автоматическом прогоне E2E тестов.
