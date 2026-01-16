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
from tkinter import messagebox
from pathlib import Path
import urllib.request
import urllib.error
import traceback

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
    """Получить список мониторов через win32api (надёжнее screeninfo)."""
    monitors = []
    
    if sys.platform == 'win32':
        try:
            import win32api
            import win32con
            
            monitor_handles = win32api.EnumDisplayMonitors()
            for handle in monitor_handles:
                monitor_info = win32api.GetMonitorInfo(handle[0])
                rc = monitor_info['Monitor']  # (left, top, right, bottom)
                is_primary = (monitor_info['Flags'] & win32con.MONITORINFOF_PRIMARY) == 1
                
                monitors.append({
                    "index": len(monitors),
                    "name": monitor_info.get('Device', f'Monitor {len(monitors)+1}'),
                    "width": abs(rc[2] - rc[0]),
                    "height": abs(rc[3] - rc[1]),
                    "left": rc[0],
                    "top": rc[1],
                    "primary": bool(is_primary)
                })
            
            # Сортируем слева направо
            monitors.sort(key=lambda m: m['left'])
            # Обновляем индексы после сортировки
            for i, m in enumerate(monitors):
                m['index'] = i
                
            log_error(f"Detected {len(monitors)} monitors via win32api")
            for m in monitors:
                log_error(f"  Monitor {m['index']}: {m['width']}x{m['height']} at ({m['left']},{m['top']}) primary={m['primary']}")
            
            return monitors
            
        except ImportError:
            log_error("win32api not available, trying screeninfo...")
        except Exception as e:
            log_error(f"win32api failed: {e}")
    
    # Fallback to screeninfo
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
        log_error(f"Detected {len(monitors)} monitors via screeninfo")
        return monitors
    except Exception as e:
        log_error(f"screeninfo failed: {e}")
    
    # Ultimate fallback
    log_error("Using fallback single monitor")
    return [{"index": 0, "name": "Monitor 1", "width": 1920, "height": 1080, 
             "left": 0, "top": 0, "primary": True}]


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


