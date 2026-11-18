@echo off
setlocal
call "%~dp0_env.bat"
if errorlevel 1 (
  pause
  exit /b 1
)
echo.
echo  ============================================================
echo   VERDANCE'S ASHES  -  JOIN A FRIEND'S SORTIE
echo  ============================================================
echo.
echo  Co-op: one player per hero. The campaign lives on your friend's PC;
echo  this joins the sortie they are playing, as one of the company's heroes.
echo  Their PC must be reachable on port 8452 (same network, a VPN, or forwarded).
echo.
set "VA_JOIN_HOST=%~1"
if "%VA_JOIN_HOST%"=="" set /p VA_JOIN_HOST=Host address (their IP): 
if "%VA_JOIN_HOST%"=="" ( echo No address given. & pause & exit /b 2 )
if not "%~1"=="" shift
"%VERDANCE_PY%" -m verdance_kernel join --workspace "%VERDANCE_ROOT%" --to "%VA_JOIN_HOST%" %1 %2
set ERR=%ERRORLEVEL%
pause
exit /b %ERR%
