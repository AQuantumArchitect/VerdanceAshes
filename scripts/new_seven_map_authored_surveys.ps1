param(
  [string]$Workspace = "$env:USERPROFILE\Documents\BAR_Verdance_Workspace"
)

$ErrorActionPreference = "Stop"
. (Join-Path (Split-Path -Parent $MyInvocation.MyCommand.Path) "_common.ps1")

function Zone {
  param(
    [string]$Id,
    [string]$Label,
    [string]$Role,
    [double]$XMin,
    [double]$XMax,
    [double]$ZMin,
    [double]$ZMax,
    [string[]]$Tags = @()
  )
  return [ordered]@{
    zoneId = $Id
    label = $Label
    role = $Role
    shape = "rect"
    bounds = [ordered]@{
      xMin = [math]::Round($XMin, 4)
      xMax = [math]::Round($XMax, 4)
      zMin = [math]::Round($ZMin, 4)
      zMax = [math]::Round($ZMax, 4)
    }
    tags = @($Tags)
  }
}

function Get-MapSize {
  param([string]$MapId)
  switch ($MapId) {
    "all_that_simmers" { return @{ x = 7168; z = 10240 } }
    "koom_valley" { return @{ x = 12288; z = 8192 } }
    "tabula" { return @{ x = 8192; z = 7168 } }
    "ancient_bastion" { return @{ x = 16384; z = 8192 } }
    "the_rock_jungle" { return @{ x = 10240; z = 8192 } }
    "eye_of_horus" { return @{ x = 6144; z = 7168 } }
    "greenest_fields" { return @{ x = 8192; z = 8192 } }
    default { return @{ x = 8192; z = 8192 } }
  }
}

