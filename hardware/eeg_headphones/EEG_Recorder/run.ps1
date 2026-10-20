# EEG + Voice Recording Application Launcher (PowerShell)

$ErrorActionPreference = "Stop"

Write-Host ""
Write-Host "============================================" -ForegroundColor Cyan
Write-Host " EEG + Voice Recording Application" -ForegroundColor Cyan
Write-Host "============================================" -ForegroundColor Cyan
Write-Host ""

# Check Python
try {
    $pythonVersion = & "c:/python313/python.exe" --version 2>&1
    Write-Host "[✓] Python $pythonVersion" -ForegroundColor Green
}
catch {
    Write-Host "[✗] Python 3.13 not found" -ForegroundColor Red
    Write-Host "Please install Python 3.13 and configure PATH"
    exit 1
}

# Check dependencies
Write-Host "[1/3] Checking dependencies..." -ForegroundColor Yellow
try {
    & "c:/python313/python.exe" -c "import PyQt5, numpy, scipy, pandas, h5py, soundfile; print('     All dependencies OK')" | ForEach-Object { Write-Host $_ -ForegroundColor Green }
}
catch {
    Write-Host "[✗] Missing dependencies" -ForegroundColor Red
    Write-Host "Run: pip install -r requirements.txt --user"
    exit 1
}

# Verify modules
Write-Host "[2/3] Verifying application modules..." -ForegroundColor Yellow
try {
    & "c:/python313/python.exe" -c "import sys; sys.path.insert(0, '..'); from core.device_manager import DeviceManager; from core.calibration_manager import CalibrationManager; from core.export_manager import ExportManager; from ui.main_window import MainWindow; print('     All modules loaded')" | ForEach-Object { Write-Host $_ -ForegroundColor Green }
}
catch {
    Write-Host "[✗] Module loading failed: $_" -ForegroundColor Red
    exit 1
}

# Start application
Write-Host "[3/3] Starting application..." -ForegroundColor Yellow
Write-Host ""

& "c:/python313/python.exe" app.py

if ($LASTEXITCODE -ne 0) {
    Write-Host ""
    Write-Host "[✗] Application exited with code: $LASTEXITCODE" -ForegroundColor Red
    exit $LASTEXITCODE
}
