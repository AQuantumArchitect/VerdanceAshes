# Consolidated product ship -> export\dist\VerdanceAshes_vX.Y.Z (+ zip)
# Self-contained: SETUP + PLAY + kernel + mod + data. No design forge required.
param(
  [string]$Workspace = "",
  [string]$Version = "",
  [string]$OutDir = "",
  [switch]$SkipPython,
  [switch]$SkipZip,
  [switch]$InstallToMyGames,
  [string]$PythonEmbedZip = "",
  [string]$PythonEmbedUrl = "https://www.python.org/ftp/python/3.12.8/python-3.12.8-embed-amd64.zip"
)

$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
. (Join-Path $ScriptDir "_common.ps1")
$Workspace = Get-VerdanceWorkspaceRoot -Workspace $Workspace

if (-not $Version) {
  $verFile = Join-Path $Workspace "VERSION"
  if (Test-Path $verFile) {
    $Version = ((Get-Content -Raw $verFile).Trim() -split "[\r\n]+")[0].Trim()
  } else {
    $Version = "0.8.0"
  }
}
if (-not $OutDir) { $OutDir = Join-Path $Workspace "export\dist" }

$releaseName = "VerdanceAshes_v$Version"
$staging = Join-Path $OutDir $releaseName
Write-Host "=== Ship $releaseName ==="
Write-Host "From: $Workspace"
Write-Host "To:   $staging"

if (Test-Path $staging) { Remove-Item -Recurse -Force $staging }
New-Item -ItemType Directory -Force -Path $staging | Out-Null

function Copy-Into([string]$Source, [string]$Dest) {
  if (!(Test-Path $Source)) {
    Write-Host "  skip missing: $Source"
    return
  }
  $destDir = Split-Path -Parent $Dest
  New-Item -ItemType Directory -Force -Path $destDir | Out-Null
  Copy-Item -Recurse -Force -LiteralPath $Source -Destination $Dest
}

function Copy-File([string]$Source, [string]$Dest) {
  if (!(Test-Path $Source)) { return }
  $destDir = Split-Path -Parent $Dest
  New-Item -ItemType Directory -Force -Path $destDir | Out-Null
  Copy-Item -Force -LiteralPath $Source -Destination $Dest
}

# ---- identity ----
Copy-File (Join-Path $Workspace "VERSION") (Join-Path $staging "VERSION")
Copy-File (Join-Path $Workspace "docs\release\START_HERE.txt") (Join-Path $staging "START_HERE.txt")
# A distributed build must carry its own terms. LICENSE also records that the
# GPL covers mod/data/scripts while tools/ and app/ are reserved -- a split that
# is meaningless if the file only exists in the repo. NOTICE credits Mupersega's
# GPL RML reference and records that maps and BAR itself are never redistributed.
Copy-File (Join-Path $Workspace "LICENSE") (Join-Path $staging "LICENSE")
Copy-File (Join-Path $Workspace "NOTICE") (Join-Path $staging "NOTICE")
Copy-File (Join-Path $Workspace "docs\DEPLOY_TRUTH.md") (Join-Path $staging "docs\DEPLOY_TRUTH.md")
Copy-File (Join-Path $Workspace "docs\SHIP_ARCHITECTURE.md") (Join-Path $staging "docs\SHIP_ARCHITECTURE.md")
foreach ($doc in @("README.md", "INSTALL.md", "PLAYTESTING.md", "START_HERE.txt")) {
  Copy-File (Join-Path $Workspace "docs\release\$doc") (Join-Path $staging "docs\$doc")
}

# ---- mod ----
Copy-Into (Join-Path $Workspace "mod\VerdanceAshes.sdd") (Join-Path $staging "mod\VerdanceAshes.sdd")
# strip per-mission generated seeds (keep fallbacks)
$gen = Join-Path $staging "mod\VerdanceAshes.sdd\singleplayer\verdance_ashes\generated"
foreach ($f in @("va_current.lua", "zone_map_current.lua")) {
  Remove-Item -Force -ErrorAction SilentlyContinue (Join-Path $gen $f)
}

