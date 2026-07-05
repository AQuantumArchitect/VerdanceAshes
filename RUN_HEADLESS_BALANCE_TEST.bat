@echo off
setlocal
powershell -ExecutionPolicy Bypass -File "%~dp0scripts\run_headless_balance_test.ps1"
if errorlevel 1 (
  echo.
  echo Verdance headless balance test failed. Check the terminal output above.
  pause
  exit /b 1
)
echo.
echo Verdance headless balance test complete. Check headless_runs\balance_*.
pause
