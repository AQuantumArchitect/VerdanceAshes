@echo off
powershell -ExecutionPolicy Bypass -File "%~dp0scripts\run_campaign_ai_baseline_suite.ps1" -Workspace "%~dp0" -GenerateMatrix -VariantMode baseline -MilestoneMinutes "1,2,3,5,8,13,21" -ExtensionMilestoneMinutes "34,55,89" -TimeoutSecondsPerRun 43200
