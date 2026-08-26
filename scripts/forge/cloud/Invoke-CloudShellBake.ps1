# Orchestrate cloud living-shell bakes: package (optional) -> sync (optional) -> remote run -> harvest -> strip.
param(
  [string]$Workspace = "",
  [string]$BundleName = "",
  [string[]]$MapIds = @(),
  [switch]$PackageOnly,
  [switch]$SkipSync,
  [switch]$SyncOnly,
  [switch]$SkipBake,
  [switch]$HarvestOnly,
  [switch]$RefreshMembrane
)

$ErrorActionPreference = "Stop"
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
$scriptsRoot = Split-Path -Parent $here
. (Join-Path $scriptsRoot "_common.ps1")
. (Join-Path $here "_cloud_common.ps1")
$Workspace = Get-VerdanceWorkspaceRoot -Workspace $Workspace

# -File passes comma lists as a single string; normalize to string[].
if ($MapIds -and $MapIds.Count -eq 1 -and [string]$MapIds[0] -match ',') {
  $MapIds = @([string]$MapIds[0] -split ',' | ForEach-Object { $_.Trim() } | Where-Object { $_ })
}

function Resolve-BundleRoot {
  param([string]$Name)
  $cloudRoot = Join-Path $Workspace "headless_runs\cloud"
  if ($Name) {
    $p = Join-Path $cloudRoot $Name
    if (!(Test-Path $p)) { throw "Bundle not found: $p" }
    return $p
  }
  $latest = Get-ChildItem $cloudRoot -Directory -ErrorAction SilentlyContinue |
    Where-Object { Test-Path (Join-Path $_.FullName "queue.json") } |
    Sort-Object LastWriteTime -Descending |
    Select-Object -First 1
  if (-not $latest) { return $null }
  return $latest.FullName
}

# --- Package ---
$bundleRoot = $null
if ($HarvestOnly) {
  $bundleRoot = Resolve-BundleRoot -Name $BundleName
  if (-not $bundleRoot) { throw "No bundle to harvest. Pass -BundleName or package first." }
} elseif ($PackageOnly -or -not $BundleName) {
  $pkgArgs = @{ Workspace = $Workspace }
  if ($MapIds -and $MapIds.Count -gt 0) { $pkgArgs.MapIds = $MapIds }
  if ($BundleName) { $pkgArgs.BundleName = $BundleName }
  $bundleRoot = & powershell -ExecutionPolicy Bypass -File (Join-Path $here "New-CloudBakeBundle.ps1") @pkgArgs
  if ($bundleRoot -is [array]) { $bundleRoot = $bundleRoot[-1] }
  $bundleRoot = [string]$bundleRoot
} else {
  $bundleRoot = Resolve-BundleRoot -Name $BundleName
  if (-not $bundleRoot) {
    $pkgArgs = @{ Workspace = $Workspace; BundleName = $BundleName }
    if ($MapIds -and $MapIds.Count -gt 0) { $pkgArgs.MapIds = $MapIds }
    $bundleRoot = & powershell -ExecutionPolicy Bypass -File (Join-Path $here "New-CloudBakeBundle.ps1") @pkgArgs
    if ($bundleRoot -is [array]) { $bundleRoot = $bundleRoot[-1] }
    $bundleRoot = [string]$bundleRoot
  }
}

Write-Host "Bundle: $bundleRoot"
if ($PackageOnly) {
  Write-Host "PackageOnly: done. Configure cloud host and re-run without -PackageOnly."
  return $bundleRoot
}

$cloud = Get-CloudConfig -Workspace $Workspace
$remoteRoot = [string]$cloud.remoteRoot
$remoteBar = [string]$cloud.remoteBarData
$remoteJobs = [string]$cloud.remoteJobs
$remoteResults = [string]$cloud.remoteResults
$engineTag = if ($cloud.engineTag) { [string]$cloud.engineTag } else { "recoil_2025.06.24" }
$engineRel = if ($cloud.remoteEngineRel) { [string]$cloud.remoteEngineRel } else { "engine\$engineTag" }

# --- Sync runtime ---
if ($SyncOnly -or (-not $SkipSync -and -not $HarvestOnly)) {
  Write-Host "=== Syncing BAR runtime to cloud ==="
  & powershell -ExecutionPolicy Bypass -File (Join-Path $here "Sync-CloudBarRuntime.ps1") -Workspace $Workspace
  if ($SyncOnly) {
    Write-Host "SyncOnly: done."
    return
  }
}

