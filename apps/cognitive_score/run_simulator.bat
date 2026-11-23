@echo off
REM Double-click: try everything without headphones (Capsule "noise" simulator).
REM The calibration and baseline steps offer "Use defaults" buttons to skip the waits.
cd /d "%~dp0"
call "%~dp0_python.bat" app.py --simulate noise --fast %*
if errorlevel 1 pause
