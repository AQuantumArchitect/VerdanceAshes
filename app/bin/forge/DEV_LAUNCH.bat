@echo off
setlocal
call "%~dp0..\_env.bat"
echo === DEV LAUNCH: champion craft + dense player telemetry ===
echo Rolls overnight craft into campaign, arms high-frequency human learning.
echo After you play: run DEV_HARVEST.bat
echo.
"%VERDANCE_PY%" -m quantum_bar_ai.dev_launch %*
exit /b %ERRORLEVEL%