# --- Upload jobs ---
if (-not $HarvestOnly -and -not $SkipBake) {
  Write-Host "=== Uploading job bundle ==="
  Invoke-RemoteSsh -CloudConfig $cloud -RemoteCommand "powershell -NoProfile -Command `"New-Item -ItemType Directory -Force -Path '$remoteJobs','$remoteResults','$remoteRoot\scripts' | Out-Null`""

  $queuePath = Join-Path $bundleRoot "queue.json"
  $queue = Get-Content -Raw -LiteralPath $queuePath | ConvertFrom-Json
  $jobsToRun = @($queue.jobs)
  if ($MapIds -and $MapIds.Count -gt 0) {
    $jobsToRun = @($jobsToRun | Where-Object { $MapIds -contains $_.mapId })
  }

  Copy-ToRemote -CloudConfig $cloud -LocalPath $queuePath -RemotePath "$remoteJobs\queue.json"
  foreach ($job in $jobsToRun) {
    $mapId = [string]$job.mapId
    $localJob = Join-Path $bundleRoot "jobs\$mapId"
    Invoke-RemoteSsh -CloudConfig $cloud -RemoteCommand "powershell -NoProfile -Command `"New-Item -ItemType Directory -Force -Path '$remoteJobs\$mapId' | Out-Null`""
    Copy-ToRemote -CloudConfig $cloud -LocalPath (Join-Path $localJob "bake_startscript.txt") -RemotePath "$remoteJobs\$mapId\bake_startscript.txt"
    if (Test-Path (Join-Path $localJob "job_meta.json")) {
      Copy-ToRemote -CloudConfig $cloud -LocalPath (Join-Path $localJob "job_meta.json") -RemotePath "$remoteJobs\$mapId\job_meta.json"
    }
  }
  Copy-ToRemote -CloudConfig $cloud -LocalPath (Join-Path $here "remote_worker_bake.ps1") -RemotePath "$remoteRoot\scripts\remote_worker_bake.ps1"

  # --- Run remote bakes ---
  Write-Host "=== Running remote shell bakes ($($jobsToRun.Count) maps) ==="
  $runSummary = New-Object System.Collections.Generic.List[object]
  foreach ($job in $jobsToRun) {
    $mapId = [string]$job.mapId
    $timeout = if ($job.timeoutSeconds) { [int]$job.timeoutSeconds } else { 3600 }
    $grow = if ($job.growFrames) { [int]$job.growFrames } else { 0 }
    Write-Host ""
    Write-Host ">>> CLOUD BAKE $mapId timeout=${timeout}s"
    $remoteCmd = @"
powershell -NoProfile -ExecutionPolicy Bypass -File '$remoteRoot\scripts\remote_worker_bake.ps1' -BarDataRoot '$remoteBar' -StartscriptPath '$remoteJobs\$mapId\bake_startscript.txt' -MapId '$mapId' -ResultDir '$remoteResults' -EngineRel '$engineRel' -TimeoutSeconds $timeout -GrowFrames $grow
"@
    try {
      Invoke-RemoteSsh -CloudConfig $cloud -RemoteCommand $remoteCmd.Trim()
      $runSummary.Add([ordered]@{ mapId = $mapId; remoteOk = $true }) | Out-Null
    } catch {
      Write-Warning "Remote bake failed for ${mapId}: $_"
      $runSummary.Add([ordered]@{ mapId = $mapId; remoteOk = $false; error = "$_" }) | Out-Null
    }
  }
  ($runSummary | ConvertTo-Json -Depth 4) | Set-Content -Encoding UTF8 -LiteralPath (Join-Path $bundleRoot "remote_run_summary.json")
}

# --- Harvest ---
Write-Host "=== Harvesting cloud results ==="
$localHarvest = Join-Path $bundleRoot "harvest"
New-Item -ItemType Directory -Force -Path $localHarvest | Out-Null

$queuePath = Join-Path $bundleRoot "queue.json"
$queue = Get-Content -Raw -LiteralPath $queuePath | ConvertFrom-Json
$jobsToHarvest = @($queue.jobs)
if ($MapIds -and $MapIds.Count -gt 0) {
  $jobsToHarvest = @($jobsToHarvest | Where-Object { $MapIds -contains $_.mapId })
}

$harvestReport = New-Object System.Collections.Generic.List[object]
$stripScript = Join-Path $scriptsRoot "apply_shell_strip.ps1"

