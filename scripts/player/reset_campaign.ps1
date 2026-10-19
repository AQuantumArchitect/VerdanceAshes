# Backup campaign_state, wipe progress, scrub stale sortie artifacts, rebuild hub.
param([string]$Workspace = "")

$ErrorActionPreference = "Stop"
$PlayerDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ScriptsDir = Split-Path -Parent $PlayerDir
. (Join-Path $ScriptsDir "_common.ps1")

$Workspace = Get-VerdanceWorkspaceRoot -Workspace $Workspace
$statePath = Join-Path $Workspace "state\campaign_state.json"
$backupDir = Join-Path $Workspace "state\backups"
$stamp = Get-Date -Format "yyyyMMdd_HHmmss"
New-Item -ItemType Directory -Force -Path $backupDir | Out-Null

Write-Host ""
Write-Host "=== Verdance Ashes - full campaign reset ==="
Write-Host "Workspace: $Workspace"
Write-Host ""

# A live PLAY kernel keeps serving hub_state.json from memory while we wipe.
# Kill EVERY listener on :8770 (not just command lines that match verdance_kernel)
# so a python -m / py launcher cannot keep Sortie 2 on the hub.
try {
  $conns = @(Get-NetTCPConnection -LocalPort 8770 -State Listen -ErrorAction SilentlyContinue)
  foreach ($c in $conns) {
    Write-Host "Stopping PID $($c.OwningProcess) on :8770 (so reset is not masked)"
    Stop-Process -Id $c.OwningProcess -Force -ErrorAction SilentlyContinue
  }
} catch {
  Write-Host "Note: could not probe :8770 ($($_.Exception.Message))"
}

if (Test-Path $statePath) {
  $dest = Join-Path $backupDir "campaign_state.reset_$stamp.json"
  Copy-Item -Force $statePath $dest
  Write-Host "Backed up campaign_state -> $dest"
  Remove-Item -Force $statePath
} else {
  Write-Host "No campaign_state.json (already clean)."
}

# Ship used to nest prior state under state\va_ship_state_keep forever; those
# ghosts can revive mid-arc progress after a wipe. Scrub them on every reset.
$shipKeep = Join-Path $Workspace "state\va_ship_state_keep"
if (Test-Path $shipKeep) {
  Remove-Item -Recurse -Force $shipKeep
  Write-Host "Scrubbed nested va_ship_state_keep (ship ghost saves)"
}

# Steam cloud is a local mirror, not a restore source — but wipe it anyway so
# a later tool cannot copy Sortie 2 back over the fresh opener.
$cloudState = Join-Path $Workspace "state\steam\cloud\campaign_state.json"
if (Test-Path $cloudState) {
  $cloudBak = Join-Path $backupDir "steam_cloud.reset_$stamp.json"
  Copy-Item -Force $cloudState $cloudBak
  Remove-Item -Force $cloudState
  Write-Host "Wiped steam cloud mirror"
}

