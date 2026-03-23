"""
Kiosk Mode Dashboard Application with Tray
Полноэкранный режим с управлением через трей.
Автоматически открывается на втором мониторе если он есть.
Переключение между экранами через меню трея.
"""
import sys

# === КРИТИЧНО: Устанавливаем AppUserModelID ДО импорта любых GUI библиотек ===
if sys.platform == 'win32':
    import ctypes
    APP_ID = 'Ekranchik.Dashboard.Kiosk.1.0'
    ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(APP_ID)

import webview
import time
import threading
from pathlib import Path

# --- Fix for Tray Menu Positioning on Windows ---
if sys.platform == 'win32':
    try:
        from ctypes import windll
        windll.shcore.SetProcessDpiAwareness(2)
    except (AttributeError, OSError):
        try:
            windll.user32.SetProcessDPIAware()
        except Exception:
            pass

try:
    import pystray
    from PIL import Image, ImageDraw
    HAS_TRAY = True
except ImportError:
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
    except ImportError:
        HAS_WIN32 = False
else:
    HAS_WIN32 = False


def get_monitors():
    """Получает список мониторов, отсортированные слева направо."""
    monitors = []
    
    if HAS_WIN32:
        try:
            monitor_handles = win32api.EnumDisplayMonitors()
            for handle in monitor_handles:
                monitor_info = win32api.GetMonitorInfo(handle[0])
                rc = monitor_info['Monitor']
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
            
            monitors.sort(key=lambda m: m['left'])
            return monitors
            
        except Exception as e:
            print(f"[ERROR] Ошибка получения мониторов: {e}")
    
    # Fallback
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
        self.current_monitor_index = monitor_index
        self.geometry = geometry
        self.is_idle_mode = False
        self.original_url = url
        self.auto_launch_enabled = False
        
    def on_loaded(self):
        """Callback when page is loaded."""
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
                
                # Загружаем иконку из файла
                icon = ctypes.windll.user32.LoadImageW(
                    None, str(ICON_FILE), 1,  # 1 = IMAGE_ICON
                    48, 48,
                    0x00000010  # LR_LOADFROMFILE
                )
                
                if not icon:
                    return
                
                # Ищем окно по заголовку
                hwnd = ctypes.windll.user32.FindWindowW(None, "Ekranchik Dashboard")
                
                if hwnd:
                    # Устанавливаем иконку
                    ctypes.windll.user32.SendMessageW(hwnd, 0x0080, 0, icon)  # WM_SETICON
                    ctypes.windll.user32.SendMessageW(hwnd, 0x0080, 1, icon)
                    
            except Exception as e:
                print(f"[WARNING] Не удалось установить иконку: {e}")
        
        # Запускаем в отдельном потоке с задержкой
        threading.Thread(target=lambda: (time.sleep(1), do_set_icon()), daemon=True).start()
    
    def create_window(self):
        """Создание окна на выбранном мониторе."""
        monitors = get_monitors()
        
        if self.geometry:
            x, y = self.geometry['x'], self.geometry['y']
            width, height = self.geometry['width'], self.geometry['height']
        else:
            if self.current_monitor_index >= len(monitors) or self.current_monitor_index < 0:
                target_monitor = next((m for m in monitors if m['is_primary']), monitors[0])
                self.current_monitor_index = monitors.index(target_monitor)
            else:
                target_monitor = monitors[self.current_monitor_index]
            
            x, y = target_monitor['left'], target_monitor['top']
            width, height = target_monitor['width'], target_monitor['height']

        # Показываем страницу ожидания пока сервер не запустится
        waiting_html = Path(__file__).parent / "waiting_server.html"
        initial_url = waiting_html.as_uri() if waiting_html.exists() else "about:blank"

        self.window = webview.create_window(
            title='Ekranchik Dashboard',
            url=initial_url,
            x=x,
            y=y,
            width=width,
            height=height,
            fullscreen=True,
            frameless=True,
            on_top=True,
            easy_drag=False,
            background_color='#1e293b'
        )
        
        self.window.events.loaded += self.on_loaded
        self.window.events.closing += self.on_closing
        
        # Запускаем поток для проверки сервера и загрузки дашборда
        threading.Thread(target=self._wait_and_load_dashboard, daemon=True).start()
    
    def _wait_and_load_dashboard(self):
        """Ждет пока сервер запустится и загружает дашборд."""
        import urllib.request
        import urllib.error
        
        max_wait = 300  # 5 минут максимум
        start_time = time.time()
        
        print(f"[INFO] Ожидание сервера {self.url}...")
        
        while time.time() - start_time < max_wait:
            try:
                urllib.request.urlopen(self.url, timeout=2)
                # Сервер доступен, загружаем дашборд
                print(f"[INFO] Сервер доступен! Загружаю дашборд...")
                if self.window:
                    self.window.load_url(self.url)
                return
            except (urllib.error.URLError, ConnectionRefusedError, Exception) as e:
                time.sleep(2)  # Проверяем каждые 2 секунды
        
        # Если сервер не запустился за 5 минут, показываем ошибку
        print("[ERROR] Сервер не запустился за 5 минут")
    
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

        next_index = (self.current_monitor_index + 1) % len(monitors)
        target = monitors[next_index]

        if self.is_fullscreen:
            self.window.toggle_fullscreen()
            time.sleep(0.3)

        self.window.move(target['left'], target['top'])
        self.window.resize(target['width'], target['height'])
        self.current_monitor_index = next_index

        if self.is_fullscreen:
            time.sleep(0.3)
            self.window.toggle_fullscreen()

    def reload_page(self):
        if self.window:
            self.window.evaluate_js("location.reload()")
    
    def toggle_idle_screen(self):
        """Переключение режима простоя (часы)."""
        if not self.window:
            return
        
        if self.is_idle_mode:
            self.is_idle_mode = False
            self.window.load_url(self.original_url)
        else:
            self.is_idle_mode = True
            idle_html = Path(__file__).parent / "idle_clock.html"
            if idle_html.exists():
                self.window.load_url(idle_html.as_uri())
            else:
                self.is_idle_mode = False
        
        # Обновляем меню трея и иконку
        self._update_tray_menu()
        self._update_tray_icon()
    
    def quit_app(self):
        if self.tray_icon:
            self.tray_icon.stop()
        if self.window:
            self.window.events.closing -= self.on_closing
            self.window.destroy()
    
    def toggle_auto_launch(self):
        """Переключение режима автозапуска при втором мониторе."""
        self.auto_launch_enabled = not self.auto_launch_enabled
        config = load_kiosk_config()
        config["auto_launch_on_second_monitor"] = self.auto_launch_enabled
        save_kiosk_config(config)
        self._update_tray_menu()
    
    def create_tray_icon(self):
        """Создание иконки в трее."""
        try:
            if getattr(sys, 'frozen', False):
                icons_path = Path(sys._MEIPASS)
            else:
                icons_path = Path(__file__).parent
            
            if str(icons_path) not in sys.path:
                sys.path.insert(0, str(icons_path))
            
            from icons import get_kiosk_tray_icon
            image = get_kiosk_tray_icon()
            
        except Exception as e:
            print(f"[WARNING] Не удалось загрузить иконку трея: {e}")
            # Fallback - простая синяя иконка
            image = Image.new('RGB', (64, 64), color='#2196F3')
            dc = ImageDraw.Draw(image)
            dc.rectangle([15, 15, 49, 49], fill='white')
        
        self._update_tray_menu()
        self.tray_icon = pystray.Icon("ekranchik_kiosk", image, "Kiosk Control", self.menu)
    
    def _update_tray_menu(self):
        """Обновление меню трея."""
        auto_launch_text = "✓ Автозапуск при 2м мониторе" if self.auto_launch_enabled else "○ Автозапуск при 2м мониторе"
        
        self.menu = pystray.Menu(
            pystray.MenuItem("Переключить монитор", lambda: self.switch_monitor()),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem(auto_launch_text, lambda: self.toggle_auto_launch()),
            pystray.MenuItem("🕐 Режим простоя (часы)", lambda: self.toggle_idle_screen()),
            pystray.MenuItem("Обновить страницу", lambda: self.reload_page()),
            pystray.MenuItem("Вкл/Выкл полный экран", lambda: self.toggle_fullscreen()),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Выход", lambda: self.quit_app())
        )
    
    def _update_tray_icon(self):
        """Обновление иконки трея в зависимости от режима."""
        try:
            if self.is_idle_mode:
                # Яркая красная иконка для режима простоя
                image = Image.new('RGB', (64, 64), color='#FF1744')
                dc = ImageDraw.Draw(image)
                
                # Белый круг часов
                dc.ellipse([8, 8, 56, 56], outline='white', width=4)
                
                # Стрелки часов (более толстые)
                dc.line([32, 32, 32, 16], fill='white', width=3)  # часовая
                dc.line([32, 32, 44, 32], fill='white', width=3)  # минутная
                
                # Центральная точка
                dc.ellipse([28, 28, 36, 36], fill='white')
            else:
                # Обычная синяя иконка
                if getattr(sys, 'frozen', False):
                    icons_path = Path(sys._MEIPASS)
                else:
                    icons_path = Path(__file__).parent
                
                if str(icons_path) not in sys.path:
                    sys.path.insert(0, str(icons_path))
                
                from icons import get_kiosk_tray_icon
                image = get_kiosk_tray_icon()
            
            if self.tray_icon:
                self.tray_icon.icon = image
        except Exception as e:
            print(f"[WARNING] Не удалось обновить иконку трея: {e}")
    
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


