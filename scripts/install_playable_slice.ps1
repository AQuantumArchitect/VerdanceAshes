param(
  [string]$Workspace = "",
  [string]$ScenarioPath = "",
  [string]$Variant = "",
  [string]$PlayerController = "human",
  [switch]$BalanceTest,
  [int]$SimFrames = 5400,
  [switch]$ListVariants,
  [switch]$Launch,
  [switch]$Headless,
  [switch]$SaveGame,
  [string]$SaveName = "verdance_playable_ats_001",
  [string]$ExtraModOptions = "",
  [string]$DebugCommandsOverride = "",
  [string]$EngineConfigPath = "",
  [int]$TimeoutSeconds = 90
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

function Get-RequiredProperty {
  param($Object, [string]$Name, [string]$Context)
  $prop = $Object.PSObject.Properties[$Name]
  if (-not $prop) { throw "Missing '$Name' in $Context." }
  return $prop.Value
}

function Format-StartScriptNumber {
  param([double]$Value)
  return ([string]::Format([System.Globalization.CultureInfo]::InvariantCulture, "{0:0.####}", $Value))
}

function Format-StartScriptScalar {
  param($Value)
  if ($null -eq $Value) { return "" }
  if ($Value -is [bool]) {
    if ($Value) { return "1" }
    return "0"
  }
  if ($Value -is [byte] -or $Value -is [int16] -or $Value -is [int32] -or $Value -is [int64] -or $Value -is [single] -or $Value -is [double] -or $Value -is [decimal]) {
    return Format-StartScriptNumber ([double]$Value)
  }
  return [string]$Value
}

function Join-Rgb {
  param($Rgb)
  return (@($Rgb) | ForEach-Object { Format-StartScriptNumber ([double]$_) }) -join " "
}

function Render-StartScriptBlock {
  param([string]$Name, [string[]]$Lines)
  $body = ($Lines | ForEach-Object { "    $_" }) -join "`r`n"
  return @"
  [$Name]
  {
$body
  }
"@
}

function Render-OptionsBlock {
  param($Options)
  if (-not $Options) { return @() }
  $lines = @("  [OPTIONS]", "  {")
  foreach ($prop in $Options.PSObject.Properties) {
    $lines += "    $($prop.Name)=$(Format-StartScriptScalar $prop.Value);"
  }
  $lines += "  }"
  return $lines
}

function Render-ExtraModOptions {
  param([string]$Value)
  if (-not $Value) { return "" }
  $lines = @()
  $separator = if ($Value -match ';') { ';' } else { ',' }
  foreach ($pair in ($Value -split [regex]::Escape($separator))) {
    $trim = $pair.Trim()
    if (-not $trim) { continue }
    if ($trim -notmatch '=') { throw "ExtraModOptions entry must be key=value: $trim" }
    $lines += "    $trim;"
  }
  if ($lines.Count -eq 0) { return "" }
  return ($lines -join "`r`n") + "`r`n"
}

function Expand-ScenarioForces {
  param($Scenario)
  $forces = @()
  foreach ($force in @($Scenario.forces)) {
    $recipeName = [string]$force.recipe
    $recipe = Get-RequiredProperty $Scenario.baseRecipes $recipeName "baseRecipes"
    $expanded = [ordered]@{
      id = $force.id
      label = $force.label
      teamID = $force.teamID
      side = $force.side
      faction = if ($force.PSObject.Properties["faction"] -and $force.faction) { [string]$force.faction } else { "" }
      role = $force.role
      base = $force.base
      recipe = $recipeName
      groups = @(
        [ordered]@{
          id = $recipeName
          # @() guards against PowerShell unrolling single-spec recipes into a
          # bare object (which would flatten the Lua units list and spawn 0).
          units = @($recipe)
        }
      )
    }
    # Drop 4: secondary-objective forces carry their ledger identity into the
    # seed -- the gadget books groups by secondaryId and gates victory on
    # required marks. Only stamped when present (whitelist stays tight).
    if ($force.PSObject.Properties["secondaryId"] -and $force.secondaryId) {
      $expanded.secondaryId = [string]$force.secondaryId
    }
    if ($force.PSObject.Properties["required"] -and $null -ne $force.required) {
      $expanded.required = [bool]$force.required
    }
    $forces += $expanded
  }
  return @($forces)
}

function New-MissionObject {
  param($Scenario, $VariantObject, [string]$PlayerController, [int]$SimFrames)
  $variantPlayerTeam = $null
  if ($VariantObject.PSObject.Properties["playerTeamID"]) { $variantPlayerTeam = [int]$VariantObject.playerTeamID }
  $balancePlayerTeam = if ($null -ne $variantPlayerTeam) { $variantPlayerTeam } elseif ($PlayerController -eq "clean_baseline") { 0 } else { 3 }
  $mission = Clone-JsonValue $Scenario.missionBase
  $existingMissionId = if ($mission.PSObject.Properties["missionId"] -and $mission.missionId) { [string]$mission.missionId } else { "" }
  if (-not $existingMissionId) {
    Add-OrSetProperty $mission "missionId" ("va_playable_ats_" + $VariantObject.id)
  }
  Add-OrSetProperty $mission "title" ($Scenario.missionBase.title + " - " + $VariantObject.label)
  Add-OrSetProperty $mission "simulation" ([ordered]@{
    variantId = $VariantObject.id
    variantLabel = $VariantObject.label
    ai = $VariantObject.ai
  })
  Add-OrSetProperty $mission "playableSetup" ([ordered]@{
    enabled = $true
    mapId = $Scenario.map.id
    variantId = $VariantObject.id
    variantLabel = $VariantObject.label
    notes = $VariantObject.notes
    forces = Expand-ScenarioForces $Scenario
  })
  Add-OrSetProperty $mission "balance" ([ordered]@{
    playerTeamID = $balancePlayerTeam
    playerController = $PlayerController
    simFrames = $SimFrames
    target = "BARb hard/aggressive should clear or gain advantage; SimpleAI should stall."
  })
  return $mission
}

function Get-AllyTeamAllies {
  # Spring alliances are symmetric per allyteam. Compute the allied allyTeamIds
  # for one allyteam by scanning the scenario's alliances list directly
  # ({ allyTeamA, allyTeamB, allied }); avoids PS hashtable int-key quirks.
  param($Scenario, [int]$AllyTeamId)
  $allies = New-Object System.Collections.Generic.List[int]
  if (-not ($Scenario.layout.PSObject.Properties["alliances"])) { return @() }
  foreach ($pact in @($Scenario.layout.alliances)) {
    if (-not $pact.allied) { continue }
    $a = [int]$pact.allyTeamA
    $b = [int]$pact.allyTeamB
    if ($a -eq $AllyTeamId -and -not $allies.Contains($b)) { $allies.Add($b) }
    elseif ($b -eq $AllyTeamId -and -not $allies.Contains($a)) { $allies.Add($a) }
  }
  return @($allies)
}

function Render-AllyTeam {
  param($AllyTeam, $Allies = @())
  $rect = @($AllyTeam.startRect)
  # Only count real allies; drop any null/empty entries defensively.
  $allyList = @(@($Allies) | Where-Object { $_ -ne $null -and "$_" -ne "" })
  $lines = @(
    "StartRectLeft=$(Format-StartScriptNumber ([double]$rect[0]));",
    "StartRectTop=$(Format-StartScriptNumber ([double]$rect[1]));",
    "StartRectRight=$(Format-StartScriptNumber ([double]$rect[2]));",
    "StartRectBottom=$(Format-StartScriptNumber ([double]$rect[3]));",
    "NumAllies=$($allyList.Count);"
  )
  for ($i = 0; $i -lt $allyList.Count; $i++) {
    $lines += "Ally$i=$($allyList[$i]);"
  }
  return Render-StartScriptBlock ("ALLYTEAM" + $AllyTeam.id) $lines
}

function Render-Team {
  param($Team, [int]$MapSizeX, [int]$MapSizeZ)
  $base = @($Team.base)
  $lines = @(
    "Side=$($Team.side);",
    "Handicap=0;",
    "AllyTeam=$($Team.allyTeam);",
    "TeamLeader=0;",
    "StartPosX=$([int]($MapSizeX * [double]$base[0]));",
    "StartPosZ=$([int]($MapSizeZ * [double]$base[1]));",
    "RgbColor=$(Join-Rgb $Team.rgb);"
  )
  return Render-StartScriptBlock ("TEAM" + $Team.id) $lines
}

function Render-AI {
  param($Ai, [int]$Index)
  $version = if ($Ai.PSObject.Properties["version"]) { [string]$Ai.version } else { "<not-versioned>" }
  $lines = @(
    "Host=0;",
    "IsFromDemo=0;",
    "Name=$($Ai.name);",
    "ShortName=$($Ai.shortName);",
    "Team=$($Ai.team);",
    "Version=$version;"
  )
  $lines += Render-OptionsBlock $Ai.options
  return Render-StartScriptBlock ("AI" + $Index) $lines
}

function New-PlayerControllerAI {
  param([string]$Controller, [int]$Team = 3)
  switch ($Controller) {
    "human" { return $null }
    "clean_baseline" { return $null }
    "simple" {
      return [pscustomobject]@{
        name = "SimpleAI(Player Legion)"
        shortName = "SimpleDefenderAI"
        team = $Team
        version = "<not-versioned>"
      }
    }
    "barbarian_hard" {
      return [pscustomobject]@{
        name = "BARbarIAn(Player Hard)"
        shortName = "BARb"
        team = $Team
        version = "stable"
        options = [pscustomobject]@{ profile = "hard" }
      }
    }
    "barbarian_aggressive" {
      return [pscustomobject]@{
        name = "BARbarIAn(Player Aggressive)"
        shortName = "BARb"
        team = $Team
        version = "stable"
        options = [pscustomobject]@{ profile = "hard_aggressive" }
      }
    }
    default {
      throw "Unknown PlayerController '$Controller'. Use human, clean_baseline, simple, barbarian_hard, or barbarian_aggressive."
    }
  }
}

$config = Get-VerdanceConfig -Workspace $Workspace
$runRoot = Join-Path $Workspace "playable_runs"
New-Item -ItemType Directory -Force -Path $runRoot | Out-Null

if (-not $ScenarioPath) {
  $ScenarioPath = Join-Path $Workspace "data\scenarios\all_that_simmers.playable.json"
}
if (!(Test-Path $ScenarioPath)) { throw "Scenario file not found: $ScenarioPath" }

$scenario = Get-Content -Raw -LiteralPath $ScenarioPath | ConvertFrom-Json
if ($scenario.PSObject.Properties["zoneMapPath"] -and $scenario.zoneMapPath) {
  $scenarioZoneMap = $scenario.zoneMapPath
  if (-not [System.IO.Path]::IsPathRooted($scenarioZoneMap)) {
    $scenarioZoneMap = Join-Path $Workspace $scenarioZoneMap
  }
  if (!(Test-Path $scenarioZoneMap)) { throw "Scenario zone map not found: $scenarioZoneMap" }
  $config.zoneMap = $scenarioZoneMap
}
if (-not $Variant) { $Variant = [string]$scenario.defaultVariant }
$variantObject = @($scenario.variants) | Where-Object { $_.id -eq $Variant } | Select-Object -First 1
if (-not $variantObject) {
  $known = (@($scenario.variants) | ForEach-Object { $_.id }) -join ", "
  throw "Unknown scenario variant '$Variant'. Known variants: $known"
}

if ($ListVariants) {
  foreach ($item in @($scenario.variants)) {
    Write-Host "$($item.id) - $($item.label): $($item.notes)"
  }
  return
}

# The player-controller AI takes over whichever team the variant assigns the
# human player (campaign missions use team 0); legacy scenarios default to 3.
$controllerTeam = 3
if ($variantObject.PSObject.Properties["playerTeamID"]) { $controllerTeam = [int]$variantObject.playerTeamID }
$playerAi = New-PlayerControllerAI $PlayerController $controllerTeam
$mapName = [string]$scenario.map.name
$mapSizeX = [int]$scenario.map.sizeX
$mapSizeZ = [int]$scenario.map.sizeZ
$runHeadless = $Headless -or $SaveGame -or $BalanceTest
if ($SaveGame -and $TimeoutSeconds -eq 90) { $TimeoutSeconds = 240 }
$debugCommands = if ($DebugCommandsOverride) {
  $DebugCommandsOverride
} elseif ($BalanceTest) {
  "90:luarules vazones|120:luarules vastatus"
} elseif ($SaveGame) {
  "90:luarules vazones|120:luarules vastatus|180:savegame $SaveName"
} elseif ($Headless -and $ExtraModOptions -match "va_autoplay_zip=1") {
  # Zip must live long enough for the objective claim, the hold, and the
  # extract pad. The result quits the engine; 9000 is only a stuck-match stop.
  "90:luarules vazones|120:luarules vastatus|9000:quitforce"
} elseif ($Headless) {
  "90:luarules vazones|120:luarules vastatus|600:quitforce"
} else {
  "90:luarules vazones|120:luarules vastatus"
}
$balanceModOptions = if ($BalanceTest) {
@"
    va_headless_autostart=1;
    va_headless_fastwin=0;
    va_balance_export_frame=$SimFrames;
    va_balance_quit=1;
"@
} elseif ($Headless) {
@"
    va_headless_autostart=1;
    va_headless_fastwin=0;
"@
} else { "" }
$extraModOptionsText = Render-ExtraModOptions $ExtraModOptions

$mission = New-MissionObject $scenario $variantObject $PlayerController $SimFrames
$missionLua = "return " + (ConvertTo-LuaLiteral $mission 0) + "`n"

New-Item -ItemType Directory -Force -Path (Split-Path -Parent $config.seedOutbox) | Out-Null
Set-Content -Encoding ASCII -Path $config.seedOutbox -Value $missionLua
try {
  New-Item -ItemType Directory -Force -Path (Split-Path -Parent $config.seedDestination) | Out-Null
  Set-Content -Encoding ASCII -Path $config.seedDestination -Value $missionLua
  $installedToBar = $true
} catch {
  $installedToBar = $false
  Write-Warning "Could not install playable seed to BAR destination: $($_.Exception.Message)"
}
$zoneMapDestination = Install-VerdanceZoneMap -Config $config

$safeMapId = if ($scenario.map.id) { [string]$scenario.map.id } else { ($mapName -replace '[^A-Za-z0-9_-]', '_') }
$safeMapId = $safeMapId -replace '[^A-Za-z0-9_-]', '_'
$startScriptPath = Join-Path $runRoot "verdance_playable_${safeMapId}_$Variant.txt"
$allyTeamBlocks = @($scenario.layout.allyTeams) | ForEach-Object {
  $allies = Get-AllyTeamAllies $scenario ([int]$_.id)
  Render-AllyTeam $_ $allies
}
$teamBlocks = @($scenario.layout.teams) | ForEach-Object { Render-Team $_ $mapSizeX $mapSizeZ }
$aiSpecs = @($variantObject.ai)
if ($playerAi) { $aiSpecs += $playerAi }
$aiIndex = 0
$aiBlocks = foreach ($ai in @($aiSpecs)) {
  Render-AI $ai $aiIndex
  $aiIndex += 1
}
$playerSpectator = if ($playerAi -or $PlayerController -eq "clean_baseline") { 1 } else { 0 }
$variantPlayerTeam = $null
if ($variantObject.PSObject.Properties["playerTeamID"]) { $variantPlayerTeam = [int]$variantObject.playerTeamID }
$playerTeamID = if ($null -ne $variantPlayerTeam) { $variantPlayerTeam } elseif ($PlayerController -eq "clean_baseline") { 0 } else { 3 }
$numUsers = 1 + @($aiSpecs).Count

$bodyBlocks = @($allyTeamBlocks) + @($teamBlocks) + @($aiBlocks)
$blocksText = $bodyBlocks -join "`r`n`r`n"

$gameType = if ($config.PSObject.Properties["gameType"] -and $config.gameType) { [string]$config.gameType } else { 'Verdance Ashes $VERSION' }
# Rock Jungle home shelf: ~5 min raptor grace (mult≈0.85). Other maps keep ~15 min (2.5).
$raptorGraceMult = if ($safeMapId -eq "the_rock_jungle") { "0.85" } else { "2.5" }
$startScript = @"
[GAME]
{
  MapName=$mapName;
  GameType=$gameType;
  GameStartDelay=0;
  StartPosType=1;
  RecordDemo=1;
  MyPlayerName=VerdanceCommander;
  IsHost=1;
  FixedRNGSeed=1;
  NumPlayers=1;
  NumUsers=$numUsers;
  HostIP=127.0.0.1;
  HostPort=0;
  NoHelperAIs=0;

  [MODOPTIONS]
  {
    deathmode=neverend;
    experimentallegionfaction=1;
    teamffa_start_boxes_shuffle=0;
    raptor_difficulty=normal;
    raptor_graceperiodmult=$raptorGraceMult;
    raptor_spawncountmult=1.0;
    va_campaign=1;
$balanceModOptions
$extraModOptionsText
    debugcommands=$debugCommands;
  }

$blocksText

  [PLAYER0]
  {
    IsFromDemo=0;
    Name=VerdanceCommander;
    Team=$playerTeamID;
    Spectator=$playerSpectator;
    Rank=0;
  }
}
"@
Set-Content -Encoding ASCII -Path $startScriptPath -Value $startScript

$scenarioManifest = [ordered]@{
  generatedAt = (Get-Date).ToString("s")
  scenarioPath = $ScenarioPath
  variant = $Variant
  variantLabel = $variantObject.label
  map = $scenario.map
  mission = [ordered]@{
    id = $scenario.missionBase.missionId
    number = $scenario.missionBase.missionNumber
    deploymentZoneId = $scenario.missionBase.deploymentZoneId
    targetZoneId = $scenario.missionBase.objective.targetZoneId
    extractionZoneId = $scenario.missionBase.extractionZoneId
  }
  startPosType = 1
  playerTeamID = $playerTeamID
  seedOutbox = $config.seedOutbox
  seedDestination = $config.seedDestination
  startScriptPath = $startScriptPath
  ai = @($aiSpecs)
  playerController = $PlayerController
  balanceTest = [bool]$BalanceTest
  simFrames = $SimFrames
  extraModOptions = $ExtraModOptions
  saveName = if ($SaveGame) { $SaveName } else { $null }
}
$scenarioManifestPath = Join-Path $runRoot "latest_playable_variant_manifest.json"
$scenarioManifest | ConvertTo-Json -Depth 50 | Set-Content -Encoding UTF8 -Path $scenarioManifestPath

Write-Host "Installed playable mission seed to workspace: $($config.seedOutbox)"
if ($installedToBar) {
  Write-Host "Installed playable mission seed to BAR: $($config.seedDestination)"
} else {
  Write-Host "Skipped BAR destination install; workspace seed is ready: $($config.seedOutbox)"
}
Write-Host "Installed zone map to BAR: $zoneMapDestination"
Write-Host "Wrote playable startscript: $startScriptPath"
Write-Host "Variant: $Variant ($($variantObject.label))"
Write-Host "Player controller: $PlayerController"
Write-Host "Wrote variant manifest: $scenarioManifestPath"

$engineName = if ($runHeadless) { "spring-headless.exe" } else { "spring.exe" }
$engineDir = Get-BAREngineDir -Config $config -EngineName $engineName
$engine = Join-Path $engineDir $engineName
if (!(Test-Path $engine)) { throw "$engineName not found at $engine" }

if ($Launch -or $runHeadless) {
  # A map the player does not own is a FATAL content_error in PreGame -- the
  # engine exits before the mutator loads, so there is no gadget, no log line
  # of ours, and nothing on screen but a crash. Nothing else in the campaign
  # path acquires maps (BAR's auto-download is a lobby behaviour and a direct
  # start-script launch does not inherit it), so this is the only chance to
  # catch it. Fetches from BAR's own content service; cache hit is a stat call.
  # Workspace-relative, not script-relative: in a shipped dist the workspace
  # root IS the dist root, and scripts\ sits beside tools\ there too.
  $provisioner = Join-Path $Workspace "tools\map_provisioner_v1.py"
  if (Test-Path -LiteralPath $provisioner) {
    # Resolving Python is the only step allowed to fail softly. If the
    # provisioner actually runs and reports the map is unavailable, that is a
    # hard stop -- launching anyway just trades a clear message for a crash.
    $mapPy = $null
    try { $mapPy = Get-VerdancePython $Workspace }
    catch { Write-Warning "No Python for the map check; relying on the map already being installed." }
    if ($mapPy) {
      & $mapPy $provisioner --workspace $Workspace --bar-data-root $config.barDataRoot `
        --map $mapName --quiet | Out-Host
      if ($LASTEXITCODE -ne 0) {
        throw ("Could not provision the map '$mapName'. BAR exits with a fatal " +
               "content_error without it. Check your connection, or join a BAR " +
               "lobby on this map once to let the client fetch it.")
      }
    }
  }

  $args = @()
  if ($runHeadless) {
    # Headless BAR still creates a graphics context on this Windows build. These
    # flags keep the engine from scanning/rendering the player's full UI stack.
    $args += @("--safemode", "--isolation")
  }
  if ($EngineConfigPath) {
    if (!(Test-Path -LiteralPath $EngineConfigPath)) { throw "Engine config not found: $EngineConfigPath" }
    $args += @("--config", $EngineConfigPath)
  }
  $args += @("--write-dir", $config.barDataRoot, "--only-local", $startScriptPath)
  if ($runHeadless) {
    $saveDir = Join-Path $config.barDataRoot "Saves"
    $saveGamePath = Join-Path $saveDir "$SaveName.ssf"
    $saveMetaPath = Join-Path $saveDir "$SaveName.lua"
    $manifestPath = Join-Path $runRoot "latest_savegame_path.txt"
    if ($SaveGame) {
      New-Item -ItemType Directory -Force -Path $saveDir | Out-Null
      Remove-Item -Force -ErrorAction SilentlyContinue -LiteralPath $saveGamePath
      Remove-Item -Force -ErrorAction SilentlyContinue -LiteralPath $saveMetaPath
    }
    $psi = [System.Diagnostics.ProcessStartInfo]::new()
    $psi.FileName = $engine
    $psi.WorkingDirectory = $config.barDataRoot
    $psi.UseShellExecute = $false
    $psi.RedirectStandardOutput = $false
    $psi.RedirectStandardError = $false
    $psi.CreateNoWindow = $true
    function Quote-ProcessArg([string]$Arg) {
      if ($Arg -match '[\s"]') { return '"' + ($Arg.Replace('"', '\"')) + '"' }
      return $Arg
    }
    $psi.Arguments = (@($args) | ForEach-Object { Quote-ProcessArg ([string]$_) }) -join " "
    $proc = [System.Diagnostics.Process]::new()
    $proc.StartInfo = $psi
    $infologBaselineLines = if (Test-Path -LiteralPath $config.infolog) {
      @(Get-Content -LiteralPath $config.infolog -ErrorAction SilentlyContinue)
    } else { @() }
    $infologBaselineLineCount = $infologBaselineLines.Count
    $infologBaselineTail = if ($infologBaselineLineCount -gt 0) {
      [string]$infologBaselineLines[$infologBaselineLineCount - 1]
    } else { "" }
    [void]$proc.Start()
    if ($SaveGame) {
      $deadline = [DateTime]::UtcNow.AddSeconds($TimeoutSeconds)
      $lastLength = -1
      $stableTicks = 0
      $saved = $false
      while ([DateTime]::UtcNow -lt $deadline) {
        if ($proc.HasExited) { break }
        if ((Test-Path $saveGamePath) -and (Test-Path $saveMetaPath)) {
          $item = Get-Item -LiteralPath $saveGamePath
          if ($item.Length -gt 0 -and $item.Length -eq $lastLength) {
            $stableTicks += 1
          } else {
            $stableTicks = 0
            $lastLength = $item.Length
          }
          if ($stableTicks -ge 3) {
            $saved = $true
            break
          }
        }
        Start-Sleep -Seconds 1
      }
      if (-not $proc.HasExited) {
        try { $proc.Kill() } catch { }
        try { $proc.WaitForExit(10000) | Out-Null } catch { }
      }
      if (-not $saved) { throw "Expected savegame was not completed at $saveGamePath within $TimeoutSeconds seconds. Check $($config.infolog)" }
      if (!(Test-Path $saveGamePath)) { throw "Expected savegame was not created at $saveGamePath. Check $($config.infolog)" }
      if (!(Test-Path $saveMetaPath)) { Write-Warning "Save metadata was not created at $saveMetaPath. The .ssf exists, but BAR's load menu may not list it cleanly." }
      @(
        "saveName=$SaveName",
        "scenarioVariant=$Variant",
        "saveGamePath=$saveGamePath",
        "saveMetaPath=$saveMetaPath",
        "startScriptPath=$startScriptPath",
        "infolog=$($config.infolog)"
      ) | Set-Content -Encoding ASCII -Path $manifestPath
      Write-Host "Created BAR savegame: $saveGamePath"
      Write-Host "Wrote savegame manifest: $manifestPath"
    } else {
      # A completed Verdance sortie can remain in the BAR process after it has
      # emitted its result (soft continuation keeps the engine alive for a
      # human). Headless runs must harvest that result and close BAR promptly;
      # waiting for process exit turns a valid battle into a false timeout.
      $deadline = [DateTime]::UtcNow.AddSeconds($TimeoutSeconds)
      $terminalObserved = $false
      while ([DateTime]::UtcNow -lt $deadline) {
        if (Test-Path -LiteralPath $config.infolog) {
          $allLines = @(Get-Content -LiteralPath $config.infolog -ErrorAction SilentlyContinue)
          # Isolation may truncate/recreate infolog.txt at process start. In
          # that case the whole current file is this run.
          $baselineStillPresent = $infologBaselineLineCount -gt 0 `
            -and $allLines.Count -ge $infologBaselineLineCount `
            -and [string]$allLines[$infologBaselineLineCount - 1] -eq $infologBaselineTail
          $newLines = if ($baselineStillPresent -and $allLines.Count -gt $infologBaselineLineCount) {
            @($allLines | Select-Object -Skip $infologBaselineLineCount)
          } elseif ($baselineStillPresent) { @() } else { $allLines }
          if ($newLines -match "VA_RESULT_JSON_END") {
            $terminalObserved = $true
            break
          }
        }
        if ($proc.HasExited) { break }
        Start-Sleep -Seconds 1
      }
      if (-not $terminalObserved -and (Test-Path -LiteralPath $config.infolog)) {
        $allLines = @(Get-Content -LiteralPath $config.infolog -ErrorAction SilentlyContinue)
        $baselineStillPresent = $infologBaselineLineCount -gt 0 `
          -and $allLines.Count -ge $infologBaselineLineCount `
          -and [string]$allLines[$infologBaselineLineCount - 1] -eq $infologBaselineTail
        $newLines = if ($baselineStillPresent -and $allLines.Count -gt $infologBaselineLineCount) {
          @($allLines | Select-Object -Skip $infologBaselineLineCount)
        } elseif ($baselineStillPresent) { @() } else { $allLines }
        if ($newLines -match "VA_RESULT_JSON_END") { $terminalObserved = $true }
      }
      if ($terminalObserved -and -not $proc.HasExited) {
        try { $proc.Kill() } catch { }
        try { $proc.WaitForExit(10000) | Out-Null } catch { }
        Write-Host "spring-headless stopped after terminal result."
      } elseif (-not $proc.HasExited) {
        try { $proc.Kill() } catch { }
        throw "spring-headless timed out after $TimeoutSeconds seconds. Check $($config.infolog)"
      }
      Write-Host "spring-headless exit code: $($proc.ExitCode)"
      if (-not $terminalObserved) {
        throw "spring-headless exited before a terminal result (code $($proc.ExitCode)). Check $($config.infolog)"
      }
    }
  } else {
    function Quote-VisibleProcessArg([string]$Arg) {
      if ($Arg -match '[\s"]') { return '"' + ($Arg.Replace('"', '\"')) + '"' }
      return $Arg
    }
    $visibleArgLine = (@($args) | ForEach-Object { Quote-VisibleProcessArg ([string]$_) }) -join " "
    $infologBaseline = 0
    if (Test-Path $config.infolog) {
      $infologBaseline = (Get-Item -LiteralPath $config.infolog).Length
    }
    $proc = Start-Process -FilePath $engine -WorkingDirectory $config.barDataRoot -ArgumentList $visibleArgLine -PassThru
    $launchManifest = [ordered]@{
      schemaVersion = "verdance-launch/1.0"
      pid = $proc.Id
      engine = $engine
      startScriptPath = $startScriptPath
      launchedAt = (Get-Date).ToUniversalTime().ToString("o")
      infologPath = $config.infolog
      infologBaselineLength = $infologBaseline
    }
    $launchManifest | ConvertTo-Json | Set-Content -Encoding UTF8 -Path (Join-Path $runRoot "latest_launch.json")
    Write-Host "Launched visible BAR/Recoil process (pid $($proc.Id))."
  }
}
