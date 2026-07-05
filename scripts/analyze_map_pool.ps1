param(
  [string]$Workspace = "$env:USERPROFILE\Documents\BAR_Verdance_Workspace",
  [string]$MapDetailsPath = "",
  [string]$OutDir = ""
)

$ErrorActionPreference = "Stop"

function Normalize-Token {
  param([string]$Text)
  if (-not $Text) { return "" }
  return (($Text.ToLowerInvariant() -replace '[^a-z0-9]+', ''))
}

function Parse-Bool {
  param([string]$Value)
  if ($Value -eq "1") { return $true }
  return $false
}

function Parse-Int {
  param([string]$Value)
  if ($Value -match '^-?\d+$') { return [int]$Value }
  return $null
}

function Unescape-LuaString {
  param([string]$Value)
  if ($null -eq $Value) { return $null }
  return ($Value -replace "\\'", "'" -replace '\\"', '"' -replace '\\n', "`n" -replace '\\r', "`r" -replace '\\t', "`t")
}

function Get-LuaProp {
  param(
    [string]$Body,
    [string]$Name,
    [switch]$String
  )
  $escapedName = [regex]::Escape($Name)
  if ($String) {
    if ($Body -match "(?:^|, )$escapedName='((?:\\'|[^'])*)'") {
      return Unescape-LuaString $matches[1]
    }
    if ($Body -match "(?:^|, )$escapedName=nil") { return $null }
    return $null
  }
  if ($Body -match "(?:^|, )$escapedName=([^,}]+)") {
    return ($matches[1].Trim())
  }
  return $null
}

