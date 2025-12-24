"""
FTP утилиты для launcher.

Защита от типичных FTP проблем:
1. Ограничение соединений (550/421) - retry с exponential backoff
2. Passive/Active mode - попытка обоих режимов
3. Зависшие соединения - таймауты
4. Кодировки - multi-encoding decode
"""

from ftplib import FTP, error_temp, error_perm
import io
from datetime import datetime
import re
import time
import socket


# Retry settings
MAX_RETRIES = 3
RETRY_BASE_DELAY = 2.0  # seconds, doubles each retry
CONNECTION_TIMEOUT = 15  # seconds
OPERATION_TIMEOUT = 30   # seconds

# Кодировки для декодирования (в порядке приоритета)
ENCODINGS = ['utf-8', 'cp1251', 'cp866', 'latin-1']


class FTPConnectionManager:
    """
    Менеджер FTP соединений с защитой от всех типичных проблем.
    
    Использование:
        with FTPConnectionManager(host, port, user, password, base_path) as ftp:
            files = ftp.nlst()
    """
    
    def __init__(self, host: str, port: int, user: str, password: str, base_path: str):
        self.host = host
        self.port = port
        self.user = user
        self.password = password
        self.base_path = base_path
        self.ftp: FTP = None
        self._passive_mode = True  # Start with passive (works behind NAT)
    
    def __enter__(self) -> FTP:
        self.ftp = get_ftp_connection(
            self.host, self.port, self.user, self.password, self.base_path
        )
        if not self.ftp:
            raise ConnectionError(f"Не удалось подключиться к {self.host}:{self.port}")
        return self.ftp
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.ftp:
            try:
                self.ftp.quit()
            except Exception:
                pass
            self.ftp = None
        return False


def get_ftp_connection(
    host: str, 
    port: int, 
    user: str, 
    password: str, 
    base_path: str, 
    retries: int = MAX_RETRIES,
    passive: bool = True
) -> FTP:
    """
    Подключение к FTP с полной защитой от ошибок.
    
    Защита:
    - Retry с exponential backoff при 550/421
    - Таймауты на все операции
    - Попытка passive/active mode
    - Binary mode для корректного чтения
    
    Args:
        host: FTP хост
        port: FTP порт
        user: Имя пользователя
        password: Пароль
        base_path: Базовый путь
        retries: Количество попыток
        passive: Использовать passive mode
    
    Returns:
        FTP объект или None при ошибке
    """
    last_error = None
    
    for attempt in range(retries):
        try:
            ftp = FTP()
            ftp.connect(host, port, timeout=CONNECTION_TIMEOUT)
            ftp.login(user, password)
            
            # Set passive/active mode
            ftp.set_pasv(passive)
            
            # Set binary mode (защита от конвертации \r\n)
            ftp.voidcmd('TYPE I')
            
            # Change to base directory
            ftp.cwd(base_path)
            
            return ftp
            
        except (error_temp, error_perm) as e:
            last_error = e
            error_str = str(e)
            
            # 550 = server busy/file not found, 421 = too many connections
            if "550" in error_str or "421" in error_str or "busy" in error_str.lower():
                delay = RETRY_BASE_DELAY * (2 ** attempt)
                print(f"[FTP] Сервер занят ({error_str[:50]}), повтор {attempt + 1}/{retries} через {delay:.1f}с...")
                time.sleep(delay)
                continue
            
            # Try switching passive/active mode on first failure
            if attempt == 0 and passive:
                print(f"[FTP] Passive mode failed, trying active mode...")
                return get_ftp_connection(host, port, user, password, base_path, retries - 1, passive=False)
            
            print(f"[FTP] Ошибка подключения: {e}")
            return None
            
        except socket.timeout:
            last_error = "Connection timeout"
            delay = RETRY_BASE_DELAY * (2 ** attempt)
            print(f"[FTP] Таймаут подключения, повтор {attempt + 1}/{retries} через {delay:.1f}с...")
            time.sleep(delay)
            continue
            
        except Exception as e:
            last_error = e
            print(f"[FTP] Ошибка подключения: {e}")
            return None
    
    print(f"[FTP] Не удалось подключиться после {retries} попыток. Последняя ошибка: {last_error}")
    return None


