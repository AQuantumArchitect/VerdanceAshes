@echo off
setlocal
call "%~dp0_env.bat"
if errorlevel 1 (
  pause
  exit /b 1
)
echo.
echo  ============================================================
echo   VERDANCE'S ASHES  —  PLAY
echo   The green is dying. Ashwalkers hold the line.
echo  ============================================================
echo.
echo  Kernel + war map + BAR bridge. Close this window when done.
echo  Playtest truth: Documents\My Games\VerdanceAshes (SHIP then point_bar_mod Deployed).
echo  First time? Run SETUP.bat once, then SHIP -InstallToMyGames.
echo.
"%VERDANCE_PY%" -m verdance_kernel launch --workspace "%VERDANCE_ROOT%"
exit /b %ERRORLEVEL%
