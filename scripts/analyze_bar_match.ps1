param(
  [string]$Workspace = "$env:USERPROFILE\Documents\BAR_Verdance_Workspace",
  [string]$Infolog = "",
  [string]$OutDir = ""
)

$ErrorActionPreference = "Stop"
. (Join-Path (Split-Path -Parent $MyInvocation.MyCommand.Path) "_common.ps1")

function Convert-LogTimeToSeconds {
  param([string]$Value)
  if ($Value -match '^(\d+):(\d+):(\d+)(?:\.(\d+))?$') {
    $fraction = if ($Matches[4]) { [double]("0." + $Matches[4]) } else { 0.0 }
    return ([int]$Matches[1] * 3600) + ([int]$Matches[2] * 60) + [int]$Matches[3] + $fraction
  }
  return 0.0
}

function Format-Clock {
  param([double]$Seconds)
  $whole = [math]::Floor($Seconds)
  $hours = [math]::Floor($whole / 3600)
  $mins = [math]::Floor(($whole % 3600) / 60)
  $secs = $whole % 60
  return "{0:00}:{1:00}:{2:00}" -f $hours, $mins, $secs
}

function Html-Escape {
  param([string]$Text)
  return [System.Net.WebUtility]::HtmlEncode($Text)
}

function Parse-SetupText {
  param([string]$Raw)
  $match = [regex]::Match($Raw, 'SetupText="([^"]+)"')
  if (-not $match.Success) { return $null }
  try {
    $decoded = [System.Text.Encoding]::UTF8.GetString([Convert]::FromBase64String($match.Groups[1].Value))
  } catch {
    return $null
  }

  $sections = [ordered]@{}
  $current = $null
  foreach ($line in ($decoded -split "`r?`n")) {
    $trim = $line.Trim()
    if (-not $trim) { continue }
    if ($trim -match '^\[([^\]]+)\]$') {
      $current = $Matches[1].ToLowerInvariant()
      if (-not $sections.Contains($current)) { $sections[$current] = [ordered]@{} }
      continue
    }
    if ($current -and $trim -match '^([^=]+)=(.*);$') {
      $sections[$current][$Matches[1].ToLowerInvariant()] = $Matches[2]
    }
  }

  $teams = @()
  foreach ($key in $sections.Keys) {
    if ($key -match '^team(\d+)$') {
      $t = $sections[$key]
      $teams += [pscustomobject]@{
        team = [int]$Matches[1]
        side = $t.side
        allyTeam = $t.allyteam
        color = $t.rgbcolor
        startX = $t.startposx
        startZ = $t.startposz
      }
    }
  }

  $ais = @()
  foreach ($key in $sections.Keys) {
    if ($key -match '^ai(\d+)$') {
      $a = $sections[$key]
      $ais += [pscustomobject]@{
        id = [int]$Matches[1]
        team = $a.team
        name = $a.name
        shortName = $a.shortname
      }
    }
  }

  $players = @()
  foreach ($key in $sections.Keys) {
    if ($key -match '^player(\d+)$') {
      $p = $sections[$key]
      $players += [pscustomobject]@{
        id = [int]$Matches[1]
        name = $p.name
        team = $p.team
        spectator = $p.spectator
      }
    }
  }

  return [pscustomobject]@{
    mapName = if ($decoded -match '(?im)^mapname=([^;]+);') { $Matches[1] } else { $sections.game.mapname }
    gameType = if ($decoded -match '(?im)^gametype=([^;]+);') { $Matches[1] } else { $sections.game.gametype }
    debugCommands = $sections.modoptions.debugcommands
    teams = @($teams | Sort-Object team)
    ais = @($ais | Sort-Object id)
    players = @($players | Sort-Object id)
  }
}

function Add-Timeline {
  param(
    [System.Collections.Generic.List[object]]$Timeline,
    [double]$Seconds,
    [int]$Frame,
    [string]$Kind,
    [string]$Text
  )
  [void]$Timeline.Add([pscustomobject]@{
    time = Format-Clock $Seconds
    seconds = [math]::Round($Seconds, 3)
    frame = $Frame
    kind = $Kind
    text = $Text
  })
}

