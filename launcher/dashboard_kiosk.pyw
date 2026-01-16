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
import logging
from pathlib import Path

# Настройка логирования
log_file = Path(__file__).parent / "kiosk.log"
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        logging.FileHandler(log_file, mode='w', encoding='utf-8'),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

# --- Fix for Tray Menu Positioning on Windows ---
# Set DPI awareness to prevent menu from appearing in the center of the screen
if sys.platform == 'win32':
    try:
        from ctypes import windll
        # Per Monitor v2 (Windows 10 Creators Update+)
        windll.shcore.SetProcessDpiAwareness(2)
        logger.info("Successfully set DPI awareness to Per Monitor v2.")
    except (AttributeError, OSError):
        try:
            # System Aware (older Windows)
            windll.user32.SetProcessDPIAware()
            logger.info("Successfully set DPI awareness to System Aware.")
        except Exception as e:
            logger.error(f"Failed to set DPI awareness: {e}")
# ------------------------------------------------

try:
    import pystray
    from PIL import Image, ImageDraw
    HAS_TRAY = True
except ImportError as e:
    HAS_TRAY = False
    logger.error(f"pystray import failed: {e}")
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
        logger.warning(f"win32api not available: {e}")
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
            
            # Логируем для проверки
            logger.info(f"--- Detected {len(monitors)} monitors (Sorted Left-to-Right) ---")
            for i, m in enumerate(monitors):
                logger.info(f"Monitor {i}: {m['width']}x{m['height']} at X={m['left']} ({m['name']})")
                
            return monitors
            
        except Exception as e:
            logger.error(f"win32api detailed detection failed: {e}")
    
    # Fallback (заглушка)
    logger.warning("get_monitors: Returning a single fallback monitor.")
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
        
    def on_loaded(self):
        """Callback when page is loaded."""
        logger.info(f"Dashboard loaded at {self.url}")
        # Устанавливаем иконку окна после загрузки страницы
        self._set_window_icon()
        
    def on_closing(self):
        """Prevent closing via Alt+F4 or X button."""
        logger.info("Close blocked - use tray menu to exit")
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
                    logger.warning(f"LoadImageW (big) failed")
                    return
                
                # Ищем окно по заголовку
                hwnd = ctypes.windll.user32.FindWindowW(None, "Ekranchik Dashboard")
                
                if not hwnd:
                    # Пробуем найти по частичному совпадению
                    logger.info("FindWindowW failed, trying EnumWindows...")
                    
                    EnumWindowsProc = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)
                    found_hwnd = [None]
                    
                    def enum_callback(hwnd_enum, lparam):
                        length = ctypes.windll.user32.GetWindowTextLengthW(hwnd_enum)
                        if length > 0:
                            buff = ctypes.create_unicode_buffer(length + 1)
                            ctypes.windll.user32.GetWindowTextW(hwnd_enum, buff, length + 1)
                            if "Ekranchik" in buff.value or "pywebview" in buff.value.lower():
                                found_hwnd[0] = hwnd_enum
                                logger.info(f"Found window: '{buff.value}' hwnd={hwnd_enum}")
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
                        logger.warning(f"SetClassLongPtrW failed: {e}")
                    
                    logger.info(f"Window icon set successfully (hwnd={hwnd})")
                else:
                    logger.warning("Could not find window handle")
                    
            except Exception as e:
                logger.error(f"Failed to set window icon: {e}")
        
        # Запускаем в отдельном потоке с задержкой
        threading.Thread(target=lambda: (time.sleep(0.5), do_set_icon()), daemon=True).start()
    
    def create_window(self):
        """Создание окна (изначально на выбранном мониторе)."""
        monitors = get_monitors()
        
        # Если передана жесткая геометрия (аргументы командной строки)
        if self.geometry:
            x, y = self.geometry['x'], self.geometry['y']
            width, height = self.geometry['width'], self.geometry['height']
            logger.info(f"Opening with manual geometry: {width}x{height} at ({x},{y})")
        else:
            target_monitor = None
            # Если запрошенный монитор не существует или индекс некорректен, берем основной
            if self.current_monitor_index >= len(monitors) or self.current_monitor_index < 0:
                logger.warning(f"Monitor index {self.current_monitor_index} is out of bounds. Falling back to primary.")
                target_monitor = next((m for m in monitors if m['is_primary']), monitors[0])
                # Обновляем индекс на фактический
                self.current_monitor_index = monitors.index(target_monitor)
            else:
                target_monitor = monitors[self.current_monitor_index]
            
            x, y = target_monitor['left'], target_monitor['top']
            width, height = target_monitor['width'], target_monitor['height']
            logger.info(f"Opening on: '{target_monitor['name']}' Monitor #{self.current_monitor_index} at ({x}, {y})")

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
            logger.info("Only 1 monitor detected, cannot switch.")
            return

        # 1. Вычисляем следующий индекс
        next_index = (self.current_monitor_index + 1) % len(monitors)
        target = monitors[next_index]
        
        logger.info(f"Switching from Monitor {self.current_monitor_index} to {next_index}")

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
    
    def quit_app(self):
        logger.info("Exiting app...")
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
            logger.info("Kiosk icon loaded successfully")
            
        except Exception as e:
            logger.error(f"Failed to load kiosk icon: {e}")
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

def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--monitor', type=int, default=1, help='Monitor index (0=leftmost, 1=next, etc.)')
    parser.add_argument('--geometry', type=str, default=None, help='Window geometry "x,y,width,height"')
    args = parser.parse_args()
    
    url = "http://localhost:5173"
    
    # Используем monitor из аргументов как стартовый
    # Если в системе мониторов 2, то индексы: 0 (левый), 1 (правый)
    # По умолчанию --monitor 1, чтобы открываться на втором экране.
    
    geometry = None
    if args.geometry:
        try:
            parts = list(map(int, args.geometry.split(',')))
            if len(parts) == 4:
                geometry = {'x': parts[0], 'y': parts[1], 'width': parts[2], 'height': parts[3]}
                logger.info(f"Received geometry argument: {geometry}")
        except ValueError:
            logger.error(f"Could not parse geometry: {args.geometry}")

    if not check_server_running(url, timeout=3):
        logger.error(f"Server at {url} is not running! Exiting.")
        sys.exit(1)
    
    app = KioskDashboard(url=url, monitor_index=args.monitor, geometry=geometry)
    app.run()

if __name__ == "__main__":
    main()
