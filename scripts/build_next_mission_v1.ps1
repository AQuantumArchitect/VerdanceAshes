param(
  [string]$Workspace = "",
  [string]$IntentPath = "",
  [string]$StatePath = "",
  [switch]$Launch,
  [switch]$SaveGame,
  [string]$SaveName = "",
  [int]$TimeoutSeconds = 300
)

$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
. (Join-Path $ScriptDir "_common.ps1")
$Workspace = Get-VerdanceWorkspaceRoot -Workspace $Workspace

function Add-OrSetProperty {
  param($Object, [string]$Name, $Value)
  if ($Object.PSObject.Properties[$Name]) {
    $Object.$Name = $Value
  } else {
    $Object | Add-Member -NotePropertyName $Name -NotePropertyValue $Value
  }
}

function Get-ZoneById {
  param($ZoneMap, [string]$ZoneId)
  if (-not $ZoneMap -or -not $ZoneMap.zones -or -not $ZoneId) { return $null }
  return @($ZoneMap.zones) | Where-Object { $_.zoneId -eq $ZoneId } | Select-Object -First 1
}

function Get-ZoneCenter {
  param($Zone, [double[]]$Fallback)
  if (-not $Zone -or -not $Zone.bounds) { return $Fallback }
  $b = $Zone.bounds
  return @(
    [Math]::Max(0.02, [Math]::Min(0.98, (([double]$b.xMin + [double]$b.xMax) / 2.0))),
    [Math]::Max(0.02, [Math]::Min(0.98, (([double]$b.zMin + [double]$b.zMax) / 2.0)))
  )
}

function New-StartRect {
  param([double[]]$Center, [double]$Radius = 0.22)
  $x = [double]$Center[0]
  $z = [double]$Center[1]
  return @(
    [Math]::Max(0.0, $x - $Radius),
    [Math]::Max(0.0, $z - $Radius),
    [Math]::Min(1.0, $x + $Radius),
    [Math]::Min(1.0, $z + $Radius)
  )
}

function Get-MapEntry {
  param($Pool, [string]$MapId)
  return @($Pool.maps) | Where-Object { $_.id -eq $MapId } | Select-Object -First 1
}

function Get-EnemySide {
  param([string]$MapId, $Intent)
  if ($Intent.objectiveTarget -and $Intent.objectiveTarget.targetZoneId -match "CORTEX|COR") { return "Cortex" }
  switch ($MapId) {
    "eye_of_horus" { return "Cortex" }
    "all_that_simmers" { return "Armada" }
    default { return "Armada" }
  }
}

function Get-EnemyRecipeName {
  param([string]$Side)
  if ($Side -eq "Cortex") { return "cortex_sortie_target" }
  return "armada_sortie_target"
}

function Get-EnemyRgb {
  param([string]$Side)
  if ($Side -eq "Cortex") { return @(1.0, 0.20, 0.16) }
  return @(0.25, 0.48, 1.0)
}

function Get-ObjectiveDescription {
  param($Intent)
  $target = $Intent.objectiveTarget
  if ($target -and $target.label) { return [string]$target.label }
  if ($Intent.storyReason) { return [string]$Intent.storyReason }
  return "Complete the local Verdance sortie objective, then extract."
}

function Get-RequiredFrames {
  param($Intent)
  $family = if ($Intent.environment -and $Intent.environment.mapFamily) { [string]$Intent.environment.mapFamily } else { "tempo" }
  switch ($family) {
    "siege" { return 36000 }
    "wild" { return 30000 }
    "economy" { return 27000 }
    default { return 21600 }
  }
}

function New-PlayerRecipe {
  return @(
    [ordered]@{ unitDefName = "legmex"; count = 3; atMetalSpots = $true; dx = -140; dz = 120; spacing = 120 },
    [ordered]@{ unitDefName = "legwin"; count = 4; dx = 120; dz = 160; spacing = 90 },
    [ordered]@{ unitDefName = "legsolar"; count = 2; dx = 240; dz = 80; spacing = 90 },
    [ordered]@{ unitDefName = "leglht"; count = 3; dx = -120; dz = -120; spacing = 120 },
    [ordered]@{ unitDefName = "legcen"; count = 4; dx = 80; dz = -210; spacing = 95 },
    [ordered]@{ unitDefName = "legjav"; count = 2; dx = 260; dz = -230; spacing = 110 }
  )
}

function Get-ScaledCount {
  param([int]$Base, [double]$Scale)
  return [int][Math]::Max(1, [Math]::Round($Base * $Scale))
}

