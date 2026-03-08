@echo off
setlocal
set ROOT=%~dp0..
set PS_SCRIPT=%~dp0build_portable_zip.ps1
echo [LabDetector] Running portable zip build script...
powershell -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%PS_SCRIPT%"
set EXIT_CODE=%ERRORLEVEL%
if not "%EXIT_CODE%"=="0" (
  echo.
  echo [LabDetector] Portable zip build failed. Exit code: %EXIT_CODE%
  echo Check logs under "%ROOT%\tmp\build_logs"
) else (
  echo.
  echo [LabDetector] Portable zip build completed.
)
pause
exit /b %EXIT_CODE%
