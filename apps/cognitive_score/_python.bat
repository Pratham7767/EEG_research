@echo off
REM Runs Python 3.13 (the plain "python" on this PC is 3.8 without the packages).
if exist "C:\Python313\python.exe" (
  "C:\Python313\python.exe" %*
) else (
  py -3 %*
)
exit /b %errorlevel%
