# FTP Polling Configuration

## Overview

FTP Poller автоматически читает логи с FTP сервера Omron PLC и broadcast события через WebSocket.

## Настройки (.env)

```env
# FTP сервер
FTP_HOST=172.17.11.194
FTP_PORT=21
FTP_USER=omron
FTP_PASSWORD=12345678
FTP_BASE_PATH=/MEMCARD1/messages/

# Интервал опроса (секунды)
FTP_POLL_INTERVAL=15

# Количество дней для чтения (сегодня + вчера = 2)
FTP_DAYS_TO_READ=2
```

## Как работает

### 1. **Автоматический опрос**
- Каждые `FTP_POLL_INTERVAL` секунд (по умолчанию 15)
- Читает `FTP_DAYS_TO_READ` файлов (по умолчанию 2: сегодня + вчера)
- Парсит все события разгрузки
- Broadcast через WebSocket

### 2. **Формат файлов**
```
/MEMCARD1/messages/2025-12-13.txt  (сегодня)
/MEMCARD1/messages/2025-12-14.txt  (завтра)
```

Формат: `YYYY-MM-DD.txt`

### 3. **Смена дня**
- В 00:00 автоматически переключается на новый файл
- Логирует: `[FTP] Date changed: 2025-12-13 -> 2025-12-14`
- Начинает читать новые файлы

## Производительность

### Бенчмарк (2 файла, ~15 MB):
- **Время чтения:** ~500ms
- **События:** ~200 событий
- **Скорость:** ~30 MB/s

### Рекомендации:
- ✅ **15 секунд** - оптимальный интервал
- ⚠️ **< 10 секунд** - может создать нагрузку на FTP
- ⚠️ **> 30 секунд** - слишком большая задержка

## WebSocket Events

### Событие разгрузки:
```json
{
  "type": "unload_event",
  "payload": {
    "time": "12:34:56",
    "hanger": 16,
    "date": "13.12.2025",
    "timestamp": "2025-12-13T12:34:56"
  },
  "timestamp": "2025-12-13T12:34:56.123456"
}
```

### Смена дня:
```json
{
  "type": "status",
  "payload": {
    "source": "ftp",
    "event": "date_rollover",
    "message": "New day started, log reset"
  },
  "timestamp": "2025-12-14T00:00:01"
}
```

### Статус подключения:
```json
{
  "type": "status",
  "payload": {
    "source": "ftp",
    "status": "connected"  // или "disconnected"
  },
  "timestamp": "2025-12-13T12:34:56"
}
```

## Мониторинг

### Логи
```bash
# Проверить работу поллера
docker-compose logs backend | grep FTP

# Примеры логов:
[FTP] Reading log file: /MEMCARD1/messages/2025-12-13.txt
[FTP] Read 202 events from 2 days
[FTP] Date changed: 2025-12-13 -> 2025-12-14. Reading new log files.
```

### Health Check
```bash
curl http://localhost:8000/health
```

Ответ:
```json
{
  "status": "healthy",
  "services": {
    "ftp_poller": true
  }
}
```

## Troubleshooting

### Поллер не работает
```bash
# Проверить статус
curl http://localhost:8000/health

# Проверить логи
docker-compose logs backend --tail 50 | grep FTP
```

### Файлы не найдены
```
[FTP] Log file not found: /MEMCARD1/messages/2025-12-13.txt
```

**Решение:** Проверить `FTP_BASE_PATH` и формат имени файла

### Медленное чтение
```
[FTP] Read 202 events from 2 days  # Если > 1 секунды
```

**Решение:** Увеличить `FTP_POLL_INTERVAL` до 30 секунд

## Тестирование

### Бенчмарк производительности:
```bash
cd backend
python scripts/benchmark_ftp_multiday.py --days 2
```

### Симуляция (без FTP):
```bash
curl -X POST http://localhost:8000/api/dashboard/simulation/start
```

## Конфигурация для разных сценариев

### Production (стабильность):
```env
FTP_POLL_INTERVAL=15
FTP_DAYS_TO_READ=2
```

### Development (быстрое тестирование):
```env
FTP_POLL_INTERVAL=5
FTP_DAYS_TO_READ=1
```

### Low traffic (экономия ресурсов):
```env
FTP_POLL_INTERVAL=30
FTP_DAYS_TO_READ=2
```
