@echo off
setlocal
REM Co-op: join a friend's sortie (app\bin\JOIN.bat; verdance_kernel.coop).
call "%~dp0app\bin\JOIN.bat" %*
exit /b %ERRORLEVEL%
