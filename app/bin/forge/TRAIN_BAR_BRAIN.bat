@echo off
setlocal
call "%~dp0..\_env.bat"
echo === Train / inspect BAR brain weights ===
"%VERDANCE_PY%" -m quantum_bar_ai.train_bar_brain %*
exit /b %ERRORLEVEL%