# Archive stale match/hub noise so the next Drop cannot bring-home a ghost result.
# Continuity: also scrub poisoned mission intents (wrong map / fortify_zone kind /
# blown-fusion secondaries) that would otherwise be what build_next_mission reads.
$archiveRoot = Join-Path $Workspace "inbox\archive"
New-Item -ItemType Directory -Force -Path $archiveRoot | Out-Null
$toArchive = @(
  (Join-Path $Workspace "inbox\latest_va_result.json"),
  (Join-Path $Workspace "inbox\latest_va_translation.json"),
  (Join-Path $Workspace "outbox\hub_result.latest.json"),
  (Join-Path $Workspace "outbox\campaign_surface.latest.json"),
  (Join-Path $Workspace "outbox\bridge.latest.json"),
  (Join-Path $Workspace "outbox\human_playthrough.latest.json"),
  (Join-Path $Workspace "outbox\hub_deploy_stamp.latest.json"),
  (Join-Path $Workspace "outbox\hub_deploy_plan.latest.json"),
  (Join-Path $Workspace "outbox\next_mission_intent.json"),
  (Join-Path $Workspace "outbox\next_sortie_order.json"),
  (Join-Path $Workspace "outbox\next_sortie_choice.json"),
  (Join-Path $Workspace "outbox\session_home.latest.json"),
  (Join-Path $Workspace "outbox\play_session.status.json"),
  (Join-Path $Workspace "outbox\continuity_audit.latest.json"),
  (Join-Path $Workspace "outbox\va_current.lua"),
  (Join-Path $Workspace "app\showoff\hub_state.json"),
  (Join-Path $Workspace "app\showoff\hub_state.embed.js"),
  (Join-Path $Workspace "data\scenarios\generated\next_mission_intent.playable.json")
)
foreach ($p in $toArchive) {
  if (Test-Path $p) {
    $name = [IO.Path]::GetFileName($p)
    $dest = Join-Path $archiveRoot ("${stamp}_$name")
    try {
      Move-Item -Force $p $dest
      Write-Host "Archived $name"
    } catch {
      Copy-Item -Force $p $dest
      Remove-Item -Force $p -ErrorAction SilentlyContinue
      Write-Host "Archived $name (copy+delete; move was locked)"
    }
  }
}

# Belt: if a live kernel re-wrote the result while we archived, kill it again.
$ghostResult = Join-Path $Workspace "inbox\latest_va_result.json"
if (Test-Path $ghostResult) {
  Remove-Item -Force $ghostResult
  Write-Host "Force-deleted leftover latest_va_result.json"
}

# Stale Act-N mission lua must not be what BAR loads after a wipe.
$generatedDirs = @(
  (Join-Path $Workspace "mod\VerdanceAshes.sdd\singleplayer\verdance_ashes\generated"),
  (Join-Path $env:LOCALAPPDATA "Programs\Beyond-All-Reason\data\games\VerdanceAshes.sdd\singleplayer\verdance_ashes\generated")
)
foreach ($generated in $generatedDirs) {
  if (-not (Test-Path $generated)) { continue }
  foreach ($name in @("va_current.lua", "proxy_story_current.lua", "zone_map_current.lua")) {
    $p = Join-Path $generated $name
    if (Test-Path $p) {
      $dest = Join-Path $backupDir ("${name}.reset_$stamp.bak")
      Copy-Item -Force $p $dest
      Remove-Item -Force $p
      Write-Host "Cleared $generated\$name (backed up)"
    }
  }
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
$hubPy = Join-Path $PlayerDir "reset_campaign_hub.py"
if (-not (Test-Path $hubPy)) {
  throw "Missing reset_campaign_hub.py next to this script."
}

Write-Host "Python:    $py"
Write-Host "Rebuilding hub surface..."

$prev = Get-Location
Set-Location $Workspace
try {
  & $py $hubPy --workspace $Workspace
  if ($LASTEXITCODE -ne 0) { throw "hub rebuild failed (exit $LASTEXITCODE)" }
} finally {
  Set-Location $prev
}

Write-Host ""
Write-Host "Reset done."
Write-Host '  - Fresh mission 1 opener (GF eco_raid — fusion vaults are OPTIONAL bonuses)'
Write-Host '  - Stale intents / playable / BAR va_current scrubbed (no ghost sorties)'
Write-Host '  - Bag starts empty — buy Punch / streams at the Broker (nothing free)'
Write-Host '  - Metal bank starts at catalog fresh wallet (earn more by extracting end metal)'
Write-Host '  - Blow a fusion vault and it stays dead next sortie (continuity scar)'
Write-Host '  - Mark GF_NE_PLATEAU before Drop if you want the Fatboy wreck'
Write-Host 'Next: hard-refresh the hub (Ctrl+F5), then PLAY.bat / Drop.'
Write-Host ""