# ---- UI + brain ----
Copy-Into (Join-Path $Workspace "app\showoff") (Join-Path $staging "app\showoff")
if (Test-Path (Join-Path $Workspace "app\brain")) {
  Copy-Into (Join-Path $Workspace "app\brain") (Join-Path $staging "app\brain")
}

# ---- kernel + tools (player surface only) ----
Copy-Into (Join-Path $Workspace "tools\verdance_kernel") (Join-Path $staging "tools\verdance_kernel")
# drop pycache
Get-ChildItem (Join-Path $staging "tools") -Recurse -Directory -Filter "__pycache__" -ErrorAction SilentlyContinue |
  Remove-Item -Recurse -Force -ErrorAction SilentlyContinue

# This list is verified, not maintained by hand: the parity gate below runs
# tools\ship_parity_check_v1.py over the staged tree and fails the ship if any
# staged module imports something that is not here. Regenerate with:
#   python tools\ship_parity_check_v1.py --staging . --closure --entry "<this list>"
$toolPy = @(
  "apply_result_to_hub_v1.py",
  "stamp_deploy_plan_v1.py",
  "build_hub_state_v1.py",
  "build_zone_boards_v1.py",
  "verdance_story_engine_v1.py",
  "world_tick_v1.py",
  "world_zone_graph.py",
  "contract_v2.py",
  "attachments_v1.py",
  "quest_generator_v1.py",
  "capture_node_claims.py",
  # --- absent from v0.10.0, and absent SILENTLY: every import site is a bare
  # try/except. Without escalation_ladder_v1 the story engine's
  # build_escalation_plan returns None, intent.escalationPlan never appears, and
  # build_next_mission_v1.ps1 pins objectiveStrength to "surgical" for the whole
  # campaign -- shipping the exact flat difficulty curve Drop 4 removed, with no
  # symptom to trace. The other two lose mission credit/debrief and the
  # between-mission offscreen war respectively.
  "escalation_ladder_v1.py",
  "match_credit_v1.py",
  "graph_collapse_v1.py",
  "narrative_v1.py",
  "offscreen_clash_v1.py",
  # Fetches campaign maps from BAR's own content service at play time.
  "map_provisioner_v1.py",
  # Continuity / company / commerce / LZ / quantum state — imported by engine +
  # kernel; missing these silently disables footprint audit, field-pool loss,
  # delivery packs, and landing-zone resolve on shipped builds.
  "commerce_delivery_v1.py",
  "company_v1.py",
  "continuity_audit_v1.py",
  "landing_zones_v1.py",
  "quantum_campaign_state_v1.py",
  # Hero observe / umwelt / molecule policy (attachments + support web + Stage 1–3 tools).
  # Missing these silently drops observe stamps and blocks molecule D(u) regen on ship.
  "hero_observe_v1.py",
  "map_umwelt_v1.py",
  "molecule_doctrine_v1.py",
  "phi_projector_v1.py",
  "shadow_intent_v1.py",
  "hero_graph_analyze_v1.py",
  "support_web_v1.py",
  "hero_codex_v1.py",
  # Narrative readings / belief world / perspectives / camp clock (passes one..four, 2026-10-19).
  # The engine imports these inside try/except, so a missing one ships a silent campaign with no
  # readings face, no belief fold, no camp clock and no intel overlay.
  "readings_v1.py",
  "occasions_v1.py",
  "belief_homecoming_v1.py",
  "umwelt_world_v1.py",
  "umwelt_replay_v1.py",
  "perspectives_v1.py",
  "camp_clock_v1.py",
  "story_dance_v1.py",
  "chronicle_v1.py",
  "intel_lua_v1.py",
  "manifest_v1.py",
  "validate_story_v1.py",
  "wet_reach_v1.py",
  # Ship so a player build can self-check; also what the gates below run.
  "ship_parity_check_v1.py",
  "validate_map_names_v1.py"
)
foreach ($t in $toolPy) {
  Copy-File (Join-Path $Workspace "tools\$t") (Join-Path $staging "tools\$t")
}

