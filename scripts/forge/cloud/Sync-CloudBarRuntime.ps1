# One-time (or force) sync of engine + seven maps + BAR.sdd + VerdanceAshes to cloud host.
param(
  [string]$Workspace = "",
  [switch]$Force,
  [switch]$SkipBarSdd,
  [switch]$MapsOnly,
  [switch]$ModOnly
)

$ErrorActionPreference = "Stop"
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
. (Join-Path (Split-Path -Parent $here) "_common.ps1")
. (Join-Path $here "_cloud_common.ps1")
$Workspace = Get-VerdanceWorkspaceRoot -Workspace $Workspace
$config = Get-VerdanceConfig -Workspace $Workspace
$cloud = Get-CloudConfig -Workspace $Workspace

if ($cloud.remoteOs -and [string]$cloud.remoteOs -ne "windows") {
  Write-Warning "remoteOs=$($cloud.remoteOs): this sync ships Windows spring-headless.exe. Use a Windows VM or provision a Linux engine separately."
}

$remoteRoot = [string]$cloud.remoteRoot
$remoteBar = [string]$cloud.remoteBarData
$engineTag = if ($cloud.engineTag) { [string]$cloud.engineTag } else { "recoil_2025.06.24" }

# Ensure remote directories exist.
$mk = "powershell -NoProfile -Command `"New-Item -ItemType Directory -Force -Path '$remoteRoot','$remoteBar','$remoteBar\engine','$remoteBar\maps','$remoteBar\games','$($cloud.remoteJobs)','$($cloud.remoteResults)' | Out-Null`""
Invoke-RemoteSsh -CloudConfig $cloud -RemoteCommand $mk

$localBar = [string]$config.barDataRoot
if (!(Test-Path $localBar)) { throw "Local barDataRoot missing: $localBar" }

function Sync-TreeOrFile {
  param([string]$Local, [string]$Remote, [switch]$Dir)
  if (!(Test-Path $Local)) { throw "Missing local path: $Local" }
  # scp -r of large trees works; for multi-GB BAR.sdd this can take a while.
  Copy-ToRemote -CloudConfig $cloud -LocalPath $Local -RemotePath $Remote -Recursive:$Dir
}

if ($ModOnly) {
  $modLocal = Join-Path $Workspace "mod\VerdanceAshes.sdd"
  if (!(Test-Path $modLocal)) { $modLocal = [string]$config.modSdd }
  Sync-TreeOrFile -Local $modLocal -Remote "$remoteBar\games\VerdanceAshes.sdd" -Dir
  Write-Host "Mod-only sync complete."
  return
}

if (-not $MapsOnly) {
  # Engine (Windows)
  $engineLocal = Join-Path $localBar "engine\$engineTag"
  if (!(Test-Path $engineLocal)) {
    $engineLocal = Get-BAREngineDir -Config $config -EngineName "spring-headless.exe"
    $engineTag = Split-Path -Leaf $engineLocal
  }
  Write-Host "Syncing engine $engineTag (~95MB)..."
  Sync-TreeOrFile -Local $engineLocal -Remote "$remoteBar\engine\$engineTag" -Dir
}

# Seven campaign maps only (not the whole 196-map catalog).
Write-Host "Syncing seven campaign maps..."
$archives = Get-SevenMapArchiveNames -Workspace $Workspace
$mapsLocal = Join-Path $localBar "maps"
foreach ($arch in $archives) {
  $src = Join-Path $mapsLocal $arch
  if (!(Test-Path $src)) { Write-Warning "Map archive missing locally: $src"; continue }
  Write-Host "  $arch"
  Copy-ToRemote -CloudConfig $cloud -LocalPath $src -RemotePath "$remoteBar\maps\$arch"
  $md5 = "$src.md5.gz"
  if (Test-Path $md5) {
    Copy-ToRemote -CloudConfig $cloud -LocalPath $md5 -RemotePath "$remoteBar\maps\$arch.md5.gz"
  }
}

if ($MapsOnly) {
  Write-Host "Maps-only sync complete."
  return
}

# Verdance mod from workspace (always newest gadgets).
$modLocal = Join-Path $Workspace "mod\VerdanceAshes.sdd"
if (!(Test-Path $modLocal)) { $modLocal = [string]$config.modSdd }
Write-Host "Syncing VerdanceAshes.sdd..."
Sync-TreeOrFile -Local $modLocal -Remote "$remoteBar\games\VerdanceAshes.sdd" -Dir

if (-not $SkipBarSdd -and (-not ($cloud.sync -and $cloud.sync.barSdd -eq $false))) {
  $barSdd = Join-Path $localBar "games\BAR.sdd"
  if (Test-Path $barSdd) {
    Write-Host "Syncing BAR.sdd (large, ~3GB — one-time)..."
    Write-Host "  This may take a long time depending on uplink."
    Sync-TreeOrFile -Local $barSdd -Remote "$remoteBar\games\BAR.sdd" -Dir
  } else {
    Write-Warning "BAR.sdd not found at $barSdd — remote must already have base game content."
  }
}

# Ship remote worker into remoteRoot/scripts
Invoke-RemoteSsh -CloudConfig $cloud -RemoteCommand "powershell -NoProfile -Command `"New-Item -ItemType Directory -Force -Path '$remoteRoot\scripts' | Out-Null`""
$worker = Join-Path $here "remote_worker_bake.ps1"
Copy-ToRemote -CloudConfig $cloud -LocalPath $worker -RemotePath "$remoteRoot\scripts\remote_worker_bake.ps1"

$marker = [ordered]@{
  syncedAt = (Get-Date).ToString("s")
  engineTag = $engineTag
  maps = @($archives)
  host = [string]$cloud.host
  remoteBarData = $remoteBar
}
($marker | ConvertTo-Json -Depth 4) | Set-Content -Encoding UTF8 -LiteralPath (Join-Path $Workspace "outbox\cloud_runtime_sync.latest.json")
Write-Host "Cloud BAR runtime sync complete -> $remoteBar"
