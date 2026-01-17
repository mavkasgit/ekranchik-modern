"""
Ekranchik Modern - System Launcher v2
Модернизированный дизайн по 10 советам
"""

import sys
import os
import subprocess
import threading
import queue
import re
from pathlib import Path
from datetime import datetime
import time
import io

# Регулярка для очистки ANSI-кодов
ANSI_ESCAPE = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')

import tempfile

try:
    import tkinter
    import customtkinter as ctk
    from PIL import Image, ImageDraw
    import pystray
    import win32gui
    import win32con
    import win32process
    import win32api
    HAS_GUI = True
    HAS_TRAY = True
except ImportError as e:
    HAS_GUI = False
    HAS_TRAY = False
    print(f"GUI недоступен: {e}")

# Настройки - определяем пути с учётом PyInstaller
if getattr(sys, 'frozen', False):
    # Запуск из EXE
    _exe_dir = Path(sys.executable).parent
    # Если exe в launcher/dist/, то:
    # - BASE_DIR = launcher/dist/../../ = проект
    # - LAUNCHER_DIR = launcher/dist/../ = launcher/
    BASE_DIR = _exe_dir.parent.parent
    LAUNCHER_DIR = _exe_dir.parent  # launcher/ (где лежит dashboard_kiosk.py)
    THEME_PATH = Path(sys._MEIPASS) / "theme.json"
else:
    # Обычный запуск
    BASE_DIR = Path(__file__).parent.parent
    LAUNCHER_DIR = Path(__file__).parent
    THEME_PATH = Path(__file__).parent / "theme.json"

BACKEND_DIR = BASE_DIR / "backend"
FRONTEND_DIR = BASE_DIR / "frontend"

# Команды запуска
# При запуске из EXE используем системный Python, иначе текущий интерпретатор
if getattr(sys, 'frozen', False):
    # Запуск из EXE - ищем Python в системе
    import shutil
    PYTHON_EXE = shutil.which("python") or shutil.which("python3") or "python"
else:
    PYTHON_EXE = sys.executable

