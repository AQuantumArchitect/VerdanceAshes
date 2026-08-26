@echo off
setlocal
cd /d "%~dp0"
title Verdance Playtest — START
echo.
echo  === Verdance's Ashes — human playtest ===
echo  Build workspace: %CD%
echo.
echo  Opening player brief...
start "" notepad "docs\LUKE_PLAYTEST_TODAY.md"
timeout /t 1 /nobreak >nul
echo.
echo  Launching PLAY.bat (hub + war map + bridge).
echo  Leave that window open. Theater map -^> rim route -^> Drop into battle.
echo.
echo  When you finish: double-click END_PLAYTEST.bat
echo.
call "%~dp0PLAY.bat" %*
endlocal