# ---- data ----
$dataParts = @(
  "map_pool",
  "zone_maps",
  "scenarios\authored",
  "story",
  "commerce",
  "contracts",
  "base_templates",
  # Both reached only as Path(workspace) / "data" / <name>, so no "data/x"
  # substring exists to grep for -- which is why both were missed. escalation
  # holds mission_escalation.json, the owner-tunable ladder; without it even a
  # staged escalation_ladder_v1 silently falls back to DEFAULT_LADDER.
  # hydrology drives the water cycle; without it intent.hydrology is empty
  # every mission and the seasons/tides work never engages.
  "escalation",
  "hydrology"
)
foreach ($p in $dataParts) {
  $src = Join-Path $Workspace "data\$p"
  if (Test-Path $src) {
    Copy-Into $src (Join-Path $staging "data\$p")
  }
}
# drop generated noise under zone_maps/scenarios if copied
foreach ($noise in @(
  "data\zone_maps\generated",
  "data\scenarios\generated"
)) {
  $npath = Join-Path $staging $noise
  if (Test-Path $npath) { Remove-Item -Recurse -Force $npath }
}

# ---- Umwelt (belief-field engine; FREEZE law: depend, don't copy) ----
# The campaign imports the umwelt package at run time (tools\umwelt_world_v1.py). A player
# build has no clone of the Umwelt repo, so vendor a snapshot of its src\umwelt package into
# tools\_vendor, which umwelt_world_v1 adds to sys.path last (UMWELT_SRC and a sibling clone win).
$umweltCandidates = @()
if ($env:UMWELT_SRC) { $umweltCandidates += $env:UMWELT_SRC }
$umweltCandidates += (Join-Path (Split-Path -Parent $Workspace) "umwelt\src")
$umweltCandidates += (Join-Path $env:USERPROFILE "ws-win\umwelt\src")
$umweltCandidates += (Join-Path $env:USERPROFILE "umwelt\src")
$umweltSrc = $umweltCandidates | Where-Object { Test-Path (Join-Path $_ "umwelt\__init__.py") } | Select-Object -First 1
if ($umweltSrc) {
  $vendor = Join-Path $staging "tools\_vendor"
  New-Item -ItemType Directory -Force -Path $vendor | Out-Null
  Copy-Into (Join-Path $umweltSrc "umwelt") (Join-Path $vendor "umwelt")
  Get-ChildItem $vendor -Recurse -Directory -Filter "__pycache__" -ErrorAction SilentlyContinue |
    Remove-Item -Recurse -Force -ErrorAction SilentlyContinue
  $umweltHash = (git -C (Split-Path -Parent $umweltSrc) rev-parse --short HEAD 2>$null)
  Set-Content -Path (Join-Path $vendor "UMWELT_SNAPSHOT.txt") -Value ("umwelt snapshot from " + $umweltSrc + " at " + (Get-Date).ToString("s") + " commit " + $umweltHash)
  Write-Host "Umwelt vendored from $umweltSrc ($umweltHash)"
} else {
  Write-Warning "Umwelt source not found (UMWELT_SRC / ..\umwelt\src / ~\ws-win\umwelt\src); shipped build will run without the belief world."
}

Copy-File (Join-Path $Workspace "verdance_config.template.json") (Join-Path $staging "verdance_config.template.json")
Copy-File (Join-Path $Workspace "requirements-ship.txt") (Join-Path $staging "requirements-ship.txt")

