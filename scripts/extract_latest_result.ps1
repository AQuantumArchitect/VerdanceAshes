param([string]$Workspace = "")
$ErrorActionPreference = "Stop"
. (Join-Path (Split-Path -Parent $MyInvocation.MyCommand.Path) "_common.ps1")
$Workspace = Get-VerdanceWorkspaceRoot -Workspace $Workspace

function Get-BalancedJsonAfterMarker {
  param([string]$Text, [string]$Marker)
  $matches = [regex]::Matches($Text, [regex]::Escape($Marker))
  if (!$matches -or $matches.Count -eq 0) { return $null }

  for ($m = $matches.Count - 1; $m -ge 0; $m--) {
    $searchStart = $matches[$m].Index + $matches[$m].Length
    $braceStart = $Text.IndexOf("{", $searchStart)
    if ($braceStart -lt 0) { continue }

    $depth = 0
    $inString = $false
    $escape = $false

    for ($i = $braceStart; $i -lt $Text.Length; $i++) {
      $ch = $Text[$i]
      if ($inString) {
        if ($escape) { $escape = $false; continue }
        if ($ch -eq '\\') { $escape = $true; continue }
        if ($ch -eq '"') { $inString = $false; continue }
      } else {
        if ($ch -eq '"') { $inString = $true; continue }
        if ($ch -eq '{') { $depth++ ; continue }
        if ($ch -eq '}') {
          $depth--
          if ($depth -eq 0) {
            return $Text.Substring($braceStart, $i - $braceStart + 1)
          }
        }
      }
    }
  }
  return $null
}

function Get-LastChunkedJson {
  param([string]$Text)
  $lines = $Text -split "`r?`n"
  $blocks = New-Object System.Collections.Generic.List[string]
  $current = $null

  foreach ($line in $lines) {
    if ($line -match 'VA_RESULT_JSON_BEGIN') {
      $current = New-Object System.Collections.Generic.List[string]
      continue
    }
    if ($line -match 'VA_RESULT_JSON_CHUNK\s+\d+\/\d+\s+(.*)$') {
      if ($null -ne $current) { [void]$current.Add($Matches[1]) }
      continue
    }
    if ($line -match 'VA_RESULT_JSON_END') {
      if ($null -ne $current) {
        [void]$blocks.Add(($current.ToArray() -join ""))
        $current = $null
      }
      continue
    }
  }

  if ($blocks.Count -gt 0) { return $blocks[$blocks.Count - 1] }
  return $null
}

$config = Get-VerdanceConfig -Workspace $Workspace
$infolog = $config.infolog
if (!(Test-Path $infolog)) { throw "infolog.txt not found at $infolog" }
$raw = Get-Content $infolog -Raw

# Preferred path for v0.7.1+: chunked JSON avoids BAR/infolog line wrapping problems.
$json = Get-LastChunkedJson -Text $raw

# Backward-compatible path for old compact output. This scans the raw file, not just one line.
if (-not $json) {
  $json = Get-BalancedJsonAfterMarker -Text $raw -Marker 'VA_RESULT_JSON_COMPACT'
}

if (-not $json) {
  $tail = ($raw -split "`r?`n" | Select-Object -Last 40) -join "`n"
  $beginCount = ([regex]::Matches($raw, "VA_RESULT_JSON_BEGIN")).Count
  $compactCount = ([regex]::Matches($raw, "VA_RESULT_JSON_COMPACT")).Count
  $failPath = Join-Path $Workspace "outbox\result_harvest_fail.latest.json"
  try {
    New-Item -ItemType Directory -Force -Path (Split-Path -Parent $failPath) | Out-Null
    $diag = @{
      schemaVersion = "verdance-result-harvest-fail/1.0"
      at = (Get-Date).ToUniversalTime().ToString("o")
      infolog = $infolog
      markerCounts = @{ VA_RESULT_JSON_BEGIN = $beginCount; VA_RESULT_JSON_COMPACT = $compactCount }
      tail = $tail
      hint = "No complete VA_RESULT in infolog. Play a sortie to terminal, or Abandon from hub."
    } | ConvertTo-Json -Depth 6
    Set-Content -Encoding UTF8 -Path $failPath -Value $diag
    Write-Host "Harvest fail diagnostics: $failPath"
  } catch { }
  throw "Could not extract Verdance result JSON from infolog. See outbox\result_harvest_fail.latest.json. Tail:`n$tail"
}

try {
  $parsed = $json | ConvertFrom-Json
} catch {
  throw "Extracted text was not valid JSON. Text starts: $($json.Substring(0, [Math]::Min(240, $json.Length)))"
}

$out = $config.resultInbox
New-Item -ItemType Directory -Force -Path (Split-Path -Parent $out) | Out-Null
$payload = ($parsed | ConvertTo-Json -Depth 50 -Compress)
Set-Content -Encoding UTF8 -Path $out -Value $payload
Write-Host "Extracted latest BAR result to: $out"
Write-Host $payload

# Protocol: extract ONLY writes inbox (+ archive). Campaign advance / hub rebuild
# is owned solely by kernel.bring_home / apply_result (no half-apply here).
try {
  $rk = $null
  if ($parsed.PSObject.Properties.Name -contains "resultKey") { $rk = [string]$parsed.resultKey }
  if ([string]::IsNullOrWhiteSpace($rk)) { $rk = "unknown_" + (Get-Date -Format "yyyyMMdd_HHmmss") }
  $safeKey = ($rk -replace '[\\/:*?"<>|]', '_')
  $archiveDir = Join-Path $Workspace "inbox\archive"
  New-Item -ItemType Directory -Force -Path $archiveDir | Out-Null
  $archivePath = Join-Path $archiveDir ($safeKey + ".json")
  Set-Content -Encoding UTF8 -Path $archivePath -Value $payload
  Write-Host "Archived result: $archivePath"
} catch {
  Write-Warning "Result archive skipped: $($_.Exception.Message)"
}

# WO-042: harvest in-engine next-mission pick from debrief (if player pressed 1/2/3).
$choiceJson = Get-BalancedJsonAfterMarker -Text $raw -Marker 'VA_NEXT_SORTIE_CHOICE'
if ($choiceJson) {
  try {
    $choice = $choiceJson | ConvertFrom-Json
    $choicePath = Join-Path $Workspace "outbox\next_sortie_choice.json"
    if (-not $choice.patron) { $choice | Add-Member -NotePropertyName patron -NotePropertyValue "nullmercs" -Force }
    if (-not $choice.schemaVersion) { $choice | Add-Member -NotePropertyName schemaVersion -NotePropertyValue "verdance-sortie-order/1.0" -Force }
    $choice | ConvertTo-Json -Depth 20 | Set-Content -Encoding UTF8 -Path $choicePath
    Write-Host "Extracted next sortie choice to: $choicePath"
  } catch {
    Write-Warning "VA_NEXT_SORTIE_CHOICE present but not valid JSON: $($_.Exception.Message)"
  }
}
