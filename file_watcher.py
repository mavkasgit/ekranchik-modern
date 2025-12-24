"""
Скрипт для мониторинга файла с событиями разгрузки по FTP.
Читает файл с FTP сервера и показывает последние N событий.
Использует настройки из backend/.env
"""
import re
import time
import sys
import os
import io
from datetime import datetime
from pathlib import Path
from ftplib import FTP, error_temp, error_perm
from typing import List, NamedTuple, Optional, Tuple
from enum import Enum


def load_env_file():
    """Загружает переменные из .env файла (backend/.env)."""
    env_paths = [
        Path("backend/.env"),
        Path(".env"),
        Path(__file__).parent / "backend" / ".env",
    ]
    
    for env_path in env_paths:
        if env_path.exists():
            try:
                with open(env_path, 'r', encoding='utf-8') as f:
                    for line in f:
                        line = line.strip()
                        if line and not line.startswith('#') and '=' in line:
                            key, _, value = line.partition('=')
                            key = key.strip()
                            value = value.strip().strip('"').strip("'")
                            if key not in os.environ:
                                os.environ[key] = value
                return True
            except Exception:
                pass
    return False


load_env_file()


class FileStatus(Enum):
    OK = "ok"
    NOT_FOUND = "not_found"
    PERMISSION_DENIED = "permission_denied"
    FILE_BUSY = "file_busy"
    FILE_LOCKED = "file_locked"
    NETWORK_ERROR = "network_error"
    CONNECTION_REFUSED = "connection_refused"
    TIMEOUT = "timeout"
    FTP_ERROR = "ftp_error"
    UNKNOWN_ERROR = "unknown_error"


ERROR_MESSAGES = {
    FileStatus.OK: "✓ Подключено",
    FileStatus.NOT_FOUND: "✗ Файл не найден на FTP",
    FileStatus.PERMISSION_DENIED: "✗ Нет доступа (Permission Denied)",
    FileStatus.FILE_BUSY: "⏳ Сервер занят (Busy)",
    FileStatus.FILE_LOCKED: "🔒 Файл заблокирован",
    FileStatus.NETWORK_ERROR: "🌐 Сетевая ошибка",
    FileStatus.CONNECTION_REFUSED: "🚫 Соединение отклонено",
    FileStatus.TIMEOUT: "⏱ Таймаут соединения",
    FileStatus.FTP_ERROR: "📡 Ошибка FTP",
    FileStatus.UNKNOWN_ERROR: "❓ Неизвестная ошибка",
}


class UnloadEvent(NamedTuple):
    time: str
    hanger: int
    raw_line: str


class FTPConfig:
    """Конфигурация FTP из переменных окружения."""
    def __init__(self):
        self.host = os.environ.get("FTP_HOST", "127.0.0.1")
        self.port = int(os.environ.get("FTP_PORT", "21"))
        self.user = os.environ.get("FTP_USER", "anonymous")
        self.password = os.environ.get("FTP_PASSWORD", "")
        self.base_path = os.environ.get("FTP_BASE_PATH", "/")
        self.poll_interval = float(os.environ.get("FTP_POLL_INTERVAL", "5"))
    
    def __str__(self):
        return f"ftp://{self.user}@{self.host}:{self.port}{self.base_path}"


def classify_ftp_error(e: Exception) -> FileStatus:
    """Классифицирует FTP ошибку."""
    error_str = str(e).lower()
    
    if isinstance(e, (error_temp, error_perm)):
        code = str(e)[:3] if len(str(e)) >= 3 else ""
        if code == "550":
            if "busy" in error_str:
                return FileStatus.FILE_BUSY
            return FileStatus.NOT_FOUND
        if code == "530":
            return FileStatus.PERMISSION_DENIED
        if code == "421":
            return FileStatus.FILE_BUSY
        return FileStatus.FTP_ERROR
    
    if "timeout" in error_str or "timed out" in error_str:
        return FileStatus.TIMEOUT
    if "refused" in error_str:
        return FileStatus.CONNECTION_REFUSED
    if "network" in error_str or "unreachable" in error_str:
        return FileStatus.NETWORK_ERROR
    if "permission" in error_str or "denied" in error_str:
        return FileStatus.PERMISSION_DENIED
    
    return FileStatus.UNKNOWN_ERROR


