@echo off
REM Double-click: start window (choose Demo or Real use) with the real Capsule headphones.
cd /d "%~dp0"
call "%~dp0_python.bat" app.py %*
if errorlevel 1 pause
