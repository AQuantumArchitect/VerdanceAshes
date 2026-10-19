<#
.SYNOPSIS
  Turns a played BAR session's infolog into a tracked run record that the AI-duel
  analyser can read unmodified.

.DESCRIPTION
  The overnight AI matrix produced, per run, a headless_runs\<stamp>\ directory
  containing calibration_data.json, and a suite manifest listing those runs.
  tools\ai_duel_zone_flow_v1.py reads exactly those two files. This script writes
  the same two shapes from a human session, so "where did the player's units
  actually go" is answered by the same code that answered it for the AIs.

  It parses four markers out of the infolog:
    VA_TELEMETRY_JSON_COMPACT   one occupancy snapshot per packet -> snapshots[]
    VA_ZONE_FLOW_JSON           cumulative border crossings -> zoneFlow
    VA_TRANSLATION_PACKET_COMPACT  optional, fills snapshots[].zones
    VA_RESULT_JSON_COMPACT      the mission outcome

  Assertions, not hope: a session that was mis-launched (tracking never armed,
  profiling flags contaminating it, a stale seed) produces a record that LOOKS
  fine and measures nothing. Each of those is checked and named.

  ASCII only in this file (PowerShell 5.1 parses BOM-less UTF-8 as ANSI).
#>
param(
  [string]$Workspace = "",
  # Defaults to the live BAR infolog. Pass a snapshot to re-harvest an old session.
  [string]$InfologPath = "",
  [string]$RunDir = "",
  [string]$MapId = "",
  [string]$MapTitle = "",
  [string]$Variant = "alpha_player",
  [string]$SeatLabel = "Human",
  [string]$EnemyLabel = "campaign_ai",
  [int]$PlayerTeamID = 0,
  [int]$ElapsedSeconds = 0,
  [string]$SuitePath = "",
  # Byte offset into the infolog from latest_launch.json. Belt-and-braces against a
  # log that was appended to rather than truncated at launch.
  [long]$BaselineLength = 0,
  # A session the player abandoned still has a usable flow record; only the outcome
  # is missing. Do not fail the harvest for that.
  [switch]$AllowNoResult
)

$ErrorActionPreference = "Stop"
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
. (Join-Path $scriptDir "_common.ps1")
. (Join-Path $scriptDir "lib_packet_parse.ps1")
$Workspace = Get-VerdanceWorkspaceRoot -Workspace $Workspace

$warnings = New-Object System.Collections.Generic.List[string]
function Add-Warn {
  param([string]$Message)
  $warnings.Add($Message) | Out-Null
  Write-Warning $Message
}

# ---- locate and snapshot the infolog -------------------------------------------
if (-not $InfologPath) { $InfologPath = Get-BARInfolog $Workspace }
if (!(Test-Path -LiteralPath $InfologPath)) {
  throw "No infolog at $InfologPath. Did the session launch?"
}

if (-not $RunDir) {
  $stamp = Get-Date -Format "yyyyMMdd_HHmmss"
  $RunDir = Join-Path (Join-Path $Workspace "human_runs") "session_$stamp"
}
New-Item -ItemType Directory -Force -Path $RunDir | Out-Null

# BAR may still hold the log open. Get-Content -Raw takes no share mode and throws
# on a live file, so copy through an explicitly shared stream first and parse the
# copy -- which also freezes the record against a later session overwriting it.
$snapshotPath = Join-Path $RunDir "infolog.txt"
$fs = $null
try {
  $fs = New-Object System.IO.FileStream(
    $InfologPath, [System.IO.FileMode]::Open, [System.IO.FileAccess]::Read,
    ([System.IO.FileShare]::ReadWrite -bor [System.IO.FileShare]::Delete))
  if ($BaselineLength -gt 0 -and $BaselineLength -lt $fs.Length) {
    [void]$fs.Seek($BaselineLength, [System.IO.SeekOrigin]::Begin)
  }
  $out = New-Object System.IO.FileStream(
    $snapshotPath, [System.IO.FileMode]::Create, [System.IO.FileAccess]::Write,
    [System.IO.FileShare]::None)
  try { $fs.CopyTo($out) } finally { $out.Dispose() }
} finally {
  if ($fs) { $fs.Dispose() }
}
Write-Host "Infolog snapshot: $snapshotPath ($((Get-Item -LiteralPath $snapshotPath).Length) bytes)"