function New-ArmadaRecipe {
  param([double]$Scale = 1.0, [double[]]$PatrolTarget = $null, [switch]$Fortify)
  $recipe = @(
    [ordered]@{ unitDefName = "armmex"; count = 4; atMetalSpots = $true; dx = -160; dz = 120; spacing = 120 },
    [ordered]@{ unitDefName = "armwin"; count = (Get-ScaledCount 5 $Scale); dx = 120; dz = 120; spacing = 85 },
    [ordered]@{ unitDefName = "armsolar"; count = (Get-ScaledCount 3 $Scale); dx = 240; dz = -20; spacing = 90 },
    [ordered]@{ unitDefName = "armllt"; count = (Get-ScaledCount 5 $Scale); dx = -150; dz = -170; spacing = 120 },
    [ordered]@{ unitDefName = "armrl"; count = (Get-ScaledCount 2 $Scale); dx = 20; dz = -190; spacing = 130 },
    [ordered]@{ unitDefName = "armwar"; count = (Get-ScaledCount 7 $Scale); dx = -40; dz = -300; spacing = 90 }
  )
  if ($Fortify) {
    $recipe += [ordered]@{ unitDefName = "armbeamer"; count = 2; dx = -60; dz = -80; spacing = 160 }
  }
  if ($PatrolTarget) {
    $recipe += [ordered]@{ unitDefName = "armpw"; count = (Get-ScaledCount 4 $Scale); dx = 160; dz = -340; spacing = 80; patrolX = $PatrolTarget[0]; patrolZ = $PatrolTarget[1] }
  }
  return $recipe
}

function New-CortexRecipe {
  param([double]$Scale = 1.0, [double[]]$PatrolTarget = $null, [switch]$Fortify)
  $recipe = @(
    [ordered]@{ unitDefName = "cormex"; count = 4; atMetalSpots = $true; dx = -140; dz = 120; spacing = 120 },
    [ordered]@{ unitDefName = "corwin"; count = (Get-ScaledCount 5 $Scale); dx = 120; dz = 120; spacing = 90 },
    [ordered]@{ unitDefName = "corsolar"; count = (Get-ScaledCount 3 $Scale); dx = 230; dz = 0; spacing = 90 },
    [ordered]@{ unitDefName = "corllt"; count = (Get-ScaledCount 5 $Scale); dx = -160; dz = -170; spacing = 120 },
    [ordered]@{ unitDefName = "corrl"; count = (Get-ScaledCount 2 $Scale); dx = 20; dz = -190; spacing = 130 },
    [ordered]@{ unitDefName = "corgator"; count = (Get-ScaledCount 7 $Scale); dx = -40; dz = -300; spacing = 90 }
  )
  if ($Fortify) {
    $recipe += [ordered]@{ unitDefName = "corhlt"; count = 2; dx = -60; dz = -80; spacing = 160 }
  }
  if ($PatrolTarget) {
    $recipe += [ordered]@{ unitDefName = "corak"; count = (Get-ScaledCount 4 $Scale); dx = 160; dz = -340; spacing = 80; patrolX = $PatrolTarget[0]; patrolZ = $PatrolTarget[1] }
  }
  return $recipe
}

function New-RaptorRecipe {
  param([double]$HazardLevel = 0.0)
  $swarmScale = 1.0 + (2.0 * [Math]::Max(0.0, [Math]::Min(1.0, $HazardLevel)))
  $recipe = @(
    [ordered]@{ unitDefName = "raptor_hive"; count = 1; dx = 0; dz = 0; spacing = 80 },
    [ordered]@{ unitDefName = "raptor_turret_basic_t2_v1"; count = 2; dx = -130; dz = 70; spacing = 120 },
    [ordered]@{ unitDefName = "raptor_land_swarmer_basic_t1_v1"; count = (Get-ScaledCount 10 $swarmScale); dx = 120; dz = -90; spacing = 70 },
    [ordered]@{ unitDefName = "raptor_land_swarmer_basic_t2_v1"; count = (Get-ScaledCount 4 $swarmScale); dx = -190; dz = -140; spacing = 80 }
  )
  if ($HazardLevel -gt 0.5) {
    $recipe += [ordered]@{ unitDefName = "raptor_hive"; count = 1; dx = 260; dz = 200; spacing = 80 }
  }
  return $recipe
}

if (-not $IntentPath) { $IntentPath = Join-Path $Workspace "outbox\next_mission_intent.json" }
if (-not $StatePath) { $StatePath = Join-Path $Workspace "state\campaign_state.json" }
if (!(Test-Path $IntentPath)) { throw "No next mission intent at $IntentPath. Run ADVANCE_CAMPAIGN_V1.bat or scripts\advance_campaign_v1.ps1 first." }

