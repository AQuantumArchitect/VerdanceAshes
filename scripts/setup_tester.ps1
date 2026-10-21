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
# verdance_config.json barDataRoot is authoritative; then BAR_DATA_ROOT; then the
# standard installer / Program Files / Steam folders (Find-BARDataRoot in _common.ps1).
function Normalize-BARDataRootInput([string]$Text) {
  if (-not $Text) { return "" }
  $p = $Text.Trim().Trim('"').Trim("'").TrimEnd('\')
  if (-not $p) { return "" }
  # Accept the install folder too (the one that holds data\), and a path into engine\ or games\.
  $dataSub = Join-Path $p "data"
  if ((Test-Path (Join-Path $dataSub "games")) -and !(Test-Path (Join-Path $p "games"))) { $p = $dataSub }
  foreach ($tail in @("\engine", "\games")) {
    if ($p.ToLower().EndsWith($tail)) { $p = $p.Substring(0, $p.Length - $tail.Length) }
  }
  return $p
}

if ($BarDataRoot) { $BarDataRoot = Normalize-BARDataRootInput $BarDataRoot }
if (-not $BarDataRoot) { $BarDataRoot = Find-BARDataRoot -Workspace $Workspace }

if (-not $NonInteractive) {
  $tries = 0
  while ($tries -lt 3) {
    $problem = $null
    try { Assert-BARDataRoot -BarDataRoot $BarDataRoot } catch { $problem = $_.Exception.Message }
    if (-not $problem) { break }
    $tries += 1
    Write-Host ""
    if ($BarDataRoot) { Write-Host $problem } else { Write-Host "Could not auto-detect your Beyond All Reason install." }
    Write-Host "It is usually  $env:LOCALAPPDATA\Programs\Beyond-All-Reason\data"
    Write-Host "(or ...\Steam\steamapps\common\Beyond All Reason\data for the Steam build)."
    $answer = Read-Host "Enter the full path to your BAR 'data' folder (contains engine\ and games\), or press Enter to stop"
    if (-not $answer -or -not $answer.Trim()) { break }
    $BarDataRoot = Normalize-BARDataRootInput $answer
  }
}
Assert-BARDataRoot -BarDataRoot $BarDataRoot
$engineDirs = Get-BAREngineDirs -BarDataRoot $BarDataRoot
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
if ($Junction) {
  & (Join-Path $ScriptDir "install_mod_archive.ps1") -Workspace $Workspace
} else {
  & (Join-Path $ScriptDir "install_mod_archive.ps1") -Workspace $Workspace -Copy
}

# ---- fresh campaign state -----------------------------------------------
$statePath = Join-Path $Workspace "state\campaign_state.json"
if (Test-Path $statePath) {
  Write-Host "Existing campaign state found; leaving it untouched. (Run RESET.bat for a fresh start.)"
} else {
  # A fresh clone / unzip has no state\campaign_state.json: init-state writes mission 1.
  New-Item -ItemType Directory -Force -Path (Split-Path -Parent $statePath) | Out-Null
  & (Join-Path $ScriptDir "migrate_state_v1.ps1") -Workspace $Workspace
  if (!(Test-Path $statePath)) { throw "Fresh campaign state was not written to $statePath" }
  Write-Host "Initialized a fresh campaign state (mission 1)."
}

# ---- materialize first mission ------------------------------------------
$intentPath = Join-Path $Workspace "outbox\next_mission_intent.json"
if (!(Test-Path $intentPath)) {
  & (Join-Path $ScriptDir "advance_campaign_v1.ps1") -Workspace $Workspace -IntentOnly | Out-Null
}

Write-Host ""
Write-Host "=== Setup complete ==="
Write-Host "Run PLAY.bat (leave the window open while you play). RESET.bat starts the campaign over."
