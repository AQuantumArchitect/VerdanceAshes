param([string]$Workspace = "$env:USERPROFILE\Documents\BAR_Verdance_Workspace")
$ErrorActionPreference = "Stop"
. (Join-Path (Split-Path -Parent $MyInvocation.MyCommand.Path) "_common.ps1")
$config = Get-VerdanceConfig -Workspace $Workspace
$exportDir = if ($config.exportDir) { $config.exportDir } else { Join-Path $Workspace "export" }
New-Item -ItemType Directory -Force -Path $exportDir | Out-Null
$stamp = Get-Date -Format "yyyyMMdd_HHmmss"
$temp = Join-Path $exportDir "handoff_$stamp"
$zip = Join-Path $exportDir "verdance_handoff_$stamp.zip"
New-Item -ItemType Directory -Force -Path $temp | Out-Null

$files = [ordered]@{
  "campaign_state.json" = $config.campaignState
  "latest_va_result.json" = $config.resultInbox
  "va_current.lua" = $config.seedOutbox
  "processed_results.json" = $config.processedLedger
  "verdance_config.json" = (Join-Path $Workspace "verdance_config.json")
}
$included = @()
foreach ($name in $files.Keys) {
  $src = $files[$name]
  if ($src -and (Test-Path $src)) {
    Copy-Item -Force $src (Join-Path $temp $name)
    $hash = (Get-FileHash -Algorithm SHA256 $src).Hash.ToLowerInvariant()
    $included += [pscustomobject]@{ name = $name; source = $src; sha256 = $hash }
  }
}

$stateSummary = $null
if (Test-Path $config.campaignState) {
  $s = Get-Content $config.campaignState -Raw | ConvertFrom-Json
  $stateSummary = [ordered]@{
    campaignId = $s.campaignId
    missionNumber = $s.missionNumber
    currentMissionId = $s.currentMissionId
    pathSignal = $s.pathSignal
    historyCount = @($s.history).Count
  }
}
$resultSummary = $null
if (Test-Path $config.resultInbox) {
  $r = Get-Content $config.resultInbox -Raw | ConvertFrom-Json
  $resultSummary = [ordered]@{
    campaignId = $r.campaignId
    missionId = $r.missionId
    missionNumber = $r.missionNumber
    status = $r.status
    holdFrames = $r.holdFrames
    requiredFrames = $r.requiredFrames
    resultKey = New-VerdanceResultKey $r
    resultHash = Get-ResultHash $r
  }
}

$manifest = [ordered]@{
  schemaVersion = "0.6"
  exportedAt = (Get-Date).ToString("s")
  workspace = $Workspace
  purpose = "Upload this zip to ChatGPT as the complete Verdance BAR handoff bundle."
  stateSummary = $stateSummary
  resultSummary = $resultSummary
  files = $included
}
$manifest | ConvertTo-Json -Depth 20 | Set-Content -Encoding UTF8 (Join-Path $temp "manifest.json")

$diagnostics = @()
$diagnostics += "Verdance handoff export $stamp"
$diagnostics += "Workspace: $Workspace"
$diagnostics += "BAR data root: $($config.barDataRoot)"
$diagnostics += "BAR seed destination: $($config.seedDestination)"
if ($stateSummary) { $diagnostics += "State: mission $($stateSummary.currentMissionId), historyCount $($stateSummary.historyCount)" }
if ($resultSummary) { $diagnostics += "Latest result: $($resultSummary.missionId) status $($resultSummary.status) key $($resultSummary.resultKey)" }
$diagnostics | Set-Content -Encoding UTF8 (Join-Path $temp "diagnostics.txt")

if (Test-Path $zip) { Remove-Item -Force $zip }
Compress-Archive -Path (Join-Path $temp "*") -DestinationPath $zip -Force
Write-Host "Created ChatGPT handoff bundle:"
Write-Host $zip
Write-Host "Upload that single zip instead of separate files."