def ftp_list_files(config: FTPConfig) -> Tuple[List[str], FileStatus, Optional[str]]:
    """Получает список .txt файлов с FTP."""
    try:
        ftp = FTP()
        ftp.connect(config.host, config.port, timeout=10)
        ftp.login(config.user, config.password)
        ftp.set_pasv(True)
        
        if config.base_path and config.base_path != "/":
            ftp.cwd(config.base_path)
        
        files = []
        ftp.retrlines('NLST', files.append)
        ftp.quit()
        
        # Фильтруем только .txt файлы
        txt_files = [f for f in files if f.endswith('.txt')]
        # Сортируем от новых к старым
        txt_files.sort(reverse=True)
        
        return txt_files, FileStatus.OK, None
        
    except Exception as e:
        status = classify_ftp_error(e)
        return [], status, f"{type(e).__name__}: {e}"


def ftp_read_file(config: FTPConfig, filename: str) -> Tuple[Optional[str], FileStatus, Optional[str]]:
    """Читает файл с FTP сервера."""
    try:
        ftp = FTP()
        ftp.connect(config.host, config.port, timeout=10)
        ftp.login(config.user, config.password)
        ftp.set_pasv(True)
        
        if config.base_path and config.base_path != "/":
            ftp.cwd(config.base_path)
        
        buffer = io.BytesIO()
        ftp.retrbinary(f'RETR {filename}', buffer.write)
        ftp.quit()
        
        # Пробуем разные кодировки
        data = buffer.getvalue()
        for encoding in ['utf-8', 'cp1251', 'cp866', 'latin-1']:
            try:
                return data.decode(encoding), FileStatus.OK, None
            except UnicodeDecodeError:
                continue
        
        return data.decode('utf-8', errors='ignore'), FileStatus.OK, None
        
    except Exception as e:
        status = classify_ftp_error(e)
        return None, status, f"{type(e).__name__}: {e}"


def parse_events(content: str) -> List[UnloadEvent]:
    """Парсит события разгрузки из содержимого файла."""
    events = []
    pattern = r'(\d{2}:\d{2}:\d{2})\.\d+\s+L#\s+Команда\s+от\s+CJ2M:\s+Разгрузка\s+подвеса\s+-\s+(\d+)\s+в\s+поз\.\s*34\.?'
    
    for line in content.split('\n'):
        line = line.strip()
        if not line:
            continue
        
        match = re.search(pattern, line)
        if match:
            time_str = match.group(1)
            hanger_num = int(match.group(2))
            events.append(UnloadEvent(time=time_str, hanger=hanger_num, raw_line=line))
    
    return events


def clear_screen():
    os.system('cls' if os.name == 'nt' else 'clear')


def select_file_menu_ftp(config: FTPConfig) -> Optional[str]:
    """Показывает меню выбора файла с FTP."""
    clear_screen()
    
    print("=" * 60)
    print("  ВЫБОР ФАЙЛА ДЛЯ МОНИТОРИНГА (FTP)")
    print(f"  Сервер: {config}")
    print("=" * 60)
    print()
    print("  Загрузка списка файлов...")
    
    files, status, error = ftp_list_files(config)
    
    clear_screen()
    print("=" * 60)
    print("  ВЫБОР ФАЙЛА ДЛЯ МОНИТОРИНГА (FTP)")
    print(f"  Сервер: {config}")
    print(f"  Статус: {ERROR_MESSAGES.get(status, 'Неизвестно')}")
    print("=" * 60)
    print()
    
    if status != FileStatus.OK:
        print(f"  {ERROR_MESSAGES.get(status, 'Ошибка')}")
        if error:
            print(f"  {error}")
        print()
        input("  Нажмите Enter для выхода...")
        return None
    
    if not files:
        print("  Файлы не найдены!")
        print()
        input("  Нажмите Enter для выхода...")
        return None
    
    print(f"  Найдено файлов: {len(files)}")
    print("-" * 40)
    print(f"  {'№':<4} {'Файл':<30}")
    print("-" * 40)
    
    for i, f in enumerate(files, 1):
        print(f"  {i:<4} {f:<30}")
    
    print("-" * 40)
    print()
    print("  0 - Выход")
    print("  r - Обновить список")
    print()
    
    while True:
        try:
            choice = input("  Выберите номер файла: ").strip().lower()
            
            if choice == '0' or choice == 'q':
                return None
            
            if choice == 'r':
                return select_file_menu_ftp(config)
            
            num = int(choice)
            if 1 <= num <= len(files):
                return files[num - 1]
            else:
                print(f"  Введите число от 1 до {len(files)}")
        except ValueError:
            print("  Введите корректный номер")
        except KeyboardInterrupt:
            return None



