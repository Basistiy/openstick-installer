@echo off
REM OpenStick Linux Installer launcher for Windows
cd /d "%~dp0"
set PYTHONUTF8=1
set PYTHONIOENCODING=utf-8
chcp 65001 >nul 2>&1
where py >nul 2>nul
if %ERRORLEVEL% equ 0 (
    py -3 main.py %*
) else (
    python main.py %*
)
pause
