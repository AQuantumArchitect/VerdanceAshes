@echo off
setlocal
title Verdance Ashes - RESET campaign
call "%~dp0app\bin\_env.bat"
if errorlevel 1 (
  pause
  exit /b 1
)

echo.
echo  ============================================================
echo   FULL CAMPAIGN RESET
echo  ============================================================
echo   Workspace: %VERDANCE_ROOT%
echo.
echo   This will:
echo     - Backup then wipe campaign_state.json
echo     - Archive stale inbox/outbox sortie results
echo     - Clear generated Act-N mission lua so BAR cannot
echo       reload a naked-com / mid-arc Drop by accident
echo     - Rebuild a fresh hub (mission 1, starter Punch)
echo     - Metal bank starts at 0x1km$
echo.
echo   Your previous save lands in state\backups\.
echo.
echo   IMPORTANT: you must type YES exactly ^(not Y / yes please^).
echo   RESET also stops any live PLAY kernel on :8770 so the hub
echo   cannot keep hosting the old campaign after the wipe.
echo  ============================================================
echo.
set /p CONFIRM=Type YES to reset: 
if /I not "%CONFIRM%"=="YES" (
  echo Cancelled - campaign was NOT wiped.
  pause
  exit /b 0
)

powershell -NoProfile -ExecutionPolicy Bypass -File "%VERDANCE_ROOT%\scripts\player\reset_campaign.ps1" -Workspace "%VERDANCE_ROOT%"
set ERR=%ERRORLEVEL%
echo.
if %ERR% neq 0 (
  echo RESET failed with code %ERR%.
  echo If you still see Python syntax errors inside PowerShell, the
  echo reset script needs a refresh - report it on the GitHub issues page.
) else (
  echo Reset complete.
  echo Hard-refresh the hub ^(Ctrl+F5^), then run PLAY.bat when ready.
)
pause
exit /b %ERR%
