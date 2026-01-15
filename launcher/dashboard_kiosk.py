"""
Kiosk Mode Dashboard Application with Tray
Полноэкранный режим с управлением через трей.
Автоматически открывается на втором мониторе если он есть.
"""
import webview
import sys
import time
import threading
import logging
from pathlib import Path

# Настройка логирования в файл
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

try:
    import pystray
    from PIL import Image, ImageDraw
    HAS_TRAY = True
    logger.info("pystray imported successfully")
except ImportError as e:
    HAS_TRAY = False
    logger.error(f"pystray import failed: {e}")
    print("Error: pystray required for kiosk mode")
    sys.exit(1)

# Для определения мониторов на Windows
if sys.platform == 'win32':
    try:
        import win32api
        import win32con
        HAS_WIN32 = True
        logger.info("win32api imported successfully")
    except ImportError as e:
        HAS_WIN32 = False
        logger.warning(f"win32api not available: {e}")
        print("Warning: pywin32 not available, multi-monitor support disabled")
else:
    HAS_WIN32 = False
    logger.info("Not Windows platform")


def get_monitors():
    """Получить список мониторов (Windows)."""
    monitors = []
    
    if not HAS_WIN32:
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
            logger.info(f"win32api detected {len(monitors)} monitor(s)")
            return monitors
    except Exception as e:
        logger.error(f"win32api detection failed: {e}")
    
    # Попытка 2: tkinter (если win32api не сработал)
    logger.info("Trying to detect monitors using tkinter as a fallback...")
    try:
        import tkinter as tk
        root = tk.Tk()
        root.withdraw()
        
        screen_width = root.winfo_screenwidth()
        screen_height = root.winfo_screenheight()
        
        logger.info(f"tkinter screen size: {screen_width}x{screen_height}")
        
        if screen_width > 2000:
            monitors.append({
                'left': 0, 'top': 0, 'right': 1920, 'bottom': 1080,
                'width': 1920, 'height': 1080
            })
            monitors.append({
                'left': 1920, 'top': 0, 'right': 3840, 'bottom': 1080,
                'width': 1920, 'height': 1080
            })
            logger.info("Detected 2 monitors (estimated from screen width)")
        else:
            monitors.append({
                'left': 0, 'top': 0, 'right': screen_width, 'bottom': screen_height,
                'width': screen_width, 'height': screen_height
            })
            logger.info("Detected 1 monitor")
        
        root.destroy()
    except Exception as e:
        logger.error(f"tkinter detection failed: {e}")
    
    return monitors


