param(
  [string]$Workspace = "$env:USERPROFILE\Documents\BAR_Verdance_Workspace",
  [string]$SuiteManifestPath = "",
  [string]$OutRoot = "",
  [int]$TopZones = 8
)

$ErrorActionPreference = "Stop"
. (Join-Path (Split-Path -Parent $MyInvocation.MyCommand.Path) "_common.ps1")

function Fmt {
  param($Value)
  if ($null -eq $Value) { return "" }
  if ($Value -is [double] -or $Value -is [single] -or $Value -is [decimal]) {
    return ([string]::Format([System.Globalization.CultureInfo]::InvariantCulture, "{0:0.###}", [double]$Value))
  }
  return [string]$Value
}

function Add-Line {
  param([System.Collections.Generic.List[string]]$Lines, [string]$Text = "")
  $Lines.Add($Text) | Out-Null
}

function Get-DesignVerdict {
  param($Result)
  if ($Result.lastVerdict -eq "player_dead") {
    if ($Result.mapId -in @("all_that_simmers", "the_rock_jungle")) { return "raptor/hazard dominated" }
    return "player crushed"
  }
  if ($Result.lastVerdict -eq "player_clear") {
    return "player steamroll"
  }
  if ($Result.lastVerdict -eq "player_stalled") {
    if ([double]$Result.lastRatio -lt 0.2) {
      if ($Result.mapId -in @("all_that_simmers", "the_rock_jungle")) { return "raptor/hazard dominated" }
      return "player crushed"
    }
    if ([double]$Result.lastRatio -lt 0.75) { return "player stalled" }
    return "contested"
  }
  if ($Result.lastVerdict -eq "player_advantage") {
    if ([double]$Result.lastRatio -ge 2.5) { return "player steamroll" }
    return "player advantage"
  }
  if ($Result.lastVerdict -eq "active") {
    if ($null -ne $Result.lastRatio -and [double]$Result.lastRatio -ge 0.75 -and [double]$Result.lastRatio -le 1.35) { return "contested" }
    if ($null -ne $Result.lastRatio -and [double]$Result.lastRatio -lt 0.75) { return "player stalled" }
    return "player advantage"
  }
  return "inconclusive"
}

function Get-RunData {
  param($Result)
  if ($Result.calibrationDataPath -and (Test-Path $Result.calibrationDataPath)) {
    try { return Get-Content -Raw -LiteralPath $Result.calibrationDataPath | ConvertFrom-Json } catch { return $null }
  }
  return $null
}

function Get-ZonePrefix {
  param([string]$MapId)
  switch ($MapId) {
    "all_that_simmers" { return "ATS_" }
    "koom_valley" { return "KOOM_" }
    "tabula" { return "TAB_" }
    "ancient_bastion" { return "AB_" }
    "the_rock_jungle" { return "RJ_" }
    "eye_of_horus" { return "EOH_" }
    "greenest_fields" { return "GF_" }
    default { return "" }
  }
}

function Test-SnapshotMap {
  param($Snapshot, [string]$MapId)
  $prefix = Get-ZonePrefix $MapId
  if (-not $prefix) { return $true }
  $zones = @($Snapshot.zones | Where-Object { $_.zoneId })
  if ($zones.Count -eq 0) { return $true }
  $matching = @($zones | Where-Object { ([string]$_.zoneId).StartsWith($prefix) })
  return ($matching.Count -eq $zones.Count)
}

if (-not $SuiteManifestPath) {
  $SuiteManifestPath = Join-Path $Workspace "reports\map_surveys\latest_campaign_ai_suite.json"
}
if (!(Test-Path $SuiteManifestPath)) { throw "Missing campaign AI suite manifest: $SuiteManifestPath" }
if (-not $OutRoot) { $OutRoot = Join-Path $Workspace "_outbox" }

