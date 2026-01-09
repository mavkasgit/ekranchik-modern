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



class TestDashboardAPI:
    """Тесты Dashboard API"""
    
    def test_dashboard_data(self, backend_running):
        """GET /api/dashboard"""
        data = api_request("/api/dashboard")
        assert "hangers" in data or "file_status" in data



if __name__ == "__main__":
    pytest.main([__file__, "-v"])
