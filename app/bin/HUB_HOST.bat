@echo off
setlocal
call "%~dp0_env.bat"
echo.
echo  Kernel HTTP only (operator / no auto-UI).
echo  Player path: PLAY.bat
echo.
"%VERDANCE_PY%" -m verdance_kernel serve --workspace "%VERDANCE_ROOT%" --no-browser
exit /b %ERRORLEVEL%
