@echo off
setlocal
cd /d "%~dp0..\..\..\.."
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0..\..\..\..\scripts\verdance_process_health.ps1" -StopAllVerdance
pause
