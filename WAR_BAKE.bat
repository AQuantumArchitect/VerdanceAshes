@echo off
setlocal
REM The standing wars: BARbarians fight on each map (dry, headless), then the field is saved as the map's
REM starting conditions (the company's seat is pulled out). Recipes: data\base_templates\<map>\war_recipe.json
REM   WAR_BAKE.bat                         every map that has a recipe and no war yet
REM   WAR_BAKE.bat --map tabula            one map, again
REM   WAR_BAKE.bat --all                   every map, again
REM   WAR_BAKE.bat --windowed              watch it in spring.exe
REM Don't play BAR while it runs.
call "%~dp0app\bin\_env.bat"
if errorlevel 1 ( pause & exit /b 1 )
"%VERDANCE_PY%" "%VERDANCE_ROOT%\tools\war_bake_v1.py" %*
echo.
echo  Logs: %VERDANCE_ROOT%\headless_runs\
pause