function New-MapOpinion {
  param($Map)

  $tags = New-Object System.Collections.Generic.List[string]
  $focus = New-Object System.Collections.Generic.List[string]

  $area = $Map.Width * $Map.Height
  $shape = if ($Map.Width -gt ($Map.Height * 1.35)) { "wide" } elseif ($Map.Height -gt ($Map.Width * 1.35)) { "tall" } else { "square" }
  $scale = if ($area -lt 120) { "micro" } elseif ($area -lt 250) { "small" } elseif ($area -lt 450) { "medium" } elseif ($area -lt 800) { "large" } else { "huge" }

  if ($Map.Special -eq "No Metal") {
    $tags.Add("converter-economy")
    $focus.Add("power curve")
    $focus.Add("converter timing")
  } elseif ($Map.Special -eq "Metal") {
    $tags.Add("metal-economy")
    $focus.Add("contest timing")
    $focus.Add("metal denial")
  } elseif ($Map.Special -eq "Lava") {
    $tags.Add("hazard-lava")
    $focus.Add("pathing discipline")
  } elseif ($Map.Special -eq "Dam") {
    $tags.Add("chokepoint-dam")
    $focus.Add("bridge timing")
  } elseif ($Map.Special -eq "Tar") {
    $tags.Add("slow-terrain")
    $focus.Add("mobility choice")
  } elseif ($Map.Special -eq "Air") {
    $tags.Add("air-dominant")
    $focus.Add("air timing")
  } elseif ($Map.Special -eq "PVE") {
    $tags.Add("pve")
    $focus.Add("survival pacing")
  } elseif ($Map.Special -eq "Asymmetrical") {
    $tags.Add("asymmetrical")
    $focus.Add("spawn bias")
  }

  if ($Map.IsFFA) {
    $tags.Add("ffa")
    $focus.Add("third-party risk")
  } elseif ($Map.TeamCount -gt 2) {
    $tags.Add("team-free-for-all")
    $focus.Add("multi-front pressure")
  } elseif ($Map.Is1v1) {
    $tags.Add("duel")
    $focus.Add("opening efficiency")
  } else {
    $tags.Add("team-lane")
    $focus.Add("frontline shape")
  }

  if ($Map.Water -and $Map.Water -ne "nil") {
    $tags.Add("mixed-water")
    $focus.Add("amphibious timing")
  }
  if ($Map.Flat -and $Map.Flat -ne "nil" -and -not $Map.Water) {
    $tags.Add("open-ground")
  }
  if ($Map.Hills -and $Map.Hills -ne "nil") {
    $tags.Add("terrain-cover")
  }

  $info = if ($Map.InfoText) { $Map.InfoText.ToLowerInvariant() } else { "" }
  if ($info -match 'lane|chokepoint|bridge|crossing') {
    $tags.Add("lane-map")
    $focus.Add("lane pressure")
  }
  if ($info -match 'island|shore|coast|sea|water|naval') {
    $tags.Add("coastal")
    $focus.Add("naval shoreline control")
  }
  if ($info -match 'center|middle|middle.*control|center.*control') {
    $tags.Add("center-contest")
    $focus.Add("middle control")
  }
  if ($info -match 'metal') {
    $tags.Add("metal-keyed")
  }
  if ($info -match 'expan|spread|territor') {
    $tags.Add("expansion-map")
    $focus.Add("expansion tempo")
  }

  if (-not $focus.Count) {
    $focus.Add("early scouting")
    $focus.Add("positioning")
  }

  $opinion = switch ($Map.Special) {
    "No Metal" { "Eco-first map with very little tolerance for sloppy power spend." }
    "Metal" { "Economy is baked into the terrain; control and denial matter more than raw expansion." }
    "Lava" { "Hazard map that rewards route discipline and punishes overcommitment." }
    "Dam" { "Crossing pressure matters; the map wants tactical timing and artillery leverage." }
    "Tar" { "Mobility and pathing choices are the main skill check here." }
    "Air" { "Air control and vertical pressure are part of the map identity." }
    "PVE" { "Best treated as a survival or scenario map rather than a clean ladder-style baseline." }
    "Asymmetrical" { "Expect spawn-side bias and uneven expansion value; balance needs extra care." }
    default {
      if ($Map.IsFFA) {
        "FFA pressure cooker; expansion safety and threat management define the game."
      } elseif ($Map.TeamCount -gt 2) {
        "Large team map; front shape and reinforcement timing matter more than single fights."
      } elseif ($Map.Is1v1) {
        "Duel map; opening efficiency and first-contest timing are the whole story."
      } else {
        "Team map with a recognizable front; map control and staging depth should be measurable."
      }
    }
  }

  if ($Map.Water -and $Map.Water -ne "nil" -and $Map.Special -ne "Air") {
    $opinion += " Water interaction likely shifts the factory mix."
  }
  if ($Map.Special -eq "No Metal") {
    $opinion += " This is a converter economy map, so build power is the real scoreboard."
  }
  if ($Map.Special -eq "Metal") {
    $opinion += " Metal density is part of the battlefield, not just the economy."
  }

  $recommendation = if ($Map.Special -eq "No Metal") {
    "Legion BARbarIAn aggressive vs Cortex SimpleAI"
  } elseif ($Map.IsFFA -or $Map.TeamCount -gt 2) {
    "Mixed BARb/simple pressure test"
  } elseif ($Map.Is1v1) {
    "SimpleAI vs BARbarIAn hard"
  } else {
    "SimpleAI baseline first, then BARbarIAn aggressive"
  }

  return [pscustomobject]@{
    map = $Map.Title
    archivePresent = [bool]$Map.ArchivePresent
    archiveStem = $Map.ArchiveStem
    width = $Map.Width
    height = $Map.Height
    area = $area
    scale = $scale
    shape = $shape
    special = $Map.Special
    is1v1 = [bool]$Map.Is1v1
    isTeam = [bool]$Map.IsTeam
    isFFA = [bool]$Map.IsFFA
    playerCount = $Map.PlayerCount
    teamCount = $Map.TeamCount
    author = $Map.Author
    infoText = $Map.InfoText
    archetype = ($tags -join ", ")
    opinion = $opinion
    measurementFocus = (@($focus | Select-Object -Unique) -join ", ")
    recommendedBaseline = $recommendation
  }
}

if (-not $MapDetailsPath) {
  $MapDetailsPath = Join-Path $env:LOCALAPPDATA "Programs\Beyond-All-Reason\data\games\BYAR-Chobby.sdd\LuaMenu\configs\gameConfig\byar\mapDetails.lua"
}
if (!(Test-Path $MapDetailsPath)) { throw "Map details file not found: $MapDetailsPath" }

if (-not $OutDir) {
  $OutDir = Join-Path $Workspace "reports"
}
New-Item -ItemType Directory -Force -Path $OutDir | Out-Null

$mapArchiveDir = Join-Path $env:LOCALAPPDATA "Programs\Beyond-All-Reason\data\maps"
$archiveIndex = @{}
if (Test-Path $mapArchiveDir) {
  foreach ($archive in Get-ChildItem -File -Path $mapArchiveDir -Filter *.sd7) {
    $stem = [System.IO.Path]::GetFileNameWithoutExtension($archive.Name)
    $archiveIndex[(Normalize-Token $stem)] = $archive.Name
  }
}