function Get-AuthoredZones {
  param($Map)
  switch ($Map.id) {
    "all_that_simmers" {
      return @(
        (Zone "ATS_CENTRAL_HIVE_FLATS" "Central Hive Flats" "raptor_hazard" 0.36 0.62 0.34 0.62 @("center","wilds","raptors","hazard")),
        (Zone "ATS_NW_CANOPY_START" "Northwest Canopy Start" "legion_start" 0.00 0.30 0.00 0.28 @("start","legion","northwest","canopy")),
        (Zone "ATS_NE_ARMADA_RIDGE" "Northeast Armada Ridge" "armada_start" 0.68 1.00 0.00 0.30 @("start","armada","northeast","ridge")),
        (Zone "ATS_SE_CORTEX_BASIN" "Southeast Cortex Basin" "cortex_start" 0.62 1.00 0.64 1.00 @("start","cortex","southeast","basin")),
        (Zone "ATS_SW_ARMADA_LAGOON" "Southwest Armada Lagoon" "armada_start" 0.00 0.34 0.62 1.00 @("start","armada","southwest","swamp")),
        (Zone "ATS_NW_CENTER_APPROACH" "Northwest-to-Center Approach" "approach_lane" 0.18 0.48 0.18 0.46 @("approach","canopy","flank")),
        (Zone "ATS_SW_NE_SWAMP_LANE" "Southwest-to-Northeast Swamp Lane" "primary_lane" 0.22 0.82 0.22 0.82 @("lane","swamp","diagonal","low"))
      )
    }
    "koom_valley" {
      return @(
        (Zone "KOOM_NW_GREEN_SHELF" "Northwest Green Shelf" "legion_start" 0.00 0.26 0.00 0.28 @("start","northwest","shelf")),
        (Zone "KOOM_SE_GREEN_SHELF" "Southeast Green Shelf" "defender_start" 0.72 1.00 0.70 1.00 @("start","southeast","shelf")),
        (Zone "KOOM_NORTH_SCAR_MOUTH" "North Scar Mouth" "scar_entrance" 0.32 0.62 0.00 0.25 @("north","scar","approach")),
        (Zone "KOOM_CENTRAL_FLUID_SCAR" "Central Fluid Scar" "primary_lane" 0.34 0.66 0.20 0.82 @("center","lane","scar","low")),
        (Zone "KOOM_WEST_RIDGE_POCKET" "West Ridge Pocket" "flank_pocket" 0.00 0.34 0.24 0.76 @("west","ridge","flank")),
        (Zone "KOOM_EAST_RIDGE_POCKET" "East Ridge Pocket" "flank_pocket" 0.66 1.00 0.24 0.76 @("east","ridge","flank"))
      )
    }
    "tabula" {
      return @(
        (Zone "TAB_NW_PLATEAU" "Northwest Plateau" "legion_start" 0.00 0.28 0.00 0.28 @("start","plateau","northwest")),
        (Zone "TAB_SE_PLATEAU" "Southeast Plateau" "defender_start" 0.72 1.00 0.72 1.00 @("start","plateau","southeast")),
        (Zone "TAB_CENTRAL_BOWL" "Central Bowl" "central_objective" 0.36 0.64 0.34 0.66 @("center","bowl","low")),
        (Zone "TAB_NORTH_RIM_TERRACES" "North Rim Terraces" "rim_control" 0.20 0.80 0.00 0.28 @("north","rim","terrace")),
        (Zone "TAB_SOUTH_RIM_TERRACES" "South Rim Terraces" "rim_control" 0.20 0.80 0.72 1.00 @("south","rim","terrace")),
        (Zone "TAB_WESTERN_ROCK_GATES" "Western Rock Gates" "approach_gate" 0.00 0.32 0.24 0.76 @("west","gate","rock")),
        (Zone "TAB_EASTERN_ROCK_GATES" "Eastern Rock Gates" "approach_gate" 0.68 1.00 0.24 0.76 @("east","gate","rock"))
      )
    }
    "ancient_bastion" {
      return @(
        (Zone "AB_WESTERN_MUSTER_GROUNDS" "Western Muster Grounds" "legion_start" 0.00 0.28 0.00 0.30 @("start","west","muster")),
        (Zone "AB_CITADEL_GATEFIELD" "Citadel Gatefield" "siege_approach" 0.24 0.52 0.22 0.62 @("approach","gatefield","siege")),
        (Zone "AB_CENTRAL_KILLFIELD" "Central Killfield" "exposed_crossing" 0.46 0.66 0.18 0.76 @("center","killfield","open")),
        (Zone "AB_EASTERN_BASTION_WALL" "Eastern Bastion Wall" "fortress" 0.66 1.00 0.40 0.82 @("bastion","fortress","east","defense")),
        (Zone "AB_NORTHERN_FLANKING_LEDGE" "Northern Flanking Ledge" "flank_lane" 0.24 1.00 0.00 0.24 @("north","flank","ledge")),
        (Zone "AB_SOUTHERN_SERVICE_ROAD" "Southern Service Road" "secondary_route" 0.24 1.00 0.72 1.00 @("south","road","flank"))
      )
    }
    "the_rock_jungle" {
      return @(
        (Zone "RJ_CENTRAL_LAGOON_MAZE" "Central Lagoon Maze" "raptor_wilds" 0.26 0.70 0.24 0.74 @("center","wilds","raptors","water","maze","low")),
        (Zone "RJ_NW_JUNGLE_SHELF" "Northwest Jungle Shelf" "legion_start" 0.00 0.28 0.00 0.28 @("start","northwest","jungle")),
        (Zone "RJ_SE_JUNGLE_SHELF" "Southeast Jungle Shelf" "defender_start" 0.70 1.00 0.70 1.00 @("start","southeast","jungle")),
        (Zone "RJ_WESTERN_CAUSEWAY" "Western Causeway" "causeway" 0.00 0.24 0.22 0.82 @("west","causeway","pathing")),
        (Zone "RJ_EASTERN_CAUSEWAY" "Eastern Causeway" "causeway" 0.68 1.00 0.12 0.72 @("east","causeway","pathing")),
        (Zone "RJ_NORTHERN_ISLAND_CHAIN" "Northern Island Chain" "island_chain" 0.20 0.72 0.00 0.24 @("north","islands","water")),
        (Zone "RJ_SOUTHERN_ISLAND_CHAIN" "Southern Island Chain" "island_chain" 0.20 0.72 0.72 1.00 @("south","islands","water"))
      )
    }
    "eye_of_horus" {
      return @(
        (Zone "EOH_NW_CRATER_CAMP" "Northwest Crater Camp" "legion_start" 0.00 0.30 0.00 0.30 @("start","northwest","crater")),
        (Zone "EOH_SE_CORTEX_POCKET" "Southeast Cortex Pocket" "cortex_start" 0.68 1.00 0.68 1.00 @("start","southeast","cortex","pocket")),
        (Zone "EOH_GLASSED_CENTER" "Glassed Center" "central_objective" 0.34 0.66 0.32 0.66 @("center","open","glassed")),
        (Zone "EOH_WESTERN_DEBRIS_LANE" "Western Debris Lane" "approach_lane" 0.00 0.34 0.24 0.78 @("west","debris","lane")),
        (Zone "EOH_EASTERN_DEBRIS_LANE" "Eastern Debris Lane" "approach_lane" 0.66 1.00 0.24 0.78 @("east","debris","lane")),
        (Zone "EOH_SOUTHERN_CROSSFIRE_SHELF" "Southern Crossfire Shelf" "crossfire_route" 0.22 0.78 0.76 1.00 @("south","crossfire","shelf"))
      )
    }
    "greenest_fields" {
      return @(
        (Zone "GF_NW_GREEN_START" "Northwest Green Start" "legion_start" 0.00 0.30 0.00 0.30 @("start","northwest","green")),
        (Zone "GF_SE_SYNTH_START" "Southeast Synth Start" "defender_start" 0.68 1.00 0.68 1.00 @("start","southeast","synth","economy")),
        (Zone "GF_CENTRAL_OPEN_GRASSLAND" "Central Open Grassland" "main_field" 0.25 0.75 0.25 0.75 @("center","open","field")),
        (Zone "GF_NORTH_DESERT_EDGE" "North Desert Edge" "energy_edge" 0.60 1.00 0.00 0.34 @("north","desert","wind","solar")),
        (Zone "GF_SOUTH_DESERT_EDGE" "South Desert Edge" "energy_edge" 0.00 0.40 0.62 1.00 @("south","desert","wind","solar")),
        (Zone "GF_MIDFIELD_PROBE_CORRIDOR" "Midfield Probe Corridor" "probe_lane" 0.44 0.74 0.36 0.70 @("midfield","probe","lane"))
      )
    }
  }
}

