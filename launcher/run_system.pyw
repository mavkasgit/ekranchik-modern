"""
run_system.pyw
Скрипт для скрытого запуска всей системы (Backend + Frontend + Kiosk).
С GUI выбором монитора для киоска.
"""

import subprocess
import sys
import os
import time
import json
import tkinter as tk
from pathlib import Path
import urllib.request
import urllib.error

# === НАСТРОЙКИ ПУТЕЙ ===
# Определяем базовую директорию
# Для EXE: используем директорию где лежит EXE
# Для .pyw: используем директорию скрипта
if getattr(sys, 'frozen', False):
    # Запущено как EXE (PyInstaller)
    CURRENT_DIR = Path(sys.executable).parent.absolute()
else:
    # Запущено как скрипт
    CURRENT_DIR = Path(__file__).parent.absolute()

BASE_DIR = CURRENT_DIR.parent
BACKEND_DIR = BASE_DIR / "backend"
FRONTEND_DIR = BASE_DIR / "frontend"
KIOSK_SCRIPT = CURRENT_DIR / "dashboard_kiosk.pyw"
CONFIG_FILE = CURRENT_DIR / "run_system_config.json"
ERROR_LOG = CURRENT_DIR / "launcher_error.log"
ICON_FILE = CURRENT_DIR / "launcher.ico"

# === ФУНКЦИИ ===

def get_monitors():
    """Получить список мониторов с разрешениями через screeninfo."""
    monitors = []
    try:
        from screeninfo import get_monitors as get_screen_monitors
        for i, m in enumerate(get_screen_monitors()):
            monitors.append({
                "index": i,
                "name": m.name or f"Monitor {i+1}",
                "width": m.width,
                "height": m.height,
                "left": m.x,
                "top": m.y,
                "primary": m.is_primary if hasattr(m, 'is_primary') else (m.x == 0 and m.y == 0)
            })
    except Exception as e:
        # Fallback
        monitors = [{"index": 0, "name": "Monitor 1", "width": 1920, "height": 1080, 
                     "left": 0, "top": 0, "primary": True}]
    return monitors


def load_config():
    """Загрузить конфиг."""
    if CONFIG_FILE.exists():
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except:
            pass
    return {"kiosk_monitor": 0, "backend_port": 8000, "frontend_url": "http://localhost:5173"}


def save_config(config):
    """Сохранить конфиг."""
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=4, ensure_ascii=False)


def log_error(msg):
    """Записать ошибку в лог."""
    with open(ERROR_LOG, "a", encoding="utf-8") as f:
        f.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} - {msg}\n")

def check_server_running(url: str, timeout: int = 30) -> bool:
    """Check if a server at the given URL is running."""
    import urllib.request
    import urllib.error
    
    start = time.time()
    while time.time() - start < timeout:
        try:
            urllib.request.urlopen(url, timeout=1)
            return True
        except (urllib.error.URLError, ConnectionRefusedError):
            time.sleep(0.5)
    return False

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


class MonitorSelector:
    """GUI для выбора монитора."""
    
    def __init__(self):
        self.selected_monitor = None
        self.monitors = get_monitors()
        self.config = load_config()
        
        self.root = tk.Tk()
        self.root.title("Ekranchik - Выбор монитора")
        self.root.resizable(False, False)
        
        # Устанавливаем иконку
        if ICON_FILE.exists():
            try:
                self.root.iconbitmap(str(ICON_FILE))
            except:
                pass  # Если не получилось - используем стандартную
        
        # Центрируем окно
        window_width = 450
        window_height = 250 + len(self.monitors) * 50
        screen_width = self.root.winfo_screenwidth()
        screen_height = self.root.winfo_screenheight()
        x = (screen_width - window_width) // 2
        y = (screen_height - window_height) // 2
        self.root.geometry(f"{window_width}x{window_height}+{x}+{y}")
        
        self._create_widgets()
        
    def _create_widgets(self):
        # Заголовок
        title = tk.Label(self.root, text="Выберите монитор для киоска", 
                        font=("Segoe UI", 14, "bold"))
        title.pack(pady=15)
        
        # Фрейм для списка мониторов
        frame = tk.Frame(self.root)
        frame.pack(fill=tk.BOTH, expand=True, padx=20)
        
        # Проверяем что сохранённый индекс валиден
        saved_monitor = self.config.get("kiosk_monitor", 0)
        if saved_monitor >= len(self.monitors):
            saved_monitor = 0
        
        self.monitor_var = tk.IntVar(value=saved_monitor)
        
        for mon in self.monitors:
            primary_text = " ★ основной" if mon['primary'] else ""
            text = f"Монитор {mon['index'] + 1}: {mon['width']}x{mon['height']}{primary_text}"
            text += f"\n     {mon['name']} | Позиция: ({mon['left']}, {mon['top']})"
            
            rb = tk.Radiobutton(
                frame, 
                text=text,
                variable=self.monitor_var,
                value=mon['index'],
                font=("Segoe UI", 11),
                anchor="w",
                justify="left",
                padx=10
            )
            rb.pack(fill=tk.X, pady=8)
        
        # Кнопки
        btn_frame = tk.Frame(self.root)
        btn_frame.pack(pady=20)
        
        start_btn = tk.Button(
            btn_frame, 
            text="▶ Запустить",
            command=self._on_start,
            font=("Segoe UI", 12, "bold"),
            width=14,
            height=2,
            bg="#2E7D32",
            fg="white",
            activebackground="#1B5E20",
            activeforeground="white"
        )
        start_btn.pack(side=tk.LEFT, padx=10)
        
        cancel_btn = tk.Button(
            btn_frame,
            text="Отмена",
            command=self._on_cancel,
            font=("Segoe UI", 11),
            width=12,
            height=2
        )
        cancel_btn.pack(side=tk.LEFT, padx=10)
        
    def _on_start(self):
        self.selected_monitor = self.monitor_var.get()
        # Сохраняем выбор
        self.config["kiosk_monitor"] = self.selected_monitor
        save_config(self.config)
        self.root.destroy()
        
    def _on_cancel(self):
        self.selected_monitor = None
        self.root.destroy()
        
    def run(self):
        self.root.mainloop()
        return self.selected_monitor, self.config


