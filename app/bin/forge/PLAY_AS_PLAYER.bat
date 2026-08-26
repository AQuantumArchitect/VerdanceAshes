@echo off
setlocal
call "%~dp0..\_env.bat"
echo.
echo  ============================================================
echo   VERDANCE — play as the human player (dense telemetry ON)
echo  ============================================================
echo.
echo  Workspace:
echo    %VERDANCE_ROOT%
echo.
echo  1) Arm craft + high-frequency player telemetry
echo  2) Build next mission seed
echo  3) Launch Beyond All Reason (you are the commander)
echo.
echo  After the match: double-click DEV_HARVEST.bat in this folder
echo  ============================================================
echo.

"%VERDANCE_PY%" -m quantum_bar_ai.dev_launch
if errorlevel 1 (
  echo.
  echo DEV arm failed. Still trying to launch so you can play...
  echo.
)

echo.
echo Building + launching next mission...
powershell -NoProfile -ExecutionPolicy Bypass -File "%VERDANCE_ROOT%\scripts\build_next_mission_v1.ps1" -Workspace "%VERDANCE_ROOT%" -Launch
set ERR=%ERRORLEVEL%
echo.
if %ERR% neq 0 (
  echo Launch script exited with code %ERR%.
  echo If BAR did not open, try: app\bin\operator\PLAY_NEXT_MISSION_V1.bat
) else (
  echo BAR should be open. Play the mission.
  echo When finished, run:
  echo   %~dp0DEV_HARVEST.bat
)
echo.
pause
exit /b %ERR%