function Get-Layout {
  param($Map)
  if ($Map.id -eq "all_that_simmers") {
    return [ordered]@{
      allyTeams = @(
        [ordered]@{ id = 0; startRect = @(0.02, 0.02, 0.48, 0.48) },
        [ordered]@{ id = 1; startRect = @(0.52, 0.02, 0.98, 0.48) },
        [ordered]@{ id = 2; startRect = @(0.52, 0.52, 0.98, 0.98) },
        [ordered]@{ id = 3; startRect = @(0.02, 0.52, 0.48, 0.98) },
        [ordered]@{ id = 4; startRect = @(0.36, 0.36, 0.64, 0.64) }
      )
      teams = @(
        [ordered]@{ id = 0; side = "Legion"; allyTeam = 0; base = @(0.14, 0.14); rgb = @(0.25, 0.85, 0.35); label = "Legion BARb Aggressive" },
        [ordered]@{ id = 1; side = "Armada"; allyTeam = 1; base = @(0.82, 0.14); rgb = @(0.25, 0.48, 1.0); label = "Armada SimpleAI Blue" },
        [ordered]@{ id = 2; side = "Cortex"; allyTeam = 2; base = @(0.82, 0.82); rgb = @(1.0, 0.20, 0.16); label = "Cortex SimpleAI Red" },
        [ordered]@{ id = 3; side = "Armada"; allyTeam = 3; base = @(0.14, 0.82); rgb = @(0.10, 0.75, 0.85); label = "Armada SimpleAI Teal" },
        [ordered]@{ id = 4; side = "Armada"; allyTeam = 4; base = @(0.50, 0.50); rgb = @(0.78, 0.14, 0.92); label = "RaptorsAI Center Wilds" }
      )
    }
  }

  if ($Map.id -eq "the_rock_jungle") {
    return [ordered]@{
      allyTeams = @(
        [ordered]@{ id = 0; startRect = @(0.02, 0.02, 0.42, 0.42) },
        [ordered]@{ id = 1; startRect = @(0.58, 0.58, 0.98, 0.98) },
        [ordered]@{ id = 2; startRect = @(0.34, 0.34, 0.66, 0.66) }
      )
      teams = @(
        [ordered]@{ id = 0; side = "Legion"; allyTeam = 0; base = @(0.16, 0.16); rgb = @(0.25, 0.85, 0.35); label = "Legion BARb Aggressive" },
        [ordered]@{ id = 1; side = "Armada"; allyTeam = 1; base = @(0.84, 0.84); rgb = @(0.25, 0.48, 1.0); label = "Armada SimpleAI" },
        [ordered]@{ id = 2; side = "Armada"; allyTeam = 2; base = @(0.50, 0.50); rgb = @(0.78, 0.14, 0.92); label = "RaptorsAI Jungle Wilds" }
      )
    }
  }

  $defenderSide = "Armada"
  if ($Map.id -eq "eye_of_horus" -or $Map.id -eq "greenest_fields") { $defenderSide = "Cortex" }
  return [ordered]@{
    allyTeams = @(
      [ordered]@{ id = 0; startRect = @(0.02, 0.02, 0.48, 0.48) },
      [ordered]@{ id = 1; startRect = @(0.52, 0.52, 0.98, 0.98) }
    )
    teams = @(
      [ordered]@{ id = 0; side = "Legion"; allyTeam = 0; base = @(0.16, 0.16); rgb = @(0.25, 0.85, 0.35); label = "Legion BARb Aggressive" },
      [ordered]@{ id = 1; side = $defenderSide; allyTeam = 1; base = @(0.84, 0.84); rgb = @(1.0, 0.20, 0.16); label = "$defenderSide SimpleAI Defender" }
    )
  }
}

