param(
  [string]$Workspace = "",
  [string]$Infolog = "",
  [string]$OutPath = ""
)

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
        if ($ch -eq '\') { $escape = $true; continue }
        if ($ch -eq '"') { $inString = $false; continue }
      } else {
        if ($ch -eq '"') { $inString = $true; continue }
        if ($ch -eq '{') { $depth++; continue }
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
  param([string]$Text, [string]$Prefix)
  $lines = $Text -split "`r?`n"
  $blocks = New-Object System.Collections.Generic.List[string]
  $current = $null

  foreach ($line in $lines) {
    if ($line -match "$Prefix`_BEGIN") {
      $current = New-Object System.Collections.Generic.List[string]
      continue
    }
    if ($line -match "$Prefix`_CHUNK\s+\d+\/\d+\s+(.*)$") {
      if ($null -ne $current) { [void]$current.Add($Matches[1]) }
      continue
    }
    if ($line -match "$Prefix`_END") {
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
if (-not $Infolog) { $Infolog = $config.infolog }
if (-not $OutPath) { $OutPath = Join-Path $Workspace "outbox\bar_zone_telemetry.latest.json" }
if (!(Test-Path $Infolog)) { throw "infolog.txt not found at $Infolog" }

$raw = Get-Content -Raw -LiteralPath $Infolog
$json = Get-LastChunkedJson -Text $raw -Prefix "VA_TELEMETRY_JSON"
if (-not $json) {
  $json = Get-BalancedJsonAfterMarker -Text $raw -Marker "VA_TELEMETRY_JSON_COMPACT"
}
if (-not $json) {
  $tail = ($raw -split "`r?`n" | Select-Object -Last 80) -join "`n"
  throw "Could not extract Verdance telemetry JSON from infolog. Tail:`n$tail"
}

try {
  $parsed = $json | ConvertFrom-Json
} catch {
  throw "Extracted telemetry was not valid JSON. Text starts: $($json.Substring(0, [Math]::Min(240, $json.Length)))"
}

if ($parsed.schemaVersion -ne "bar-zone-telemetry/1.0") {
  throw "Unexpected telemetry schema: $($parsed.schemaVersion)"
}
if (-not $parsed.teams -or @($parsed.teams).Count -lt 1) {
  throw "Telemetry did not include any teams."
}
if (-not $parsed.zones) {
  throw "Telemetry did not include zones."
}

New-Item -ItemType Directory -Force -Path (Split-Path -Parent $OutPath) | Out-Null
$parsed | ConvertTo-Json -Depth 80 | Set-Content -Encoding UTF8 -Path $OutPath
Write-Host "Extracted latest BAR telemetry to: $OutPath"
Write-Host "Frame: $($parsed.frame)"
Write-Host "Balance verdict: $($parsed.balance.verdict)"
Write-Host "Value ratio: $($parsed.balance.valueRatio)"
