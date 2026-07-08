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
  # The standing war of the campaign world is Null Mercs vs Armada, so Armada
  # is the default enemy power on most maps. Cortex is an ACCENT: it holds its
  # own maps (the synth economy, the desolate dealer hideout) and never shares
  # a camp with Armada - the two are mortal enemies. A camp is one faction.
  $tz = if ($Intent.objectiveTarget -and $Intent.objectiveTarget.targetZoneId) { [string]$Intent.objectiveTarget.targetZoneId } else { "" }
  if ($tz -match "CORTEX|SYNTH") { return "Cortex" }
  if ($MapId -eq "eye_of_horus") { return "Cortex" }
  return "Armada"
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

# ============================================================================
# THEMED FORCE CONSTRUCTION
# Camps are assembled from faction rings (eco / perimeter / production /
# patrol) around an objective CENTERPIECE. Only the centerpiece force carries
# role=objective_target, so destruction missions are surgical strikes into a
# defended camp instead of base-wipes. Armada camps read as ordered garrisons
# (walls, turret arcs, Guardians); Cortex camps as industrial works (dense
# energy, converter farms, Thud/AK packs, Punishers).
# ============================================================================

$FACTION = @{
  Armada = @{
    mex = "armmex"; wind = "armwin"; solar = "armsolar"; advsolar = "armadvsol"
    llt = "armllt"; hlt = "armbeamer"; aa = "armrl"; radar = "armrad"; wall = "armdrag"
    mstor = "armmstor"; estor = "armestor"; conv = "armmakr"; lab = "armlab"; nano = "armnanotc"
    raider = "armpw"; skirm = "armham"; assault = "armwar"
    bigGun = "armguard"; popup = "armpb"; fus = "armfus"; arad = "armarad"; targ = "armtarg"
    fort = "armfort"; lrpc = "armbrtha"
    rgb = @(0.25, 0.48, 1.0)
  }
  Cortex = @{
    mex = "cormex"; wind = "corwin"; solar = "corsolar"; advsolar = "coradvsol"
    llt = "corllt"; hlt = "corhlt"; aa = "corrl"; radar = "corrad"; wall = "cordrag"
    mstor = "cormstor"; estor = "corestor"; conv = "cormakr"; lab = "corlab"; nano = "cornanotc"
    raider = "corak"; skirm = "corthud"; assault = "corstorm"
    bigGun = "corpun"; popup = "corvipe"; fus = "corfus"; arad = "corarad"; targ = "cortarg"
    fort = "corfort"; lrpc = "corint"
    rgb = @(1.0, 0.20, 0.16)
  }
}

# Null Mercs field Legion-family scrap-line chassis like the player's clans -
# outsider tech on both - but fly ash-grey null colors. Their camps are lean:
# quick eco, light teeth, and patrols that press the Armada approaches.
$MERC = @{
  mex = "legmex"; wind = "legwin"; solar = "legsolar"; radar = "legrad"
  llt = "leglht"; mg = "legmg"; aa = "legrl"; wall = "legdrag"; mstor = "legmstor"
  lab = "leglab"; nano = "legnanotc"
  raider = "leggat"; skirm = "legcen"; assault = "legjav"
  rgb = @(0.63, 0.62, 0.66)
}

function Get-ScaledCount {
  param([int]$Base, [double]$Scale)
  return [int][Math]::Max(1, [Math]::Round($Base * $Scale))
}

function Spec {
  param([string]$Def, [int]$Count, [int]$Dx, [int]$Dz, [int]$Spacing = 90, [bool]$AtSpots = $false, $PatrolX = $null, $PatrolZ = $null)
  $s = [ordered]@{ unitDefName = $Def; count = [Math]::Max(1, $Count); dx = $Dx; dz = $Dz; spacing = $Spacing }
  if ($AtSpots) { $s.atMetalSpots = $true }
  if ($null -ne $PatrolX) { $s.patrolX = [double]$PatrolX; $s.patrolZ = [double]$PatrolZ }
  return $s
}

