@echo off
setlocal
REM Canonical player entry (v0.8+). See docs\DEPLOY_TRUTH.md
call "%~dp0app\bin\PLAY.bat" %*
exit /b %ERRORLEVEL%
