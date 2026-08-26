@echo off
setlocal
call "%~dp0app\bin\SHIP.bat" %*
exit /b %ERRORLEVEL%
