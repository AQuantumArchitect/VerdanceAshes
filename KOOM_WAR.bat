@echo off
setlocal
REM Koom Valley, the standing war: six BARbarians (3 Armada vs 3 Null Mercs) fight 20 game minutes, headless,
REM then the field is saved as the map's starting conditions (the company's seat is pulled out).
REM   KOOM_WAR.bat                 20 game minutes
REM   KOOM_WAR.bat --minutes 13    a shorter war
REM   KOOM_WAR.bat --windowed      watch it in spring.exe
REM Don't play BAR while it runs.
call "%~dp0app\bin\_env.bat"
if errorlevel 1 ( pause & exit /b 1 )
"%VERDANCE_PY%" "%VERDANCE_ROOT%\tools\koom_war_bake_v1.py" %*
echo.
echo  Logs: %VERDANCE_ROOT%\headless_runs\
pause
