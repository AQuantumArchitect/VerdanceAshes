@echo off
setlocal
cd /d "%~dp0..\..\..\.."
powershell -NoProfile -ExecutionPolicy Bypass -File "%CD%\scripts\play_session_v1.ps1" -Workspace "%CD%"
pause