$maps = New-Object System.Collections.Generic.List[object]
foreach ($line in Get-Content -LiteralPath $MapDetailsPath) {
  if ($line -notmatch "^\['(?<name>(?:\\'|[^'])+)'\]=\{(?<body>.*)\},$") { continue }
  $title = Unescape-LuaString $matches.name
  $body = $matches.body
  $map = [ordered]@{
    Title = $title
    Width = (Parse-Int (Get-LuaProp $body "Width"))
    Height = (Parse-Int (Get-LuaProp $body "Height"))
    Is1v1 = Parse-Bool (Get-LuaProp $body "Is1v1")
    IsTeam = Parse-Bool (Get-LuaProp $body "IsTeam")
    IsFFA = Parse-Bool (Get-LuaProp $body "IsFFA")
    Special = (Get-LuaProp $body "Special" -String)
    Flat = Parse-Bool (Get-LuaProp $body "Flat")
    Hills = Parse-Bool (Get-LuaProp $body "Hills")
    Water = Parse-Bool (Get-LuaProp $body "Water")
    IsInPool = Parse-Bool (Get-LuaProp $body "IsInPool")
    PlayerCount = (Parse-Int (Get-LuaProp $body "PlayerCount" -String))
    TeamCount = (Parse-Int (Get-LuaProp $body "TeamCount" -String))
    Author = (Get-LuaProp $body "Author" -String)
    InfoText = (Get-LuaProp $body "InfoText" -String)
    LastUpdate = (Parse-Int (Get-LuaProp $body "LastUpdate"))
  }
  if (-not $map.IsInPool) { continue }
  $normalized = Normalize-Token $title
  $archiveStem = $archiveIndex[$normalized]
  $map.ArchiveStem = $archiveStem
  $map.ArchivePresent = [bool]$archiveStem
  $maps.Add([pscustomobject]$map) | Out-Null
}

$opinionRows = foreach ($map in $maps) {
  New-MapOpinion $map
}

$summary = [ordered]@{
  schemaVersion = "verdance-map-pool-opinion/0.1"
  generatedAt = (Get-Date).ToString("s")
  mapDetailsPath = $MapDetailsPath
  mapArchiveDir = $mapArchiveDir
  totalMaps = @($opinionRows).Count
  localArchivesMatched = @($opinionRows | Where-Object { $_.archivePresent }).Count
    missingArchives = @($opinionRows | Where-Object { -not $_.archivePresent } | Select-Object -ExpandProperty map)
  specials = [ordered]@{
    noMetal = @($opinionRows | Where-Object { $_.special -eq "No Metal" }).Count
    metal = @($opinionRows | Where-Object { $_.special -eq "Metal" }).Count
    lava = @($opinionRows | Where-Object { $_.special -eq "Lava" }).Count
    water = @($opinionRows | Where-Object { $_.measurementFocus -match 'naval shoreline control|amphibious timing' }).Count
    ffa = @($opinionRows | Where-Object { $_.isFFA }).Count
    duel = @($opinionRows | Where-Object { $_.is1v1 }).Count
  }
}

$jsonPath = Join-Path $OutDir "map_pool_opinions.latest.json"
$summaryPath = Join-Path $OutDir "map_pool_opinions.latest.md"
$summary | Add-Member -NotePropertyName maps -NotePropertyValue $opinionRows
$summary | ConvertTo-Json -Depth 20 | Set-Content -Encoding UTF8 -Path $jsonPath

$lines = @(
  "# Map Pool Opinions",
  "",
  "- Source: ``$MapDetailsPath``",
  "- Maps in pool: ``$($summary.totalMaps)``",
  "- Local archives matched: ``$($summary.localArchivesMatched)``",
  "",
  "| Map | Arch | Size | Archetype | Opinion | Focus | Baseline |",
  "| --- | --- | --- | --- | --- | --- | --- |"
)
foreach ($row in $opinionRows) {
  $arch = if ($row.archivePresent) { "yes" } else { "no" }
  $size = "$($row.width)x$($row.height)"
  $lines += "| $($row.map) | $arch | $size | $($row.archetype) | $($row.opinion) | $($row.measurementFocus) | $($row.recommendedBaseline) |"
}
$lines += ""
$lines += "## Missing Local Archives"
$lines += ""
if ($summary.missingArchives.Count -gt 0) {
  foreach ($name in $summary.missingArchives) {
    $lines += "- $name"
  }
} else {
  $lines += "- None"
}

$lines | Set-Content -Encoding UTF8 -Path $summaryPath

Write-Host "Wrote map pool opinion report: $summaryPath"
Write-Host "Wrote map pool opinion JSON: $jsonPath"
Write-Host "Maps analyzed: $($summary.totalMaps)"
Write-Host "Matched local archives: $($summary.localArchivesMatched)"