function New-PlayerKit {
  param([string]$Family)
  $kit = @(
    (Spec "legmex" 3 -140 120 120 $true),
    (Spec "legwin" 4 120 160 90),
    (Spec "legsolar" 2 240 80 90),
    (Spec "legrad" 1 40 -60 100),
    (Spec "leglht" 2 -120 -120 130),
    (Spec "legmg" 1 60 -160 100),
    (Spec "legcen" 3 80 -210 95),
    (Spec "legjav" 2 260 -230 110)
  )
  switch ($Family) {
    "economy" { $kit += @((Spec "legck" 2 180 240 90), (Spec "legwin" 2 320 200 85)) }
    "tempo"   { $kit += @((Spec "leggat" 2 -60 -260 90), (Spec "legcen" 1 140 -260 95)) }
    "siege"   { $kit += @((Spec "legjav" 2 -200 -200 110), (Spec "legrl" 1 -40 -60 100)) }
    "wild"    { $kit += @((Spec "legmg" 1 -180 -60 100), (Spec "leglht" 1 200 -140 130)) }
  }
  return $kit
}

function New-PlayerKitFromRoster {
  # Pillar C: the player's starting force IS their persistent warband - a
  # commander hero plus the veteran cadre they carried out of prior sorties -
  # on top of an economy floor so a wiped roster still yields a playable base.
  param([string]$Family, $Roster, [double]$ResourceMod = 1.0)
  # q7 scarcity thins the economy floor (resourceModifier from the graph).
  $wind = [Math]::Max(2, [int][Math]::Round(4 * $ResourceMod))
  $kit = @(
    (Spec "legmex" 3 -140 120 120 $true),
    (Spec "legwin" $wind 120 160 90),
    (Spec "legsolar" 2 240 80 90),
    (Spec "legrad" 1 40 -60 100)
  )
  $comDef = if ($Roster.commander -and $Roster.commander.unitDef) { [string]$Roster.commander.unitDef } else { "legcom" }
  $kit += (Spec $comDef 1 0 40 100)
  $cadreTotal = 0
  if ($Roster.cadre) {
    foreach ($p in $Roster.cadre.PSObject.Properties) {
      $cnt = [int]$p.Value
      if ($cnt -gt 0) { $kit += (Spec ([string]$p.Name) $cnt -120 -160 95); $cadreTotal += $cnt }
    }
  }
  # Floor: a thin cadre (fresh campaign or a rout) still fields a minimum strike element.
  if ($cadreTotal -lt 4) { $kit += (Spec "legcen" (4 - $cadreTotal) 80 -210 95) }
  $active = @(); if ($Roster.commander -and $Roster.commander.activePerks) { $active = @($Roster.commander.activePerks) }
  if ($active -contains "rapid_deploy") { $kit += (Spec "legjav" 1 200 -230 110) }
  switch ($Family) {
    "economy" { $kit += (Spec "legck" 1 180 240 90) }
    "tempo"   { $kit += (Spec "leggat" 1 -60 -260 90) }
    "siege"   { $kit += (Spec "legrl" 1 -40 -60 100) }
    "wild"    { $kit += (Spec "leglht" 1 200 -140 130) }
  }
  return $kit
}

function Ring-Eco {
  param($T, [double]$S)
  @(
    (Spec $T.mex 4 -160 120 120 $true),
    (Spec $T.wind (Get-ScaledCount 4 $S) 140 170 85),
    (Spec $T.solar (Get-ScaledCount 2 $S) 260 60 95),
    (Spec $T.mstor 1 60 240 100),
    (Spec $T.conv (Get-ScaledCount 2 $S) 320 170 95)
  )
}

function Ring-Perimeter {
  param($T, [double]$S, [int]$FX, [int]$FZ)
  # FX/FZ point from the camp toward the player: defenses face the approach.
  @(
    (Spec $T.llt (Get-ScaledCount 4 $S) (170 * $FX) (150 * $FZ) 150),
    (Spec $T.wall (Get-ScaledCount 8 $S) (270 * $FX) (240 * $FZ) 40),
    (Spec $T.aa 2 (-90 * $FX) (60 * $FZ) 170),
    (Spec $T.radar 1 0 -80 100)
  )
}

