@echo off
setlocal
powershell -ExecutionPolicy Bypass -File "%~dp0scripts\install_playable_slice.ps1" -ListVariants
pause
