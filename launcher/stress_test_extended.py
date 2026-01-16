"""
Extended Stress Test for Ekranchik-modern.

Имитирует реальную нагрузку:
- WebSocket клиенты (медленные и быстрые)
- HTTP API запросы
- Мониторинг метрик сервера
- Детекция утечек памяти и деградации

Запуск: python stress_test_extended.py
"""
import asyncio
import aiohttp
import logging
import time
import statistics
from datetime import datetime
from dataclasses import dataclass, field
from typing import List, Dict, Optional
import json

# --- Configuration ---
BASE_URL = "http://localhost:8000"
WS_URL = "ws://localhost:8000/ws"

# Нагрузка
NUM_WS_CLIENTS = 30          # WebSocket клиентов
NUM_API_WORKERS = 5          # Параллельных API воркеров
API_REQUESTS_PER_SEC = 10    # Запросов в секунду на воркер

# Время теста
TEST_DURATION = 120         # 2 минуты
METRICS_INTERVAL = 10        # Сбор метрик каждые 10 сек
REPORT_INTERVAL = 20         # Отчёт каждые 20 сек

# --- Logger ---
logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] %(message)s",
    datefmt="%H:%M:%S",
    handlers=[
        logging.FileHandler("stress_test.log", mode='w'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("StressTest")


@dataclass
class TestMetrics:
    """Метрики теста."""
    start_time: float = field(default_factory=time.time)
    
    # WebSocket
    ws_connected: int = 0
    ws_disconnected: int = 0
    ws_messages_received: int = 0
    ws_errors: int = 0
    
    # API
    api_requests: int = 0
    api_errors: int = 0
    api_latencies: List[float] = field(default_factory=list)
    
    # Server metrics (from /opcua/status)
    server_metrics: List[Dict] = field(default_factory=list)
    
    # Memory tracking
    memory_samples: List[int] = field(default_factory=list)
    
    def elapsed(self) -> float:
        return time.time() - self.start_time
    
    def api_latency_avg(self) -> float:
        if not self.api_latencies:
            return 0
        return statistics.mean(self.api_latencies[-100:])  # Последние 100
    
    def api_latency_p95(self) -> float:
        if len(self.api_latencies) < 10:
            return 0
        sorted_lat = sorted(self.api_latencies[-100:])
        idx = int(len(sorted_lat) * 0.95)
        return sorted_lat[idx]


metrics = TestMetrics()
running = True


async def ws_client(client_id: int, slow: bool = False):
    """WebSocket клиент."""
    global metrics, running
    
    delay = 5.0 if slow else 0.1  # Медленный vs быстрый клиент
    
    while running:
        try:
            async with aiohttp.ClientSession() as session:
                async with session.ws_connect(WS_URL, heartbeat=30) as ws:
                    metrics.ws_connected += 1
                    logger.debug(f"WS Client {client_id}: Connected")
                    
                    async for msg in ws:
                        if not running:
                            break
                        if msg.type == aiohttp.WSMsgType.TEXT:
                            metrics.ws_messages_received += 1
                            await asyncio.sleep(delay)
                        elif msg.type == aiohttp.WSMsgType.ERROR:
                            metrics.ws_errors += 1
                            break
                    
                    metrics.ws_disconnected += 1
                    
        except asyncio.CancelledError:
            break
        except Exception as e:
            metrics.ws_errors += 1
            logger.warning(f"WS Client {client_id}: {type(e).__name__}: {e}")
            await asyncio.sleep(2)  # Реконнект через 2 сек


async def api_worker(worker_id: int):
    """HTTP API воркер - долбит разные эндпоинты."""
    global metrics, running
    
    endpoints = [
        "/api/opcua/status",
        "/api/opcua/line/status",
        "/api/opcua/data",
        "/api/opcua/hangers/active",
        "/api/opcua/monitor/status",
    ]
    
    async with aiohttp.ClientSession() as session:
        while running:
            for endpoint in endpoints:
                if not running:
                    break
                    
                start = time.time()
                try:
                    async with session.get(f"{BASE_URL}{endpoint}", timeout=aiohttp.ClientTimeout(total=10)) as resp:
                        await resp.json()
                        latency = (time.time() - start) * 1000  # ms
                        metrics.api_requests += 1
                        metrics.api_latencies.append(latency)
                        
                        # Предупреждение о медленных запросах
                        if latency > 500:
                            logger.warning(f"SLOW API: {endpoint} took {latency:.0f}ms")
                            
                except asyncio.TimeoutError:
                    metrics.api_errors += 1
                    logger.error(f"API TIMEOUT: {endpoint}")
                except Exception as e:
                    metrics.api_errors += 1
                    logger.error(f"API ERROR: {endpoint}: {e}")
                
                # Пауза между запросами
                await asyncio.sleep(1.0 / API_REQUESTS_PER_SEC)


async def metrics_collector():
    """Собирает метрики с сервера."""
    global metrics, running
    
    async with aiohttp.ClientSession() as session:
        while running:
            try:
                # Полная диагностика системы
                async with session.get(f"{BASE_URL}/api/opcua/system/health", timeout=aiohttp.ClientTimeout(total=5)) as resp:
                    data = await resp.json()
                    metrics.server_metrics.append({
                        "time": datetime.now().isoformat(),
                        "connected": data.get("opcua", {}).get("connected"),
                        "state": data.get("opcua", {}).get("state"),
                        "stats": data.get("opcua", {}).get("stats", {}),
                        "hangers": data.get("line_monitor", {}).get("hangers_tracked", 0),
                        "cache_kb": data.get("opcua", {}).get("cache_size_kb", 0),
                        "warnings": data.get("warnings", []),
                    })
                    
                    # Проверка на отключение OPC UA
                    if not data.get("opcua", {}).get("connected"):
                        logger.error("!!! OPC UA DISCONNECTED !!!")
                    
                    # Проверка предупреждений
                    warnings = data.get("warnings", [])
                    if warnings:
                        for w in warnings:
                            logger.warning(f"SERVER WARNING: {w}")
                        
            except Exception as e:
                logger.error(f"Metrics collector error: {e}")
            
            await asyncio.sleep(METRICS_INTERVAL)


async def reporter():
    """Периодический отчёт."""
    global metrics, running
    
    last_api_requests = 0
    last_ws_messages = 0
    last_time = time.time()
    
    while running:
        await asyncio.sleep(REPORT_INTERVAL)
        
        now = time.time()
        elapsed = now - last_time
        
        # Вычисляем RPS
        api_rps = (metrics.api_requests - last_api_requests) / elapsed
        ws_mps = (metrics.ws_messages_received - last_ws_messages) / elapsed
        
        last_api_requests = metrics.api_requests
        last_ws_messages = metrics.ws_messages_received
        last_time = now
        
        # Последние метрики сервера
        server_stats = {}
        hangers_count = 0
        cache_kb = 0
        server_warnings = []
        if metrics.server_metrics:
            last = metrics.server_metrics[-1]
            server_stats = last.get("stats", {})
            hangers_count = last.get("hangers", 0)
            cache_kb = last.get("cache_kb", 0)
            server_warnings = last.get("warnings", [])
        
        # Отчёт
        report = f"""
╔══════════════════════════════════════════════════════════════╗
║  STRESS TEST REPORT - {datetime.now().strftime('%H:%M:%S')} (elapsed: {metrics.elapsed():.0f}s)
╠══════════════════════════════════════════════════════════════╣
║  WebSocket:
║    Connected: {metrics.ws_connected}  Disconnected: {metrics.ws_disconnected}  Errors: {metrics.ws_errors}
║    Messages/sec: {ws_mps:.1f}
║
║  HTTP API:
║    Requests: {metrics.api_requests}  Errors: {metrics.api_errors}
║    RPS: {api_rps:.1f}
║    Latency avg: {metrics.api_latency_avg():.1f}ms  p95: {metrics.api_latency_p95():.1f}ms
║
║  OPC UA Server:
║    Connections: {server_stats.get('connections', '?')}
║    Reads: {server_stats.get('reads', '?')}
║    Errors: {server_stats.get('errors', '?')}
║    Cache hits: {server_stats.get('cache_hits', '?')}
║    Cache size: {cache_kb} KB
║    Hangers tracked: {hangers_count}
║
║  Warnings: {len(server_warnings)}
╚══════════════════════════════════════════════════════════════╝"""
        print(report)
        
        # Детекция проблем
        if metrics.api_latency_p95() > 1000:
            logger.error("!!! HIGH LATENCY DETECTED - p95 > 1000ms !!!")
        
        if metrics.api_errors > metrics.api_requests * 0.05:
            logger.error("!!! HIGH ERROR RATE - >5% API errors !!!")


async def main():
    """Главная функция теста."""
    global running
    
    print(f"""
╔══════════════════════════════════════════════════════════════╗
║           EKRANCHIK EXTENDED STRESS TEST                     ║
╠══════════════════════════════════════════════════════════════╣
║  Target: {BASE_URL}
║  Duration: {TEST_DURATION} seconds
║  WebSocket clients: {NUM_WS_CLIENTS} (15 slow + 15 fast)
║  API workers: {NUM_API_WORKERS}
╚══════════════════════════════════════════════════════════════╝
    """)
    
    # Проверяем что сервер доступен
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(f"{BASE_URL}/api/opcua/status", timeout=aiohttp.ClientTimeout(total=5)) as resp:
                if resp.status != 200:
                    logger.error(f"Server not ready: {resp.status}")
                    return
                logger.info("Server is ready, starting test...")
    except Exception as e:
        logger.error(f"Cannot connect to server: {e}")
        logger.error("Make sure backend is running: cd backend && uvicorn app.main:app")
        return
    
    tasks = []
    
    # WebSocket клиенты (половина медленных, половина быстрых)
    for i in range(NUM_WS_CLIENTS):
        slow = i < NUM_WS_CLIENTS // 2
        tasks.append(asyncio.create_task(ws_client(i, slow=slow)))
    
    # API воркеры
    for i in range(NUM_API_WORKERS):
        tasks.append(asyncio.create_task(api_worker(i)))
    
    # Сборщик метрик
    tasks.append(asyncio.create_task(metrics_collector()))
    
    # Репортер
    tasks.append(asyncio.create_task(reporter()))
    
    # Ждём окончания теста
    try:
        await asyncio.sleep(TEST_DURATION)
    except KeyboardInterrupt:
        logger.info("Test interrupted by user")
    
    running = False
    
    # Даём задачам завершиться
    await asyncio.sleep(2)
    for task in tasks:
        task.cancel()
    
    # Финальный отчёт
    print(f"""
╔══════════════════════════════════════════════════════════════╗
║                    FINAL REPORT                              ║
╠══════════════════════════════════════════════════════════════╣
║  Total duration: {metrics.elapsed():.0f} seconds
║
║  WebSocket:
║    Total connections: {metrics.ws_connected}
║    Total disconnections: {metrics.ws_disconnected}
║    Total messages: {metrics.ws_messages_received}
║    Total errors: {metrics.ws_errors}
║
║  HTTP API:
║    Total requests: {metrics.api_requests}
║    Total errors: {metrics.api_errors}
║    Error rate: {(metrics.api_errors / max(1, metrics.api_requests)) * 100:.2f}%
║    Avg latency: {metrics.api_latency_avg():.1f}ms
║    p95 latency: {metrics.api_latency_p95():.1f}ms
╚══════════════════════════════════════════════════════════════╝
    """)
    
    # Сохраняем метрики в файл
    with open("stress_test_results.json", "w") as f:
        json.dump({
            "duration": metrics.elapsed(),
            "ws_connected": metrics.ws_connected,
            "ws_disconnected": metrics.ws_disconnected,
            "ws_messages": metrics.ws_messages_received,
            "ws_errors": metrics.ws_errors,
            "api_requests": metrics.api_requests,
            "api_errors": metrics.api_errors,
            "api_latency_avg": metrics.api_latency_avg(),
            "api_latency_p95": metrics.api_latency_p95(),
            "server_metrics": metrics.server_metrics[-10:],  # Последние 10
        }, f, indent=2)
    logger.info("Results saved to stress_test_results.json")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nTest stopped by user")
