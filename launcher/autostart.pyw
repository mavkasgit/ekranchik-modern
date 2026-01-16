"""
autostart.pyw - Надёжный автозапуск киоска с retry и логированием.
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
KIOSK_SCRIPT = CURRENT_DIR / "dashboard_kiosk.pyw"
LOG_FILE = CURRENT_DIR / "autostart.log"
PID_FILE = CURRENT_DIR / "autostart.pid"

# === Настройки ===
MAX_RETRIES = 5           # Максимум попыток запуска
RETRY_DELAY = 10          # Секунд между попытками
STARTUP_DELAY = 15        # Задержка перед первым запуском (ждём загрузку Windows)
CHECK_INTERVAL = 30       # Интервал проверки что киоск жив

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


def get_pythonw():
    """Получить путь к pythonw.exe"""
    pythonw = sys.executable.replace("python.exe", "pythonw.exe")
    if Path(pythonw).exists():
        return pythonw
    return sys.executable


def is_process_running(pid: int) -> bool:
    """Проверить, запущен ли процесс с данным PID."""
    if sys.platform == 'win32':
        try:
            import ctypes
            kernel32 = ctypes.windll.kernel32
            SYNCHRONIZE = 0x00100000
            handle = kernel32.OpenProcess(SYNCHRONIZE, False, pid)
            if handle:
                kernel32.CloseHandle(handle)
                return True
            return False
        except:
            pass
    
    # Fallback через tasklist
    try:
        result = subprocess.run(
            f'tasklist /FI "PID eq {pid}"',
            capture_output=True, text=True, shell=True,
            creationflags=subprocess.CREATE_NO_WINDOW
        )
        return str(pid) in result.stdout
    except:
        return False


def save_pid(pid: int):
    """Сохранить PID в файл."""
    PID_FILE.write_text(str(pid))


def load_pid() -> int | None:
    """Загрузить PID из файла."""
    if PID_FILE.exists():
        try:
            return int(PID_FILE.read_text().strip())
        except:
            pass
    return None


def start_kiosk() -> subprocess.Popen | None:
    """Запустить киоск."""
    pythonw = get_pythonw()
    cmd = [pythonw, str(KIOSK_SCRIPT), "--no-gui"]
    
    logger.info(f"Starting kiosk: {' '.join(cmd)}")
    
    try:
        # Скрытый запуск
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        startupinfo.wShowWindow = subprocess.SW_HIDE
        
        proc = subprocess.Popen(
            cmd,
            cwd=str(CURRENT_DIR),
            startupinfo=startupinfo,
            creationflags=subprocess.CREATE_NO_WINDOW
        )
        
        logger.info(f"Kiosk started with PID: {proc.pid}")
        save_pid(proc.pid)
        return proc
        
    except Exception as e:
        logger.error(f"Failed to start kiosk: {e}")
        return None


def main():
    logger.info("=" * 50)
    logger.info(f"Autostart initiated at {datetime.now()}")
    logger.info(f"Kiosk script: {KIOSK_SCRIPT}")
    
    # Проверяем что скрипт киоска существует
    if not KIOSK_SCRIPT.exists():
        logger.error(f"Kiosk script not found: {KIOSK_SCRIPT}")
        sys.exit(1)
    
    # Задержка при старте Windows
    logger.info(f"Waiting {STARTUP_DELAY}s for Windows to fully load...")
    time.sleep(STARTUP_DELAY)
    
    # Проверяем, может киоск уже запущен
    existing_pid = load_pid()
    if existing_pid and is_process_running(existing_pid):
        logger.info(f"Kiosk already running (PID: {existing_pid}), exiting")
        sys.exit(0)
    
    # Пробуем запустить с retry
    proc = None
    for attempt in range(1, MAX_RETRIES + 1):
        logger.info(f"Attempt {attempt}/{MAX_RETRIES}")
        
        proc = start_kiosk()
        
        if proc:
            # Ждём немного и проверяем что процесс не упал сразу
            time.sleep(3)
            if proc.poll() is None:  # Процесс ещё жив
                logger.info("Kiosk started successfully!")
                break
            else:
                logger.warning(f"Kiosk exited immediately with code: {proc.returncode}")
                proc = None
        
        if attempt < MAX_RETRIES:
            logger.info(f"Retrying in {RETRY_DELAY}s...")
            time.sleep(RETRY_DELAY)
    
    if not proc:
        logger.error("Failed to start kiosk after all retries!")
        sys.exit(1)
    
    # Мониторинг - перезапуск если упал
    logger.info(f"Monitoring kiosk (check every {CHECK_INTERVAL}s)...")
    
    while True:
        time.sleep(CHECK_INTERVAL)
        
        if proc.poll() is not None:
            logger.warning(f"Kiosk died (exit code: {proc.returncode}), restarting...")
            proc = start_kiosk()
            
            if not proc:
                logger.error("Failed to restart kiosk!")
                time.sleep(RETRY_DELAY)


if __name__ == "__main__":
    main()
