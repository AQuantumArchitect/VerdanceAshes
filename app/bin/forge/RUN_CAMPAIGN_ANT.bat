@echo off
setlocal
call "%~dp0..\_env.bat"
echo === Fair full campaign arcs 1-3 (ant subscription + train bar brain) ===
"%VERDANCE_PY%" -m quantum_bar_ai.beat_campaign --once --difficulty 1.0 --arcs 1,2,3 --ant --ant-every 6 --train %*
exit /b %ERRORLEVEL%
