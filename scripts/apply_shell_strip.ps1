param(
  [string]$Workspace = "",
  [Parameter(Mandatory = $true)][string]$RawDumpPath,
  [string]$MapId = "greenest_fields",
  [string]$TemplateId = "armada_t15_v1",
  [string]$RecipePath = "",
  [string]$FilterPath = "",
  [string]$OutPath = ""
)

$ErrorActionPreference = "Stop"
. (Join-Path (Split-Path -Parent $MyInvocation.MyCommand.Path) "_common.ps1")
$Workspace = Get-VerdanceWorkspaceRoot -Workspace $Workspace

if (!(Test-Path $RawDumpPath)) { throw "Raw dump not found: $RawDumpPath" }
if (-not $FilterPath) {
  $FilterPath = Join-Path $Workspace "data\base_templates\strip_filter.json"
}
if (!(Test-Path $FilterPath)) { throw "Missing strip filter: $FilterPath" }
$filter = Get-Content -Raw -LiteralPath $FilterPath | ConvertFrom-Json

if (-not $RecipePath) {
  $RecipePath = Join-Path $Workspace "data\base_templates\$MapId\bake_recipe.json"
}
$recipe = $null
if (Test-Path $RecipePath) {
  $recipe = Get-Content -Raw -LiteralPath $RecipePath | ConvertFrom-Json
}

$keepExact = @{}
foreach ($k in @($filter.keepExact)) { $keepExact[[string]$k] = $true }
$stripExact = @{}
foreach ($k in @($filter.stripExact)) { $stripExact[[string]$k] = $true }
$keepPrefixes = @($filter.keepPrefixes | ForEach-Object { [string]$_ })
$stripPrefixes = @($filter.stripPrefixes | ForEach-Object { [string]$_ })

function Test-KeepDef([string]$Def) {
  if (-not $Def) { return $false }
  $d = $Def.ToLowerInvariant()
  if ($stripExact.ContainsKey($d) -or $stripExact.ContainsKey($Def)) { return $false }
  foreach ($p in $stripPrefixes) {
    if ($d.StartsWith($p.ToLowerInvariant())) { return $false }
  }
  if ($keepExact.ContainsKey($d) -or $keepExact.ContainsKey($Def)) { return $true }
  foreach ($p in $keepPrefixes) {
    if ($d.StartsWith($p.ToLowerInvariant())) { return $true }
  }
  # Unknown: strip (safer for living shells).
  return $false
}

function Find-KeepClass([string]$Def) {
  if (-not $filter.keepClasses) { return "static" }
  foreach ($prop in $filter.keepClasses.PSObject.Properties) {
    foreach ($name in @($prop.Value)) {
      if ([string]$name -eq $Def) { return [string]$prop.Name }
    }
  }
  return "static"
}

function NearestPocket($x, $z, $starts) {
  $best = $null
  $bestD = 1e9
  foreach ($s in @($starts)) {
    $dx = [double]$s.x - $x
    $dz = [double]$s.z - $z
    $d = $dx * $dx + $dz * $dz
    if ($d -lt $bestD) { $bestD = $d; $best = $s }
  }
  return $best
}

# Accept either JSON array dump or line-based VA_SHELL_UNIT logs.
$rawText = Get-Content -Raw -LiteralPath $RawDumpPath
$rawUnits = @()
if ($rawText.TrimStart().StartsWith("{") -or $rawText.TrimStart().StartsWith("[")) {
  $parsed = $rawText | ConvertFrom-Json
  if ($parsed.units) { $rawUnits = @($parsed.units) }
  elseif ($parsed -is [System.Array]) { $rawUnits = @($parsed) }
  else { $rawUnits = @($parsed) }
} else {
  foreach ($line in ($rawText -split "`r?`n")) {
    if ($line -match 'VA_SHELL_UNIT\s+(\S+)\s+([\d\.\-]+)\s+([\d\.\-]+)\s+(\d+)') {
      $rawUnits += [pscustomobject]@{
        unitDefName = $Matches[1]
        x = [double]$Matches[2]
        z = [double]$Matches[3]
        facing = [int]$Matches[4]
      }
    }
  }
}