# ---- scripts (player + kernel-needed) ----
$scriptList = @(
  "_common.ps1",
  "setup_tester.ps1",
  "install_mod_archive.ps1",
  # pass five: the kernel launches spring and reads the infolog itself; play_session_v1 /
  # extract_latest_result / run_full_cycle are operator (headless) tools, not the player path.
  "build_next_mission_v1.ps1",
  "install_playable_slice.ps1",
  "extract_latest_telemetry.ps1",
  "advance_campaign_v1.ps1",
  "migrate_state_v1.ps1",
  "ship.ps1"
)
foreach ($s in $scriptList) {
  Copy-File (Join-Path $Workspace "scripts\$s") (Join-Path $staging "scripts\$s")
}
# player helpers
if (Test-Path (Join-Path $Workspace "scripts\player")) {
  Copy-Into (Join-Path $Workspace "scripts\player") (Join-Path $staging "scripts\player")
}

# ---- empty runtime dirs ----
foreach ($d in @("state", "inbox", "outbox", "ledger", "playable_runs", "reports", "logs")) {
  New-Item -ItemType Directory -Force -Path (Join-Path $staging $d) | Out-Null
}
# seed empty ledger
"{}" | Set-Content -Encoding UTF8 (Join-Path $staging "ledger\processed_results.json")

# ---- app\bin launcher glue (same as forge product) ----
New-Item -ItemType Directory -Force -Path (Join-Path $staging "app\bin") | Out-Null
Copy-File (Join-Path $Workspace "app\bin\_env.bat") (Join-Path $staging "app\bin\_env.bat")
Copy-File (Join-Path $Workspace "app\bin\PLAY.bat") (Join-Path $staging "app\bin\PLAY.bat")
Copy-File (Join-Path $Workspace "app\bin\HUB_HOST.bat") (Join-Path $staging "app\bin\HUB_HOST.bat")

# ---- root entry points ----
@'
@echo off
setlocal
call "%~dp0app\bin\PLAY.bat" %*
exit /b %ERRORLEVEL%
'@ | Set-Content -Encoding ASCII (Join-Path $staging "PLAY.bat")

@'
@echo off
setlocal
title Verdance Ashes - SETUP
call "%~dp0app\bin\_env.bat"
if errorlevel 1 ( pause & exit /b 1 )
echo.
echo  VERDANCE SETUP - find BAR, install mutator, rebuild hub
echo.
powershell -NoProfile -ExecutionPolicy Bypass -File "%VERDANCE_ROOT%\scripts\player\setup_play.ps1" -Workspace "%VERDANCE_ROOT%"
set ERR=%ERRORLEVEL%
if %ERR% neq 0 ( echo SETUP failed. & pause & exit /b %ERR% )
echo Next: PLAY.bat
pause
exit /b 0
'@ | Set-Content -Encoding ASCII (Join-Path $staging "SETUP.bat")

@'
@echo off
setlocal
call "%~dp0app\bin\_env.bat"
if errorlevel 1 ( pause & exit /b 1 )
set /p CONFIRM=Type YES to reset campaign: 
if /I not "%CONFIRM%"=="YES" ( echo Cancelled. & pause & exit /b 0 )
powershell -NoProfile -ExecutionPolicy Bypass -File "%VERDANCE_ROOT%\scripts\player\reset_campaign.ps1" -Workspace "%VERDANCE_ROOT%"
pause
'@ | Set-Content -Encoding ASCII (Join-Path $staging "RESET.bat")

# START_HERE.txt is already staged from the real docs\release\START_HERE.txt
# by the identity block above (both at the dist root and under docs\) --
# do not regenerate it here. A hardcoded copy used to live in this spot and
# silently clobber that real file with a second, out-of-date copy; worse,
# this .ps1 is BOM-less UTF-8, which PowerShell 5.1 parses as ANSI, so the
# em dashes in that hardcoded copy corrupted into garbage bytes in every
# shipped build. One source of truth, ASCII-only, fixes both.

