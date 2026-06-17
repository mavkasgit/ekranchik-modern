# Руководство по тестированию (Testing Guide)

Проект **Ekranchik-Modern** покрыт тестами на всех уровнях: юнит-тестирование бэкенда, компонентное тестирование фронтенда и сквозное (E2E) тестирование веб-интерфейса.

---

## 1. Тестирование Бэкенда (pytest)

Бэкенд использует фреймворк **pytest** для запуска тестов. Файлы тестов расположены в каталоге [backend/tests](file:///c:/Users/user/VibeCoding/ekranchik-modern/backend/tests).

### Конфигурация
Настройки тестирования определены в файле [backend/pytest.ini](file:///c:/Users/user/VibeCoding/ekranchik-modern/backend/pytest.ini).

### Запуск тестов
1. Перейдите в каталог бэкенда и активируйте виртуальное окружение:
   ```powershell
   cd backend
   .\venv\Scripts\Activate.ps1
   ```
2. Запустите тесты командой:
   ```bash
   pytest
   ```
3. Для получения подробного вывода логов или конкретного теста:
   ```bash
   pytest -v
   pytest tests/unit/test_opcua.py
   ```

---

## 2. Тестирование Фронтенда (vitest)

Фронтенд использует **Vitest** в качестве тестового фреймворка, так как он отлично интегрирован с Vite.

### Запуск тестов
1. Перейдите в каталог фронтенда:
   ```bash
   cd frontend
   ```
2. Выполните скрипт запуска тестов:
   ```bash
   npm run test
   ```
   Эта команда запустит Vitest в интерактивном (watch) режиме.
3. Для одиночного прогона тестов (например, в CI/CD):
   ```bash
   npx vitest run
   ```

---

## 3. Сквозное тестирование (E2E Playwright с поддержкой CDP)

Сквозные тесты автоматизируют действия пользователя в браузере и проверяют работоспособность всей цепочки: Frontend -> Backend -> OPC UA Simulator -> Excel.

Для обхода проблем с запуском браузеров на изолированных серверах и повышения скорости отладки используется **Chrome DevTools Protocol (CDP)**.

### Что такое CDP-режим в тестах?
В режиме CDP (`E2E_BROWSER_MODE=cdp` в настройках) Playwright не запускает собственный изолированный экземпляр браузера, а подключается по порту отладки (по умолчанию `9222`) к уже запущенному процессу Google Chrome. Это позволяет:
* Проходить тесты в том же окне браузера, где ведется разработка.
* Сохранять сессии авторизации и куки.
* Проводить визуальную отладку без перезапуска браузера на каждый тест.

### Подготовка Chrome к работе по CDP
Чтобы Chrome принимал входящие соединения отладки, его нужно запустить со специальным флагом:
```bash
# Windows
"C:\Program Files\Google\Chrome\Application\chrome.exe" --remote-debugging-port=9222 --user-data-dir="C:\Temp\ChromeDevProfile"

# Linux
google-chrome --remote-debugging-port=9222 --user-data-dir=/tmp/chrome-profile
```

### Настройка и Запуск E2E
Параметры подключения к CDP задаются в конфигурационном файле [playwright.config.ts](file:///c:/Users/user/VibeCoding/ekranchik-modern/playwright.config.ts) и файле окружения `.env` в корне проекта.

Запуск тестов осуществляется из корня проекта:
```bash
# Установка Playwright (при первом запуске)
npx playwright install chromium

# Запуск тестов
npx playwright test
```
Тесты будут использовать фикстуру `connectedPage` из [e2e/fixtures.ts](file:///c:/Users/user/VibeCoding/ekranchik-modern/e2e/fixtures.ts), автоматически определяющую режим подключения (CDP или стандартный headless/headed).
