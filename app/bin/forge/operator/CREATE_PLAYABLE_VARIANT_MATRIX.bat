@echo off
setlocal
powershell -ExecutionPolicy Bypass -File "%~dp0scripts\run_playable_variant_matrix.ps1" -SaveGame
if errorlevel 1 (
  echo.
  echo Verdance variant matrix generation failed. Check the terminal output above.
  pause
  exit /b 1
)
echo.
echo Verdance variant matrix generated. Check playable_runs\matrix_* for save names.
pause
