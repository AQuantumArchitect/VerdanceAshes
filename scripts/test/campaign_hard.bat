@echo off
rem The whole campaign against the hard AI (BARb hard_aggressive), up to 20 sorties.
rem Double-click it; the log is export\campaign_hard.log.
set "VA_LOG=campaign_hard"
call "%~dp0autopilot.bat" --sorties 20 --speed 10 --beats --hud --profile hard_aggressive --wall-timeout 5400
