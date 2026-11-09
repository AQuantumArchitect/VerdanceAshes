@echo off
rem Two sorties on stock BAR: the quick "does it still come home" check before a release.
rem Double-click it; the log is export\rehearsal.log.
set "VA_LOG=rehearsal"
call "%~dp0autopilot.bat" --sorties 2 --speed 10 --hud --profile hard_aggressive --wall-timeout 1800
