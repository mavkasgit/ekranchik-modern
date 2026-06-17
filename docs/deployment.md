# Руководство по развертыванию (Deployment Guide) — Экранчик

В этом документе описаны требования и процесс развертывания проекта **Ekranchik-Modern** на сервере в виде системных служб `systemd` и через `Docker Compose`.

## Сетевые режимы работы (Порты)

Проект поддерживает два параллельных режима сетевого доступа:

1. **Режим единой общей сети (порт 80 / 443)**:
   - Контейнеры подключаются к внешней сети `shared_gateway`.
   - Запросы маршрутизируются через центральный обратный прокси на порту 80/443 (используя имена хостов контейнеров, такие как `ekranchik-nginx-prod`).

2. **Автономный режим (прямой доступ)**:
   - Доступ к Экранчику осуществляется напрямую через порт хоста **8083** (проброшен в `docker-compose.prod.yml` на порт Nginx).
   - В системе также параллельно работают `hrms` (на порту **8081**) и `ktm2000` (на порту **8082**).

---

## Переменные окружения (Environment Variables)

Бэкенд конфигурируется через файл `.env` в папке `backend/`. Основные параметры:

| Переменная | Описание | Значение по умолчанию / Пример |
| :--- | :--- | :--- |
| `ENVIRONMENT` | Окружение запуска | `production` / `development` |
| `DEBUG` | Флаг отладки (вывод подробных логов) | `false` / `true` |
| `HOST` | IP-адрес для привязки FastAPI | `0.0.0.0` (все интерфейсы) |
| `PORT` | Порт FastAPI | `8000` |
| `DATABASE_URL` | Строка подключения к SQLite | `sqlite+aiosqlite:///../static/ekranchik.db` |
| `CORS_ORIGINS` | Разрешенные источники для запросов (JSON-массив) | `["http://localhost:3000", "http://localhost:5173"]` |
| `SIMULATION_ENABLED`| Переключатель режима (true = симулятор, false = рабочий) | `false` (в продакшене) |
| `OPCUA_ENDPOINT` | Эндпоинт реального OPC UA сервера КПЗ | `opc.tcp://172.17.11.115:4840/` |
| `OPCUA_SIM_ENDPOINT`| Эндпоинт симулятора OPC UA | `opc.tcp://127.0.0.1:4840/freeopcua/server/` |

---

## Важный нюанс: Запуск симулятора на Headless-сервере (Edge Case)

Симулятор OPC UA (`opcua_server_simulator.py`) построен с использованием графической библиотеки **Tkinter**. На безэкрановом сервере Linux для обхода ошибки дисплея используйте `Xvfb` (X Virtual Frame Buffer):

1. Установите необходимые пакеты:
   ```bash
   sudo apt-get update
   sudo apt-get install -y xvfb python3-tk
   ```
2. Используйте утилиту `xvfb-run` для запуска симулятора:
   ```bash
   xvfb-run --server-args="-screen 0 1024x768x24" python opcua_server_simulator.py
   ```

---

## Вариант A. Нативное развертывание (systemd)

Настройте службы `systemd` для фоновой работы:

### 1. Бэкенд (`/etc/systemd/system/ekranchik-backend.service`)
```ini
[Unit]
Description=Ekranchik Modern Backend Service
After=network.target

[Service]
Type=simple
User=deploy
WorkingDirectory=/home/deploy/ekranchik-modern/backend
EnvironmentFile=/home/deploy/ekranchik-modern/backend/.env
ExecStart=/home/deploy/ekranchik-modern/backend/venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8000
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

### 2. Симулятор OPC UA (`/etc/systemd/system/ekranchik-simulator.service`)
```ini
[Unit]
Description=Ekranchik Modern OPC UA Simulator
After=network.target

[Service]
Type=simple
User=deploy
WorkingDirectory=/home/deploy/ekranchik-modern/backend
ExecStart=/usr/bin/xvfb-run --auto-servernum --server-args="-screen 0 1024x768x24" /home/deploy/ekranchik-modern/backend/venv/bin/python opcua_server_simulator.py
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

---

## Вариант B. Развертывание через Docker Compose

Для запуска в контейнерах:
```bash
cd infra/compose
docker compose -f docker-compose.prod.yml up -d --build
```
Это запустит бэкенд, фронтенд и Nginx, пробросив порт **8083** на хост и подключив контейнеры к общей сети `shared_gateway`.
