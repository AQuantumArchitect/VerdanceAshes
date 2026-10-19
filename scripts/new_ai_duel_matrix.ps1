<#
.SYNOPSIS
  Generates the three-way AI duel matrix: SimpleAI vs BARbarIAn(hard) vs
  BARbarIAn(hard_aggressive), across the seven-map pool.

.DESCRIPTION
  new_campaign_ai_baseline_matrix.ps1 pins one seat to BARb hard_aggressive and
  the other to SimpleAI, so it can only ever answer "how does the aggressive AI
  do against the stock one". This generator emits every pairing of the three
  seats instead, which is what a zone-flow study needs: the same map played by
  two turtles, two rushers, and every mix, so the difference in where units go is
  attributable to the AI rather than to the terrain.

  Scenarios land in data\scenarios\ai_duel\ and never touch the calibrated
  campaign_ai set. Raptor/wild teams keep RaptorsAI exactly as the baseline
  generator does.
#>
param(
  [string]$Workspace = "",
  [switch]$IncludeMirrors,
  # BARb's shipped config (engine\AI\Skirmish\BARb\stable\config\*.json) names 369
  # Armada units and 363 Cortex units and ZERO Legion units, so BARb seated on a
  # Legion team has no build chain: it puts down a few eco structures and never
  # builds an army. Every authored scenario has team 0 = Legion, which makes any
  # BARb-on-team-0 measurement a measurement of a crippled AI rather than of the
  # map. The duel matrix therefore reassigns the two duelling teams to factions
  # BARb can actually play. -KeepAuthoredFactions opts back out (useful only for
  # reproducing the Legion defect on purpose).
  [switch]$KeepAuthoredFactions,
  [string]$SeatASide = "Armada",
  [string]$SeatBSide = "Cortex"
)

$ErrorActionPreference = "Stop"
. (Join-Path (Split-Path -Parent $MyInvocation.MyCommand.Path) "_common.ps1")
$Workspace = Get-VerdanceWorkspaceRoot -Workspace $Workspace

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

# The three seats under test. shortName/version/options are exactly what
# install_playable_slice.ps1's Render-AI writes into the startscript, so these
# stay in lockstep with the hand-run -PlayerController values.
$SEATS = [ordered]@{
  simple = [ordered]@{
    key = "simple"
    label = "SimpleAI"
    shortName = "SimpleAI"
    version = "<not-versioned>"
    options = $null
  }
  bhard = [ordered]@{
    key = "bhard"
    label = "BARb hard"
    shortName = "BARb"
    version = "stable"
    options = [ordered]@{ profile = "hard" }
  }
  bagg = [ordered]@{
    key = "bagg"
    label = "BARb aggressive"
    shortName = "BARb"
    version = "stable"
    options = [ordered]@{ profile = "hard_aggressive" }
  }
}

function New-SeatAi {
  param($Seat, [int]$TeamId, [string]$Side)
  $ai = [ordered]@{
    name = "$($Seat.label)(Team $TeamId $Side)"
    shortName = $Seat.shortName
    team = $TeamId
    version = $Seat.version
  }
  if ($Seat.options) { $ai.options = $Seat.options }
  return $ai
}

function Get-PlayableTeams {
  param($Scenario)
  return @($Scenario.layout.teams | Where-Object {
    $label = if ($_.label) { [string]$_.label } else { "" }
    $side = if ($_.side) { [string]$_.side } else { "" }
    -not ($label -match 'RaptorsAI' -or $side -match 'Raptor')
  })
}

function Get-WildAis {
  param($Scenario)
  $ais = @()
  foreach ($team in @($Scenario.layout.teams)) {
    $label = if ($team.label) { [string]$team.label } else { "Team $($team.id)" }
    $side = [string]$team.side
    if ($label -match 'RaptorsAI' -or $side -match 'Raptor') {
      $ais += [ordered]@{
        name = "RaptorsDefenseAI($label)"
        shortName = "RaptorsAI"
        team = [int]$team.id
        version = "<not-versioned>"
      }
    }
  }
  return @($ais)
}