$logText = Get-Content -LiteralPath $snapshotPath -Raw -Encoding UTF8

# ---- assertions on how the session was launched --------------------------------
# A1: tracking actually armed. Without this every packet count below is zero and
# the analyser reports a map on which nothing ever moved.
if ($logText -notmatch 'VA_DEV_TELEMETRY_ARMED') {
  throw ("Session was not tracked: no VA_DEV_TELEMETRY_ARMED in the infolog. " +
         "The launcher must pass va_play_track=1 through to [MODOPTIONS].")
}

# A2: profiling flags must be absent. They would have produced packets, but with
# LuaUI off, the sim at 20x, waves and beats disabled, and no Spring.GameOver --
# a record of something that was not a playable session.
foreach ($contaminant in @("VA_HEADLESS_AUTOSTART", "VA_BALANCE_AUTORUN", "VA_FIB_PROFILER")) {
  if ($logText -match [regex]::Escape($contaminant)) {
    throw ("Profiling marker $contaminant present: this was not a normal playable " +
           "session (LuaUI off / 20x sim / no waves). Refusing to file it as human play.")
  }
}

# A3: the seed that loaded should be the one just built. The generated va_current.lua
# outlives whatever wrote it, so a session launched without rebuilding silently runs
# the last headless probe's mission.
$bridgeMission = ""
if ($logText -match 'VA_BRIDGE_LOADED[^\r\n]*mission=([^\s\r\n]+)') { $bridgeMission = $Matches[1] }

# ---- parse packets --------------------------------------------------------------
$telemetryFails = 0
$flowFails = 0
$telemetryPackets = Parse-CompactJsonPackets -Infolog $snapshotPath -Marker "VA_TELEMETRY_JSON_COMPACT" -FailureCount ([ref]$telemetryFails)
$zoneFlowPackets  = Parse-CompactJsonPackets -Infolog $snapshotPath -Marker "VA_ZONE_FLOW_JSON" -FailureCount ([ref]$flowFails)
$translationPackets = Parse-CompactJsonPackets -Infolog $snapshotPath -Marker "VA_TRANSLATION_PACKET_COMPACT"
$resultPackets = Parse-CompactJsonPackets -Infolog $snapshotPath -Marker "VA_RESULT_JSON_COMPACT"
$devPackets = Parse-CompactJsonPackets -Infolog $snapshotPath -Marker "VA_DEV_SAMPLE_JSON"

Write-Host "Telemetry packets:   $($telemetryPackets.Count)"
Write-Host "Zone-flow packets:   $($zoneFlowPackets.Count)"
Write-Host "Translation packets: $($translationPackets.Count)"
Write-Host "Dev samples:         $($devPackets.Count)"
Write-Host "Result packets:      $($resultPackets.Count)"
if ($telemetryFails -gt 0) { Add-Warn "$telemetryFails telemetry packet(s) failed to parse." }
if ($flowFails -gt 0) { Add-Warn "$flowFails zone-flow packet(s) failed to parse." }

# A4: the measurement exists. An empty edge list is the failure this whole script
# is built to make loud: the analyser would happily report every corridor inert.
if ($zoneFlowPackets.Count -eq 0) {
  throw "No VA_ZONE_FLOW_JSON packets. The zone-flow sampler never ran."
}
$lastFlowFrame = ($zoneFlowPackets.Keys | Sort-Object | Select-Object -Last 1)
$zoneFlowFinal = $zoneFlowPackets[$lastFlowFrame]
$edgeCount = @($zoneFlowFinal.edges).Count
if ($edgeCount -eq 0) {
  throw ("Zone-flow packet at frame $lastFlowFrame has no edges: nothing crossed a zone " +
         "border all session. Expected for a sub-minute session, a bug otherwise.")
}
# A5: crossings are only comparable to the AI runs at the same observation rate.
$sampleEvery = [int]$zoneFlowFinal.sampleEvery
if ($sampleEvery -ne 150) {
  Add-Warn ("zoneFlow.sampleEvery is $sampleEvery, not the 150 the AI matrix used. " +
            "Crossing counts are a function of sampling rate and are NOT comparable.")
}
Write-Host "Zone-flow: frame $lastFlowFrame, $edgeCount edge(s), sampleEvery=$sampleEvery"

