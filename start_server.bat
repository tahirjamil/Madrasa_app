@echo off
REM Madrasha App Server Startup Script
REM ===================================

echo Starting Madrasha App Server...
echo.

REM Check if virtual environment exists
if not exist ".venv\Scripts\python.exe" (
    echo Error: Virtual environment not found!
    echo Please run: python -m venv .venv
    echo Then run: .venv\Scripts\pip.exe install -r requirements.txt
    pause
    exit /b 1
)

REM Check if dev mode is enabled
if exist "dev.md" (
    echo Development mode detected
    set DEV_MODE=--dev
) else (
    echo Production mode
    set DEV_MODE=
)

REM Start the server
echo Starting server...
.venv\Scripts\python.exe run_server.py %DEV_MODE%

pause 