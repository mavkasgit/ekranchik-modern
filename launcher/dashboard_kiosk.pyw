"""
Kiosk Mode Dashboard Application with Tray
Полноэкранный режим с управлением через трей.
Автоматически открывается на втором мониторе если он есть.
Переключение между экранами через меню трея.
"""
import sys

# === КРИТИЧНО: Устанавливаем AppUserModelID ДО импорта любых GUI библиотек ===
# Это позволяет Windows показывать нашу иконку в панели задач вместо иконки Python
if sys.platform == 'win32':
    import ctypes
    # Уникальный ID приложения
    APP_ID = 'Ekranchik.Dashboard.Kiosk.1.0'
    ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(APP_ID)

import webview
import time
import threading
from pathlib import Path

# --- Fix for Tray Menu Positioning on Windows ---
# Set DPI awareness to prevent menu from appearing in the center of the screen
if sys.platform == 'win32':
    try:
        from ctypes import windll
        # Per Monitor v2 (Windows 10 Creators Update+)
        windll.shcore.SetProcessDpiAwareness(2)
    except (AttributeError, OSError):
        try:
            # System Aware (older Windows)
            windll.user32.SetProcessDPIAware()
        except Exception as e:
            pass
# ------------------------------------------------

try:
    import pystray
    from PIL import Image, ImageDraw
    HAS_TRAY = True
except ImportError as e:
    HAS_TRAY = False
    sys.exit(1)

# Путь к иконке
ICON_FILE = Path(__file__).parent / "launcher.ico"

# Проверка наличия win32api для работы с мониторами
if sys.platform == 'win32':
    try:
        import win32api
        import win32con
        HAS_WIN32 = True
    except ImportError as e:
        HAS_WIN32 = False
else:
    HAS_WIN32 = False


def get_monitors():
    """
    Получает список мониторов.
    СОРТИРУЕТ их слева направо (по координате X).
    Это гарантирует, что monitors[0] - это самый левый, а monitors[1] - правее.
    """
    monitors = []
    
    if HAS_WIN32:
        try:
            monitor_handles = win32api.EnumDisplayMonitors()
            for handle in monitor_handles:
                monitor_info = win32api.GetMonitorInfo(handle[0])
                rc = monitor_info['Monitor']  # (left, top, right, bottom)
                is_primary = (monitor_info['Flags'] & win32con.MONITORINFOF_PRIMARY) == 1
                
                monitors.append({
                    'left': rc[0],
                    'top': rc[1],
                    'right': rc[2],
                    'bottom': rc[3],
                    'width': abs(rc[2] - rc[0]),
                    'height': abs(rc[3] - rc[1]),
                    'is_primary': bool(is_primary),
                    'name': 'Primary' if is_primary else 'Secondary'
                })
            
            # СОРТИРОВКА: Самое важное изменение!
            # Сортируем список по координате 'left'. 
            # Теперь monitors[0] всегда будет левым экраном, а monitors[1] - правым.
            monitors.sort(key=lambda m: m['left'])
            
            return monitors
            
        except Exception as e:
            pass
    
    # Fallback (заглушка)
    return [{
        'left': 0, 'top': 0, 'right': 1920, 'bottom': 1080,
        'width': 1920, 'height': 1080,
        'is_primary': True,
        'name': 'Fallback'
    }]


