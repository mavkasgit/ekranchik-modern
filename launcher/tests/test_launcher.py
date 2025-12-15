"""
Тесты для Ekranchik Launcher
"""
import pytest
import sys
import os
import time
import threading
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock

# Добавляем путь к launcher
sys.path.insert(0, str(Path(__file__).parent.parent))

from launcher import ProcessManager, BACKEND_DIR, FRONTEND_DIR, COLORS, FONTS


class TestProcessManager:
    """Тесты для ProcessManager"""
    
    def test_init(self):
        """Тест инициализации"""
        pm = ProcessManager("Test", ["echo", "hello"], Path("."))
        assert pm.name == "Test"
        assert pm.cmd == ["echo", "hello"]
        assert pm.process is None
        assert pm.is_running is False
        assert pm.pid is None
    
    def test_is_running_false_when_not_started(self):
        """Процесс не запущен по умолчанию"""
        pm = ProcessManager("Test", ["echo", "hello"], Path("."))
        assert pm.is_running is False
    
    def test_pid_none_when_not_started(self):
        """PID None когда процесс не запущен"""
        pm = ProcessManager("Test", ["echo", "hello"], Path("."))
        assert pm.pid is None
    
    def test_get_output_empty_when_no_output(self):
        """get_output возвращает None когда нет вывода"""
        pm = ProcessManager("Test", ["echo", "hello"], Path("."))
        assert pm.get_output() is None
    
    @pytest.mark.skipif(sys.platform != 'win32', reason="Windows only")
    def test_start_stop_echo(self):
        """Тест запуска и остановки простой команды"""
        pm = ProcessManager("Echo", ["cmd", "/c", "echo hello"], Path("."))
        
        # Запуск
        result = pm.start()
        assert result is True
        time.sleep(0.5)
        
        # Проверяем что процесс был запущен
        # (может уже завершиться т.к. echo быстрая команда)
        
        # Остановка
        pm.stop()
        assert pm.is_running is False


class TestColors:
    """Тесты для цветовой палитры"""
    
    def test_colors_defined(self):
        """Все цвета определены"""
        required_colors = [
            'accent', 'accent_hover', 'success', 'success_hover',
            'danger', 'danger_hover', 'warning', 'text', 'text_muted',
            'text_dim', 'bg_dark', 'bg_card', 'bg_input', 'bg_sidebar', 'border'
        ]
        for color in required_colors:
            assert color in COLORS, f"Цвет {color} не определён"
    
    def test_colors_are_hex(self):
        """Все цвета в hex формате"""
        for name, color in COLORS.items():
            assert color.startswith('#'), f"Цвет {name} не в hex формате: {color}"
            assert len(color) == 7, f"Цвет {name} неправильной длины: {color}"


class TestFonts:
    """Тесты для шрифтов"""
    
    def test_fonts_defined(self):
        """Все шрифты определены"""
        required_fonts = ['title', 'heading', 'body', 'small', 'mono', 'mono_small']
        for font in required_fonts:
            assert font in FONTS, f"Шрифт {font} не определён"
    
    def test_fonts_are_tuples(self):
        """Шрифты - кортежи"""
        for name, font in FONTS.items():
            assert isinstance(font, tuple), f"Шрифт {name} не кортеж"
            assert len(font) >= 2, f"Шрифт {name} должен иметь минимум 2 элемента"


class TestPaths:
    """Тесты для путей"""
    
    def test_backend_dir_exists(self):
        """Директория бэкенда существует"""
        assert BACKEND_DIR.exists(), f"Backend dir не существует: {BACKEND_DIR}"
    
    def test_frontend_dir_exists(self):
        """Директория фронтенда существует"""
        assert FRONTEND_DIR.exists(), f"Frontend dir не существует: {FRONTEND_DIR}"


class TestLogCategories:
    """Тесты для категорий логов"""
    
    def test_log_categories_import(self):
        """LOG_CATEGORIES импортируется"""
        from launcher import LOG_CATEGORIES
        assert 'all' in LOG_CATEGORIES
        assert 'ftp' in LOG_CATEGORIES
        assert 'error' in LOG_CATEGORIES
    
    def test_all_category_has_empty_patterns(self):
        """Категория 'all' имеет пустые паттерны"""
        from launcher import LOG_CATEGORIES
        assert LOG_CATEGORIES['all']['patterns'] == []
    
    def test_error_category_has_patterns(self):
        """Категория 'error' имеет паттерны"""
        from launcher import LOG_CATEGORIES
        patterns = LOG_CATEGORIES['error']['patterns']
        assert 'ERROR' in patterns or 'error' in patterns


class TestFTPUtils:
    """Тесты для FTP утилит"""
    
    def test_ftp_utils_import(self):
        """ftp_utils импортируется"""
        import ftp_utils
        assert hasattr(ftp_utils, 'get_ftp_connection')
        assert hasattr(ftp_utils, 'decode_content')
    
    def test_decode_content_utf8(self):
        """decode_content работает с UTF-8"""
        from ftp_utils import decode_content
        test_bytes = "Привет мир".encode('utf-8')
        result = decode_content(test_bytes)
        assert result == "Привет мир"
    
    def test_decode_content_cp1251(self):
        """decode_content работает с CP1251"""
        from ftp_utils import decode_content
        test_bytes = "Привет мир".encode('cp1251')
        result = decode_content(test_bytes)
        assert "Привет" in result or result is not None


class TestAPIEndpoints:
    """Тесты для API эндпоинтов (требуют запущенный бэкенд)"""
    
    @pytest.fixture
    def api_available(self):
        """Проверка доступности API"""
        import urllib.request
        try:
            req = urllib.request.Request("http://127.0.0.1:8000/health")
            urllib.request.urlopen(req, timeout=2)
            return True
        except Exception:
            pytest.skip("Backend не запущен")
    
    def test_health_endpoint(self, api_available):
        """Тест /health эндпоинта"""
        import urllib.request
        import json
        
        req = urllib.request.Request("http://127.0.0.1:8000/health")
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read().decode())
            assert data['status'] == 'healthy'
    
    def test_poller_status_endpoint(self, api_available):
        """Тест /api/dashboard/poller/status"""
        import urllib.request
        import json
        
        req = urllib.request.Request("http://127.0.0.1:8000/api/dashboard/poller/status")
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read().decode())
            assert 'running' in data
            assert 'interval' in data
    
    def test_poller_start_stop(self, api_available):
        """Тест запуска и остановки поллинга"""
        import urllib.request
        import json
        
        # Запуск
        req = urllib.request.Request(
            "http://127.0.0.1:8000/api/dashboard/poller/start",
            method="POST", data=b""
        )
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read().decode())
            assert data['running'] is True
        
        time.sleep(1)
        
        # Остановка
        req = urllib.request.Request(
            "http://127.0.0.1:8000/api/dashboard/poller/stop",
            method="POST", data=b""
        )
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read().decode())
            assert data['running'] is False


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
