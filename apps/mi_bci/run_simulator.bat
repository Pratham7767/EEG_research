@echo off
REM MI-BCI app on simulated EEG (no headset). Subject "SIM" so it never mixes with real data.
cd /d "%~dp0"
C:\Python313\python.exe app.py --simulate --subject SIM %*
