@echo off
REM Drives every screen automatically on the simulator with a temporary data folder. Exit code 0 = PASS.
cd /d "%~dp0"
set PY=python
if exist C:\Python313\python.exe set PY=C:\Python313\python.exe
%PY% app.py --selftest %*
echo Exit code %errorlevel%
pause
