@echo off
REM Double-click: DEMO mode with the real headphones (10-minute presentation timings).
cd /d "%~dp0"
call "%~dp0_python.bat" app.py --mode demo %*
if errorlevel 1 pause
