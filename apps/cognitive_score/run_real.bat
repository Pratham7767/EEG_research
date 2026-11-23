@echo off
REM Double-click: REAL USE mode with the real headphones (work-session timings).
cd /d "%~dp0"
call "%~dp0_python.bat" app.py --mode real %*
if errorlevel 1 pause
