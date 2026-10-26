@echo off
REM MI Live with the headphones. Double-click to start.
cd /d "%~dp0"
C:\Python313\python.exe live.py --source headset %*
