param(
  [string]$Workspace = "$env:USERPROFILE\Documents\BAR_Verdance_Workspace",
  [string]$SubtleSaveName = "20260621_012932",
  [string]$DramaticSaveName = "",
  [string]$OutboxRoot = ""
)

$ErrorActionPreference = "Stop"
. (Join-Path (Split-Path -Parent $MyInvocation.MyCommand.Path) "_common.ps1")

function Copy-SavePair {
  param(
    [string]$BarDataRoot,
    [string]$SaveName,
    [string]$Destination
  )
  $srcMeta = Join-Path $BarDataRoot "Saves\$SaveName.lua"
  $srcSave = Join-Path $BarDataRoot "Saves\$SaveName.ssf"
  if (!(Test-Path $srcMeta)) { throw "Missing save metadata: $srcMeta" }
  if (!(Test-Path $srcSave)) { throw "Missing save file: $srcSave" }
  Copy-Item -Force -LiteralPath $srcMeta -Destination (Join-Path $Destination "save_metadata.lua")
  Copy-Item -Force -LiteralPath $srcSave -Destination (Join-Path $Destination "savegame.ssf")
}

function Get-AnalysisStats {
  param($Analysis)
  $attackCount = 0
  foreach ($row in @($Analysis.attackSummary)) { $attackCount += [int]$row.count }
  $peak = @($Analysis.attackBuckets | Sort-Object count -Descending | Select-Object -First 1)
  $peakText = if ($peak.Count -gt 0) { "$($peak[0].bucket) / $($peak[0].count) alerts" } else { "none" }
  $top = @($Analysis.attackSummary | Select-Object -First 8 | ForEach-Object {
    [ordered]@{
      unit = $_.unit
      alerts = [int]$_.count
      first = $_.first
      last = $_.last
    }
  })
  return [pscustomobject]@{
    attackAlerts = $attackCount
    peakPressure = $peakText
    topAttacks = $top
  }
}

function Write-SavePacket {
  param(
    [string]$Kind,
    [string]$SaveName,
    [string]$Destination,
    $Analysis,
    [string]$AnalysisHtml,
    [string]$Commentary
  )
  New-Item -ItemType Directory -Force -Path $Destination | Out-Null
  $stats = Get-AnalysisStats $Analysis
  $analysisJsonPath = Join-Path $Destination "analytics_packet.json"
  $analysisHtmlPath = Join-Path $Destination "analytics_report.html"
  $manifestPath = Join-Path $Destination "manifest.json"
  $summaryPath = Join-Path $Destination "summary.md"

  $Analysis | ConvertTo-Json -Depth 60 | Set-Content -Encoding UTF8 -LiteralPath $analysisJsonPath
  Copy-Item -Force -LiteralPath $AnalysisHtml -Destination $analysisHtmlPath

  $attackLines = @($stats.topAttacks | ForEach-Object {
    "- $($_.unit): $($_.alerts) alerts, first $($_.first), last $($_.last)"
  })
  if ($attackLines.Count -eq 0) { $attackLines = @("- No attack alerts detected.") }

  $summary = @"
# Verdance BAR Save Packet: $Kind

Save: $SaveName
Map: $($Analysis.mapName)
GameID: $($Analysis.gameId)
Last frame: $($Analysis.lastFrame)
Last log time: $($Analysis.lastLogTime)
Attack alerts: $($stats.attackAlerts)
Peak pressure: $($stats.peakPressure)
Observed Verdance export marker: $($Analysis.observedExport)

## Commentary

$Commentary

## Top Attack Alerts

$($attackLines -join "`r`n")

## Flat Packet Files

- manifest.json
- summary.md
- analytics_packet.json
- analytics_report.html
- save_metadata.lua
- savegame.ssf
"@
  Set-Content -Encoding UTF8 -LiteralPath $summaryPath -Value $summary

  $manifest = [ordered]@{
    schemaVersion = "verdance-flat-save-packet/0.1"
    kind = $Kind
    saveName = $SaveName
    mapName = $Analysis.mapName
    gameId = $Analysis.gameId
    lastFrame = $Analysis.lastFrame
    lastLogTime = $Analysis.lastLogTime
    observedExport = $Analysis.observedExport
    attackAlerts = $stats.attackAlerts
    peakPressure = $stats.peakPressure
    files = [ordered]@{
      summary = "summary.md"
      analyticsPacket = "analytics_packet.json"
      analyticsReport = "analytics_report.html"
      saveMetadata = "save_metadata.lua"
      saveGame = "savegame.ssf"
    }
  }
  Save-Json $manifest $manifestPath
}