$suite = Get-Content -Raw -LiteralPath $SuiteManifestPath | ConvertFrom-Json
$stamp = Get-Date -Format "yyyyMMdd_HHmmss"
$outDir = Join-Path $OutRoot "${stamp}_campaign_ai_baseline_packet"
$packetDir = Join-Path $outDir "map_packets"
$heavyDir = Join-Path $Workspace ("reports\map_surveys\campaign_ai_heavy_archive_$stamp")
New-Item -ItemType Directory -Force -Path $packetDir, $heavyDir | Out-Null

$bestByMap = @{}
foreach ($result in @($suite.results)) {
  if ($result.status -ne "completed") { continue }
  $key = [string]$result.mapId
  if (-not $bestByMap.ContainsKey($key)) {
    $bestByMap[$key] = $result
  } elseif ([int]$result.lastFrame -gt [int]$bestByMap[$key].lastFrame) {
    $bestByMap[$key] = $result
  }
}

$scenarioResults = @()
$zoneRecommendations = @()
$zoneEvidence = @{}
$balanceRows = @()

$completedResults = @($suite.results | Where-Object { $_.status -eq "completed" })
foreach ($result in @($completedResults)) {
  $finalMinute = if ($result.lastFrame) { [math]::Round(([double]$result.lastFrame / 1800), 1) } else { 0 }
  $designVerdict = Get-DesignVerdict $result
  $scenarioResults += [ordered]@{
    mapId = $result.mapId
    mapTitle = $result.mapTitle
    variant = $result.variant
    playerTeamID = $result.playerTeamID
    playerSide = $result.playerSide
    playerStartLabel = $result.playerStartLabel
    phase = $result.phase
    finalMinute = $finalMinute
    finalVerdict = $result.lastVerdict
    designVerdict = $designVerdict
    finalRatio = $result.lastRatio
    finalPlayerValue = $result.lastPlayerValue
    finalEnemyValue = $result.lastEnemyValue
    observedTelemetryPackets = $result.observedTelemetryPackets
    observedTranslationPackets = $result.observedTranslationPackets
    calibrationDataPath = $result.calibrationDataPath
    calibrationReportPath = $result.calibrationReportPath
  }
  $balanceRows += [ordered]@{
    map = $result.mapTitle
    mapId = $result.mapId
    variant = $result.variant
    playerSide = $result.playerSide
    playerTeamID = $result.playerTeamID
    finalMinute = $finalMinute
    verdict = $designVerdict
    ratio = $result.lastRatio
    playerValue = $result.lastPlayerValue
    enemyValue = $result.lastEnemyValue
  }
}

$main = [System.Collections.Generic.List[string]]::new()
Add-Line $main "# Verdance Campaign AI Baseline"
Add-Line $main ""
Add-Line $main "Purpose: compact design packet from real BAR/Recoil headless simulations. The simulated player is BARbarIAn hard_aggressive; NPCs are SimpleAI unless a scenario says otherwise; wild maps keep RaptorsAI."
Add-Line $main ""
Add-Line $main "Source suite: ``$SuiteManifestPath``"
Add-Line $main ""
Add-Line $main "| Map | Variant | Final minute | Verdict | Ratio | Player | Enemy | Recommendation |"
Add-Line $main "| --- | --- | ---: | --- | ---: | ---: | ---: | --- |"

