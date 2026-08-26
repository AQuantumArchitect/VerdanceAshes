@echo off
setlocal
call "%~dp0..\_env.bat"
echo === Proxy story hearth (HTTP) ===
echo Open http://127.0.0.1:8765/
start "" "http://127.0.0.1:8765/"
"%VERDANCE_PY%" -m quantum_bar_ai.story_http --port 8765
exit /b %ERRORLEVEL%
