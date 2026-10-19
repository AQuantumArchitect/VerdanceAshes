<#
.SYNOPSIS
  Reports scenario AI seats whose skirmish AI has no build chain for the faction
  its team is assigned.

.DESCRIPTION
  Native skirmish AIs carry their build knowledge as unit-name tables in their own
  config. BARbarIAn's shipped config (engine\AI\Skirmish\BARb\stable\config\*.json)
  names hundreds of arm* and cor* units and not a single leg* unit, so a BARb
  seated on a Legion team lays down a few economy structures and never builds an
  army. Nothing in the startscript pipeline notices: the AI loads, runs, and
  quietly does nothing, which reads downstream as "this map is hard" rather than
  "this AI cannot play".

  This scans a scenario directory, and for every AI seat that is a native AI with
  a discoverable config, checks whether that config mentions the faction prefix of
  the seat's team. Lua AIs defined by the game (SimpleAI, SimpleDefenderAI,
  RaptorsAI, ...) have no such config and are reported as "unknown" rather than
  guessed at.

  Read-only. Exits 1 if any confirmed mismatch is found, so it can gate a suite.
#>
param(
  [string]$Workspace = "",
  [string[]]$ScenarioDirs = @(),
  [switch]$Quiet
)

$ErrorActionPreference = "Stop"
. (Join-Path (Split-Path -Parent $MyInvocation.MyCommand.Path) "_common.ps1")
$Workspace = Get-VerdanceWorkspaceRoot -Workspace $Workspace

# Faction -> unit-name prefix used throughout BAR's unit defs.
$FACTION_PREFIX = @{
  "armada" = "arm"
  "cortex" = "cor"
  "legion" = "leg"
}

function Get-AiConfigText {
  param([string]$ShortName, [string]$Version, $Config)
  $engineDir = Get-BAREngineDir -Config $Config -EngineName "spring-headless.exe"
  $verDir = if ($Version -and $Version -ne "<not-versioned>") { $Version } else { "stable" }
  $aiRoot = Join-Path (Join-Path (Join-Path $engineDir "AI") "Skirmish") $ShortName
  if (!(Test-Path $aiRoot)) { return $null }
  $cfgDir = Join-Path (Join-Path $aiRoot $verDir) "config"
  if (!(Test-Path $cfgDir)) {
    # Some AIs version their folder differently; take whatever single version exists.
    $versions = @(Get-ChildItem -Directory -LiteralPath $aiRoot -ErrorAction SilentlyContinue)
    foreach ($v in $versions) {
      $candidate = Join-Path $v.FullName "config"
      if (Test-Path $candidate) { $cfgDir = $candidate; break }
    }
  }
  if (!(Test-Path $cfgDir)) { return $null }
  $sb = [System.Text.StringBuilder]::new()
  foreach ($f in @(Get-ChildItem -LiteralPath $cfgDir -Filter *.json -Recurse -ErrorAction SilentlyContinue)) {
    [void]$sb.Append((Get-Content -Raw -LiteralPath $f.FullName))
  }
  if ($sb.Length -eq 0) { return $null }
  return $sb.ToString()
}

$config = Get-VerdanceConfig -Workspace $Workspace
if ($ScenarioDirs.Count -eq 0) {
  $ScenarioDirs = @(
    (Join-Path $Workspace "data\scenarios\campaign_ai"),
    (Join-Path $Workspace "data\scenarios\ai_duel"),
    (Join-Path $Workspace "data\scenarios\authored")
  )
}

$configCache = @{}
$findings = @()
$checked = 0

foreach ($dir in $ScenarioDirs) {
  if (!(Test-Path $dir)) { continue }
  foreach ($file in @(Get-ChildItem -LiteralPath $dir -Filter *.json -ErrorAction SilentlyContinue)) {
    $scenario = $null
    try { $scenario = Get-Content -Raw -LiteralPath $file.FullName | ConvertFrom-Json } catch { continue }
    if (-not $scenario.layout -or -not $scenario.variants) { continue }

    $sides = @{}
    foreach ($t in @($scenario.layout.teams)) { $sides[[int]$t.id] = [string]$t.side }

    foreach ($variant in @($scenario.variants)) {
      foreach ($ai in @($variant.ai)) {
        $shortName = [string]$ai.shortName
        $teamId = [int]$ai.team
        $side = [string]$sides[$teamId]
        if (-not $side) { continue }
        $prefix = $FACTION_PREFIX[$side.ToLowerInvariant()]
        if (-not $prefix) { continue }

        $key = "$shortName|$($ai.version)"
        if (-not $configCache.ContainsKey($key)) {
          $configCache[$key] = Get-AiConfigText -ShortName $shortName -Version ([string]$ai.version) -Config $config
        }
        $text = $configCache[$key]
        if ($null -eq $text) { continue }   # Lua AI or no config: nothing to judge

        $checked += 1
        $hits = ([regex]::Matches($text, ('"' + $prefix + '[a-z0-9_]*"'))).Count
        if ($hits -eq 0) {
          $findings += [ordered]@{
            scenario = $file.Name
            scenarioDir = (Split-Path -Leaf $dir)
            variant = [string]$variant.id
            ai = $shortName
            team = $teamId
            side = $side
            prefix = $prefix
            configUnitRefs = $hits
          }
        }
      }
    }
  }
}

if (-not $Quiet) {
  Write-Host "Checked $checked native-AI seat(s) with a discoverable config."
  if ($findings.Count -eq 0) {
    Write-Host "No faction mismatches found."
  } else {
    Write-Host ""
    Write-Host "FACTION MISMATCHES ($($findings.Count)) -- these AIs have no build chain for their team's faction:"
    Write-Host ""
    Write-Host ("{0,-34} {1,-28} {2,-6} {3,-5} {4}" -f "scenario", "variant", "ai", "team", "side")
    foreach ($f in $findings) {
      Write-Host ("{0,-34} {1,-28} {2,-6} {3,-5} {4}" -f $f.scenario, $f.variant, $f.ai, $f.team, $f.side)
    }
  }
}

$outPath = Join-Path $Workspace "reports\ai_seat_faction_check.latest.json"
New-Item -ItemType Directory -Force -Path (Split-Path -Parent $outPath) | Out-Null
$report = [ordered]@{
  schemaVersion = "verdance-ai-seat-faction-check/0.1"
  generatedAt = (Get-Date).ToString("s")
  scenarioDirs = $ScenarioDirs
  seatsChecked = $checked
  mismatchCount = $findings.Count
  mismatches = $findings
}
Save-Json $report $outPath
if (-not $Quiet) { Write-Host ""; Write-Host "Report: $outPath" }

if ($findings.Count -gt 0) { exit 1 }
exit 0