$kept = New-Object System.Collections.Generic.List[object]
$stripCount = 0
foreach ($u in $rawUnits) {
  $def = if ($u.unitDefName) { [string]$u.unitDefName } elseif ($u.def) { [string]$u.def } else { "" }
  if (-not (Test-KeepDef $def)) { $stripCount += 1; continue }
  $x = [double]$(if ($null -ne $u.x) { $u.x } else { 0.5 })
  $z = [double]$(if ($null -ne $u.z) { $u.z } else { 0.5 })
  # Normalize if dump was in elmos ( > 1.5 ).
  if ($x -gt 1.5 -or $z -gt 1.5) {
    $sx = if ($u.mapSizeX) { [double]$u.mapSizeX } else { 8192 }
    $sz = if ($u.mapSizeZ) { [double]$u.mapSizeZ } else { 8192 }
    if ($sx -le 0) { $sx = 8192 }
    if ($sz -le 0) { $sz = 8192 }
    $x = $x / $sx
    $z = $z / $sz
  }
  $pocket = $null
  if ($recipe -and $recipe.starts) { $pocket = NearestPocket $x $z $recipe.starts }
  $kept.Add(@{
    unitDefName = $def
    x = [Math]::Round($x, 4)
    z = [Math]::Round($z, 4)
    facing = if ($null -ne $u.facing) { [int]$u.facing } else { 0 }
    zoneId = if ($pocket) { [string]$pocket.zoneId } else { "" }
    pocketId = if ($pocket) { [string]$pocket.pocketId } else { "" }
    keepClass = (Find-KeepClass $def)
  }) | Out-Null
}

# --- Decoy commander swarm nodes (occupation flavor) ---
# Sims grow with REAL commanders (AI needs them). Strip removes armcom/corcom/legcom.
# Then plant armdecom/cordecom/legdecom as Armada autonomous eco-farm nodes:
# weaker, cheaper metal, no real com explosion — good for military metal counting.
function Resolve-DecoyDef([string]$Faction) {
  $f = ($Faction).ToLowerInvariant()
  $defs = $null
  if ($filter.decoyCommanders -and $filter.decoyCommanders.defs) { $defs = $filter.decoyCommanders.defs }
  if ($defs) {
    if ($defs.PSObject.Properties[$f]) { return [string]$defs.$f }
    if ($f -eq "mixed" -and $defs.PSObject.Properties["armada"]) { return [string]$defs.armada }
  }
  switch ($f) {
    "cortex" { return "cordecom" }
    "nullmercs" { return "legdecom" }
    "legion" { return "legdecom" }
    default { return "armdecom" }
  }
}

$decoyPolicy = $filter.decoyCommanders
$wantDecoys = $true
if ($decoyPolicy -and $null -ne $decoyPolicy.enabledByDefault) {
  $wantDecoys = [bool]$decoyPolicy.enabledByDefault
}
if ($recipe -and $recipe.occupation -and $null -ne $recipe.occupation.decoyCommanders) {
  $wantDecoys = [bool]$recipe.occupation.decoyCommanders
}
$decoyPerPocket = 1
if ($decoyPolicy -and $decoyPolicy.perPocket) { $decoyPerPocket = [int]$decoyPolicy.perPocket }
if ($recipe -and $recipe.occupation -and $recipe.occupation.decoyPerPocket) {
  $decoyPerPocket = [int]$recipe.occupation.decoyPerPocket
}
$skipKinds = @("thin")
if ($decoyPolicy -and $decoyPolicy.skipKinds) { $skipKinds = @($decoyPolicy.skipKinds | ForEach-Object { [string]$_ }) }