class KioskDashboard:
    def __init__(self, url: str = "http://localhost:5173", monitor_index: int = 0, geometry: dict = None):
        self.url = url
        self.window = None
        self.tray_icon = None
        self.is_fullscreen = True
        self.current_monitor_index = monitor_index # Текущий индекс монитора
        self.geometry = geometry
        self.is_idle_mode = False  # Флаг режима простоя
        self.original_url = url  # Сохраняем оригинальный URL
        
    def on_loaded(self):
        """Callback when page is loaded."""
        # Устанавливаем иконку окна после загрузки страницы
        self._set_window_icon()
        
    def on_closing(self):
        """Prevent closing via Alt+F4 or X button."""
        return False
    
    def _set_window_icon(self):
        """Устанавливает иконку окна через Windows API."""
        if sys.platform != 'win32' or not ICON_FILE.exists():
            return
        
        def do_set_icon():
            try:
                import ctypes
                
                # Константы Windows
                IMAGE_ICON = 1
                LR_LOADFROMFILE = 0x00000010
                LR_DEFAULTSIZE = 0x00000040
                WM_SETICON = 0x0080
                ICON_SMALL = 0
                ICON_BIG = 1
                GCL_HICON = -14
                GCL_HICONSM = -34
                
                # Загружаем иконку из файла (большую и маленькую)
                icon_big = ctypes.windll.user32.LoadImageW(
                    None, str(ICON_FILE), IMAGE_ICON,
                    48, 48,  # Большая иконка для Alt+Tab
                    LR_LOADFROMFILE
                )
                
                icon_small = ctypes.windll.user32.LoadImageW(
                    None, str(ICON_FILE), IMAGE_ICON,
                    16, 16,  # Маленькая иконка для заголовка
                    LR_LOADFROMFILE
                )
                
                if not icon_big:
                    return
                
                # Ищем окно по заголовку
                hwnd = ctypes.windll.user32.FindWindowW(None, "Ekranchik Dashboard")
                
                if not hwnd:
                    # Пробуем найти по частичному совпадению
                    EnumWindowsProc = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)
                    found_hwnd = [None]
                    
                    def enum_callback(hwnd_enum, lparam):
                        length = ctypes.windll.user32.GetWindowTextLengthW(hwnd_enum)
                        if length > 0:
                            buff = ctypes.create_unicode_buffer(length + 1)
                            ctypes.windll.user32.GetWindowTextW(hwnd_enum, buff, length + 1)
                            if "Ekranchik" in buff.value or "pywebview" in buff.value.lower():
                                found_hwnd[0] = hwnd_enum
                                return False
                        return True
                    
                    ctypes.windll.user32.EnumWindows(EnumWindowsProc(enum_callback), 0)
                    hwnd = found_hwnd[0]
                
                if hwnd:
                    # Устанавливаем иконку через WM_SETICON
                    ctypes.windll.user32.SendMessageW(hwnd, WM_SETICON, ICON_SMALL, icon_small or icon_big)
                    ctypes.windll.user32.SendMessageW(hwnd, WM_SETICON, ICON_BIG, icon_big)
                    
                    # Также устанавливаем через SetClassLongPtrW для панели задач
                    try:
                        SetClassLongPtrW = ctypes.windll.user32.SetClassLongPtrW
                        SetClassLongPtrW(hwnd, GCL_HICON, icon_big)
                        SetClassLongPtrW(hwnd, GCL_HICONSM, icon_small or icon_big)
                    except Exception as e:
                        pass
                else:
                    pass
                    
            except Exception as e:
                pass
        
        # Запускаем в отдельном потоке с задержкой
        threading.Thread(target=lambda: (time.sleep(0.5), do_set_icon()), daemon=True).start()
    
    def create_window(self):
        """Создание окна (изначально на выбранном мониторе)."""
        monitors = get_monitors()
        
        # Если передана жесткая геометрия (аргументы командной строки)
        if self.geometry:
            x, y = self.geometry['x'], self.geometry['y']
            width, height = self.geometry['width'], self.geometry['height']
        else:
            target_monitor = None
            # Если запрошенный монитор не существует или индекс некорректен, берем основной
            if self.current_monitor_index >= len(monitors) or self.current_monitor_index < 0:
                target_monitor = next((m for m in monitors if m['is_primary']), monitors[0])
                # Обновляем индекс на фактический
                self.current_monitor_index = monitors.index(target_monitor)
            else:
                target_monitor = monitors[self.current_monitor_index]
            
            x, y = target_monitor['left'], target_monitor['top']
            width, height = target_monitor['width'], target_monitor['height']

        self.window = webview.create_window(
            title='Ekranchik Dashboard',
            url=self.url,
            x=x,
            y=y,
            width=width,
            height=height,
            fullscreen=True,
            frameless=True,
            on_top=True,
            background_color='#1e293b'
        )
        
        self.window.events.loaded += self.on_loaded
        self.window.events.closing += self.on_closing
    
    def toggle_fullscreen(self):
        """Переключение полноэкранного режима."""
        if self.window:
            self.window.toggle_fullscreen()
            self.is_fullscreen = not self.is_fullscreen

    def switch_monitor(self):
        """Перемещение окна на следующий монитор."""
        if not self.window:
            return

        monitors = get_monitors()
        if len(monitors) < 2:
            return

        # 1. Вычисляем следующий индекс
        next_index = (self.current_monitor_index + 1) % len(monitors)
        target = monitors[next_index]

        # 2. ВАЖНО: Выходим из Fullscreen перед перемещением
        if self.is_fullscreen:
            self.window.toggle_fullscreen()
            time.sleep(0.2) # Даем винде время подумать

        # 3. Перемещаем и меняем размер
        self.window.move(target['left'], target['top'])
        self.window.resize(target['width'], target['height'])
        
        # 4. Обновляем внутренний индекс
        self.current_monitor_index = next_index

        # 5. Возвращаем Fullscreen обратно
        if self.is_fullscreen:
            time.sleep(0.2)
            self.window.toggle_fullscreen()

    def reload_page(self):
        if self.window:
            self.window.evaluate_js("location.reload()")
    
    def toggle_idle_screen(self):
        """Переключение режима простоя (часы)."""
        if not self.window:
            return
        
        if self.is_idle_mode:
            # Возвращаемся к дашборду
            self.is_idle_mode = False
            self.window.load_url(self.original_url)
        else:
            # Переключаемся на экран простоя
            self.is_idle_mode = True
            
            # Получаем путь к HTML файлу
            idle_html = Path(__file__).parent / "idle_clock.html"
            if idle_html.exists():
                idle_url = idle_html.as_uri()
                self.window.load_url(idle_url)
            else:
                self.is_idle_mode = False
    
    def quit_app(self):
        if self.tray_icon:
            self.tray_icon.stop()
        if self.window:
            self.window.events.closing -= self.on_closing
            self.window.destroy()
    
    def create_tray_icon(self):
        """Создание иконки в трее."""
        # Импортируем функцию создания иконки
        try:
            import sys
            from pathlib import Path
            
            # Добавляем путь к icons.py
            if getattr(sys, 'frozen', False):
                # Запуск из exe - icons.py в _MEIPASS
                icons_path = Path(sys._MEIPASS)
            else:
                # Обычный запуск
                icons_path = Path(__file__).parent
            
            if str(icons_path) not in sys.path:
                sys.path.insert(0, str(icons_path))
            
            from icons import get_kiosk_tray_icon
            image = get_kiosk_tray_icon()
            
        except Exception as e:
            # Fallback - создаём простую синюю иконку
            width = 64
            height = 64
            image = Image.new('RGB', (width, height), color='#2196F3')
            dc = ImageDraw.Draw(image)
            dc.rectangle([15, 15, 49, 49], fill='white')
            dc.text((22, 22), "K", fill='#2196F3') # font_size=20 # PIL по умолчанию не умеет в размер
        
        # Меню трея (с новыми пунктами и корректировкой текста)
        menu = pystray.Menu(
            pystray.MenuItem("Переключить монитор", lambda: self.switch_monitor()),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("🕐 Режим простоя (часы)", lambda: self.toggle_idle_screen()),
            pystray.MenuItem("Обновить страницу", lambda: self.reload_page()),
            pystray.MenuItem("Вкл/Выкл полный экран", lambda: self.toggle_fullscreen()),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Выход", lambda: self.quit_app())
        )
        
        self.tray_icon = pystray.Icon("ekranchik_kiosk", image, "Kiosk Control", menu)
    
    def run_tray(self):
        if self.tray_icon:
            self.tray_icon.run()
    
    def run(self):
        self.create_window()
        
        if HAS_TRAY:
            self.create_tray_icon()
            tray_thread = threading.Thread(target=self.run_tray, daemon=True)
            tray_thread.start()
        
        webview.start(debug=False)

