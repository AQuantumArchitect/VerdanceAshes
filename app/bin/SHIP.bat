@echo off
setlocal
call "%~dp0_env.bat"
if errorlevel 1 (
  pause
  exit /b 1
)
echo === Ship consolidated dist (scripts\ship.ps1) ===
powershell -NoProfile -ExecutionPolicy Bypass -File "%VERDANCE_ROOT%\scripts\ship.ps1" -Workspace "%VERDANCE_ROOT%" %*
exit /b %ERRORLEVEL%
