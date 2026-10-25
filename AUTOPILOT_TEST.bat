@echo off
REM One-click autopilot test: 2 sorties, BARb hard_aggressive in the company seat, headless.
call "%~dp0AUTOPILOT.bat" --sorties 2 %*
