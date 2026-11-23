@echo off
REM Double-click: automatic check of every screen in both modes on the simulator (exit code 0 = PASS).
cd /d "%~dp0"
call "%~dp0_python.bat" app.py --selftest --mode real --sessions "%TEMP%\cogscore_selftest"
if errorlevel 1 (echo REAL MODE: FAIL & pause & exit /b 1)
call "%~dp0_python.bat" app.py --selftest --mode demo --sessions "%TEMP%\cogscore_selftest"
if errorlevel 1 (echo DEMO MODE: FAIL & pause & exit /b 1)
echo SELF-TEST PASSED (both modes)
pause