foreach ($mapId in ($bestByMap.Keys | Sort-Object)) {
  $result = $bestByMap[$mapId]
  $data = Get-RunData $result
  $designVerdict = Get-DesignVerdict $result
  $finalMinute = if ($result.lastFrame) { [math]::Round(([double]$result.lastFrame / 1800), 1) } else { 0 }
  $recommendation = switch ($designVerdict) {
    "raptor/hazard dominated" { "Reduce raptor pressure or make hive-clearing the explicit objective; zone map should separate hive core from lanes." }
    "player steamroll" { "Add defender depth, expand NPC start, or move objective pressure earlier." }
    "player advantage" { "Healthy candidate; tune enemy base density upward if mission should resist longer." }
    "contested" { "Best calibration band; preserve topology and inspect zone crossings." }
    "player stalled" { "Add player resources/routes or weaken static defender development." }
    "player crushed" { "Lower enemy or hazard starting pressure before campaign use." }
    default { "Rerun or inspect logs; evidence incomplete." }
  }

  Add-Line $main "| $($result.mapTitle) | $($result.variant) | $finalMinute | $designVerdict | $(Fmt $result.lastRatio) | $(Fmt $result.lastPlayerValue) | $(Fmt $result.lastEnemyValue) | $recommendation |"

  $packet = [System.Collections.Generic.List[string]]::new()
  Add-Line $packet "# $($result.mapTitle) Campaign AI Packet"
  Add-Line $packet ""
  Add-Line $packet "Variant: ``$($result.variant)``"
  Add-Line $packet "Player simulation: BARbarIAn hard_aggressive on team $($result.playerTeamID) / $($result.playerSide) / $($result.playerStartLabel)."
  Add-Line $packet "Verdict: $designVerdict. Final ratio $(Fmt $result.lastRatio), player $(Fmt $result.lastPlayerValue), enemy $(Fmt $result.lastEnemyValue)."
  Add-Line $packet ""
  Add-Line $packet "Recommendation: $recommendation"
  Add-Line $packet ""

  if ($data) {
    $validSnapshots = @($data.snapshots | Where-Object { Test-SnapshotMap $_ $result.mapId })
    $filteredCount = @($data.snapshots).Count - $validSnapshots.Count
    if ($filteredCount -gt 0) {
      Add-Line $packet "Data quality note: omitted $filteredCount snapshot(s) whose zone IDs did not match this map, likely from an interrupted/resumed headless log."
      Add-Line $packet ""
    }
    Add-Line $packet "## Timeline"
    Add-Line $packet ""
    Add-Line $packet "| Time | Engine verdict | Ratio | Player | Enemy | Top zones |"
    Add-Line $packet "| --- | --- | ---: | ---: | ---: | --- |"
    foreach ($snapshot in @($validSnapshots | Where-Object { $_.balance })) {
      $topBits = @()
      foreach ($zone in @($snapshot.telemetryZones | Select-Object -First $TopZones)) {
        $topBits += "$($zone.label) P=$(Fmt $zone.totalPresence) U=$($zone.unitCount)"
      }
      Add-Line $packet "| $($snapshot.label) | $($snapshot.balance.verdict) | $(Fmt $snapshot.balance.valueRatio) | $(Fmt $snapshot.balance.playerValue) | $(Fmt $snapshot.balance.enemyValue) | $($topBits -join '; ') |"
    }
    Add-Line $packet ""
    Add-Line $packet "## Zone Notes"
    Add-Line $packet ""
    $lastSnap = @($validSnapshots | Where-Object { $_.telemetryZones } | Select-Object -Last 1)
    foreach ($zone in @($lastSnap.telemetryZones | Select-Object -First $TopZones)) {
      $teamBits = @()
      foreach ($team in @($zone.teams)) {
        if ([double]$team.totalPresence -gt 0 -or [int]$team.unitCount -gt 0) {
          $teamBits += "T$($team.teamId) $($team.side) P=$(Fmt $team.totalPresence) U=$($team.unitCount)"
        }
      }
      Add-Line $packet "- $($zone.label): final presence $(Fmt $zone.totalPresence), units $($zone.unitCount). $($teamBits -join '; ')"
    }

    foreach ($snapshot in @($validSnapshots | Where-Object { $_.telemetryZones })) {
      $activeZones = @($snapshot.telemetryZones | Where-Object { [double]$_.totalPresence -gt 500 })
      foreach ($zone in @($activeZones | Select-Object -First $TopZones)) {
        $zoneKey = "$($result.mapId)::$($zone.zoneId)"
        $presence = [double]$zone.totalPresence
        if (-not $zoneEvidence.ContainsKey($zoneKey)) {
          $zoneEvidence[$zoneKey] = [ordered]@{
            mapId = $result.mapId
            mapTitle = $result.mapTitle
            zoneId = $zone.zoneId
            zoneLabel = $zone.label
            firstSeenMinute = $snapshot.label
            lastSeenMinute = $snapshot.label
            observationCount = 0
            maxPresence = 0
            maxUnitCount = 0
            confidence = "medium"
            recommendation = if ($zone.label -match 'Start|Shelf|Pocket|Basin|Ridge') { "Keep as base/start zone; observed sustained development." } elseif ($zone.label -match 'Center|Lane|Gate|Scar|Causeway|Field') { "Keep or split as conflict lane if repeated high presence appears across milestones." } else { "Review against minimap after more variants." }
          }
        }
        $evidence = $zoneEvidence[$zoneKey]
        $evidence.observationCount = [int]$evidence.observationCount + 1
        $evidence.lastSeenMinute = $snapshot.label
        if ($presence -gt [double]$evidence.maxPresence) { $evidence.maxPresence = $presence }
        if ([int]$zone.unitCount -gt [int]$evidence.maxUnitCount) { $evidence.maxUnitCount = [int]$zone.unitCount }
        if ([double]$evidence.maxPresence -gt 10000 -or [int]$evidence.observationCount -ge 4) { $evidence.confidence = "high" }
      }
    }
  } else {
    Add-Line $packet "No parseable calibration data was available for this run."
  }

  $packetPath = Join-Path $packetDir ("{0}.md" -f $result.mapId)
  $packet | Set-Content -Encoding UTF8 -Path $packetPath
}

