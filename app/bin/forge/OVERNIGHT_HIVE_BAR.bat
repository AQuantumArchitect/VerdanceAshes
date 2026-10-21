@echo off
REM Overnight hive <-> quantum-BAR residual bridge (v0.8.5). Forge tool, not the player path.
REM No spring.exe. No human. ASCII only.
setlocal
call "%~dp0..\_env.bat"
if errorlevel 1 (
  pause
  exit /b 1
)
powershell -NoProfile -ExecutionPolicy Bypass -File "%VERDANCE_ROOT%\scripts\player\overnight_hive_bar.ps1" %*
exit /b %ERRORLEVEL%
