<#!
.SYNOPSIS
  Run one real BARbarIAn-controlled Verdance sortie unattended.

.DESCRIPTION
  This is a bounded playtest harness, not a balance shortcut. BAR owns the
  player seat and the Verdance autoplay gadget issues ordinary movement,
  attack, repair, guard, and extraction orders. The headless process is always
  harvested and closed before the script returns.
#>
param(
  [string]$Workspace = "",
  [string]$ScenarioPath = "",
  [string]$Variant = "alpha_player",
  # Windows BAR startup is typically 60-90 seconds before the bridge; leave
  # enough bounded wall time for a normal objective and extraction cycle.
  [int]$TimeoutSeconds = 360,
  [string]$Label = "opening_autoplay"
)

$ErrorActionPreference = "Stop"
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
. (Join-Path $scriptDir "_common.ps1")
$Workspace = Get-VerdanceWorkspaceRoot -Workspace $Workspace
if (-not $ScenarioPath) {
  $ScenarioPath = Join-Path $Workspace "data\scenarios\generated\next_mission_intent.playable.json"
}
if (!(Test-Path -LiteralPath $ScenarioPath)) { throw "Scenario file not found: $ScenarioPath" }

$runRoot = Join-Path $Workspace "reports\playtest_runs"
$stamp = Get-Date -Format "yyyyMMdd_HHmmss"
$runDir = Join-Path $runRoot ("{0}_{1}" -f $stamp, ($Label -replace '[^A-Za-z0-9_-]', '_'))
New-Item -ItemType Directory -Force -Path $runDir | Out-Null
$config = Get-VerdanceConfig -Workspace $Workspace
$infolog = [string]$config.infolog
$baseline = if (Test-Path -LiteralPath $infolog) { (Get-Item -LiteralPath $infolog).Length } else { 0 }
$baselineLineCount = if (Test-Path -LiteralPath $infolog) {
  @(Get-Content -LiteralPath $infolog -ErrorAction SilentlyContinue).Count
} else { 0 }

# Keep the test long enough to show approach, contact, objective damage, and
# extraction, while Fibonacci markers provide compact checkpoints in the log.
$extra = @(
  "va_headless_autostart=1",
  "va_headless_fastwin=0",
  "va_headless_quit=1",
  "va_no_ui=1",
  "va_autoplay=1",
  "va_play_track=1",
  "va_dev_sample_period=150",
  "va_headless_speed=20",
  "va_fib_export_frames=1800,3600,5400,9000",
  "va_fib_quit=1"
) -join ";"
$debug = "90:luarules vazones|120:luarules vastatus"
$runnerLog = Join-Path $runDir "runner.log.txt"
$infologCopy = Join-Path $runDir "infolog.txt"
$startScript = Join-Path $Workspace ("playable_runs\verdance_playable_{0}_{1}.txt" -f $Variant, "alpha_player")
$engineConfig = Join-Path $runDir "headless.cfg"
@(
  "UnitIconDist=0",
  "UnitIconsAsUI=0",
  "BuildIconsFirst=0",
  "LuaUI=0",
  "ShowClock=0",
  "ShowFPS=0",
  "ShowPlayerInfo=0",
  "ShowSpeed=0",
  "Sound=0",
  "Shadows=-1",
  "Water=0"
) | Set-Content -Encoding ASCII -LiteralPath $engineConfig
$runError = $null

try {
  # A stale visible BAR session can otherwise consume the machine or share the
  # infolog. This harness owns the test slot and clears only BAR engine processes.
  @(Get-Process -Name "spring", "spring-headless" -ErrorAction SilentlyContinue) |
    ForEach-Object { try { Stop-Process -Id $_.Id -Force } catch {} }
  Start-Sleep -Seconds 2

  $installer = Join-Path $scriptDir "install_playable_slice.ps1"
  $args = @(
    "-ExecutionPolicy", "Bypass",
    "-File", $installer,
    "-Workspace", $Workspace,
    "-ScenarioPath", $ScenarioPath,
    "-Variant", $Variant,
    "-PlayerController", "barbarian_aggressive",
    "-Headless",
    "-TimeoutSeconds", ([string]$TimeoutSeconds),
    "-ExtraModOptions", $extra,
    "-DebugCommandsOverride", $debug,
    "-EngineConfigPath", $engineConfig
  )
  $output = & powershell @args 2>&1
  $output | Set-Content -Encoding UTF8 -LiteralPath $runnerLog
  if ($LASTEXITCODE -ne 0) { $runError = "Autoplay installer failed with exit code $LASTEXITCODE." }
} catch {
  $runError = ($_ | Out-String)
} 
finally {
  if (Test-Path -LiteralPath $infolog) {
    Copy-Item -Force -LiteralPath $infolog -Destination $infologCopy
  }
  @(Get-Process -Name "spring", "spring-headless" -ErrorAction SilentlyContinue) |
    ForEach-Object { try { Stop-Process -Id $_.Id -Force } catch {} }
}

$logLines = if (Test-Path -LiteralPath $infologCopy) { @(Get-Content -LiteralPath $infologCopy) } else { @() }
$copyLength = if (Test-Path -LiteralPath $infologCopy) { (Get-Item -LiteralPath $infologCopy).Length } else { 0 }
$runLogLines = if ($copyLength -lt $baseline -or $logLines.Count -lt $baselineLineCount) {
  # BAR isolation can replace infolog.txt instead of appending to it.
  $logLines
} elseif ($logLines.Count -gt $baselineLineCount) {
  @($logLines | Select-Object -Skip $baselineLineCount)
} else { @() }
$markers = [ordered]@{}
foreach ($name in @(
  "VA_AUTOPLAY_ARMED", "VA_AUTOPLAY phase=", "VA_OBJECTIVE_COMPLETE",
  "VA_TERMINAL", "VA_RESULT_JSON_COMPACT", "VA_RESULT_JSON_END", "VA_FIB_MILESTONE",
  "VA_TRANSLATION_OK", "VA_ZONE_FLOW_JSON"
)) {
  $markers[$name] = @($runLogLines | Where-Object { $_ -like "*$name*" }).Count
}
if (-not $runError -and $markers["VA_AUTOPLAY_ARMED"] -lt 1) {
  $runError = "Current BAR run produced no VA_AUTOPLAY_ARMED marker; refusing to report a stale or empty smoke as completed."
} elseif (-not $runError -and $markers["VA_RESULT_JSON_END"] -lt 1) {
  $runError = "Current BAR run produced no complete terminal result packet."
}
$manifest = [ordered]@{
  schemaVersion = "verdance-autoplay-run/1.0"
  status = if ($runError) { "failed" } else { "completed" }
  generatedAt = (Get-Date).ToUniversalTime().ToString("o")
  scenarioPath = $ScenarioPath
  variant = $Variant
  controller = "barbarian_aggressive"
  autoplay = $true
  infologBaselineLength = $baseline
  runnerLog = $runnerLog
  infolog = $infologCopy
  markers = $markers
  infologBaselineLineCount = $baselineLineCount
  currentRunLogLineCount = $runLogLines.Count
}
$manifest | ConvertTo-Json -Depth 20 | Set-Content -Encoding UTF8 -LiteralPath (Join-Path $runDir "manifest.json")
if ($runError) {
  if (!(Test-Path -LiteralPath $runnerLog)) { $runError | Set-Content -Encoding UTF8 -LiteralPath $runnerLog }
  Write-Warning $runError
  throw $runError
}
Write-Host "Autoplay sortie complete: $runDir"
Write-Host ($markers | ConvertTo-Json -Compress)