def is_server_running(url: str) -> bool:
    """Быстрая проверка - запущен ли сервер (без ожидания)."""
    import urllib.request
    import urllib.error
    
    try:
        urllib.request.urlopen(url, timeout=2)
        return True
    except:
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
    """GUI для выбора монитора и URL."""
    
    def __init__(self):
        self.selected_monitor = None
        self.monitors = get_monitors()
        self.config = load_config()
        
        self.root = tk.Tk()
        self.root.title("Ekranchik - Настройки запуска")
        self.root.resizable(False, False)
        
        # Устанавливаем иконку
        if ICON_FILE.exists():
            try:
                self.root.iconbitmap(str(ICON_FILE))
            except:
                pass  # Если не получилось - используем стандартную
        
        # Центрируем окно
        window_width = 500
        window_height = 350 + len(self.monitors) * 50
        screen_width = self.root.winfo_screenwidth()
        screen_height = self.root.winfo_screenheight()
        x = (screen_width - window_width) // 2
        y = (screen_height - window_height) // 2
        self.root.geometry(f"{window_width}x{window_height}+{x}+{y}")
        
        self._create_widgets()
        
    def _create_widgets(self):
        # === URL секция ===
        url_frame = tk.LabelFrame(self.root, text="URL дашборда", font=("Segoe UI", 11))
        url_frame.pack(fill=tk.X, padx=20, pady=(15, 10))
        
        # Поле ввода URL
        self.url_var = tk.StringVar(value=self.config.get("kiosk_url", "http://localhost:5173"))
        url_entry = tk.Entry(url_frame, textvariable=self.url_var, font=("Segoe UI", 11), width=50)
        url_entry.pack(fill=tk.X, padx=10, pady=10)
        
        # Быстрые кнопки для URL
        url_buttons_frame = tk.Frame(url_frame)
        url_buttons_frame.pack(fill=tk.X, padx=10, pady=(0, 10))
        
        tk.Button(url_buttons_frame, text="localhost:5173", 
                  command=lambda: self.url_var.set("http://localhost:5173"),
                  font=("Segoe UI", 9)).pack(side=tk.LEFT, padx=2)
        tk.Button(url_buttons_frame, text="localhost:3000", 
                  command=lambda: self.url_var.set("http://localhost:3000"),
                  font=("Segoe UI", 9)).pack(side=tk.LEFT, padx=2)
        tk.Button(url_buttons_frame, text="localhost:80", 
                  command=lambda: self.url_var.set("http://localhost:80"),
                  font=("Segoe UI", 9)).pack(side=tk.LEFT, padx=2)
        
        # === Монитор секция ===
        monitor_frame = tk.LabelFrame(self.root, text="Монитор для киоска", font=("Segoe UI", 11))
        monitor_frame.pack(fill=tk.BOTH, expand=True, padx=20, pady=10)
        
        # Фрейм для списка мониторов
        self.monitors_frame = tk.Frame(monitor_frame)
        self.monitors_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
        
        self._refresh_monitors_list()
        
        # Кнопки
        btn_frame = tk.Frame(self.root)
        btn_frame.pack(pady=15)
        
        refresh_btn = tk.Button(
            btn_frame,
            text="🔄 Обновить",
            command=self._on_refresh,
            font=("Segoe UI", 10),
            width=10,
            height=2
        )
        refresh_btn.pack(side=tk.LEFT, padx=5)
        
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
    
    def _refresh_monitors_list(self):
        """Обновить список мониторов."""
        # Очищаем фрейм
        for widget in self.monitors_frame.winfo_children():
            widget.destroy()
        
        # Получаем мониторы заново
        self.monitors = get_monitors()
        
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
                self.monitors_frame, 
                text=text,
                variable=self.monitor_var,
                value=mon['index'],
                font=("Segoe UI", 11),
                anchor="w",
                justify="left",
                padx=10
            )
            rb.pack(fill=tk.X, pady=5)
        
        # Обновляем размер окна
        window_height = 350 + len(self.monitors) * 50
        self.root.geometry(f"500x{window_height}")
    
    def _on_refresh(self):
        """Обновить список мониторов."""
        self._refresh_monitors_list()
        
    def _on_start(self):
        self.selected_monitor = self.monitor_var.get()
        # Сохраняем выбор монитора и URL
        self.config["kiosk_monitor"] = self.selected_monitor
        self.config["kiosk_url"] = self.url_var.get().strip()
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
        import shutil
        PYTHON_EXE = shutil.which("python") or shutil.which("python3") or "python"
        PYTHONW_EXE = PYTHON_EXE.replace("python.exe", "pythonw.exe")
        if not Path(PYTHONW_EXE).exists():
            PYTHONW_EXE = PYTHON_EXE
    else:
        PYTHON_EXE = sys.executable
        PYTHONW_EXE = PYTHON_EXE.replace("python.exe", "pythonw.exe")
        if not Path(PYTHONW_EXE).exists():
            PYTHONW_EXE = PYTHON_EXE
    
    BACKEND_PORT = config.get("backend_port", 8000)
    BACKEND_URL = f"http://localhost:{BACKEND_PORT}"
    FRONTEND_URL = config.get("frontend_url", "http://localhost:5173")
    
    log_error(f"Starting system: monitor={monitor_index}, port={BACKEND_PORT}")
    log_error(f"PYTHON_EXE: {PYTHON_EXE}")
    log_error(f"PYTHONW_EXE: {PYTHONW_EXE}")
    log_error(f"BACKEND_DIR: {BACKEND_DIR}")
    log_error(f"FRONTEND_DIR: {FRONTEND_DIR}")
    log_error(f"KIOSK_SCRIPT: {KIOSK_SCRIPT}")
    
    hidden_kwargs = get_hidden_startup_info()
    processes = []
    services_were_running = False
    
    try:
        # Проверяем, запущены ли уже сервисы (автозапуск)
        backend_running = is_server_running(BACKEND_URL)
        frontend_running = is_server_running(FRONTEND_URL)
        
        log_error(f"Backend already running: {backend_running}")
        log_error(f"Frontend already running: {frontend_running}")
        
        if backend_running and frontend_running:
            log_error("Services already running (autostart), skipping startup")
            services_were_running = True
        else:
            # Запускаем сервисы
            
            # Очистка порта если бэкенд не запущен
            if not backend_running:
                log_error("Killing processes on port...")
                kill_process_on_port(BACKEND_PORT)
                time.sleep(1)
            
            # Backend
            if not backend_running:
                log_error("Starting backend...")
                backend_cmd = [PYTHON_EXE, "-m", "uvicorn", "app.main:app", 
                               "--host", "0.0.0.0", "--port", str(BACKEND_PORT)]
                log_error(f"Backend cmd: {backend_cmd}")
                
                try:
                    backend_proc = subprocess.Popen(
                        backend_cmd,
                        cwd=str(BACKEND_DIR),
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                        **hidden_kwargs
                    )
                    processes.append(('backend', backend_proc))
                    log_error(f"Backend started, PID: {backend_proc.pid}")
                except Exception as e:
                    log_error(f"Backend start FAILED: {e}")
                    messagebox.showerror("Ошибка", f"Не удалось запустить Backend:\n{e}")
                    return
            
            # Frontend
            if not frontend_running:
                log_error("Starting frontend...")
                frontend_cmd = ["npm", "run", "dev"]
                log_error(f"Frontend cmd: {frontend_cmd} in {FRONTEND_DIR}")
                
                try:
                    frontend_proc = subprocess.Popen(
                        frontend_cmd,
                        cwd=str(FRONTEND_DIR),
                        shell=True,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                        **hidden_kwargs
                    )
                    processes.append(('frontend', frontend_proc))
                    log_error(f"Frontend started, PID: {frontend_proc.pid}")
                except Exception as e:
                    log_error(f"Frontend start FAILED: {e}")
                    messagebox.showerror("Ошибка", f"Не удалось запустить Frontend:\n{e}")
                    return
            
            # Ждём запуска сервисов
            log_error("Waiting for services to start...")
            
            log_error(f"Checking Backend at {BACKEND_URL}...")
            if not check_server_running(BACKEND_URL, timeout=30):
                # Читаем stderr бэкенда
                for name, proc in processes:
                    if name == 'backend':
                        stderr = proc.stderr.read().decode('utf-8', errors='ignore') if proc.stderr else ''
                        log_error(f"Backend stderr: {stderr[:1000]}")
                        messagebox.showerror("Ошибка", f"Backend не запустился!\n\nПроверьте лог:\n{ERROR_LOG}\n\n{stderr[:500]}")
                        return
                log_error("ERROR: Backend failed to start")
                messagebox.showerror("Ошибка", f"Backend не запустился!\n\nПроверьте лог:\n{ERROR_LOG}")
                return

            log_error(f"Checking Frontend at {FRONTEND_URL}...")
            if not check_server_running(FRONTEND_URL, timeout=60):
                for name, proc in processes:
                    if name == 'frontend':
                        stderr = proc.stderr.read().decode('utf-8', errors='ignore') if proc.stderr else ''
                        log_error(f"Frontend stderr: {stderr[:1000]}")
                        messagebox.showerror("Ошибка", f"Frontend не запустился!\n\nПроверьте лог:\n{ERROR_LOG}\n\n{stderr[:500]}")
                        return
                log_error("ERROR: Frontend failed to start")
                messagebox.showerror("Ошибка", f"Frontend не запустился!\n\nПроверьте лог:\n{ERROR_LOG}")
                return
                
        log_error("All services are running!")

        # Kiosk
        log_error(f"Starting kiosk on monitor {monitor_index}...")
        kiosk_url = config.get("kiosk_url", FRONTEND_URL)
        kiosk_cmd = [PYTHONW_EXE, str(KIOSK_SCRIPT), "--no-gui", "--monitor", str(monitor_index), "--url", kiosk_url]
        
        if config.get("kiosk_geometry"):
            kiosk_cmd.extend(["--geometry", config["kiosk_geometry"]])
        
        log_error(f"Kiosk cmd: {kiosk_cmd}")
        
        try:
            kiosk_proc = subprocess.Popen(
                kiosk_cmd,
                cwd=str(CURRENT_DIR),
                **hidden_kwargs
            )
            log_error(f"Kiosk started, PID: {kiosk_proc.pid}")
        except Exception as e:
            log_error(f"Kiosk start FAILED: {e}")
            messagebox.showerror("Ошибка", f"Не удалось запустить Kiosk:\n{e}")
            return
        
        # Ждём закрытия киоска
        kiosk_proc.wait()
        log_error("Kiosk closed")
        
    except Exception as e:
        log_error(f"CRITICAL ERROR: {e}")
        log_error(traceback.format_exc())
        messagebox.showerror("Критическая ошибка", f"{e}\n\nПодробности в:\n{ERROR_LOG}")
    
    finally:
        # Останавливаем процессы ТОЛЬКО если мы их запустили
        if not services_were_running and processes:
            log_error("Stopping processes...")
            for name, p in processes:
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
        else:
            log_error("Services left running (autostart mode)")


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
