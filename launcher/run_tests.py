#!/usr/bin/env python
"""
Запуск тестов лаунчера

Использование:
    python run_tests.py          # Только unit тесты
    python run_tests.py --all    # Все тесты (требует запущенный бэкенд)
    python run_tests.py --integration  # Только интеграционные тесты
"""
import sys
import subprocess
from pathlib import Path

LAUNCHER_DIR = Path(__file__).parent


def run_unit_tests():
    """Запуск unit тестов"""
    print("=" * 60)
    print("  UNIT ТЕСТЫ")
    print("=" * 60)
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "tests/test_launcher.py", "-v", "--tb=short"],
        cwd=LAUNCHER_DIR
    )
    return result.returncode


def run_integration_tests():
    """Запуск интеграционных тестов"""
    print("\n" + "=" * 60)
    print("  ИНТЕГРАЦИОННЫЕ ТЕСТЫ")
    print("  (требуют запущенный бэкенд)")
    print("=" * 60)
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "tests/test_integration.py", "-v", "--tb=short"],
        cwd=LAUNCHER_DIR
    )
    return result.returncode


def main():
    args = sys.argv[1:]
    
    if "--integration" in args:
        return run_integration_tests()
    elif "--all" in args:
        code1 = run_unit_tests()
        code2 = run_integration_tests()
        return max(code1, code2)
    else:
        return run_unit_tests()


if __name__ == "__main__":
    sys.exit(main())
