@echo off
setlocal
title Verdance Ashes - PROXY campaign (quantum vs Simple/BARb)
call "%~dp0..\_env.bat"
if errorlevel 1 (
  pause
  exit /b 1
)

echo.
echo  Proxy campaign: quantum-BAR-AI player vs Simple + Barbarian enemies
echo  Story engine + offscreen clash + Tnb BP. No BAR launch. No human.
echo  Workspace: %VERDANCE_ROOT%
echo.

powershell -NoProfile -ExecutionPolicy Bypass -File "%VERDANCE_ROOT%\scripts\player\proxy_campaign.ps1" -Workspace "%VERDANCE_ROOT%" -Sorties 6 -Seeds 2 -Enemy both
set ERR=%ERRORLEVEL%
echo.
if %ERR% neq 0 (
  echo PROXY campaign failed with code %ERR%.
) else (
  echo Proxy campaign PASS. See outbox\proxy_campaign.latest.json
  echo Docs: docs\PROXY_CAMPAIGN.md
)
pause
exit /b %ERR%