$config = Get-VerdanceConfig -Workspace $Workspace
$intent = Get-Content -Raw -LiteralPath $IntentPath | ConvertFrom-Json
$state = if (Test-Path $StatePath) { Get-Content -Raw -LiteralPath $StatePath | ConvertFrom-Json } else { $null }
$poolPath = Join-Path $Workspace "data\map_pool\seven_maps.json"
if (!(Test-Path $poolPath)) { throw "Missing map pool: $poolPath" }
$pool = Get-Content -Raw -LiteralPath $poolPath | ConvertFrom-Json
$map = Get-MapEntry $pool ([string]$intent.mapId)
if (-not $map) { throw "Unknown campaign map id in intent: $($intent.mapId)" }

$zoneMapRel = "data\zone_maps\authored\$($intent.mapId).authored.zone_map.json"
$zoneMapPath = Join-Path $Workspace $zoneMapRel
if (!(Test-Path $zoneMapPath)) { throw "Missing authored zone map for $($intent.mapId): $zoneMapPath" }
$zoneMap = Get-Content -Raw -LiteralPath $zoneMapPath | ConvertFrom-Json

$deployZone = Get-ZoneById $zoneMap ([string]$intent.deploymentZoneId)
$targetZoneId = if ($intent.objectiveTarget -and $intent.objectiveTarget.targetZoneId) { [string]$intent.objectiveTarget.targetZoneId } else { "" }
$targetZone = Get-ZoneById $zoneMap $targetZoneId
$deployCenter = Get-ZoneCenter $deployZone @(0.16, 0.16)
$enemyCenter = Get-ZoneCenter $targetZone @(0.84, 0.84)
$wildCenter = @(0.50, 0.50)

$enemySide = Get-EnemySide ([string]$intent.mapId) $intent
$enemyRecipe = Get-EnemyRecipeName $enemySide
$enemyRgb = Get-EnemyRgb $enemySide
$hasWild = ($map.PSObject.Properties["wilds"] -and $map.wilds) -or ($map.PSObject.Properties["raptors"] -and $map.raptors) -or ($intent.hazardPolicy -and $intent.hazardPolicy -ne "none")

$missionNumber = if ($intent.missionNumber) { [int]$intent.missionNumber } elseif ($state -and $state.missionNumber) { [int]$state.missionNumber } else { 1 }
$missionId = if ($intent.missionId) { [string]$intent.missionId } else { "va_$('{0:d3}' -f $missionNumber)" }
$title = if ($intent.PSObject.Properties["title"] -and $intent.title) {
  "$($intent.title) - $($map.title)"
} else {
  "Verdance Alpha: $($map.title)"
}
$requiredFrames = Get-RequiredFrames $intent
$description = Get-ObjectiveDescription $intent

# --- Difficulty scaling from campaign state -------------------------------
# expectedEnemyScale.center comes from zone-memory abstract presence; the
# difficulty coefficient tracks q6_contested. Both were computed by the engine.
$diffCoeff = if ($intent.economy -and $intent.economy.difficultyCoefficient) { [double]$intent.economy.difficultyCoefficient } else { 1.0 }
$scaleCenter = if ($intent.expectedEnemyScale -and $intent.expectedEnemyScale.center) { [double]$intent.expectedEnemyScale.center } else { 6000.0 }
$enemyScale = [Math]::Round(([Math]::Max(0.7, [Math]::Min(2.2, $scaleCenter / 6000.0)) * $diffCoeff), 3)
$fortify = $enemyScale -ge 1.4
$maxHazard = if ($intent.offscreenPressureSummary -and $intent.offscreenPressureSummary.maxHazard) { [double]$intent.offscreenPressureSummary.maxHazard } else { 0.0 }
$objectiveKind = if ($intent.objectiveTarget -and $intent.objectiveTarget.kind) { [string]$intent.objectiveTarget.kind } else { [string]$intent.objective }
$presenceKind = $objectiveKind -in @("seize_lane", "gate_control")
# Presence objectives: enemy patrols defend the target zone. Destruction
# objectives: enemy patrols pressure the midpoint toward the player.
$patrolTarget = if ($presenceKind) {
  @($enemyCenter[0], $enemyCenter[1])
} else {
  @((($deployCenter[0] + $enemyCenter[0]) / 2.0), (($deployCenter[1] + $enemyCenter[1]) / 2.0))
}

