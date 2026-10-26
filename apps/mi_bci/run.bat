@echo off
REM MI-BCI app. Double-click to start. Use run_simulator.bat if no headset is connected.
cd /d "%~dp0"
C:\Python313\python.exe app.py %*
