@echo off
setlocal
cd /d "%~dp0..\..\..\.."
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0..\..\..\..\scripts\build_next_mission_v1.ps1" -SaveGame
pause