def decode_content(content_bytes: bytes) -> str:
    """
    Декодирование содержимого файла с поддержкой нескольких кодировок.
    
    Пробует: UTF-8 -> CP1251 -> CP866 -> Latin-1
    """
    if not content_bytes:
        return ""
    
    for encoding in ENCODINGS:
        try:
            return content_bytes.decode(encoding)
        except UnicodeDecodeError:
            continue
    
    # Fallback: decode с игнорированием ошибок
    return content_bytes.decode('utf-8', errors='ignore')


def read_file_safe(ftp: FTP, filename: str, timeout: int = OPERATION_TIMEOUT) -> bytes:
    """
    Безопасное чтение файла с FTP с таймаутом.
    
    Args:
        ftp: FTP соединение
        filename: Имя файла
        timeout: Таймаут операции
    
    Returns:
        Содержимое файла в байтах
    """
    # Set socket timeout for this operation
    old_timeout = ftp.sock.gettimeout()
    ftp.sock.settimeout(timeout)
    
    try:
        buffer = io.BytesIO()
        ftp.retrbinary(f'RETR {filename}', buffer.write)
        return buffer.getvalue()
    finally:
        ftp.sock.settimeout(old_timeout)


def read_file_from_position(ftp: FTP, filename: str, position: int = 0) -> tuple:
    """
    Чтение файла с определённой позиции (для incremental polling).
    
    Защита от неполных строк:
    - Читает данные с позиции
    - Возвращает только полные строки
    - Возвращает новую позицию для следующего чтения
    
    Args:
        ftp: FTP соединение
        filename: Имя файла
        position: Начальная позиция в байтах
    
    Returns:
        Tuple (content: str, new_position: int)
    """
    # Get file size
    try:
        size = ftp.size(filename)
        if size is None or size <= position:
            return "", position
    except Exception:
        return "", position
    
    # Read from position
    buffer = io.BytesIO()
    ftp.retrbinary(f'RETR {filename}', buffer.write, rest=position)
    content_bytes = buffer.getvalue()
    
    # Decode
    content = decode_content(content_bytes)
    
    # Handle incomplete lines
    if content and not content.endswith('\n'):
        last_newline = content.rfind('\n')
        if last_newline >= 0:
            # Return only complete lines
            complete_content = content[:last_newline + 1]
            incomplete_bytes = len(content[last_newline + 1:].encode('utf-8'))
            new_position = size - incomplete_bytes
            return complete_content, new_position
        else:
            # No complete lines yet
            return "", position
    
    return content, size


def parse_unload_events(content: str) -> list:
    """Парсинг событий разгрузки подвесов"""
    events = []
    pattern = r'(\d{2}:\d{2}:\d{2}\.\d{3}).*Команда от CJ2M: Разгрузка подвеса - (\d+)'
    
    for line in content.split('\n'):
        match = re.search(pattern, line)
        if match:
            events.append({
                'time': match.group(1),
                'hanger': int(match.group(2))
            })
    
    return events


def test_connection(host: str, port: int, user: str, password: str, base_path: str) -> dict:
    """
    Тестирование FTP подключения с диагностикой.
    
    Returns:
        Dict с результатами теста
    """
    result = {
        'success': False,
        'host': host,
        'port': port,
        'passive_mode': None,
        'server_banner': None,
        'files_count': 0,
        'error': None,
        'latency_ms': 0,
    }
    
    start_time = time.time()
    
    try:
        ftp = get_ftp_connection(host, port, user, password, base_path)
        if ftp:
            result['success'] = True
            result['server_banner'] = ftp.getwelcome()
            result['passive_mode'] = ftp.passiveserver
            
            try:
                files = ftp.nlst()
                result['files_count'] = len(files)
            except Exception:
                pass
            
            ftp.quit()
        else:
            result['error'] = "Connection failed after retries"
            
    except Exception as e:
        result['error'] = str(e)
    
    result['latency_ms'] = int((time.time() - start_time) * 1000)
    return result
