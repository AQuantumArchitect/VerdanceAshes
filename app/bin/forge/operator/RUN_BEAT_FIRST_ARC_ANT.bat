@echo off
setlocal
cd /d "%~dp0..\..\..\.."
REM Fair first arc with yurt ant_brain subscription steam (grok.com session).
REM Law: no XAI_API_KEY ??? subscription only (GROK_SUBSCRIPTION_BRAINS.md)
set PYTHONPATH=%~dp0..\..\..\tools;C:\Users\Luke Spooner\ws-win\umwelt\src;C:\Users\Luke Spooner\ws-win\yurt-sync\work\_wargen\coral
set XAI_API_KEY=
set GROK_API_KEY=
set GROK_ALLOW_API=
"C:\Users\Luke Spooner\ws-win\umwelt\.venv\Scripts\python.exe" -m quantum_bar_ai.beat_first_arc --once --ant --ant-every 5 --difficulty 1.0 %*
exit /b %ERRORLEVEL%
