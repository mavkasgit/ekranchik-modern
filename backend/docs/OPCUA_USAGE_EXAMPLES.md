# OPC UA Service - Примеры использования

## Базовое подключение

```python
from app.services.opcua_service import opcua_service

# Подключение
connected = await opcua_service.connect()
if connected:
    print("Подключено к OPC UA серверу")
```

## Чтение одного узла

```python
# Чтение с автоматическим кешированием
value = await opcua_service.read_node("ns=2;s=MyVariable")
if value is not None:
    print(f"Значение: {value}")
```

## Чтение нескольких узлов (параллельно)

### Вариант 1: Небольшое количество узлов (1-10)

```python
# Использует asyncio.gather для параллельного чтения
node_ids = [
    "ns=2;s=Temperature",
    "ns=2;s=Pressure",
    "ns=2;s=Speed"
]

results = await opcua_service.read_nodes(node_ids)

for node_id, value in results.items():
    print(f"{node_id}: {value}")
```

### Вариант 2: Большое количество узлов (>10)

```python
# Оптимизированное пакетное чтение
node_ids = [
    "ns=2;s=Sensor1",
    "ns=2;s=Sensor2",
    # ... много узлов
    "ns=2;s=Sensor100"
]

results = await opcua_service.read_nodes_batch(node_ids)

# Обработка результатов
valid_values = {k: v for k, v in results.items() if v is not None}
print(f"Успешно прочитано {len(valid_values)} из {len(node_ids)} узлов")
```

## Проверка соединения

```python
# Автоматическая проверка и переподключение
is_connected = await opcua_service.ensure_connected()
if is_connected:
    # Выполняем операции
    value = await opcua_service.read_node("ns=2;s=MyVariable")
```

## Диагностика

```python
# Получение диагностической информации
diagnostics = opcua_service.get_diagnostics()

print(f"Состояние: {diagnostics['state']}")
print(f"Подключено: {diagnostics['connected']}")
print(f"Попыток переподключения: {diagnostics['reconnect_attempts']}")
print(f"Узлов в черном списке: {diagnostics['blacklisted_nodes']}")
print(f"Кешированных узлов: {diagnostics['cached_nodes']}")
print(f"Статистика: {diagnostics['stats']}")
```

## Обработка ошибок

```python
try:
    value = await opcua_service.read_node("ns=2;s=MyVariable")
    if value is None:
        print("Не удалось прочитать узел (проверьте логи)")
except Exception as e:
    print(f"Ошибка: {e}")
```

## Использование в API endpoint

```python
from fastapi import APIRouter, HTTPException
from app.services.opcua_service import opcua_service

router = APIRouter()

@router.get("/opcua/nodes")
async def read_multiple_nodes(node_ids: list[str]):
    """Чтение нескольких узлов"""
    
    if not await opcua_service.ensure_connected():
        raise HTTPException(status_code=503, detail="OPC UA server not available")
    
    # Выбираем метод в зависимости от количества узлов
    if len(node_ids) <= 10:
        results = await opcua_service.read_nodes(node_ids)
    else:
        results = await opcua_service.read_nodes_batch(node_ids)
    
    return {
        "nodes": results,
        "diagnostics": opcua_service.get_diagnostics()
    }
```

## Периодическое чтение (polling)

```python
import asyncio

async def poll_nodes():
    """Периодическое чтение узлов"""
    node_ids = [
        "ns=2;s=Temperature",
        "ns=2;s=Pressure",
        "ns=2;s=Speed"
    ]
    
    while True:
        try:
            # Проверяем соединение
            if await opcua_service.ensure_connected():
                # Читаем узлы
                results = await opcua_service.read_nodes(node_ids)
                
                # Обрабатываем результаты
                for node_id, value in results.items():
                    if value is not None:
                        print(f"{node_id}: {value}")
            
            # Ждем перед следующим чтением
            await asyncio.sleep(1.0)
            
        except Exception as e:
            print(f"Ошибка в polling: {e}")
            await asyncio.sleep(5.0)  # Увеличенная задержка при ошибке

# Запуск в фоне
asyncio.create_task(poll_nodes())
```

## Best Practices

### 1. Используйте кеширование
Сервис автоматически кеширует значения на 10 секунд. Не читайте один и тот же узел слишком часто.

### 2. Выбирайте правильный метод
- `read_node()` - для одного узла
- `read_nodes()` - для 1-10 узлов
- `read_nodes_batch()` - для >10 узлов

### 3. Обрабатывайте None значения
```python
value = await opcua_service.read_node("ns=2;s=MyVariable")
if value is None:
    # Узел недоступен или в черном списке
    pass
```

### 4. Мониторьте диагностику
```python
diag = opcua_service.get_diagnostics()
if diag['reconnect_attempts'] > 5:
    # Проблемы с соединением
    logger.warning("Частые переподключения к OPC UA")
```

### 5. Используйте ensure_connected перед операциями
```python
if await opcua_service.ensure_connected():
    # Безопасно выполнять операции
    value = await opcua_service.read_node("ns=2;s=MyVariable")
```

## Производительность

### Сравнение методов чтения

| Метод | Узлов | Время | Использование |
|-------|-------|-------|---------------|
| `read_node()` | 1 | ~50ms | Одиночное чтение |
| `read_nodes()` | 5 | ~100ms | Параллельное чтение |
| `read_nodes_batch()` | 50 | ~200ms | Пакетное чтение |

### Оптимизация

1. **Группируйте чтения** - читайте несколько узлов за раз
2. **Используйте кеш** - не читайте чаще чем раз в 10 секунд
3. **Фильтруйте узлы** - сервис автоматически пропускает узлы из черного списка
4. **Мониторьте ошибки** - проверяйте логи на повторяющиеся ошибки
