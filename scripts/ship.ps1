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
  "capture_node_claims.py"
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
  "base_templates"
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

Copy-File (Join-Path $Workspace "verdance_config.template.json") (Join-Path $staging "verdance_config.template.json")
Copy-File (Join-Path $Workspace "requirements-ship.txt") (Join-Path $staging "requirements-ship.txt")

# ---- scripts (player + kernel-needed) ----
$scriptList = @(
  "_common.ps1",
  "setup_tester.ps1",
  "install_mod_archive.ps1",
  "play_session_v1.ps1",
  "build_next_mission_v1.ps1",
  "install_playable_slice.ps1",
  "extract_latest_result.ps1",
  "extract_latest_telemetry.ps1",
  "advance_campaign_v1.ps1",
  "run_full_cycle_v1.ps1",
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
    # preserve state if present
    $keepState = $null
    $stateSrc = Join-Path $dest "state"
    if (Test-Path $stateSrc) {
      $keepState = Join-Path $env:TEMP "va_ship_state_keep"
      if (Test-Path $keepState) { Remove-Item -Recurse -Force $keepState }
      Copy-Item -Recurse -Force $stateSrc $keepState
    }
    Get-ChildItem $dest -Force | Remove-Item -Recurse -Force -ErrorAction SilentlyContinue
  } else {
    New-Item -ItemType Directory -Force -Path $dest | Out-Null
  }
  Copy-Item -Recurse -Force (Join-Path $staging "*") $dest
  if ($keepState) {
    Copy-Item -Recurse -Force $keepState (Join-Path $dest "state")
  }
  Write-Host "My Games install complete (full kernel dist)."
}

Write-Host ""
Write-Host "=== Ship complete ==="
Write-Host "Folder: $staging"
Write-Host "Files:  $($files.Count)"
Write-Host "Play:   $staging\SETUP.bat then PLAY.bat"
