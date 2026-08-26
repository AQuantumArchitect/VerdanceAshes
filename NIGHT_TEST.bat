@echo off
setlocal
title Verdance Ashes - NIGHT preflight
call "%~dp0app\bin\_env.bat"
if errorlevel 1 (
  pause
  exit /b 1
)

echo.
echo  Night preflight: abstract multi-rate + clash + Tnb BP + kernel sim
echo  Workspace: %VERDANCE_ROOT%
echo  No BAR launch.
echo.

powershell -NoProfile -ExecutionPolicy Bypass -File "%VERDANCE_ROOT%\scripts\player\night_preflight.ps1" -Workspace "%VERDANCE_ROOT%"
set ERR=%ERRORLEVEL%
echo.
if %ERR% neq 0 (
  echo NIGHT preflight failed with code %ERR%.
) else (
  echo Night preflight PASS. See docs\NIGHT_TEST_0_8_4.md and docs\NIGHT_PLAYTEST_SCORECARD.md
  echo Next: RESET.bat optional, SETUP.bat if needed, PLAY.bat
)
pause
exit /b %ERR%