$decoyPlanted = 0
if ($wantDecoys -and $recipe -and $recipe.starts -and $decoyPerPocket -gt 0) {
  # Don't double-plant if dump already kept a decoy in that pocket.
  $existingDecoyPockets = @{}
  foreach ($u in $kept) {
    $d = ([string]$u.unitDefName).ToLowerInvariant()
    if ($d -match 'decom$' -or $d -eq "armdecom" -or $d -eq "cordecom" -or $d -eq "legdecom") {
      if ($u.pocketId) { $existingDecoyPockets[[string]$u.pocketId] = $true }
    }
  }
  foreach ($s in @($recipe.starts)) {
    $kind = if ($s.kind) { [string]$s.kind } else { "mixed" }
    if ($skipKinds -contains $kind) { continue }
    $pocketKey = [string]$s.pocketId
    if ($existingDecoyPockets.ContainsKey($pocketKey)) { continue }
    $faction = "armada"
    if ($s.faction) { $faction = [string]$s.faction }
    elseif ($recipe.faction) { $faction = [string]$recipe.faction }
    $def = Resolve-DecoyDef $faction
    $cx = [double]$s.x
    $cz = [double]$s.z
    for ($di = 0; $di -lt $decoyPerPocket; $di++) {
      $ox = 0.0; $oz = 0.0
      if ($di -gt 0) {
        $ox = 0.012 * [Math]::Cos($di * 2.2)
        $oz = 0.012 * [Math]::Sin($di * 2.2)
      }
      $kept.Add(@{
        unitDefName = $def
        x = [Math]::Round([Math]::Max(0.02, [Math]::Min(0.98, $cx + $ox)), 4)
        z = [Math]::Round([Math]::Max(0.02, [Math]::Min(0.98, $cz + $oz)), 4)
        facing = $di % 4
        zoneId = [string]$s.zoneId
        pocketId = $pocketKey
        keepClass = "decoy_node"
        role = "autonomous_decoy_farmer"
      }) | Out-Null
      $decoyPlanted += 1
    }
  }
  Write-Host "Planted $decoyPlanted decoy commander node(s) (occupation swarm; sims used real coms)."
}

$pocketCounts = @{}
foreach ($u in $kept) {
  $pocketKey = "unknown"
  if ($u.ContainsKey("pocketId") -and $u["pocketId"]) { $pocketKey = [string]$u["pocketId"] }
  if (-not $pocketCounts.ContainsKey($pocketKey)) { $pocketCounts[$pocketKey] = 0 }
  $pocketCounts[$pocketKey] = [int]$pocketCounts[$pocketKey] + 1
}

$pockets = New-Object System.Collections.Generic.List[object]
if ($recipe -and $recipe.starts) {
  foreach ($s in @($recipe.starts)) {
    $pocketKey = [string]$s.pocketId
    $isPrimary = $false
    if ($s.PSObject.Properties["primaryCandidate"] -and $s.primaryCandidate) {
      $isPrimary = [bool]$s.primaryCandidate
    }
    $pockets.Add(@{
      pocketId = $pocketKey
      zoneId = [string]$s.zoneId
      label = [string]$s.label
      kind = [string]$s.kind
      center = @([double]$s.x, [double]$s.z)
      unitCount = if ($pocketCounts.ContainsKey($pocketKey)) { [int]$pocketCounts[$pocketKey] } else { 0 }
      primaryCandidate = $isPrimary
    }) | Out-Null
  }
}

$unitsOut = @($kept.ToArray())

$template = [pscustomobject]@{
  schemaVersion = "verdance-living-shell/1.1"
  mapId = $MapId
  templateId = $TemplateId
  source = "bake"
  faction = if ($recipe -and $recipe.faction) { [string]$recipe.faction } else { "armada" }
  occupation = [pscustomobject]@{
    decoyCommanders = [bool]$wantDecoys
    decoyPlanted = [int]$decoyPlanted
    notes = "Real commanders stripped after sim; decoy coms planted as autonomous eco-farm swarm (less metal, less danger)."
  }
  bake = [pscustomobject]@{
    growMinutes = if ($recipe) { [int]$recipe.growMinutes } else { 15 }
    teams = if ($recipe) { [int]$recipe.teamCount } else { 8 }
    seed = if ($recipe) { [int]$recipe.fixedRngSeed } else { 11 }
    rawDumpPath = [string]$RawDumpPath
    stripped = [int]$stripCount
    kept = [int]$kept.Count
    simCommanders = "normal"
    occupationCommanders = "decoy"
  }
  generatedAt = (Get-Date).ToString("s")
  unitCount = [int]$kept.Count
  pockets = @($pockets.ToArray())
  units = $unitsOut
}

if (-not $OutPath) {
  $OutPath = Join-Path $Workspace "data\base_templates\$MapId\$TemplateId.json"
}
New-Item -ItemType Directory -Force -Path (Split-Path -Parent $OutPath) | Out-Null
try {
  $json = $template | ConvertTo-Json -Depth 8
} catch {
  throw "ConvertTo-Json failed: $($_.Exception.Message) (kept=$($kept.Count) decoys=$decoyPlanted)"
}
Set-Content -Encoding UTF8 -LiteralPath $OutPath -Value $json
Write-Host "Stripped shell: kept=$($kept.Count) stripped=$stripCount decoys=$decoyPlanted -> $OutPath"
return $OutPath
