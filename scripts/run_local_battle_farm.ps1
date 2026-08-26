# Run a battle-farm shell bake on THIS machine (no cloud).
# Default: Koom Valley 1v1 BARb hard_aggressive -> ~T2 mid claim package.
# Launch contract matches bake_living_shell.ps1 (quoted paths, barDataRoot write-dir,
# isolation, IconsAtlas-avoiding springsettings patch).
param(
  [string]$Workspace = "",
  [string]$MapId = "koom_valley",
  [string]$RecipePath = "",
  [switch]$PackageOnly,
  [switch]$SkipEngine,
  [int]$TimeoutSeconds = 0
)

$ErrorActionPreference = "Stop"
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
. (Join-Path $here "_common.ps1")
$Workspace = Get-VerdanceWorkspaceRoot -Workspace $Workspace
$config = Get-VerdanceConfig -Workspace $Workspace

if (-not $RecipePath) {
  $RecipePath = Join-Path $Workspace "data\base_templates\$MapId\bake_recipe_t2_battle_1v1.json"
}
if (!(Test-Path $RecipePath)) { throw "Missing battle recipe: $RecipePath" }

Write-Host "=== Local battle farm ==="
Write-Host "Recipe: $RecipePath"

# 1) Package startscript + queue (offline-safe).
$pkg = & powershell -ExecutionPolicy Bypass -File (Join-Path $here "package_battle_farm.ps1") `
  -Workspace $Workspace -RecipePath $RecipePath -MapId $MapId
if ($LASTEXITCODE -ne 0 -and -not $pkg) { throw "package_battle_farm failed" }

$latest = Join-Path $Workspace "outbox\battle_farm_bundle.latest.json"
if (!(Test-Path $latest)) { throw "Missing battle_farm_bundle.latest.json after package" }
$queue = Get-Content -Raw -LiteralPath $latest | ConvertFrom-Json
$bundleName = [string]$queue.bundleName
$bundleRoot = Join-Path $Workspace "headless_runs\cloud\$bundleName"
if (!(Test-Path $bundleRoot)) {
  $cand = Get-ChildItem (Join-Path $Workspace "headless_runs\cloud") -Directory -Filter "battle_farm_*" |
    Sort-Object LastWriteTime -Descending | Select-Object -First 1
  if ($cand) { $bundleRoot = $cand.FullName; $bundleName = $cand.Name }
}
Write-Host "Bundle: $bundleRoot"

if ($PackageOnly -or $SkipEngine) {
  Write-Host "PackageOnly/SkipEngine: startscript ready under $bundleRoot"
  Write-Host "Run without -SkipEngine to launch spring-headless."
  return $bundleRoot
}

$job = $queue.jobs[0]
$scriptRel = [string]$job.startscriptRel
$scriptPath = Join-Path $bundleRoot $scriptRel
if (!(Test-Path $scriptPath)) { throw "Missing startscript: $scriptPath" }

$engineDir = Get-BAREngineDir -Config $config -EngineName "spring-headless.exe"
$engine = Join-Path $engineDir "spring-headless.exe"
if (!(Test-Path $engine)) { throw "spring-headless.exe not found at $engine" }

$growFrames = if ($job.growFrames) { [int]$job.growFrames } else { 39600 }
if ($TimeoutSeconds -le 0) {
  $TimeoutSeconds = [Math]::Max(2400, [int]($growFrames / 6) + 900)
}

$barDataRoot = if ($config.barDataRoot) { [string]$config.barDataRoot } else { Split-Path -Parent $engineDir }

function Quote-ProcessArg([string]$Arg) {
  if ($Arg -match '[\s"]') { return '"' + ($Arg.Replace('"', '\"')) + '"' }
  return $Arg
}

# IconsAtlas hang avoidance (same patch as bake_living_shell).
$settingsPath = Join-Path $barDataRoot "springsettings.cfg"
$settingsBak = Join-Path $bundleRoot "springsettings.pre_battle.cfg"
$didSettingsPatch = $false
if (Test-Path $settingsPath) {
  Copy-Item -Force -LiteralPath $settingsPath -Destination $settingsBak
  $settingsText = Get-Content -Raw -LiteralPath $settingsPath
  $patch = @"

// Verdance battle-farm headless overrides (restored after bake)
UnitIconsAsUI = 0
UnitIconDist = 99999
MinimapIconScale = 0.1
LuaUI = 0
SplashScreenDir =
"@
  if ($settingsText -notmatch "Verdance battle-farm headless") {
    Set-Content -Encoding ASCII -Path $settingsPath -Value ($settingsText.TrimEnd() + "`r`n" + $patch)
    $didSettingsPatch = $true
  }
}

$argLine = (@("--write-dir", $barDataRoot, "--isolation", "--only-local", $scriptPath) |
  ForEach-Object { Quote-ProcessArg ([string]$_) }) -join " "

Write-Host "Engine: $engine"
Write-Host "Startscript: $scriptPath"
Write-Host "TimeoutSeconds: $TimeoutSeconds growFrames: $growFrames"
Write-Host "WriteDir: $barDataRoot (isolation)"
Write-Host "Args: $argLine"
Write-Host "NOTE: if IconsAtlas hangs past ~2 min with no frame progress, kill and revisit cloud."

$psi = [System.Diagnostics.ProcessStartInfo]::new()
$psi.FileName = $engine
$psi.WorkingDirectory = $barDataRoot
$psi.Arguments = $argLine
$psi.UseShellExecute = $false
$psi.CreateNoWindow = $true
$proc = [System.Diagnostics.Process]::new()
$proc.StartInfo = $psi
[void]$proc.Start()
Write-Host ("Headless pid={0}" -f $proc.Id)

$ok = $proc.WaitForExit($TimeoutSeconds * 1000)
if (-not $ok) {
  try { $proc.Kill() } catch {}
  if ($didSettingsPatch -and (Test-Path $settingsBak)) {
    Copy-Item -Force -LiteralPath $settingsBak -Destination $settingsPath
  }
  throw "Battle farm timed out after ${TimeoutSeconds}s. Bundle: $bundleRoot"
}

if ($didSettingsPatch -and (Test-Path $settingsBak)) {
  Copy-Item -Force -LiteralPath $settingsBak -Destination $settingsPath
  Write-Host "Restored springsettings.cfg after bake."
}

# Harvest infolog into bundle
$isoInfolog = Join-Path $barDataRoot "infolog.txt"
if (Test-Path $isoInfolog) {
  Copy-Item -Force -LiteralPath $isoInfolog -Destination (Join-Path $bundleRoot "infolog.txt")
}

Write-Host ("spring-headless exit: {0}" -f $proc.ExitCode)
Write-Host "Bundle: $bundleRoot"
Write-Host "Next after dump: apply_shell_strip.ps1 with strip_filter_t2_battle.json"
return $bundleRoot
