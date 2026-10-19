<#
.SYNOPSIS
  Runs the three-way AI duel matrix unattended and collects per-run zone flow.

.DESCRIPTION
  Serial by design. Every headless run writes into the same BAR write-dir and the
  packet parsers scrape that one infolog.txt, which Spring truncates on each
  launch -- two concurrent runs would interleave their packets and silently
  corrupt both. Throughput comes from the gadget forcing the sim clock to 20x
  under profiling, not from parallelism.

  Resumable: -Resume picks up the newest suite and skips runs already completed,
  so an interrupted night can be continued without repeating work.
#>
param(
  [string]$Workspace = "",
  [string]$MilestoneMinutes = "3,5,8,13,21",
  [string[]]$MapIds = @(),
  [string[]]$Variants = @(),
  [int]$TimeoutSecondsPerRun = 2400,
  [int]$MaxRuns = 0,
  [switch]$Resume,
  [switch]$SkipPatchInstall
)

$ErrorActionPreference = "Continue"
. (Join-Path (Split-Path -Parent $MyInvocation.MyCommand.Path) "_common.ps1")
$Workspace = Get-VerdanceWorkspaceRoot -Workspace $Workspace

function Split-ListArg {
  param([string[]]$Value)
  if ($Value.Count -eq 1 -and $Value[0] -match ',') {
    return @($Value[0] -split ',' | ForEach-Object { $_.Trim() } | Where-Object { $_ })
  }
  return @($Value)
}

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
$profiler = Join-Path $scriptDir "run_translation_profiler.ps1"
$installPatch = Join-Path $scriptDir "install_balance_telemetry_patch.ps1"
$matrixScript = Join-Path $scriptDir "new_ai_duel_matrix.ps1"

$manifestPath = Join-Path $Workspace "reports\map_surveys\ai_duel_matrix_manifest.json"
if (!(Test-Path $manifestPath)) {
  Write-Host "No AI duel matrix yet; generating."
  & powershell -ExecutionPolicy Bypass -File $matrixScript -Workspace $Workspace
  if ($LASTEXITCODE -ne 0) { throw "AI duel matrix generation failed." }
}
if (-not $SkipPatchInstall) {
  & powershell -ExecutionPolicy Bypass -File $installPatch -Workspace $Workspace | Out-Null
}

$matrix = Get-Content -Raw -LiteralPath $manifestPath | ConvertFrom-Json
$runs = @($matrix.runs)

$MapIds = Split-ListArg $MapIds
$Variants = Split-ListArg $Variants
if ($MapIds.Count -gt 0) {
  # Order by the caller's map order, not the manifest's. An overnight suite that
  # runs out of night should have finished the maps that matter most, and the
  # pool order puts the opening theatre last.
  $rank = @{}
  for ($i = 0; $i -lt $MapIds.Count; $i++) { $rank[$MapIds[$i]] = $i }
  $runs = @($runs |
    Where-Object { $rank.ContainsKey([string]$_.mapId) } |
    Sort-Object @{ Expression = { $rank[[string]$_.mapId] } }, @{ Expression = { [string]$_.variant } })
}
if ($Variants.Count -gt 0) {
  $wantedV = @{}
  foreach ($v in $Variants) { $wantedV[$v] = $true }
  $runs = @($runs | Where-Object { $wantedV.ContainsKey([string]$_.variant) })
}
if ($runs.Count -eq 0) { throw "No AI duel runs matched the requested filters." }
if ($MaxRuns -gt 0 -and $runs.Count -gt $MaxRuns) { $runs = @($runs | Select-Object -First $MaxRuns) }

$maxFrames = Get-MaxFrameFromMinutes $MilestoneMinutes
$latestPath = Join-Path $Workspace "reports\map_surveys\latest_ai_duel_suite.json"
$results = @()
$stamp = Get-Date -Format "yyyyMMdd_HHmmss"
$suiteDir = Join-Path $Workspace ("reports\map_surveys\ai_duel_suite_$stamp")

if ($Resume -and (Test-Path $latestPath)) {
  try {
    $previous = Get-Content -Raw -LiteralPath $latestPath | ConvertFrom-Json
    if ($previous.suiteDir -and (Test-Path $previous.suiteDir)) {
      $suiteDir = [string]$previous.suiteDir
      $results = @($previous.results)
      Write-Host "Resuming AI duel suite: $suiteDir ($($results.Count) run(s) already recorded)"
    }
  } catch {
    Write-Warning "Could not resume; starting a new suite. $($_.Exception.Message)"
  }
}
New-Item -ItemType Directory -Force -Path $suiteDir | Out-Null
$suiteManifestPath = Join-Path $suiteDir "manifest.json"

function Save-SuiteManifest {
  param([string]$Status)
  $manifest = [ordered]@{
    schemaVersion = "verdance-ai-duel-suite/0.1"
    generatedAt = (Get-Date).ToString("s")
    status = $Status
    milestoneMinutes = $MilestoneMinutes
    maxFrames = $maxFrames
    timeoutSecondsPerRun = $TimeoutSecondsPerRun
    suiteDir = $suiteDir
    matrixManifestPath = $manifestPath
    runCount = @($runs).Count
    completedCount = @($results | Where-Object { $_.status -eq "completed" }).Count
    results = $results
  }
  Save-Json $manifest $suiteManifestPath
  Copy-Item -Force -LiteralPath $suiteManifestPath -Destination $latestPath
}

