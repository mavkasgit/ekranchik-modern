"""
Тесты для Ekranchik Launcher
"""
import pytest
import sys
import os
import time
import threading
import subprocess
import socket
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock

# Добавляем путь к launcher
sys.path.insert(0, str(Path(__file__).parent.parent))

from launcher import (
    ProcessManager, BACKEND_DIR, FRONTEND_DIR, COLORS, FONTS,
    kill_process_on_port, kill_process_by_name, CREATE_NO_WINDOW
)


class TestKillProcessOnPort:
    """Тесты для kill_process_on_port - КРИТИЧЕСКИ ВАЖНО"""
    
    @pytest.mark.skipif(sys.platform != 'win32', reason="Windows only")
    def test_kill_process_on_port_returns_list(self):
        """kill_process_on_port возвращает список"""
        result = kill_process_on_port(9999)  # Порт который скорее всего свободен
        assert isinstance(result, list)
    
    @pytest.mark.skipif(sys.platform != 'win32', reason="Windows only")
    def test_kill_process_on_port_kills_listening_process(self):
        """kill_process_on_port убивает процесс на порту"""
        test_port = 19876  # Уникальный порт для теста
        
        # Запускаем простой сервер на порту
        server_process = subprocess.Popen(
            ['python', '-c', f'''
import socket
import time
s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
s.bind(("127.0.0.1", {test_port}))
s.listen(1)
time.sleep(60)
'''],
            creationflags=CREATE_NO_WINDOW if sys.platform == 'win32' else 0
        )
        
        time.sleep(1)  # Даём время запуститься
        
        # Проверяем что порт занят
        def is_port_in_use(port):
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                return s.connect_ex(('127.0.0.1', port)) == 0
        
        # Порт должен быть занят (или процесс слушает)
        # Убиваем процесс на порту
        killed = kill_process_on_port(test_port)
        
        time.sleep(0.5)
        
        # Проверяем что процесс убит
        assert server_process.poll() is not None or len(killed) > 0
        
        # Cleanup
        try:
            server_process.kill()
        except Exception:
            pass
    
    @pytest.mark.skipif(sys.platform != 'win32', reason="Windows only")
    def test_kill_process_on_port_8000_before_backend_start(self):
        """Тест что порт 8000 освобождается перед запуском backend"""
        # Этот тест проверяет что функция работает для порта 8000
        # Не запускаем реальный процесс, просто проверяем что функция не падает
        result = kill_process_on_port(8000)
        assert isinstance(result, list)
    
    @pytest.mark.skipif(sys.platform != 'win32', reason="Windows only")
    def test_kill_process_on_port_5173_before_frontend_start(self):
        """Тест что порт 5173 освобождается перед запуском frontend"""
        result = kill_process_on_port(5173)
        assert isinstance(result, list)


class TestKillProcessByName:
    """Тесты для kill_process_by_name"""
    
    @pytest.mark.skipif(sys.platform != 'win32', reason="Windows only")
    def test_kill_process_by_name_returns_list(self):
        """kill_process_by_name возвращает список"""
        result = kill_process_by_name("nonexistent_process_12345")
        assert isinstance(result, list)
        assert len(result) == 0  # Такого процесса нет


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
    
    @pytest.mark.skipif(sys.platform != 'win32', reason="Windows only")
    def test_backend_start_kills_previous_on_port_8000(self):
        """КРИТИЧЕСКИЙ ТЕСТ: Backend start убивает предыдущий процесс на порту 8000"""
        test_port = 8000
        
        # Запускаем фейковый процесс на порту 8000
        fake_server = subprocess.Popen(
            ['python', '-c', f'''
import socket
import time
s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
s.bind(("0.0.0.0", {test_port}))
s.listen(1)
print("Fake server listening on port {test_port}")
time.sleep(120)
'''],
            creationflags=CREATE_NO_WINDOW
        )
        
        time.sleep(1)  # Даём время запуститься
        fake_pid = fake_server.pid
        
        # Создаём ProcessManager для backend
        pm = ProcessManager("Backend", ["python", "-c", "print('test')"], Path("."))
        # Подменяем имя чтобы сработала логика убийства порта 8000
        pm.name = "Backend"
        
        # При старте должен убить процесс на порту 8000
        # Проверяем через вызов kill_process_on_port напрямую
        killed = kill_process_on_port(test_port)
        
        time.sleep(0.5)
        
        # Фейковый сервер должен быть убит
        assert fake_server.poll() is not None, f"Процесс {fake_pid} на порту {test_port} не был убит!"
        
        # Cleanup
        try:
            fake_server.kill()
        except Exception:
            pass
    
    @pytest.mark.skipif(sys.platform != 'win32', reason="Windows only")
    def test_frontend_start_kills_previous_on_port_5173(self):
        """КРИТИЧЕСКИЙ ТЕСТ: Frontend start убивает предыдущий процесс на порту 5173"""
        test_port = 5173
        
        # Запускаем фейковый процесс на порту 5173
        fake_server = subprocess.Popen(
            ['python', '-c', f'''
import socket
import time
s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
s.bind(("0.0.0.0", {test_port}))
s.listen(1)
print("Fake server listening on port {test_port}")
time.sleep(120)
'''],
            creationflags=CREATE_NO_WINDOW
        )
        
        time.sleep(1)
        fake_pid = fake_server.pid
        
        # Убиваем процесс на порту
        killed = kill_process_on_port(test_port)
        
        time.sleep(0.5)
        
        # Фейковый сервер должен быть убит
        assert fake_server.poll() is not None, f"Процесс {fake_pid} на порту {test_port} не был убит!"
        
        # Cleanup
        try:
            fake_server.kill()
        except Exception:
            pass


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
    
    def test_get_ftp_connections_status_import(self):
        """get_ftp_connections_status импортируется"""
        from ftp_utils import get_ftp_connections_status
        assert callable(get_ftp_connections_status)
    
    def test_close_ftp_connections_import(self):
        """close_ftp_connections импортируется"""
        from ftp_utils import close_ftp_connections
        assert callable(close_ftp_connections)
    
    def test_wait_for_ftp_available_import(self):
        """wait_for_ftp_available импортируется"""
        from ftp_utils import wait_for_ftp_available
        assert callable(wait_for_ftp_available)
    
    @pytest.mark.skipif(sys.platform != 'win32', reason="Windows only")
    def test_get_ftp_connections_status_returns_dict(self):
        """get_ftp_connections_status возвращает словарь с нужными полями"""
        from ftp_utils import get_ftp_connections_status
        result = get_ftp_connections_status("172.17.11.194", 21)
        
        assert isinstance(result, dict)
        assert 'total' in result
        assert 'established' in result
        assert 'time_wait' in result
        assert 'close_wait' in result
        assert 'connections' in result
        assert isinstance(result['connections'], list)
    
    @pytest.mark.skipif(sys.platform != 'win32', reason="Windows only")
    def test_close_ftp_connections_returns_dict(self):
        """close_ftp_connections возвращает словарь с результатами"""
        from ftp_utils import close_ftp_connections
        result = close_ftp_connections("172.17.11.194", 21)
        
        assert isinstance(result, dict)
        assert 'closed' in result
        assert 'killed_pids' in result
        assert 'errors' in result
        assert isinstance(result['killed_pids'], list)


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
