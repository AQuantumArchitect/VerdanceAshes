param(
  [string]$Workspace = "",
  [string]$Version = "0.1.0",
  [string]$OutDir = "",
  [string]$PythonEmbedZip = "",
  [string]$PythonEmbedUrl = "https://www.python.org/ftp/python/3.12.8/python-3.12.8-embed-amd64.zip",
  [switch]$SkipPython
)

$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
. (Join-Path $ScriptDir "_common.ps1")
$Workspace = Get-VerdanceWorkspaceRoot -Workspace $Workspace
if (-not $OutDir) { $OutDir = Join-Path $Workspace "export\release" }

$modSource = Join-Path $Workspace "mod\VerdanceAshes.sdd"
if (!(Test-Path (Join-Path $modSource "modinfo.lua"))) {
  throw "mod\VerdanceAshes.sdd\modinfo.lua not found - cannot package a release without the mod archive."
}

$releaseName = "VerdanceAshes_v$Version"
$staging = Join-Path $OutDir "staging\$releaseName"
if (Test-Path $staging) { Remove-Item -Recurse -Force $staging }
New-Item -ItemType Directory -Force -Path $staging | Out-Null
$ws = Join-Path $staging "workspace"

function Copy-Into {
  param([string]$Source, [string]$Dest)
  $destDir = Split-Path -Parent $Dest
  New-Item -ItemType Directory -Force -Path $destDir | Out-Null
  Copy-Item -Recurse -Force -LiteralPath $Source -Destination $Dest
}

# ---- docs ---------------------------------------------------------------
foreach ($doc in @("README.md", "INSTALL.md", "PLAYTESTING.md", "START_HERE.txt")) {
  $src = Join-Path $Workspace "docs\release\$doc"
  if (Test-Path $src) {
    Copy-Into $src (Join-Path $staging $doc)
  }
}
# Top-level START_HERE for zip browsers that never open docs/
if (Test-Path (Join-Path $Workspace "docs\release\START_HERE.txt")) {
  Copy-Into (Join-Path $Workspace "docs\release\START_HERE.txt") (Join-Path $staging "START_HERE.txt")
}

# ---- mod archive (exclude per-mission generated seeds; keep the fallback) ----
Copy-Into $modSource (Join-Path $staging "VerdanceAshes.sdd")
$generatedDir = Join-Path $staging "VerdanceAshes.sdd\singleplayer\verdance_ashes\generated"
foreach ($f in @("va_current.lua", "zone_map_current.lua")) {
  Remove-Item -Force -ErrorAction SilentlyContinue (Join-Path $generatedDir $f)
}

# ---- curated scripts ----------------------------------------------------
$scriptList = @(
  "_common.ps1", "setup_tester.ps1", "install_mod_archive.ps1",
  "play_session_v1.ps1", "build_next_mission_v1.ps1", "install_playable_slice.ps1",
  "extract_latest_result.ps1", "extract_latest_telemetry.ps1",
  "advance_campaign_v1.ps1", "run_full_cycle_v1.ps1", "migrate_state_v1.ps1",
  "verdance_console_server.ps1", "verdance_process_health.ps1",
  "analyze_bar_match.ps1"
)
foreach ($s in $scriptList) {
  Copy-Into (Join-Path $Workspace "scripts\$s") (Join-Path $ws "scripts\$s")
}

# ---- tools ---------------------------------------------------------------
Copy-Into (Join-Path $Workspace "tools\verdance_story_engine_v1.py") (Join-Path $ws "tools\verdance_story_engine_v1.py")
Copy-Into (Join-Path $Workspace "tools\verdance_companion_console_v0_7.html") (Join-Path $ws "tools\verdance_companion_console_v0_7.html")

# ---- data (only what the mission builder needs) --------------------------
Copy-Into (Join-Path $Workspace "data\map_pool\seven_maps.json") (Join-Path $ws "data\map_pool\seven_maps.json")
Copy-Into (Join-Path $Workspace "data\zone_maps\authored") (Join-Path $ws "data\zone_maps\authored")
Copy-Into (Join-Path $Workspace "data\scenarios\authored") (Join-Path $ws "data\scenarios\authored")
Copy-Into (Join-Path $Workspace "data\story\ketha_voice.json") (Join-Path $ws "data\story\ketha_voice.json")
Copy-Into (Join-Path $Workspace "verdance_config.template.json") (Join-Path $ws "verdance_config.template.json")
# Zone graph + world atlas for adjacent continues / minimap (WO-020a / L1)
$zoneGraph = Join-Path $Workspace "data\zone_maps\world_zone_graph.v1.json"
if (Test-Path $zoneGraph) {
  Copy-Into $zoneGraph (Join-Path $ws "data\zone_maps\world_zone_graph.v1.json")
}
Get-ChildItem (Join-Path $Workspace "data\zone_maps") -Filter "*.json" -ErrorAction SilentlyContinue |
  Where-Object { $_.Name -match 'adjacency|zone_map' } |
  ForEach-Object { Copy-Into $_.FullName (Join-Path $ws "data\zone_maps\$($_.Name)") }

