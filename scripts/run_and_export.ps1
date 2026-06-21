param([string]$Workspace = "$env:USERPROFILE\Documents\BAR_Verdance_Workspace")
$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
& (Join-Path $ScriptDir "extract_latest_result.ps1") -Workspace $Workspace
& (Join-Path $ScriptDir "advance_campaign.ps1") -Workspace $Workspace
& (Join-Path $ScriptDir "export_for_chatgpt.ps1") -Workspace $Workspace
