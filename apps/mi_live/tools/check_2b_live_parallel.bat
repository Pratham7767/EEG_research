@echo off
REM Runs tools\check_2b_live.py for the 9 subjects in parallel, then merges (tools\merge_check.py).
cd /d "%~dp0\.."
set OMP_NUM_THREADS=1
set OPENBLAS_NUM_THREADS=1
set MKL_NUM_THREADS=1
for %%s in (1 2 3 4 5 6 7 8 9) do start "chk%%s" /b cmd /c "C:\Python313\python.exe tools\check_2b_live.py %%s > _out\check_2b_live_B0%%s.txt 2>&1"