BACKEND_CMD = [PYTHON_EXE, "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
FRONTEND_CMD = ["npm", "run", "dev"]
KIOSK_CMD = [PYTHON_EXE, "dashboard_kiosk.pyw", "--no-gui"]

# Настройки браузера в трее
CHROME_PATH = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
BROWSER_URL = "http://ktm.local"
BROWSER_PROFILE_DIR = None  # Будет установлен в __init__

# Windows-specific
if sys.platform == 'win32':
    CREATE_NO_WINDOW = subprocess.CREATE_NO_WINDOW
else:
    CREATE_NO_WINDOW = 0


def get_monitors():
    """Получить список мониторов (Windows)."""
    monitors = []
    
    if sys.platform != 'win32':
        return monitors
    
    # Попытка 1: win32api (более надежный способ)
    try:
        import win32api
        monitor_handles = win32api.EnumDisplayMonitors()
        for handle in monitor_handles:
            info = win32api.GetMonitorInfo(handle[0])
            rc = info['Monitor']
            monitors.append({
                'left': rc[0],
                'top': rc[1],
                'right': rc[2],
                'bottom': rc[3],
                'width': rc[2] - rc[0],
                'height': rc[3] - rc[1]
            })
        
        if monitors:
            return monitors
    except Exception as e:
        print(f"win32api detection failed: {e}")
    
    # Попытка 2: ctypes (менее надежный fallback)
    try:
        import ctypes
        user32 = ctypes.windll.user32
        
        monitor_count = user32.GetSystemMetrics(80)  # SM_CMONITORS
        
        if monitor_count > 0:
            # Получаем размер виртуального экрана
            virtual_width = user32.GetSystemMetrics(78)  # SM_CXVIRTUALSCREEN
            virtual_height = user32.GetSystemMetrics(79)  # SM_CYVIRTUALSCREEN
            
            if monitor_count > 1:
                # Предполагаем стандартные мониторы
                for i in range(monitor_count):
                    monitors.append({
                        'left': i * 1920,
                        'top': 0,
                        'right': (i + 1) * 1920,
                        'bottom': 1080,
                        'width': 1920,
                        'height': 1080
                    })
            else:
                monitors.append({
                    'left': 0,
                    'top': 0,
                    'right': virtual_width,
                    'bottom': virtual_height,
                    'width': virtual_width,
                    'height': virtual_height
                })
            
            return monitors
    except Exception as e:
        print(f"ctypes detection failed: {e}")
    
    # Попытка 3: tkinter (самый ненадежный)
    try:
        import tkinter as tk
        root = tk.Tk()
        root.withdraw()
        
        screen_width = root.winfo_screenwidth()
        screen_height = root.winfo_screenheight()
        
        if screen_width > 2000:
            monitors.append({
                'left': 0, 'top': 0, 'right': 1920, 'bottom': 1080,
                'width': 1920, 'height': 1080
            })
            monitors.append({
                'left': 1920, 'top': 0, 'right': 3840, 'bottom': 1080,
                'width': 1920, 'height': 1080
            })
        else:
            monitors.append({
                'left': 0, 'top': 0, 'right': screen_width, 'bottom': screen_height,
                'width': screen_width, 'height': screen_height
            })
        
        root.destroy()
    except Exception as e:
        print(f"tkinter detection failed: {e}")
    
    return monitors


def kill_process_on_port(port: int) -> list:
    """
    Убивает все процессы, занимающие указанный порт.
    Возвращает список убитых PID.
    """
    killed = []
    if sys.platform != 'win32':
        return killed
    
    try:
        # Получаем список процессов на порту
        result = subprocess.run(
            ['netstat', '-ano'],
            capture_output=True,
            text=True,
            creationflags=CREATE_NO_WINDOW
        )
        
        pids_to_kill = set()
        for line in result.stdout.split('\n'):
            if f':{port}' in line and 'LISTENING' in line:
                parts = line.split()
                if parts:
                    try:
                        pid = int(parts[-1])
                        if pid > 0:
                            pids_to_kill.add(pid)
                    except ValueError:
                        pass
        
        # Убиваем найденные процессы
        for pid in pids_to_kill:
            try:
                subprocess.run(
                    ['taskkill', '/PID', str(pid), '/F'],
                    capture_output=True,
                    creationflags=CREATE_NO_WINDOW
                )
                killed.append(pid)
            except Exception:
                pass
                
    except Exception:
        pass
    
    return killed


def kill_process_by_name(name_pattern: str) -> list:
    """
    Убивает процессы по имени (частичное совпадение).
    Возвращает список убитых PID.
    """
    killed = []
    if sys.platform != 'win32':
        return killed
    
    try:
        # Получаем список процессов
        result = subprocess.run(
            ['tasklist', '/FO', 'CSV'],
            capture_output=True,
            text=True,
            creationflags=CREATE_NO_WINDOW
        )
        
        for line in result.stdout.split('\n')[1:]:  # Пропускаем заголовок
            if name_pattern.lower() in line.lower():
                parts = line.strip('"').split('","')
                if len(parts) >= 2:
                    try:
                        pid = int(parts[1].strip('"'))
                        subprocess.run(
                            ['taskkill', '/PID', str(pid), '/F'],
                            capture_output=True,
                            creationflags=CREATE_NO_WINDOW
                        )
                        killed.append(pid)
                    except (ValueError, Exception):
                        pass
    except Exception:
        pass
    
    return killed


def get_hidden_subprocess_args():
    """Возвращает аргументы для скрытого запуска subprocess на Windows"""
    if sys.platform == 'win32':
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        startupinfo.wShowWindow = subprocess.SW_HIDE
        return {
            'creationflags': CREATE_NO_WINDOW,
            'startupinfo': startupinfo
        }
    return {}


# === Цветовая палитра ===
COLORS = {
    'accent': '#ff6b00',
    'accent_hover': '#ff8533',
    'success': '#4caf50',
    'success_hover': '#66bb6a',
    'danger': '#ef5350',
    'danger_hover': '#f44336',
    'warning': '#ffb74d',
    'text': '#e0e0e0',
    'text_muted': '#a0a0a0',
    'text_dim': '#666666',
    'bg_dark': '#1e1e1e',
    'bg_card': '#2b2b2b',
    'bg_input': '#111111',
    'bg_sidebar': '#252525',
    'border': '#3d3d3d',
}

# === Шрифты ===
FONTS = {
    'title': ('Segoe UI', 24, 'bold'),
    'heading': ('Segoe UI', 16, 'bold'),
    'body': ('Segoe UI', 13),
    'small': ('Segoe UI', 11),
    'mono': ('Consolas', 10),
    'mono_small': ('Consolas', 9),
}


class ProcessManager:
    """Управление процессом с логами"""
    
    def __init__(self, name: str, cmd: list, cwd: Path):
        self.name = name
        self.cmd = cmd
        self.cwd = cwd
        self.process: subprocess.Popen = None
        self.output_queue = queue.Queue()
        self._stop_reading = threading.Event()
        
    @property
    def is_running(self) -> bool:
        if self.process is None:
            return False
        return self.process.poll() is None
    
    @property
    def pid(self) -> int:
        return self.process.pid if self.process else None
    
    def start(self) -> bool:
        if self.is_running:
            return False
        
        # ОБЯЗАТЕЛЬНО убиваем предыдущие процессы на нужных портах
        if "backend" in self.name.lower() or "8000" in str(self.cmd):
            killed = kill_process_on_port(8000)
            if killed:
                self.output_queue.put(f"[SYSTEM] Убиты предыдущие процессы на порту 8000: {killed}")
                time.sleep(1)  # Даём время освободить порт
        
        if "frontend" in self.name.lower() or "npm" in str(self.cmd):
            killed = kill_process_on_port(5173)
            if killed:
                self.output_queue.put(f"[SYSTEM] Убиты предыдущие процессы на порту 5173: {killed}")
                time.sleep(1)  # Даём время освободить порт
            
        try:
            # Получаем аргументы для скрытого запуска
            hidden_args = get_hidden_subprocess_args()
            
            self.process = subprocess.Popen(
                self.cmd,
                cwd=self.cwd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
                shell=True if "npm" in self.cmd[0] else False,
                **hidden_args
            )
            
            self._stop_reading.clear()
            threading.Thread(target=self._read_output, daemon=True).start()
            
            self.output_queue.put(f"[SYSTEM] {self.name} запущен (PID: {self.pid})")
            return True
        except Exception as e:
            self.output_queue.put(f"[ERROR] Ошибка запуска {self.name}: {e}")
            return False
    
    def stop(self) -> bool:
        if not self.is_running:
            return False
            
        try:
            self._stop_reading.set()
            pid = self.pid
            self.process.terminate()
            
            try:
                self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait(timeout=2)
            
            self.output_queue.put(f"[SYSTEM] {self.name} остановлен (PID: {pid})")
            self.process = None
            return True
        except Exception as e:
            self.output_queue.put(f"[ERROR] Ошибка остановки {self.name}: {e}")
            return False
    
    def restart(self) -> bool:
        self.stop()
        time.sleep(1)
        return self.start()
    
    def _read_output(self):
        try:
            while not self._stop_reading.is_set() and self.process:
                if self.process.stdout:
                    line = self.process.stdout.readline()
                    if line:
                        # Очищаем ANSI-коды и заменяем проблемные символы
                        clean = ANSI_ESCAPE.sub('', line.rstrip())
                        clean = clean.replace('вћњ', '>').replace('[32m', '').replace('[39m', '')
                        clean = clean.replace('[1m', '').replace('[22m', '').replace('[2m', '')
                        clean = clean.replace('[36m', '').replace('[0m', '')
                        self.output_queue.put(clean)
                    elif self.process.poll() is not None:
                        break
        except Exception:
            pass
    
    def get_output(self) -> str:
        try:
            return self.output_queue.get_nowait()
        except queue.Empty:
            return None


if HAS_GUI:
    # Добавляем путь для PyInstaller
    import sys
    if getattr(sys, 'frozen', False):
        # Запуск из EXE
        _base_path = sys._MEIPASS
    else:
        _base_path = Path(__file__).parent
    
    if str(_base_path) not in sys.path:
        sys.path.insert(0, str(_base_path))
    
    from icons import (
        get_ctk_image, get_status_image,
        icon_play, icon_stop, icon_restart, icon_copy, icon_trash,
        icon_folder, icon_connection, icon_calendar, icon_filter, icon_refresh
    )


    class StatusBadge(ctk.CTkFrame):
        """Компонент статуса с цветным кружком (Совет 7)"""
        
        def __init__(self, parent, text: str = "Остановлен", running: bool = False):
            super().__init__(parent, fg_color="transparent")
            
            self._running = running
            
            # Canvas для кружка
            self.dot_canvas = ctk.CTkCanvas(
                self, width=12, height=12, 
                bg=COLORS['bg_card'], highlightthickness=0
            )
            self.dot_canvas.pack(side="left", padx=(0, 8))
            
            self.label = ctk.CTkLabel(
                self, text=text,
                font=ctk.CTkFont(family=FONTS['body'][0], size=FONTS['body'][1])
            )
            self.label.pack(side="left")
            
            self._draw_dot()
        
        def _draw_dot(self):
            self.dot_canvas.delete("all")
            color = COLORS['success'] if self._running else COLORS['text_dim']
            self.dot_canvas.create_oval(2, 2, 10, 10, fill=color, outline="")
        
        def set_status(self, running: bool, text: str = None):
            self._running = running
            self._draw_dot()
            if text:
                self.label.configure(text=text)


    # Категории логов для фильтрации
    LOG_CATEGORIES = {
        'all': {'label': 'Все', 'patterns': []},
        'error': {'label': 'Ошибки', 'patterns': ['ERROR', 'Error', 'error', 'Exception', 'Traceback', 'Failed']},
        'system': {'label': 'Система', 'patterns': ['[SYSTEM]', 'Started', 'Stopped', 'PID', 'startup']},
        'opcua': {'label': 'OPC UA', 'patterns': ['OPC', 'opc.tcp', 'opcua']},
        'excel': {'label': 'Excel', 'patterns': ['excel', 'Excel', 'xlsx', 'workbook', 'sheet', 'openpyxl']},
        'websocket': {'label': 'WebSocket', 'patterns': ['websocket', 'WebSocket', 'ws://', 'broadcast']},
        'api': {'label': 'API', 'patterns': ['POST', 'GET', 'PUT', 'DELETE', '/api/', 'HTTP', '200', '404', '500']},
        'simulation': {'label': 'Симуляция', 'patterns': ['[SIMULATION]', 'simulation', 'Simulation']},
    }

    class LogWidget(ctk.CTkFrame):
        """Виджет логов с фильтрацией и гарантированным копированием"""
        
        def __init__(self, parent, height: int = 300, show_filters: bool = True):
            super().__init__(parent, fg_color=COLORS['bg_card'], corner_radius=12)
            
            # Ссылка на title из родительской карточки для сохранения в файл
            self.title = parent.title if hasattr(parent, 'title') else "Логи"

            self._all_logs = []
            self._current_filter = 'all'
            self._show_filters = show_filters
            
            # Toolbar
            toolbar = ctk.CTkFrame(self, fg_color="transparent")
            toolbar.pack(fill="x", padx=16, pady=(12, 8))
            
            actions_frame = ctk.CTkFrame(toolbar, fg_color="transparent")
            actions_frame.pack(side="left")
            
            ctk.CTkButton(
                actions_frame, text="Копировать все", command=self.copy_all, width=110, height=28,
                font=ctk.CTkFont(family=FONTS['small'][0], size=FONTS['small'][1]),
                fg_color=COLORS['border'], hover_color=COLORS['bg_sidebar'], corner_radius=6
            ).pack(side="left", padx=(0, 8))

            ctk.CTkButton(
                actions_frame, text="В блокнот", command=self.open_in_notepad, width=90, height=28,
                font=ctk.CTkFont(family=FONTS['small'][0], size=FONTS['small'][1]),
                fg_color=COLORS['border'], hover_color=COLORS['bg_sidebar'], corner_radius=6
            ).pack(side="left", padx=(0, 8))

            ctk.CTkButton(
                actions_frame, text="Очистить", command=self.clear, width=80, height=28,
                font=ctk.CTkFont(family=FONTS['small'][0], size=FONTS['small'][1]),
                fg_color=COLORS['border'], hover_color=COLORS['bg_sidebar'], corner_radius=6
            ).pack(side="left")
            
            if show_filters:
                filters_frame = ctk.CTkFrame(toolbar, fg_color="transparent")
                filters_frame.pack(side="right")
                
                ctk.CTkLabel(
                    filters_frame, text="Фильтр:",
                    font=ctk.CTkFont(family=FONTS['small'][0], size=FONTS['small'][1]),
                    text_color=COLORS['text_muted']
                ).pack(side="left", padx=(0, 8))
                
                self._filter_buttons = {}
                for cat_id, cat_info in LOG_CATEGORIES.items():
                    btn = ctk.CTkButton(
                        filters_frame, text=cat_info['label'], width=70, height=24,
                        font=ctk.CTkFont(family=FONTS['mono_small'][0], size=FONTS['mono_small'][1]),
                        fg_color=COLORS['accent'] if cat_id == 'all' else COLORS['bg_input'],
                        hover_color=COLORS['accent_hover'] if cat_id == 'all' else COLORS['border'],
                        corner_radius=4, command=lambda c=cat_id: self._set_filter(c)
                    )
                    btn.pack(side="left", padx=2)
                    self._filter_buttons[cat_id] = btn

            self._count_label = ctk.CTkLabel(
                toolbar, text="0 записей",
                font=ctk.CTkFont(family=FONTS['small'][0], size=FONTS['small'][1]),
                text_color=COLORS['text_dim']
            )
            self._count_label.pack(side="right" if not show_filters else "left", padx=(16, 0))
            
            text_container = ctk.CTkFrame(self, fg_color=COLORS['bg_input'], corner_radius=8)
            text_container.pack(fill="both", expand=True, padx=12, pady=(0, 12))
            
            self.text = tkinter.Text(
                text_container,
                height=1,
                font=FONTS['mono'],
                background=COLORS['bg_input'],
                foreground=COLORS['text_muted'],
                selectbackground=COLORS['accent'],
                selectforeground=COLORS['bg_input'],
                insertbackground=COLORS['text'],
                wrap="word",
                borderwidth=0,
                highlightthickness=0,
                relief="flat",
                state="disabled" 
            )
            self.text.pack(fill="both", expand=True, padx=10, pady=5)

        def _set_filter(self, category: str):
            self._current_filter = category
            if self._show_filters:
                for cat_id, btn in self._filter_buttons.items():
                    btn.configure(fg_color=COLORS['accent'] if cat_id == category else COLORS['bg_input'],
                                  hover_color=COLORS['accent_hover'] if cat_id == category else COLORS['border'])
            self._redraw_logs()
        
        def _matches_filter(self, text: str, category: str) -> bool:
            if category == 'all':
                return True
            patterns = LOG_CATEGORIES.get(category, {}).get('patterns', [])
            return any(p.lower() in text.lower() for p in patterns)
        
        def _redraw_logs(self):
            self.text.config(state="normal")
            self.text.delete("1.0", "end")
            filtered = [log for log in self._all_logs if self._matches_filter(log, self._current_filter)]
            for log in filtered:
                self.text.insert("end", log + "\n")
            self.text.see("end")
            self.text.config(state="disabled")
            self._update_count(len(filtered), len(self._all_logs))
        
        def _update_count(self, shown: int, total: int):
            text = f"{total} записей" if shown == total else f"{shown}/{total} записей"
            self._count_label.configure(text=text)
        
        def append(self, text: str, tag: str = 'output'):
            timestamp = datetime.now().strftime("%H:%M:%S")
            log_line = f"[{timestamp}] {text}"
            self._all_logs.append(log_line)
            
            if len(self._all_logs) > 5000:
                self._all_logs = self._all_logs[-4000:]
            
            if self._matches_filter(log_line, self._current_filter):
                self.text.config(state="normal")
                self.text.insert("end", log_line + "\n")
                self.text.see("end")
                self.text.config(state="disabled")
            
            self._update_count(
                sum(1 for l in self._all_logs if self._matches_filter(l, self._current_filter)),
                len(self._all_logs)
            )
        
        def add_separator(self, title: str = ""):
            sep = f"{'─' * 30} {title} {'─' * 10}" if title else "─" * 50
            self._all_logs.append(sep)
            if self._current_filter == 'all':
                self.text.config(state="normal")
                self.text.insert("end", f"\n{sep}\n")
                self.text.see("end")
                self.text.config(state="disabled")
        
        def clear(self):
            self._all_logs.clear()
            self.text.config(state="normal")
            self.text.delete("1.0", "end")
            self.text.config(state="disabled")
            self._update_count(0, 0)

        def open_in_notepad(self):
            """Открыть текущие отфильтрованные логи в блокноте"""
            content = '\n'.join(self.get_filtered_logs())
            if not content.strip():
                self.append("[SYSTEM] Нет логов для открытия")
                return

            try:
                filter_name = LOG_CATEGORIES.get(self._current_filter, {}).get('label', 'Все')
                fd, path = tempfile.mkstemp(suffix=".txt", prefix=f"ekranchik-{filter_name}-", text=True)
                with os.fdopen(fd, 'w', encoding='utf-8') as f:
                    f.write(f"Логи Ekranchik Modern\n")
                    f.write(f"Фильтр: {filter_name}\n")
                    f.write(f"Сгенерировано: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
                    f.write("=" * 80 + "\n\n")
                    f.write(content)

                if sys.platform == "win32":
                    os.startfile(path)
                elif sys.platform == "darwin":
                    subprocess.run(["open", path])
                else:
                    subprocess.run(["xdg-open", path])
                
                self.append(f"[SYSTEM] Логи ({filter_name}) открыты в блокноте")
            except Exception as e:
                self.append(f"[ERROR] Не удалось открыть: {e}")

        def copy_all(self):
            content = self.text.get("1.0", "end-1c")
            if not content.strip():
                self.append("[SYSTEM] Нет логов для копирования.")
                return
            try:
                root = self.winfo_toplevel()
                root.clipboard_clear()
                root.clipboard_append(content)
                root.update()
                self.append("[SYSTEM] Все логи скопированы")
            except Exception as e:
                self.append(f"[ERROR] Не удалось скопировать: {e}")
        
        def get_filtered_logs(self, category: str = None) -> list:
            cat = category or self._current_filter
            return [l for l in self._all_logs if self._matches_filter(l, cat)]


    class ServiceCard(ctk.CTkFrame):
        """Карточка сервиса (Совет 3 - принцип карточек)"""
        
        def __init__(self, parent, title: str, manager: ProcessManager):
            super().__init__(parent, fg_color=COLORS['bg_card'], corner_radius=12)
            
            self.title = title
            self.manager = manager
            
            # Header с отступами (Совет 5)
            header = ctk.CTkFrame(self, fg_color="transparent")
            header.pack(fill="x", padx=20, pady=(16, 12))
            
            # Заголовок (Совет 4 - типографика)
            ctk.CTkLabel(
                header,
                text=title,
                font=ctk.CTkFont(family=FONTS['heading'][0], size=FONTS['heading'][1], weight='bold')
            ).pack(side="left")
            
            # Статус badge (Совет 7)
            self.status_badge = StatusBadge(header, "Остановлен", False)
            self.status_badge.pack(side="right")
            
            # Кнопки (Совет 8 - иерархия кнопок)
            btn_frame = ctk.CTkFrame(self, fg_color="transparent")
            btn_frame.pack(fill="x", padx=20, pady=(0, 16))
            
            # Запустить - яркая (Filled)
            self.start_btn = ctk.CTkButton(
                btn_frame,
                text="Запустить",
                image=get_ctk_image(icon_play, 18),
                command=self.start,
                width=130,
                height=38,
                font=ctk.CTkFont(family=FONTS['body'][0], size=FONTS['body'][1], weight='bold'),
                fg_color=COLORS['success'],
                hover_color=COLORS['success_hover'],
                corner_radius=8
            )
            self.start_btn.pack(side="left", padx=(0, 10))
            
            # Остановить - приглушенная (Совет 8)
            self.stop_btn = ctk.CTkButton(
                btn_frame,
                text="Остановить",
                image=get_ctk_image(icon_stop, 18),
                command=self.stop,
                width=130,
                height=38,
                font=ctk.CTkFont(family=FONTS['body'][0], size=FONTS['body'][1]),
                fg_color=COLORS['border'],  # Приглушенный
                hover_color=COLORS['danger'],
                corner_radius=8,
                state="disabled"
            )
            self.stop_btn.pack(side="left", padx=(0, 10))
            
            # Перезапуск - outline стиль
            self.restart_btn = ctk.CTkButton(
                btn_frame,
                text="Перезапуск",
                image=get_ctk_image(icon_restart, 18),
                command=self.restart,
                width=130,
                height=38,
                font=ctk.CTkFont(family=FONTS['body'][0], size=FONTS['body'][1]),
                fg_color="transparent",
                hover_color=COLORS['border'],
                border_width=1,
                border_color=COLORS['border'],
                corner_radius=8,
                state="disabled"
            )
            self.restart_btn.pack(side="left")
            
            # Логи
            self.log = LogWidget(self, height=220)
            self.log.pack(fill="both", expand=True, padx=12, pady=(0, 12))
        
        def start(self):
            self.log.add_separator("ЗАПУСК")
            if self.manager.start():
                self._update_status(True)
        
        def stop(self):
            self.log.add_separator("ОСТАНОВКА")
            if self.manager.stop():
                self._update_status(False)
        
        def restart(self):
            self.log.add_separator("ПЕРЕЗАПУСК")
            if self.manager.restart():
                self._update_status(True)
        
        def _update_status(self, running: bool):
            if running:
                self.status_badge.set_status(True, f"PID: {self.manager.pid}")
                self.start_btn.configure(state="disabled")
                self.stop_btn.configure(state="normal", fg_color=COLORS['danger'])
                self.restart_btn.configure(state="normal")
            else:
                self.status_badge.set_status(False, "Остановлен")
                self.start_btn.configure(state="normal")
                self.stop_btn.configure(state="disabled", fg_color=COLORS['border'])
                self.restart_btn.configure(state="disabled")
        
        def update_log(self):
            while True:
                output = self.manager.get_output()
                if output is None:
                    break
                self.log.append(output)
            
            is_running = self.manager.is_running
            badge_running = "PID" in self.status_badge.label.cget("text")
            if is_running != badge_running:
                self._update_status(is_running)


    class LauncherApp:
        """Главное приложение с Sidebar (Совет 9)"""
        
        def __init__(self):
            # Применяем кастомную тему (Совет 2)
            ctk.set_appearance_mode("dark")
            if THEME_PATH.exists():
                ctk.set_default_color_theme(str(THEME_PATH))
            else:
                ctk.set_default_color_theme("blue")
            
            self.root = ctk.CTk()
            self.root.title("Ekranchik Modern")
            self.root.geometry("1200x800")
            self.root.minsize(1000, 700)
            self.root.configure(fg_color=COLORS['bg_dark'])
            
            # Иконка
            icon_path = Path(__file__).parent / "launcher.ico"
            if icon_path.exists():
                try:
                    self.root.iconbitmap(str(icon_path))
                except:
                    pass
            
            # Менеджеры процессов
            self.backend_manager = ProcessManager("Backend", BACKEND_CMD, BACKEND_DIR)
            self.frontend_manager = ProcessManager("Frontend", FRONTEND_CMD, FRONTEND_DIR)
            self.kiosk_manager = ProcessManager("Kiosk", KIOSK_CMD, LAUNCHER_DIR)
            
            # Выбранный монитор для киоска (по умолчанию второй)
            self._kiosk_monitor = 1
            
            # Tray
            self.tray_icon = None
            self.tray_thread = None
            
            # Браузер в трее (новая логика из tray_kiosk.py)
            self.chrome_process = None
            self.chrome_hwnd = None
            self.chrome_is_visible = True
            
            # Профиль браузера
            global BROWSER_PROFILE_DIR
            BROWSER_PROFILE_DIR = os.path.join(os.environ.get("TEMP", tempfile.gettempdir()), "EkranchikBrowserProfile")
            
            # Текущая страница
            self.current_page = "backend"
            self.pages = {}
            self.sidebar_buttons = {}
            
            self._create_ui()
            
            # Обработка закрытия
            self.root.protocol("WM_DELETE_WINDOW", self._on_close_request)
            
            # Обновление логов
            self._start_log_updates()
            
            # System Tray
            if HAS_TRAY:
                self._setup_tray()
        
        def _create_ui(self):
            # Главный контейнер
            main = ctk.CTkFrame(self.root, fg_color="transparent")
            main.pack(fill="both", expand=True)
            
            # === TOP BAR с навигацией и статусами ===
            topbar = ctk.CTkFrame(main, height=50, fg_color=COLORS['bg_card'], corner_radius=0)
            topbar.pack(fill="x", side="top")
            topbar.pack_propagate(False)
            
            # Навигация (табы)
            nav_frame = ctk.CTkFrame(topbar, fg_color="transparent")
            nav_frame.pack(side="left", padx=16)
            
            self.sidebar_buttons["backend"] = ctk.CTkButton(
                nav_frame, text="Backend", width=100, height=36,
                font=ctk.CTkFont(family=FONTS['body'][0], size=12),
                fg_color=COLORS['accent'], hover_color=COLORS['accent_hover'],
                corner_radius=6, command=lambda: self._switch_page("backend")
            )
            self.sidebar_buttons["backend"].pack(side="left", padx=(0, 8))
            
            self.sidebar_buttons["frontend"] = ctk.CTkButton(
                nav_frame, text="Frontend", width=100, height=36,
                font=ctk.CTkFont(family=FONTS['body'][0], size=12),
                fg_color=COLORS['border'], hover_color=COLORS['bg_sidebar'],
                corner_radius=6, command=lambda: self._switch_page("frontend")
            )
            self.sidebar_buttons["frontend"].pack(side="left", padx=(0, 8))
            
            # Статусы справа
            status_frame = ctk.CTkFrame(topbar, fg_color="transparent")
            status_frame.pack(side="right", padx=16)
            
            self.backend_status = StatusBadge(status_frame, "Backend", False)
            self.backend_status.pack(side="left", padx=(0, 16))
            
            self.frontend_status = StatusBadge(status_frame, "Frontend", False)
            self.frontend_status.pack(side="left", padx=(0, 16))
            
            self.kiosk_status = StatusBadge(status_frame, "Kiosk", False)
            self.kiosk_status.pack(side="left", padx=(0, 16))
            
            # Кнопки управления
            ctk.CTkButton(
                status_frame, text="Запустить всё", width=110, height=32,
                font=ctk.CTkFont(family=FONTS['small'][0], size=11, weight='bold'),
                fg_color=COLORS['success'], hover_color=COLORS['success_hover'],
                corner_radius=6, command=self._start_all
            ).pack(side="left", padx=(0, 8))
            
            ctk.CTkButton(
                status_frame, text="Остановить", width=100, height=32,
                font=ctk.CTkFont(family=FONTS['small'][0], size=11),
                fg_color=COLORS['border'], hover_color=COLORS['danger'],
                corner_radius=6, command=self._stop_all
            ).pack(side="left", padx=(0, 8))
            
            # Кнопка киоска
            ctk.CTkButton(
                status_frame, text="🖥️ Киоск", width=90, height=32,
                font=ctk.CTkFont(family=FONTS['small'][0], size=11),
                fg_color=COLORS['warning'], hover_color=COLORS['accent_hover'],
                corner_radius=6, command=self._start_kiosk
            ).pack(side="left", padx=(0, 8))
            
            # Кнопка открытия браузера в трее
            ctk.CTkButton(
                status_frame, text="🌐 Браузер", width=90, height=32,
                font=ctk.CTkFont(family=FONTS['small'][0], size=11),
                fg_color=COLORS['accent'], hover_color=COLORS['accent_hover'],
                corner_radius=6, command=self._open_tray_browser
            ).pack(side="left", padx=(0, 8))
            
            # Кнопка выхода
            ctk.CTkButton(
                status_frame, text="Выход ✕", width=80, height=32,
                font=ctk.CTkFont(family=FONTS['small'][0], size=11),
                fg_color=COLORS['border'], hover_color=COLORS['danger'],
                corner_radius=6, command=self._full_exit
            ).pack(side="left")
            
            # === CONTENT AREA ===
            self.content = ctk.CTkFrame(main, fg_color="transparent")
            self.content.pack(fill="both", expand=True, padx=16, pady=16)
            
            # Создаём страницы
            self.pages["backend"] = ServiceCard(self.content, "Backend (FastAPI)", self.backend_manager)
            self.pages["frontend"] = ServiceCard(self.content, "Frontend (React)", self.frontend_manager)
            
            # Показываем первую страницу
            self.pages["backend"].pack(fill="both", expand=True)
        
        def _switch_page(self, page_name: str):
            if page_name == self.current_page:
                return
            
            # Скрываем текущую
            self.pages[self.current_page].pack_forget()
            
            # Обновляем кнопки (меняем цвет)
            self.sidebar_buttons[self.current_page].configure(
                fg_color=COLORS['border'], hover_color=COLORS['bg_sidebar']
            )
            self.sidebar_buttons[page_name].configure(
                fg_color=COLORS['accent'], hover_color=COLORS['accent_hover']
            )
            
            # Показываем новую
            self.pages[page_name].pack(fill="both", expand=True)
            self.current_page = page_name
        
        def _start_all(self):
            # ОБЯЗАТЕЛЬНО сначала останавливаем всё
            self._stop_all()
            time.sleep(1)  # Даём время освободить ресурсы
            
            # Принудительно убиваем процессы на портах
            killed_8000 = kill_process_on_port(8000)
            killed_5173 = kill_process_on_port(5173)
            if killed_8000:
                self.pages["backend"].log.append(f"[SYSTEM] Убиты процессы на порту 8000: {killed_8000}")
            if killed_5173:
                self.pages["frontend"].log.append(f"[SYSTEM] Убиты процессы на порту 5173: {killed_5173}")
            
            if killed_8000 or killed_5173:
                time.sleep(1)  # Даём время освободить порты
            
            # Запускаем бэкенд
            if not self.backend_manager.is_running:
                self.pages["backend"].start()
            
            # Ждём запуска бэкенда
            time.sleep(2)
            
            # Запускаем фронтенд
            if not self.frontend_manager.is_running:
                self.pages["frontend"].start()
            
            # Ждём запуска фронтенда
            time.sleep(3)
            
            # Запускаем киоск
            self._start_kiosk()
        
        def _start_kiosk(self):
            """Запуск киоска"""
            if self.kiosk_manager.is_running:
                self.pages[self.current_page].log.append("[SYSTEM] Киоск уже запущен")
                return
            
            # Полный путь к dashboard_kiosk.pyw
            kiosk_script = LAUNCHER_DIR / "dashboard_kiosk.pyw"
            
            if not kiosk_script.exists():
                self.pages[self.current_page].log.append(f"[ERROR] Файл не найден: {kiosk_script}")
                self.pages[self.current_page].log.append(f"[ERROR] LAUNCHER_DIR: {LAUNCHER_DIR}")
                return
            
            # Получаем геометрию нужного монитора
            monitors = get_monitors()
            kiosk_cmd = [PYTHON_EXE, str(kiosk_script)]

            if monitors:
                # Убедимся, что индекс не выходит за пределы списка
                target_index = min(self._kiosk_monitor, len(monitors) - 1)
                target_monitor = monitors[target_index]
                
                geom = target_monitor
                geometry_str = f"{geom['left']},{geom['top']},{geom['width']},{geom['height']}"
                
                kiosk_cmd.extend(["--geometry", geometry_str])
                self.pages[self.current_page].log.append(f"[SYSTEM] Запуск киоска на мониторе {target_index + 1} с геометрией {geometry_str}...")

            else:
                # Если мониторы не найдены, используем старый метод
                kiosk_cmd.extend(["--monitor", str(self._kiosk_monitor)])
                self.pages[self.current_page].log.append(f"[SYSTEM] Запуск киоска на мониторе {self._kiosk_monitor + 1} (мониторы не определены)...")

            self.kiosk_manager.cmd = kiosk_cmd
            
            # self.pages[self.current_page].log.append(f"[SYSTEM] Команда: {' '.join(kiosk_cmd)}")
            # if self.kiosk_manager.start():
            #     self.pages[self.current_page].log.append(f"[SYSTEM] Киоск запущен (PID: {self.kiosk_manager.pid})")
            # else:
            #     self.pages[self.current_page].log.append("[ERROR] Не удалось запустить киоск")
            self.pages[self.current_page].log.append("[SYSTEM] Запуск киоска отключен (только Backend + Frontend)")
        
        def _stop_all(self):
            # Сначала киоск
            if self.kiosk_manager.is_running:
                self.kiosk_manager.stop()
                self.pages[self.current_page].log.append("[SYSTEM] Киоск остановлен")
            
            # Потом сервисы
            if self.frontend_manager.is_running:
                self.pages["frontend"].stop()
            if self.backend_manager.is_running:
                self.pages["backend"].stop()
            
            # Принудительно убиваем оставшиеся процессы на портах
            time.sleep(0.5)
            kill_process_on_port(8000)
            kill_process_on_port(5173)
        
        def _open_tray_browser(self):
            """Открыть браузер в трее (из tray_kiosk.py)"""
            if self.chrome_process and self.chrome_process.poll() is None:
                self.pages[self.current_page].log.append("[SYSTEM] Браузер уже запущен")
                return
            
            # Ищем Chrome
            import shutil
            chrome_path = None
            
            if sys.platform == 'win32':
                chrome_paths = [
                    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
                    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
                    os.path.expandvars(r"%LocalAppData%\Google\Chrome\Application\chrome.exe"),
                ]
                for p in chrome_paths:
                    if os.path.exists(p):
                        chrome_path = p
                        break
            
            if not chrome_path:
                self.pages[self.current_page].log.append("[ERROR] Chrome не найден")
                return
            
            # Создаём профиль
            if not os.path.exists(BROWSER_PROFILE_DIR):
                os.makedirs(BROWSER_PROFILE_DIR)
            
            # Аргументы запуска
            args = [
                chrome_path,
                f'--app={BROWSER_URL}',
                '--window-size=1000,700',
                f'--user-data-dir={BROWSER_PROFILE_DIR}',
                '--no-first-run'
            ]
            
            try:
                self.chrome_process = subprocess.Popen(args)
                self.pages[self.current_page].log.append(f"[SYSTEM] Браузер запущен (PID: {self.chrome_process.pid})")
                
                # Запускаем поток для поиска окна и настройки трея
                threading.Thread(target=self._setup_browser_window, daemon=True).start()
                
            except Exception as e:
                self.pages[self.current_page].log.append(f"[ERROR] Ошибка запуска браузера: {e}")
        
        def _find_chrome_window(self):
            """Ищет окно Chrome"""
            if not self.chrome_process:
                return None
            
            hwnds = []
            
            def callback(hwnd, _):
                if win32gui.IsWindowVisible(hwnd):
                    _, found_pid = win32process.GetWindowThreadProcessId(hwnd)
                    try:
                        handle = win32api.OpenProcess(win32con.PROCESS_QUERY_INFORMATION | win32con.PROCESS_VM_READ, False, found_pid)
                        proc_path = win32process.GetModuleFileNameEx(handle, 0)
                        win32api.CloseHandle(handle)
                        
                        if "chrome.exe" in proc_path.lower():
                            if win32gui.GetWindowText(hwnd):
                                hwnds.append(hwnd)
                    except:
                        pass
            
            win32gui.EnumWindows(callback, None)
            return hwnds[0] if hwnds else None
        
        def _remove_taskbar_icon(self):
            """Убирает кнопку из панели задач"""
            if not self.chrome_hwnd:
                return
            
            try:
                style = win32gui.GetWindowLong(self.chrome_hwnd, win32con.GWL_EXSTYLE)
                
                if not (style & win32con.WS_EX_TOOLWINDOW):
                    new_style = (style | win32con.WS_EX_TOOLWINDOW) & ~win32con.WS_EX_APPWINDOW
                    win32gui.SetWindowLong(self.chrome_hwnd, win32con.GWL_EXSTYLE, new_style)
                    
                    win32gui.SetWindowPos(
                        self.chrome_hwnd, 0, 0, 0, 0, 0,
                        win32con.SWP_NOMOVE | win32con.SWP_NOSIZE | 
                        win32con.SWP_NOZORDER | win32con.SWP_FRAMECHANGED
                    )
                    self.pages[self.current_page].log.append("[SYSTEM] Иконка убрана из панели задач")
            except Exception as e:
                self.pages[self.current_page].log.append(f"[ERROR] Ошибка скрытия иконки: {e}")
        
        def _setup_browser_window(self):
            """Настройка окна браузера"""
            time.sleep(2)
            
            # Ищем окно
            for i in range(10):
                hwnd = self._find_chrome_window()
                if hwnd:
                    self.chrome_hwnd = hwnd
                    self.pages[self.current_page].log.append(f"[SYSTEM] Окно найдено (HWND: {hwnd})")
                    self._remove_taskbar_icon()
                    self.pages[self.current_page].log.append("[SYSTEM] Управление браузером доступно в меню трея Ekranchik")
                    break
                time.sleep(1)
        
        def _toggle_browser_visibility(self):
            """Показать/скрыть браузер"""
            if not self.chrome_hwnd:
                self.chrome_hwnd = self._find_chrome_window()
            
            if not self.chrome_hwnd:
                return
            
            if self.chrome_is_visible:
                win32gui.ShowWindow(self.chrome_hwnd, win32con.SW_HIDE)
                self.chrome_is_visible = False
            else:
                win32gui.ShowWindow(self.chrome_hwnd, win32con.SW_SHOW)
                win32gui.SetForegroundWindow(self.chrome_hwnd)
                self.chrome_is_visible = True
        
        def _close_browser(self):
            """Закрыть браузер"""
            if self.chrome_process:
                try:
                    self.chrome_process.terminate()
                except:
                    pass
                self.chrome_process = None
                self.chrome_hwnd = None
                self.chrome_is_visible = True
        
        def _start_log_updates(self):
            def update():
                self.pages["backend"].update_log()
                self.pages["frontend"].update_log()
                self._update_status_panel()
                self.root.after(100, update)
            update()
        
        def _update_status_panel(self):
            if self.backend_manager.is_running:
                self.backend_status.set_status(True, f"Backend: PID {self.backend_manager.pid}")
            else:
                self.backend_status.set_status(False, "Backend: Остановлен")
            
            if self.frontend_manager.is_running:
                self.frontend_status.set_status(True, f"Frontend: PID {self.frontend_manager.pid}")
            else:
                self.frontend_status.set_status(False, "Frontend: Остановлен")
            
            if self.kiosk_manager.is_running:
                self.kiosk_status.set_status(True, f"Kiosk: PID {self.kiosk_manager.pid}")
            else:
                self.kiosk_status.set_status(False, "Kiosk: Остановлен")
        
        def _setup_tray(self):
            """Настройка System Tray"""
            from icons import get_tray_icon
            icon_image = get_tray_icon()
            
            menu = pystray.Menu(
                pystray.MenuItem("Показать окно", self._show_from_tray, default=True),
                pystray.Menu.SEPARATOR,
                pystray.MenuItem("Запустить всё", self._start_all),
                pystray.MenuItem("Остановить всё", self._stop_all),
                pystray.Menu.SEPARATOR,
                pystray.MenuItem("Запустить Backend", lambda: self.pages["backend"].start()),
                pystray.MenuItem("Запустить Frontend", lambda: self.pages["frontend"].start()),
                pystray.MenuItem("Запустить Kiosk", lambda: self._start_kiosk()),
                pystray.Menu.SEPARATOR,
                pystray.MenuItem("Показать/Скрыть браузер", lambda: self._toggle_browser_visibility()),
                pystray.MenuItem("Закрыть браузер", lambda: self._close_browser()),
                pystray.Menu.SEPARATOR,
                pystray.MenuItem("Выход", self._full_exit)
            )
            
            self.tray_icon = pystray.Icon("ekranchik", icon_image, "Ekranchik Modern", menu)
            
            def run_tray():
                self.tray_icon.run()
            
            self.tray_thread = threading.Thread(target=run_tray, daemon=True)
            self.tray_thread.start()
        
        def _show_from_tray(self):
            self.root.after(0, self.root.deiconify)
        
        def _hide_to_tray(self):
            self.root.withdraw()
        
        def _on_close_request(self):
            """При закрытии окна — сворачиваем в трей"""
            self._hide_to_tray()
        
        def _full_exit(self):
            self._stop_all()
            
            # Закрываем браузер
            self._close_browser()
            
            if self.tray_icon:
                self.tray_icon.stop()
            self.root.quit()
            self.root.destroy()
        
        def run(self):
            # Сразу сворачиваем в трей (без показа окна)
            self.root.withdraw()
            
            # Автоматически запускаем всё при старте
            self._kiosk_monitor = 1 if len(get_monitors()) > 1 else 0  # Второй монитор если есть
            self.root.after(100, self._start_all)
            self.root.mainloop()
        
        def _show_autostart_dialog(self):
            """Показывает диалог автозапуска при старте"""
            import tkinter as tk
            import tkinter.messagebox as messagebox
            
            # Определяем мониторы
            monitors = get_monitors()
            monitor_count = len(monitors)
            
            # Создаём кастомное диалоговое окно
            dialog = tk.Toplevel(self.root)
            dialog.title("Автозапуск Ekranchik")
            dialog.geometry("450x350")
            dialog.resizable(False, False)
            dialog.configure(bg='#2b2b2b')
            dialog.transient(self.root)
            dialog.grab_set()
            
            # Центрируем окно
            dialog.update_idletasks()
            x = (dialog.winfo_screenwidth() // 2) - (450 // 2)
            y = (dialog.winfo_screenheight() // 2) - (350 // 2)
            dialog.geometry(f"450x350+{x}+{y}")
            
            # Заголовок
            tk.Label(
                dialog, text="Запустить все компоненты?",
                font=('Segoe UI', 14, 'bold'),
                bg='#2b2b2b', fg='#e0e0e0'
            ).pack(pady=(20, 10))
            
            # Список компонентов
            components_frame = tk.Frame(dialog, bg='#2b2b2b')
            components_frame.pack(pady=10)
            
            for comp in ["• Backend (FastAPI)", "• Frontend (React)", "• Kiosk (Dashboard)"]:
                tk.Label(
                    components_frame, text=comp,
                    font=('Segoe UI', 11),
                    bg='#2b2b2b', fg='#a0a0a0'
                ).pack(anchor='w', padx=40)
            
            # Выбор монитора для киоска
            tk.Label(
                dialog, text="Монитор для киоска:",
                font=('Segoe UI', 11, 'bold'),
                bg='#2b2b2b', fg='#e0e0e0'
            ).pack(pady=(20, 5))
            
            # По умолчанию второй монитор если есть, иначе первый
            default_monitor = 1 if monitor_count > 1 else 0
            monitor_var = tk.IntVar(value=default_monitor)
            
            monitor_frame = tk.Frame(dialog, bg='#2b2b2b')
            monitor_frame.pack()
            
            # Показываем только реальные мониторы
            if monitor_count == 0:
                tk.Label(
                    monitor_frame, text="⚠ Мониторы не обнаружены",
                    font=('Segoe UI', 10),
                    bg='#2b2b2b', fg='#ffb74d'
                ).pack(anchor='w', pady=2)
            else:
                for i, mon in enumerate(monitors):
                    label_text = f"Монитор {i + 1}: {mon['width']}x{mon['height']}"
                    if i == 0:
                        label_text += " (основной)"
                    elif i == 1:
                        label_text += " (рекомендуется)"
                    
                    tk.Radiobutton(
                        monitor_frame, text=label_text,
                        variable=monitor_var, value=i,
                        font=('Segoe UI', 10),
                        bg='#2b2b2b', fg='#a0a0a0',
                        selectcolor='#1e1e1e', activebackground='#2b2b2b',
                        activeforeground='#e0e0e0'
                    ).pack(anchor='w', pady=2)
            
            # Результат
            result = {'start': False, 'monitor': default_monitor}
            
            def on_start():
                result['start'] = True
                result['monitor'] = monitor_var.get()
                dialog.destroy()
            
            def on_cancel():
                result['start'] = False
                dialog.destroy()
            
            # Кнопки
            btn_frame = tk.Frame(dialog, bg='#2b2b2b')
            btn_frame.pack(pady=30, side='bottom')
            
            start_btn = tk.Button(
                btn_frame, text="Запустить",
                command=on_start,
                font=('Segoe UI', 11, 'bold'),
                bg='#4caf50', fg='white',
                activebackground='#66bb6a',
                activeforeground='white',
                relief='flat', 
                width=12, height=2,
                cursor='hand2',
                borderwidth=0
            )
            start_btn.pack(side='left', padx=10)
            
            cancel_btn = tk.Button(
                btn_frame, text="Отмена",
                command=on_cancel,
                font=('Segoe UI', 11),
                bg='#3d3d3d', fg='#e0e0e0',
                activebackground='#4d4d4d',
                activeforeground='#ffffff',
                relief='flat', 
                width=12, height=2,
                cursor='hand2',
                borderwidth=0
            )
            cancel_btn.pack(side='left', padx=10)
            
            # Обработка закрытия окна
            dialog.protocol("WM_DELETE_WINDOW", on_cancel)
            
            # Ждём закрытия диалога
            dialog.wait_window()
            
            if result['start']:
                # Сохраняем выбранный монитор для киоска
                self._kiosk_monitor = result['monitor']
                
                # Запускаем всё
                self._start_all()
                
                # Сворачиваем в трей через 1 секунду
                self.root.after(1000, self._hide_to_tray)


class ConsoleMode:
    """Консольный режим без GUI"""
    
    def __init__(self):
        self.backend_manager = ProcessManager("Backend", BACKEND_CMD, BACKEND_DIR)
        self.frontend_manager = ProcessManager("Frontend", FRONTEND_CMD, FRONTEND_DIR)
        self.kiosk_manager = ProcessManager("Kiosk", KIOSK_CMD, LAUNCHER_DIR)
    
    def run(self):
        print("\n" + "="*60)
        print("  Ekranchik Modern - Console Mode")
        print("="*60 + "\n")
        
        print("Запуск Backend...")
        if self.backend_manager.start():
            print("Backend запущен")
        else:
            print("Не удалось запустить Backend")
            return
        
        time.sleep(2)
        
        print("\nЗапуск Frontend...")
        if self.frontend_manager.start():
            print("Frontend запущен")
        else:
            print("Не удалось запустить Frontend")
            self.backend_manager.stop()
            return
        
        time.sleep(3)
        
        # print("\nЗапуск Kiosk...")
        # if self.kiosk_manager.start():
        #     print("Kiosk запущен")
        # else:
        #     print("Не удалось запустить Kiosk")
        #     # Продолжаем работу без киоска
        print("\n[INFO] Запуск киоска отключен (только Backend + Frontend)")
        
        print("\n" + "="*60)
        print("Система запущена! (Ctrl+C для остановки)")
        print("="*60 + "\n")
        
        try:
            while True:
                while True:
                    msg = self.backend_manager.get_output()
                    if msg is None:
                        break
                    print(f"[BACKEND] {msg}")
                
                while True:
                    msg = self.frontend_manager.get_output()
                    if msg is None:
                        break
                    print(f"[FRONTEND] {msg}")
                
                while True:
                    msg = self.kiosk_manager.get_output()
                    if msg is None:
                        break
                    print(f"[KIOSK] {msg}")
                
                time.sleep(0.1)
        
        except KeyboardInterrupt:
            print("\n\nОстановка системы...")
            self.kiosk_manager.stop()
            self.frontend_manager.stop()
            self.backend_manager.stop()
            print("Система остановлена")


def run_startup_diagnostics() -> dict:
    """
    Запускает диагностику системы при старте.
    Возвращает словарь с результатами проверок.
    """
    import shutil
    
    results = {
        'errors': [],
        'warnings': [],
        'info': [],
        'checks': {}
    }
    
    # === 1. Режим запуска ===
    is_frozen = getattr(sys, 'frozen', False)
    results['info'].append(f"Режим запуска: {'EXE (PyInstaller)' if is_frozen else 'Python скрипт'}")
    results['info'].append(f"sys.executable: {sys.executable}")
    results['checks']['frozen'] = is_frozen
    
    if is_frozen:
        results['info'].append(f"_MEIPASS: {getattr(sys, '_MEIPASS', 'N/A')}")
    
    # === 2. Пути ===
    results['info'].append(f"BASE_DIR: {BASE_DIR}")
    results['info'].append(f"BACKEND_DIR: {BACKEND_DIR}")
    results['info'].append(f"FRONTEND_DIR: {FRONTEND_DIR}")
    
    # === 3. Проверка директорий ===
    if not BASE_DIR.exists():
        results['errors'].append(f"BASE_DIR не существует: {BASE_DIR}")
        results['checks']['base_dir'] = False
    else:
        results['checks']['base_dir'] = True
    
    if not BACKEND_DIR.exists():
        results['errors'].append(f"BACKEND_DIR не существует: {BACKEND_DIR}")
        results['checks']['backend_dir'] = False
    else:
        results['checks']['backend_dir'] = True
        # Проверяем структуру бэкенда
        app_main = BACKEND_DIR / "app" / "main.py"
        if not app_main.exists():
            results['warnings'].append(f"app/main.py не найден в {BACKEND_DIR}")
        requirements = BACKEND_DIR / "requirements.txt"
        if not requirements.exists():
            results['warnings'].append(f"requirements.txt не найден в {BACKEND_DIR}")
    
    if not FRONTEND_DIR.exists():
        results['errors'].append(f"FRONTEND_DIR не существует: {FRONTEND_DIR}")
        results['checks']['frontend_dir'] = False
    else:
        results['checks']['frontend_dir'] = True
        # Проверяем структуру фронтенда
        package_json = FRONTEND_DIR / "package.json"
        if not package_json.exists():
            results['warnings'].append(f"package.json не найден в {FRONTEND_DIR}")
        node_modules = FRONTEND_DIR / "node_modules"
        if not node_modules.exists():
            results['warnings'].append(f"node_modules не найден - нужен npm install")
    
    # === 4. Проверка Python ===
    results['info'].append(f"PYTHON_EXE: {PYTHON_EXE}")
    
    python_found = shutil.which(PYTHON_EXE) if is_frozen else True
    if is_frozen and not python_found:
        # Пробуем найти Python разными способами
        python_paths = [
            shutil.which("python"),
            shutil.which("python3"),
            shutil.which("py"),
        ]
        python_found = any(python_paths)
        if python_found:
            found_path = next(p for p in python_paths if p)
            results['info'].append(f"Python найден: {found_path}")
        else:
            results['errors'].append("Python не найден в PATH! Бэкенд не запустится.")
            results['errors'].append("Установите Python и добавьте в PATH")
    
    results['checks']['python'] = bool(python_found)
    
    # Аргументы для скрытого запуска
    hidden_args = get_hidden_subprocess_args()
    
    # Проверяем версию Python
    try:
        if is_frozen:
            proc = subprocess.run(
                [PYTHON_EXE, "--version"],
                capture_output=True, text=True, timeout=5,
                **hidden_args
            )
            if proc.returncode == 0:
                results['info'].append(f"Python версия: {proc.stdout.strip()}")
            else:
                results['warnings'].append(f"Не удалось получить версию Python: {proc.stderr}")
        else:
            results['info'].append(f"Python версия: {sys.version.split()[0]}")
    except Exception as e:
        results['warnings'].append(f"Ошибка проверки версии Python: {e}")
    
    # === 5. Проверка uvicorn ===
    try:
        proc = subprocess.run(
            [PYTHON_EXE, "-c", "import uvicorn; print(uvicorn.__version__)"],
            capture_output=True, text=True, timeout=10,
            cwd=str(BACKEND_DIR),
            **hidden_args
        )
        if proc.returncode == 0:
            results['info'].append(f"uvicorn версия: {proc.stdout.strip()}")
            results['checks']['uvicorn'] = True
        else:
            results['errors'].append(f"uvicorn не установлен: {proc.stderr.strip()}")
            results['errors'].append("Выполните: pip install uvicorn")
            results['checks']['uvicorn'] = False
    except subprocess.TimeoutExpired:
        results['warnings'].append("Таймаут проверки uvicorn")
        results['checks']['uvicorn'] = None
    except Exception as e:
        results['warnings'].append(f"Ошибка проверки uvicorn: {e}")
        results['checks']['uvicorn'] = None
    
    # === 6. Проверка npm ===
    npm_path = shutil.which("npm")
    if npm_path:
        results['info'].append(f"npm найден: {npm_path}")
        results['checks']['npm'] = True
        try:
            proc = subprocess.run(
                ["npm", "--version"],
                capture_output=True, text=True, timeout=5,
                shell=True,
                **hidden_args
            )
            if proc.returncode == 0:
                results['info'].append(f"npm версия: {proc.stdout.strip()}")
        except:
            pass
    else:
        results['warnings'].append("npm не найден в PATH - фронтенд не запустится")
        results['checks']['npm'] = False
    
    # === 7. Проверка .env ===
    env_file = BACKEND_DIR / ".env"
    if env_file.exists():
        results['info'].append(f".env файл найден: {env_file}")
        results['checks']['env_file'] = True
    else:
        results['warnings'].append(f".env файл не найден: {env_file}")
        env_example = BACKEND_DIR / ".env.example"
        if env_example.exists():
            results['warnings'].append("Скопируйте .env.example в .env")
        results['checks']['env_file'] = False
    
    # === 8. Проверка GUI ===
    results['checks']['gui'] = HAS_GUI
    results['checks']['tray'] = HAS_TRAY
    if not HAS_GUI:
        results['warnings'].append("GUI библиотеки недоступны (customtkinter, PIL)")
    
    # === 9. Проверка theme.json ===
    if THEME_PATH.exists():
        results['info'].append(f"theme.json найден: {THEME_PATH}")
        results['checks']['theme'] = True
    else:
        results['warnings'].append(f"theme.json не найден: {THEME_PATH}")
        results['checks']['theme'] = False
    
    return results


def print_diagnostics(results: dict):
    """Выводит результаты диагностики в консоль"""
    print("\n" + "=" * 60)
    print("  ДИАГНОСТИКА EKRANCHIK LAUNCHER")
    print("=" * 60)
    
    print("\n[INFO] Информация о системе:")
    for info in results['info']:
        print(f"  • {info}")
    
    if results['warnings']:
        print("\n[WARNING] Предупреждения:")
        for warn in results['warnings']:
            print(f"  ⚠ {warn}")
    
    if results['errors']:
        print("\n[ERROR] Ошибки:")
        for err in results['errors']:
            print(f"  ✗ {err}")
    
    print("\n[CHECKS] Статус проверок:")
    for check, status in results['checks'].items():
        icon = "✓" if status else ("?" if status is None else "✗")
        print(f"  {icon} {check}: {status}")
    
    print("\n" + "=" * 60)
    
    return len(results['errors']) == 0


def show_diagnostics_dialog(results: dict):
    """Показывает диалог с результатами диагностики (если есть ошибки)"""
    if not HAS_GUI:
        return
    
    has_errors = len(results['errors']) > 0
    has_warnings = len(results['warnings']) > 0
    
    if not has_errors and not has_warnings:
        return  # Всё ок, не показываем диалог
    
    try:
        import tkinter.messagebox as messagebox
        
        title = "Ошибки запуска" if has_errors else "Предупреждения"
        
        message_parts = []
        
        if results['errors']:
            message_parts.append("ОШИБКИ:")
            for err in results['errors']:
                message_parts.append(f"• {err}")
        
        if results['warnings']:
            if message_parts:
                message_parts.append("")
            message_parts.append("ПРЕДУПРЕЖДЕНИЯ:")
            for warn in results['warnings'][:5]:  # Показываем только первые 5
                message_parts.append(f"• {warn}")
            if len(results['warnings']) > 5:
                message_parts.append(f"... и ещё {len(results['warnings']) - 5}")
        
        message = "\n".join(message_parts)
        
        if has_errors:
            messagebox.showerror(title, message)
        else:
            messagebox.showwarning(title, message)
            
    except Exception as e:
        print(f"Не удалось показать диалог: {e}")


def main():
    """Главная функция"""
    
    # Запускаем диагностику
    print("\nЗапуск диагностики...")
    results = run_startup_diagnostics()
    
    # Выводим в консоль
    diagnostics_ok = print_diagnostics(results)
    
    # Критические ошибки - не запускаемся
    if not results['checks'].get('backend_dir', False):
        print(f"\n[FATAL] Директория бэкенда не найдена: {BACKEND_DIR}")
        print("Проверьте расположение EXE файла относительно проекта")
        show_diagnostics_dialog(results)
        sys.exit(1)
    
    if not results['checks'].get('frontend_dir', False):
        print(f"\n[FATAL] Директория фронтенда не найдена: {FRONTEND_DIR}")
        show_diagnostics_dialog(results)
        sys.exit(1)
    
    if not results['checks'].get('python', False):
        print(f"\n[FATAL] Python не найден в системе!")
        show_diagnostics_dialog(results)
        sys.exit(1)
    
    # Показываем предупреждения если есть
    if results['warnings'] or results['errors']:
        show_diagnostics_dialog(results)
    
    # Запускаем приложение
    if HAS_GUI and "--console" not in sys.argv:
        app = LauncherApp()
        # Передаём результаты диагностики в приложение
        app.startup_diagnostics = results
        app.run()
    else:
        if not HAS_GUI:
            print("GUI недоступен, запуск в консольном режиме")
        console = ConsoleMode()
        console.run()


if __name__ == "__main__":
    # Режим только диагностики
    if "--diagnose" in sys.argv or "--diag" in sys.argv:
        results = run_startup_diagnostics()
        print_diagnostics(results)
        input("\nНажмите Enter для выхода...")
        sys.exit(0 if len(results['errors']) == 0 else 1)
    
    main()
