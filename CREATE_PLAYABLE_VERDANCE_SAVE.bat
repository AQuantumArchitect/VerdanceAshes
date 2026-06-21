@echo off
setlocal
powershell -ExecutionPolicy Bypass -File "%~dp0scripts\install_playable_slice.ps1" -SaveGame
if errorlevel 1 (
  echo.
  echo Verdance savegame generation failed. Check the terminal output above.
  pause
  exit /b 1
)
echo.
echo Verdance savegame generated. Load "verdance_playable_ats_001" from the BAR client.
pause
