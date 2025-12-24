"""
Локальный FTP сервер для тестирования.

Эмулирует Omron PLC:
- Создаёт файлы YYYY-MM-DD.txt
- Добавляет новые строки в реальном времени
- Поддерживает смену дня

Использование:
    python ftp_mock_server.py [--port 2121] [--interval 5]

Потом в .env:
    FTP_HOST=127.0.0.1
    FTP_PORT=2121
    FTP_USER=test
    FTP_PASSWORD=test
    FTP_BASE_PATH=/
"""

import os
import sys
import time
import random
import threading
import argparse
from datetime import datetime, timedelta
from pathlib import Path

# Добавляем путь к pyftpdlib
try:
    from pyftpdlib.authorizers import DummyAuthorizer
    from pyftpdlib.handlers import FTPHandler
    from pyftpdlib.servers import FTPServer
except ImportError:
    print("Установите pyftpdlib: pip install pyftpdlib")
    sys.exit(1)


class MockPLCSimulator:
    """Симулятор PLC который пишет события в файлы."""
    
    def __init__(self, data_dir: Path, interval: float = 5.0):
        self.data_dir = data_dir
        self.interval = interval
        self._running = False
        self._thread = None
        self.hangers = list(range(1, 51))  # Подвесы 1-50
        self.event_count = 0
    
    def _get_today_file(self) -> Path:
        """Получить путь к файлу сегодняшнего дня."""
        filename = datetime.now().strftime("%Y-%m-%d.txt")
        return self.data_dir / filename
    
    def _generate_event(self) -> str:
        """Генерация события разгрузки."""
        now = datetime.now()
        time_str = now.strftime("%H:%M:%S.%f")[:-3]  # HH:MM:SS.mmm
        hanger = random.choice(self.hangers)
        return f"{time_str} L# Команда от CJ2M: Разгрузка подвеса - {hanger} в поз. 34.\n"
    
    def _write_event(self):
        """Записать событие в файл."""
        file_path = self._get_today_file()
        event = self._generate_event()
        
        with open(file_path, 'a', encoding='utf-8') as f:
            f.write(event)
        
        self.event_count += 1
        print(f"[PLC] Event #{self.event_count}: {event.strip()}")
    
    def _simulation_loop(self):
        """Основной цикл симуляции."""
        print(f"[PLC] Симуляция запущена, интервал: {self.interval}с")
        
        while self._running:
            self._write_event()
            
            # Случайный интервал ±50%
            sleep_time = self.interval * (0.5 + random.random())
            time.sleep(sleep_time)
    
    def start(self):
        """Запустить симуляцию."""
        if self._running:
            return
        
        self._running = True
        self._thread = threading.Thread(target=self._simulation_loop, daemon=True)
        self._thread.start()
    
    def stop(self):
        """Остановить симуляцию."""
        self._running = False
        if self._thread:
            self._thread.join(timeout=2)


def main():
    parser = argparse.ArgumentParser(description='Mock FTP Server для тестирования')
    parser.add_argument('--port', type=int, default=2121, help='FTP порт (default: 2121)')
    parser.add_argument('--interval', type=float, default=5.0, help='Интервал событий в секундах')
    parser.add_argument('--data-dir', type=str, default=None, help='Директория для файлов')
    parser.add_argument('--no-simulate', action='store_true', help='Не генерировать события автоматически')
    args = parser.parse_args()
    
    # Создаём директорию для данных
    if args.data_dir:
        data_dir = Path(args.data_dir)
    else:
        data_dir = Path(__file__).parent.parent.parent / "testdata" / "ftp_mock"
    
    data_dir.mkdir(parents=True, exist_ok=True)
    print(f"[FTP] Директория данных: {data_dir}")
    
    # Создаём файл сегодняшнего дня если нет
    today_file = data_dir / datetime.now().strftime("%Y-%m-%d.txt")
    if not today_file.exists():
        today_file.touch()
        print(f"[FTP] Создан файл: {today_file.name}")
    
    # Настраиваем FTP сервер
    authorizer = DummyAuthorizer()
    authorizer.add_user("test", "test", str(data_dir), perm="elradfmw")
    authorizer.add_anonymous(str(data_dir), perm="elr")
    
    handler = FTPHandler
    handler.authorizer = authorizer
    handler.passive_ports = range(60000, 60100)
    
    server = FTPServer(("0.0.0.0", args.port), handler)
    server.max_cons = 5
    server.max_cons_per_ip = 3
    
    print(f"""
╔══════════════════════════════════════════════════════════════╗
║           Mock FTP Server для тестирования                  ║
╠══════════════════════════════════════════════════════════════╣
║  Адрес:     ftp://127.0.0.1:{args.port:<5}                          ║
║  Логин:     test                                             ║
║  Пароль:    test                                             ║
║  Путь:      /                                                ║
╠══════════════════════════════════════════════════════════════╣
║  Для .env:                                                   ║
║    FTP_HOST=127.0.0.1                                        ║
║    FTP_PORT={args.port:<5}                                         ║
║    FTP_USER=test                                             ║
║    FTP_PASSWORD=test                                         ║
║    FTP_BASE_PATH=/                                           ║
╚══════════════════════════════════════════════════════════════╝
""")
    
    # Запускаем симулятор PLC
    simulator = None
    if not args.no_simulate:
        simulator = MockPLCSimulator(data_dir, args.interval)
        simulator.start()
        print(f"[PLC] Автоматическая генерация событий каждые ~{args.interval}с")
    else:
        print("[PLC] Автоматическая генерация отключена (--no-simulate)")
    
    print("\nНажмите Ctrl+C для остановки...\n")
    
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n[FTP] Остановка сервера...")
        if simulator:
            simulator.stop()
        server.close_all()
        print("[FTP] Сервер остановлен")


if __name__ == "__main__":
    main()