# ---- empty runtime dirs ---------------------------------------------------
foreach ($d in @("state", "inbox", "outbox", "ledger", "playable_runs", "headless_runs", "data\scenarios\generated", "reports")) {
  New-Item -ItemType Directory -Force -Path (Join-Path $ws $d) | Out-Null
}

# ---- entry-point bats -----------------------------------------------------
@'
@echo off
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\setup_tester.ps1"
pause
'@ | Set-Content -Encoding ASCII (Join-Path $ws "SETUP.bat")
@'
@echo off
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\play_session_v1.ps1"
pause
'@ | Set-Content -Encoding ASCII (Join-Path $ws "PLAY_SESSION.bat")
@'
@echo off
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\verdance_console_server.ps1"
'@ | Set-Content -Encoding ASCII (Join-Path $ws "LAUNCH_CONSOLE.bat")
$resetSrc = Join-Path $Workspace "RESET_CAMPAIGN.bat"
if (Test-Path $resetSrc) {
  Copy-Into $resetSrc (Join-Path $ws "RESET_CAMPAIGN.bat")
} else {
  @'
@echo off
echo Resetting campaign state...
if exist "%~dp0state" rmdir /s /q "%~dp0state"
mkdir "%~dp0state" 2>nul
echo Done. Run PLAY_SESSION.bat for a fresh start.
pause
'@ | Set-Content -Encoding ASCII (Join-Path $ws "RESET_CAMPAIGN.bat")
}

# ---- embedded python ------------------------------------------------------
if (-not $SkipPython) {
  $cacheDir = Join-Path $Workspace "runtime_cache"
  New-Item -ItemType Directory -Force -Path $cacheDir | Out-Null
  if (-not $PythonEmbedZip) {
    $PythonEmbedZip = Join-Path $cacheDir (Split-Path -Leaf $PythonEmbedUrl)
    if (!(Test-Path $PythonEmbedZip)) {
      Write-Host "Downloading embeddable Python: $PythonEmbedUrl"
      Invoke-WebRequest -Uri $PythonEmbedUrl -OutFile $PythonEmbedZip
    }
  }
  $pyDir = Join-Path $ws "runtime\python"
  New-Item -ItemType Directory -Force -Path $pyDir | Out-Null
  Expand-Archive -Path $PythonEmbedZip -DestinationPath $pyDir -Force
  Write-Host "Bundled embeddable Python from $PythonEmbedZip"
} else {
  Write-Host "Skipping embedded Python (testers will need python on PATH)."
}

# ---- manifest + zip -------------------------------------------------------
$gitSha = ""
try { $gitSha = (git -C $Workspace rev-parse HEAD 2>$null) } catch { }
$files = Get-ChildItem -Recurse -File $staging
$manifest = [ordered]@{
  schemaVersion = "verdance-release/1.0"
  name = $releaseName
  version = $Version
  builtAt = (Get-Date).ToUniversalTime().ToString("o")
  gitCommit = $gitSha
  fileCount = $files.Count
  files = @($files | ForEach-Object {
    [ordered]@{
      path = $_.FullName.Substring($staging.Length + 1)
      bytes = $_.Length
      sha256 = (Get-FileHash -Algorithm SHA256 $_.FullName).Hash.ToLowerInvariant()
    }
  })
}
$manifest | ConvertTo-Json -Depth 10 | Set-Content -Encoding UTF8 (Join-Path $staging "release_manifest.json")

$zipPath = Join-Path $OutDir "$releaseName`_win64.zip"
if (Test-Path $zipPath) { Remove-Item -Force $zipPath }
Compress-Archive -Path $staging -DestinationPath $zipPath
$zipHash = (Get-FileHash -Algorithm SHA256 $zipPath).Hash.ToLowerInvariant()

Write-Host ""
Write-Host "=== Release built ==="
Write-Host "Zip:    $zipPath"
Write-Host "SHA256: $zipHash"
Write-Host "Files:  $($files.Count)"
