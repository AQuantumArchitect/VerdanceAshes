param([string]$Workspace = "")

# Legacy shim. The balance telemetry code that this script used to patch into
# BAR.sdd's loose gadget now lives permanently in the VerdanceAshes.sdd mutator
# (mod\VerdanceAshes.sdd\luarules\gadgets\game_verdance_campaign.lua).
# All this script does now is make sure the mutator is installed.

$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
& (Join-Path $ScriptDir "install_mod_archive.ps1") -Workspace $Workspace
Write-Host "Balance telemetry is built into VerdanceAshes.sdd; mod archive verified."
