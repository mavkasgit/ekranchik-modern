#!/usr/bin/env python
"""
Сборка EXE файла для скрытого запуска системы (без иконки в таскбаре)
"""
import subprocess
import sys
from pathlib import Path

LAUNCHER_DIR = Path(__file__).parent

def build():
    print("=" * 60)
    print("  Сборка RunSystem.exe (скрытый запуск)")
    print("=" * 60)
    
    # Иконка для EXE
    icon_path = LAUNCHER_DIR / "launcher.ico"
    
    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--onefile",
        "--noconsole",  # Без консоли
        "--windowed",   # Без окна
        "--name", "RunSystem",
        "--clean",
        "--hidden-import", "screeninfo",
        "--hidden-import", "screeninfo.enumerators",
        "--hidden-import", "screeninfo.enumerators.windows",
    ]
    
    # Добавляем иконку для EXE если есть
    if icon_path.exists():
        cmd.extend(["--icon", str(icon_path)])
        print(f"✓ Иконка для EXE: {icon_path}")
    
    # Главный файл
    cmd.append(str(LAUNCHER_DIR / "run_system.pyw"))
    
    print(f"\nКоманда: {' '.join(cmd)}\n")
    
    result = subprocess.run(cmd, cwd=LAUNCHER_DIR)
    
    if result.returncode == 0:
        exe_path = LAUNCHER_DIR / 'dist' / 'RunSystem.exe'
        print("\n" + "=" * 60)
        print("  УСПЕХ!")
        print(f"  EXE: {exe_path}")
        print("=" * 60)
    else:
        print("\n" + "=" * 60)
        print("  ОШИБКА СБОРКИ")
        print("=" * 60)
    
    return result.returncode


if __name__ == "__main__":
    sys.exit(build())