Save-SuiteManifest "started"
$index = 0
$suiteStart = Get-Date

foreach ($run in @($runs)) {
  $index += 1
  $already = @($results | Where-Object { $_.id -eq $run.id -and $_.status -eq "completed" } | Select-Object -First 1)
  if ($already) {
    Write-Host "[$index/$($runs.Count)] skip (done): $($run.id)"
    continue
  }

  $safeId = ($run.id -replace '[^A-Za-z0-9_-]', '_')
  $logPath = Join-Path $suiteDir "$safeId.runner.log.txt"
  $runStart = Get-Date
  Write-Host ""
  Write-Host "[$index/$($runs.Count)] $($run.mapTitle): $($run.seatALabel) vs $($run.seatBLabel)"

  $args = @(
    "-ExecutionPolicy", "Bypass",
    "-File", $profiler,
    "-Workspace", $Workspace,
    "-ScenarioPath", ([string]$run.scenarioPath),
    "-Variant", ([string]$run.variant),
    "-MaxFrames", ([string]$maxFrames),
    "-MilestoneMinutes", $MilestoneMinutes,
    "-TimeoutSeconds", ([string]$TimeoutSecondsPerRun),
    "-QuitAfterLast",
    "-SkipPatchInstall"
  )
  $output = & powershell @args 2>&1
  $exit = $LASTEXITCODE
  $output | Set-Content -Encoding UTF8 -Path $logPath

  $runDir = $null
  foreach ($line in $output) {
    if ($line -match '^Suite dir:\s+(.+)$') { $runDir = $Matches[1].Trim() }
  }

  $lastVerdict = "unknown"
  $lastFrame = 0
  $lastRatio = $null
  $lastPlayerValue = $null
  $lastEnemyValue = $null
  $flowEdges = 0
  $flowCrossings = 0
  $observedTelemetry = 0
  $dataPath = if ($runDir) { Join-Path $runDir "calibration_data.json" } else { $null }
  if ($dataPath -and (Test-Path $dataPath)) {
    try {
      $data = Get-Content -Raw -LiteralPath $dataPath | ConvertFrom-Json
      $observedTelemetry = [int]$data.observedTelemetryPackets
      $last = @($data.snapshots | Where-Object { $_.balance } | Select-Object -Last 1)
      if ($last) {
        $lastVerdict = [string]$last.balance.verdict
        $lastFrame = [int]$last.actualFrame
        $lastRatio = [double]$last.balance.valueRatio
        $lastPlayerValue = [double]$last.balance.playerValue
        $lastEnemyValue = [double]$last.balance.enemyValue
      }
      if ($data.zoneFlow -and $data.zoneFlow.edges) {
        $flowEdges = @($data.zoneFlow.edges).Count
        foreach ($e in @($data.zoneFlow.edges)) { $flowCrossings += [int]$e.crossings }
      }
    } catch {
      Write-Warning "Could not parse calibration data for $($run.id): $($_.Exception.Message)"
    }
  }

  $results += [ordered]@{
    id = $run.id
    mapId = $run.mapId
    mapTitle = $run.mapTitle
    variant = $run.variant
    seatA = $run.seatA
    seatB = $run.seatB
    seatALabel = $run.seatALabel
    seatBLabel = $run.seatBLabel
    symmetric = [bool]$run.symmetric
    status = if ($exit -eq 0) { "completed" } else { "failed" }
    exitCode = $exit
    runDir = $runDir
    runnerLogPath = $logPath
    observedTelemetryPackets = $observedTelemetry
    lastVerdict = $lastVerdict
    lastFrame = $lastFrame
    lastRatio = $lastRatio
    lastPlayerValue = $lastPlayerValue
    lastEnemyValue = $lastEnemyValue
    zoneFlowEdges = $flowEdges
    zoneFlowCrossings = $flowCrossings
    elapsedSeconds = [int]((Get-Date) - $runStart).TotalSeconds
    finishedAt = (Get-Date).ToString("s")
  }

  $done = @($results | Where-Object { $_.status -eq "completed" }).Count
  $elapsed = (Get-Date) - $suiteStart
  Write-Host ("    -> {0} ratio={1} flow={2} edges/{3} crossings  [{4}s]  suite {5} done, {6:hh\:mm\:ss} elapsed" -f `
    $lastVerdict, $(if ($null -ne $lastRatio) { [math]::Round($lastRatio, 3) } else { "n/a" }), `
    $flowEdges, $flowCrossings, $results[-1].elapsedSeconds, $done, $elapsed)

  Save-SuiteManifest "running"
}

$failed = @($results | Where-Object { $_.status -ne "completed" }).Count
Save-SuiteManifest $(if ($failed -gt 0) { "completed_with_failures" } else { "completed" })

Write-Host ""
Write-Host "AI duel suite complete. $(@($results | Where-Object { $_.status -eq 'completed' }).Count)/$($runs.Count) runs, $failed failed."
Write-Host "Manifest: $suiteManifestPath"
