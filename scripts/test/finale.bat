@echo off
rem One finale on its own: finale.bat A, B or C.
rem Double-click it; the log is export\finale_A.log (B, C).
set "VA_LOG=finale_%1"
call "%~dp0autopilot.bat" --finale %1 --sorties 3 --speed 10 --beats --hud --profile hard_aggressive --band "pavise,solarium,halbard" --boost "" --wall-timeout 5400
