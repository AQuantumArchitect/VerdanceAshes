param(
  [string]$Workspace = "$env:USERPROFILE\Documents\BAR_Verdance_Workspace",
  [switch]$Launch,
  [switch]$Headless,
  [switch]$SaveGame,
  [string]$SaveName = "verdance_playable_ats_001",
  [int]$TimeoutSeconds = 90
)

$ErrorActionPreference = "Stop"
. (Join-Path (Split-Path -Parent $MyInvocation.MyCommand.Path) "_common.ps1")

$config = Get-VerdanceConfig -Workspace $Workspace
$runRoot = Join-Path $Workspace "playable_runs"
New-Item -ItemType Directory -Force -Path $runRoot | Out-Null

$mapName = "All That Simmers v1.1.1"
$mapSizeX = 7168
$mapSizeZ = 10240
$runHeadless = $Headless -or $SaveGame
if ($SaveGame -and $TimeoutSeconds -eq 90) { $TimeoutSeconds = 240 }
$debugCommands = if ($SaveGame) {
  "90:luarules vazones|120:luarules vastatus|180:savegame $SaveName|1200:quitforce"
} elseif ($Headless) {
  "90:luarules vazones|120:luarules vastatus|600:quitforce"
} else {
  "90:luarules vazones|120:luarules vastatus"
}

$missionLua = @'
return {
  schemaVersion = "0.9-playable",
  campaignId = "verdance_ashes",
  missionId = "va_playable_ats_001",
  missionNumber = 901,
  pathSignal = "B",
  title = "Verdance Playable Slice: All That Simmers",
  zone = "All That Simmers",
  objective = {
    id = "ats_playable_proxy_breakout",
    kind = "playable_proxy",
    requiredFrames = 1800,
    description = "Clans start upper-left. Armada holds upper-right and center. Cortex anchors bottom-right. Raptors infest bottom-left."
  },
  economy = {
    metalIncome = 18,
    energyIncome = 42,
    buildPower = 75
  },
  graph = {
    q0_armada_cortex = 0.23,
    q2_void_structure = 0.15,
    q3_biogenesis_memory = 0.28,
    q4_ai_human = 0.72,
    q6_contested = 0.73,
    q6_independent = 0.34,
    q7_scarcity = 0.98
  },
  reputation = {
    armada = 34,
    cortex = 18,
    clans = 66,
    nullmercs = 47,
    sev = 56
  },
  companions = {
    {
      id = "ketha_rhekk_line",
      displayName = "Ketha of Rhekk's Line",
      unitDefName = "legcen",
      xp = 0.504,
      morale = 80,
      loyalty = 85,
      stress = 6,
      autonomy = 0.35,
      commandMode = "hybrid"
    }
  },
  playableSetup = {
    enabled = true,
    mapId = "all_that_simmers",
    notes = "Proxy layout for fast feel-testing. Coordinates are normalized fractions of the observed 7168x10240 map.",
    forces = {
      {
        id = "clans_upper_left",
        label = "Clans / Player Upper-Left",
        teamID = 0,
        side = "Legion",
        role = "player_anchor",
        base = { x = 0.16, z = 0.18 },
        groups = {
          { id = "clans_base", units = {
            { unitDefName = "legcom", count = 1, dx = 0, dz = 0, spacing = 80 },
            { unitDefName = "legck", count = 2, dx = 140, dz = 40, spacing = 90 },
            { unitDefName = "legmex", count = 3, dx = -160, dz = 120, spacing = 120 },
            { unitDefName = "legwin", count = 4, dx = 120, dz = 180, spacing = 90 },
            { unitDefName = "legsolar", count = 2, dx = 260, dz = 120, spacing = 100 },
            { unitDefName = "leglht", count = 3, dx = -120, dz = -140, spacing = 130 },
            { unitDefName = "legcen", count = 6, dx = 80, dz = -220, spacing = 95, patrolX = 0.34, patrolZ = 0.34 },
          } }
        }
      },
      {
        id = "armada_upper_right",
        label = "Armada Upper-Right Bastion",
        teamID = 1,
        side = "Armada",
        role = "defender",
        base = { x = 0.80, z = 0.18 },
        groups = {
          { id = "armada_bastion", units = {
            { unitDefName = "armcom", count = 1, dx = 0, dz = 0, spacing = 80 },
            { unitDefName = "armmex", count = 3, dx = -160, dz = 120, spacing = 120 },
            { unitDefName = "armwin", count = 5, dx = 130, dz = 120, spacing = 85 },
            { unitDefName = "armsolar", count = 3, dx = 240, dz = -20, spacing = 90 },
            { unitDefName = "armllt", count = 5, dx = -180, dz = -180, spacing = 120 },
            { unitDefName = "armwar", count = 8, dx = -40, dz = -300, spacing = 90, patrolX = 0.58, patrolZ = 0.44 },
          } }
        }
      },
      {
        id = "armada_center_lane",
        label = "Armada Center-Lane Hold",
        teamID = 1,
        side = "Armada",
        role = "center_hold",
        base = { x = 0.57, z = 0.48 },
        groups = {
          { id = "armada_center", units = {
            { unitDefName = "armllt", count = 6, dx = 0, dz = 0, spacing = 130 },
            { unitDefName = "armwar", count = 10, dx = -220, dz = 120, spacing = 85, patrolX = 0.42, patrolZ = 0.58 },
            { unitDefName = "armpw", count = 14, dx = 120, dz = -140, spacing = 75, patrolX = 0.32, patrolZ = 0.62 },
          } }
        }
      },
      {
        id = "cortex_bottom_right",
        label = "Cortex Bottom-Right Island",
        teamID = 2,
        side = "Cortex",
        role = "defender",
        base = { x = 0.82, z = 0.82 },
        groups = {
          { id = "cortex_island", units = {
            { unitDefName = "corcom", count = 1, dx = 0, dz = 0, spacing = 80 },
            { unitDefName = "cormex", count = 3, dx = -120, dz = -100, spacing = 120 },
            { unitDefName = "corwin", count = 5, dx = 120, dz = -80, spacing = 90 },
            { unitDefName = "corsolar", count = 3, dx = 220, dz = 80, spacing = 90 },
            { unitDefName = "corllt", count = 5, dx = -180, dz = 180, spacing = 120 },
            { unitDefName = "corgator", count = 8, dx = -260, dz = -230, spacing = 90, patrolX = 0.62, patrolZ = 0.66 },
            { unitDefName = "corthud", count = 4, dx = -40, dz = -320, spacing = 95, patrolX = 0.56, patrolZ = 0.62 },
          } }
        }
      },
      {
        id = "raptors_bottom_left",
        label = "Raptor Bottom-Left Infestation",
        teamID = 3,
        side = "Raptors",
        role = "wild_pressure",
        base = { x = 0.18, z = 0.78 },
        groups = {
          { id = "raptor_nest", units = {
            { unitDefName = "raptor_hive", count = 1, dx = 0, dz = 0, spacing = 80 },
            { unitDefName = "raptor_turret_basic_t2_v1", count = 4, dx = -160, dz = 80, spacing = 130 },
            { unitDefName = "raptor_land_swarmer_basic_t1_v1", count = 16, dx = 120, dz = -80, spacing = 70, patrolX = 0.35, patrolZ = 0.60 },
            { unitDefName = "raptor_land_swarmer_basic_t2_v1", count = 8, dx = -220, dz = -160, spacing = 80, patrolX = 0.42, patrolZ = 0.58 },
            { unitDefName = "raptor_land_assault_basic_t2_v1", count = 4, dx = 180, dz = 150, spacing = 90, patrolX = 0.48, patrolZ = 0.52 },
          } }
        }
      },
    }
  }
}
'@

