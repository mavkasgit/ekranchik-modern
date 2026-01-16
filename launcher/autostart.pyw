"""
autostart.pyw - Автозапуск Backend + Frontend (без киоска).
Добавить в автозагрузку Windows или Планировщик задач.
"""
import subprocess
import sys
import time
import logging
from pathlib import Path
from datetime import datetime

# === Пути ===
CURRENT_DIR = Path(__file__).parent.absolute()
BASE_DIR = CURRENT_DIR.parent
BACKEND_DIR = BASE_DIR / "backend"
FRONTEND_DIR = BASE_DIR / "frontend"
LOG_FILE = CURRENT_DIR / "autostart.log"
PID_FILE = CURRENT_DIR / "autostart.pid"

# === Настройки ===
STARTUP_DELAY = 10        # Задержка перед запуском (ждём загрузку Windows)
BACKEND_PORT = 8000
FRONTEND_URL = "http://localhost:5173"
BACKEND_URL = f"http://localhost:{BACKEND_PORT}"

# === Логирование ===
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        logging.FileHandler(LOG_FILE, encoding='utf-8'),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)


def get_python():
    """Получить путь к python.exe (не pythonw!)"""
    # sys.executable может быть pythonw.exe, нужен python.exe для uvicorn
    return sys.executable.replace("pythonw.exe", "python.exe")


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
                logger.info(f"Killed process on port {port}, PID: {pid}")
        except Exception as e:
            logger.warning(f"Failed to kill process on port {port}: {e}")


def check_server_running(url: str, timeout: int = 30) -> bool:
    """Проверить, запущен ли сервер."""
    import urllib.request
    import urllib.error
    
    start = time.time()
    while time.time() - start < timeout:
        try:
            urllib.request.urlopen(url, timeout=2)
            return True
        except:
            time.sleep(1)
    return False


def is_server_running(url: str) -> bool:
    """Быстрая проверка - запущен ли сервер."""
    import urllib.request
    try:
        urllib.request.urlopen(url, timeout=2)
        return True
    except:
        return False


def main():
    logger.info("=" * 50)
    logger.info(f"Autostart initiated at {datetime.now()}")
    logger.info(f"Backend dir: {BACKEND_DIR}")
    logger.info(f"Frontend dir: {FRONTEND_DIR}")
    
    # Задержка при старте Windows
    logger.info(f"Waiting {STARTUP_DELAY}s for Windows to load...")
    time.sleep(STARTUP_DELAY)
    
    # Проверяем, может сервисы уже запущены
    backend_running = is_server_running(BACKEND_URL)
    frontend_running = is_server_running(FRONTEND_URL)
    
    logger.info(f"Backend already running: {backend_running}")
    logger.info(f"Frontend already running: {frontend_running}")
    
    if backend_running and frontend_running:
        logger.info("Services already running, exiting")
        return
    
    hidden_kwargs = get_hidden_startup_info()
    python_exe = get_python()
    
    # === Backend ===
    if not backend_running:
        logger.info("Starting backend...")
        kill_process_on_port(BACKEND_PORT)
        time.sleep(1)
        
        try:
            backend_cmd = [python_exe, "-m", "uvicorn", "app.main:app",
                          "--host", "0.0.0.0", "--port", str(BACKEND_PORT)]
            
            subprocess.Popen(
                backend_cmd,
                cwd=str(BACKEND_DIR),
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                **hidden_kwargs
            )
            logger.info("Backend process started")
        except Exception as e:
            logger.error(f"Failed to start backend: {e}")
    
    # === Frontend ===
    if not frontend_running:
        logger.info("Starting frontend...")
        
        try:
            subprocess.Popen(
                ["npm", "run", "dev"],
                cwd=str(FRONTEND_DIR),
                shell=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                **hidden_kwargs
            )
            logger.info("Frontend process started")
        except Exception as e:
            logger.error(f"Failed to start frontend: {e}")
    
    # Ждём запуска
    logger.info("Waiting for services to start...")
    
    if check_server_running(BACKEND_URL, timeout=30):
        logger.info(f"Backend is running at {BACKEND_URL}")
    else:
        logger.error("Backend failed to start!")
    
    if check_server_running(FRONTEND_URL, timeout=60):
        logger.info(f"Frontend is running at {FRONTEND_URL}")
    else:
        logger.error("Frontend failed to start!")
    
    logger.info("Autostart complete")


if __name__ == "__main__":
    main()
