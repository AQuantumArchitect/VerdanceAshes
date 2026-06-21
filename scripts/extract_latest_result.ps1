param([string]$Workspace = "$env:USERPROFILE\Documents\BAR_Verdance_Workspace")
$ErrorActionPreference = "Stop"
. (Join-Path (Split-Path -Parent $MyInvocation.MyCommand.Path) "_common.ps1")

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
  throw "Could not extract Verdance result JSON from infolog. Run /varesult again after installing v0.7.1. Tail:`n$tail"
}

try {
  $parsed = $json | ConvertFrom-Json
} catch {
  throw "Extracted text was not valid JSON. Text starts: $($json.Substring(0, [Math]::Min(240, $json.Length)))"
}

$out = $config.resultInbox
New-Item -ItemType Directory -Force -Path (Split-Path -Parent $out) | Out-Null
Set-Content -Encoding UTF8 -Path $out -Value ($parsed | ConvertTo-Json -Depth 50 -Compress)
Write-Host "Extracted latest BAR result to: $out"
Write-Host ($parsed | ConvertTo-Json -Depth 50 -Compress)
