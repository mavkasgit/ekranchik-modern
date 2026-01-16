# OPC UA Service

## Конфигурация

```env
# backend/.env
OPCUA_ENABLED=True
OPCUA_ENDPOINT=opc.tcp://172.17.11.131:4840/
OPCUA_POLL_INTERVAL=5
```

## Использование

```python
from app.services.opcua_service import opcua_service

# Подключение
await opcua_service.connect()

# Чтение одного узла
value = await opcua_service.read_node("ns=2;s=MyVariable")

# Чтение нескольких узлов (1-10)
results = await opcua_service.read_nodes(["ns=2;s=Var1", "ns=2;s=Var2"])

# Пакетное чтение (>10 узлов)
results = await opcua_service.read_nodes_batch(node_ids)

# Диагностика
diagnostics = opcua_service.get_diagnostics()
```

## API Endpoints

| Endpoint | Описание |
|----------|----------|
| `GET /api/opcua/status` | Статус подключения |
| `GET /api/opcua/diagnose` | Полная диагностика |
| `POST /api/opcua/connect` | Подключиться |
| `POST /api/opcua/disconnect` | Отключиться |
| `GET /api/opcua/line/status` | Статус всех ванн |

## Диагностика Проблем

### Быстрая проверка

```bash
# 1. Проверить доступность хоста
ping 172.17.11.131

# 2. Проверить порт
nc -zv 172.17.11.131 4840

# 3. Проверить API
curl http://localhost:8000/api/opcua/diagnose
```

### Типичные Ошибки

| Ошибка | Причина | Решение |
|--------|---------|---------|
| Connection timeout | Сервер недоступен | Проверить IP, firewall, сеть |
| Connection refused | Сервер не запущен | Запустить OPC UA сервер |
| BadSessionIdInvalid | Сессия истекла | Автоматическое переподключение |
| Error in watchdog loop | Сервер зависает | Перезагрузить сервер |

### Проверка на сервере OPC UA

```bash
# Проверить процесс
ps aux | grep opcua

# Проверить порт
netstat -an | grep 4840
```

## Архитектура

### Обработка ошибок

- **Ошибки сессии** (`BadSessionIdInvalid`) → жесткий сброс без отключения
- **Ошибки соединения** → попытка корректного отключения
- **Ошибки узлов** → добавление в черный список
- **Таймауты** → жесткий сброс

### Таймауты

```python
client = Client(endpoint, timeout=30)  # Запрос: 30 сек
client.session_timeout = 60000         # Сессия: 60 сек
client.secure_channel_timeout = 3600000  # Канал: 1 час
```

### Экспоненциальная задержка

При переподключении: 2s → 4s → 8s → 16s → 32s → 60s (макс)

### Кеширование

- TTL: 10 секунд
- Черный список для проблемных узлов
- Автоматическая очистка при переподключении

## Мониторинг

```python
diagnostics = opcua_service.get_diagnostics()
# {
#   'connected': True,
#   'state': 'connected',
#   'reconnect_attempts': 0,
#   'blacklisted_nodes': 0,
#   'cached_nodes': 15,
#   'stats': {'connections': 1, 'reads': 100, 'errors': 0, 'cache_hits': 50},
#   'metrics': {...}  # Детальные метрики
# }
```

## Метрики Подключения

Для диагностики проблем со стабильностью добавлены детальные метрики:

### API Endpoint

```bash
curl http://localhost:8000/api/opcua/metrics
```

### Доступные метрики

| Метрика | Описание |
|---------|----------|
| `connects.total` | Общее количество подключений |
| `connects.avg_ms` | Среднее время подключения |
| `connects.p95_ms` | 95-й перцентиль времени подключения |
| `disconnects.total` | Общее количество отключений |
| `reads.avg_ms` | Среднее время чтения узла |
| `reads.p95_ms` | 95-й перцентиль времени чтения |
| `errors.total` | Общее количество ошибок |
| `errors.timeouts` | Количество таймаутов |
| `errors.session_errors` | Количество ошибок сессии |
| `session.current_uptime_seconds` | Текущее время работы сессии |
| `session.longest_session_seconds` | Самая длинная сессия |
| `network.last_ping_ms` | Последний ping до сервера |
| `network.avg_ping_ms` | Средний ping |

### Пример ответа

```json
{
  "connected": true,
  "state": "connected",
  "current_ping_ms": 2.5,
  "metrics": {
    "connects": {"total": 5, "avg_ms": 1250.0, "p95_ms": 2100.0},
    "disconnects": {"total": 4},
    "reads": {"total": 15000, "avg_ms": 3.2, "p95_ms": 8.5},
    "errors": {"total": 12, "timeouts": 8, "session_errors": 2},
    "session": {"current_uptime_seconds": 3600.0, "longest_session_seconds": 21600.0},
    "network": {"last_ping_ms": 2.5, "avg_ping_ms": 2.8, "p95_ping_ms": 5.2}
  }
}
```

### Диагностика по метрикам

| Симптом | Возможная причина |
|---------|-------------------|
| Высокий `avg_ping_ms` (>50ms) | Проблемы с сетью, WiFi вместо Ethernet |
| Много `session_errors` | Сервер перезагружается или нестабилен |
| Много `timeouts` | Сеть нестабильна или сервер перегружен |
| Короткие сессии | Проблемы с энергосбережением сетевого адаптера |
| Высокий `p95_ms` при низком `avg_ms` | Периодические задержки в сети |
