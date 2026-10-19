param(
  [string]$Workspace = "",
  [ValidateSet("terrain", "behaviour", "both")]
  [string]$Mode = "both",
  # Arrays, not strings: PowerShell parses an unquoted -MapIds a,b as an ARRAY
  # literal, and binding that to [string] joins it with a space, so the comma
  # split finds nothing and the run silently does no maps. [string[]] accepts
  # both "a,b" and a,b.
  [string[]]$MapIds = @(),
  [string[]]$Configs = @(),
  [string]$PlanPath = "",
  [switch]$RegeneratePlan,
  [switch]$Resume,
  [switch]$DryRun,
  [int]$GridRes = 0,
  [int]$MaxRuns = 0,
  [int]$TerrainTimeoutSeconds = 420
)

# Zone cartography survey runner.
#
#   terrain   -- one ~40s headless load per map; game_verdance_cartography.lua
#                dumps the engine's own view of the map (height, slope, water,
#                buildability, metal, move-class speeds, feature mass, metal
#                spots, authored start positions) and quits.
#   behaviour -- AI-vs-AI matches from data/cartography/run_plan.json, one BAR
#                process at a time, position-binned into the same grid and
#                emitted at milestone frames.
#
# Both land as JSON under data/terrain/ and data/behavior/ via
# tools/parse_cartography_log_v1.py. Re-runnable: -Resume skips any run whose
# output already exists, so an overnight batch that ends early just continues.
#
# ASCII only in this file (PS 5.1 parses BOM-less UTF-8 as ANSI; an em dash
# terminates a double-quoted string mid-line).

$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
. (Join-Path $ScriptDir "_common.ps1")
$Workspace = Get-VerdanceWorkspaceRoot -Workspace $Workspace
$config = Get-VerdanceConfig -Workspace $Workspace
$python = Get-VerdancePython -Workspace $Workspace

$engineDir = Get-BAREngineDir -Config $config -EngineName "spring-headless.exe"
$engine = Join-Path $engineDir "spring-headless.exe"
if (!(Test-Path $engine)) { throw "spring-headless.exe not found at $engine" }
$gameType = if ($config.PSObject.Properties["gameType"] -and $config.gameType) { [string]$config.gameType } else { 'Verdance Ashes $VERSION' }
$barDataRoot = [string]$config.barDataRoot

# The cartography gadget ships inside the mutator, so the mutator must be the
# installed junction (a stale copy silently runs old Lua). Skipped under
# -DryRun so plan inspection never touches the BAR install.
if (-not $DryRun) {
  & (Join-Path $ScriptDir "install_mod_archive.ps1") -Workspace $Workspace | Out-Null
}

$poolPath = Join-Path $Workspace "data\map_pool\seven_maps.json"
$pool = Get-Content -Raw -LiteralPath $poolPath | ConvertFrom-Json
$mapFilter = @()
if ($MapIds) { $mapFilter = @($MapIds -split ',' | ForEach-Object { $_.Trim() } | Where-Object { $_ }) }
$configFilter = @()
if ($Configs) { $configFilter = @($Configs -split ',' | ForEach-Object { $_.Trim() } | Where-Object { $_ }) }

$runRoot = Join-Path $Workspace "headless_runs"
New-Item -ItemType Directory -Force -Path $runRoot | Out-Null
$batchStamp = Get-Date -Format "yyyyMMdd_HHmmss"
$batchDir = Join-Path $runRoot "cartography_$batchStamp"
New-Item -ItemType Directory -Force -Path $batchDir | Out-Null

$results = New-Object System.Collections.Generic.List[object]

function Quote-ProcessArg([string]$Arg) {
  if ($Arg -match '[\s"]') { return '"' + ($Arg.Replace('"', '\"')) + '"' }
  return $Arg
}