$config = Get-VerdanceConfig -Workspace $Workspace
if (-not $Infolog) { $Infolog = $config.infolog }
if (-not $OutDir) { $OutDir = Join-Path $Workspace "reports" }
if (!(Test-Path $Infolog)) { throw "infolog.txt not found at $Infolog" }

New-Item -ItemType Directory -Force -Path $OutDir | Out-Null
$raw = Get-Content -Raw -LiteralPath $Infolog
$lines = $raw -split "`r?`n"

$timeline = [System.Collections.Generic.List[object]]::new()
$attacks = [System.Collections.Generic.List[object]]::new()
$aiTakeovers = [System.Collections.Generic.List[object]]::new()
$vaEvents = [System.Collections.Generic.List[object]]::new()
$warnings = 0
$errors = 0
$lastFrame = $null
$lastSeconds = 0.0
$gameId = $null
$playerLoaded = $false
$setup = Parse-SetupText $raw

foreach ($line in $lines) {
  if (-not $line) { continue }
  if ($line -notmatch '^\[t=([^\]]+)\]\[f=([-\d]+)\]\s*(.*)$') { continue }
  $seconds = Convert-LogTimeToSeconds $Matches[1]
  $frame = [int]$Matches[2]
  $msg = $Matches[3]
  if ($frame -ge 0) { $lastFrame = $frame }
  if ($seconds -gt $lastSeconds) { $lastSeconds = $seconds }

  if ($msg -match '\bWarning:') { $warnings++ }
  if ($msg -match '\bError:|\bfatal\b|Exception|LUA_ERRRUN') { $errors++ }

  if ($msg -match 'WriteSetupText') {
    continue
  }
  if ($msg -match '^GameID:\s+(.+)$') {
    $gameId = $Matches[1].Trim()
    Add-Timeline $timeline $seconds $frame "game" ("GameID " + $gameId)
    continue
  }
  if ($msg -match 'Player VerdanceCommander finished loading') {
    $playerLoaded = $true
    Add-Timeline $timeline $seconds $frame "player" "Player finished loading"
    continue
  }
  if ($msg -match 'VerdanceCommander paused the game') {
    Add-Timeline $timeline $seconds $frame "pause" "Paused"
    continue
  }
  if ($msg -match 'VerdanceCommander unpaused the game') {
    Add-Timeline $timeline $seconds $frame "pause" "Unpaused"
    continue
  }
  if ($msg -match 'local skirmish AI "([^"]+)".*took over control of team (\d+)') {
    $obj = [pscustomobject]@{
      time = Format-Clock $seconds
      seconds = [math]::Round($seconds, 3)
      frame = $frame
      name = $Matches[1]
      team = [int]$Matches[2]
    }
    $aiTakeovers += $obj
    Add-Timeline $timeline $seconds $frame "ai" ("AI team {0}: {1}" -f $obj.team, $obj.name)
    continue
  }
  if ($msg -match '^(.+?) is being attacked!$') {
    $unit = $Matches[1]
    $obj = [pscustomobject]@{
      time = Format-Clock $seconds
      seconds = [math]::Round($seconds, 3)
      frame = $frame
      unit = $unit
      text = $msg
    }
    $attacks += $obj
    Add-Timeline $timeline $seconds $frame "attack" $msg
    continue
  }
  if ($msg -match '^Added (.+?) to autogroup #(\d+)\.$') {
    Add-Timeline $timeline $seconds $frame "control" ("Autogroup #{0}: {1}" -f $Matches[2], $Matches[1])
    continue
  }
  if ($msg -match '^Buildings set to face (.+)$') {
    Add-Timeline $timeline $seconds $frame "control" $msg
    continue
  }
  if ($msg -match '^VA_') {
    $ev = [pscustomobject]@{
      time = Format-Clock $seconds
      seconds = [math]::Round($seconds, 3)
      frame = $frame
      text = $msg
    }
    $vaEvents += $ev
    Add-Timeline $timeline $seconds $frame "verdance" $msg
    continue
  }
  if ($msg -match 'Spring finished with code|QuitAction|Game Over|won|lost|destroyed') {
    Add-Timeline $timeline $seconds $frame "system" $msg
    continue
  }
}

