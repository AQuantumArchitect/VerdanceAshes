param(
  [string]$Workspace = "",
  [int]$Missions = 3,
  [switch]$KeepState
)

# Chains N missions through the real play-session loop (headless fast-win) to
# prove the campaign arc: state advances, maps rotate along the Alpha Spine,
# story output varies, and the ledger grows exactly once per mission.
# Campaign state is snapshotted and restored unless -KeepState is passed.

$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
. (Join-Path $ScriptDir "_common.ps1")
$Workspace = Get-VerdanceWorkspaceRoot -Workspace $Workspace
$config = Get-VerdanceConfig -Workspace $Workspace

$snapDir = Join-Path $Workspace "state\backups\arc_verify_snapshot"
$protected = @(
  @{ live = (Join-Path $Workspace "state\campaign_state.json"); snap = (Join-Path $snapDir "campaign_state.json") },
  @{ live = (Join-Path $Workspace "outbox\next_mission_intent.json"); snap = (Join-Path $snapDir "next_mission_intent.json") },
  @{ live = (Join-Path $Workspace "outbox\next_mission_build_manifest.json"); snap = (Join-Path $snapDir "next_mission_build_manifest.json") },
  @{ live = (Join-Path $Workspace "inbox\latest_va_result.json"); snap = (Join-Path $snapDir "latest_va_result.json") }
)
New-Item -ItemType Directory -Force -Path $snapDir | Out-Null
foreach ($p in $protected) {
  if (Test-Path $p.live) { Copy-Item -Force $p.live $p.snap }
}

function Restore-Snapshot {
  foreach ($p in $protected) {
    if (Test-Path $p.snap) { Copy-Item -Force $p.snap $p.live }
  }
  # Reinstall the seed matching the restored intent.
  & (Join-Path $ScriptDir "build_next_mission_v1.ps1") -Workspace $Workspace | Out-Null
}

$report = [ordered]@{
  schemaVersion = "verdance-arc-verify/1.0"
  startedAt = (Get-Date).ToUniversalTime().ToString("o")
  missions = @()
  passed = $false
}

try {
  for ($i = 1; $i -le $Missions; $i++) {
    $stateBefore = Get-Content (Join-Path $Workspace "state\campaign_state.json") -Raw | ConvertFrom-Json
    $intent = Get-Content (Join-Path $Workspace "outbox\next_mission_intent.json") -Raw | ConvertFrom-Json
    Write-Host ""
    Write-Host ">>> Arc mission $i/$($Missions): $($intent.missionId) on $($intent.mapId) ($($intent.objective))"

    & (Join-Path $ScriptDir "play_session_v1.ps1") -Workspace $Workspace -EngineMode headless-fastwin | Out-Null

    $status = Get-Content (Join-Path $Workspace "outbox\play_session.status.json") -Raw | ConvertFrom-Json
    if ($status.phase -ne "next-ready") { throw "Mission $($intent.missionId): session ended in phase '$($status.phase)' (expected next-ready)." }

    $stateAfter = Get-Content (Join-Path $Workspace "state\campaign_state.json") -Raw | ConvertFrom-Json
    if ([int]$stateAfter.missionNumber -ne ([int]$stateBefore.missionNumber + 1)) {
      throw "Mission $($intent.missionId): missionNumber $($stateBefore.missionNumber) -> $($stateAfter.missionNumber), expected +1."
    }
    $ledgerBefore = @($stateBefore.processedResults.PSObject.Properties).Count
    $ledgerAfter = @($stateAfter.processedResults.PSObject.Properties).Count
    if ($ledgerAfter -le $ledgerBefore) { throw "Mission $($intent.missionId): processedResults did not grow." }

    $events = Get-Content (Join-Path $Workspace "outbox\story_events.latest.json") -Raw | ConvertFrom-Json
    $dialogue = @($events.events | Where-Object { $_.kind -eq "dialogue" } | ForEach-Object { $_.text })
    $nextIntent = Get-Content (Join-Path $Workspace "outbox\next_mission_intent.json") -Raw | ConvertFrom-Json

    $report.missions += [ordered]@{
      missionId = $intent.missionId
      mapId = $intent.mapId
      objective = $intent.objective
      title = $intent.title
      briefingFirstLine = if ($intent.briefing -and $intent.briefing.lines -and $intent.briefing.lines.Count -gt 0) { $intent.briefing.lines[0].text } else { $null }
      debriefLine = if ($dialogue.Count -gt 0) { $dialogue[0] } else { $null }
      missionNumberAfter = $stateAfter.missionNumber
      nextMissionId = $nextIntent.missionId
      nextMapId = $nextIntent.mapId
    }
    Write-Host "    advanced to mission $($stateAfter.missionNumber); next: $($nextIntent.missionId) on $($nextIntent.mapId)"
    Write-Host "    Ketha: `"$($dialogue[0])`""
  }

  # Map rotation check: consecutive missions must not repeat a map.
  $maps = @($report.missions | ForEach-Object { $_.mapId })
  for ($i = 1; $i -lt $maps.Count; $i++) {
    if ($maps[$i] -eq $maps[$i - 1]) { throw "Alpha Spine did not rotate: $($maps[$i]) repeated." }
  }

  $report.passed = $true
} finally {
  $report.finishedAt = (Get-Date).ToUniversalTime().ToString("o")
  $reportPath = Join-Path $Workspace "reports\arc_verify.latest.json"
  New-Item -ItemType Directory -Force -Path (Split-Path -Parent $reportPath) | Out-Null
  $report | ConvertTo-Json -Depth 10 | Set-Content -Encoding UTF8 $reportPath
  Write-Host ""
  Write-Host "Arc report: $reportPath"
  if (-not $KeepState) {
    Write-Host "Restoring campaign state snapshot..."
    Restore-Snapshot
  }
}

if (-not $report.passed) { throw "Campaign arc verification failed." }
Write-Host "Campaign arc verification passed: $Missions missions chained."
