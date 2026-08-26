@echo off
setlocal
call "%~dp0..\_env.bat"
echo === Fair full campaign arcs 1-3 (champion craft + train bar brain) ===
echo Difficulty defaults to craft_recipe.json (overnight champion).
"%VERDANCE_PY%" -m quantum_bar_ai.beat_campaign --once --arcs 1,2,3 --train %*
exit /b %ERRORLEVEL%
