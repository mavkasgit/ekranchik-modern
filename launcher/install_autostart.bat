@echo off
chcp 65001 >nul
echo ========================================
echo  Установка автозапуска Ekranchik Kiosk
echo ========================================
echo.

:: Получаем путь к текущей директории
set SCRIPT_DIR=%~dp0
set PYTHONW=pythonw.exe
set SCRIPT=%SCRIPT_DIR%autostart.pyw

echo Скрипт: %SCRIPT%
echo.

:: Проверяем что файл существует
if not exist "%SCRIPT%" (
    echo ОШИБКА: Файл autostart.pyw не найден!
    pause
    exit /b 1
)

:: Удаляем старую задачу если есть
schtasks /delete /tn "Ekranchik Kiosk Autostart" /f >nul 2>&1

:: Создаём задачу в Планировщике
echo Создание задачи в Планировщике Windows...
schtasks /create /tn "Ekranchik Kiosk Autostart" /tr "\"%PYTHONW%\" \"%SCRIPT%\"" /sc onlogon /rl highest /f

if %errorlevel% equ 0 (
    echo.
    echo ✓ Автозапуск успешно установлен!
    echo.
    echo Киоск будет запускаться автоматически при входе в Windows.
    echo.
    echo Для удаления выполните: schtasks /delete /tn "Ekranchik Kiosk Autostart" /f
) else (
    echo.
    echo ОШИБКА: Не удалось создать задачу!
    echo Попробуйте запустить от имени Администратора.
)

echo.
pause
