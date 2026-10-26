@echo off
REM MI Live without a headset: hold the Left / Right arrow keys to 'imagine'.
cd /d "%~dp0"
C:\Python313\python.exe live.py --source sim %*
