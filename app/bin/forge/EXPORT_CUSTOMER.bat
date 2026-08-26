@echo off
setlocal
call "%~dp0..\_env.bat"
if errorlevel 1 exit /b 1
REM Legacy name → consolidated ship (full kernel dist, not brochure).
echo === EXPORT_CUSTOMER is now SHIP (scripts\ship.ps1) ===
echo === Optional: pass -InstallToMyGames for full My Games install ===
powershell -NoProfile -ExecutionPolicy Bypass -File "%VERDANCE_ROOT%\scripts\ship.ps1" -Workspace "%VERDANCE_ROOT%" %*
exit /b %ERRORLEVEL%
