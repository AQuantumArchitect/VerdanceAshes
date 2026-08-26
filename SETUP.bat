@echo off
setlocal
title Verdance Ashes - SETUP
call "%~dp0app\bin\_env.bat"
if errorlevel 1 (
  pause
  exit /b 1
)

echo.
echo  ============================================================
echo   VERDANCE'S ASHES  -  SETUP
echo  ============================================================
echo   Workspace: %VERDANCE_ROOT%
echo   Python:    %VERDANCE_PY%
echo  ============================================================
echo.

powershell -NoProfile -ExecutionPolicy Bypass -File "%VERDANCE_ROOT%\scripts\player\setup_play.ps1" -Workspace "%VERDANCE_ROOT%"
set ERR=%ERRORLEVEL%
echo.
if %ERR% neq 0 (
  echo SETUP failed with code %ERR%.
  echo See docs\DEPLOY_TRUTH.md
  pause
  exit /b %ERR%
)
echo.
echo  Next: double-click PLAY.bat  (leave it open while you play)
echo.
pause
exit /b 0
