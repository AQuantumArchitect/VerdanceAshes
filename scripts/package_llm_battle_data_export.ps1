param(
  [string]$Workspace = "$env:USERPROFILE\Documents\BAR_Verdance_Workspace",
  [string]$OutRoot = ""
)

$ErrorActionPreference = "Stop"

function Fmt {
  param($Value)
  if ($null -eq $Value) { return "" }
  if ($Value -is [double] -or $Value -is [single] -or $Value -is [decimal]) {
    return ([string]::Format([System.Globalization.CultureInfo]::InvariantCulture, "{0:0.##}", [double]$Value))
  }
  return [string]$Value
}

function Add-Line {
  param([System.Collections.Generic.List[string]]$Lines, [string]$Text = "")
  $Lines.Add($Text) | Out-Null
}

$stamp = Get-Date -Format "yyyyMMdd_HHmmss"
if (-not $OutRoot) {
  $OutRoot = Join-Path $Workspace "_outbox"
}
$outDir = Join-Path $OutRoot "${stamp}_seven_map_llm_battle_data"
New-Item -ItemType Directory -Force -Path $outDir | Out-Null

$fitPath = Join-Path $Workspace "reports\baselines\ats_clean_baseline_calibration.fit_source.json"
$latestPath = Join-Path $Workspace "outbox\bar_zone_telemetry.latest.json"
$recommendationsPath = Join-Path $Workspace "reports\map_calibration_recommendations.md"

if (!(Test-Path $fitPath)) { throw "Missing ATS calibration source: $fitPath" }
if (!(Test-Path $latestPath)) { throw "Missing latest telemetry: $latestPath" }

$fit = Get-Content -Raw -LiteralPath $fitPath | ConvertFrom-Json
$latest = Get-Content -Raw -LiteralPath $latestPath | ConvertFrom-Json

$pool = @(
  [ordered]@{ map="All That Simmers"; subtitle="The Default High-Conflict Swamp"; hazard="35%"; wind="W4-12 avg6e/t"; metal="1.8mu/s"; arm="M1 So1 D1"; nmc="M1 D1"; cor="M1"; evidence="real_BAR_AI_samples_available" },
  [ordered]@{ map="Koom Valley"; subtitle="The Fluid Scar"; hazard="35%"; wind="W10-22 avg12e/t"; metal="2.8mu/s"; arm="M6 So2 Wi2 D1"; nmc="M3 Wi1 D2"; cor="-"; evidence="pending_BAR_AI_samples" },
  [ordered]@{ map="Tabula"; subtitle="The Tiered Plateau"; hazard="35%"; wind="W18-36 avg20e/t"; metal="2.1mu/s"; arm="M2 So1 Wi1 D1"; nmc="M2 Wi1 D1"; cor="-"; evidence="pending_BAR_AI_samples" },
  [ordered]@{ map="Ancient Bastion"; subtitle="Taelith-Armada Citadel"; hazard=""; wind="W12-28 avg15e/t"; metal="2.9mu/s"; arm="M9 So4 Wi3 D8"; nmc="-"; cor="D1"; evidence="pending_BAR_AI_samples" },
  [ordered]@{ map="The Rock Jungle"; subtitle="Limestone Spire Labyrinth"; hazard="PVE"; wind="W6-16 avg8e/t"; metal="1.5mu/s"; arm="-"; nmc="M2 D1"; cor="-"; evidence="pending_BAR_AI_samples" },
  [ordered]@{ map="Eye of Horus"; subtitle="The MIRV Glassed Core"; hazard="CORTEX DEALER"; wind="W14-30 avg17e/t"; metal="3.1mu/s"; arm="-"; nmc="-"; cor="M5 So3 D5"; evidence="pending_BAR_AI_samples" },
  [ordered]@{ map="Greenest Fields"; subtitle="The Synthesized Utopia"; hazard=""; wind="W8-20 avg11e/t"; metal="0mu/s"; arm="So6 Wi4 D2"; nmc="So1 Wi2 D1"; cor="-"; evidence="pending_BAR_AI_samples_archive_missing" }
)

$machine = [ordered]@{
  schemaVersion = "verdance-seven-map-llm-battle-export/0.1"
  generatedAt = (Get-Date).ToString("s")
  purpose = "Compact export for design LLMs. Contains real BAR-AI telemetry where available and explicit gaps where map battle samples have not been produced."
  evidenceWarning = "Only All That Simmers currently has real BAR-AI sampled battle telemetry in this workspace. Do not infer exact numeric scales for the other six maps yet."
  sevenMapPool = $pool
  realSamples = [ordered]@{
    allThatSimmers = [ordered]@{
      calibrationSource = Split-Path -Leaf $fitPath
      telemetrySource = Split-Path -Leaf $latestPath
      sampledFrames = $fit.milestoneFrames
      sampledSeconds = @($fit.milestoneFrames | ForEach-Object { [Math]::Round(([double]$_ / 30.0), 2) })
      valueScaleStats = $fit.stats
      proposedDensityDivisor = $fit.proposedTanhDivisor
      proposedAvDisparityDivisor = $fit.proposedAvDisparityDivisor
      latestTelemetry = [ordered]@{
        frame = $latest.frame
        seconds = $latest.seconds
        variantId = $latest.variantId
        missionId = $latest.missionId
        balance = $latest.balance
      }
      snapshots = $fit.snapshots
      latestTeams = $latest.teams
      latestZones = $latest.zones
    }
  }
}

