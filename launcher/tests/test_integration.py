"""
Интеграционные тесты для Launcher + Backend
Запускать при работающем бэкенде: python -m pytest launcher/tests/test_integration.py -v
"""
import pytest
import urllib.request
import json
import time


BASE_URL = "http://127.0.0.1:8000"


def api_request(endpoint: str, method: str = "GET", data: bytes = None) -> dict:
    """Выполнить API запрос"""
    url = f"{BASE_URL}{endpoint}"
    req = urllib.request.Request(url, method=method, data=data)
    req.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(req, timeout=10) as resp:
        return json.loads(resp.read().decode())


@pytest.fixture(scope="module")
def backend_running():
    """Проверка что бэкенд запущен"""
    try:
        api_request("/health")
        return True
    except Exception:
        pytest.skip("Backend не запущен. Запустите: python -m uvicorn app.main:app --port 8000")


class TestHealthEndpoint:
    """Тесты /health"""
    
    def test_health_returns_healthy(self, backend_running):
        data = api_request("/health")
        assert data["status"] == "healthy"
    
    def test_health_has_services(self, backend_running):
        data = api_request("/health")
        assert "services" in data
        assert "excel_watcher" in data["services"]
        assert "ftp_poller" in data["services"]


class TestPollerAPI:
    """Тесты API поллинга"""
    
    def test_poller_status(self, backend_running):
        """GET /api/dashboard/poller/status"""
        data = api_request("/api/dashboard/poller/status")
        assert "running" in data
        assert "interval" in data
        assert isinstance(data["running"], bool)
        assert isinstance(data["interval"], int)
    
    def test_poller_start(self, backend_running):
        """POST /api/dashboard/poller/start"""
        data = api_request("/api/dashboard/poller/start", method="POST", data=b"")
        assert data["running"] is True
    
    def test_poller_stop(self, backend_running):
        """POST /api/dashboard/poller/stop"""
        # Сначала запустим
        api_request("/api/dashboard/poller/start", method="POST", data=b"")
        time.sleep(0.5)
        
        # Теперь остановим
        data = api_request("/api/dashboard/poller/stop", method="POST", data=b"")
        assert data["running"] is False
    
    def test_poller_poll_now(self, backend_running):
        """POST /api/dashboard/poller/poll-now"""
        data = api_request("/api/dashboard/poller/poll-now", method="POST", data=b"")
        assert data["status"] == "ok"


class TestSimulationAPI:
    """Тесты API симуляции"""
    
    def test_simulation_status(self, backend_running):
        """GET /api/dashboard/simulation/status"""
        data = api_request("/api/dashboard/simulation/status")
        assert "active" in data
    
    def test_simulation_start_stop(self, backend_running):
        """Тест запуска и остановки симуляции"""
        # Запуск
        try:
            data = api_request("/api/dashboard/simulation/start", method="POST", data=b"")
            assert data["active"] is True
        except urllib.error.HTTPError as e:
            if e.code == 404:
                pytest.skip("Файл симуляции не найден")
            raise
        
        # Остановка
        data = api_request("/api/dashboard/simulation/stop", method="POST", data=b"")
        assert data["active"] is False


class TestDashboardAPI:
    """Тесты Dashboard API"""
    
    def test_dashboard_data(self, backend_running):
        """GET /api/dashboard"""
        data = api_request("/api/dashboard")
        assert "hangers" in data or "file_status" in data or "ftp_status" in data
    
    def test_ftp_status(self, backend_running):
        """GET /api/dashboard/status/ftp"""
        data = api_request("/api/dashboard/status/ftp")
        assert "connected" in data or "simulation" in data


class TestPollerLifecycle:
    """Тесты жизненного цикла поллинга"""
    
    def test_full_lifecycle(self, backend_running):
        """Полный цикл: старт -> статус -> poll now -> стоп"""
        # 1. Остановим если запущен
        api_request("/api/dashboard/poller/stop", method="POST", data=b"")
        
        # 2. Проверим что остановлен
        status = api_request("/api/dashboard/poller/status")
        assert status["running"] is False
        
        # 3. Запустим
        start_result = api_request("/api/dashboard/poller/start", method="POST", data=b"")
        assert start_result["running"] is True
        
        # 4. Проверим статус
        status = api_request("/api/dashboard/poller/status")
        assert status["running"] is True
        
        # 5. Poll now
        poll_result = api_request("/api/dashboard/poller/poll-now", method="POST", data=b"")
        assert poll_result["status"] == "ok"
        
        # 6. Остановим
        stop_result = api_request("/api/dashboard/poller/stop", method="POST", data=b"")
        assert stop_result["running"] is False
        
        # 7. Финальная проверка
        status = api_request("/api/dashboard/poller/status")
        assert status["running"] is False


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
