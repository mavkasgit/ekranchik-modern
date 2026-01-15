@echo off
REM Build Ekranchik Modern Launcher to .exe

echo ========================================
echo Building Ekranchik Modern Launcher
echo ========================================
echo.

REM Check if pyinstaller is installed
python -c "import PyInstaller" 2>nul
if errorlevel 1 (
    echo Installing launcher dependencies...
    pip install -r requirements.txt
)

echo.
echo Building executable...
echo.

REM Используем spec файл для onefile сборки
pyinstaller --noconfirm EkranchikLauncher.spec

echo.
echo ========================================
echo Build complete!
echo Executable: dist\EkranchikLauncher.exe
echo ========================================
echo.
echo Place dashboard_kiosk.py next to the exe
echo.

pause
