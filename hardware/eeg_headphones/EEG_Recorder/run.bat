@echo off
REM EEG + Voice Recording Application Launcher
REM This script starts the GUI application

echo.
echo ============================================
echo  EEG + Voice Recording Application
echo ============================================
echo.

cd /d "%~dp0"

REM Check Python
c:/python313/python.exe --version >nul 2>&1
if errorlevel 1 (
    echo Error: Python 3.13 not found
    echo Please install Python 3.13 and add to PATH
    pause
    exit /b 1
)

echo [1/3] Checking dependencies...
c:/python313/python.exe -c "import PyQt5, numpy, scipy, pandas, h5py, soundfile; print('✓ All dependencies installed')" >nul 2>&1
if errorlevel 1 (
    echo Error: Missing dependencies
    echo Run: pip install -r requirements.txt --user
    pause
    exit /b 1
)

echo [2/3] Verifying modules...
c:/python313/python.exe -c "import sys; sys.path.insert(0, '..'); from core import *; from ui import *; print('✓ All modules loaded')" >nul 2>&1
if errorlevel 1 (
    echo Error: Module loading failed
    pause
    exit /b 1
)

echo [3/3] Starting application...
c:/python313/python.exe app.py

if errorlevel 1 (
    echo.
    echo Application encountered an error (exit code: %errorlevel%)
    pause
)
