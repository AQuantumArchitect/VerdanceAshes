param(
  [string]$Workspace = "",
  [switch]$WriteState
)

$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
if (-not $Workspace) { $Workspace = Split-Path -Parent $ScriptDir }

& (Join-Path $ScriptDir "extract_latest_result.ps1") -Workspace $Workspace
try {
  & (Join-Path $ScriptDir "extract_latest_telemetry.ps1") -Workspace $Workspace
} catch {
  Write-Warning "Telemetry extraction failed; v1 advancement will use result-only/default elapsed behavior. $($_.Exception.Message)"
}
try {
  & (Join-Path $ScriptDir "extract_latest_translation.ps1") -Workspace $Workspace
} catch {
  Write-Warning "Translation-packet extraction failed; graph will fall back to proxy measurement (Level 1). $($_.Exception.Message)"
}
& (Join-Path $ScriptDir "advance_campaign_v1.ps1") -Workspace $Workspace -WriteState:$WriteState

# Explicit hub pull so play_session / operator paths always leave hub_result.latest.json
# in sync even if advance script hub-refresh is skipped.
if ($WriteState) {
  try {
    . (Join-Path $ScriptDir "_common.ps1")
    $py = Get-VerdancePython -Workspace $Workspace
    $env:PYTHONPATH = Join-Path $Workspace "tools"
    & $py -m verdance.hub.apply_result_to_hub --workspace $Workspace --skip-advance 2>$null | Out-Null
  } catch {
    Write-Warning "Hub apply after full cycle skipped: $($_.Exception.Message)"
  }
}