$poolPath = Join-Path $Workspace "data\map_pool\seven_maps.json"
if (!(Test-Path $poolPath)) { throw "Missing seven-map pool: $poolPath" }
$pool = Get-Content -Raw -LiteralPath $poolPath | ConvertFrom-Json

$sourceDir = Join-Path $Workspace "data\scenarios\authored"
$outDir = Join-Path $Workspace "data\scenarios\ai_duel"
New-Item -ItemType Directory -Force -Path $outDir | Out-Null

# Unordered pairings with repetition: 6 for three seats. Mirrors (swapping which
# side each seat starts on) only matter on maps whose starts are not symmetric,
# so they are opt-in.
$seatKeys = @($SEATS.Keys)
$pairings = @()
for ($i = 0; $i -lt $seatKeys.Count; $i++) {
  for ($j = $i; $j -lt $seatKeys.Count; $j++) {
    $pairings += , @($seatKeys[$i], $seatKeys[$j])
  }
}
if ($IncludeMirrors) {
  for ($i = 0; $i -lt $seatKeys.Count; $i++) {
    for ($j = $i + 1; $j -lt $seatKeys.Count; $j++) {
      $pairings += , @($seatKeys[$j], $seatKeys[$i])
    }
  }
}

$manifestMaps = @()
$manifestRuns = @()

