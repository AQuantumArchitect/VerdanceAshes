# Backup campaign_state then re-migrate clean + rebuild hub.
param([string]$Workspace = "")

$ErrorActionPreference = "Stop"
$PlayerDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ScriptsDir = Split-Path -Parent $PlayerDir
. (Join-Path $ScriptsDir "_common.ps1")

$Workspace = Get-VerdanceWorkspaceRoot -Workspace $Workspace
$statePath = Join-Path $Workspace "state\campaign_state.json"
$backupDir = Join-Path $Workspace "state\backups"
New-Item -ItemType Directory -Force -Path $backupDir | Out-Null

if (Test-Path $statePath) {
  $stamp = Get-Date -Format "yyyyMMdd_HHmmss"
  $dest = Join-Path $backupDir "campaign_state.reset_$stamp.json"
  Copy-Item -Force $statePath $dest
  Write-Host "Backed up to $dest"
  Remove-Item -Force $statePath
}

$migrate = Join-Path $ScriptsDir "migrate_state_v1.ps1"
if (Test-Path $migrate) {
  & $migrate -Workspace $Workspace
} else {
  New-Item -ItemType Directory -Force -Path (Split-Path $statePath) | Out-Null
  Write-Host "migrate_state_v1.ps1 missing - left state empty for next PLAY rebuild."
}

$py = Get-VerdancePython -Workspace $Workspace
$env:PYTHONPATH = (Join-Path $Workspace "tools")
Write-Host "Python:    $py"
Write-Host "Rebuilding hub surface..."

$prev = Get-Location
Set-Location $Workspace
try {
  $code = @"
from verdance_kernel.api import CampaignKernel
k = CampaignKernel(r'''$Workspace''')
r = k.rebuild_hub()
print('ok' if r.get('ok') else r)
"@
  $result = & $py -c $code
  Write-Host "Hub: $result"
  if ($LASTEXITCODE -ne 0) { throw "hub rebuild failed (exit $LASTEXITCODE)" }
} finally {
  Set-Location $prev
}

Write-Host "Reset done."
