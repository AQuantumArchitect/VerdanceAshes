# Restore campaign state from pre_afternoon_playtest snapshot.
param(
    [string]$Workspace = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
)
$src = Join-Path $Workspace "state\backups\pre_afternoon_playtest"
$dstState = Join-Path $Workspace "state\campaign_state.json"
$dstIntent = Join-Path $Workspace "outbox\next_mission_intent.json"
if (-not (Test-Path (Join-Path $src "campaign_state.json"))) {
    Write-Error "No snapshot at $src\campaign_state.json"
    exit 1
}
# Safety backup of current
$stamp = Get-Date -Format "yyyyMMdd_HHmmss"
$curBak = Join-Path $Workspace "state\backups\pre_restore_$stamp"
New-Item -ItemType Directory -Force -Path $curBak | Out-Null
if (Test-Path $dstState) {
    Copy-Item $dstState (Join-Path $curBak "campaign_state.json") -Force
}
Copy-Item (Join-Path $src "campaign_state.json") $dstState -Force
if (Test-Path (Join-Path $src "next_mission_intent.json")) {
    New-Item -ItemType Directory -Force -Path (Split-Path $dstIntent) | Out-Null
    Copy-Item (Join-Path $src "next_mission_intent.json") $dstIntent -Force
}
Write-Host "Restored afternoon snapshot from $src"
Write-Host "Previous state backed up to $curBak"
exit 0
