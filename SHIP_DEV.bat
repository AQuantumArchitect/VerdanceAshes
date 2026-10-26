@echo off
setlocal
REM Test-machine build: SHIP with the headless rig (AUTOPILOT, WAR_BAKE) and tests\ included.
call "%~dp0app\bin\SHIP.bat" -Dev %*
set ERR=%ERRORLEVEL%
pause
exit /b %ERR%
