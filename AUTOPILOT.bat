@echo off
setlocal
REM A BARbarian (hard_aggressive) plays the company's seat, sortie after sortie, headless.
REM Runs on a copy of the workspace: your campaign is untouched. Don't play BAR while it runs.
REM   AUTOPILOT.bat                       defaults (Verse boosted, prefers All That Simmers)
REM   AUTOPILOT.bat --windowed            watch it in spring.exe
REM   AUTOPILOT.bat --profile hard        plain hard BARb
call "%~dp0app\bin\_env.bat"
if errorlevel 1 ( pause & exit /b 1 )
"%VERDANCE_PY%" "%VERDANCE_ROOT%\tools\autopilot_campaign_v1.py" %*
echo.
echo  Logs: %VERDANCE_ROOT%\autopilot_runs\
pause
