param(
  [string]$Workspace = "",
  [string]$ScenarioPath = "",
  [string]$Variant = "simple_defenders",
  [string[]]$PlayerControllers = @("simple", "barbarian_aggressive"),
  [int]$SimFrames = 5400,
  [int]$TimeoutSeconds = 360,
  [switch]$SkipPatchInstall
)

$ErrorActionPreference = "Stop"
. (Join-Path (Split-Path -Parent $MyInvocation.MyCommand.Path) "_common.ps1")
$Workspace = Get-VerdanceWorkspaceRoot -Workspace $Workspace

if (-not $ScenarioPath) {
  $ScenarioPath = Join-Path $Workspace "data\scenarios\all_that_simmers.playable.json"
}
if (!(Test-Path $ScenarioPath)) { throw "Scenario file not found: $ScenarioPath" }
if ($PlayerControllers.Count -eq 1 -and $PlayerControllers[0] -match ',') {
  $PlayerControllers = @($PlayerControllers[0] -split ',' | ForEach-Object { $_.Trim() } | Where-Object { $_ })
}

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$installPatch = Join-Path $scriptDir "install_balance_telemetry_patch.ps1"
$installPlayable = Join-Path $scriptDir "install_playable_slice.ps1"
$extractTelemetry = Join-Path $scriptDir "extract_latest_telemetry.ps1"
$analyzeMatch = Join-Path $scriptDir "analyze_bar_match.ps1"

if (-not $SkipPatchInstall) {
  & powershell -ExecutionPolicy Bypass -File $installPatch -Workspace $Workspace
}

$runRoot = Join-Path $Workspace "headless_runs"
New-Item -ItemType Directory -Force -Path $runRoot | Out-Null
$stamp = Get-Date -Format "yyyyMMdd_HHmmss"
$suiteDir = Join-Path $runRoot "balance_$stamp"
New-Item -ItemType Directory -Force -Path $suiteDir | Out-Null

$results = @()

foreach ($controller in $PlayerControllers) {
  $safe = ($controller -replace '[^A-Za-z0-9_-]', '_')
  $runDir = Join-Path $suiteDir $safe
  New-Item -ItemType Directory -Force -Path $runDir | Out-Null
  $logPath = Join-Path $runDir "runner.log.txt"
  $telemetryPath = Join-Path $runDir "bar_zone_telemetry.json"
  $analysisDir = Join-Path $runDir "analysis"

  Write-Host "Running balance test: variant=$Variant playerController=$controller simFrames=$SimFrames"
  $playableArgs = @(
    "-ExecutionPolicy", "Bypass",
    "-File", $installPlayable,
    "-Workspace", $Workspace,
    "-ScenarioPath", $ScenarioPath,
    "-Variant", $Variant,
    "-PlayerController", $controller,
    "-BalanceTest",
    "-SimFrames", ([string]$SimFrames),
    "-TimeoutSeconds", ([string]$TimeoutSeconds)
  )
  $output = & powershell @playableArgs 2>&1
  $output | Set-Content -Encoding UTF8 -Path $logPath
  if ($LASTEXITCODE -ne 0) {
    throw "Headless balance run failed for controller '$controller'. See $logPath"
  }

  & powershell -ExecutionPolicy Bypass -File $extractTelemetry -Workspace $Workspace -OutPath $telemetryPath
  & powershell -ExecutionPolicy Bypass -File $analyzeMatch -Workspace $Workspace -OutDir $analysisDir

  $telemetry = Get-Content -Raw -LiteralPath $telemetryPath | ConvertFrom-Json
  $result = [ordered]@{
    playerController = $controller
    variant = $Variant
    simFrames = $SimFrames
    frame = $telemetry.frame
    verdict = $telemetry.balance.verdict
    valueRatio = $telemetry.balance.valueRatio
    playerValue = $telemetry.balance.playerValue
    enemyValue = $telemetry.balance.enemyValue
    playerUnitCount = $telemetry.balance.playerUnitCount
    enemyUnitCount = $telemetry.balance.enemyUnitCount
    telemetryPath = $telemetryPath
    latestTelemetryPath = (Join-Path $Workspace "outbox\bar_zone_telemetry.latest.json")
    analysisPath = (Join-Path $analysisDir "bar_match_analysis.latest.json")
    runnerLog = $logPath
  }
  Copy-Item -Force -LiteralPath $telemetryPath -Destination $result.latestTelemetryPath
  $results += $result
}

$simple = @($results | Where-Object { $_.playerController -eq "simple" } | Select-Object -First 1)
$aggressive = @($results | Where-Object { $_.playerController -eq "barbarian_aggressive" } | Select-Object -First 1)
$classification = "inconclusive"
if ($simple -and $aggressive) {
  $simpleStalls = $simple.verdict -in @("player_stalled", "player_dead", "active")
  $aggressiveWins = $aggressive.verdict -in @("player_advantage", "player_clear")
  if ($SimFrames -lt 1800 -and $aggressive.verdict -eq "active") {
    $classification = "needs_longer"
  } elseif ($simpleStalls -and $aggressiveWins) {
    $classification = "target_band"
  } elseif (-not $aggressiveWins) {
    $classification = "too_hard_for_aggressive"
  } elseif (-not $simpleStalls) {
    $classification = "too_easy_for_simple"
  }
}

$manifest = [ordered]@{
  schemaVersion = "verdance-headless-balance-suite/0.1"
  generatedAt = (Get-Date).ToString("s")
  scenarioPath = $ScenarioPath
  variant = $Variant
  simFrames = $SimFrames
  timeoutSeconds = $TimeoutSeconds
  suiteDir = $suiteDir
  classification = $classification
  target = "BARb hard/aggressive should clear or gain advantage while SimpleAI stalls."
  results = $results
}
$manifestPath = Join-Path $suiteDir "manifest.json"
$manifest | ConvertTo-Json -Depth 80 | Set-Content -Encoding UTF8 -Path $manifestPath

$summaryPath = Join-Path $suiteDir "SUMMARY.md"
$lines = @(
  "# Verdance Headless Balance Test",
  "",
  "- Variant: ``$Variant``",
  "- Sim frames: ``$SimFrames``",
  "- Classification: ``$classification``",
  "",
  "| Player Controller | Verdict | Value Ratio | Player Value | Enemy Value | Units |",
  "| --- | --- | ---: | ---: | ---: | ---: |"
)
foreach ($r in $results) {
  $lines += "| $($r.playerController) | $($r.verdict) | $($r.valueRatio) | $($r.playerValue) | $($r.enemyValue) | $($r.playerUnitCount)/$($r.enemyUnitCount) |"
}
$lines | Set-Content -Encoding UTF8 -Path $summaryPath

Write-Host "Headless balance suite complete: $manifestPath"
Write-Host "Classification: $classification"