# --- Main ---
import json

CONFIG_FILE = Path(__file__).parent / "kiosk_config.json"

def load_kiosk_config():
    """Загрузить конфиг киоска."""
    if CONFIG_FILE.exists():
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except:
            pass
    return {"url": "http://localhost:5173", "monitor": 1}

def save_kiosk_config(config):
    """Сохранить конфиг киоска."""
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=4, ensure_ascii=False)

def check_server_running(url: str, timeout: int = 5) -> bool:
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


class KioskLauncher:
    """GUI для выбора монитора и URL перед запуском киоска."""
    
    def __init__(self):
        import tkinter as tk
        self.tk = tk
        
        self.result = None
        self.monitors = get_monitors()
        self.config = load_kiosk_config()
        
        self.root = tk.Tk()
        self.root.title("Ekranchik Kiosk - Настройки")
        self.root.resizable(False, False)
        
        # Устанавливаем иконку
        if ICON_FILE.exists():
            try:
                self.root.iconbitmap(str(ICON_FILE))
            except:
                pass
        
        # Центрируем окно
        window_width = 500
        window_height = 320 + len(self.monitors) * 45
        screen_width = self.root.winfo_screenwidth()
        screen_height = self.root.winfo_screenheight()
        x = (screen_width - window_width) // 2
        y = (screen_height - window_height) // 2
        self.root.geometry(f"{window_width}x{window_height}+{x}+{y}")
        
        self._create_widgets()
    
    def _create_widgets(self):
        tk = self.tk
        
        # === URL секция ===
        url_frame = tk.LabelFrame(self.root, text="URL дашборда", font=("Segoe UI", 11))
        url_frame.pack(fill=tk.X, padx=20, pady=(15, 10))
        
        self.url_var = tk.StringVar(value=self.config.get("url", "http://localhost:5173"))
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
                  command=lambda: self.url_var.set("http://localhost"),
                  font=("Segoe UI", 9)).pack(side=tk.LEFT, padx=2)
        
        # === Монитор секция ===
        monitor_frame = tk.LabelFrame(self.root, text="Монитор", font=("Segoe UI", 11))
        monitor_frame.pack(fill=tk.BOTH, expand=True, padx=20, pady=10)
        
        saved_monitor = self.config.get("monitor", 1)
        if saved_monitor >= len(self.monitors):
            saved_monitor = 0
        
        self.monitor_var = tk.IntVar(value=saved_monitor)
        
        for i, mon in enumerate(self.monitors):
            primary_text = " ★" if mon.get('is_primary') else ""
            text = f"Монитор {i + 1}: {mon['width']}x{mon['height']}{primary_text} ({mon['name']})"
            
            rb = tk.Radiobutton(
                monitor_frame, 
                text=text,
                variable=self.monitor_var,
                value=i,
                font=("Segoe UI", 10),
                anchor="w",
                padx=10
            )
            rb.pack(fill=tk.X, pady=3)
        
        # === Кнопки ===
        btn_frame = tk.Frame(self.root)
        btn_frame.pack(pady=15)
        
        start_btn = tk.Button(
            btn_frame, 
            text="▶ Запустить",
            command=self._on_start,
            font=("Segoe UI", 12, "bold"),
            width=14,
            height=2,
            bg="#2E7D32",
            fg="white"
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
        url = self.url_var.get().strip()
        monitor = self.monitor_var.get()
        
        # Сохраняем настройки
        self.config["url"] = url
        self.config["monitor"] = monitor
        save_kiosk_config(self.config)
        
        self.result = {"url": url, "monitor": monitor}
        self.root.destroy()
    
    def _on_cancel(self):
        self.result = None
        self.root.destroy()
    
    def run(self):
        self.root.mainloop()
        return self.result


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--monitor', type=int, default=None, help='Monitor index (0=leftmost, 1=next, etc.)')
    parser.add_argument('--url', type=str, default=None, help='Dashboard URL')
    parser.add_argument('--geometry', type=str, default=None, help='Window geometry "x,y,width,height"')
    parser.add_argument('--no-gui', action='store_true', help='Skip GUI launcher, use args/config directly')
    args = parser.parse_args()
    
    # Если переданы аргументы или --no-gui, пропускаем GUI
    if args.no_gui or (args.url and args.monitor is not None):
        config = load_kiosk_config()
        url = args.url or config.get("url", "http://localhost:5173")
        monitor = args.monitor if args.monitor is not None else config.get("monitor", 1)
    else:
        # Показываем GUI для выбора
        launcher = KioskLauncher()
        result = launcher.run()
        
        if result is None:
            sys.exit(0)
        
        url = result["url"]
        monitor = result["monitor"]
    
    geometry = None
    if args.geometry:
        try:
            parts = list(map(int, args.geometry.split(',')))
            if len(parts) == 4:
                geometry = {'x': parts[0], 'y': parts[1], 'width': parts[2], 'height': parts[3]}
        except ValueError:
            pass

    if not check_server_running(url, timeout=3):
        # Показываем сообщение об ошибке
        try:
            import tkinter as tk
            from tkinter import messagebox
            root = tk.Tk()
            root.withdraw()
            messagebox.showerror("Ошибка", f"Сервер {url} не отвечает!\n\nУбедитесь что сервер запущен.")
            root.destroy()
        except:
            pass
        sys.exit(1)
    
    app = KioskDashboard(url=url, monitor_index=monitor, geometry=geometry)
    app.run()

if __name__ == "__main__":
    main()
