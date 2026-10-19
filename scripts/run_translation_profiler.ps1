<#
.SYNOPSIS
  Runs one headless BAR match and exports Verdance translation packets at
  Fibonacci frame milestones for calibration.
#>
param(
  [string]$Workspace = "$env:USERPROFILE\Documents\BAR_Verdance_Workspace",
  [string]$ScenarioPath = "",
  [string]$Variant = "clean_baseline",
  [int]$MaxFrames = 129600,
  [int]$TimeoutSeconds = 5400,
  [string]$MilestoneMinutes = "",
  [string]$MilestoneFrames = "",
  [switch]$QuitAfterLast,
  [switch]$SkipPatchInstall
)

$ErrorActionPreference = "Stop"
. (Join-Path (Split-Path -Parent $MyInvocation.MyCommand.Path) "_common.ps1")
# Packet parsing moved to lib_packet_parse.ps1 so harvest_human_run_v1.ps1 can reuse
# it -- this file launches a headless match in its own body and cannot be dot-sourced.
. (Join-Path (Split-Path -Parent $MyInvocation.MyCommand.Path) "lib_packet_parse.ps1")

function Get-FibMilestones {
  param([int]$MaxFrame, [int]$Tick = 900)
  $a = 1
  $b = 1
  $frames = [System.Collections.Generic.List[int]]::new()
  while ($true) {
    $f = $a * $Tick
    if ($f -gt $MaxFrame) { break }
    if (-not $frames.Contains($f)) { [void]$frames.Add($f) }
    $c = $a + $b
    $a = $b
    $b = $c
  }
  return $frames.ToArray()
}

function Get-ExplicitMilestones {
  param([string]$Frames, [string]$Minutes, [int]$MaxFrame)
  $values = [System.Collections.Generic.List[int]]::new()
  if ($Frames) {
    foreach ($part in ($Frames -split ',')) {
      $trim = $part.Trim()
      if (-not $trim) { continue }
      $n = [int][double]$trim
      if ($n -gt 0 -and $n -le $MaxFrame -and -not $values.Contains($n)) { [void]$values.Add($n) }
    }
  }
  if ($Minutes) {
    foreach ($part in ($Minutes -split ',')) {
      $trim = $part.Trim()
      if (-not $trim) { continue }
      $frame = [int]([double]$trim * 60 * 30)
      if ($frame -gt 0 -and $frame -le $MaxFrame -and -not $values.Contains($frame)) { [void]$values.Add($frame) }
    }
  }
  return @($values.ToArray() | Sort-Object)
}

function Get-Percentile {
  param([object[]]$Values, [double]$P)
  if (-not $Values -or $Values.Count -eq 0) { return 0 }
  $sorted = @($Values | Sort-Object)
  $idx = [math]::Floor(($sorted.Count - 1) * $P)
  return [double]$sorted[$idx]
}

if (-not $ScenarioPath) {
  $ScenarioPath = Join-Path $Workspace "data\scenarios\ats_clean_baseline.json"
}
if (!(Test-Path $ScenarioPath)) { throw "Scenario not found: $ScenarioPath" }

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$installPatch = Join-Path $scriptDir "install_balance_telemetry_patch.ps1"
$installPlayable = Join-Path $scriptDir "install_playable_slice.ps1"
$infolog = Get-BARInfolog $Workspace

$explicitMilestones = Get-ExplicitMilestones -Frames $MilestoneFrames -Minutes $MilestoneMinutes -MaxFrame $MaxFrames
$milestones = if (@($explicitMilestones).Count -gt 0) { $explicitMilestones } else { Get-FibMilestones -MaxFrame $MaxFrames }
$milestoneFrameStr = ($milestones -join ",")
$fibQuit = if ($QuitAfterLast) { "true" } else { "false" }

$stamp = Get-Date -Format "yyyyMMdd_HHmmss"
$suiteDir = Join-Path (Join-Path $Workspace "headless_runs") "fib_profiler_$stamp"
$milestonesDir = Join-Path $suiteDir "milestones"
New-Item -ItemType Directory -Force -Path $milestonesDir | Out-Null

