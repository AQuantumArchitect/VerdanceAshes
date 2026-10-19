<#
.SYNOPSIS
  Shared infolog packet parsing for Verdance telemetry consumers.

.DESCRIPTION
  These functions used to live inside run_translation_profiler.ps1. That file
  launches a headless BAR match in its own body, so dot-sourcing it to reuse the
  parser would launch a match as a side effect. Anything that wants to read
  VA_* packets out of an infolog therefore had to copy the regexes, and two
  copies had already drifted. One home, dot-sourced by both.

  Pure functions only: no launching, no state, no writes.

  Parse-CompactJsonPackets contract
  ---------------------------------
    input  : an infolog path and a marker such as VA_TELEMETRY_JSON_COMPACT
    output : Hashtable keyed by the packet's own integer "frame" field,
             valued with the parsed PSCustomObject
    accepts: "<MARKER> {json}" on one line, and the chunked form
             "<BASE>_BEGIN" / "<BASE>_CHUNK n/m <payload>" / "<BASE>_END"
             where <BASE> is <MARKER> with a trailing _COMPACT removed.
             A marker with no _COMPACT suffix is its own base, so
             VA_ZONE_FLOW_JSON picks up VA_ZONE_FLOW_JSON_BEGIN/_CHUNK/_END
             for free.
    first-wins per frame: an earlier packet for a frame is never replaced.
    every packet MUST carry a numeric top-level "frame" or it is dropped.

  ASCII only in this file: PowerShell 5.1 reads a BOM-less UTF-8 .ps1 as ANSI,
  which turns any non-ASCII byte into mojibake inside string literals.
#>

function Get-FrameLabel {
  param([int]$Frame)
  $seconds = $Frame / 30
  $minutes = $seconds / 60
  if ($minutes -lt 1) { return ("{0:F0}sec" -f $seconds) }
  return ("{0:F1}min" -f $minutes)
}

function Parse-CompactJsonPackets {
  param(
    [string]$Infolog,
    [string]$Marker,
    # Set by callers that would rather know than silently measure nothing.
    # Every parse failure below is swallowed so one corrupt line cannot kill a
    # whole harvest, but a caller asserting "I expect packets" needs the count.
    [ref]$FailureCount = $null
  )
  $packets = @{}
  $failures = 0
  if (!(Test-Path $Infolog)) {
    if ($FailureCount) { $FailureCount.Value = $failures }
    return $packets
  }
  $pattern = [regex]::Escape($Marker) + '\s+(\{.+\})'
  $chunkMarker = $Marker -replace '_COMPACT$', ''
  $beginPattern = [regex]::Escape($chunkMarker) + '_BEGIN'
  # A single literal space before the payload, not \s+. The producer pads
  # nothing, and a greedy \s+ in front of a possibly-empty capture eats a
  # payload's own leading space -- which silently corrupts the rejoined JSON
  # only when a chunk boundary happens to fall on a space.
  $chunkPattern = [regex]::Escape($chunkMarker) + '_CHUNK\s+\d+/\d+ (.*)$'
  $endPattern = [regex]::Escape($chunkMarker) + '_END'
  $inChunk = $false
  $chunks = [System.Collections.Generic.List[string]]::new()

  foreach ($line in (Get-Content -LiteralPath $Infolog -Encoding UTF8)) {
    if ($line -match $pattern) {
      try {
        $packet = $Matches[1] | ConvertFrom-Json
        $frame = [int]$packet.frame
        if (-not $packets.ContainsKey($frame)) { $packets[$frame] = $packet }
      } catch {
        $failures++
      }
      continue
    }

    if ($line -match $beginPattern) {
      $inChunk = $true
      $chunks.Clear()
      continue
    }
    if ($inChunk -and $line -match $chunkPattern) {
      [void]$chunks.Add($Matches[1])
      continue
    }
    if ($inChunk -and $line -match $endPattern) {
      $inChunk = $false
      try {
        $json = -join $chunks
        $packet = $json | ConvertFrom-Json
        $frame = [int]$packet.frame
        if (-not $packets.ContainsKey($frame)) { $packets[$frame] = $packet }
      } catch {
        $failures++
      }
      $chunks.Clear()
    }
  }
  if ($FailureCount) { $FailureCount.Value = $failures }
  return $packets
}

function Find-PacketNearFrame {
  param($Packets, [int]$Frame, [int]$Tolerance = 60)
  if ($Packets.ContainsKey($Frame)) { return $Packets[$Frame] }
  foreach ($key in ($Packets.Keys | Sort-Object)) {
    if ([math]::Abs([int]$key - $Frame) -le $Tolerance) { return $Packets[$key] }
  }
  return $null
}

function Convert-TeamBucketSummary {
  param($Bucket)
  if (-not $Bucket) { return $null }
  $m = $Bucket.metrics
  $total = [double]$m.armyValue + [double]$m.buildPower + [double]$m.defensiveValue
  return [ordered]@{
    teamId = [int]$Bucket.teamId
    side = [string]$Bucket.side
    armyValue = [double]$m.armyValue
    buildPower = [double]$m.buildPower
    defensiveValue = [double]$m.defensiveValue
    totalPresence = $total
    totalUnitValue = [double]$m.totalUnitValue
    unitCount = [int]$m.unitCount
    combatUnitCount = [int]$m.combatUnitCount
    builderUnitCount = [int]$m.builderUnitCount
    structureCount = [int]$m.structureCount
    unitCountsByDef = $Bucket.unitCountsByDef
  }
}

function Convert-TelemetryZoneSummary {
  param($Telemetry)
  $zones = @()
  if (-not $Telemetry -or -not $Telemetry.zones) { return $zones }
  foreach ($prop in $Telemetry.zones.PSObject.Properties) {
    $zone = $prop.Value
    $teams = @()
    $total = 0
    $units = 0
    foreach ($bucket in @($zone.teams)) {
      $summary = Convert-TeamBucketSummary $bucket
      if ($summary) {
        $teams += $summary
        $total += [double]$summary.totalPresence
        $units += [int]$summary.unitCount
      }
    }
    $zones += [ordered]@{
      zoneId = [string]$zone.zoneId
      label = [string]$zone.label
      totalPresence = $total
      unitCount = $units
      teams = $teams
    }
  }
  return @($zones | Sort-Object -Descending -Property @{ Expression = { [double]$_.totalPresence } })
}