function Get-Ai {
  param($Map)
  if ($Map.id -eq "all_that_simmers") {
    return @(
      [ordered]@{ name = "BARbarIAn(Legion Aggressive)"; shortName = "BARb"; team = 0; version = "stable"; options = [ordered]@{ profile = "hard_aggressive" } },
      [ordered]@{ name = "SimpleAI(Armada Blue)"; shortName = "SimpleDefenderAI"; team = 1; version = "<not-versioned>" },
      [ordered]@{ name = "SimpleAI(Cortex Red)"; shortName = "SimpleDefenderAI"; team = 2; version = "<not-versioned>" },
      [ordered]@{ name = "SimpleAI(Armada Teal)"; shortName = "SimpleDefenderAI"; team = 3; version = "<not-versioned>" },
      [ordered]@{ name = "RaptorsDefenseAI(Center Wilds)"; shortName = "RaptorsAI"; team = 4; version = "<not-versioned>" }
    )
  }
  if ($Map.id -eq "the_rock_jungle") {
    return @(
      [ordered]@{ name = "BARbarIAn(Legion Aggressive)"; shortName = "BARb"; team = 0; version = "stable"; options = [ordered]@{ profile = "hard_aggressive" } },
      [ordered]@{ name = "SimpleAI(Armada Defender)"; shortName = "SimpleDefenderAI"; team = 1; version = "<not-versioned>" },
      [ordered]@{ name = "RaptorsDefenseAI(Jungle Wilds)"; shortName = "RaptorsAI"; team = 2; version = "<not-versioned>" }
    )
  }
  return @(
    [ordered]@{ name = "BARbarIAn(Legion Aggressive)"; shortName = "BARb"; team = 0; version = "stable"; options = [ordered]@{ profile = "hard_aggressive" } },
    [ordered]@{ name = "SimpleAI(Defender)"; shortName = "SimpleDefenderAI"; team = 1; version = "<not-versioned>" }
  )
}

