param(
  [string]$Workspace = "",
  [string]$StatePath = ""
)

$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$WorkspaceRoot = Split-Path -Parent $ScriptDir
if (-not $Workspace) { $Workspace = $WorkspaceRoot }
$env:PYTHONPATH = Join-Path $WorkspaceRoot "tools"  # python -m verdance.* below

if (-not $StatePath) { $StatePath = Join-Path $Workspace "state\campaign_state.json" }

$before = "missing"
if (Test-Path $StatePath) {
  try { $before = (Get-Content $StatePath -Raw | ConvertFrom-Json).schemaVersion } catch { $before = "unreadable" }
}

. (Join-Path $ScriptDir "_common.ps1")
$python = Get-VerdancePython -Workspace $Workspace
& $python -m verdance.campaign.engine init-state --workspace $Workspace --state $StatePath --write-state
if ($LASTEXITCODE -ne 0) { throw "Verdance Story Engine v1 init-state failed with exit code $LASTEXITCODE" }

$after = (Get-Content $StatePath -Raw | ConvertFrom-Json).schemaVersion
Write-Host "Campaign state schema: $before -> $after"
