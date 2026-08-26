@echo off
powershell -ExecutionPolicy Bypass -File "%~dp0scripts\package_campaign_ai_baseline_export.ps1" -Workspace "%~dp0"