foreach ($map in @($pool.maps)) {
  $sourcePath = Join-Path $sourceDir ("{0}.authored_baseline.json" -f $map.id)
  if (!(Test-Path $sourcePath)) { throw "Missing authored baseline scenario: $sourcePath" }
  $scenario = Get-Content -Raw -LiteralPath $sourcePath | ConvertFrom-Json
  $scenarioOutPath = Join-Path $outDir ("{0}.ai_duel.json" -f $map.id)

  $playableTeams = @(Get-PlayableTeams $scenario)
  if ($playableTeams.Count -lt 2) {
    Write-Warning "Skipping $($map.id): needs two non-wild teams, found $($playableTeams.Count)."
    continue
  }
  $teamA = $playableTeams[0]
  $teamB = $playableTeams[1]
  $wildAis = @(Get-WildAis $scenario)

  $authoredSideA = [string]$teamA.side
  $authoredSideB = [string]$teamB.side
  if (-not $KeepAuthoredFactions) {
    # Mutate the live team objects so Render-Team writes the new Side= into the
    # startscript. Only the two duelling teams move; wild/raptor teams are left
    # exactly as authored.
    $teamA.side = $SeatASide
    $teamB.side = $SeatBSide
  }

  Add-OrSetProperty $scenario "schemaVersion" "verdance-ai-duel-scenario/0.1"
  Add-OrSetProperty $scenario "notes" "Three-way AI duel matrix: SimpleAI / BARb hard / BARb hard_aggressive in every pairing. Wild teams keep RaptorsAI."

  $missionBase = Clone-JsonValue $scenario.missionBase
  Add-OrSetProperty $missionBase "pathSignal" "AI_DUEL_MATRIX"
  Add-OrSetProperty $missionBase "title" ("Verdance AI Duel: " + $map.title)
  # The campaign's Tenebrium gate applies to playerTeamID only: AllowUnitCreation
  # refuses any build-power unit when the bank cannot cover it, and the BP ceiling
  # is 150 * (bank + invested), so a bank of 0 means a hard cap of 0. No scenario
  # set in this repo sets a bank, which silently prevents the "player" team from
  # ever building a constructor, factory or nano while its opponents build freely.
  # A duel is not a campaign sortie and must not carry that economy gate at all.
  Add-OrSetProperty $missionBase "tenebrium" ([ordered]@{
    bank = 2000
    note = "AI duel: unconstrained build power. Not a campaign economy."
  })
  $scenario.missionBase = $missionBase

  $variants = @()
  foreach ($pair in $pairings) {
    $aKey = $pair[0]
    $bKey = $pair[1]
    $seatA = $SEATS[$aKey]
    $seatB = $SEATS[$bKey]
    $variantId = "duel_${aKey}_vs_${bKey}"

    $ai = @()
    $ai += New-SeatAi -Seat $seatA -TeamId ([int]$teamA.id) -Side ([string]$teamA.side)
    $ai += New-SeatAi -Seat $seatB -TeamId ([int]$teamB.id) -Side ([string]$teamB.side)
    # all_that_simmers has five playable teams and the_rock_jungle three. A team
    # with no AI and no player still gets a start position and a commander, so
    # leaving them empty parks free value on the map and skews every ratio. Fill
    # them with SimpleAI, which is what the campaign_ai matrix uses for NPCs, so
    # the filler is identical across all six pairings and cancels out.
    foreach ($extra in @($playableTeams | Select-Object -Skip 2)) {
      $ai += [ordered]@{
        name = "SimpleAI(NPC Team $($extra.id) $($extra.side))"
        shortName = "SimpleAI"
        team = [int]$extra.id
        version = "<not-versioned>"
      }
    }
    $ai += $wildAis

    # playerTeamID is what the gadget clamps to and what telemetry calls
    # "playerValue". Team A is always the reported side, so a row in the results
    # table reads "seat A's value vs seat B's value".
    $variants += [ordered]@{
      id = $variantId
      label = "$($seatA.label) (T$($teamA.id) $($teamA.side)) vs $($seatB.label) (T$($teamB.id) $($teamB.side))"
      playerTeamID = [int]$teamA.id
      playerSide = [string]$teamA.side
      playerStartLabel = if ($teamA.label) { [string]$teamA.label } else { "Team $($teamA.id)" }
      seatA = $aKey
      seatB = $bKey
      seatALabel = $seatA.label
      seatBLabel = $seatB.label
      mirrored = [bool]($aKey -ne $bKey -and $pairings.IndexOf($pair) -ge 6)
      notes = "Team $($teamA.id) = $($seatA.label); team $($teamB.id) = $($seatB.label)."
      ai = @($ai)
    }

    $manifestRuns += [ordered]@{
      id = "$($map.id)::$variantId"
      mapId = $map.id
      mapTitle = $map.title
      scenarioPath = $scenarioOutPath
      variant = $variantId
      seatA = $aKey
      seatB = $bKey
      seatALabel = $seatA.label
      seatBLabel = $seatB.label
      playerTeamID = [int]$teamA.id
      enemyTeamID = [int]$teamB.id
      seatASide = [string]$teamA.side
      seatBSide = [string]$teamB.side
      authoredSideA = $authoredSideA
      authoredSideB = $authoredSideB
      factionsForced = [bool](-not $KeepAuthoredFactions)
      symmetric = [bool]($aKey -eq $bKey)
      wilds = [bool]$map.wilds
      raptors = [bool]$map.raptors
    }
  }

  Add-OrSetProperty $scenario "defaultVariant" ([string]$variants[0].id)
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
  schemaVersion = "verdance-ai-duel-matrix/0.1"
  generatedAt = (Get-Date).ToString("s")
  seats = $SEATS
  includeMirrors = [bool]$IncludeMirrors
  pairingCount = @($pairings).Count
  maps = $manifestMaps
  runs = $manifestRuns
}
$manifestPath = Join-Path $Workspace "reports\map_surveys\ai_duel_matrix_manifest.json"
New-Item -ItemType Directory -Force -Path (Split-Path -Parent $manifestPath) | Out-Null
Save-Json $manifest $manifestPath

Write-Host "Generated AI duel scenarios."
Write-Host "Scenario dir: $outDir"
Write-Host "Maps: $(@($manifestMaps).Count)  Pairings/map: $(@($pairings).Count)  Runs: $(@($manifestRuns).Count)"
Write-Host "Manifest: $manifestPath"
