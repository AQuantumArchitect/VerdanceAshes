@echo off
rem Screen tour: no BAR, fake results; saves each sortie's state, intent, scenario and manifest (the builder parity corpus).
rem Double-click it; the log is export\tour.log.
set "VA_LOG=tour"
call "%~dp0autopilot.bat" --tour --sorties 20 --band "pavise,solarium,halbard" --boost ""
