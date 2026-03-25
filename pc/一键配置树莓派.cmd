@echo off
setlocal
chcp 65001 >nul
net session >nul 2>&1
if %errorlevel% neq 0 (
  powershell -NoProfile -ExecutionPolicy Bypass -Command "Start-Process -FilePath '%~f0' -Verb RunAs"
  exit /b 0
)
set "SCRIPT_DIR=%~dp0"
set "PYTHONW=%LocalAppData%\Programs\Python\Python311\pythonw.exe"
set "PYTHON=%LocalAppData%\Programs\Python\Python311\python.exe"
set "SCRIPT_PATH=%SCRIPT_DIR%tools\pi_one_click_setup.py"
set "CONFIG_PATH=%SCRIPT_DIR%pi_one_click_setup.json"

if exist "%PYTHONW%" (
  start "" /min "%PYTHONW%" "%SCRIPT_PATH%" --config "%CONFIG_PATH%"
) else (
  start "" /min "%PYTHON%" "%SCRIPT_PATH%" --config "%CONFIG_PATH%"
)
exit /b 0