function Ring-Production {
  param($T)
  @((Spec $T.lab 1 -300 -150 120), (Spec $T.nano 2 -210 -240 90))
}

function Ring-Patrol {
  param($T, [double]$S, [double]$PX, [double]$PZ)
  @(
    (Spec $T.raider (Get-ScaledCount 4 $S) 120 -300 80 $false $PX $PZ),
    (Spec $T.skirm (Get-ScaledCount 3 $S) -140 -320 90 $false $PX $PZ),
    (Spec $T.assault (Get-ScaledCount 3 $S) 20 -390 95 $false $PX $PZ)
  )
}

function Ring-Fortify {
  param($T, [int]$FX, [int]$FZ)
  @(
    (Spec $T.hlt 2 (110 * $FX) (-70 * $FZ) 180),
    (Spec $T.popup 1 (200 * $FX) (120 * $FZ) 100),
    (Spec $T.bigGun 1 -50 40 100)
  )
}

function Ring-Jammers {
  # Cortex hideout flavor: radar jammer towers + a cloaking field so the base
  # reads as hidden/desolate until you are on top of it (eye_of_horus).
  param($T)
  @(
    (Spec "corjamt" 2 -60 120 160),
    (Spec "corjamt" 1 180 -40 160),
    (Spec "corshroud" 1 0 -30 100)
  )
}

function Centerpiece-Relay {
  param($T)
  @((Spec $T.targ 1 0 0 100), (Spec $T.arad 1 120 60 100), (Spec $T.fus 1 -130 70 110))
}

function Centerpiece-LRPC {
  param($T)
  @((Spec $T.lrpc 1 0 0 100), (Spec $T.fus 1 140 80 110), (Spec $T.fort 6 -90 -120 42))
}

function Centerpiece-EcoWorks {
  param($T, [double]$S)
  @(
    (Spec $T.fus 1 0 0 110),
    (Spec $T.advsolar (Get-ScaledCount 3 $S) 150 60 100),
    (Spec $T.conv (Get-ScaledCount 4 $S) -150 80 90),
    (Spec $T.estor 1 40 180 100)
  )
}

function Centerpiece-CommandPost {
  param($T)
  @((Spec $T.arad 1 0 0 100), (Spec $T.fus 1 130 60 110), (Spec $T.hlt 1 -110 -60 120))
}

function Centerpiece-Hives {
  param([double]$Hazard)
  $specs = @(
    (Spec "raptor_hive" 1 -120 -40 240),
    (Spec "raptor_hive" 1 140 80 240)
  )
  if ($Hazard -gt 0.5) { $specs += (Spec "raptor_hive" 1 0 -220 240) }
  return $specs
}

function New-MercFoothold {
  param([double]$S, [double]$PX, [double]$PZ, [int]$FX, [int]$FZ)
  # FX/FZ face the Armada camp: the mercs' war, not the player's approach.
  @(
    (Spec $MERC.mex 3 -140 110 120 $true),
    (Spec $MERC.wind (Get-ScaledCount 4 $S) 130 160 85),
    (Spec $MERC.solar 1 250 70 95),
    (Spec $MERC.mstor 1 60 230 100),
    (Spec $MERC.radar 1 0 -70 100),
    (Spec $MERC.llt (Get-ScaledCount 3 $S) (160 * $FX) (140 * $FZ) 150),
    (Spec $MERC.mg 1 (230 * $FX) (90 * $FZ) 110),
    (Spec $MERC.aa 1 (-80 * $FX) (60 * $FZ) 160),
    (Spec $MERC.wall (Get-ScaledCount 6 $S) (260 * $FX) (220 * $FZ) 40),
    (Spec $MERC.lab 1 -290 -140 120),
    (Spec $MERC.nano 1 -200 -230 90),
    (Spec $MERC.raider (Get-ScaledCount 3 $S) 110 -290 80 $false $PX $PZ),
    (Spec $MERC.skirm (Get-ScaledCount 2 $S) -130 -310 90 $false $PX $PZ),
    (Spec $MERC.assault (Get-ScaledCount 2 $S) 10 -370 95 $false $PX $PZ)
  )
}

