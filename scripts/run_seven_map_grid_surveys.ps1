param(
  [string]$Workspace = "$env:USERPROFILE\Documents\BAR_Verdance_Workspace",
  [int]$MaxFrames = 1800,
  [int]$TimeoutSeconds = 900,
  [switch]$SkipPatchInstall
)

$ErrorActionPreference = "Continue"
. (Join-Path (Split-Path -Parent $MyInvocation.MyCommand.Path) "_common.ps1")

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$poolPath = Join-Path $Workspace "data\map_pool\seven_maps.json"
$pool = Get-Content -Raw -LiteralPath $poolPath | ConvertFrom-Json
$profiler = Join-Path $scriptDir "run_translation_profiler.ps1"
$installPatch = Join-Path $scriptDir "install_balance_telemetry_patch.ps1"

if (-not $SkipPatchInstall) {
  & powershell -ExecutionPolicy Bypass -File $installPatch -Workspace $Workspace
  if ($LASTEXITCODE -ne 0) { throw "Telemetry patch install failed." }
}

$stamp = Get-Date -Format "yyyyMMdd_HHmmss"
$suiteDir = Join-Path $Workspace ("reports\map_surveys\grid_battle_suite_$stamp")
New-Item -ItemType Directory -Force -Path $suiteDir | Out-Null

$results = @()
foreach ($map in @($pool.maps)) {
  $scenarioPath = Join-Path $Workspace ("data\scenarios\generated\{0}.grid_survey.json" -f $map.id)
  $logPath = Join-Path $suiteDir ("{0}.runner.log.txt" -f $map.id)
  Write-Host ""
  Write-Host "=== Verdance grid battle survey: $($map.title) ==="
  Write-Host "Scenario: $scenarioPath"

  $started = Get-Date
  $output = & powershell -ExecutionPolicy Bypass -File $profiler `
    -Workspace $Workspace `
    -ScenarioPath $scenarioPath `
    -Variant grid_survey `
    -MaxFrames $MaxFrames `
    -TimeoutSeconds $TimeoutSeconds `
    -QuitAfterLast `
    -SkipPatchInstall 2>&1
  $exit = $LASTEXITCODE
  $output | Set-Content -Encoding UTF8 -Path $logPath

  $runDir = $null
  foreach ($line in $output) {
    if ($line -match '^Suite dir:\s+(.+)$') { $runDir = $Matches[1].Trim() }
  }
  $dataPath = if ($runDir) { Join-Path $runDir "calibration_data.json" } else { $null }
  $reportPath = if ($runDir) { Join-Path $runDir "calibration_report.md" } else { $null }
  $observedTelemetry = 0
  $observedTranslation = 0
  if ($dataPath -and (Test-Path $dataPath)) {
    try {
      $data = Get-Content -Raw -LiteralPath $dataPath | ConvertFrom-Json
      $observedTelemetry = [int]$data.observedTelemetryPackets
      $observedTranslation = [int]$data.observedPackets
    } catch {
    }
  }

  $results += [ordered]@{
    id = $map.id
    title = $map.title
    mapName = $map.mapName
    status = if ($exit -eq 0) { "completed" } else { "failed" }
    exitCode = $exit
    startedAt = $started.ToString("s")
    finishedAt = (Get-Date).ToString("s")
    scenarioPath = $scenarioPath
    runDir = $runDir
    calibrationDataPath = $dataPath
    calibrationReportPath = $reportPath
    runnerLogPath = $logPath
    observedTelemetryPackets = $observedTelemetry
    observedTranslationPackets = $observedTranslation
  }

  if ($exit -eq 0) {
    Write-Host "Completed $($map.title): telemetry=$observedTelemetry translation=$observedTranslation"
  } else {
    Write-Warning "Failed $($map.title): exit=$exit. Continuing."
  }
}

$manifest = [ordered]@{
  schemaVersion = "verdance-grid-battle-suite/0.1"
  generatedAt = (Get-Date).ToString("s")
  maxFrames = $MaxFrames
  timeoutSeconds = $TimeoutSeconds
  suiteDir = $suiteDir
  results = $results
}
$manifestPath = Join-Path $suiteDir "manifest.json"
Save-Json $manifest $manifestPath
Copy-Item -Force -LiteralPath $manifestPath -Destination (Join-Path $Workspace "reports\map_surveys\latest_grid_battle_suite.json")

Write-Host ""
Write-Host "Seven-map grid battle suite complete."
Write-Host "Manifest: $manifestPath"