Write-Host "Verdance Fibonacci profiler"
Write-Host "Scenario: $ScenarioPath"
Write-Host "Variant: $Variant"
Write-Host "Milestones: $milestoneFrameStr"
Write-Host "Suite dir: $suiteDir"

if (-not $SkipPatchInstall) {
  & powershell -ExecutionPolicy Bypass -File $installPatch -Workspace $Workspace
}

$logPath = Join-Path $suiteDir "run.log.txt"
$playableArgs = @(
  "-ExecutionPolicy", "Bypass",
  "-File", $installPlayable,
  "-Workspace", $Workspace,
  "-ScenarioPath", $ScenarioPath,
  "-Variant", $Variant,
  "-PlayerController", "clean_baseline",
  "-BalanceTest",
  "-SimFrames", ([string]$MaxFrames),
  "-TimeoutSeconds", ([string]$TimeoutSeconds),
  "-ExtraModOptions", "va_fib_export_frames=$milestoneFrameStr;va_fib_quit=$fibQuit;va_headless_autostart=1"
)

$output = & powershell @playableArgs 2>&1
$output | Set-Content -Encoding UTF8 -Path $logPath
if ($LASTEXITCODE -ne 0) {
  Write-Warning "Headless run returned exit code $LASTEXITCODE; parsing any packets that were emitted."
}

$packets = Parse-CompactJsonPackets -Infolog $infolog -Marker "VA_TRANSLATION_PACKET_COMPACT"
$telemetryPackets = Parse-CompactJsonPackets -Infolog $infolog -Marker "VA_TELEMETRY_JSON_COMPACT"
# Cumulative border traffic, sampled on its own clock by the campaign gadget.
# The translation packet's own entanglement list only reports pairs that are
# coupled *right now*; this is the record of everything that actually moved.
$zoneFlowPackets = Parse-CompactJsonPackets -Infolog $infolog -Marker "VA_ZONE_FLOW_JSON"
Write-Host "Found $($packets.Count) translation packet(s)."
Write-Host "Found $($telemetryPackets.Count) telemetry packet(s)."
Write-Host "Found $($zoneFlowPackets.Count) zone-flow packet(s)."

$zoneFlowFinal = $null
if ($zoneFlowPackets.Count -gt 0) {
  $lastFlowFrame = ($zoneFlowPackets.Keys | Sort-Object | Select-Object -Last 1)
  $zoneFlowFinal = $zoneFlowPackets[$lastFlowFrame]
  $zoneFlowFinal | ConvertTo-Json -Depth 40 | Set-Content -Encoding UTF8 -Path (Join-Path $suiteDir "zone_flow.json")
}

$snapshots = @()
$allTotals = @()
$allAvDiffs = @()