$attackSummary = @(
  $attacks |
    Group-Object unit |
    ForEach-Object {
      $items = @($_.Group | Sort-Object seconds)
      [pscustomobject]@{
        unit = $_.Name
        count = $_.Count
        first = $items[0].time
        last = $items[$items.Count - 1].time
        firstFrame = $items[0].frame
        lastFrame = $items[$items.Count - 1].frame
      }
    } |
    Sort-Object @{ Expression = "count"; Descending = $true }, unit
)

$bucketSize = 300
$attackBuckets = @(
  $attacks |
    Group-Object { [math]::Floor($_.seconds / $bucketSize) } |
    ForEach-Object {
      $start = [int]$_.Name * $bucketSize
      [pscustomobject]@{
        bucket = Format-Clock $start
        startSeconds = $start
        count = $_.Count
      }
    } |
    Sort-Object startSeconds
)

$stamp = Get-Date -Format "yyyyMMdd_HHmmss"
$jsonPath = Join-Path $OutDir "bar_match_analysis_$stamp.json"
$htmlPath = Join-Path $OutDir "bar_match_analysis_$stamp.html"
$latestJsonPath = Join-Path $OutDir "bar_match_analysis.latest.json"
$latestHtmlPath = Join-Path $OutDir "bar_match_analysis.latest.html"

$analysis = [ordered]@{
  schemaVersion = "verdance-bar-match-analysis/0.1"
  generatedAt = (Get-Date).ToString("s")
  sourceInfolog = $Infolog
  gameId = $gameId
  mapName = if ($setup) { $setup.mapName } else { $null }
  playerLoaded = $playerLoaded
  lastFrame = $lastFrame
  lastLogTime = Format-Clock $lastSeconds
  warningCount = $warnings
  errorCount = $errors
  setup = $setup
  aiTakeovers = @($aiTakeovers)
  attackSummary = @($attackSummary)
  attackBuckets = @($attackBuckets)
  timeline = @($timeline | Sort-Object seconds, frame)
  vaEvents = @($vaEvents)
  observedExport = [bool](@($vaEvents | Where-Object { $_.text -match 'VA_RESULT_JSON|VA_EXPORT|VA_STATUS' }).Count)
}

$analysis | ConvertTo-Json -Depth 60 | Set-Content -Encoding UTF8 -Path $jsonPath
$analysis | ConvertTo-Json -Depth 60 | Set-Content -Encoding UTF8 -Path $latestJsonPath

$teamRows = ""
if ($setup -and $setup.teams) {
  foreach ($team in $setup.teams) {
    $teamRows += "<tr><td>$($team.team)</td><td>$(Html-Escape $team.side)</td><td>$(Html-Escape $team.allyTeam)</td><td>$(Html-Escape $team.color)</td><td>$($team.startX), $($team.startZ)</td></tr>`n"
  }
}

$aiRows = ""
foreach ($ai in $aiTakeovers) {
  $aiRows += "<tr><td>$($ai.time)</td><td>$($ai.team)</td><td>$(Html-Escape $ai.name)</td></tr>`n"
}

$attackRows = ""
foreach ($attack in $attackSummary) {
  $attackRows += "<tr><td>$(Html-Escape $attack.unit)</td><td>$($attack.count)</td><td>$($attack.first)</td><td>$($attack.last)</td></tr>`n"
}

$maxBucket = 1
foreach ($b in $attackBuckets) { if ($b.count -gt $maxBucket) { $maxBucket = $b.count } }
$bucketRows = ""
foreach ($b in $attackBuckets) {
  $pct = [math]::Round(($b.count / $maxBucket) * 100)
  $bucketRows += "<tr><td>$($b.bucket)</td><td><div class='bar'><span style='width:$pct%'></span></div></td><td>$($b.count)</td></tr>`n"
}

$timelineRows = ""
foreach ($ev in (@($timeline | Sort-Object seconds, frame | Select-Object -Last 80))) {
  $timelineRows += "<tr><td>$($ev.time)</td><td>$($ev.frame)</td><td><span class='pill $($ev.kind)'>$($ev.kind)</span></td><td>$(Html-Escape $ev.text)</td></tr>`n"
}

