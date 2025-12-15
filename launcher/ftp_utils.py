"""FTP утилиты для launcher"""

from ftplib import FTP
import io
from datetime import datetime
import re


def get_ftp_connection(host: str, port: int, user: str, password: str, base_path: str) -> FTP:
    """Подключение к FTP"""
    try:
        ftp = FTP()
        ftp.connect(host, port, timeout=10)
        ftp.login(user, password)
        ftp.cwd(base_path)
        return ftp
    except Exception:
        return None


def decode_content(content_bytes: bytes) -> str:
    """Декодирование содержимого файла"""
    encodings = ['utf-8', 'cp1251', 'latin-1']
    for enc in encodings:
        try:
            return content_bytes.decode(enc)
        except:
            continue
    return None


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
