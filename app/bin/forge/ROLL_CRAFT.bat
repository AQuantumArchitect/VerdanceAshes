@echo off
setlocal
call "%~dp0..\_env.bat"
echo === Roll champion craft into live campaign ===
"%VERDANCE_PY%" -m quantum_bar_ai.craft_apply --roll-in --verify %*
exit /b %ERRORLEVEL%
