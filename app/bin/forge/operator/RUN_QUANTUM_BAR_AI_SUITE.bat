@echo off
setlocal
cd /d "%~dp0..\..\..\.."
powershell -ExecutionPolicy Bypass -File "%~dp0..\..\..\..\scripts\run_quantum_bar_ai_suite.ps1" %*
exit /b %ERRORLEVEL%
