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

pyinstaller --noconfirm ^
    --onefile ^
    --windowed ^
    --name "EkranchikLauncher" ^
    --icon=launcher.ico ^
    --add-data "tray_icons.py;." ^
    --hidden-import=customtkinter ^
    --hidden-import=PIL ^
    --hidden-import=pystray ^
    --hidden-import=dotenv ^
    launcher.py

echo.
echo ========================================
echo Build complete!
echo Executable: dist\EkranchikLauncher.exe
echo ========================================
echo.

pause
