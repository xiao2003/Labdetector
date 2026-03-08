@echo off
setlocal
set ROOT=%~dp0..
set PS_SCRIPT=%~dp0build_installer.ps1
echo [LabDetector] Running installer build script...
powershell -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%PS_SCRIPT%"
set EXIT_CODE=%ERRORLEVEL%
if not "%EXIT_CODE%"=="0" (
  echo.
  echo [LabDetector] Installer build failed. Exit code: %EXIT_CODE%
  echo Check logs under "%ROOT%\tmp\build_logs"
) else (
  echo.
  echo [LabDetector] Installer build completed.
)
pause
exit /b %EXIT_CODE%
