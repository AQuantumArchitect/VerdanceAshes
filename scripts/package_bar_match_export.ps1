param(
  [string]$Workspace = "$env:USERPROFILE\Documents\BAR_Verdance_Workspace",
  [string]$SaveName = "",
  [string]$OutboxRoot = "",
  [switch]$IncludeSaveGame
)

$ErrorActionPreference = "Stop"
. (Join-Path (Split-Path -Parent $MyInvocation.MyCommand.Path) "_common.ps1")

$config = Get-VerdanceConfig -Workspace $Workspace
if (-not $OutboxRoot) { $OutboxRoot = Join-Path $Workspace "_outbox" }

$analysisScript = Join-Path $Workspace "scripts\analyze_bar_match.ps1"
if (!(Test-Path $analysisScript)) { throw "Missing analyzer at $analysisScript" }

& powershell -ExecutionPolicy Bypass -File $analysisScript -Workspace $Workspace | Write-Host

$analysisPath = Join-Path $Workspace "reports\bar_match_analysis.latest.json"
$analysisHtmlPath = Join-Path $Workspace "reports\bar_match_analysis.latest.html"
if (!(Test-Path $analysisPath)) { throw "Missing latest analysis JSON at $analysisPath" }
if (!(Test-Path $analysisHtmlPath)) { throw "Missing latest analysis HTML at $analysisHtmlPath" }

$analysis = Get-Content -Raw -LiteralPath $analysisPath | ConvertFrom-Json
$stamp = Get-Date -Format "yyyyMMdd_HHmmss"
$safeMap = if ($analysis.mapName) { ($analysis.mapName -replace '[^A-Za-z0-9]+', '_').Trim('_').ToLowerInvariant() } else { "unknown_map" }
$folderName = "${stamp}_${safeMap}_playtest_packet"
$packetDir = Join-Path $OutboxRoot $folderName
$rawDir = Join-Path $packetDir "raw"
$reportsDir = Join-Path $packetDir "reports"
$saveDir = Join-Path $packetDir "save"
New-Item -ItemType Directory -Force -Path $rawDir, $reportsDir, $saveDir | Out-Null

$infologCopy = Join-Path $rawDir "infolog.txt"
Copy-Item -Force -LiteralPath $config.infolog -Destination $infologCopy
Copy-Item -Force -LiteralPath $analysisPath -Destination (Join-Path $reportsDir "bar_match_analysis.json")
Copy-Item -Force -LiteralPath $analysisHtmlPath -Destination (Join-Path $reportsDir "bar_match_analysis.html")

$selectedSaveMeta = $null
$selectedSaveGame = $null
if ($SaveName) {
  $selectedSaveMeta = Join-Path $config.barDataRoot "Saves\$SaveName.lua"
  $selectedSaveGame = Join-Path $config.barDataRoot "Saves\$SaveName.ssf"
} else {
  $latestMeta = Get-ChildItem -Path (Join-Path $config.barDataRoot "Saves") -File -Filter "*.lua" |
    Sort-Object LastWriteTime -Descending |
    Select-Object -First 1
  if ($latestMeta) {
    $selectedSaveMeta = $latestMeta.FullName
    $selectedSaveGame = [System.IO.Path]::ChangeExtension($latestMeta.FullName, ".ssf")
    $SaveName = [System.IO.Path]::GetFileNameWithoutExtension($latestMeta.FullName)
  }
}

if ($selectedSaveMeta -and (Test-Path $selectedSaveMeta)) {
  Copy-Item -Force -LiteralPath $selectedSaveMeta -Destination (Join-Path $saveDir ([System.IO.Path]::GetFileName($selectedSaveMeta)))
}
if ($IncludeSaveGame -and $selectedSaveGame -and (Test-Path $selectedSaveGame)) {
  Copy-Item -Force -LiteralPath $selectedSaveGame -Destination (Join-Path $saveDir ([System.IO.Path]::GetFileName($selectedSaveGame)))
}

$topAttacks = @($analysis.attackSummary | Select-Object -First 8 | ForEach-Object {
  "- $($_.unit): $($_.count) alerts, first $($_.first), last $($_.last)"
})
if ($topAttacks.Count -eq 0) { $topAttacks = @("- No attack alerts detected.") }

$peakBucket = @($analysis.attackBuckets | Sort-Object count -Descending | Select-Object -First 1)
$peakText = if ($peakBucket.Count -gt 0) { "$($peakBucket[0].bucket), $($peakBucket[0].count) alerts" } else { "none" }
$exportText = if ($analysis.observedExport) { "Verdance export markers were observed in the log." } else { "No Verdance result/export marker was observed in the log." }

$commentary = @"
# Verdance BAR Playtest Packet

Generated: $(Get-Date -Format "s")
Map: $($analysis.mapName)
GameID: $($analysis.gameId)
Last frame: $($analysis.lastFrame)
Last log time: $($analysis.lastLogTime)
Save selected: $SaveName

## Codex Commentary

This playtest produced a usable extraction point, but it reads as a limited contact run rather than a decisive battle. The player established a base in the original spawn zone, pushed or scouted enough to draw repeated fire, and caused at least some damage. The log evidence shows pressure clustering late in the session rather than a continuous front-wide escalation.

Peak attack pressure: $peakText.

$exportText

## Attack Summary

$($topAttacks -join "`r`n")

## Packet Contents

- raw/infolog.txt: raw BAR log copied from the local BAR data folder.
- reports/bar_match_analysis.json: machine-readable analytics extraction.
- reports/bar_match_analysis.html: human-readable analytics display.
- save/: latest BAR save metadata, plus the .ssf save when IncludeSaveGame is set.
"@

$commentaryPath = Join-Path $packetDir "codex_commentary.md"
Set-Content -Encoding UTF8 -LiteralPath $commentaryPath -Value $commentary

$manifest = [ordered]@{
  schemaVersion = "verdance-outbox-packet/0.1"
  generatedAt = (Get-Date).ToString("s")
  packetDir = $packetDir
  sourceInfolog = $config.infolog
  analysisJson = Join-Path $reportsDir "bar_match_analysis.json"
  analysisHtml = Join-Path $reportsDir "bar_match_analysis.html"
  commentary = $commentaryPath
  saveName = $SaveName
  includedSaveGame = [bool]($IncludeSaveGame -and $selectedSaveGame -and (Test-Path $selectedSaveGame))
  gameId = $analysis.gameId
  mapName = $analysis.mapName
  lastFrame = $analysis.lastFrame
  lastLogTime = $analysis.lastLogTime
  observedExport = $analysis.observedExport
}
Save-Json $manifest (Join-Path $packetDir "manifest.json")

Write-Host "Wrote outbox packet: $packetDir"
Write-Host "Commentary: $commentaryPath"
