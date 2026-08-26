# Runs ON the cloud Windows host. Bakes one map using local bar_data + startscript.
param(
  [Parameter(Mandatory = $true)][string]$BarDataRoot,
  [Parameter(Mandatory = $true)][string]$StartscriptPath,
  [Parameter(Mandatory = $true)][string]$MapId,
  [Parameter(Mandatory = $true)][string]$ResultDir,
  [string]$EngineRel = "engine\recoil_2025.06.24",
  [int]$TimeoutSeconds = 3600,
  [int]$GrowFrames = 0
)

$ErrorActionPreference = "Stop"

function Quote-ProcessArg([string]$Arg) {
  if ($Arg -match '[\s"]') { return '"' + ($Arg.Replace('"', '\"')) + '"' }
  return $Arg
}

if (!(Test-Path $BarDataRoot)) { throw "BarDataRoot missing: $BarDataRoot" }
if (!(Test-Path $StartscriptPath)) { throw "Startscript missing: $StartscriptPath" }

$engineDir = Join-Path $BarDataRoot $EngineRel
$engine = Join-Path $engineDir "spring-headless.exe"
if (!(Test-Path $engine)) {
  # Fallback: newest engine with spring-headless.exe
  $engineRoot = Join-Path $BarDataRoot "engine"
  $dirs = Get-ChildItem $engineRoot -Directory -ErrorAction SilentlyContinue |
    Where-Object { Test-Path (Join-Path $_.FullName "spring-headless.exe") } |
    Sort-Object Name -Descending
  if (-not $dirs) { throw "spring-headless.exe not found under $BarDataRoot\engine" }
  $engineDir = $dirs[0].FullName
  $engine = Join-Path $engineDir "spring-headless.exe"
}

New-Item -ItemType Directory -Force -Path $ResultDir | Out-Null
$runStamp = Get-Date -Format "yyyyMMdd_HHmmss"
$runDir = Join-Path $ResultDir "${MapId}_$runStamp"
New-Item -ItemType Directory -Force -Path $runDir | Out-Null
Copy-Item -Force -LiteralPath $StartscriptPath -Destination (Join-Path $runDir "bake_startscript.txt")

# Headless settings that avoid IconsAtlas stall (learning from local Phase B).
$settingsPath = Join-Path $BarDataRoot "springsettings.cfg"
$settingsBak = Join-Path $runDir "springsettings.pre_bake.cfg"
$didSettingsPatch = $false
$patch = @"

VerdanceCloudShellBake = 1
UnitIconsAsUI = 0
UnitIconDist = 99999
MinimapIconScale = 0.1
LuaUI = 0
SplashScreenDir =
"@
if (Test-Path $settingsPath) {
  Copy-Item -Force -LiteralPath $settingsPath -Destination $settingsBak
  $settingsText = Get-Content -Raw -LiteralPath $settingsPath
  if ($settingsText -notmatch "VerdanceCloudShellBake") {
    Set-Content -Encoding ASCII -Path $settingsPath -Value ($settingsText.TrimEnd() + "`r`n" + $patch)
    $didSettingsPatch = $true
  }
} else {
  Set-Content -Encoding ASCII -Path $settingsPath -Value $patch.Trim()
  $didSettingsPatch = $true
  $settingsBak = $null
}

if ($TimeoutSeconds -le 0) {
  if ($GrowFrames -gt 0) { $TimeoutSeconds = [Math]::Max(1200, [int]($GrowFrames / 8) + 480) }
  else { $TimeoutSeconds = 3600 }
}

$argLine = (@("--write-dir", $BarDataRoot, "--isolation", "--only-local", $StartscriptPath) |
  ForEach-Object { Quote-ProcessArg ([string]$_) }) -join " "

Write-Host "CLOUD BAKE map=$MapId engine=$engine timeout=${TimeoutSeconds}s"
Write-Host "Args: $argLine"
Write-Host "cwd=$BarDataRoot"

$psi = [System.Diagnostics.ProcessStartInfo]::new()
$psi.FileName = $engine
$psi.WorkingDirectory = $BarDataRoot
$psi.Arguments = $argLine
$psi.UseShellExecute = $false
$psi.CreateNoWindow = $true
$proc = [System.Diagnostics.Process]::new()
$proc.StartInfo = $psi
[void]$proc.Start()
$ok = $proc.WaitForExit($TimeoutSeconds * 1000)
$exitCode = -1
if (-not $ok) {
  try { $proc.Kill() } catch {}
  Write-Warning "Timed out after ${TimeoutSeconds}s"
  $exitCode = 124
} else {
  $exitCode = $proc.ExitCode
  Write-Host "spring-headless exit: $exitCode"
}

if ($didSettingsPatch) {
  if ($settingsBak -and (Test-Path $settingsBak)) {
    Copy-Item -Force -LiteralPath $settingsBak -Destination $settingsPath
  } elseif (Test-Path $settingsPath) {
    # Minimal file we created — leave headless defaults in place on cloud.
  }
}

$infolog = Join-Path $BarDataRoot "infolog.txt"
if (Test-Path $infolog) {
  Copy-Item -Force -LiteralPath $infolog -Destination (Join-Path $runDir "infolog.txt")
}

# Extract unit lines for lightweight transfer.
if (Test-Path (Join-Path $runDir "infolog.txt")) {
  $lines = Get-Content -LiteralPath (Join-Path $runDir "infolog.txt")
  $shellLines = @($lines | Where-Object { $_ -match 'VA_SHELL_' })
  $shellLines | Set-Content -Encoding UTF8 -LiteralPath (Join-Path $runDir "shell_markers.txt")
  $unitCount = @($shellLines | Where-Object { $_ -match 'VA_SHELL_UNIT\s+' }).Count
  $armed = @($shellLines | Where-Object { $_ -match 'VA_SHELL_BAKE_ARMED' }).Count -gt 0
  $dumped = @($shellLines | Where-Object { $_ -match 'VA_SHELL_DUMP_BEGIN' }).Count -gt 0
} else {
  $unitCount = 0
  $armed = $false
  $dumped = $false
}

$result = [ordered]@{
  schemaVersion = "verdance-cloud-bake-result/1.0"
  mapId = $MapId
  ok = ($unitCount -gt 0 -and $dumped)
  exitCode = $exitCode
  timedOut = (-not $ok)
  unitCount = $unitCount
  armed = $armed
  dumped = $dumped
  runDir = $runDir
  engine = $engine
  finishedAt = (Get-Date).ToString("s")
}
($result | ConvertTo-Json -Depth 4) | Set-Content -Encoding UTF8 -LiteralPath (Join-Path $runDir "result.json")
($result | ConvertTo-Json -Depth 4) | Set-Content -Encoding UTF8 -LiteralPath (Join-Path $ResultDir "${MapId}_latest.json")

Write-Host "Result: units=$unitCount armed=$armed dumped=$dumped ok=$($result.ok)"
Write-Host "RUNDIR=$runDir"
if (-not $result.ok) { exit 2 }
exit 0
