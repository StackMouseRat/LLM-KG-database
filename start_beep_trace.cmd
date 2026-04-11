@echo off
setlocal
set SCRIPT_DIR=%~dp0
set PS_SCRIPT=%SCRIPT_DIR%beep_trace_watcher.ps1

if not exist "%PS_SCRIPT%" (
  echo Missing file: %PS_SCRIPT%
  pause
  exit /b 1
)

echo Starting beep trace watcher...
echo A UAC prompt may appear. Please click Yes.
echo.

powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%PS_SCRIPT%"

endlocal