function Ring-RaptorGarrison {
  param([double]$Hazard)
  $swarmScale = 1.0 + (2.0 * [Math]::Max(0.0, [Math]::Min(1.0, $Hazard)))
  @(
    (Spec "raptor_turret_basic_t2_v1" 3 -140 90 150),
    (Spec "raptor_land_swarmer_basic_t1_v1" (Get-ScaledCount 10 $swarmScale) 130 -100 70),
    (Spec "raptor_land_swarmer_basic_t2_v1" (Get-ScaledCount 4 $swarmScale) -200 -150 80)
  )
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
# Onboarding ramp: the first two sorties ease in regardless of lore pressure.
$rampFactor = [Math]::Min(1.0, 0.7 + 0.15 * ($missionNumber - 1))
$enemyScale = [Math]::Round(([Math]::Max(0.7, [Math]::Min(2.2, $scaleCenter / 6000.0)) * $diffCoeff * $rampFactor), 3)
$maxHazard = if ($intent.offscreenPressureSummary -and $intent.offscreenPressureSummary.maxHazard) { [double]$intent.offscreenPressureSummary.maxHazard } else { 0.0 }
$objectiveKind = if ($intent.objectiveTarget -and $intent.objectiveTarget.kind) { [string]$intent.objectiveTarget.kind } else { [string]$intent.objective }
$presenceKind = $objectiveKind -in @("seize_lane", "gate_control")
$mapFamily = if ($intent.environment -and $intent.environment.mapFamily) { [string]$intent.environment.mapFamily } else { "tempo" }

# --- The standing war: Null Mercs vs Armada ---------------------------------
# The mercs keep a foothold on every faction-war mission. Reputation decides
# whether their guns tolerate the player (allied) or merely share a target
# (wary, hostile-to-all). Allied mercs tip the field, so the Armada garrison
# scales up slightly to compensate.
$mercInfo = if ($intent.PSObject.Properties["worldConflict"] -and $intent.worldConflict.nullMercs) { $intent.worldConflict.nullMercs } else { $null }
$mercRep = if ($mercInfo -and $null -ne $mercInfo.reputation) { [double]$mercInfo.reputation }
           elseif ($state -and $state.reputation -and $null -ne $state.reputation.nullmercs) { [double]$state.reputation.nullmercs }
           else { 43.0 }
$mercsAllied = if ($mercInfo -and $null -ne $mercInfo.alliedWithPlayer) { [bool]$mercInfo.alliedWithPlayer } else { $mercRep -ge 40.0 }
# Standing scales the merc foothold: allied lines field a fuller camp, wary thinner.
$mercFootholdScale = if ($mercInfo -and $null -ne $mercInfo.footholdScale) { [double]$mercInfo.footholdScale } else { 1.0 }
$mercsPresent = $objectiveKind -ne "hive_clear_or_bypass"
if ($mercsPresent -and $mercsAllied) { $enemyScale = [Math]::Round($enemyScale * 1.1, 3) }
$fortify = $enemyScale -ge 1.4

# Defenses face the player's approach; patrols defend presence zones or
# pressure the midline on destruction objectives.
$faceX = [Math]::Sign($deployCenter[0] - $enemyCenter[0]); if ($faceX -eq 0) { $faceX = 1 }
$faceZ = [Math]::Sign($deployCenter[1] - $enemyCenter[1]); if ($faceZ -eq 0) { $faceZ = 1 }
$patrolTarget = if ($presenceKind) {
  @($enemyCenter[0], $enemyCenter[1])
} else {
  # Destruction objectives: patrols screen the camp approaches (2/3 toward
  # camp from the midline) rather than camping the middle of the map.
  $midX = ($deployCenter[0] + $enemyCenter[0]) / 2.0
  $midZ = ($deployCenter[1] + $enemyCenter[1]) / 2.0
  @((($midX + 2.0 * $enemyCenter[0]) / 3.0), (($midZ + 2.0 * $enemyCenter[1]) / 3.0))
}

function Clamp01 { param([double]$V) return [Math]::Max(0.03, [Math]::Min(0.97, $V)) }

# --- Camp assembly ---------------------------------------------------------
# Each camp -> one team on its own allyteam (contractor centerpieces share the
# garrison's allyteam). Camps carry a small objective-tagged centerpiece force
# plus an untagged garrison shell. Teams carry an explicit faction tag so
# telemetry reads the world war (nullmercs/armada/cortex), not the chassis.
$roster = if ($intent.PSObject.Properties["roster"] -and $intent.roster) { $intent.roster } else { $null }
$resourceMod = if ($intent.economy -and $null -ne $intent.economy.resourceModifier) { [double]$intent.economy.resourceModifier } else { 1.0 }
$playerKit = if ($roster) { New-PlayerKitFromRoster $mapFamily $roster $resourceMod } else { New-PlayerKit $mapFamily }
$baseRecipes = [ordered]@{ legion_player_kit = @($playerKit) }
$allyTeams = @([ordered]@{ id = 0; startRect = New-StartRect $deployCenter 0.20 })
$teams = @([ordered]@{ id = 0; side = "Legion"; allyTeam = 0; base = @($deployCenter[0], $deployCenter[1]); rgb = @(0.25, 0.85, 0.35); label = "Legion Green Player"; faction = "ashwalkers" })
$forces = @([ordered]@{ id = "player_deployment"; label = "Player Deployment - $($intent.deploymentZoneId)"; teamID = 0; side = "Legion"; faction = "ashwalkers"; role = "player_anchor"; base = [ordered]@{ x = $deployCenter[0]; z = $deployCenter[1] }; recipe = "legion_player_kit" })
$ai = @()
$alliances = @()
$nextTeam = 1
$nextAllyTeam = 1

function Add-FactionCamp {
  param([string]$Side, [double[]]$Center, $CenterpieceSpecs, [string]$CenterpieceLabel, [bool]$WithEco = $true, [bool]$WithProduction = $false, [bool]$WithJammers = $false)
  # A camp is ONE faction end to end - Armada and Cortex are mortal enemies and
  # never share a team or allyteam. The centerpiece (objective) and its garrison
  # are the same side.
  $T = $FACTION[$Side]
  $teamID = $script:nextTeam; $script:nextTeam += 1
  $allyID = $script:nextAllyTeam; $script:nextAllyTeam += 1
  $script:allyTeams += [ordered]@{ id = $allyID; startRect = New-StartRect $Center 0.20 }
  $script:teams += [ordered]@{ id = $teamID; side = $Side; allyTeam = $allyID; base = @($Center[0], $Center[1]); rgb = $T.rgb; label = "$Side - $CenterpieceLabel"; faction = $Side.ToLower() }

  if ($CenterpieceSpecs) {
    $coreRecipe = "camp${teamID}_core"
    $script:baseRecipes[$coreRecipe] = @($CenterpieceSpecs)
    $script:forces += [ordered]@{ id = "camp${teamID}_objective"; label = $CenterpieceLabel; teamID = $teamID; side = $Side; faction = $Side.ToLower(); role = "objective_target"; base = [ordered]@{ x = $Center[0]; z = $Center[1] }; recipe = $coreRecipe }
  }

  $garrison = @()
  if ($WithEco) { $garrison += Ring-Eco $T $enemyScale }
  $garrison += Ring-Perimeter $T $enemyScale $faceX $faceZ
  if ($WithProduction) { $garrison += Ring-Production $T }
  if ($WithJammers) { $garrison += Ring-Jammers $T }
  $garrison += Ring-Patrol $T $enemyScale $patrolTarget[0] $patrolTarget[1]
  if ($fortify) { $garrison += Ring-Fortify $T $faceX $faceZ }
  $garrisonRecipe = "camp${teamID}_garrison"
  $script:baseRecipes[$garrisonRecipe] = @($garrison)
  $script:forces += [ordered]@{ id = "camp${teamID}_garrison"; label = "$Side garrison"; teamID = $teamID; side = $Side; faction = $Side.ToLower(); role = "garrison"; base = [ordered]@{ x = $Center[0]; z = $Center[1] }; recipe = $garrisonRecipe }

  $script:ai += [ordered]@{ name = "SimpleAI($Side $CenterpieceLabel)"; shortName = "SimpleAI"; team = $teamID; version = "<not-versioned>" }
}

function Add-RaptorCamp {
  param([double[]]$Center, [bool]$AsObjective, [string]$Label)
  $teamID = $script:nextTeam; $script:nextTeam += 1
  $allyID = $script:nextAllyTeam; $script:nextAllyTeam += 1
  $script:allyTeams += [ordered]@{ id = $allyID; startRect = New-StartRect $Center 0.18 }
  $script:teams += [ordered]@{ id = $teamID; side = "Armada"; allyTeam = $allyID; base = @($Center[0], $Center[1]); rgb = @(0.78, 0.14, 0.92); label = $Label; faction = "wild" }
  if ($AsObjective) {
    $script:baseRecipes["camp${teamID}_hives"] = @(Centerpiece-Hives $maxHazard)
    $script:forces += [ordered]@{ id = "camp${teamID}_objective"; label = $Label; teamID = $teamID; side = "Raptors"; faction = "wild"; role = "objective_target"; base = [ordered]@{ x = $Center[0]; z = $Center[1] }; recipe = "camp${teamID}_hives" }
  }
  $script:baseRecipes["camp${teamID}_swarm"] = @(Ring-RaptorGarrison $maxHazard)
  $script:forces += [ordered]@{ id = "camp${teamID}_swarm"; label = "Raptor swarm"; teamID = $teamID; side = "Raptors"; faction = "wild"; role = $(if ($AsObjective) { "garrison" } else { "wild_pressure" }); base = [ordered]@{ x = $Center[0]; z = $Center[1] }; recipe = "camp${teamID}_swarm" }
  $script:ai += [ordered]@{ name = "RaptorsDefenseAI(Verdance)"; shortName = "RaptorsAI"; team = $teamID; version = "<not-versioned>" }
}

function Add-NullMercCamp {
  param([double[]]$Center, [double]$Scale, [bool]$Allied)
  $teamID = $script:nextTeam; $script:nextTeam += 1
  $allyID = $script:nextAllyTeam; $script:nextAllyTeam += 1
  $script:allyTeams += [ordered]@{ id = $allyID; startRect = New-StartRect $Center 0.16 }
  $script:teams += [ordered]@{ id = $teamID; side = "Legion"; allyTeam = $allyID; base = @($Center[0], $Center[1]); rgb = $MERC.rgb; label = "Null Mercs foothold"; faction = "nullmercs" }
  $mfx = [Math]::Sign($enemyCenter[0] - $Center[0]); if ($mfx -eq 0) { $mfx = 1 }
  $mfz = [Math]::Sign($enemyCenter[1] - $Center[1]); if ($mfz -eq 0) { $mfz = 1 }
  $script:baseRecipes["camp${teamID}_mercs"] = @(New-MercFoothold $Scale $patrolTarget[0] $patrolTarget[1] $mfx $mfz)
  $script:forces += [ordered]@{ id = "camp${teamID}_mercs"; label = "Null Mercs foothold"; teamID = $teamID; side = "Legion"; faction = "nullmercs"; role = "merc_foothold"; base = [ordered]@{ x = $Center[0]; z = $Center[1] }; recipe = "camp${teamID}_mercs" }
  $script:ai += [ordered]@{ name = "SimpleAI(Null Mercs)"; shortName = "SimpleAI"; team = $teamID; version = "<not-versioned>" }
  if ($Allied) {
    $script:alliances += [ordered]@{ allyTeamA = 0; allyTeamB = $allyID; allied = $true }
  }
}

switch ($objectiveKind) {
  "strike_relay" {
    # The dealer relay sits in a desolate Cortex hideout: jammers everywhere.
    $T = $FACTION[$enemySide]
    $jam = $enemySide -eq "Cortex"
    Add-FactionCamp $enemySide $enemyCenter (Centerpiece-Relay $T) $description -WithEco $true -WithJammers $jam
  }
  "destroy_key_structure" {
    $T = $FACTION[$enemySide]
    Add-FactionCamp $enemySide $enemyCenter (Centerpiece-LRPC $T) $description -WithEco $true -WithProduction $true
  }
  "economy_disrupt" {
    # Synth works are a Cortex economy: the whole camp is Cortex (garrison +
    # works). Armada never protects Cortex - they are mortal enemies.
    $T = $FACTION[$enemySide]
    Add-FactionCamp $enemySide $enemyCenter (Centerpiece-EcoWorks $T $enemyScale) $description -WithEco $true
  }
  "hive_clear_or_bypass" {
    Add-RaptorCamp $enemyCenter $true $description
  }
  "choose_target_then_extract" {
    # Two rival faction camps flanking the contested center; they are on
    # separate allyteams and will pressure each other while you choose.
    $armadaCenter = @((Clamp01 ($enemyCenter[0] - 0.16)), (Clamp01 ($enemyCenter[1] - 0.05)))
    $cortexCenter = @((Clamp01 ($enemyCenter[0] + 0.16)), (Clamp01 ($enemyCenter[1] + 0.08)))
    Add-FactionCamp "Armada" $armadaCenter (Centerpiece-CommandPost $FACTION["Armada"]) "Armada command post" -WithEco $true
    Add-FactionCamp "Cortex" $cortexCenter (Centerpiece-CommandPost $FACTION["Cortex"]) "Cortex forward works" -WithEco $true
  }
  default {
    # Presence objectives (seize_lane / gate_control): a garrison holds the
    # zone - no eco, just teeth. Victory is standing where they stood.
    $T = $FACTION[$enemySide]
    Add-FactionCamp $enemySide $enemyCenter $null $description -WithEco $false
  }
}

# Null Merc foothold: a flank camp perpendicular to the deploy->target axis,
# kept clear of the player start and the wild center. Their patrols press the
# same Armada approaches the garrison screens - the war happens on the map.
if ($mercsPresent) {
  $axisX = $enemyCenter[0] - $deployCenter[0]
  $axisZ = $enemyCenter[1] - $deployCenter[1]
  $axisLen = [Math]::Sqrt($axisX * $axisX + $axisZ * $axisZ)
  if ($axisLen -lt 0.001) { $axisLen = 0.001 }
  $perpX = -$axisZ / $axisLen
  $perpZ = $axisX / $axisLen
  $midX = ($deployCenter[0] + $enemyCenter[0]) / 2.0
  $midZ = ($deployCenter[1] + $enemyCenter[1]) / 2.0
  $candidates = @(
    @((Clamp01 ($midX + 0.26 * $perpX)), (Clamp01 ($midZ + 0.26 * $perpZ))),
    @((Clamp01 ($midX - 0.26 * $perpX)), (Clamp01 ($midZ - 0.26 * $perpZ)))
  )
  $mercCenter = $candidates[0]
  $bestScore = -1.0
  foreach ($cand in $candidates) {
    $dxD = $cand[0] - $deployCenter[0]; $dzD = $cand[1] - $deployCenter[1]
    $dxW = $cand[0] - $wildCenter[0]; $dzW = $cand[1] - $wildCenter[1]
    $score = [Math]::Min([Math]::Sqrt($dxD * $dxD + $dzD * $dzD), [Math]::Sqrt($dxW * $dxW + $dzW * $dzW))
    if ($score -gt $bestScore) { $bestScore = $score; $mercCenter = $cand }
  }
  Add-NullMercCamp $mercCenter ([Math]::Max(0.5, $enemyScale * 0.75 * $mercFootholdScale)) $mercsAllied
}

# Wild pressure nest on wild-family maps whose objective is not already the hive.
if ($hasWild -and $objectiveKind -ne "hive_clear_or_bypass") {
  Add-RaptorCamp $wildCenter $false "Raptor wild pressure"
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
    alliances = $alliances
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
  nullMercs = [ordered]@{ present = [bool]$mercsPresent; allied = [bool]$mercsAllied; reputation = $mercRep }
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
