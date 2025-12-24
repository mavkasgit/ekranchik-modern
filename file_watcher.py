"""
Простой скрипт для мониторинга файла с событиями разгрузки.
Читает файл и показывает последние N событий.
"""
import re
import time
import sys
import os
import errno
from datetime import datetime
from pathlib import Path
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
                            # Не перезаписываем если уже есть в окружении
                            if key not in os.environ:
                                os.environ[key] = value
                return True
            except Exception:
                pass
    return False


# Загружаем .env при импорте
load_env_file()


class FileStatus(Enum):
    OK = "ok"
    NOT_FOUND = "not_found"
    PERMISSION_DENIED = "permission_denied"
    FILE_BUSY = "file_busy"
    FILE_LOCKED = "file_locked"
    NETWORK_ERROR = "network_error"
    DISK_ERROR = "disk_error"
    ENCODING_ERROR = "encoding_error"
    TIMEOUT = "timeout"
    UNKNOWN_ERROR = "unknown_error"


# Сообщения об ошибках
ERROR_MESSAGES = {
    FileStatus.OK: "✓ Файл доступен",
    FileStatus.NOT_FOUND: "✗ Файл не найден",
    FileStatus.PERMISSION_DENIED: "✗ Нет доступа к файлу (Permission Denied)",
    FileStatus.FILE_BUSY: "⏳ Файл занят другим процессом (Busy)",
    FileStatus.FILE_LOCKED: "🔒 Файл заблокирован (Locked)",
    FileStatus.NETWORK_ERROR: "🌐 Сетевая ошибка (Network Error)",
    FileStatus.DISK_ERROR: "💾 Ошибка диска (Disk I/O Error)",
    FileStatus.ENCODING_ERROR: "📝 Ошибка кодировки файла",
    FileStatus.TIMEOUT: "⏱ Таймаут при чтении файла",
    FileStatus.UNKNOWN_ERROR: "❓ Неизвестная ошибка",
}


class UnloadEvent(NamedTuple):
    time: str
    hanger: int
    raw_line: str


def classify_error(e: Exception) -> FileStatus:
    """Классифицирует исключение и возвращает статус."""
    error_str = str(e).lower()
    
    # OSError / IOError с errno
    if isinstance(e, OSError):
        if e.errno == errno.ENOENT:
            return FileStatus.NOT_FOUND
        elif e.errno == errno.EACCES:
            return FileStatus.PERMISSION_DENIED
        elif e.errno == errno.EBUSY:
            return FileStatus.FILE_BUSY
        elif e.errno in (errno.EAGAIN, errno.EWOULDBLOCK):
            return FileStatus.FILE_LOCKED
        elif e.errno == errno.ENETDOWN or e.errno == errno.ENETUNREACH:
            return FileStatus.NETWORK_ERROR
        elif e.errno == errno.EIO:
            return FileStatus.DISK_ERROR
        elif e.errno == errno.ETIMEDOUT:
            return FileStatus.TIMEOUT
    
    # FileNotFoundError
    if isinstance(e, FileNotFoundError):
        return FileStatus.NOT_FOUND
    
    # PermissionError
    if isinstance(e, PermissionError):
        return FileStatus.PERMISSION_DENIED
    
    # По тексту ошибки
    if 'permission' in error_str or 'access' in error_str or 'denied' in error_str:
        return FileStatus.PERMISSION_DENIED
    if 'busy' in error_str or 'in use' in error_str or 'being used' in error_str:
        return FileStatus.FILE_BUSY
    if 'locked' in error_str or 'lock' in error_str:
        return FileStatus.FILE_LOCKED
    if 'network' in error_str or 'connection' in error_str or 'unreachable' in error_str:
        return FileStatus.NETWORK_ERROR
    if 'timeout' in error_str or 'timed out' in error_str:
        return FileStatus.TIMEOUT
    if 'disk' in error_str or 'i/o' in error_str or 'io error' in error_str:
        return FileStatus.DISK_ERROR
    if 'encoding' in error_str or 'decode' in error_str or 'codec' in error_str:
        return FileStatus.ENCODING_ERROR
    if 'not found' in error_str or 'no such file' in error_str:
        return FileStatus.NOT_FOUND
    
    return FileStatus.UNKNOWN_ERROR


