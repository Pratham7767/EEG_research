@echo off
REM Double-click: start the session monitor with the real Capsule headphones.
cd /d "%~dp0"
python app.py %*
if errorlevel 1 pause