def start_system(monitor_index, config):
    """Запустить систему."""
    # Определяем путь к Python
    if getattr(sys, 'frozen', False):
        # Для EXE - ищем Python в системе
        import shutil
        PYTHON_EXE = shutil.which("python") or shutil.which("python3") or "python"
        PYTHONW_EXE = PYTHON_EXE.replace("python.exe", "pythonw.exe")
        if not Path(PYTHONW_EXE).exists():
            PYTHONW_EXE = PYTHON_EXE
    else:
        # Для скрипта - используем текущий интерпретатор
        PYTHON_EXE = sys.executable
        PYTHONW_EXE = PYTHON_EXE.replace("python.exe", "pythonw.exe")
        if not Path(PYTHONW_EXE).exists():
            PYTHONW_EXE = PYTHON_EXE
    
    BACKEND_PORT = config.get("backend_port", 8000)
    
    log_error(f"Starting system: monitor={monitor_index}, port={BACKEND_PORT}")
    log_error(f"Python: {PYTHON_EXE}, Pythonw: {PYTHONW_EXE}")
    log_error(f"Backend dir: {BACKEND_DIR}")
    log_error(f"Frontend dir: {FRONTEND_DIR}")
    log_error(f"Kiosk script: {KIOSK_SCRIPT}")
    
    # Очистка порта
    kill_process_on_port(BACKEND_PORT)
    time.sleep(1)
    
    hidden_kwargs = get_hidden_startup_info()
    processes = []
    
    try:
        # Backend
        log_error("Starting backend...")
        backend_cmd = [PYTHON_EXE, "-m", "uvicorn", "app.main:app", 
                       "--host", "0.0.0.0", "--port", str(BACKEND_PORT)]
        backend_proc = subprocess.Popen(
            backend_cmd,
            cwd=str(BACKEND_DIR),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            **hidden_kwargs
        )
        processes.append(backend_proc)
        log_error(f"Backend started, PID: {backend_proc.pid}")
        
        # Frontend
        log_error("Starting frontend...")
        frontend_proc = subprocess.Popen(
            ["npm", "run", "dev"],
            cwd=str(FRONTEND_DIR),
            shell=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            **hidden_kwargs
        )
        processes.append(frontend_proc)
        log_error(f"Frontend started, PID: {frontend_proc.pid}")
        
        # Ждём запуска сервисов
        log_error("Waiting for services to start...")
        
        BACKEND_URL = f"http://localhost:{config.get('backend_port', 8000)}"
        FRONTEND_URL = config.get("frontend_url", "http://localhost:5173")

        log_error(f"Checking Backend at {BACKEND_URL}...")
        if not check_server_running(BACKEND_URL, timeout=30): # Increased timeout for backend
            log_error(f"ERROR: Backend server at {BACKEND_URL} failed to start in time. Exiting.")
            return # Exit start_system, then finally block cleans up

        log_error(f"Checking Frontend at {FRONTEND_URL}...")
        if not check_server_running(FRONTEND_URL, timeout=60): # Increased timeout for frontend (npm run dev can be slow)
            log_error(f"ERROR: Frontend server at {FRONTEND_URL} failed to start in time. Exiting.")
            return # Exit start_system, then finally block cleans up
            
        log_error("All services are running.")

        # Kiosk
        log_error(f"Starting kiosk on monitor {monitor_index}...")
        kiosk_cmd = [PYTHONW_EXE, str(KIOSK_SCRIPT), "--monitor", str(monitor_index)]
        
        # Pass geometry to kiosk if specified in config
        if config.get("kiosk_geometry"):
            kiosk_cmd.extend(["--geometry", config["kiosk_geometry"]])
        
        kiosk_proc = subprocess.Popen(
            kiosk_cmd,
            cwd=str(CURRENT_DIR),
            **hidden_kwargs
        )
        log_error(f"Kiosk started, PID: {kiosk_proc.pid}")
        
        # Ждём закрытия киоска
        kiosk_proc.wait()
        log_error("Kiosk closed")
        
    except Exception as e:
        log_error(f"ERROR: {e}")
        import traceback
        log_error(traceback.format_exc())
    
    finally:
        # Останавливаем процессы
        log_error("Stopping processes...")
        for p in processes:
            try:
                p.terminate()
                p.wait(timeout=2)
            except:
                try:
                    p.kill()
                except:
                    pass
        
        kill_process_on_port(BACKEND_PORT)
        log_error("System stopped")


def main():
    # Очищаем лог
    if ERROR_LOG.exists():
        ERROR_LOG.unlink()
    
    # Показываем выбор монитора
    selector = MonitorSelector()
    monitor, config = selector.run()
    
    if monitor is not None:
        start_system(monitor, config)


if __name__ == "__main__":
    main()
