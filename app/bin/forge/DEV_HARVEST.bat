@echo off
setlocal
call "%~dp0..\_env.bat"
echo === DEV HARVEST: infolog → bar_brain (human gold weight) ===
"%VERDANCE_PY%" -m quantum_bar_ai.dev_launch --harvest %*
exit /b %ERRORLEVEL%
