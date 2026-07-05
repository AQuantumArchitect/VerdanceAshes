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
& (Join-Path $ScriptDir "advance_campaign_v1.ps1") -Workspace $Workspace -WriteState:$WriteState

