param(
  [string]$Workspace = "$env:USERPROFILE\Documents\BAR_Verdance_Workspace",
  [string]$MilestoneMinutes = "1,2,3,5,8,13,21",
  [string[]]$MapIds = @(),
  [int]$TimeoutSecondsPerMap = 7200,
  [switch]$SkipPatchInstall
)

$ErrorActionPreference = "Continue"
. (Join-Path (Split-Path -Parent $MyInvocation.MyCommand.Path) "_common.ps1")

function Get-MaxFrameFromMinutes {
  param([string]$Minutes)
  $max = 0
  foreach ($part in ($Minutes -split ',')) {
    $trim = $part.Trim()
    if (-not $trim) { continue }
    $frame = [int]([double]$trim * 60 * 30)
    if ($frame -gt $max) { $max = $frame }
  }
  return $max
}

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$poolPath = Join-Path $Workspace "data\map_pool\seven_maps.json"
$pool = Get-Content -Raw -LiteralPath $poolPath | ConvertFrom-Json
$maps = @($pool.maps)
if ($MapIds.Count -eq 1 -and $MapIds[0] -match ',') {
  $MapIds = @($MapIds[0] -split ',' | ForEach-Object { $_.Trim() } | Where-Object { $_ })
}
if ($MapIds.Count -gt 0) {
  $wanted = @{}
  foreach ($id in $MapIds) { $wanted[$id] = $true }
  $maps = @($maps | Where-Object { $wanted.ContainsKey([string]$_.id) })
  if ($maps.Count -eq 0) { throw "No maps matched MapIds: $($MapIds -join ', ')" }
}
$profiler = Join-Path $scriptDir "run_translation_profiler.ps1"
$installPatch = Join-Path $scriptDir "install_balance_telemetry_patch.ps1"

if (-not $SkipPatchInstall) {
  & powershell -ExecutionPolicy Bypass -File $installPatch -Workspace $Workspace
  if ($LASTEXITCODE -ne 0) { throw "Telemetry patch install failed." }
}

$maxFrames = Get-MaxFrameFromMinutes $MilestoneMinutes
if ($maxFrames -le 0) { throw "No valid milestone minutes: $MilestoneMinutes" }

$stamp = Get-Date -Format "yyyyMMdd_HHmmss"
$suiteDir = Join-Path $Workspace ("reports\map_surveys\authored_long_suite_$stamp")
New-Item -ItemType Directory -Force -Path $suiteDir | Out-Null

$results = @()

$manifestPath = Join-Path $suiteDir "manifest.json"
$latestPath = Join-Path $Workspace "reports\map_surveys\latest_authored_long_suite.json"
function Save-PartialManifest {
  param([string]$Status)
  $manifest = [ordered]@{
    schemaVersion = "verdance-authored-long-suite/0.2"
    generatedAt = (Get-Date).ToString("s")
    status = $Status
    milestoneMinutes = $MilestoneMinutes
    mapIds = @($maps | ForEach-Object { $_.id })
    maxFrames = $maxFrames
    timeoutSecondsPerMap = $TimeoutSecondsPerMap
    suiteDir = $suiteDir
    results = $results
  }
  Save-Json $manifest $manifestPath
  Copy-Item -Force -LiteralPath $manifestPath -Destination $latestPath
}

Save-PartialManifest "started"

foreach ($map in @($maps)) {
  $scenarioPath = Join-Path $Workspace ("data\scenarios\authored\{0}.authored_baseline.json" -f $map.id)
  $logPath = Join-Path $suiteDir ("{0}.runner.log.txt" -f $map.id)
  Write-Host ""
  Write-Host "=== Verdance authored long survey: $($map.title) ==="
  Write-Host "Scenario: $scenarioPath"
  Write-Host "Milestones minutes: $MilestoneMinutes"

  $started = Get-Date
  $results += [ordered]@{
    id = $map.id
    title = $map.title
    mapName = $map.mapName
    status = "running"
    exitCode = $null
    startedAt = $started.ToString("s")
    finishedAt = $null
    scenarioPath = $scenarioPath
    runDir = $null
    calibrationDataPath = $null
    calibrationReportPath = $null
    runnerLogPath = $logPath
    observedTelemetryPackets = 0
    observedTranslationPackets = 0
    lastVerdict = "running"
    lastFrame = 0
  }
  Save-PartialManifest "running"

  $output = & powershell -ExecutionPolicy Bypass -File $profiler `
    -Workspace $Workspace `
    -ScenarioPath $scenarioPath `
    -Variant authored_baseline `
    -MaxFrames $maxFrames `
    -MilestoneMinutes $MilestoneMinutes `
    -TimeoutSeconds $TimeoutSecondsPerMap `
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
  $lastVerdict = "unknown"
  $lastFrame = 0
  if ($dataPath -and (Test-Path $dataPath)) {
    try {
      $data = Get-Content -Raw -LiteralPath $dataPath | ConvertFrom-Json
      $observedTelemetry = [int]$data.observedTelemetryPackets
      $observedTranslation = [int]$data.observedPackets
      $last = @($data.snapshots | Where-Object { $_.balance } | Select-Object -Last 1)
      if ($last) {
        $lastVerdict = [string]$last.balance.verdict
        $lastFrame = [int]$last.actualFrame
      }
    } catch {
    }
  }

  $current = $results[$results.Count - 1]
  $current.status = if ($exit -eq 0) { "completed" } else { "failed" }
  $current.exitCode = $exit
  $current.finishedAt = (Get-Date).ToString("s")
  $current.runDir = $runDir
  $current.calibrationDataPath = $dataPath
  $current.calibrationReportPath = $reportPath
  $current.observedTelemetryPackets = $observedTelemetry
  $current.observedTranslationPackets = $observedTranslation
  $current.lastVerdict = $lastVerdict
  $current.lastFrame = $lastFrame
  Save-PartialManifest "running"

  if ($exit -eq 0) {
    Write-Host "Completed $($map.title): telemetry=$observedTelemetry translation=$observedTranslation lastVerdict=$lastVerdict"
  } else {
    Write-Warning "Failed $($map.title): exit=$exit. Continuing."
  }
}

Save-PartialManifest "completed"

Write-Host ""
Write-Host "Seven-map authored long suite complete."
Write-Host "Manifest: $manifestPath"