New-Item -ItemType Directory -Force -Path (Split-Path -Parent $config.seedOutbox) | Out-Null
Set-Content -Encoding ASCII -Path $config.seedOutbox -Value $missionLua
New-Item -ItemType Directory -Force -Path (Split-Path -Parent $config.seedDestination) | Out-Null
Set-Content -Encoding ASCII -Path $config.seedDestination -Value $missionLua
$zoneMapDestination = Install-VerdanceZoneMap -Config $config

$startScriptPath = Join-Path $runRoot "verdance_playable_all_that_simmers.txt"
$startScript = @"
[GAME]
{
  MapName=$mapName;
  GameType=Beyond All Reason `$VERSION;
  GameStartDelay=0;
  StartPosType=3;
  RecordDemo=1;
  MyPlayerName=VerdanceCommander;
  IsHost=1;
  FixedRNGSeed=1;
  NumPlayers=1;
  NumUsers=4;
  HostIP=127.0.0.1;
  HostPort=0;
  NoHelperAIs=0;

  [MODOPTIONS]
  {
    deathmode=neverend;
    experimentallegionfaction=1;
    teamffa_start_boxes_shuffle=0;
    raptor_difficulty=normal;
    raptor_graceperiodmult=1.0;
    raptor_spawncountmult=1.0;
    va_campaign=1;
    debugcommands=$debugCommands;
  }

  [ALLYTEAM0]
  {
    StartRectLeft=0.02;
    StartRectTop=0.02;
    StartRectRight=0.32;
    StartRectBottom=0.36;
    NumAllies=0;
  }

  [ALLYTEAM1]
  {
    StartRectLeft=0.58;
    StartRectTop=0.02;
    StartRectRight=0.98;
    StartRectBottom=0.58;
    NumAllies=0;
  }

  [ALLYTEAM2]
  {
    StartRectLeft=0.65;
    StartRectTop=0.62;
    StartRectRight=0.98;
    StartRectBottom=0.98;
    NumAllies=0;
  }

  [ALLYTEAM3]
  {
    StartRectLeft=0.02;
    StartRectTop=0.58;
    StartRectRight=0.38;
    StartRectBottom=0.98;
    NumAllies=0;
  }

  [TEAM0]
  {
    Side=Legion;
    Handicap=0;
    AllyTeam=0;
    TeamLeader=0;
    StartPosX=$([int]($mapSizeX * 0.16));
    StartPosZ=$([int]($mapSizeZ * 0.18));
    RgbColor=0.25 0.85 0.35;
  }

  [TEAM1]
  {
    Side=Armada;
    Handicap=0;
    AllyTeam=1;
    TeamLeader=0;
    StartPosX=$([int]($mapSizeX * 0.80));
    StartPosZ=$([int]($mapSizeZ * 0.18));
    RgbColor=0.25 0.48 1.0;
  }

  [TEAM2]
  {
    Side=Cortex;
    Handicap=0;
    AllyTeam=2;
    TeamLeader=0;
    StartPosX=$([int]($mapSizeX * 0.82));
    StartPosZ=$([int]($mapSizeZ * 0.82));
    RgbColor=1.0 0.20 0.16;
  }

  [TEAM3]
  {
    Side=Armada;
    Handicap=0;
    AllyTeam=3;
    TeamLeader=0;
    StartPosX=$([int]($mapSizeX * 0.18));
    StartPosZ=$([int]($mapSizeZ * 0.78));
    RgbColor=0.78 0.14 0.92;
  }

  [AI0]
  {
    Host=0;
    IsFromDemo=0;
    Name=SimpleDefenderAI(Armada);
    ShortName=SimpleDefenderAI;
    Team=1;
    Version=<not-versioned>;
  }

  [AI1]
  {
    Host=0;
    IsFromDemo=0;
    Name=SimpleDefenderAI(Cortex);
    ShortName=SimpleDefenderAI;
    Team=2;
    Version=<not-versioned>;
  }

  [AI2]
  {
    Host=0;
    IsFromDemo=0;
    Name=RaptorsDefenseAI(Verdance);
    ShortName=RaptorsAI;
    Team=3;
    Version=<not-versioned>;
  }

  [PLAYER0]
  {
    IsFromDemo=0;
    Name=VerdanceCommander;
    Team=0;
    Spectator=0;
    Rank=0;
  }
}
"@
Set-Content -Encoding ASCII -Path $startScriptPath -Value $startScript

Write-Host "Installed playable mission seed to workspace: $($config.seedOutbox)"
Write-Host "Installed playable mission seed to BAR: $($config.seedDestination)"
Write-Host "Installed zone map to BAR: $zoneMapDestination"
Write-Host "Wrote playable startscript: $startScriptPath"

$engineName = if ($runHeadless) { "spring-headless.exe" } else { "spring.exe" }
$engine = Join-Path $config.barDataRoot "engine\recoil_2025.06.24\$engineName"
if (!(Test-Path $engine)) { throw "$engineName not found at $engine" }

if ($Launch -or $runHeadless) {
  $args = @("--write-dir", $config.barDataRoot, "--only-local", $startScriptPath)
  if ($runHeadless) {
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
    [void]$proc.Start()
    if (-not $proc.WaitForExit($TimeoutSeconds * 1000)) {
      try { $proc.Kill() } catch { }
      throw "spring-headless timed out after $TimeoutSeconds seconds. Check $($config.infolog)"
    }
    Write-Host "spring-headless exit code: $($proc.ExitCode)"
    if ($proc.ExitCode -ne 0) { throw "spring-headless exited with code $($proc.ExitCode). Check $($config.infolog)" }
    if ($SaveGame) {
      $saveDir = Join-Path $config.barDataRoot "Saves"
      $saveGamePath = Join-Path $saveDir "$SaveName.ssf"
      $saveMetaPath = Join-Path $saveDir "$SaveName.lua"
      $manifestPath = Join-Path $runRoot "latest_savegame_path.txt"
      if (!(Test-Path $saveGamePath)) { throw "Expected savegame was not created at $saveGamePath. Check $($config.infolog)" }
      if (!(Test-Path $saveMetaPath)) { Write-Warning "Save metadata was not created at $saveMetaPath. The .ssf exists, but BAR's load menu may not list it cleanly." }
      @(
        "saveName=$SaveName",
        "saveGamePath=$saveGamePath",
        "saveMetaPath=$saveMetaPath",
        "startScriptPath=$startScriptPath",
        "infolog=$($config.infolog)"
      ) | Set-Content -Encoding ASCII -Path $manifestPath
      Write-Host "Created BAR savegame: $saveGamePath"
      Write-Host "Wrote savegame manifest: $manifestPath"
    }
  } else {
    Start-Process -FilePath $engine -WorkingDirectory $config.barDataRoot -ArgumentList $args
    Write-Host "Launched visible BAR/Recoil process."
  }
}
