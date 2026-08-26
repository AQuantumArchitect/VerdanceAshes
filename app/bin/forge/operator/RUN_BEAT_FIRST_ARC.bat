@echo off
setlocal
cd /d "%~dp0..\..\..\.."
set PYTHONPATH=%~dp0..\..\..\tools;C:\Users\Luke Spooner\ws-win\umwelt\src
set QBAI_NO_LLM=1
"C:\Users\Luke Spooner\ws-win\umwelt\.venv\Scripts\python.exe" -m quantum_bar_ai.beat_first_arc --difficulty 1.0 --seeds 3 --max-rounds 8 %*
exit /b %ERRORLEVEL%
