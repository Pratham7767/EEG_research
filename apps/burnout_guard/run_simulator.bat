@echo off
REM Double-click: try everything without headphones (Capsule "noise" simulator) and with
REM five weeks of made-up history in a separate demo_data folder (your real data is not touched).
cd /d "%~dp0"
set PY=python
if exist C:\Python313\python.exe set PY=C:\Python313\python.exe
%PY% app.py --simulate noise --fast --demo --data demo_data %*
if errorlevel 1 pause