foreach ($frame in $milestones) {
  $label = Get-FrameLabel $frame
  $snapDir = Join-Path $milestonesDir ($label -replace '[^A-Za-z0-9_]', '_')
  New-Item -ItemType Directory -Force -Path $snapDir | Out-Null
  $packet = Find-PacketNearFrame -Packets $packets -Frame $frame
  $telemetry = Find-PacketNearFrame -Packets $telemetryPackets -Frame $frame
  $zones = @()
  $telemetryZones = @()
  $status = "missing"
  $actualFrame = $null

  if ($packet) {
    $status = "ok"
    $actualFrame = [int]$packet.frame
    $packet | ConvertTo-Json -Depth 50 | Set-Content -Encoding UTF8 -Path (Join-Path $snapDir "translation_packet.json")
    foreach ($node in @($packet.nodes)) {
      $total = [double]$node.raw.av + [double]$node.raw.bp + [double]$node.raw.dp
      $allTotals += $total
      $zones += [ordered]@{
        zoneId = $node.zoneId
        name = $node.name
        type = $node.type
        av = [double]$node.raw.av
        bp = [double]$node.raw.bp
        dp = [double]$node.raw.dp
        total = $total
        density = [double]$node.density
        hydroCoupling = [double]$node.hydroCoupling
      }
    }
    for ($i = 0; $i -lt $zones.Count; $i++) {
      for ($j = $i + 1; $j -lt $zones.Count; $j++) {
        $allAvDiffs += [math]::Abs($zones[$i].av - $zones[$j].av)
      }
    }
  }
  if ($telemetry) {
    $telemetry | ConvertTo-Json -Depth 80 | Set-Content -Encoding UTF8 -Path (Join-Path $snapDir "telemetry_packet.json")
    $telemetryZones = Convert-TelemetryZoneSummary $telemetry
    if ($status -eq "missing") {
      $status = "telemetry_only"
      $actualFrame = [int]$telemetry.frame
    }
  }

  $snapshots += [ordered]@{
    label = $label
    targetFrame = $frame
    actualFrame = $actualFrame
    status = $status
    zones = $zones
    telemetryZones = $telemetryZones
    balance = if ($telemetry) { $telemetry.balance } else { $null }
    teams = if ($telemetry) { $telemetry.teams } else { @() }
    factoids = if ($packet) { @($packet.factoids) } else { @() }
    entanglements = if ($packet) { @($packet.entanglements) } else { @() }
  }

  if ($packet) {
    Write-Host ("[{0,7}] {1,-8} ok zones={2} factoids={3} entanglements={4}" -f $frame, $label, @($packet.nodes).Count, @($packet.factoids).Count, @($packet.entanglements).Count)
  } else {
    Write-Host ("[{0,7}] {1,-8} missing" -f $frame, $label)
  }
}

$atanh05 = 0.5493
$stats = [ordered]@{
  count = @($allTotals).Count
  min = Get-Percentile $allTotals 0.00
  p25 = Get-Percentile $allTotals 0.25
  p50 = Get-Percentile $allTotals 0.50
  p75 = Get-Percentile $allTotals 0.75
  p90 = Get-Percentile $allTotals 0.90
  p95 = Get-Percentile $allTotals 0.95
  max = Get-Percentile $allTotals 1.00
}
$avDiffStats = [ordered]@{
  count = @($allAvDiffs).Count
  p50 = Get-Percentile $allAvDiffs 0.50
  p75 = Get-Percentile $allAvDiffs 0.75
  p90 = Get-Percentile $allAvDiffs 0.90
}

$proposedDensityDivisor = if ($stats.count -gt 0) { [math]::Max(500, [int]($stats.p50 / $atanh05)) } else { 5000 }
$proposedAvDisparityDivisor = if ($avDiffStats.count -gt 0) { [math]::Max(500, [int]($avDiffStats.p50 / $atanh05)) } else { [math]::Max(500, [int]($proposedDensityDivisor / 2)) }

$calibData = [ordered]@{
  schemaVersion = "verdance-fib-calibration/0.2"
  generatedAt = (Get-Date).ToString("s")
  scenarioPath = $ScenarioPath
  variant = $Variant
  milestoneFrames = $milestones
  observedPackets = $packets.Count
  observedTelemetryPackets = $telemetryPackets.Count
  observedZoneFlowPackets = $zoneFlowPackets.Count
  zoneFlow = $zoneFlowFinal
  stats = $stats
  avDiffStats = $avDiffStats
  proposedTanhDivisor = $proposedDensityDivisor
  proposedAvDisparityDivisor = $proposedAvDisparityDivisor
  snapshots = $snapshots
}
$calibJsonPath = Join-Path $suiteDir "calibration_data.json"
$calibData | ConvertTo-Json -Depth 80 | Set-Content -Encoding UTF8 -Path $calibJsonPath

