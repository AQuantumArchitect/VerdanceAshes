@echo off
setlocal
cd /d "%~dp0"
call "%~dp0app\bin\_env.bat"
if errorlevel 1 (
  pause
  exit /b 1
)
title Verdance's Ashes - Tracked Playtest

echo.
echo  ============================================================
echo   VERDANCE'S ASHES  -  TRACKED PLAYTEST
echo  ============================================================
echo.
echo   Plays the next campaign mission with the session recorded:
echo     - where your units go, zone by zone
echo     - what each zone is worth, over time
echo     - your orders, by class, through the mission
echo     - the outcome
echo.
echo   Leave THIS window open while you play. It waits for BAR to
echo   exit, then files the record and advances the campaign.
echo.
echo   To end a mission without finishing it, type in BAR's chat:
echo      /luarules vawin      (count it as a win)
echo      /luarules vafail     (count it as a loss)
echo      /luarules vapartial  (count it as partial)
echo   Alt-F4 also works - you keep the movement record, but the
echo   mission has no outcome and the campaign will not advance.
echo.
echo  ============================================================
echo.

powershell -NoProfile -ExecutionPolicy Bypass -File "%VERDANCE_ROOT%\scripts\play_tracked_v1.ps1" -Workspace "%VERDANCE_ROOT%" %*
set ERR=%ERRORLEVEL%

echo.
if %ERR% neq 0 (
  echo  Tracked playtest exited with code %ERR%.
  echo  Nothing was lost: re-run this file to try again.
) else (
  echo  Done. See reports\human_zone_flow.latest.md
)
echo.
pause
exit /b %ERR%
