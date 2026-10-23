param(
  [string]$Workspace = "",
  [string]$StatePath = "",
  [string]$ResultPath = "",
  [string]$TelemetryPath = "",
  [switch]$WriteState,
  [switch]$IntentOnly
)

$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$WorkspaceRoot = Split-Path -Parent $ScriptDir
if (-not $Workspace) { $Workspace = $WorkspaceRoot }
$env:PYTHONPATH = Join-Path $WorkspaceRoot "tools"  # python -m verdance.* below

. (Join-Path $ScriptDir "_common.ps1")
$python = Get-VerdancePython -Workspace $Workspace
$command = if ($IntentOnly) { "intent" } else { "advance" }
$args = @("-m", "verdance.campaign.engine", $command, "--workspace", $Workspace)
if ($StatePath) { $args += @("--state", $StatePath) }
if (-not $IntentOnly) {
  if ($ResultPath) { $args += @("--result", $ResultPath) }
  if ($TelemetryPath) { $args += @("--telemetry", $TelemetryPath) }
  if ($WriteState) { $args += "--write-state" }
}

& $python @args
if ($LASTEXITCODE -ne 0) { throw "Verdance Story Engine v1 failed with exit code $LASTEXITCODE" }

# G4/G5: refresh war-map hub after campaign advance (aces, ρ, Mode A home, shop bag).
if ($WriteState -and -not $IntentOnly) {
  try {
    & $python -m verdance.hub.apply_result_to_hub --workspace $Workspace --skip-advance 2>$null | Out-Null
    Write-Host "Hub state refreshed from campaign advance."
  } catch {
    Write-Warning "Hub refresh after advance skipped: $($_.Exception.Message)"
  }
}

