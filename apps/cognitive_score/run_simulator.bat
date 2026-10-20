@echo off
REM Double-click: try the whole flow without headphones (Capsule "noise" simulator).
REM The calibration and baseline steps offer "Use typical values" buttons to skip the waits.
cd /d "%~dp0"
python app.py --simulate noise --fast %*
if errorlevel 1 pause