# ---- embed python (optional) ----
if (-not $SkipPython) {
  $cacheDir = Join-Path $Workspace "runtime_cache"
  New-Item -ItemType Directory -Force -Path $cacheDir | Out-Null
  if (-not $PythonEmbedZip) {
    $PythonEmbedZip = Join-Path $cacheDir (Split-Path -Leaf $PythonEmbedUrl)
  }
  if (!(Test-Path $PythonEmbedZip)) {
    Write-Host "Downloading embeddable Python..."
    try {
      Invoke-WebRequest -Uri $PythonEmbedUrl -OutFile $PythonEmbedZip
    } catch {
      Write-Host "WARNING: could not download Python embed: $_"
      Write-Host "Ship will require system Python on PATH."
      $SkipPython = $true
    }
  }
  if (-not $SkipPython -and (Test-Path $PythonEmbedZip)) {
    $pyDir = Join-Path $staging "runtime\python"
    New-Item -ItemType Directory -Force -Path $pyDir | Out-Null
    Expand-Archive -Path $PythonEmbedZip -DestinationPath $pyDir -Force
    # Allow site imports for tools path (embed _pth)
    $pth = Get-ChildItem $pyDir -Filter "python*._pth" | Select-Object -First 1
    if ($pth) {
      $pthText = Get-Content -Raw $pth.FullName
      if ($pthText -notmatch "import site") {
        Add-Content -Path $pth.FullName -Value "import site"
      }
      if ($pthText -notmatch "\.\.\\..\\tools") {
        Add-Content -Path $pth.FullName -Value "..\..\tools"
      }
    }
    Write-Host "Bundled embeddable Python"
  }
} else {
  Write-Host "Skipping embedded Python"
}

# ---- disarm dev telemetry in shipped mod ----
$flag = Join-Path $staging "mod\VerdanceAshes.sdd\singleplayer\verdance_ashes\generated\dev_telemetry_flag.lua"
if (Test-Path (Split-Path $flag)) {
  @"
return {
  enabled = false,
  samplePeriodFrames = 150,
  trackPlayerCommands = true,
  schemaVersion = 'verdance-dev-telemetry-flag/0.1',
}
"@ | Set-Content -Encoding ASCII -Path $flag
}

# ---- parity gate ----
# v0.10.0 shipped without escalation_ladder_v1, match_credit_v1,
# offscreen_clash_v1, data\escalation and data\hydrology. Nothing crashed --
# every import site is a bare try/except, so the build ran, looked healthy, and
# was quietly the pre-Drop-4 game. The only way to catch that class of mistake
# is statically, before the zip exists. Hard failure: a build that cannot import
# its own subsystems is not a build worth handing anyone.
$parity = Join-Path $staging "tools\ship_parity_check_v1.py"
if (Test-Path -LiteralPath $parity) {
  $py = Get-VerdancePython $Workspace
  & $py $parity --staging $staging | Out-Host
  if ($LASTEXITCODE -ne 0) {
    throw ("Ship parity check failed (see above). The staged tree imports " +
           "modules or reads data directories it does not contain. Fix " +
           "`$toolPy / `$dataParts in this script; do not ship around it.")
  }
} else {
  Write-Warning "tools\ship_parity_check_v1.py not staged; parity gate skipped."
}

# ---- map name gate ----
# A map name the engine cannot resolve is fatal in PreGame, before the mutator
# loads, so it surfaces to a player as "crashed on launch" with nothing naming
# the cause. v0.10.0 shipped two of them. Offline check only: the ship must not
# depend on a network round trip. Run --online by hand when changing the pool.
$mapCheck = Join-Path $staging "tools\validate_map_names_v1.py"
if (Test-Path -LiteralPath $mapCheck) {
  $py2 = Get-VerdancePython $Workspace
  & $py2 $mapCheck --root $staging | Out-Host
  if ($LASTEXITCODE -ne 0) {
    throw "Map name validation failed (see above). Fix the data before shipping."
  }
}

