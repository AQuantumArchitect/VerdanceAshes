@echo off
REM Field-driven war bake, preview only (does not replace the installed snapshot).
call "%~dp0app\bin\_env.bat"
if errorlevel 1 ( pause & exit /b 1 )
"%VERDANCE_PY%" "%VERDANCE_ROOT%\tools\war_bake_v1.py" --map ancient_bastion --field --no-install %*
pause
