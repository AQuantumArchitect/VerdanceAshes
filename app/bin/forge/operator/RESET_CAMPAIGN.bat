@echo off
echo This resets your Verdance's Ashes campaign to mission 1.
set /p CONFIRM="Type YES to continue: "
if /i not "%CONFIRM%"=="YES" (
  echo Cancelled.
  pause
  exit /b 1
)
del /q "%~dp0state\campaign_state.json" 2>nul
del /q "%~dp0inbox\latest_va_result.json" 2>nul
del /q "%~dp0outbox\next_mission_intent.json" 2>nul
del /q "%~dp0outbox\next_mission_build_manifest.json" 2>nul
del /q "%~dp0outbox\advance_report.v1.json" 2>nul
del /q "%~dp0outbox\play_session.status.json" 2>nul
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\migrate_state_v1.ps1"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\advance_campaign_v1.ps1" -IntentOnly
echo Campaign reset. Run PLAY_SESSION_V1.bat to start mission 1.
pause