# ---- manifest ----
$files = Get-ChildItem -Recurse -File $staging
$manifest = [ordered]@{
  schemaVersion   = "verdance-ship/1.0"
  name            = $releaseName
  version         = $Version
  builtAt         = (Get-Date).ToUniversalTime().ToString("o")
  sourceWorkspace = $Workspace
  fileCount       = $files.Count
  playerEntry     = @("SETUP.bat", "PLAY.bat")
  includesKernel  = $true
  includesMod     = $true
  includesPython  = (Test-Path (Join-Path $staging "runtime\python\python.exe"))
}
$manifest | ConvertTo-Json -Depth 6 | Set-Content -Encoding UTF8 (Join-Path $staging "release_manifest.json")

# ---- zip ----
$zipPath = Join-Path $OutDir "$releaseName`_win64.zip"
if (-not $SkipZip) {
  if (Test-Path $zipPath) { Remove-Item -Force $zipPath }
  Compress-Archive -Path $staging -DestinationPath $zipPath -CompressionLevel Optimal
  $zipHash = (Get-FileHash -Algorithm SHA256 $zipPath).Hash.ToLowerInvariant()
  Write-Host "Zip:    $zipPath"
  Write-Host "SHA256: $zipHash"
}

# ---- optional install full dist to My Games (real product, not brochure) ----
if ($InstallToMyGames) {
  $dest = Join-Path $env:USERPROFILE "Documents\My Games\VerdanceAshes"
  Write-Host "Installing full dist to $dest"
  if (Test-Path $dest) {
    # Preserve live campaign progress across ship, but never nest prior
    # va_ship_state_keep trees (that revived Sortie 5 after RESET + ship).
    $keepState = $null
    $stateSrc = Join-Path $dest "state"
    if (Test-Path $stateSrc) {
      $keepState = Join-Path $env:TEMP "va_ship_state_keep"
      if (Test-Path $keepState) { Remove-Item -Recurse -Force $keepState }
      New-Item -ItemType Directory -Force -Path $keepState | Out-Null
      Get-ChildItem -LiteralPath $stateSrc -Force | Where-Object {
        $_.Name -ne "va_ship_state_keep"
      } | ForEach-Object {
        Copy-Item -Recurse -Force -LiteralPath $_.FullName -Destination (Join-Path $keepState $_.Name)
      }
    }
    Get-ChildItem $dest -Force | Remove-Item -Recurse -Force -ErrorAction SilentlyContinue
  } else {
    New-Item -ItemType Directory -Force -Path $dest | Out-Null
  }
  Copy-Item -Recurse -Force (Join-Path $staging "*") $dest
  if ($keepState) {
    $destState = Join-Path $dest "state"
    New-Item -ItemType Directory -Force -Path $destState | Out-Null
    Get-ChildItem -LiteralPath $keepState -Force | ForEach-Object {
      Copy-Item -Recurse -Force -LiteralPath $_.FullName -Destination (Join-Path $destState $_.Name)
    }
  }
  Write-Host "My Games install complete (full kernel dist)."
  # Playtests must load deployed Lua — not the workspace junction.
  $pointBar = Join-Path $Workspace "scripts\player\point_bar_mod.ps1"
  if (Test-Path $pointBar) {
    Write-Host "Pointing BAR VerdanceAshes.sdd -> My Games mod (deployed play truth)"
    & powershell -NoProfile -ExecutionPolicy Bypass -File $pointBar -Mode Deployed -Workspace $Workspace
    if ($LASTEXITCODE -ne 0) {
      throw "point_bar_mod Deployed failed (exit $LASTEXITCODE)"
    }
  } else {
    Write-Host "WARN: point_bar_mod.ps1 missing — BAR may still junction to workspace."
  }
}

Write-Host ""
Write-Host "=== Ship complete ==="
Write-Host "Folder: $staging"
Write-Host "Files:  $($files.Count)"
Write-Host "Play:   Documents\My Games\VerdanceAshes\PLAY.bat (deployed truth)"
Write-Host "Dev:    point_bar_mod.ps1 -Mode Workspace  then workspace PLAY if needed"