class KioskDashboard:
    def __init__(self, url: str = "http://localhost", monitor_index: int = 1, geometry: dict = None):
        self.url = url
        self.window = None
        self.tray_icon = None
        self.is_fullscreen = True
        self.monitor_index = monitor_index
        self.geometry = geometry  # {'x':, 'y':, 'width':, 'height':}
        self._use_move_hack = not bool(geometry) # Не использовать перемещение, если геометрия задана
        
    def on_loaded(self):
        """Callback when page is loaded."""
        logger.info(f"Dashboard loaded at {self.url}")
        
        # Перемещаем на нужный монитор после загрузки, если нужно
        if HAS_WIN32 and self._use_move_hack:
            self._move_to_monitor()
        
    def on_closing(self):
        """Prevent closing in kiosk mode - only via tray."""
        logger.info("Close blocked - use tray menu to exit")
        return False
    
    def _move_to_monitor(self):
        """Переместить окно на указанный монитор (Fallback)."""
        monitors = get_monitors()
        
        if not monitors:
            logger.warning("Could not detect monitors in _move_to_monitor")
            return
        
        logger.info(f"Fallback: Detected {len(monitors)} monitor(s) in _move_to_monitor")
        
        target_index = min(self.monitor_index, len(monitors) - 1)
        monitor = monitors[target_index]
        
        logger.info(f"Fallback: Moving to monitor {target_index + 1}: {monitor['width']}x{monitor['height']} at ({monitor['left']}, {monitor['top']})")
        
        try:
            self.window.move(monitor['left'], monitor['top'])
            self.window.resize(monitor['width'], monitor['height'])
            logger.info("Fallback: Window moved and resized successfully")
        except Exception as e:
            logger.error(f"Fallback: Error moving window: {e}")
    
    def create_window(self):
        """Create fullscreen kiosk window."""
        x, y, width, height = 0, 0, 1920, 1080
        
        # Приоритет - прямая геометрия
        if self.geometry:
            x, y = self.geometry['x'], self.geometry['y']
            width, height = self.geometry['width'], self.geometry['height']
            logger.info(f"Using provided geometry: {width}x{height} at ({x}, {y})")
        
        # Fallback - определение по индексу
        elif HAS_WIN32:
            monitors = get_monitors()
            if monitors:
                target_index = min(self.monitor_index, len(monitors) - 1)
                monitor = monitors[target_index]
                x, y = monitor['left'], monitor['top']
                width, height = monitor['width'], monitor['height']
                logger.info(f"Using monitor index {target_index + 1}: {width}x{height} at ({x}, {y})")
        
        self.window = webview.create_window(
            title='Ekranchik Dashboard - Kiosk',
            url=self.url,
            x=x,
            y=y,
            width=width,
            height=height,
            fullscreen=True,
            frameless=True,
            resizable=False,
            on_top=True,
            background_color='#1e293b',
            text_select=False,
        )
        
        self.window.events.loaded += self.on_loaded
        self.window.events.closing += self.on_closing
    
    def toggle_fullscreen(self):
        """Toggle fullscreen mode."""
        if self.window:
            self.window.toggle_fullscreen()
            self.is_fullscreen = not self.is_fullscreen
    
    def reload_page(self):
        """Reload dashboard."""
        if self.window:
            self.window.evaluate_js("location.reload()")
    
    def quit_app(self):
        """Quit application."""
        print("[Kiosk] Exiting...")
        if self.tray_icon:
            self.tray_icon.stop()
        if self.window:
            # Force close
            self.window.events.closing -= self.on_closing
            self.window.destroy()
    
    def create_tray_icon(self):
        """Create system tray icon for kiosk control."""
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
            # Fallback - создаём простую красную иконку
            width = 64
            height = 64
            image = Image.new('RGB', (width, height), color='#ef5350')
            dc = ImageDraw.Draw(image)
            
            # Draw "K" for Kiosk
            dc.rectangle([10, 10, 54, 54], fill='white')
            dc.rectangle([15, 15, 49, 49], fill='#ef5350')
            dc.text((18, 18), "K", fill='white')
        
        # Create menu
        menu = pystray.Menu(
            pystray.MenuItem("Обновить страницу", lambda: self.reload_page()),
            pystray.MenuItem("Переключить полный экран", lambda: self.toggle_fullscreen()),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Выход из киоска", lambda: self.quit_app())
        )
        
        self.tray_icon = pystray.Icon(
            "ekranchik_kiosk",
            image,
            "Ekranchik Kiosk",
            menu
        )
    
    def run_tray(self):
        """Run tray icon."""
        if self.tray_icon:
            self.tray_icon.run()
    
    def run(self):
        """Start kiosk mode."""
        self.create_window()
        
        # Setup tray
        self.create_tray_icon()
        tray_thread = threading.Thread(target=self.run_tray, daemon=True)
        tray_thread.start()
        
        # Start webview
        webview.start(debug=False)
        
        # Cleanup
        if self.tray_icon:
            self.tray_icon.stop()


def check_server_running(url: str, timeout: int = 30) -> bool:
    """Check if server is running."""
    import urllib.request
    import urllib.error
    
    start = time.time()
    while time.time() - start < timeout:
        try:
            urllib.request.urlopen(url, timeout=2)
            return True
        except (urllib.error.URLError, ConnectionRefusedError):
            time.sleep(0.5)
    return False


def main():
    import argparse
    
    parser = argparse.ArgumentParser(description='Kiosk Mode Dashboard')
    parser.add_argument('--monitor', type=int, default=1, help='Monitor index (0=first, 1=second)')
    parser.add_argument('--geometry', type=str, default=None, help='Window geometry "x,y,width,height"')
    args = parser.parse_args()
    
    dashboard_url = "http://localhost"  # Порт 80
    
    logger.info("Starting kiosk mode...")
    logger.info(f"URL: {dashboard_url}")
    
    # Обрабатываем аргументы
    monitor_index = args.monitor
    geometry = None
    
    if args.geometry:
        try:
            parts = list(map(int, args.geometry.split(',')))
            if len(parts) == 4:
                geometry = {'x': parts[0], 'y': parts[1], 'width': parts[2], 'height': parts[3]}
                logger.info(f"Received geometry argument: {geometry}")
            else:
                logger.error(f"Invalid geometry format: {args.geometry}")
        except ValueError:
            logger.error(f"Could not parse geometry: {args.geometry}")
    
    if not geometry:
        logger.info(f"Using monitor index: {monitor_index + 1}")

    # Проверяем сервер
    logger.info("Checking server...")
    if not check_server_running(dashboard_url, timeout=5):
        logger.error("Server not running!")
        
        try:
            import tkinter as tk
            from tkinter import messagebox
            root = tk.Tk()
            root.withdraw()
            root.attributes('-topmost', True)
            messagebox.showerror(
                "Ошибка запуска киоска",
                "Сервер не запущен!\n\nЗапустите Backend и Frontend через лаунчер."
            )
            root.destroy()
        except Exception as e:
            logger.error(f"Error showing dialog: {e}")
        
        sys.exit(1)
    
    logger.info("Server is running")
    
    # Запускаем приложение
    logger.info("Starting webview...")
    app = KioskDashboard(url=dashboard_url, monitor_index=monitor_index, geometry=geometry)
    app.run()


if __name__ == "__main__":
    main()
