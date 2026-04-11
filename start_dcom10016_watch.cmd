@echo off
setlocal
set SCRIPT_DIR=%~dp0
set PS_SCRIPT=%SCRIPT_DIR%dcom10016_watch.ps1

if not exist "%PS_SCRIPT%" (
  echo Missing file: %PS_SCRIPT%
  pause
  exit /b 1
)

echo Starting DCOM 10016 watcher...
echo A UAC prompt may appear. Click Yes.
echo.

powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%PS_SCRIPT%"

endlocal
