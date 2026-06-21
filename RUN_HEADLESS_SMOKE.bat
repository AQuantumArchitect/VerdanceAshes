@echo off
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\run_headless_smoke.ps1" %*
