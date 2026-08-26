@echo off
setlocal
call "%~dp0..\_env.bat"
echo === Fair first arc (local tools chassis, free) ===
"%VERDANCE_PY%" -m quantum_bar_ai.beat_first_arc --once --difficulty 1.0 %*
exit /b %ERRORLEVEL%
