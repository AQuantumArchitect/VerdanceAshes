param(
  [string]$Workspace = "$env:USERPROFILE\Documents\BAR_Verdance_Workspace",
  [string]$NpcAiShortName = "SimpleAI"
)

$ErrorActionPreference = "Stop"
. (Join-Path (Split-Path -Parent $MyInvocation.MyCommand.Path) "_common.ps1")

function Clone-JsonValue {
  param($Value)
  return ($Value | ConvertTo-Json -Depth 100 | ConvertFrom-Json)
}

function Add-OrSetProperty {
  param($Object, [string]$Name, $Value)
  if ($Object.PSObject.Properties[$Name]) {
    $Object.$Name = $Value
  } else {
    $Object | Add-Member -NotePropertyName $Name -NotePropertyValue $Value
  }
}

function Get-AiForVariant {
  param($Scenario, [int]$PlayerTeamId, [string]$VariantKind, [string]$NpcShortName)
  $ais = @()
  foreach ($team in @($Scenario.layout.teams)) {
    $teamId = [int]$team.id
    $side = [string]$team.side
    $label = if ($team.label) { [string]$team.label } else { "Team $teamId" }

    if ($label -match 'RaptorsAI' -or $side -match 'Raptor') {
      $ais += [ordered]@{
        name = "RaptorsDefenseAI($label)"
        shortName = "RaptorsAI"
        team = $teamId
        version = "<not-versioned>"
      }
      continue
    }

    if ($teamId -eq $PlayerTeamId) {
      $ais += [ordered]@{
        name = "BARbarIAn(Player $side Team $teamId Aggressive)"
        shortName = "BARb"
        team = $teamId
        version = "stable"
        options = [ordered]@{ profile = "hard_aggressive" }
      }
    } else {
      $shortName = $NpcShortName
      if ($VariantKind -eq "turtle_hold") { $shortName = "SimpleDefenderAI" }
      $ais += [ordered]@{
        name = "$shortName(NPC $side Team $teamId)"
        shortName = $shortName
        team = $teamId
        version = "<not-versioned>"
      }
    }
  }
  return @($ais)
}

function Get-PlayableTeams {
  param($Scenario)
  return @($Scenario.layout.teams | Where-Object {
    $label = if ($_.label) { [string]$_.label } else { "" }
    $side = if ($_.side) { [string]$_.side } else { "" }
    -not ($label -match 'RaptorsAI' -or $side -match 'Raptor')
  })
}

$poolPath = Join-Path $Workspace "data\map_pool\seven_maps.json"
if (!(Test-Path $poolPath)) { throw "Missing seven-map pool: $poolPath" }
$pool = Get-Content -Raw -LiteralPath $poolPath | ConvertFrom-Json

$sourceDir = Join-Path $Workspace "data\scenarios\authored"
$outDir = Join-Path $Workspace "data\scenarios\campaign_ai"
New-Item -ItemType Directory -Force -Path $outDir | Out-Null

$manifestMaps = @()
$manifestRuns = @()

foreach ($map in @($pool.maps)) {
  $sourcePath = Join-Path $sourceDir ("{0}.authored_baseline.json" -f $map.id)
  if (!(Test-Path $sourcePath)) { throw "Missing authored baseline scenario: $sourcePath" }
  $scenario = Get-Content -Raw -LiteralPath $sourcePath | ConvertFrom-Json
  $scenarioOutPath = Join-Path $outDir ("{0}.campaign_ai.json" -f $map.id)

  Add-OrSetProperty $scenario "schemaVersion" "verdance-campaign-ai-scenario/0.1"
  Add-OrSetProperty $scenario "defaultVariant" "player_team_0_aggressive"
  Add-OrSetProperty $scenario "notes" "Campaign AI baseline matrix. Player slot is simulated by BARbarIAn hard_aggressive; NPCs default to SimpleAI; raptor/wild teams remain RaptorsAI."

  $missionBase = Clone-JsonValue $scenario.missionBase
  Add-OrSetProperty $missionBase "pathSignal" "CAMPAIGN_AI_BASELINE"
  Add-OrSetProperty $missionBase "title" ("Verdance Campaign AI Baseline: " + $map.title)
  $scenario.missionBase = $missionBase

  $variants = @()
  $playableTeams = Get-PlayableTeams $scenario
  foreach ($team in @($playableTeams)) {
    $teamId = [int]$team.id
    $side = [string]$team.side
    $label = if ($team.label) { [string]$team.label } else { "Team $teamId" }
    $variantId = "player_team_${teamId}_aggressive"
    $variants += [ordered]@{
      id = $variantId
      label = "Player-as-$side Team $teamId Aggressive"
      playerTeamID = $teamId
      playerSide = $side
      playerStartLabel = $label
      npcAiShortName = $NpcAiShortName
      notes = "Simulates a human commander taking over $label with BARbarIAn hard_aggressive; all other non-wild teams use $NpcAiShortName."
      ai = Get-AiForVariant -Scenario $scenario -PlayerTeamId $teamId -VariantKind "mobile_simple" -NpcShortName $NpcAiShortName
    }
    $manifestRuns += [ordered]@{
      id = "$($map.id)::$variantId"
      mapId = $map.id
      mapTitle = $map.title
      scenarioPath = $scenarioOutPath
      variant = $variantId
      playerTeamID = $teamId
      playerSide = $side
      playerStartLabel = $label
      priority = if ($teamId -eq 0) { "baseline" } else { "variant" }
      wilds = [bool]$map.wilds
      raptors = [bool]$map.raptors
    }
  }

  $scenario.variants = @($variants)
  Save-Json $scenario $scenarioOutPath

  $manifestMaps += [ordered]@{
    id = $map.id
    title = $map.title
    mapName = $map.mapName
    scenarioPath = $scenarioOutPath
    zoneMapPath = $scenario.zoneMapPath
    variantCount = @($variants).Count
    wilds = [bool]$map.wilds
    raptors = [bool]$map.raptors
  }
}

$manifest = [ordered]@{
  schemaVersion = "verdance-campaign-ai-matrix/0.1"
  generatedAt = (Get-Date).ToString("s")
  npcAiShortName = $NpcAiShortName
  milestonePolicy = "Run every scenario to 1,2,3,5,8,13,21 minutes; extend unresolved/suspicious/wild cases to 34,55,89."
  maps = $manifestMaps
  runs = $manifestRuns
}
$manifestPath = Join-Path $Workspace "reports\map_surveys\campaign_ai_matrix_manifest.json"
Save-Json $manifest $manifestPath

Write-Host "Generated campaign AI baseline scenarios."
Write-Host "Scenario dir: $outDir"
Write-Host "Manifest: $manifestPath"