foreach ($job in $jobsToHarvest) {
  $mapId = [string]$job.mapId
  $localMap = Join-Path $localHarvest $mapId
  New-Item -ItemType Directory -Force -Path $localMap | Out-Null
  $templateId = if ($job.templateId) { [string]$job.templateId } else { "living_shell_v1" }
  $aiMix = @()
  if ($job.aiMix) { $aiMix = @($job.aiMix) }

  try {
    # Prefer shell_markers (small) + latest result json.
    Copy-FromRemote -CloudConfig $cloud -RemotePath "$remoteResults\${mapId}_latest.json" -LocalPath (Join-Path $localMap "result_latest.json")
  } catch {
    Write-Warning "No result_latest for $mapId yet."
  }

  # Pull the newest run dir markers via remote PowerShell list + scp.
  $listCmd = "powershell -NoProfile -Command `"`$d = Get-ChildItem '$remoteResults' -Directory | Where-Object { `$_.Name -like '${mapId}_*' } | Sort-Object LastWriteTime -Descending | Select-Object -First 1; if (`$d) { Write-Output `$d.FullName }`""
  $remoteRunDir = $null
  try {
    $out = Invoke-RemoteSsh -CloudConfig $cloud -RemoteCommand $listCmd -Capture
    $remoteRunDir = (@($out) | Where-Object { $_ -and "$_".Trim() -ne "" } | Select-Object -Last 1)
    if ($remoteRunDir) { $remoteRunDir = [string]$remoteRunDir.ToString().Trim() }
  } catch {
    $remoteRunDir = $null
  }

  $infologLocal = Join-Path $localMap "infolog.txt"
  $markersLocal = Join-Path $localMap "shell_markers.txt"
  $gotMarkers = $false
  if ($remoteRunDir) {
    try {
      Copy-FromRemote -CloudConfig $cloud -RemotePath "$remoteRunDir\shell_markers.txt" -LocalPath $markersLocal
      $gotMarkers = Test-Path $markersLocal
    } catch {}
    try {
      Copy-FromRemote -CloudConfig $cloud -RemotePath "$remoteRunDir\infolog.txt" -LocalPath $infologLocal
    } catch {}
    try {
      Copy-FromRemote -CloudConfig $cloud -RemotePath "$remoteRunDir\result.json" -LocalPath (Join-Path $localMap "result.json")
    } catch {}
  }

  $parseSource = $null
  if ($gotMarkers) { $parseSource = $markersLocal }
  elseif (Test-Path $infologLocal) { $parseSource = $infologLocal }

  $entry = [ordered]@{
    mapId = $mapId
    harvested = $false
    unitCount = 0
    templatePath = $null
    error = $null
  }

  if (-not $parseSource) {
    $entry.error = "no shell markers or infolog"
    $harvestReport.Add($entry) | Out-Null
    Write-Warning "Harvest miss: $mapId (no markers)"
    continue
  }

  $rawDump = Join-Path $localMap "shell_raw_units.json"
  try {
    $parsed = Convert-InfologToRawDump -InfologPath $parseSource -MapId $mapId -OutJsonPath $rawDump -AiMix $aiMix
    $entry.unitCount = [int]$parsed.unitCount
    $entry.armed = [bool]$parsed.armed
    $entry.dumped = [bool]$parsed.dumped
    if ([int]$parsed.unitCount -le 0) {
      $entry.error = "zero VA_SHELL_UNIT lines"
      $harvestReport.Add($entry) | Out-Null
      Write-Warning "Harvest empty: $mapId"
      continue
    }

    $outPath = Join-Path $Workspace "data\base_templates\$mapId\$templateId.json"
    & powershell -ExecutionPolicy Bypass -File $stripScript `
      -Workspace $Workspace `
      -RawDumpPath $rawDump `
      -MapId $mapId `
      -TemplateId $templateId `
      -OutPath $outPath | Out-Host

    $entry.harvested = $true
    $entry.templatePath = $outPath
    $entry.rawDump = $rawDump
    Write-Host "Harvest OK $mapId units=$($entry.unitCount) -> $outPath"
  } catch {
    $entry.error = "$_"
    Write-Warning "Harvest/strip failed for ${mapId}: $_"
  }
  $harvestReport.Add($entry) | Out-Null
}

$reportPath = Join-Path $bundleRoot "harvest_report.json"
$report = [ordered]@{
  schemaVersion = "verdance-cloud-harvest/1.0"
  bundleRoot = $bundleRoot
  host = [string]$cloud.host
  finishedAt = (Get-Date).ToString("s")
  computeLocus = "cloud"
  results = @($harvestReport)
  okCount = @($harvestReport | Where-Object { $_.harvested }).Count
  total = $harvestReport.Count
}
($report | ConvertTo-Json -Depth 8) | Set-Content -Encoding UTF8 -LiteralPath $reportPath
($report | ConvertTo-Json -Depth 8) | Set-Content -Encoding UTF8 -LiteralPath (Join-Path $Workspace "outbox\cloud_bake_harvest.latest.json")

# --- Membrane refresh ---
if ($RefreshMembrane -or $report.okCount -gt 0) {
  Write-Host "=== Refreshing shell character membrane ==="
  $py = $null
  $umweltPy = "C:\Users\Luke Spooner\ws-win\umwelt\.venv\Scripts\python.exe"
  if (Test-Path $umweltPy) { $py = $umweltPy }
  else {
    try { $py = Get-VerdancePython -Workspace $Workspace } catch { $py = $null }
  }
  if ($py) {
    $env:PYTHONPATH = "$Workspace\tools;C:\Users\Luke Spooner\ws-win\umwelt\src"
    try {
      & $py -m quantum_bar_ai.shell_character_membrane $Workspace
      Write-Host "Membrane refreshed -> outbox/shell_character_membrane.latest.json"
    } catch {
      Write-Warning "Membrane refresh failed: $_"
    }
  } else {
    Write-Warning "No Python for membrane refresh."
  }
}

Write-Host ""
Write-Host "Cloud bake complete: $($report.okCount)/$($report.total) templates harvested"
Write-Host "Report: $reportPath"
return $reportPath
