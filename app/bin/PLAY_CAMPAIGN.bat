@echo off
REM Compat alias → product launcher (kernel Phase 1+)
setlocal
call "%~dp0PLAY.bat"
exit /b %ERRORLEVEL%
