param(
  [string]$Workspace = "",
  [string]$MapId = "",
  [double]$FloodTo = 0.85,
  [int]$FloodFrame = 900,
  [int]$TimeoutSeconds = 600,
  [switch]$KeepResult
)

# Hydrology probe: does moving the waterline actually work in the engine, and
# what does it do to an army standing in the basin?
#
# Everything else in the water cycle is measured or deterministic. This one is
# not: Spring has no synced water-level setter, so a flood is realised by
# sinking the whole heightmap, and the engine's behaviour toward units and
# buildings caught in that is not documented anywhere. This script finds out
# rather than assuming.
#
# It arms va_test_hydro_frame on the CURRENT installed mission, samples ground
# height and unit state before and after the ramp, and reports what changed.
#
# ASCII only in this file (PS 5.1 parses BOM-less UTF-8 as ANSI; an em dash
# terminates a double-quoted string mid-line).

$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
. (Join-Path $ScriptDir "_common.ps1")
$Workspace = Get-VerdanceWorkspaceRoot -Workspace $Workspace
$config = Get-VerdanceConfig -Workspace $Workspace

$engineDir = Get-BAREngineDir -Config $config -EngineName "spring-headless.exe"
$engine = Join-Path $engineDir "spring-headless.exe"
if (!(Test-Path $engine)) { throw "spring-headless.exe not found at $engine" }
$barDataRoot = [string]$config.barDataRoot

& (Join-Path $ScriptDir "install_mod_archive.ps1") -Workspace $Workspace | Out-Null

# The installed seed decides which map and which waterline we start from.
$seedPath = Join-Path $barDataRoot "games\VerdanceAshes.sdd\singleplayer\verdance_ashes\generated\va_current.lua"
if (!(Test-Path $seedPath)) { throw "No installed mission seed at $seedPath -- run build_next_mission_v1.ps1 first." }
$seedText = Get-Content -Raw -LiteralPath $seedPath

if (-not $MapId) {
  $m = [regex]::Match($seedText, 'deploymentMapId\s*=\s*"([^"]+)"')
  if ($m.Success) { $MapId = $m.Groups[1].Value }
}
if (-not $MapId) { throw "Could not determine the mission's map from the seed." }

$pool = Get-Content -Raw -LiteralPath (Join-Path $Workspace "data\map_pool\seven_maps.json") | ConvertFrom-Json
$mapEntry = $pool.maps | Where-Object { $_.id -eq $MapId }
if (-not $mapEntry) { throw "Map '$MapId' is not in the seven-map pool." }

