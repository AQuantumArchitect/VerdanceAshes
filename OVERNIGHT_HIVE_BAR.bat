@echo off
REM Overnight hive <-> quantum-BAR residual bridge (v0.8.5)
REM No spring.exe. No human. ASCII only.
setlocal
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\player\overnight_hive_bar.ps1" %*
exit /b %ERRORLEVEL%
