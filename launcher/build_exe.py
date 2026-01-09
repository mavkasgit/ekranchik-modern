#!/usr/bin/env python
"""
Сборка EXE файла для Ekranchik Launcher
"""
import subprocess
import sys
from pathlib import Path

LAUNCHER_DIR = Path(__file__).parent

def build():
    print("=" * 60)
    print("  Сборка Ekranchik Launcher")
    print("=" * 60)
    
    # Файлы для включения
    data_files = [
        ("theme.json", "."),
        ("icons.py", "."),
    ]
    
    # Иконка
    icon_path = LAUNCHER_DIR / "launcher.ico"
    
    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--onefile",
        "--windowed",
        "--name", "EkranchikLauncher",
        "--clean",
    ]
    
    # Добавляем иконку если есть
    if icon_path.exists():
        cmd.extend(["--icon", str(icon_path)])
    
    # Добавляем data файлы
    for src, dst in data_files:
        src_path = LAUNCHER_DIR / src
        if src_path.exists():
            cmd.extend(["--add-data", f"{src_path};{dst}"])
    
    # Hidden imports
    hidden_imports = [
        "customtkinter",
        "PIL",
        "PIL.Image",
        "PIL.ImageDraw",
        "pystray",
        "pystray._win32",
        "dotenv",
    ]
    for imp in hidden_imports:
        cmd.extend(["--hidden-import", imp])
    
    # Главный файл
    cmd.append(str(LAUNCHER_DIR / "launcher.py"))
    
    print(f"\nКоманда: {' '.join(cmd)}\n")
    
    result = subprocess.run(cmd, cwd=LAUNCHER_DIR)
    
    if result.returncode == 0:
        print("\n" + "=" * 60)
        print("  УСПЕХ!")
        print(f"  EXE: {LAUNCHER_DIR / 'dist' / 'EkranchikLauncher.exe'}")
        print("=" * 60)
    else:
        print("\n" + "=" * 60)
        print("  ОШИБКА СБОРКИ")
        print("=" * 60)
    
    return result.returncode


if __name__ == "__main__":
    sys.exit(build())