$hydroPath = Join-Path $Workspace "data\hydrology\$MapId.hydrology.json"
if (Test-Path $hydroPath) {
  $hydro = Get-Content -Raw -LiteralPath $hydroPath | ConvertFrom-Json
  $rung = $hydro.rungs | Sort-Object { [Math]::Abs([double]$_.level - $FloodTo) } | Select-Object -First 1
  Write-Host ("Map {0}: amplitude {1}, flooding to level {2} = {3} elmos, {4}% of the map, {5}% of its metal" -f `
    $MapId, $hydro.amplitude, $FloodTo, $rung.elevation,
    [Math]::Round([double]$rung.areaSubmerged * 100, 1),
    [Math]::Round([double]$rung.metalSpotsSubmerged * 100, 1))
} else {
  Write-Warning "No measured hydrology for $MapId -- run tools/hydrology_v1.py first."
}

$runRoot = Join-Path $Workspace "headless_runs"
New-Item -ItemType Directory -Force -Path $runRoot | Out-Null
$runDir = Join-Path $runRoot ("hydrology_" + (Get-Date -Format "yyyyMMdd_HHmmss"))
New-Item -ItemType Directory -Force -Path $runDir | Out-Null

$gameType = if ($config.PSObject.Properties["gameType"] -and $config.gameType) { [string]$config.gameType } else { 'Verdance Ashes $VERSION' }
$quitFrame = $FloodFrame + 900
$startScript = @"
[GAME]
{
  MapName=$([string]$mapEntry.mapName);
  GameType=$gameType;
  GameStartDelay=0;
  StartPosType=0;
  RecordDemo=0;
  MyPlayerName=VerdanceHydro;
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
    va_campaign=1;
    va_headless=1;
    va_headless_autostart=1;
    va_headless_fastwin=0;
    va_test_hydro_frame=$FloodFrame;
    va_test_hydro_to=$FloodTo;
    debugcommands=${quitFrame}:quitforce;
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
    Name=VerdanceHydro;
    Team=0;
    Spectator=0;
    Rank=0;
  }
}
"@

$scriptPath = Join-Path $runDir "startscript.txt"
Set-Content -Encoding ASCII -Path $scriptPath -Value $startScript

Write-Host "Launching headless flood probe (frame $FloodFrame -> level $FloodTo)..."
$psi = [System.Diagnostics.ProcessStartInfo]::new()
$psi.FileName = $engine
$psi.WorkingDirectory = $barDataRoot
$psi.Arguments = ('--write-dir "{0}" --isolation --only-local "{1}"' -f $barDataRoot, $scriptPath)
$psi.UseShellExecute = $false
$psi.CreateNoWindow = $true
$proc = [System.Diagnostics.Process]::new()
$proc.StartInfo = $psi
[void]$proc.Start()
$ok = $proc.WaitForExit($TimeoutSeconds * 1000)
if (-not $ok) { try { $proc.Kill() } catch {}; Write-Warning "timed out after ${TimeoutSeconds}s" }

$isoInfolog = Join-Path $barDataRoot "infolog.txt"
$runLog = Join-Path $runDir "infolog.txt"
if (Test-Path $isoInfolog) { Copy-Item -Force -LiteralPath $isoInfolog -Destination $runLog }
elseif (Test-Path $config.infolog) { Copy-Item -Force -LiteralPath $config.infolog -Destination $runLog }

# Probes must never leave a result the campaign could advance on.
if (-not $KeepResult -and (Test-Path $config.resultInbox)) {
  Remove-Item -LiteralPath $config.resultInbox -Force -Confirm:$false
  Write-Host "removed probe-written result from inbox (phantom-advance guard)"
}

if (!(Test-Path $runLog)) { throw "No infolog captured at $runLog" }
$lines = Get-Content -LiteralPath $runLog

Write-Host ""
Write-Host "=== Hydrology probe ==="
$marks = $lines | Where-Object { $_ -match "VA_HYDRO_" }
if (-not $marks) {
  Write-Warning "No VA_HYDRO_* lines. Did the campaign gadget load? Check $runLog for VA_BRIDGE_LOADED."
} else {
  $marks | ForEach-Object { Write-Host ("  " + ($_ -replace '^\[.*?\]\[.*?\]\s*', '')) }
}

$before = $marks | Where-Object { $_ -match "VA_HYDRO_PROBE before" } | Select-Object -First 1
$after = $marks | Where-Object { $_ -match "VA_HYDRO_PROBE after" } | Select-Object -First 1
$pass = $true
if (-not $before -or -not $after) {
  Write-Warning "Probe did not sample both sides of the flood."
  $pass = $false
} else {
  $b = [regex]::Match($before, 'ground=([\d\-/]+) units=(\d+) underwater=(\d+) structures=(\d+)')
  $a = [regex]::Match($after, 'ground=([\d\-/]+) units=(\d+) underwater=(\d+) structures=(\d+)')
  if ($b.Success -and $a.Success) {
    Write-Host ""
    Write-Host ("  ground before : {0}" -f $b.Groups[1].Value)
    Write-Host ("  ground after  : {0}" -f $a.Groups[1].Value)
    Write-Host ("  units         : {0} -> {1}   (underwater {2} -> {3}, structures {4} -> {5})" -f `
      $b.Groups[2].Value, $a.Groups[2].Value, $b.Groups[3].Value, $a.Groups[3].Value,
      $b.Groups[4].Value, $a.Groups[4].Value)
    # A control run asks for the level it is already at, so the terrain SHOULD
    # stay put. Only demand movement when movement was actually requested.
    $startLevel = 0.0
    $initLine = $marks | Where-Object { $_ -match "VA_HYDRO_INIT" } | Select-Object -First 1
    if ($initLine -and $initLine -match 'level=([\d\.]+)') { $startLevel = [double]$Matches[1] }
    $expectMove = [Math]::Abs($FloodTo - $startLevel) -ge 0.02
    if ($b.Groups[1].Value -eq $a.Groups[1].Value) {
      if ($expectMove) {
        Write-Warning "The terrain did not move. AdjustHeightMap had no effect."
        $pass = $false
      } else {
        Write-Host "  (control run: no waterline change requested, terrain correctly unchanged)"
      }
    }
    $lostUnits = [int]$b.Groups[2].Value - [int]$a.Groups[2].Value
    $lostStructures = [int]$b.Groups[4].Value - [int]$a.Groups[4].Value
    if ($lostUnits -gt 0 -or $lostStructures -gt 0) {
      Write-Host ""
      Write-Host ("  NOTE: the flood cost {0} unit(s) and {1} structure(s). That is the" -f $lostUnits, $lostStructures)
      Write-Host "        number that decides whether this mechanic ships as-is."
    }
  }
}

Write-Host ""
Write-Host ("  run dir: {0}" -f $runDir)
if ($pass) { Write-Host "  RESULT: PASS -- the waterline moved and the probe sampled both sides." }
else { Write-Warning "  RESULT: FAIL -- see above." }
