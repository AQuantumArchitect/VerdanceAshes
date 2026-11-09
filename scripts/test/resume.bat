@echo off
rem Resume a stopped run: resume.bat autopilot_runs\<stamp>.
rem Double-click it; the log is export\resume.log.
set "VA_LOG=resume"
call "%~dp0autopilot.bat" --resume %1 --sorties 20 --speed 10 --beats --hud --profile hard_aggressive --wall-timeout 5400