$machinePath = Join-Path $outDir "machine_readable_battle_data.json"
$machine | ConvertTo-Json -Depth 100 | Set-Content -Encoding UTF8 -Path $machinePath

$readme = New-Object System.Collections.Generic.List[string]
Add-Line $readme "# Verdance Seven-Map Battle Data Export"
Add-Line $readme ""
Add-Line $readme "This folder is meant to be dumped into a design LLM without drowning it in raw BAR logs."
Add-Line $readme ""
Add-Line $readme "Important: only `All That Simmers` currently has real sampled BAR-AI battle telemetry in this export. The other six maps have design descriptors and recommended measurement targets, but not fought numeric samples yet."
Add-Line $readme ""
Add-Line $readme "Files:"
Add-Line $readme ""
Add-Line $readme "- README_FOR_LLM.md: short orientation and evidence limits."
Add-Line $readme "- battle_scale_slices.md: human-readable time slices and actual army/build/defense values."
Add-Line $readme "- seven_map_design_matrix.md: the seven-map pool, what each map is supposed to teach, and what is missing."
Add-Line $readme "- machine_readable_battle_data.json: compact structured data for programmatic ingestion."
Add-Line $readme ""
Add-Line $readme "Metric vocabulary:"
Add-Line $readme ""
Add-Line $readme "- AV / armyValue: mobile combat and army value."
Add-Line $readme "- BP / buildPower: construction capacity."
Add-Line $readme "- DP / defensiveValue: static or defensive value."
Add-Line $readme "- total: AV + BP + DP in the translation profiler."
Add-Line $readme "- density: normalized zone saturation after calibration."
Add-Line $readme "- valueRatio: playerTeamValue / enemyTeamValue."
Add-Line $readme ""
Add-Line $readme "Scale warning:"
Add-Line $readme ""
Add-Line $readme "On All That Simmers, values in the low thousands are normal local force clusters by 30-180 seconds. The authored center and raptor/hive defenses can produce huge defensive values, so do not treat one 75000 DP zone as a normal mobile army. The current density divisor from real samples is about 5735, replacing the old /250 scale that saturated everything immediately."
$readmePath = Join-Path $outDir "README_FOR_LLM.md"
$readme | Set-Content -Encoding UTF8 -Path $readmePath

$slices = New-Object System.Collections.Generic.List[string]
Add-Line $slices "# Real Battle Scale Slices"
Add-Line $slices ""
Add-Line $slices "Source map: All That Simmers v1.1.1"
Add-Line $slices ""
Add-Line $slices "Evidence type: BAR/Recoil headless telemetry with BAR-AI/simple AI participants, sampled at Fibonacci-ish early-game milestones and one later zone telemetry export."
Add-Line $slices ""
Add-Line $slices "Calibration stats from the sampled zones:"
Add-Line $slices ""
Add-Line $slices "- sample count: $($fit.stats.count) zone totals"
Add-Line $slices "- p50 total: $($fit.stats.p50)"
Add-Line $slices "- p75 total: $($fit.stats.p75)"
Add-Line $slices "- p90 total: $($fit.stats.p90)"
Add-Line $slices "- max total: $($fit.stats.max)"
Add-Line $slices "- recommended density divisor: $($fit.proposedTanhDivisor)"
Add-Line $slices "- recommended AV-disparity divisor: $($fit.proposedAvDisparityDivisor)"
Add-Line $slices ""
Add-Line $slices "## Time Slices"
Add-Line $slices ""
foreach ($snap in @($fit.snapshots)) {
  Add-Line $slices "### $($snap.label) / frame $($snap.actualFrame)"
  Add-Line $slices ""
  Add-Line $slices "| Zone | AV | BP | DP | Total | Density |"
  Add-Line $slices "| --- | ---: | ---: | ---: | ---: | ---: |"
  foreach ($z in @($snap.zones)) {
    Add-Line $slices "| $($z.name) | $(Fmt $z.av) | $(Fmt $z.bp) | $(Fmt $z.dp) | $(Fmt $z.total) | $(Fmt $z.density) |"
  }
  Add-Line $slices ""
}

