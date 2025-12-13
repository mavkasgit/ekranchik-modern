# FTP Simulation Quick Start

## Быстрый запуск симуляции

### 1. Тестовый скрипт (рекомендуется)

```bash
cd backend
python scripts/test_ftp_simulation.py
```

Этот скрипт:
- ✅ Проверяет наличие тестового файла
- ✅ Запускает симуляцию
- ✅ Показывает прогресс в реальном времени
- ✅ Выводит найденные события

### 2. Через API (для интеграции)

```bash
# Запустить симуляцию
curl -X POST http://localhost:8000/api/dashboard/simulation/start

# Проверить статус
curl http://localhost:8000/api/dashboard/simulation/status

# Остановить
curl -X POST http://localhost:8000/api/dashboard/simulation/stop
```

### 3. Автоматические тесты

```bash
# Property-based тесты (парсинг, rollover)
pytest tests/property/test_ftp_properties.py -v

# Интеграционные тесты (полный цикл)
pytest tests/integration/test_ftp_simulation_integration.py -v

# Все FTP тесты
pytest tests/property/test_ftp_properties.py tests/integration/test_ftp_simulation_integration.py -v
```

## Что исправлено

### Проблема
Регулярное выражение не находило события в логе из-за точки в конце строки.

### Решение
Изменен паттерн в `ftp_service.py`:

```python
# Было:
pattern = r'...\s+в\s+поз\.\s*34'

# Стало:
pattern = r'...\s+в\s+поз\.\s*34\.?'  # Опциональная точка в конце
```

## Результаты тестов

```
✅ 8/8 property-based тестов
✅ 4/4 интеграционных тестов
✅ 12/12 всего тестов

Время выполнения: ~12 секунд
```

## Производительность

- **Файл:** 152,954 строк (7.7 MB)
- **Скорость:** ~850 строк/сек
- **Время обработки:** ~3 минуты
- **События:** ~1,500 разгрузок

## Конфигурация

### Скорость обработки

В `ftp_poller.py`:
```python
events = await ftp_service.poll_simulation(lines_per_tick=425)
```

- Увеличить `lines_per_tick` → быстрее
- Уменьшить `lines_per_tick` → медленнее

### Интервал опроса

```python
interval = 0.5 if ftp_service.is_simulation else self._poll_interval
```

- Симуляция: 0.5 секунды
- Реальный FTP: 5 секунд

## Формат лога

Ожидаемый формат CJ2M:
```
00:07:20.145 L# Команда от CJ2M: Разгрузка подвеса - 16 в поз. 34.
```

Парсится:
- **Время:** `00:07:20`
- **Подвес:** `16`
- **Дата:** из имени файла (`2025-11-29.txt` → `29.11.2025`)

## Troubleshooting

### Нет событий
Проверьте формат лога. Должен быть:
```
HH:MM:SS.mmm L# Команда от CJ2M: Разгрузка подвеса - N в поз. 34.
```

### Файл не найден
Проверьте пути в `dashboard.py`:
```python
possible_paths = [
    Path("/app/testdata/ftp/2025-11-29.txt"),  # Docker
    Path(...) / "testdata/ftp/2025-11-29.txt",  # Local
]
```

### Слишком медленно/быстро
Измените `lines_per_tick` в `ftp_poller.py`.

## Документация

Полная документация: `backend/docs/FTP_SIMULATION.md`
