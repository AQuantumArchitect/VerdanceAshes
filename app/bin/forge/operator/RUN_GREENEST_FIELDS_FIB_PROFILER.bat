@echo off
setlocal
powershell -ExecutionPolicy Bypass -File "%~dp0scripts\run_translation_profiler.ps1" -ScenarioPath "%~dp0data\scenarios\greenest_fields.playable.json"
if errorlevel 1 (
  echo.
  echo Verdance Greenest Fields profiler failed. Check the terminal output above.
  pause
  exit /b 1
)
echo.
echo Verdance Greenest Fields profiler complete. Check headless_runs\fib_profiler_*.
pause