$zoneRecommendations = @(
  $zoneEvidence.Values |
    Sort-Object mapTitle, zoneLabel |
    ForEach-Object {
      [ordered]@{
        mapId = $_.mapId
        mapTitle = $_.mapTitle
        zoneId = $_.zoneId
        zoneLabel = $_.zoneLabel
        firstSeenMinute = $_.firstSeenMinute
        lastSeenMinute = $_.lastSeenMinute
        observationCount = $_.observationCount
        maxPresence = $_.maxPresence
        maxUnitCount = $_.maxUnitCount
        confidence = $_.confidence
        recommendation = $_.recommendation
      }
    }
)

Add-Line $main ""
Add-Line $main "Map packets live in ``map_packets/``. Raw logs are intentionally excluded from this compact folder; heavy archive path is recorded in ``scenario_results.json``."
$mainPath = Join-Path $outDir "campaign_ai_baseline.md"
$main | Set-Content -Encoding UTF8 -Path $mainPath

$scenarioObject = [ordered]@{
  schemaVersion = "verdance-campaign-ai-export/0.1"
  generatedAt = (Get-Date).ToString("s")
  sourceSuiteManifestPath = $SuiteManifestPath
  compactExportDir = $outDir
  heavyArchiveDir = $heavyDir
  results = $scenarioResults
}
Save-Json $scenarioObject (Join-Path $outDir "scenario_results.json")
Save-Json ([ordered]@{ schemaVersion = "verdance-zone-recommendations/0.1"; generatedAt = (Get-Date).ToString("s"); recommendations = $zoneRecommendations }) (Join-Path $outDir "zone_recommendations.json")

$csvLines = @("map,mapId,variant,playerSide,playerTeamID,finalMinute,verdict,ratio,playerValue,enemyValue")
foreach ($row in $balanceRows) {
  $csvLines += ('"{0}","{1}","{2}","{3}",{4},{5},"{6}",{7},{8},{9}' -f $row.map, $row.mapId, $row.variant, $row.playerSide, $row.playerTeamID, (Fmt $row.finalMinute), $row.verdict, (Fmt $row.ratio), (Fmt $row.playerValue), (Fmt $row.enemyValue))
}
$csvLines | Set-Content -Encoding UTF8 -Path (Join-Path $outDir "balance_matrix.csv")

Copy-Item -Force -LiteralPath $SuiteManifestPath -Destination (Join-Path $heavyDir "suite_manifest.json")
foreach ($result in @($suite.results)) {
  if ($result.runnerLogPath -and (Test-Path $result.runnerLogPath)) {
    Copy-Item -Force -LiteralPath $result.runnerLogPath -Destination (Join-Path $heavyDir (Split-Path -Leaf $result.runnerLogPath))
  }
}

Write-Host "Created compact campaign AI export: $outDir"
Write-Host "Created heavy archive: $heavyDir"