# --- Config Management ---
import json

CONFIG_FILE = Path(__file__).parent / "kiosk_config.json"

def load_kiosk_config():
    """Загрузить конфиг киоска."""
    if CONFIG_FILE.exists():
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            print(f"[WARNING] Ошибка чтения конфига: {e}")
    return {"url": "http://localhost:5173", "monitor": 1, "auto_launch_on_second_monitor": False}

def save_kiosk_config(config):
    """Сохранить конфиг киоска."""
    try:
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(config, f, indent=4, ensure_ascii=False)
    except Exception as e:
        print(f"[ERROR] Ошибка сохранения конфига: {e}")

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
        
        if ICON_FILE.exists():
            try:
                self.root.iconbitmap(str(ICON_FILE))
            except Exception:
                pass
        
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
        tk.Button(url_buttons_frame, text="172.17.11.8:5173", 
                  command=lambda: self.url_var.set("http://172.17.11.8:5173"),
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
        
        # === Опции секция ===
        options_frame = tk.LabelFrame(self.root, text="Опции", font=("Segoe UI", 11))
        options_frame.pack(fill=tk.X, padx=20, pady=10)
        
        self.auto_launch_var = tk.BooleanVar(value=self.config.get("auto_launch_on_second_monitor", False))
        auto_launch_cb = tk.Checkbutton(
            options_frame,
            text="Автоматически запускать при наличии второго монитора",
            variable=self.auto_launch_var,
            font=("Segoe UI", 10),
            anchor="w",
            padx=10
        )
        auto_launch_cb.pack(fill=tk.X, pady=8)
        
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
        auto_launch = self.auto_launch_var.get()
        
        self.config["url"] = url
        self.config["monitor"] = monitor
        self.config["auto_launch_on_second_monitor"] = auto_launch
        save_kiosk_config(self.config)
        
        self.result = {"url": url, "monitor": monitor, "auto_launch": auto_launch}
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
    
    config = load_kiosk_config()
    
    monitors = get_monitors()
    auto_launch_enabled = config.get("auto_launch_on_second_monitor", False)
    
    if auto_launch_enabled and len(monitors) >= 2 and not args.no_gui:
        args.no_gui = True
    
    if args.no_gui or (args.url and args.monitor is not None):
        url = args.url or config.get("url", "http://localhost:5173")
        monitor = args.monitor if args.monitor is not None else config.get("monitor", 1)
    else:
        launcher = KioskLauncher()
        result = launcher.run()
        
        if result is None:
            sys.exit(0)
        
        url = result["url"]
        monitor = result["monitor"]
        auto_launch_enabled = result.get("auto_launch", False)
    
    geometry = None
    if args.geometry:
        try:
            parts = list(map(int, args.geometry.split(',')))
            if len(parts) == 4:
                geometry = {'x': parts[0], 'y': parts[1], 'width': parts[2], 'height': parts[3]}
        except ValueError:
            print("[ERROR] Неверный формат геометрии")
    
    # Открываем киоск сразу, он будет ждать сервер
    app = KioskDashboard(url=url, monitor_index=monitor, geometry=geometry)
    app.auto_launch_enabled = auto_launch_enabled
    app.run()

if __name__ == "__main__":
    main()
