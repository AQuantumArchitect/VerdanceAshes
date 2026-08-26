@echo off
setlocal
cd /d "%~dp0"
title Verdance Playtest — END (telemetry harvest)
echo.
echo  === Harvesting YOUR playthrough (not AI proxy) ===
echo.

set PY=
if exist "C:\Users\Luke Spooner\ws-win\umwelt\.venv\Scripts\python.exe" set PY=C:\Users\Luke Spooner\ws-win\umwelt\.venv\Scripts\python.exe
if not defined PY if exist "C:\Users\Luke\ws-win\umwelt\.venv\Scripts\python.exe" set PY=C:\Users\Luke\ws-win\umwelt\.venv\Scripts\python.exe
if not defined PY set PY=python

"%PY%" "%~dp0tools\human_play_telemetry_v1.py" harvest
set RC=%ERRORLEVEL%
echo.
echo  Opening scorecard — fill what you can (5 bullets is enough).
start "" notepad "docs\HUMAN_PLAY_SCORECARD.md"
echo.
echo  Faces written:
echo    outbox\human_playthrough.latest.json
echo    yurt-sync\commons\vitals\human_playthrough.latest.json  (if sync present)
echo.
if %RC% neq 0 (
  echo  Harvest exited %RC% — still open the scorecard; partial notes help.
) else (
  echo  Harvest OK. Grok/hive can read human_player telemetry now.
)
echo.
pause
endlocal