$config = Get-VerdanceConfig -Workspace $Workspace
if (-not $OutboxRoot) { $OutboxRoot = Join-Path $Workspace "_outbox" }
if (-not $DramaticSaveName) {
  $latest = Get-ChildItem -Path (Join-Path $config.barDataRoot "Saves") -File -Filter "*.lua" |
    Sort-Object LastWriteTime -Descending |
    Select-Object -First 1
  if (-not $latest) { throw "Could not find a latest BAR save metadata file." }
  $DramaticSaveName = [System.IO.Path]::GetFileNameWithoutExtension($latest.FullName)
}

$analysisScript = Join-Path $Workspace "scripts\analyze_bar_match.ps1"
& powershell -ExecutionPolicy Bypass -File $analysisScript -Workspace $Workspace | Write-Host

$subtleAnalysisPath = Join-Path $Workspace "_outbox\20260621_013534_all_that_simmers_v1_1_1_playtest_packet\reports\bar_match_analysis.json"
$subtleHtmlPath = Join-Path $Workspace "_outbox\20260621_013534_all_that_simmers_v1_1_1_playtest_packet\reports\bar_match_analysis.html"
if (!(Test-Path $subtleAnalysisPath)) { throw "Missing subtle analysis packet: $subtleAnalysisPath" }
if (!(Test-Path $subtleHtmlPath)) { throw "Missing subtle analysis report: $subtleHtmlPath" }

$dramaticAnalysisPath = Join-Path $Workspace "reports\bar_match_analysis.latest.json"
$dramaticHtmlPath = Join-Path $Workspace "reports\bar_match_analysis.latest.html"
if (!(Test-Path $dramaticAnalysisPath)) { throw "Missing dramatic analysis packet: $dramaticAnalysisPath" }
if (!(Test-Path $dramaticHtmlPath)) { throw "Missing dramatic analysis report: $dramaticHtmlPath" }

$subtleAnalysis = Get-Content -Raw -LiteralPath $subtleAnalysisPath | ConvertFrom-Json
$dramaticAnalysis = Get-Content -Raw -LiteralPath $dramaticAnalysisPath | ConvertFrom-Json

$stamp = Get-Date -Format "yyyyMMdd_HHmmss"
$exportDir = Join-Path $OutboxRoot "${stamp}_verdance_dual_save_flat_export"
$subtleDir = Join-Path $exportDir "subtle_$SubtleSaveName"
$dramaticDir = Join-Path $exportDir "dramatic_$DramaticSaveName"
New-Item -ItemType Directory -Force -Path $subtleDir, $dramaticDir | Out-Null

Copy-SavePair -BarDataRoot $config.barDataRoot -SaveName $SubtleSaveName -Destination $subtleDir
Copy-SavePair -BarDataRoot $config.barDataRoot -SaveName $DramaticSaveName -Destination $dramaticDir

Write-SavePacket `
  -Kind "subtle" `
  -SaveName $SubtleSaveName `
  -Destination $subtleDir `
  -Analysis $subtleAnalysis `
  -AnalysisHtml $subtleHtmlPath `
  -Commentary "Baseline/subtle playtest. The player established a base and made limited contact. This packet is useful for comparing early procedural setup, moderate scouting, and low-to-medium battlefield drama before the Javlen reinforcement branch."

Write-SavePacket `
  -Kind "dramatic" `
  -SaveName $DramaticSaveName `
  -Destination $dramaticDir `
  -Analysis $dramaticAnalysis `
  -AnalysisHtml $dramaticHtmlPath `
  -Commentary "Dramatic Javlen branch. The player used the reinforced Legion position to clear the Armada and Cortex/Vortex opposition, producing the stronger visual and tactical comparison point requested for inspection."

$indexPath = Join-Path $exportDir "EXPORT_INDEX.md"
$manifestPath = Join-Path $exportDir "export_manifest.json"
$index = @"
# Verdance Dual Save Flat Export

Generated: $(Get-Date -Format "s")

This export intentionally excludes raw logs. Each save has a single flat folder containing only the inspection/save artifacts and summary packets needed by intermediary layers.

## Folders

- subtle_$SubtleSaveName
- dramatic_$DramaticSaveName

## Intended Use

Use the subtle packet as the low-drama baseline. Use the dramatic packet as the Javlen-assisted outcome where Armada and Cortex/Vortex have been cleared.
"@
Set-Content -Encoding UTF8 -LiteralPath $indexPath -Value $index

$exportManifest = [ordered]@{
  schemaVersion = "verdance-dual-save-flat-export/0.1"
  generatedAt = (Get-Date).ToString("s")
  exportDir = $exportDir
  excludesRawLogs = $true
  saves = @(
    [ordered]@{ kind = "subtle"; saveName = $SubtleSaveName; folder = "subtle_$SubtleSaveName" },
    [ordered]@{ kind = "dramatic"; saveName = $DramaticSaveName; folder = "dramatic_$DramaticSaveName" }
  )
}
Save-Json $exportManifest $manifestPath

Write-Host "Wrote flat dual-save export: $exportDir"
Write-Host "Subtle folder: $subtleDir"
Write-Host "Dramatic folder: $dramaticDir"
