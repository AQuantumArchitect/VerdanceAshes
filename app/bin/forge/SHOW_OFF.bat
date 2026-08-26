@echo off
setlocal
call "%~dp0..\_env.bat"
echo.
echo  ============================================
echo   VERDANCE'S ASHES  -  WAR MAP HUB
echo  ============================================
echo.
echo  Opening CYOA command hub (aces + theaters)...
echo  Offline file:// = deploy stub. For real BAR glue use HUB_HOST.bat
echo.

REM Prefer local showoff pack (offline, no server needed)
set "SHOW=%VERDANCE_ROOT%\app\showoff\index.html"
if exist "%SHOW%" (
  start "" "%SHOW%"
) else (
  echo  Show pack missing - rebuilding from latest campaign...
  "%VERDANCE_PY%" -c "from pathlib import Path; import json; from quantum_bar_ai.story_teller import build_story; from quantum_bar_ai.showoff_hearth import write_showoff; ws=Path(r'%VERDANCE_ROOT%'); d=json.loads((ws/'outbox'/'quantum_bar_ai_campaign.latest.json').read_text(encoding='utf-8')); write_showoff(build_story(d) if 'results' in d else d, workspace=ws)"
  start "" "%SHOW%"
)

echo.
echo.
echo  Pitch card:  %VERDANCE_ROOT%\app\showoff\SHOW_TO_FRIENDS.md
echo  Rebuild hub: python tools\build_hub_state_v1.py
echo  Schema:       docs\hub_state_v1.md
echo  BAR glue:     app\bin\HUB_HOST.bat  -^> http://127.0.0.1:8770/
echo  Scope freeze: docs\G0_SCOPE_FREEZE.md
echo  Optional old autoplay: story server still available via SERVE_STORY.bat
echo.
exit /b 0