function Invoke-CartographyRun {
  param(
    [string]$Label,
    [string]$StartScript,
    [string]$RunDir,
    [int]$TimeoutSeconds
  )
  New-Item -ItemType Directory -Force -Path $RunDir | Out-Null
  $scriptPath = Join-Path $RunDir "startscript.txt"
  Set-Content -Encoding ASCII -Path $scriptPath -Value $StartScript

  if ($DryRun) {
    Write-Host "  [dry run] would launch: $Label"
    return $null
  }

  $inboxExisted = Test-Path $config.resultInbox
  $inboxStamp = if ($inboxExisted) { (Get-Item -LiteralPath $config.resultInbox).LastWriteTimeUtc } else { $null }

  $argLine = (@("--write-dir", $barDataRoot, "--isolation", "--only-local", $scriptPath) |
    ForEach-Object { Quote-ProcessArg ([string]$_) }) -join " "
  $psi = [System.Diagnostics.ProcessStartInfo]::new()
  $psi.FileName = $engine
  $psi.WorkingDirectory = $barDataRoot
  $psi.Arguments = $argLine
  $psi.UseShellExecute = $false
  $psi.CreateNoWindow = $true
  $proc = [System.Diagnostics.Process]::new()
  $proc.StartInfo = $psi
  $started = Get-Date
  [void]$proc.Start()
  $ok = $proc.WaitForExit($TimeoutSeconds * 1000)
  if (-not $ok) {
    try { $proc.Kill() } catch {}
    Write-Warning "  timed out after ${TimeoutSeconds}s: $Label"
  }
  $elapsed = [int]((Get-Date) - $started).TotalSeconds

  $isoInfolog = Join-Path $barDataRoot "infolog.txt"
  $runLog = Join-Path $RunDir "infolog.txt"
  if (Test-Path $isoInfolog) {
    Copy-Item -Force -LiteralPath $isoInfolog -Destination $runLog
  } elseif (Test-Path $config.infolog) {
    Copy-Item -Force -LiteralPath $config.infolog -Destination $runLog
  }

  # Probe runs must never leave a result the campaign could advance on.
  if (Test-Path $config.resultInbox) {
    $newStamp = (Get-Item -LiteralPath $config.resultInbox).LastWriteTimeUtc
    if (-not $inboxExisted -or $newStamp -ne $inboxStamp) {
      Remove-Item -LiteralPath $config.resultInbox -Force -Confirm:$false
      Write-Host "  removed probe-written result from inbox (phantom-advance guard)"
    }
  }

  return [pscustomobject]@{
    timedOut = (-not $ok)
    exitCode = if ($ok) { $proc.ExitCode } else { -1 }
    elapsedSeconds = $elapsed
    infolog = $runLog
  }
}

function New-TerrainStartScript {
  param([string]$MapName, [string]$MapId, [int]$Res)
  return @"
[GAME]
{
  MapName=$MapName;
  GameType=$gameType;
  GameStartDelay=0;
  StartPosType=0;
  RecordDemo=0;
  MyPlayerName=VerdanceCartographer;
  IsHost=1;
  FixedRNGSeed=1;
  NumPlayers=1;
  NumUsers=1;
  HostIP=127.0.0.1;
  HostPort=0;
  NoHelperAIs=0;

  [MODOPTIONS]
  {
    deathmode=neverend;
    experimentallegionfaction=1;
    va_campaign=0;
    va_cartography=1;
    va_cart_terrain_only=1;
    va_cart_res=$Res;
    va_cart_mapid=$MapId;
    va_cart_speed=0;
    debugcommands=900:quitforce;
  }

  [ALLYTEAM0]
  {
    NumAllies=0;
  }

  [TEAM0]
  {
    Side=Armada;
    Handicap=0;
    AllyTeam=0;
    TeamLeader=0;
  }

  [PLAYER0]
  {
    Name=VerdanceCartographer;
    Team=0;
    Spectator=0;
    Rank=0;
  }
}
"@
}

