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
    
    # Попытка 1: win32api
    if HAS_WIN32:
        logger.info("Trying to detect monitors using win32api...")
        
        try:
            import win32api
            
            def callback(hMonitor, hdcMonitor, lprcMonitor, dwData):
                monitors.append({
                    'left': lprcMonitor[0],
                    'top': lprcMonitor[1],
                    'right': lprcMonitor[2],
                    'bottom': lprcMonitor[3],
                    'width': lprcMonitor[2] - lprcMonitor[0],
                    'height': lprcMonitor[3] - lprcMonitor[1]
                })
                return True
            
            # Вызываем EnumDisplayMonitors с callback
            win32api.EnumDisplayMonitors(None, None, callback)
            
            # Альтернативный способ через ctypes
            if not monitors:
                import ctypes
                user32 = ctypes.windll.user32
                
                # Получаем количество мониторов
                monitor_count = user32.GetSystemMetrics(80)  # SM_CMONITORS
                logger.info(f"GetSystemMetrics reports {monitor_count} monitor(s)")
                
                if monitor_count > 0:
                    # Получаем размер виртуального экрана
                    virtual_width = user32.GetSystemMetrics(78)  # SM_CXVIRTUALSCREEN
                    virtual_height = user32.GetSystemMetrics(79)  # SM_CYVIRTUALSCREEN
                    
                    logger.info(f"Virtual screen: {virtual_width}x{virtual_height}")
                    
                    # Если больше одного монитора
                    if monitor_count > 1:
                        # Предполагаем стандартные мониторы 1920x1080
                        for i in range(monitor_count):
                            monitors.append({
                                'left': i * 1920,
                                'top': 0,
                                'right': (i + 1) * 1920,
                                'bottom': 1080,
                                'width': 1920,
                                'height': 1080
                            })
                        logger.info(f"Created {monitor_count} monitor entries (estimated)")
            
            logger.info(f"win32api detected {len(monitors)} monitor(s)")
        except Exception as e:
            logger.error(f"win32api detection failed: {e}")
    
    # Попытка 2: tkinter (если win32api не сработал)
    if not monitors:
        logger.info("Trying to detect monitors using tkinter...")
        try:
            import tkinter as tk
            root = tk.Tk()
            root.withdraw()
            
            # Получаем размер экрана
            screen_width = root.winfo_screenwidth()
            screen_height = root.winfo_screenheight()
            
            logger.info(f"tkinter screen size: {screen_width}x{screen_height}")
            
            # Если ширина больше 2000, вероятно 2 монитора
            if screen_width > 2000:
                # Предполагаем 2 монитора по 1920
                monitors.append({
                    'left': 0,
                    'top': 0,
                    'right': 1920,
                    'bottom': 1080,
                    'width': 1920,
                    'height': 1080
                })
                monitors.append({
                    'left': 1920,
                    'top': 0,
                    'right': 3840,
                    'bottom': 1080,
                    'width': 1920,
                    'height': 1080
                })
                logger.info("Detected 2 monitors (estimated from screen width)")
            else:
                # Один монитор
                monitors.append({
                    'left': 0,
                    'top': 0,
                    'right': screen_width,
                    'bottom': screen_height,
                    'width': screen_width,
                    'height': screen_height
                })
                logger.info("Detected 1 monitor")
            
            root.destroy()
        except Exception as e:
            logger.error(f"tkinter detection failed: {e}")
    
    return monitors


class KioskDashboard:
    def __init__(self, url: str = "http://localhost", monitor_index: int = 1):
        self.url = url
        self.window = None
        self.tray_icon = None
        self.is_fullscreen = True
        self.monitor_index = monitor_index  # 0 = первый, 1 = второй
        
    def on_loaded(self):
        """Callback when page is loaded."""
        print(f"[Kiosk] Dashboard loaded")
        
        # Перемещаем на нужный монитор после загрузки
        if HAS_WIN32:
            self._move_to_monitor()
        
    def on_closing(self):
        """Prevent closing in kiosk mode - only via tray."""
        print("[Kiosk] Close blocked - use tray menu to exit")
        return False
    
    def _move_to_monitor(self):
        """Переместить окно на указанный монитор."""
        monitors = get_monitors()
        
        if not monitors:
            logger.warning("Could not detect monitors in _move_to_monitor")
            return
        
        logger.info(f"Detected {len(monitors)} monitor(s) in _move_to_monitor")
        
        # Если запрошен второй монитор, но его нет - используем первый
        target_index = min(self.monitor_index, len(monitors) - 1)
        monitor = monitors[target_index]
        
        logger.info(f"Moving to monitor {target_index + 1}: {monitor['width']}x{monitor['height']} at ({monitor['left']}, {monitor['top']})")
        
        # Перемещаем окно
        try:
            self.window.move(monitor['left'], monitor['top'])
            # Устанавливаем размер монитора
            self.window.resize(monitor['width'], monitor['height'])
            logger.info("Window moved and resized successfully")
        except Exception as e:
            logger.error(f"Error moving window: {e}")
    
    def create_window(self):
        """Create fullscreen kiosk window."""
        # Определяем начальную позицию и размер
        x, y, width, height = 0, 0, 1920, 1080
        
        if HAS_WIN32:
            monitors = get_monitors()
            if monitors and self.monitor_index < len(monitors):
                monitor = monitors[self.monitor_index]
                x = monitor['left']
                y = monitor['top']
                width = monitor['width']
                height = monitor['height']
                print(f"[Kiosk] Target monitor: {width}x{height} at ({x}, {y})")
        
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
    args = parser.parse_args()
    
    dashboard_url = "http://localhost"  # Порт 80
    
    print(f"[Kiosk] Starting kiosk mode...")
    print(f"[Kiosk] URL: {dashboard_url}")
    print(f"[Kiosk] Target monitor: {args.monitor + 1}")
    
    # Проверяем сервер
    print("[Kiosk] Checking server...")
    if not check_server_running(dashboard_url, timeout=5):
        print("[Kiosk] ERROR: Server not running!")
        
        # Показываем диалог с ошибкой
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
            print(f"[Kiosk] Error showing dialog: {e}")
        
        sys.exit(1)
    
    print("[Kiosk] Server is running")
    
    # Определяем мониторы
    monitors = get_monitors() if HAS_WIN32 else []
    
    print(f"[Kiosk] Detected {len(monitors)} monitor(s)")
    
    if monitors:
        for i, mon in enumerate(monitors):
            print(f"  Monitor {i + 1}: {mon['width']}x{mon['height']} at ({mon['left']}, {mon['top']})")
    
    # Используем монитор из аргументов
    monitor_index = args.monitor
    
    # Проверяем что монитор существует
    if monitors and monitor_index >= len(monitors):
        print(f"[Kiosk] Warning: Monitor {monitor_index + 1} not found, using monitor 1")
        monitor_index = 0
    
    print(f"[Kiosk] Using monitor: {monitor_index + 1}")
    print(f"[Kiosk] Starting webview...")
    
    app = KioskDashboard(url=dashboard_url, monitor_index=monitor_index)
    app.run()


if __name__ == "__main__":
    main()