$poolPath = Join-Path $Workspace "data\map_pool\seven_maps.json"
$pool = Get-Content -Raw -LiteralPath $poolPath | ConvertFrom-Json
$zoneDir = Join-Path $Workspace "data\zone_maps\authored"
$scenarioDir = Join-Path $Workspace "data\scenarios\authored"
New-Item -ItemType Directory -Force -Path $zoneDir, $scenarioDir | Out-Null

$manifestMaps = @()
foreach ($map in @($pool.maps)) {
  $size = Get-MapSize $map.id
  $zoneMapPath = Join-Path $zoneDir ("{0}.authored.zone_map.json" -f $map.id)
  $scenarioPath = Join-Path $scenarioDir ("{0}.authored_baseline.json" -f $map.id)
  $zones = Get-AuthoredZones $map
  $zoneMap = [ordered]@{
    schemaVersion = "verdance-zone-map/0.2"
    mapId = $map.id
    mapName = $map.title
    coordinateSystem = "normalized_to_elmos"
    authoringStatus = "authored_from_20260623_grid_battle_survey_v0_1"
    notes = "Coarse authored Verdance zones promoted from 8x8 battle-grid survey. Rectangles may overlap; earlier zones win in the current telemetry classifier."
    zones = $zones
  }
  Save-Json $zoneMap $zoneMapPath

  $scenario = [ordered]@{
    schemaVersion = "verdance-playable-scenario/0.1"
    map = [ordered]@{ id = $map.id; name = $map.mapName; sizeX = $size.x; sizeZ = $size.z; sizeStatus = "measured_from_headless_engine" }
    zoneMapPath = ("data/zone_maps/authored/{0}.authored.zone_map.json" -f $map.id)
    defaultVariant = "authored_baseline"
    notes = "Authored-zone long-run survey scenario. Wild maps include RaptorsAI spawn(s)."
    missionBase = [ordered]@{
      schemaVersion = "0.10-playable"
      campaignId = "verdance_ashes"
      missionNumber = 1100
      pathSignal = "SURVEY_AUTHORED"
      title = ("Verdance Authored Survey: " + $map.title)
      zone = $map.title
      objective = [ordered]@{ id = ($map.id + "_authored_survey"); kind = "authored_zone_survey"; requiredFrames = 1800; description = "Headless BAR-AI authored-zone survey." }
      economy = [ordered]@{ metalIncome = 0; energyIncome = 0; buildPower = 0 }
      graph = [ordered]@{}
      reputation = [ordered]@{}
      companions = @()
    }
    baseRecipes = [ordered]@{}
    layout = Get-Layout $map
    forces = @()
    variants = @(
      [ordered]@{ id = "authored_baseline"; label = "Authored Baseline"; notes = $map.baseline; ai = Get-Ai $map }
    )
  }
  Save-Json $scenario $scenarioPath

  $manifestMaps += [ordered]@{ id = $map.id; title = $map.title; mapName = $map.mapName; zoneMapPath = $zoneMapPath; scenarioPath = $scenarioPath; zoneCount = @($zones).Count; raptors = [bool]$map.raptors; wilds = [bool]$map.wilds }
}

$manifest = [ordered]@{
  schemaVersion = "verdance-authored-zone-survey-manifest/0.1"
  generatedAt = (Get-Date).ToString("s")
  poolPath = $poolPath
  maps = $manifestMaps
}
$manifestPath = Join-Path $Workspace "reports\map_surveys\seven_map_authored_survey_manifest.json"
Save-Json $manifest $manifestPath

Write-Host "Generated seven-map authored survey files."
Write-Host "Manifest: $manifestPath"