function New-BehaviourStartScript {
  param($Run)
  $teams = @($Run.teams)
  $allyBlocks = New-Object System.Collections.Generic.List[string]
  $teamBlocks = New-Object System.Collections.Generic.List[string]
  $aiBlocks = New-Object System.Collections.Generic.List[string]

  $mapSize = Get-CartographyMapSize -MapId ([string]$Run.mapId)
  for ($i = 0; $i -lt $teams.Count; $i++) {
    $entry = $teams[$i]
    $posX = [double]$entry.x
    $posZ = [double]$entry.z
    $normX = [Math]::Max(0.0, [Math]::Min(1.0, $posX / [double]$mapSize.x))
    $normZ = [Math]::Max(0.0, [Math]::Min(1.0, $posZ / [double]$mapSize.z))
    $rectLeft = [string]::Format([System.Globalization.CultureInfo]::InvariantCulture, "{0:0.####}", [Math]::Max(0.0, $normX - 0.06))
    $rectTop = [string]::Format([System.Globalization.CultureInfo]::InvariantCulture, "{0:0.####}", [Math]::Max(0.0, $normZ - 0.06))
    $rectRight = [string]::Format([System.Globalization.CultureInfo]::InvariantCulture, "{0:0.####}", [Math]::Min(1.0, $normX + 0.06))
    $rectBottom = [string]::Format([System.Globalization.CultureInfo]::InvariantCulture, "{0:0.####}", [Math]::Min(1.0, $normZ + 0.06))

    $allyBlocks.Add(@"
  [ALLYTEAM$i]
  {
    NumAllies=0;
    StartRectLeft=$rectLeft;
    StartRectTop=$rectTop;
    StartRectRight=$rectRight;
    StartRectBottom=$rectBottom;
  }
"@) | Out-Null

    $rgb = switch ([string]$entry.side) {
      "Cortex" { "1.0 0.2 0.16" }
      "Legion" { "0.25 0.85 0.35" }
      default  { "0.25 0.48 1.0" }
    }
    $teamBlocks.Add(@"
  [TEAM$i]
  {
    Side=$([string]$entry.side);
    Handicap=0;
    AllyTeam=$([int]$entry.allyTeam);
    TeamLeader=0;
    StartPosX=$([int][Math]::Round($posX));
    StartPosZ=$([int][Math]::Round($posZ));
    RgbColor=$rgb;
  }
"@) | Out-Null

    $aiShort = [string]$entry.ai.shortName
    $aiVersion = if ($entry.ai.PSObject.Properties["version"] -and $entry.ai.version) { [string]$entry.ai.version } else { "stable" }
    $optionBlock = ""
    if ($entry.ai.PSObject.Properties["profile"] -and $entry.ai.profile) {
      $optionBlock = @"

      [OPTIONS]
      {
        profile=$([string]$entry.ai.profile);
      }
"@
    }
    $aiBlocks.Add(@"
  [AI$i]
  {
    Host=0;
    IsFromDemo=0;
    Name=$aiShort-$i($([string]$entry.side));
    ShortName=$aiShort;
    Team=$i;
    Version=$aiVersion;$optionBlock
  }
"@) | Out-Null
  }

  $extraOptions = ""
  if ($Run.PSObject.Properties["modOptions"] -and $Run.modOptions) {
    foreach ($prop in $Run.modOptions.PSObject.Properties) {
      $extraOptions += "    $($prop.Name)=$($prop.Value);`r`n"
    }
  }
  $milestones = (@($Run.milestoneFrames) | ForEach-Object { [int]$_ }) -join ","
  $quitFrame = [int]$Run.maxFrame + 300
  $configTag = "$([string]$Run.configId)_$([string]$Run.variant)"

  return @"
[GAME]
{
  MapName=$([string]$Run.mapName);
  GameType=$gameType;
  GameStartDelay=0;
  StartPosType=3;
  RecordDemo=0;
  MyPlayerName=VerdanceCartographer;
  IsHost=1;
  FixedRNGSeed=1;
  NumPlayers=1;
  NumUsers=$($teams.Count + 1);
  HostIP=127.0.0.1;
  HostPort=0;
  NoHelperAIs=0;

  [MODOPTIONS]
  {
    deathmode=neverend;
    experimentallegionfaction=1;
    teamffa_start_boxes_shuffle=0;
    va_campaign=0;
    va_cartography=1;
    va_cart_res=$([int]$Run.gridRes);
    va_cart_mapid=$([string]$Run.mapId);
    va_cart_config=$configTag;
    va_cart_sample_frames=$([int]$Run.sampleFrames);
    va_cart_milestones=$milestones;
    va_cart_quit=1;
    va_cart_speed=20;
$extraOptions    debugcommands=${quitFrame}:quitforce;
  }

$($allyBlocks -join "`r`n")
$($teamBlocks -join "`r`n")
$($aiBlocks -join "`r`n")

  [PLAYER0]
  {
    Name=VerdanceCartographer;
    Team=0;
    Spectator=1;
    Rank=0;
  }
}
"@
}

function Get-CartographyMapSize {
  param([string]$MapId)
  # Prefer the measured terrain raster; fall back to the engine-measured table.
  $terrainPath = Join-Path $Workspace "data\terrain\$MapId.terrain.json"
  if (Test-Path $terrainPath) {
    $raster = Get-Content -Raw -LiteralPath $terrainPath | ConvertFrom-Json
    if ($raster.size -and [double]$raster.size.x -gt 0) {
      return @{ x = [double]$raster.size.x; z = [double]$raster.size.z }
    }
  }
  switch ($MapId) {
    "all_that_simmers" { return @{ x = 7168.0; z = 10240.0 } }
    "koom_valley" { return @{ x = 12288.0; z = 8192.0 } }
    "tabula" { return @{ x = 8192.0; z = 7168.0 } }
    "ancient_bastion" { return @{ x = 16384.0; z = 8192.0 } }
    "the_rock_jungle" { return @{ x = 10240.0; z = 8192.0 } }
    "eye_of_horus" { return @{ x = 6144.0; z = 7168.0 } }
    "greenest_fields" { return @{ x = 8192.0; z = 8192.0 } }
    default { return @{ x = 8192.0; z = 8192.0 } }
  }
}

#-------------------------------------------------------------------------------
# Terrain pass
#-------------------------------------------------------------------------------
if ($Mode -eq "terrain" -or $Mode -eq "both") {
  $res = if ($GridRes -gt 0) { $GridRes } else { 48 }
  Write-Host "=== Terrain pass (res=$res) ==="
  foreach ($mapEntry in @($pool.maps)) {
    $mapId = [string]$mapEntry.id
    if ($mapFilter.Count -gt 0 -and ($mapFilter -notcontains $mapId)) { continue }
    $terrainOut = Join-Path $Workspace "data\terrain\$mapId.terrain.json"
    if ($Resume -and (Test-Path $terrainOut)) {
      Write-Host "  skip (resume): $mapId"
      continue
    }
    Write-Host "  $mapId ($([string]$mapEntry.mapName))"
    $startScript = New-TerrainStartScript -MapName ([string]$mapEntry.mapName) -MapId $mapId -Res $res
    $runDir = Join-Path $batchDir "terrain_$mapId"
    $outcome = Invoke-CartographyRun -Label "terrain:$mapId" -StartScript $startScript -RunDir $runDir -TimeoutSeconds $TerrainTimeoutSeconds
    if ($null -eq $outcome) { continue }

    $parsed = & $python (Join-Path $Workspace "tools\parse_cartography_log_v1.py") `
      --infolog $outcome.infolog --workspace $Workspace --map-id $mapId 2>&1
    $parsed | ForEach-Object { Write-Host "    $_" }
    $results.Add([pscustomobject]@{
      kind = "terrain"; id = $mapId; seconds = $outcome.elapsedSeconds
      ok = (Test-Path $terrainOut); timedOut = $outcome.timedOut
    }) | Out-Null
  }
}

#-------------------------------------------------------------------------------
# Behaviour pass
#-------------------------------------------------------------------------------
if ($Mode -eq "behaviour" -or $Mode -eq "both") {
  $planFile = if ($PlanPath) { $PlanPath } else { Join-Path $Workspace "data\cartography\run_plan.json" }
  if ($RegeneratePlan -or !(Test-Path $planFile)) {
    Write-Host "Building run plan..."
    & $python (Join-Path $Workspace "tools\plan_cartography_runs_v1.py") --workspace $Workspace --out $planFile |
      ForEach-Object { Write-Host "  $_" }
  }
  $plan = Get-Content -Raw -LiteralPath $planFile | ConvertFrom-Json
  Write-Host "=== Behaviour pass ($($plan.runs.Count) planned runs) ==="

  $launched = 0
  foreach ($run in @($plan.runs)) {
    $mapId = [string]$run.mapId
    $configId = [string]$run.configId
    if ($mapFilter.Count -gt 0 -and ($mapFilter -notcontains $mapId)) { continue }
    if ($configFilter.Count -gt 0 -and ($configFilter -notcontains $configId)) { continue }
    if ($MaxRuns -gt 0 -and $launched -ge $MaxRuns) { break }

    $configTag = "${configId}_$([string]$run.variant)"
    $rasterOut = Join-Path $Workspace "data\behavior\$mapId\$configTag.raster.json"
    if ($Resume -and (Test-Path $rasterOut)) {
      Write-Host "  skip (resume): $mapId/$configTag"
      continue
    }

    $timeout = [int]([int]$run.simMinutes * 60 * 2.5) + 420
    Write-Host "  $mapId/$configTag  teams=$(@($run.teams).Count) sim=$([int]$run.simMinutes)min timeout=${timeout}s"
    $startScript = New-BehaviourStartScript -Run $run
    $runDir = Join-Path $batchDir "$mapId`_$configTag"
    $outcome = Invoke-CartographyRun -Label "$mapId/$configTag" -StartScript $startScript -RunDir $runDir -TimeoutSeconds $timeout
    $launched++
    if ($null -eq $outcome) { continue }

    $parsed = & $python (Join-Path $Workspace "tools\parse_cartography_log_v1.py") `
      --infolog $outcome.infolog --workspace $Workspace --map-id $mapId --config-id $configTag 2>&1
    $parsed | ForEach-Object { Write-Host "    $_" }
    $results.Add([pscustomobject]@{
      kind = "behaviour"; id = "$mapId/$configTag"; seconds = $outcome.elapsedSeconds
      ok = (Test-Path $rasterOut); timedOut = $outcome.timedOut
    }) | Out-Null
  }
}

#-------------------------------------------------------------------------------
Write-Host ""
Write-Host "=== Cartography survey summary ==="
$failed = @()
foreach ($entry in $results) {
  $mark = if ($entry.ok) { "OK  " } else { $failed += $entry.id; "FAIL" }
  Write-Host ("  {0} {1,-40} {2,5}s{3}" -f $mark, $entry.id, $entry.seconds, $(if ($entry.timedOut) { " (timeout)" } else { "" }))
}
Write-Host "  batch dir: $batchDir"
if ($failed.Count -gt 0) {
  Write-Warning "Runs without output: $($failed -join ', ')"
}
