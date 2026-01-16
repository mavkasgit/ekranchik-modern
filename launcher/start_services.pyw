"""
start_services.pyw
Запуск backend и frontend в фоновом режиме.
Используется для автозапуска при старте Windows.
Киоск НЕ запускается - только сервисы.
"""

import subprocess
import sys
import time
import json
from pathlib import Path

# === ПУТИ ===
if getattr(sys, 'frozen', False):
    CURRENT_DIR = Path(sys.executable).parent.absolute()
else:
    CURRENT_DIR = Path(__file__).parent.absolute()

BASE_DIR = CURRENT_DIR.parent
BACKEND_DIR = BASE_DIR / "backend"
FRONTEND_DIR = BASE_DIR / "frontend"
CONFIG_FILE = CURRENT_DIR / "run_system_config.json"
LOG_FILE = CURRENT_DIR / "services.log"


def log(msg):
    """Записать в лог."""
    timestamp = time.strftime('%Y-%m-%d %H:%M:%S')
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(f"{timestamp} - {msg}\n")


def load_config():
    """Загрузить конфиг."""
    if CONFIG_FILE.exists():
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except:
            pass
    return {"backend_port": 8000}


def get_hidden_startup_info():
    """Настройки для скрытия консольного окна."""
    if sys.platform == 'win32':
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        startupinfo.wShowWindow = subprocess.SW_HIDE
        return {
            'startupinfo': startupinfo,
            'creationflags': subprocess.CREATE_NO_WINDOW
        }
    return {}


def kill_process_on_port(port):
    """Убить процесс на порту."""
    if sys.platform == 'win32':
        try:
            cmd = f'netstat -ano | findstr :{port}'
            proc = subprocess.run(cmd, capture_output=True, shell=True, text=True,
                                  creationflags=subprocess.CREATE_NO_WINDOW)
            lines = proc.stdout.strip().split('\n')
            pids = set()
            for line in lines:
                if 'LISTENING' in line:
                    parts = line.split()
                    pids.add(parts[-1])
            for pid in pids:
                subprocess.run(f'taskkill /F /PID {pid}', shell=True,
                               creationflags=subprocess.CREATE_NO_WINDOW)
        except:
            pass


def main():
    # Очищаем лог
    if LOG_FILE.exists():
        LOG_FILE.unlink()
    
    log("=== Ekranchik Services Autostart ===")
    
    config = load_config()
    BACKEND_PORT = config.get("backend_port", 8000)
    
    # Определяем Python
    PYTHON_EXE = sys.executable
    
    log(f"Python: {PYTHON_EXE}")
    log(f"Backend dir: {BACKEND_DIR}")
    log(f"Frontend dir: {FRONTEND_DIR}")
    log(f"Backend port: {BACKEND_PORT}")
    
    # Очистка порта
    kill_process_on_port(BACKEND_PORT)
    time.sleep(1)
    
    hidden_kwargs = get_hidden_startup_info()
    
    try:
        # Backend
        log("Starting backend...")
        backend_cmd = [PYTHON_EXE, "-m", "uvicorn", "app.main:app",
                       "--host", "0.0.0.0", "--port", str(BACKEND_PORT)]
        backend_proc = subprocess.Popen(
            backend_cmd,
            cwd=str(BACKEND_DIR),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            **hidden_kwargs
        )
        log(f"Backend started, PID: {backend_proc.pid}")
        
        # Frontend
        log("Starting frontend...")
        frontend_proc = subprocess.Popen(
            ["npm", "run", "dev"],
            cwd=str(FRONTEND_DIR),
            shell=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            **hidden_kwargs
        )
        log(f"Frontend started, PID: {frontend_proc.pid}")
        
        log("Services started successfully!")
        log("Use run_system.pyw to start kiosk manually.")
        
    except Exception as e:
        log(f"ERROR: {e}")
        import traceback
        log(traceback.format_exc())


if __name__ == "__main__":
    main()
