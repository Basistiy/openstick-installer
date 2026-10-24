@echo off
REM OpenStick Linux Installer launcher for Windows
cd /d "%~dp0"
set PYTHONUTF8=1
set PYTHONIOENCODING=utf-8
chcp 65001 >nul 2>&1

where py >nul 2>nul
if %ERRORLEVEL% equ 0 (
    py -3 main.py %*
    goto :end
)

where python >nul 2>nul
if %ERRORLEVEL% equ 0 (
    python main.py %*
    goto :end
)

echo.
echo ========================================================
echo [!] Python 3 was not detected on your system.
echo.
echo Please install Python 3.8 or newer from:
echo   https://www.python.org/downloads/
echo.
echo IMPORTANT: During setup, make sure to check:
echo   [x] "Add Python to PATH"
echo ========================================================
echo.

:end
pause
