@echo off
setlocal
call "%~dp0..\_env.bat"
powershell -NoProfile -ExecutionPolicy Bypass -File "%VERDANCE_ROOT%\scripts\verdance_console_server.ps1"
exit /b %ERRORLEVEL%
