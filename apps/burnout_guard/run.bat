@echo off
REM Double-click: start Burnout Guard with the real Capsule headphones.
cd /d "%~dp0"
set PY=python
if exist C:\Python313\python.exe set PY=C:\Python313\python.exe
%PY% app.py %*
if errorlevel 1 pause
