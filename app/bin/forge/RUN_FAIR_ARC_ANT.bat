@echo off
setlocal
call "%~dp0..\_env.bat"
echo === Fair first arc with yurt ant subscription steam ===
echo Law: ~/.grok/auth.json only — no metered XAI_API_KEY
"%VERDANCE_PY%" -m quantum_bar_ai.beat_first_arc --once --ant --ant-every 5 --difficulty 1.0 --base-seed 11 %*
exit /b %ERRORLEVEL%