def display_events(events: List[UnloadEvent], count: int, file_path: str, 
                   status: FileStatus, error_details: str = None, config: FTPConfig = None):
    """Отображает последние N событий."""
    clear_screen()
    
    print("=" * 60)
    print("  МОНИТОР РАЗГРУЗКИ ПОДВЕСОВ (FTP)")
    if config:
        print(f"  Сервер: {config.host}:{config.port}")
    print(f"  Файл: {file_path}")
    print(f"  Обновлено: {datetime.now().strftime('%H:%M:%S')}")
    print(f"  Статус: {ERROR_MESSAGES.get(status, 'Неизвестно')}")
    if error_details:
        print(f"  Детали: {error_details}")
    print(f"  Всего событий: {len(events)}")
    print("=" * 60)
    print()
    
    if status != FileStatus.OK:
        print(f"  {ERROR_MESSAGES.get(status, 'Ошибка')}")
        if error_details:
            print(f"  {error_details}")
        print()
        print("  Повторная попытка через несколько секунд...")
        print()
        print("  Нажмите Ctrl+C для выхода")
        return
    
    if not events:
        print("  Событий не найдено")
        print()
        print("  Нажмите Ctrl+C для выхода")
        return
    
    last_events = events[-count:]
    
    print(f"  Последние {len(last_events)} событий:")
    print("-" * 40)
    print(f"  {'№':<4} {'Время':<12} {'Подвес':<10}")
    print("-" * 40)
    
    for i, event in enumerate(last_events, 1):
        print(f"  {i:<4} {event.time:<12} {event.hanger:<10}")
    
    print("-" * 40)
    print()
    print("  Нажмите Ctrl+C для выхода")


def countdown_sleep(seconds: float):
    """Ожидание с обратным отсчётом."""
    start = time.time()
    end = start + seconds
    
    while True:
        remaining = end - time.time()
        if remaining <= 0:
            break
        
        bar_width = 20
        progress = 1 - (remaining / seconds)
        filled = int(bar_width * progress)
        bar = "█" * filled + "░" * (bar_width - filled)
        
        print(f"\r  Обновление через: {remaining:.1f} сек [{bar}]  ", end="", flush=True)
        time.sleep(0.1)
    
    print("\r" + " " * 60 + "\r", end="", flush=True)


def watch_file_ftp(config: FTPConfig, filename: str, count: int = 10):
    """Основной цикл мониторинга файла по FTP."""
    print(f"Запуск мониторинга: {filename}")
    print(f"Сервер: {config}")
    print(f"Интервал: {config.poll_interval} сек")
    print()
    
    try:
        while True:
            content, status, error_details = ftp_read_file(config, filename)
            
            events = []
            if content:
                events = parse_events(content)
            
            display_events(events, count, filename, status, error_details, config)
            countdown_sleep(config.poll_interval)
            
    except KeyboardInterrupt:
        print("\n\nМониторинг остановлен.")


def main():
    config = FTPConfig()
    count = 10
    filename = None
    
    args = sys.argv[1:]
    
    if '--help' in args or '-h' in args:
        print(f"""
Использование: python file_watcher.py [файл] [опции]

Опции:
  -n, --count N      Количество последних событий (по умолчанию: 10)
  -h, --help         Показать эту справку

Настройки FTP из backend/.env:
  FTP_HOST           {config.host}
  FTP_PORT           {config.port}
  FTP_USER           {config.user}
  FTP_BASE_PATH      {config.base_path}
  FTP_POLL_INTERVAL  {config.poll_interval} сек

Примеры:
  python file_watcher.py                    # Меню выбора файла
  python file_watcher.py 2025-12-24.txt     # Конкретный файл
  python file_watcher.py -n 5               # Показать 5 событий
""")
        sys.exit(0)
    
    i = 0
    while i < len(args):
        arg = args[i]
        
        if arg in ('-n', '--count') and i + 1 < len(args):
            count = int(args[i + 1])
            i += 2
        elif not arg.startswith('-'):
            filename = arg
            i += 1
        else:
            i += 1
    
    if not filename:
        filename = select_file_menu_ftp(config)
        if not filename:
            print("Файл не выбран. Выход.")
            sys.exit(0)
    
    watch_file_ftp(config, filename, count)


if __name__ == "__main__":
    main()
