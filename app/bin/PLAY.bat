@echo off
setlocal
call "%~dp0_env.bat"
if errorlevel 1 (
  pause
  exit /b 1
)
echo.
echo  ============================================================
echo   VERDANCE'S ASHES  -  PLAY
echo   The green is dying. Ashwalkers hold the line.
echo  ============================================================
echo.
echo  Kernel + war map + BAR bridge. Leave this window open while you play.
echo  This workspace is the Drop path: every Drop copies mod\VerdanceAshes.sdd
echo  from here into BAR's data\games and launches the sortie.
echo  First time? Run SETUP.bat once. RESET.bat starts the campaign over.
echo.
"%VERDANCE_PY%" -m verdance_kernel launch --workspace "%VERDANCE_ROOT%"
exit /b %ERRORLEVEL%