$mdPath = Join-Path $suiteDir "calibration_report.md"
$md = [System.Text.StringBuilder]::new()
[void]$md.AppendLine("# Verdance Fibonacci Calibration Report")
[void]$md.AppendLine("")
[void]$md.AppendLine("Scenario: ``$(Split-Path -Leaf $ScenarioPath)`` / ``$Variant``")
[void]$md.AppendLine("Observed packets: $($packets.Count) / $($milestones.Count)")
[void]$md.AppendLine("")
[void]$md.AppendLine("## Proposed Constants")
[void]$md.AppendLine("")
[void]$md.AppendLine("| Constant | Proposed | Basis |")
[void]$md.AppendLine("| --- | ---: | --- |")
[void]$md.AppendLine("| Density tanh divisor | $proposedDensityDivisor | tanh(P50 zone total / divisor) ~= 0.5 |")
[void]$md.AppendLine("| AV disparity divisor | $proposedAvDisparityDivisor | tanh(P50 AV diff / divisor) ~= 0.5 |")
[void]$md.AppendLine("")
[void]$md.AppendLine("## Zone Total Distribution")
[void]$md.AppendLine("")
[void]$md.AppendLine("| Stat | Value |")
[void]$md.AppendLine("| --- | ---: |")
foreach ($key in @("count", "min", "p25", "p50", "p75", "p90", "p95", "max")) {
  [void]$md.AppendLine("| $key | $([int]$stats[$key]) |")
}
[void]$md.AppendLine("")
[void]$md.AppendLine("## Timeline")
foreach ($snapshot in $snapshots) {
  [void]$md.AppendLine("")
  [void]$md.AppendLine("### $($snapshot.label) frame $($snapshot.targetFrame) status=$($snapshot.status)")
  if ($snapshot.status -ne "ok" -and $snapshot.status -ne "telemetry_only") { continue }
  if ($snapshot.balance) {
    [void]$md.AppendLine("")
    [void]$md.AppendLine("Balance: playerValue=$($snapshot.balance.playerValue) enemyValue=$($snapshot.balance.enemyValue) ratio=$($snapshot.balance.valueRatio) verdict=$($snapshot.balance.verdict)")
  }
  [void]$md.AppendLine("")
  [void]$md.AppendLine("| Zone | Type | AV | BP | DP | Total | Density |")
  [void]$md.AppendLine("| --- | --- | ---: | ---: | ---: | ---: | ---: |")
  foreach ($zone in $snapshot.zones) {
    [void]$md.AppendLine("| $($zone.name) | $($zone.type) | $([int]$zone.av) | $([int]$zone.bp) | $([int]$zone.dp) | $([int]$zone.total) | $($zone.density) |")
  }
  if (@($snapshot.telemetryZones).Count -gt 0) {
    [void]$md.AppendLine("")
    [void]$md.AppendLine("Top telemetry cells:")
    [void]$md.AppendLine("")
    [void]$md.AppendLine("| Cell/Zone | Presence | Units | Teams |")
    [void]$md.AppendLine("| --- | ---: | ---: | --- |")
    foreach ($zone in @($snapshot.telemetryZones | Select-Object -First 12)) {
      $teamBits = @()
      foreach ($team in @($zone.teams)) {
        if ($team.unitCount -gt 0 -or $team.totalPresence -gt 0) {
          $teamBits += "T$($team.teamId) $($team.side) P=$([int]$team.totalPresence) U=$($team.unitCount)"
        }
      }
      [void]$md.AppendLine("| $($zone.label) | $([int]$zone.totalPresence) | $($zone.unitCount) | $($teamBits -join '; ') |")
    }
  }
}
$md.ToString() | Set-Content -Encoding UTF8 -Path $mdPath

Write-Host "Fibonacci profiler complete."
Write-Host "Observed packets: $($packets.Count) / $($milestones.Count)"
Write-Host "Proposed density divisor: $proposedDensityDivisor"
Write-Host "Proposed AV disparity divisor: $proposedAvDisparityDivisor"
Write-Host "Report: $mdPath"
Write-Host "Data: $calibJsonPath"