$exportNote = if ($analysis.observedExport) { "Verdance export markers were observed." } else { "No /luarules vaexport result marker was observed in this log." }
$html = @"
<!doctype html>
<html>
<head>
<meta charset="utf-8">
<title>Verdance BAR Match Analysis</title>
<style>
  body { font-family: Segoe UI, Arial, sans-serif; margin: 24px; background: #101316; color: #e8edf2; }
  h1, h2 { margin: 0 0 12px; }
  h1 { font-size: 28px; }
  h2 { font-size: 18px; margin-top: 28px; }
  .grid { display: grid; grid-template-columns: repeat(4, minmax(140px, 1fr)); gap: 12px; margin: 18px 0; }
  .metric { border: 1px solid #2b333c; background: #171d23; border-radius: 8px; padding: 14px; }
  .metric b { display: block; font-size: 22px; margin-top: 4px; color: #9ad6ff; }
  .note { color: #b6c2cc; max-width: 980px; line-height: 1.45; }
  table { width: 100%; border-collapse: collapse; margin-top: 10px; background: #141a20; }
  th, td { border-bottom: 1px solid #28313a; text-align: left; padding: 9px 10px; vertical-align: top; }
  th { color: #9ad6ff; font-weight: 600; background: #18212a; }
  .pill { display: inline-block; padding: 2px 8px; border-radius: 999px; background: #2b333c; color: #d8e2ea; font-size: 12px; }
  .attack { background: #5c2430; }
  .pause { background: #3b3b24; }
  .ai { background: #263f66; }
  .player { background: #235640; }
  .game, .system { background: #333846; }
  .verdance { background: #4f315d; }
  .control { background: #25444a; }
  .bar { height: 14px; background: #252c33; border-radius: 999px; overflow: hidden; }
  .bar span { display: block; height: 100%; background: linear-gradient(90deg, #9ad6ff, #5fe0a1); }
  code { color: #cce7ff; }
</style>
</head>
<body>
<h1>Verdance BAR Match Analysis</h1>
<p class="note">Generated $($analysis.generatedAt) from <code>$(Html-Escape $Infolog)</code>. $exportNote</p>
<div class="grid">
  <div class="metric">Map<b>$(Html-Escape $analysis.mapName)</b></div>
  <div class="metric">Last Frame<b>$($analysis.lastFrame)</b></div>
  <div class="metric">Last Log Time<b>$($analysis.lastLogTime)</b></div>
  <div class="metric">Attack Alerts<b>$(@($attacks).Count)</b></div>
</div>
<div class="grid">
  <div class="metric">Warnings<b>$warnings</b></div>
  <div class="metric">Errors<b>$errors</b></div>
  <div class="metric">AI Takeovers<b>$(@($aiTakeovers).Count)</b></div>
  <div class="metric">GameID<b>$(Html-Escape $gameId)</b></div>
</div>
<h2>Teams From Save Setup</h2>
<table><thead><tr><th>Team</th><th>Side</th><th>AllyTeam</th><th>RGB</th><th>Start X/Z</th></tr></thead><tbody>$teamRows</tbody></table>
<h2>AI Control</h2>
<table><thead><tr><th>Time</th><th>Team</th><th>AI</th></tr></thead><tbody>$aiRows</tbody></table>
<h2>Attack Summary</h2>
<table><thead><tr><th>Unit</th><th>Alerts</th><th>First</th><th>Last</th></tr></thead><tbody>$attackRows</tbody></table>
<h2>Attack Pressure By 5-Minute Bucket</h2>
<table><thead><tr><th>Start</th><th>Pressure</th><th>Alerts</th></tr></thead><tbody>$bucketRows</tbody></table>
<h2>Recent Timeline</h2>
<table><thead><tr><th>Time</th><th>Frame</th><th>Kind</th><th>Event</th></tr></thead><tbody>$timelineRows</tbody></table>
</body>
</html>
"@

Set-Content -Encoding UTF8 -Path $htmlPath -Value $html
Set-Content -Encoding UTF8 -Path $latestHtmlPath -Value $html

Write-Host "Wrote analysis JSON: $jsonPath"
Write-Host "Wrote analysis HTML: $htmlPath"
Write-Host "Latest HTML: $latestHtmlPath"
Write-Host "Attack alerts: $(@($attacks).Count)"
Write-Host "Observed export marker: $($analysis.observedExport)"