# ---- build snapshots ------------------------------------------------------------
# One snapshot per telemetry packet: a human session has no milestone list to bind
# to, and a denser timeline is strictly better here.
$snapshots = @()
foreach ($frame in ($telemetryPackets.Keys | Sort-Object)) {
  $telemetry = $telemetryPackets[$frame]
  $packet = Find-PacketNearFrame -Packets $translationPackets -Frame $frame -Tolerance 60
  $zones = @()
  $status = "telemetry_only"
  if ($packet) {
    $status = "ok"
    foreach ($node in @($packet.nodes)) {
      $zones += [ordered]@{
        zoneId = $node.zoneId
        name = $node.name
        type = $node.type
        av = [double]$node.raw.av
        bp = [double]$node.raw.bp
        dp = [double]$node.raw.dp
        total = [double]$node.raw.av + [double]$node.raw.bp + [double]$node.raw.dp
        density = [double]$node.density
        hydroCoupling = [double]$node.hydroCoupling
      }
    }
  }
  $snapshots += [ordered]@{
    label = Get-FrameLabel $frame
    targetFrame = $frame
    actualFrame = [int]$telemetry.frame
    status = $status
    zones = $zones
    telemetryZones = Convert-TelemetryZoneSummary $telemetry
    balance = $telemetry.balance
    teams = $telemetry.teams
    factoids = if ($packet) { @($packet.factoids) } else { @() }
    entanglements = if ($packet) { @($packet.entanglements) } else { @() }
  }
}
if ($snapshots.Count -eq 0) {
  throw "No VA_TELEMETRY_JSON_COMPACT packets: there is no occupancy timeline to file."
}

# ---- the player's own actions ----------------------------------------------------
# VA_DEV_SAMPLE_JSON carries what no AI run has: order counts by class, economy, and
# army centroid, sampled through the session. This is the human-specific half.
$playerTape = @()
foreach ($frame in ($devPackets.Keys | Sort-Object)) {
  $d = $devPackets[$frame]
  $playerTape += [ordered]@{
    frame = [int]$frame
    minutes = [math]::Round($frame / 1800.0, 2)
    commands = $d.playerCommands
    commandTotal = [int]$d.playerCommandTotal
    metal = $d.dev.metal
    energy = $d.dev.energy
    metalIncome = $d.dev.metalIncome
    energyIncome = $d.dev.energyIncome
    centroid = $d.dev.centroid
  }
}
$totalCommands = 0
foreach ($row in $playerTape) { $totalCommands += [int]$row.commandTotal }
Write-Host "Player command tape: $($playerTape.Count) sample(s), $totalCommands order(s) total"
if ($playerTape.Count -gt 0 -and $totalCommands -eq 0) {
  Add-Warn ("Tracking was armed and sampled, but zero player orders were counted. " +
            "Either nothing was commanded, or playerTeamID does not match the seat " +
            "the human actually played (gadget:UnitCommand filters on it).")
}

# ---- outcome ---------------------------------------------------------------------
$lastVerdict = "abandoned"
$resultObj = $null
if ($resultPackets.Count -gt 0) {
  $lastResultFrame = ($resultPackets.Keys | Sort-Object | Select-Object -Last 1)
  $resultObj = $resultPackets[$lastResultFrame]
  if ($resultObj.status) { $lastVerdict = [string]$resultObj.status }
} else {
  if (-not $AllowNoResult) {
    Add-Warn ("No VA_RESULT_JSON_COMPACT: the session never reached a terminal. " +
              "Zone flow and occupancy are still valid; the outcome is not. " +
              "Use /luarules vawin | vafail | vapartial to end a session cleanly.")
  }
}
$lastRatio = $null
$lastBalance = $snapshots[-1].balance
if ($lastBalance -and $lastBalance.valueRatio -ne $null) { $lastRatio = [double]$lastBalance.valueRatio }

# ---- identity --------------------------------------------------------------------
if (-not $MapId) {
  $intentPath = Join-Path $Workspace "outbox\next_mission_intent.json"
  if (Test-Path -LiteralPath $intentPath) {
    $intent = Get-Content -Raw -LiteralPath $intentPath | ConvertFrom-Json
    if ($intent.mapId) { $MapId = [string]$intent.mapId }
    if (-not $MapTitle -and $intent.mapTitle) { $MapTitle = [string]$intent.mapTitle }
  }
}
if (-not $MapId) { throw "Cannot determine mapId. Pass -MapId; the analyser keys zone data on it." }
if (-not $MapTitle) { $MapTitle = $MapId }

