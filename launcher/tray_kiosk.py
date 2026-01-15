import sys
import os
import subprocess
import time
import threading
import win32gui
import win32con
import win32process
import win32api

# Попытка импорта библиотек для трея
try:
    import pystray
    from PIL import Image, ImageDraw
except ImportError:
    print("ОШИБКА: Нужны библиотеки для трея!")
    print("Выполните в консоли: pip install pystray pillow")
    sys.exit(1)

# --- НАСТРОЙКИ ---
CHROME_PATH = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
URL = "https://google.com"
PROFILE_DIR = os.path.join(os.environ["TEMP"], "TrayProfile")

class TrayBrowser:
    def __init__(self):
        self.chrome_process = None
        self.chrome_hwnd = None
        self.is_visible = True

    def create_icon(self):
        # Рисуем простую иконку (синий квадрат с буквой C), чтобы не искать файл .ico
        width = 64
        height = 64
        image = Image.new('RGB', (width, height), color=(255, 255, 255))
        dc = ImageDraw.Draw(image)
        dc.rectangle((0, 0, width, height), fill='#2196F3') # Синий фон
        dc.ellipse((16, 16, 48, 48), fill='white') # Белый круг
        
        return image

    def find_chrome_window(self):
        """Ищет окно Chrome, запущенного нами"""
        if not self.chrome_process: return None
        
        target_pid = self.chrome_process.pid
        hwnds = []
        
        def callback(hwnd, _):
            if win32gui.IsWindowVisible(hwnd):
                _, found_pid = win32process.GetWindowThreadProcessId(hwnd)
                # Chrome создает много процессов, ищем любой, принадлежащий дереву процессов, 
                # но проще искать по имени файла, так как PID может смениться у окна
                try:
                    handle = win32api.OpenProcess(win32con.PROCESS_QUERY_INFORMATION | win32con.PROCESS_VM_READ, False, found_pid)
                    proc_path = win32process.GetModuleFileNameEx(handle, 0)
                    win32api.CloseHandle(handle)
                    
                    if "chrome.exe" in proc_path.lower():
                        # Проверяем заголовок, чтобы не поймать скрытое служебное окно
                        if win32gui.GetWindowText(hwnd):
                            hwnds.append(hwnd)
                except:
                    pass
        
        win32gui.EnumWindows(callback, None)
        return hwnds[0] if hwnds else None

    def remove_taskbar_icon(self):
        """Убирает кнопку из панели задач, превращая окно в 'Инструмент'"""
        if not self.chrome_hwnd: return

        try:
            style = win32gui.GetWindowLong(self.chrome_hwnd, win32con.GWL_EXSTYLE)
            
            # Добавляем TOOLWINDOW (нет в панели задач) и убираем APPWINDOW
            if not (style & win32con.WS_EX_TOOLWINDOW):
                new_style = (style | win32con.WS_EX_TOOLWINDOW) & ~win32con.WS_EX_APPWINDOW
                win32gui.SetWindowLong(self.chrome_hwnd, win32con.GWL_EXSTYLE, new_style)
                
                # Обновляем кэш стиля
                win32gui.SetWindowPos(
                    self.chrome_hwnd, 0, 0, 0, 0, 0,
                    win32con.SWP_NOMOVE | win32con.SWP_NOSIZE | 
                    win32con.SWP_NOZORDER | win32con.SWP_FRAMECHANGED
                )
                print("Иконка убрана из панели задач.")
        except Exception as e:
            print(f"Ошибка скрытия иконки: {e}")

    def on_tray_click(self, icon, item):
        """Обработка нажатия на иконку трея"""
        if not self.chrome_hwnd:
            self.chrome_hwnd = self.find_chrome_window()
        
        if not self.chrome_hwnd: return

        if self.is_visible:
            # Скрываем окно полностью
            win32gui.ShowWindow(self.chrome_hwnd, win32con.SW_HIDE)
            self.is_visible = False
        else:
            # Показываем окно
            win32gui.ShowWindow(self.chrome_hwnd, win32con.SW_SHOW)
            win32gui.SetForegroundWindow(self.chrome_hwnd)
            self.is_visible = True

    def exit_app(self, icon, item):
        icon.stop()
        if self.chrome_process:
            self.chrome_process.terminate()
        sys.exit()

    def run(self):
        # 1. Запуск Chrome
        if not os.path.exists(PROFILE_DIR): os.makedirs(PROFILE_DIR)
        
        args = [
            CHROME_PATH,
            f'--app={URL}',
            '--window-size=1000,700',
            f'--user-data-dir={PROFILE_DIR}',
            '--no-first-run'
        ]
        
        print("Запускаем Chrome...")
        self.chrome_process = subprocess.Popen(args)
        
        # 2. Ждем и убираем иконку из панели задач
        threading.Thread(target=self._startup_logic, daemon=True).start()

        # 3. Запуск иконки в трее
        menu = pystray.Menu(
            pystray.MenuItem("Показать/Скрыть", self.on_tray_click, default=True),
            pystray.MenuItem("Закрыть", self.exit_app)
        )

        self.icon = pystray.Icon("name", self.create_icon(), "Мой Браузер", menu)
        print("Иконка в трее создана. Нажмите на неё, чтобы показать/скрыть браузер.")
        self.icon.run()

    def _startup_logic(self):
        """Ждет появления окна и сразу убирает его из панели задач"""
        time.sleep(2) # Даем время на старт
        
        # Пытаемся найти окно 10 раз
        for i in range(10):
            hwnd = self.find_chrome_window()
            if hwnd:
                self.chrome_hwnd = hwnd
                print(f"Окно найдено (HWND: {hwnd})")
                self.remove_taskbar_icon()
                break
            time.sleep(1)

if __name__ == "__main__":
    app = TrayBrowser()
    app.run()