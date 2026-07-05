param(
  [string]$Workspace = "$env:USERPROFILE\Documents\BAR_Verdance_Workspace",
  [string]$MilestoneMinutes = "1,2,3,5,8,13,21",
  [string]$ExtensionMilestoneMinutes = "34,55,89",
  [string[]]$MapIds = @(),
  [string]$VariantMode = "baseline",
  [int]$TimeoutSecondsPerRun = 43200,
  [switch]$GenerateMatrix,
  [switch]$SkipPatchInstall,
  [switch]$NoAdaptiveExtension,
  [switch]$Resume
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

function Merge-Minutes {
  param([string]$A, [string]$B)
  $seen = @{}
  $vals = @()
  foreach ($part in (($A + "," + $B) -split ',')) {
    $trim = $part.Trim()
    if (-not $trim) { continue }
    $key = [string]([double]$trim)
    if (-not $seen.ContainsKey($key)) {
      $seen[$key] = $true
      $vals += [double]$trim
    }
  }
  return (($vals | Sort-Object) -join ",")
}

function Get-RunVerdict {
  param([string]$DataPath)
  $summary = [ordered]@{
    observedTelemetryPackets = 0
    observedTranslationPackets = 0
    lastVerdict = "unknown"
    lastFrame = 0
    lastRatio = $null
    lastPlayerValue = $null
    lastEnemyValue = $null
    extensionReason = ""
  }
  if (-not $DataPath -or !(Test-Path $DataPath)) { return $summary }
  try {
    $data = Get-Content -Raw -LiteralPath $DataPath | ConvertFrom-Json
    $summary.observedTelemetryPackets = [int]$data.observedTelemetryPackets
    $summary.observedTranslationPackets = [int]$data.observedPackets
    $last = @($data.snapshots | Where-Object { $_.balance } | Select-Object -Last 1)
    if ($last) {
      $summary.lastVerdict = [string]$last.balance.verdict
      $summary.lastFrame = [int]$last.actualFrame
      $summary.lastRatio = [double]$last.balance.valueRatio
      $summary.lastPlayerValue = [double]$last.balance.playerValue
      $summary.lastEnemyValue = [double]$last.balance.enemyValue
    }
  } catch {
    $summary.extensionReason = "parse_failed"
  }
  return $summary
}

function Should-ExtendRun {
  param($Run, $Summary)
  if ($NoAdaptiveExtension) { return $false }
  if ([bool]$Run.wilds -or [bool]$Run.raptors) {
    $Summary.extensionReason = "wild_or_raptor_map"
    return $true
  }
  if ($Summary.lastVerdict -in @("active", "unknown", "player_stalled")) {
    $Summary.extensionReason = "unresolved_or_stalled"
    return $true
  }
  if ($null -ne $Summary.lastRatio -and [double]$Summary.lastRatio -gt 0.75 -and [double]$Summary.lastRatio -lt 1.35) {
    $Summary.extensionReason = "contested_ratio_band"
    return $true
  }
  return $false
}

function Invoke-ProfilerRun {
  param($Run, [string]$Minutes, [string]$Phase, [string]$SuiteDir, [string]$ProfilerPath, [int]$TimeoutSeconds, [bool]$SkipPatch)
  $safeId = ($Run.id -replace '[^A-Za-z0-9_-]', '_')
  $logPath = Join-Path $SuiteDir ("{0}.{1}.runner.log.txt" -f $safeId, $Phase)
  $maxFrames = Get-MaxFrameFromMinutes $Minutes
  Write-Host ""
  Write-Host "=== Campaign AI ${Phase}: $($Run.mapTitle) / $($Run.variant) ==="
  Write-Host "Milestones minutes: $Minutes"

  $args = @(
    "-ExecutionPolicy", "Bypass",
    "-File", $ProfilerPath,
    "-Workspace", $Workspace,
    "-ScenarioPath", ([string]$Run.scenarioPath),
    "-Variant", ([string]$Run.variant),
    "-MaxFrames", ([string]$maxFrames),
    "-MilestoneMinutes", $Minutes,
    "-TimeoutSeconds", ([string]$TimeoutSeconds),
    "-QuitAfterLast"
  )
  if ($SkipPatch) { $args += "-SkipPatchInstall" }

  $output = & powershell @args 2>&1
  $exit = $LASTEXITCODE
  $output | Set-Content -Encoding UTF8 -Path $logPath

  $runDir = $null
  foreach ($line in $output) {
    if ($line -match '^Suite dir:\s+(.+)$') { $runDir = $Matches[1].Trim() }
  }
  $dataPath = if ($runDir) { Join-Path $runDir "calibration_data.json" } else { $null }
  $reportPath = if ($runDir) { Join-Path $runDir "calibration_report.md" } else { $null }
  $summary = Get-RunVerdict -DataPath $dataPath

  return [ordered]@{
    id = $Run.id
    mapId = $Run.mapId
    mapTitle = $Run.mapTitle
    scenarioPath = $Run.scenarioPath
    variant = $Run.variant
    playerTeamID = $Run.playerTeamID
    playerSide = $Run.playerSide
    playerStartLabel = $Run.playerStartLabel
    phase = $Phase
    status = if ($exit -eq 0) { "completed" } else { "failed" }
    exitCode = $exit
    milestoneMinutes = $Minutes
    maxFrames = $maxFrames
    runDir = $runDir
    calibrationDataPath = $dataPath
    calibrationReportPath = $reportPath
    runnerLogPath = $logPath
    observedTelemetryPackets = $summary.observedTelemetryPackets
    observedTranslationPackets = $summary.observedTranslationPackets
    lastVerdict = $summary.lastVerdict
    lastFrame = $summary.lastFrame
    lastRatio = $summary.lastRatio
    lastPlayerValue = $summary.lastPlayerValue
    lastEnemyValue = $summary.lastEnemyValue
    extensionReason = $summary.extensionReason
    finishedAt = (Get-Date).ToString("s")
  }
}

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$matrixScript = Join-Path $scriptDir "new_campaign_ai_baseline_matrix.ps1"
$profiler = Join-Path $scriptDir "run_translation_profiler.ps1"
$installPatch = Join-Path $scriptDir "install_balance_telemetry_patch.ps1"

if ($GenerateMatrix) {
  & powershell -ExecutionPolicy Bypass -File $matrixScript -Workspace $Workspace
  if ($LASTEXITCODE -ne 0) { throw "Campaign AI matrix generation failed." }
}
if (-not $SkipPatchInstall) {
  & powershell -ExecutionPolicy Bypass -File $installPatch -Workspace $Workspace
  if ($LASTEXITCODE -ne 0) { throw "Telemetry patch install failed." }
}

$manifestPath = Join-Path $Workspace "reports\map_surveys\campaign_ai_matrix_manifest.json"
if (!(Test-Path $manifestPath)) { throw "Missing campaign AI matrix manifest. Run with -GenerateMatrix first: $manifestPath" }
$matrix = Get-Content -Raw -LiteralPath $manifestPath | ConvertFrom-Json
$runs = @($matrix.runs)

if ($MapIds.Count -eq 1 -and $MapIds[0] -match ',') {
  $MapIds = @($MapIds[0] -split ',' | ForEach-Object { $_.Trim() } | Where-Object { $_ })
}
if ($MapIds.Count -gt 0) {
  $wanted = @{}
  foreach ($id in $MapIds) { $wanted[$id] = $true }
  $runs = @($runs | Where-Object { $wanted.ContainsKey([string]$_.mapId) })
}
if ($VariantMode -eq "baseline") {
  $runs = @($runs | Where-Object { $_.priority -eq "baseline" })
} elseif ($VariantMode -ne "all") {
  throw "VariantMode must be baseline or all."
}
if ($runs.Count -eq 0) { throw "No campaign AI runs matched the requested filters." }

$latestPath = Join-Path $Workspace "reports\map_surveys\latest_campaign_ai_suite.json"
$results = @()
$stamp = Get-Date -Format "yyyyMMdd_HHmmss"
$suiteDir = Join-Path $Workspace ("reports\map_surveys\campaign_ai_suite_$stamp")
$suiteManifestPath = Join-Path $suiteDir "manifest.json"

if ($Resume -and (Test-Path $latestPath)) {
  try {
    $previous = Get-Content -Raw -LiteralPath $latestPath | ConvertFrom-Json
    if ($previous.suiteDir -and (Test-Path $previous.suiteDir)) {
      $suiteDir = [string]$previous.suiteDir
      $suiteManifestPath = Join-Path $suiteDir "manifest.json"
      $results = @($previous.results)
      Write-Host "Resuming campaign AI suite: $suiteDir"
    }
  } catch {
    Write-Warning "Could not resume latest suite; starting a new suite. $($_.Exception.Message)"
  }
}
New-Item -ItemType Directory -Force -Path $suiteDir | Out-Null

function Save-PartialManifest {
  param([string]$Status)
  $manifest = [ordered]@{
    schemaVersion = "verdance-campaign-ai-suite/0.1"
    generatedAt = (Get-Date).ToString("s")
    status = $Status
    variantMode = $VariantMode
    milestoneMinutes = $MilestoneMinutes
    extensionMilestoneMinutes = $ExtensionMilestoneMinutes
    adaptiveExtension = -not [bool]$NoAdaptiveExtension
    timeoutSecondsPerRun = $TimeoutSecondsPerRun
    suiteDir = $suiteDir
    matrixManifestPath = $manifestPath
    runCount = @($runs).Count
    results = $results
  }
  Save-Json $manifest $suiteManifestPath
  Copy-Item -Force -LiteralPath $suiteManifestPath -Destination $latestPath
}

Save-PartialManifest "started"

foreach ($run in @($runs)) {
  $existingBase = @($results | Where-Object { $_.id -eq $run.id -and $_.phase -eq "base" -and $_.status -eq "completed" } | Select-Object -First 1)
  if ($existingBase) {
    Write-Host "Skipping completed base run: $($run.id)"
    $baseResult = $existingBase
  } else {
    $baseResult = Invoke-ProfilerRun -Run $run -Minutes $MilestoneMinutes -Phase "base" -SuiteDir $suiteDir -ProfilerPath $profiler -TimeoutSeconds $TimeoutSecondsPerRun -SkipPatch ([bool]$true)
    $results += $baseResult
  }
  Save-PartialManifest "running"

  $summary = [ordered]@{
    lastVerdict = $baseResult.lastVerdict
    lastRatio = $baseResult.lastRatio
    extensionReason = ""
  }
  if ($baseResult.status -eq "completed" -and (Should-ExtendRun -Run $run -Summary $summary)) {
    $extendedMinutes = Merge-Minutes $MilestoneMinutes $ExtensionMilestoneMinutes
    $existingExtended = @($results | Where-Object { $_.id -eq $run.id -and $_.phase -eq "extended" -and $_.status -eq "completed" } | Select-Object -First 1)
    if ($existingExtended) {
      Write-Host "Skipping completed extended run: $($run.id)"
    } else {
      $extResult = Invoke-ProfilerRun -Run $run -Minutes $extendedMinutes -Phase "extended" -SuiteDir $suiteDir -ProfilerPath $profiler -TimeoutSeconds $TimeoutSecondsPerRun -SkipPatch ([bool]$true)
      $extResult.extensionReason = $summary.extensionReason
      $results += $extResult
      Save-PartialManifest "running"
    }
  }
}

$failedCount = @($results | Where-Object { $_.status -ne "completed" }).Count
if ($failedCount -gt 0) {
  Save-PartialManifest "completed_with_failures"
} else {
  Save-PartialManifest "completed"
}

Write-Host ""
Write-Host "Campaign AI baseline suite complete."
Write-Host "Manifest: $suiteManifestPath"
Write-Host "Latest: $latestPath"
