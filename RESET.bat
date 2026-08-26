@echo off
setlocal
title Verdance Ashes - RESET campaign
call "%~dp0app\bin\_env.bat"
if errorlevel 1 (
  pause
  exit /b 1
)

echo.
echo  This will BACK UP then wipe campaign_state.json and rebuild hub.
echo  Workspace: %VERDANCE_ROOT%
echo.
set /p CONFIRM=Type YES to reset: 
if /I not "%CONFIRM%"=="YES" (
  echo Cancelled.
  pause
  exit /b 0
)

powershell -NoProfile -ExecutionPolicy Bypass -File "%VERDANCE_ROOT%\scripts\player\reset_campaign.ps1" -Workspace "%VERDANCE_ROOT%"
set ERR=%ERRORLEVEL%
echo.
if %ERR% neq 0 (
  echo RESET failed with code %ERR%.
) else (
  echo Reset complete. Run PLAY.bat when ready.
)
pause
exit /b %ERR%
