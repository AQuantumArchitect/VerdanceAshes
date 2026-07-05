param(
  [string]$Workspace = "",
  [string]$BarDataRoot = "",
  [switch]$NonInteractive,
  [switch]$Junction
)

$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
. (Join-Path $ScriptDir "_common.ps1")
$Workspace = Get-VerdanceWorkspaceRoot -Workspace $Workspace

Write-Host "=== Verdance's Ashes tester setup ==="
Write-Host "Workspace: $Workspace"

# ---- locate BAR ---------------------------------------------------------
if (-not $BarDataRoot) { $BarDataRoot = Find-BARDataRoot }
if (-not $BarDataRoot -and -not $NonInteractive) {
  Write-Host ""
  Write-Host "Could not auto-detect your Beyond All Reason install."
  $BarDataRoot = Read-Host "Enter the full path to your BAR 'data' directory (contains engine\ and games\)"
}
if (-not $BarDataRoot -or !(Test-Path $BarDataRoot)) {
  throw "No Beyond All Reason data directory found. Install BAR first (https://www.beyondallreason.info), or pass -BarDataRoot."
}
if (!(Test-Path (Join-Path $BarDataRoot "games"))) { throw "'$BarDataRoot' does not look like a BAR data directory (no games\ folder)." }
$engineDirs = Get-ChildItem (Join-Path $BarDataRoot "engine") -Directory -ErrorAction SilentlyContinue |
  Where-Object { Test-Path (Join-Path $_.FullName "spring.exe") }
if (-not $engineDirs) { throw "No engine with spring.exe found under $BarDataRoot\engine. Launch BAR once so it downloads an engine, then re-run setup." }
Write-Host "BAR data root: $BarDataRoot"
Write-Host "Engine: $($engineDirs[-1].Name)"

# ---- write config -------------------------------------------------------
$configPath = Join-Path $Workspace "verdance_config.json"
$config = [ordered]@{
  schemaVersion = "0.8"
  barDataRoot = $BarDataRoot
  workspace = $Workspace
  gameType = 'Verdance Ashes $VERSION'
}
$config | ConvertTo-Json | Set-Content -Encoding UTF8 -Path $configPath
Write-Host "Wrote $configPath"

# ---- install the mod ----------------------------------------------------
$modArgs = @()
if (-not $Junction) { $modArgs += "-Copy" }
& (Join-Path $ScriptDir "install_mod_archive.ps1") -Workspace $Workspace @modArgs

# ---- fresh campaign state -----------------------------------------------
$statePath = Join-Path $Workspace "state\campaign_state.json"
if (Test-Path $statePath) {
  Write-Host "Existing campaign state found; leaving it untouched. (Use RESET_CAMPAIGN.bat for a fresh start.)"
} else {
  & (Join-Path $ScriptDir "migrate_state_v1.ps1") -Workspace $Workspace
  Write-Host "Initialized a fresh campaign state."
}

# ---- materialize first mission ------------------------------------------
$intentPath = Join-Path $Workspace "outbox\next_mission_intent.json"
if (!(Test-Path $intentPath)) {
  & (Join-Path $ScriptDir "advance_campaign_v1.ps1") -Workspace $Workspace -IntentOnly | Out-Null
}

Write-Host ""
Write-Host "=== Setup complete ==="
Write-Host "Run PLAY_SESSION_V1.bat to build and play the next campaign mission."
Write-Host "Or run LAUNCH_VERDANCE_CONSOLE.bat for the full control panel."
