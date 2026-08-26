# Build a cloud bake job bundle: startscripts + queue + recipes + worker scripts.
# Does not need a live cloud host — package locally, then submit later.
param(
  [string]$Workspace = "",
  [string[]]$MapIds = @(),
  [string]$BundleName = ""
)

$ErrorActionPreference = "Stop"
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
. (Join-Path (Split-Path -Parent $here) "_common.ps1")
. (Join-Path $here "_cloud_common.ps1")
$Workspace = Get-VerdanceWorkspaceRoot -Workspace $Workspace
$config = Get-VerdanceConfig -Workspace $Workspace

# -File passes comma lists as a single string; normalize to string[].
if ($MapIds -and $MapIds.Count -eq 1 -and [string]$MapIds[0] -match ',') {
  $MapIds = @([string]$MapIds[0] -split ',' | ForEach-Object { $_.Trim() } | Where-Object { $_ })
}

if (-not $MapIds -or $MapIds.Count -eq 0) {
  $opt = Get-CloudConfigOptional -Workspace $Workspace
  if ($opt -and $opt.bake -and $opt.bake.mapOrder) {
    $MapIds = @($opt.bake.mapOrder)
  } else {
    $MapIds = @(
      "the_rock_jungle",
      "koom_valley",
      "all_that_simmers",
      "eye_of_horus",
      "greenest_fields",
      "tabula",
      "ancient_bastion"
    )
  }
}

$stamp = Get-Date -Format "yyyyMMdd_HHmmss"
if (-not $BundleName) { $BundleName = "shell_bake_cloud_$stamp" }
$bundleRoot = Join-Path $Workspace "headless_runs\cloud\$BundleName"
$jobsDir = Join-Path $bundleRoot "jobs"
$scriptsDir = Join-Path $bundleRoot "scripts"
New-Item -ItemType Directory -Force -Path $jobsDir, $scriptsDir | Out-Null

$gameType = if ($config.PSObject.Properties["gameType"] -and $config.gameType) { [string]$config.gameType } else { 'Verdance Ashes $VERSION' }

$queue = New-Object System.Collections.Generic.List[object]
foreach ($mapId in $MapIds) {
  $jobDir = Join-Path $jobsDir $mapId
  New-Item -ItemType Directory -Force -Path $jobDir | Out-Null
  $scriptPath = Join-Path $jobDir "bake_startscript.txt"
  $meta = New-ShellBakeStartscript -Workspace $Workspace -MapId $mapId -OutPath $scriptPath -GameType $gameType
  ($meta | ConvertTo-Json -Depth 6) | Set-Content -Encoding UTF8 -LiteralPath (Join-Path $jobDir "job_meta.json")
  ($meta.aiMix -join "`n") | Set-Content -Encoding UTF8 -LiteralPath (Join-Path $jobDir "ai_mix.txt")

  # Copy recipe for remote visibility / debugging.
  $recipeSrc = Join-Path $Workspace "data\base_templates\$mapId\bake_recipe.json"
  if (Test-Path $recipeSrc) {
    Copy-Item -Force -LiteralPath $recipeSrc -Destination (Join-Path $jobDir "bake_recipe.json")
  }

  $timeout = 0
  $growFrames = [int]$meta.growFrames
  $timeout = [Math]::Max(1200, [int]($growFrames / 8) + 480)
  $queue.Add([ordered]@{
    mapId = $mapId
    mapName = $meta.mapName
    growFrames = $growFrames
    teamCount = $meta.teamCount
    templateId = $meta.templateId
    aiMix = $meta.aiMix
    startscriptRel = "jobs/$mapId/bake_startscript.txt"
    timeoutSeconds = $timeout
  }) | Out-Null
  Write-Host "Queued $mapId frames=$growFrames timeout=${timeout}s mix=$($meta.aiMix -join ' | ')"
}

$queuePath = Join-Path $bundleRoot "queue.json"
$engineTag = "recoil_2025.06.24"
if ($config.PSObject.Properties["engineDir"] -and $config.engineDir) {
  $engineTag = [System.IO.Path]::GetFileName(([string]$config.engineDir).TrimEnd('\', '/'))
  if (-not $engineTag) { $engineTag = "recoil_2025.06.24" }
}
# Materialize jobs as plain hashtables so ConvertTo-Json stays stable.
$jobList = @()
foreach ($j in $queue) {
  $jobList += @{
    mapId = [string]$j.mapId
    mapName = [string]$j.mapName
    growFrames = [int]$j.growFrames
    teamCount = [int]$j.teamCount
    templateId = [string]$j.templateId
    aiMix = @($j.aiMix | ForEach-Object { [string]$_ })
    startscriptRel = [string]$j.startscriptRel
    timeoutSeconds = [int]$j.timeoutSeconds
  }
}
$queueDoc = @{
  schemaVersion = "verdance-cloud-bake-queue/1.0"
  bundleName = [string]$BundleName
  createdAt = (Get-Date).ToString("s")
  computeLocus = "cloud"
  engineTag = [string]$engineTag
  gameType = [string]$gameType
  jobs = $jobList
}
($queueDoc | ConvertTo-Json -Depth 8) | Set-Content -Encoding UTF8 -LiteralPath $queuePath

# Ship worker scripts with the bundle.
Copy-Item -Force -LiteralPath (Join-Path $here "remote_worker_bake.ps1") -Destination (Join-Path $scriptsDir "remote_worker_bake.ps1")
if (Test-Path (Join-Path $here "remote_worker_bake.sh")) {
  Copy-Item -Force -LiteralPath (Join-Path $here "remote_worker_bake.sh") -Destination (Join-Path $scriptsDir "remote_worker_bake.sh")
}

# Manifest for membrane / craft.
$manifest = @{
  schemaVersion = "verdance-cloud-bake-bundle/1.0"
  bundleName = [string]$BundleName
  bundleRoot = [string]$bundleRoot
  queuePath = [string]$queuePath
  mapCount = [int]$queue.Count
  mapIds = @($MapIds | ForEach-Object { [string]$_ })
  createdAt = (Get-Date).ToString("s")
  computeLocus = "cloud"
  notes = "Local package only. Submit with Invoke-CloudShellBake.ps1 after cloud_config.json is filled."
}
($manifest | ConvertTo-Json -Depth 6) | Set-Content -Encoding UTF8 -LiteralPath (Join-Path $bundleRoot "bundle_manifest.json")
($manifest | ConvertTo-Json -Depth 6) | Set-Content -Encoding UTF8 -LiteralPath (Join-Path $Workspace "outbox\cloud_bake_bundle.latest.json")

Write-Host ""
Write-Host "Cloud bake bundle ready: $bundleRoot"
Write-Host "Queue: $queuePath ($($queue.Count) maps)"
Write-Host "Next: fill data/cloud/cloud_config.json then:"
Write-Host "  powershell -File scripts/cloud/Invoke-CloudShellBake.ps1 -BundleName $BundleName"
return $bundleRoot
