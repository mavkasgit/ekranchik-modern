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


def get_ftp_connections_status(ftp_host: str, ftp_port: int = 21) -> dict:
    """
    Получить статус FTP соединений с данного хоста.
    
    Использует netstat для анализа TCP соединений к FTP серверу.
    
    Returns:
        Dict с информацией о соединениях:
        - total: общее количество соединений
        - established: активные соединения
        - time_wait: соединения в TIME_WAIT
        - close_wait: соединения в CLOSE_WAIT
        - connections: список всех соединений с деталями
    """
    import subprocess
    import sys
    
    result = {
        'host': ftp_host,
        'port': ftp_port,
        'total': 0,
        'established': 0,
        'time_wait': 0,
        'close_wait': 0,
        'fin_wait': 0,
        'listening': 0,
        'connections': [],
        'error': None
    }
    
    if sys.platform != 'win32':
        result['error'] = 'Only Windows supported'
        return result
    
    try:
        # Запускаем netstat
        proc = subprocess.run(
            ['netstat', '-ano'],
            capture_output=True,
            text=True,
            creationflags=subprocess.CREATE_NO_WINDOW
        )
        
        for line in proc.stdout.split('\n'):
            # Ищем соединения к FTP серверу
            if f'{ftp_host}:{ftp_port}' in line or f'{ftp_host}:21' in line:
                parts = line.split()
                if len(parts) >= 4:
                    conn_info = {
                        'local': parts[1] if len(parts) > 1 else '',
                        'remote': parts[2] if len(parts) > 2 else '',
                        'state': parts[3] if len(parts) > 3 else '',
                        'pid': parts[4] if len(parts) > 4 else ''
                    }
                    result['connections'].append(conn_info)
                    result['total'] += 1
                    
                    state = conn_info['state'].upper()
                    if 'ESTABLISHED' in state:
                        result['established'] += 1
                    elif 'TIME_WAIT' in state:
                        result['time_wait'] += 1
                    elif 'CLOSE_WAIT' in state:
                        result['close_wait'] += 1
                    elif 'FIN_WAIT' in state:
                        result['fin_wait'] += 1
                    elif 'LISTENING' in state:
                        result['listening'] += 1
                        
    except Exception as e:
        result['error'] = str(e)
    
    return result


def close_ftp_connections(ftp_host: str, ftp_port: int = 21) -> dict:
    """
    Закрыть все FTP соединения к указанному хосту.
    
    Убивает процессы, которые держат соединения к FTP серверу.
    ВНИМАНИЕ: Это принудительное закрытие, используйте осторожно!
    
    Returns:
        Dict с результатами:
        - closed: количество закрытых соединений
        - killed_pids: список убитых PID
        - errors: список ошибок
    """
    import subprocess
    import sys
    
    result = {
        'closed': 0,
        'killed_pids': [],
        'errors': [],
        'skipped_pids': []  # PID которые не убивали (системные)
    }
    
    if sys.platform != 'win32':
        result['errors'].append('Only Windows supported')
        return result
    
    # Получаем текущие соединения
    status = get_ftp_connections_status(ftp_host, ftp_port)
    
    if status['error']:
        result['errors'].append(status['error'])
        return result
    
    # Собираем уникальные PID (кроме 0 и системных)
    pids_to_kill = set()
    current_pid = str(subprocess.os.getpid())
    
    for conn in status['connections']:
        pid = conn.get('pid', '0')
        if pid and pid != '0' and pid != current_pid:
            # Не убиваем системные процессы
            try:
                pid_int = int(pid)
                if pid_int > 4:  # PID 0-4 обычно системные
                    pids_to_kill.add(pid)
            except ValueError:
                pass
    
    # Убиваем процессы
    for pid in pids_to_kill:
        try:
            subprocess.run(
                ['taskkill', '/PID', pid, '/F'],
                capture_output=True,
                creationflags=subprocess.CREATE_NO_WINDOW
            )
            result['killed_pids'].append(int(pid))
            result['closed'] += 1
        except Exception as e:
            result['errors'].append(f"Failed to kill PID {pid}: {e}")
    
    return result


def wait_for_ftp_available(
    host: str, 
    port: int, 
    user: str, 
    password: str, 
    base_path: str,
    max_wait: int = 30,
    close_existing: bool = True
) -> dict:
    """
    Дождаться доступности FTP сервера.
    
    Если сервер занят (550/421), опционально закрывает существующие соединения
    и ждёт освобождения.
    
    Args:
        host: FTP хост
        port: FTP порт
        user: Пользователь
        password: Пароль
        base_path: Базовый путь
        max_wait: Максимальное время ожидания (секунды)
        close_existing: Закрывать существующие соединения
    
    Returns:
        Dict с результатом:
        - success: удалось ли подключиться
        - wait_time: время ожидания
        - closed_connections: количество закрытых соединений
        - error: ошибка если не удалось
    """
    result = {
        'success': False,
        'wait_time': 0,
        'closed_connections': 0,
        'attempts': 0,
        'error': None
    }
    
    start_time = time.time()
    
    # Сначала проверяем текущие соединения
    if close_existing:
        status = get_ftp_connections_status(host, port)
        if status['total'] > 0:
            print(f"[FTP] Найдено {status['total']} существующих соединений, закрываем...")
            close_result = close_ftp_connections(host, port)
            result['closed_connections'] = close_result['closed']
            if close_result['closed'] > 0:
                time.sleep(1)  # Даём время закрыться
    
    # Пробуем подключиться
    while (time.time() - start_time) < max_wait:
        result['attempts'] += 1
        
        try:
            ftp = FTP()
            ftp.connect(host, port, timeout=CONNECTION_TIMEOUT)
            ftp.login(user, password)
            ftp.cwd(base_path)
            ftp.quit()
            
            result['success'] = True
            result['wait_time'] = time.time() - start_time
            return result
            
        except (error_temp, error_perm) as e:
            error_str = str(e)
            if "550" in error_str or "421" in error_str or "busy" in error_str.lower():
                # Сервер занят, ждём
                time.sleep(2)
                continue
            else:
                result['error'] = str(e)
                break
                
        except Exception as e:
            result['error'] = str(e)
            break
    
    result['wait_time'] = time.time() - start_time
    if not result['error']:
        result['error'] = f"Timeout after {max_wait}s"
    
    return result
