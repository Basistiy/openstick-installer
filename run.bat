@echo off
REM OpenStick Linux Flasher launcher for Windows
cd /d "%~dp0"
where py >nul 2>nul
if %ERRORLEVEL% equ 0 (
    py -3 main.py %*
) else (
    python main.py %*
)
pause