Add-Line $slices "## Latest Full Team Snapshot"
Add-Line $slices ""
Add-Line $slices "Frame $($latest.frame) / $($latest.seconds) seconds / variant $($latest.variantId)."
Add-Line $slices ""
Add-Line $slices "Balance verdict: $($latest.balance.verdict), value ratio $([Math]::Round([double]$latest.balance.valueRatio, 4)), player value $($latest.balance.playerValue), enemy value $($latest.balance.enemyValue)."
Add-Line $slices ""
Add-Line $slices "| Team | Side | AI | Army | BP | DP | Total | Metal/s | Energy/s | Units | Structures | Top units |"
Add-Line $slices "| --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |"
foreach ($team in @($latest.teams)) {
  if ([double]$team.metrics.totalUnitValue -le 0 -and [int]$team.metrics.unitCount -eq 0) { continue }
  $topUnits = @($team.unitCountsByDef.PSObject.Properties | Sort-Object Value -Descending | Select-Object -First 5 | ForEach-Object { "$($_.Name)x$($_.Value)" }) -join ", "
  Add-Line $slices "| $($team.teamId) | $($team.side) | $($team.isAi) | $(Fmt $team.metrics.armyValue) | $(Fmt $team.metrics.buildPower) | $(Fmt $team.metrics.defensiveValue) | $(Fmt $team.metrics.totalUnitValue) | $(Fmt $team.metrics.metalIncome) | $(Fmt $team.metrics.energyIncome) | $(Fmt $team.metrics.unitCount) | $(Fmt $team.metrics.structureCount) | $topUnits |"
}
Add-Line $slices ""
Add-Line $slices "## Latest Zone Snapshot"
Add-Line $slices ""
foreach ($zoneProp in $latest.zones.PSObject.Properties) {
  $zone = $zoneProp.Value
  Add-Line $slices "### $($zone.label)"
  Add-Line $slices ""
  Add-Line $slices "| Team | Side | Army | BP | DP | Total | Units | Structures | Top units |"
  Add-Line $slices "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |"
  foreach ($team in @($zone.teams)) {
    $topUnits = @($team.unitCountsByDef.PSObject.Properties | Sort-Object Value -Descending | Select-Object -First 5 | ForEach-Object { "$($_.Name)x$($_.Value)" }) -join ", "
    Add-Line $slices "| $($team.teamId) | $($team.side) | $(Fmt $team.metrics.armyValue) | $(Fmt $team.metrics.buildPower) | $(Fmt $team.metrics.defensiveValue) | $(Fmt $team.metrics.totalUnitValue) | $(Fmt $team.metrics.unitCount) | $(Fmt $team.metrics.structureCount) | $topUnits |"
  }
  Add-Line $slices ""
}
$slicesPath = Join-Path $outDir "battle_scale_slices.md"
$slices | Set-Content -Encoding UTF8 -Path $slicesPath

$matrix = New-Object System.Collections.Generic.List[string]
Add-Line $matrix "# Seven-Map Design Matrix"
Add-Line $matrix ""
Add-Line $matrix "| Map | Role | Economy / Setup | Evidence | What The Design LLM Should Learn |"
Add-Line $matrix "| --- | --- | --- | --- | --- |"
foreach ($m in $pool) {
  $lesson = switch ($m.map) {
    "All That Simmers" { "Lane pressure, early real value scale, center/forward-zone saturation." }
    "Koom Valley" { "Moving fronts, expansion tempo, flank pressure. Needs fought samples." }
    "Tabula" { "Elevation bands and plateau capture order. Needs fought samples." }
    "Ancient Bastion" { "Siege pressure, defensive saturation, breach timing. Needs fought samples." }
    "The Rock Jungle" { "PVE pathing, survival pressure, maze/choke behavior. Needs fought samples." }
    "Eye of Horus" { "Cortex tech spike, artillery/core pressure, late attrition. Needs fought samples." }
    "Greenest Fields" { "No-metal converter economy, build-power growth, stall detection. Needs archive and fought samples." }
    default { "Needs fought samples." }
  }
  $eco = "H=$($m.hazard); $($m.wind); $($m.metal); ARM $($m.arm); NMC $($m.nmc); COR $($m.cor)"
  Add-Line $matrix "| $($m.map) | $($m.subtitle) | $eco | $($m.evidence) | $lesson |"
}
Add-Line $matrix ""
Add-Line $matrix "Testing priority:"
Add-Line $matrix ""
Add-Line $matrix "1. Re-run All That Simmers after headless stability is confirmed."
Add-Line $matrix "2. Add Koom Valley and Tabula next because they teach front movement and elevation."
Add-Line $matrix "3. Add Ancient Bastion and Eye of Horus for siege/late-tech values."
Add-Line $matrix "4. Add Greenest Fields only after the local archive is installed."
Add-Line $matrix "5. Add The Rock Jungle as a special PVE pathing benchmark."
$matrixPath = Join-Path $outDir "seven_map_design_matrix.md"
$matrix | Set-Content -Encoding UTF8 -Path $matrixPath

if (Test-Path $recommendationsPath) {
  Copy-Item -Force -LiteralPath $recommendationsPath -Destination (Join-Path $outDir "seven_map_recommendations.md")
}

Write-Host "Created LLM battle data export: $outDir"
Write-Host "Main file: $readmePath"
