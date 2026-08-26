# Player-path alias for extract_latest_result.
param([string]$Workspace = "")
$ErrorActionPreference = "Stop"
$ScriptsDir = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
& (Join-Path $ScriptsDir "extract_latest_result.ps1") -Workspace $Workspace
