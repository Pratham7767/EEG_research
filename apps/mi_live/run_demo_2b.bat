@echo off
REM Real EEG from BCI Competition IV 2b (subject B04, session 4) streamed as if live.
REM The model never saw B04. Change --sub 1..9, --session 4 or 5, --speed 2 to go faster.
cd /d "%~dp0"
C:\Python313\python.exe live.py --source replay2b --sub 4 --session 4 --speed 1 %*