$baseRecipes = [ordered]@{
  legion_sortie_start = New-PlayerRecipe
  armada_sortie_target = (New-ArmadaRecipe -Scale $enemyScale -PatrolTarget $patrolTarget -Fortify:$fortify)
  cortex_sortie_target = (New-CortexRecipe -Scale $enemyScale -PatrolTarget $patrolTarget -Fortify:$fortify)
  raptor_pressure_nest = (New-RaptorRecipe -HazardLevel $maxHazard)
}

$allyTeams = @(
  [ordered]@{ id = 0; startRect = New-StartRect $deployCenter 0.20 },
  [ordered]@{ id = 1; startRect = New-StartRect $enemyCenter 0.22 }
)
$teams = @(
  [ordered]@{ id = 0; side = "Legion"; allyTeam = 0; base = @($deployCenter[0], $deployCenter[1]); rgb = @(0.25, 0.85, 0.35); label = "Legion Green Player" },
  [ordered]@{ id = 1; side = $enemySide; allyTeam = 1; base = @($enemyCenter[0], $enemyCenter[1]); rgb = $enemyRgb; label = "$enemySide Mission Target" }
)
$forces = @(
  [ordered]@{ id = "player_deployment"; label = "Player Deployment - $($intent.deploymentZoneId)"; teamID = 0; side = "Legion"; role = "player_anchor"; base = [ordered]@{ x = $deployCenter[0]; z = $deployCenter[1] }; recipe = "legion_sortie_start" },
  [ordered]@{ id = "primary_objective_force"; label = $description; teamID = 1; side = $enemySide; role = "objective_target"; base = [ordered]@{ x = $enemyCenter[0]; z = $enemyCenter[1] }; recipe = $enemyRecipe }
)
$ai = @(
  [ordered]@{ name = "SimpleAI($enemySide Target)"; shortName = "SimpleAI"; team = 1; version = "<not-versioned>" }
)

if ($hasWild) {
  $allyTeams += [ordered]@{ id = 2; startRect = New-StartRect $wildCenter 0.18 }
  $teams += [ordered]@{ id = 2; side = "Armada"; allyTeam = 2; base = @($wildCenter[0], $wildCenter[1]); rgb = @(0.78, 0.14, 0.92); label = "Raptor Wild Pressure" }
  $forces += [ordered]@{ id = "wild_pressure"; label = "Raptor pressure nest"; teamID = 2; side = "Raptors"; role = "wild_pressure"; base = [ordered]@{ x = $wildCenter[0]; z = $wildCenter[1] }; recipe = "raptor_pressure_nest" }
  $ai += [ordered]@{ name = "RaptorsDefenseAI(Verdance)"; shortName = "RaptorsAI"; team = 2; version = "<not-versioned>" }
}

$graph = if ($state -and $state.graph) { $state.graph } else { [pscustomobject]@{} }
$reputation = if ($state -and $state.reputation) { $state.reputation } else { [pscustomobject]@{} }
$companions = @()
if ($state -and $state.companion) {
  $companions = @([ordered]@{
    id = $state.companion.id
    displayName = $state.companion.displayName
    unitDefName = if ($state.companion.unitDefName) { $state.companion.unitDefName } else { "legcen" }
    xp = $state.companion.xp
    morale = $state.companion.morale
    loyalty = $state.companion.loyalty
    stress = $state.companion.stress
    autonomy = $state.companion.autonomy
    commandMode = $state.companion.commandMode
  })
}

$scenario = [ordered]@{
  schemaVersion = "verdance-playable-scenario/1.0-alpha"
  sourceIntentPath = $IntentPath
  sourceStatePath = $StatePath
  map = [ordered]@{
    id = $map.id
    name = $map.mapName
    sizeX = 0
    sizeZ = 0
    descriptor = $map.descriptor
  }
  zoneMapPath = $zoneMapRel
  defaultVariant = "alpha_player"
  notes = "Generated from Verdance Story Engine v1 mission intent. Human player controls team 0; NPCs use SimpleAI/RaptorsAI."
  missionBase = [ordered]@{
    schemaVersion = "verdance-playable/1.0-alpha"
    campaignId = "verdance_ashes"
    missionId = $missionId
    missionNumber = $missionNumber
    deploymentMapId = $intent.mapId
    deploymentZoneId = $intent.deploymentZoneId
    extractionZoneId = $intent.extractionZoneId
    pathSignal = if ($state -and $state.pathSignal) { $state.pathSignal } else { "B" }
    title = $title
    zone = $map.title
    objective = [ordered]@{
      id = if ($intent.objectiveTarget -and $intent.objectiveTarget.id) { $intent.objectiveTarget.id } else { "$missionId`_objective" }
      kind = if ($intent.objectiveTarget -and $intent.objectiveTarget.kind) { $intent.objectiveTarget.kind } else { $intent.objective }
      requiredFrames = $requiredFrames
      description = $description
      targetZoneId = $targetZoneId
      extractionZoneId = $intent.extractionZoneId
    }
    economy = if ($state -and $state.economy) { $state.economy } else { [ordered]@{ metalIncome = 0; energyIncome = 0; buildPower = 0 } }
    difficulty = [ordered]@{
      enemyScale = $enemyScale
      difficultyCoefficient = $diffCoeff
      hazardLevel = [Math]::Round($maxHazard, 3)
      fortified = $fortify
    }
    graph = $graph
    reputation = $reputation
    companions = $companions
    storyIntent = $intent
  }
  baseRecipes = $baseRecipes
  layout = [ordered]@{
    allyTeams = $allyTeams
    teams = $teams
  }
  forces = $forces
  variants = @(
    [ordered]@{
      id = "alpha_player"
      label = "Alpha Campaign Player"
      playerTeamID = 0
      playerSide = "Legion"
      playerStartLabel = "Legion Green Player"
      notes = "Human-controlled alpha campaign sortie generated from next_mission_intent.json."
      ai = $ai
    }
  )
}

