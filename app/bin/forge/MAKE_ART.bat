@echo off
setlocal
call "%~dp0..\_env.bat"
echo === Verdance campaign ART ceremony (multi-seed lock + brain + gallery) ===
"%VERDANCE_PY%" -m quantum_bar_ai.make_art --seeds 11,28,45 --difficulty 1.0 --export %*
exit /b %ERRORLEVEL%