def read_file_safe(path: Path) -> Tuple[Optional[str], FileStatus, Optional[str]]:
    """
    Безопасное чтение файла с обработкой всех ошибок.
    Возвращает: (содержимое, статус, детали_ошибки)
    """
    if not path.exists():
        return None, FileStatus.NOT_FOUND, f"Путь: {path}"
    
    try:
        # Пробуем разные кодировки
        encodings = ['utf-8', 'cp1251', 'cp866', 'latin-1']
        content = None
        
        for encoding in encodings:
            try:
                with open(path, 'r', encoding=encoding) as f:
                    content = f.read()
                break
            except UnicodeDecodeError:
                continue
        
        if content is None:
            # Последняя попытка с игнорированием ошибок
            with open(path, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()
        
        return content, FileStatus.OK, None
        
    except Exception as e:
        status = classify_error(e)
        details = f"{type(e).__name__}: {e}"
        return None, status, details


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
    """Очистка консоли."""
    os.system('cls' if os.name == 'nt' else 'clear')


def get_log_files(directory: str) -> List[Path]:
    """
    Получает список .txt файлов из директории.
    Сортирует от новых к старым (по имени файла, т.к. формат YYYY-MM-DD).
    """
    dir_path = Path(directory)
    if not dir_path.exists():
        return []
    
    files = list(dir_path.glob("*.txt"))
    # Сортируем по имени в обратном порядке (новые первые)
    files.sort(key=lambda f: f.name, reverse=True)
    return files


def select_file_menu(directory: str = "testdata/ftp") -> Optional[Path]:
    """
    Показывает меню выбора файла.
    Возвращает выбранный файл или None.
    """
    clear_screen()
    
    print("=" * 60)
    print("  ВЫБОР ФАЙЛА ДЛЯ МОНИТОРИНГА")
    print(f"  Директория: {directory}")
    print("=" * 60)
    print()
    
    files = get_log_files(directory)
    
    if not files:
        print("  Файлы не найдены в директории!")
        print()
        input("  Нажмите Enter для выхода...")
        return None
    
    print(f"  Найдено файлов: {len(files)}")
    print("-" * 40)
    print(f"  {'№':<4} {'Файл':<25} {'Размер':<10}")
    print("-" * 40)
    
    for i, f in enumerate(files, 1):
        try:
            size = f.stat().st_size
            size_str = f"{size:,} б" if size < 1024 else f"{size/1024:.1f} КБ"
        except:
            size_str = "?"
        print(f"  {i:<4} {f.name:<25} {size_str:<10}")
    
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
                return select_file_menu(directory)  # Рекурсивно обновляем
            
            num = int(choice)
            if 1 <= num <= len(files):
                return files[num - 1]
            else:
                print(f"  Введите число от 1 до {len(files)}")
        except ValueError:
            print("  Введите корректный номер")
        except KeyboardInterrupt:
            return None


def display_events(events: List[UnloadEvent], count: int = 10, file_path: str = "", status: FileStatus = FileStatus.OK, error_details: str = None):
    """Отображает последние N событий."""
    clear_screen()
    
    print("=" * 60)
    print(f"  МОНИТОР РАЗГРУЗКИ ПОДВЕСОВ")
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
    
    # Берём последние N
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
    """
    Ожидание с обратным отсчётом в одной строке.
    Показывает оставшееся время до обновления.
    """
    start = time.time()
    end = start + seconds
    
    while True:
        remaining = end - time.time()
        if remaining <= 0:
            break
        
        # Формируем строку с таймером
        bar_width = 20
        progress = 1 - (remaining / seconds)
        filled = int(bar_width * progress)
        bar = "█" * filled + "░" * (bar_width - filled)
        
        # \r возвращает курсор в начало строки
        print(f"\r  Обновление через: {remaining:.1f} сек [{bar}]  ", end="", flush=True)
        
        time.sleep(0.1)
    
    # Очищаем строку таймера
    print("\r" + " " * 60 + "\r", end="", flush=True)


def watch_file(file_path: str, count: int = 10, interval: float = 2.0):
    """Основной цикл мониторинга файла."""
    path = Path(file_path)
    
    print(f"Запуск мониторинга: {file_path}")
    print(f"Интервал обновления: {interval} сек")
    print(f"Показывать последних: {count} событий")
    print()
    
    try:
        while True:
            content, status, error_details = read_file_safe(path)
            
            events = []
            if content:
                events = parse_events(content)
            
            display_events(events, count, str(path), status, error_details)
            
            # Обратный отсчёт вместо простого sleep
            countdown_sleep(interval)
            
    except KeyboardInterrupt:
        print("\n\nМониторинг остановлен.")


def main():
    # Загружаем дефолты из .env
    default_dir = os.environ.get("FTP_LOG_DIR", "testdata/ftp")
    count = 10
    interval = float(os.environ.get("FTP_POLL_INTERVAL", "2.0"))
    file_path = None
    
    # Простой парсинг аргументов
    args = sys.argv[1:]
    
    if '--help' in args or '-h' in args:
        print(f"""
Использование: python file_watcher.py [файл] [опции]

Опции:
  -d, --dir DIR      Директория с файлами (из .env: {default_dir})
  -n, --count N      Количество последних событий (по умолчанию: 10)
  -i, --interval N   Интервал обновления в секундах (из .env: {interval})
  -h, --help         Показать эту справку

Переменные окружения (backend/.env):
  FTP_LOG_DIR        Директория с лог-файлами
  FTP_POLL_INTERVAL  Интервал обновления

Примеры:
  python file_watcher.py                              # Меню выбора файла
  python file_watcher.py testdata/ftp/2025-11-29.txt  # Конкретный файл
  python file_watcher.py -d C:/logs -n 5 -i 1         # Другая директория
""")
        sys.exit(0)
    
    i = 0
    while i < len(args):
        arg = args[i]
        
        if arg in ('-n', '--count') and i + 1 < len(args):
            count = int(args[i + 1])
            i += 2
        elif arg in ('-i', '--interval') and i + 1 < len(args):
            interval = float(args[i + 1])
            i += 2
        elif arg in ('-d', '--dir') and i + 1 < len(args):
            default_dir = args[i + 1]
            i += 2
        elif not arg.startswith('-'):
            file_path = arg
            i += 1
        else:
            i += 1
    
    # Если файл не указан - показываем меню выбора
    if not file_path:
        selected = select_file_menu(default_dir)
        if selected:
            file_path = str(selected)
        else:
            print("Файл не выбран. Выход.")
            sys.exit(0)
    
    watch_file(file_path, count, interval)


if __name__ == "__main__":
    main()