# install_playable_slice needs explicit dimensions for start positions.
$authoredScenarioPath = Join-Path $Workspace "data\scenarios\authored\$($intent.mapId).authored_baseline.json"
if (Test-Path $authoredScenarioPath) {
  $authored = Get-Content -Raw -LiteralPath $authoredScenarioPath | ConvertFrom-Json
  if ($authored.map) {
    $scenario["map"]["sizeX"] = [int]$authored.map.sizeX
    $scenario["map"]["sizeZ"] = [int]$authored.map.sizeZ
  }
}
if (-not $scenario["map"]["sizeX"] -or -not $scenario["map"]["sizeZ"]) {
  throw "Could not determine map dimensions for $($intent.mapId)."
}

$generatedDir = Join-Path $Workspace "data\scenarios\generated"
New-Item -ItemType Directory -Force -Path $generatedDir | Out-Null
$scenarioPath = Join-Path $generatedDir "next_mission_intent.playable.json"
Save-Json $scenario $scenarioPath

if (-not $SaveName) {
  $safeMission = $missionId -replace '[^A-Za-z0-9_-]', '_'
  $SaveName = "verdance_${safeMission}_alpha"
}

$installer = Join-Path $ScriptDir "install_playable_slice.ps1"
if ($Launch -and $SaveGame) {
  & $installer -Workspace $Workspace -ScenarioPath $scenarioPath -Variant "alpha_player" -PlayerController "human" -TimeoutSeconds $TimeoutSeconds -Launch -SaveGame -SaveName $SaveName
} elseif ($Launch) {
  & $installer -Workspace $Workspace -ScenarioPath $scenarioPath -Variant "alpha_player" -PlayerController "human" -TimeoutSeconds $TimeoutSeconds -Launch
} elseif ($SaveGame) {
  & $installer -Workspace $Workspace -ScenarioPath $scenarioPath -Variant "alpha_player" -PlayerController "human" -TimeoutSeconds $TimeoutSeconds -SaveGame -SaveName $SaveName
} else {
  & $installer -Workspace $Workspace -ScenarioPath $scenarioPath -Variant "alpha_player" -PlayerController "human" -TimeoutSeconds $TimeoutSeconds
}

$manifest = [ordered]@{
  ok = $true
  generatedAt = (Get-Date).ToString("s")
  intentPath = $IntentPath
  statePath = $StatePath
  scenarioPath = $scenarioPath
  missionId = $missionId
  missionNumber = $missionNumber
  mapId = $intent.mapId
  mapName = $map.mapName
  deploymentZoneId = $intent.deploymentZoneId
  objectiveTarget = $intent.objectiveTarget
  enemySide = $enemySide
  hasWild = [bool]$hasWild
  saveName = if ($SaveGame) { $SaveName } else { $null }
  seedOutbox = $config.seedOutbox
  seedDestination = $config.seedDestination
  nextStep = if ($Launch) { "BAR launch requested." } elseif ($SaveGame) { "Load the generated save from BAR Saves." } else { "Launch BAR with playable_runs latest startscript, or use PLAY_NEXT_MISSION_V1.bat." }
}
$manifestPath = Join-Path $Workspace "outbox\next_mission_build_manifest.json"
Save-Json $manifest $manifestPath

Write-Host "Built Verdance alpha mission from v1 intent."
Write-Host "Mission: $missionId on $($map.mapName)"
Write-Host "Scenario: $scenarioPath"
Write-Host "Manifest: $manifestPath"