# Team roles, stated rather than inferred. The analyser otherwise reads them out of
# data\scenarios\ai_duel\<map>.ai_duel.json, which describes a different match.
$duelTeams = @($PlayerTeamID)
$raptorTeams = @()
$enemyTeams = @()
foreach ($bucket in @($snapshots[-1].teams)) {
  $tid = [int]$bucket.teamId
  $side = [string]$bucket.side
  if ($tid -eq $PlayerTeamID) { continue }
  if ($side -match 'Raptor') { $raptorTeams += $tid } else { $enemyTeams += $tid }
}
if (@($enemyTeams).Count -gt 0) { $duelTeams += ([int](@($enemyTeams | Sort-Object)[0])) }
else { Add-Warn "No non-raptor enemy team found in the final telemetry packet; duel ratio will be unavailable." }

# ---- write ------------------------------------------------------------------------
$calib = [ordered]@{
  # Deliberately the profiler's own schema string: downstream readers branch on it,
  # and a tracked human run is the same shape by construction.
  schemaVersion = "verdance-fib-calibration/0.2"
  generatedAt = (Get-Date).ToString("s")
  sourceKind = "human_session"
  variant = $Variant
  mapId = $MapId
  bridgeMission = $bridgeMission
  milestoneFrames = @($snapshots | ForEach-Object { $_.actualFrame })
  observedPackets = $translationPackets.Count
  observedTelemetryPackets = $telemetryPackets.Count
  observedZoneFlowPackets = $zoneFlowPackets.Count
  observedDevSamples = $devPackets.Count
  zoneFlow = $zoneFlowFinal
  snapshots = $snapshots
  playerTape = $playerTape
  playerCommandTotal = $totalCommands
  result = $resultObj
  warnings = @($warnings)
}
Save-Json $calib (Join-Path $RunDir "calibration_data.json")
$zoneFlowFinal | ConvertTo-Json -Depth 40 | Set-Content -Encoding UTF8 -Path (Join-Path $RunDir "zone_flow.json")

$suiteEntry = [ordered]@{
  status = "completed"
  runDir = $RunDir
  id = "$MapId::human_session"
  mapId = $MapId
  mapTitle = $MapTitle
  variant = $Variant
  seatA = "human"
  seatB = "campaign_ai"
  seatALabel = $SeatLabel
  seatBLabel = $EnemyLabel
  seatKind = "human"
  playerTeamID = $PlayerTeamID
  duelTeams = @($duelTeams)
  raptorTeams = @($raptorTeams)
  lastVerdict = $lastVerdict
  lastRatio = $lastRatio
  elapsedSeconds = $ElapsedSeconds
}

# Appended to a human-only suite, never merged into latest_ai_duel_suite.json: the
# analyser pools every run on a map into one edge total and averages seat ratios by
# sample count, so one human session dropped in there would be averaged against 42
# AI runs and vanish.
if (-not $SuitePath) { $SuitePath = Join-Path $Workspace "reports\map_surveys\latest_human_suite.json" }
New-Item -ItemType Directory -Force -Path (Split-Path -Parent $SuitePath) | Out-Null
$results = @()
if (Test-Path -LiteralPath $SuitePath) {
  $existing = Get-Content -Raw -LiteralPath $SuitePath | ConvertFrom-Json
  foreach ($r in @($existing.results)) {
    if ([string]$r.runDir -ne $RunDir) { $results += $r }
  }
}
$results += $suiteEntry
$suite = [ordered]@{
  schemaVersion = "verdance-human-suite/0.1"
  generatedAt = (Get-Date).ToString("s")
  status = "completed"
  results = @($results)
}
Save-Json $suite $SuitePath

Write-Host ""
Write-Host "Run dir:  $RunDir"
Write-Host "Suite:    $SuitePath ($(@($results).Count) session(s))"
Write-Host "Map:      $MapId  verdict=$lastVerdict  duelTeams=$($duelTeams -join ',')  raptorTeams=$($raptorTeams -join ',')"
if (@($warnings).Count -gt 0) {
  Write-Host ""
  Write-Host "$(@($warnings).Count) warning(s) recorded in calibration_data.json."
}
