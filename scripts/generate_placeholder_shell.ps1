param(
  [string]$Workspace = "",
  [string]$MapId = "greenest_fields",
  [string]$OutName = ""
)

$ErrorActionPreference = "Stop"
. (Join-Path (Split-Path -Parent $MyInvocation.MyCommand.Path) "_common.ps1")
$Workspace = Get-VerdanceWorkspaceRoot -Workspace $Workspace

$recipePath = Join-Path $Workspace "data\base_templates\$MapId\bake_recipe.json"
if (!(Test-Path $recipePath)) { throw "Missing bake recipe: $recipePath" }
$recipe = Get-Content -Raw -LiteralPath $recipePath | ConvertFrom-Json
$dens = $recipe.placeholderDensity
if (-not $dens) { throw "bake_recipe missing placeholderDensity for $MapId" }

# Grow-profile multipliers (simulate SimpleAI sprawl vs BARb fortify strip results).
$growCatalog = @{}
$growCatalogPath = Join-Path $Workspace "data\base_templates\grow_profiles.json"
if (Test-Path $growCatalogPath) {
  $growDoc = Get-Content -Raw -LiteralPath $growCatalogPath | ConvertFrom-Json
  foreach ($prop in $growDoc.profiles.PSObject.Properties) {
    $growCatalog[$prop.Name] = $prop.Value
  }
}

function Get-GrowMul([string]$ProfileName) {
  $m = @{ eco = 1.0; def = 1.0; wall = 1.0; mex = 1.0; hlt = 1.0 }
  if (-not $ProfileName) { return $m }
  if (-not $growCatalog.ContainsKey($ProfileName)) { return $m }
  $pm = $growCatalog[$ProfileName].placeholderMul
  if (-not $pm) { return $m }
  if ($null -ne $pm.eco) { $m.eco = [double]$pm.eco }
  if ($null -ne $pm.def) { $m.def = [double]$pm.def }
  if ($null -ne $pm.wall) { $m.wall = [double]$pm.wall }
  if ($null -ne $pm.mex) { $m.mex = [double]$pm.mex }
  if ($null -ne $pm.hlt) { $m.hlt = [double]$pm.hlt }
  return $m
}

if (-not $OutName) {
  $tid = if ($recipe.templateId) { [string]$recipe.templateId } else { "living_placeholder_v1" }
  if ($tid -notmatch "placeholder") {
    # Keep Greenest's historic placeholder name so resolve prefers rate-tuned file.
    if ($MapId -eq "greenest_fields") { $tid = "armada_placeholder_v1" }
    else { $tid = "living_placeholder_v1" }
  }
  $OutName = "$tid.json"
}

$seed = if ($recipe.fixedRngSeed) { [int]$recipe.fixedRngSeed } else { 11 }
$rng = [System.Random]::new($seed)

# Unit kits by faction (static shell only).
$KITS = @{
  armada = @{
    solar = "armsolar"; wind = "armwin"; advsolar = "armadvsol"; conv = "armmakr"
    estor = "armestor"; mex = "armmex"; llt = "armllt"; hlt = "armbeamer"
    wall = "armdrag"; radar = "armrad"; fus = "armfus"; decoy = "armdecom"
  }
  cortex = @{
    solar = "corsolar"; wind = "corwin"; advsolar = "coradvsol"; conv = "cormakr"
    estor = "corestor"; mex = "cormex"; llt = "corllt"; hlt = "corhlt"
    wall = "cordrag"; radar = "corrad"; fus = "corfus"; decoy = "cordecom"
  }
  nullmercs = @{
    solar = "legsolar"; wind = "legwin"; advsolar = "legsolar"; conv = "legmex"
    estor = "legmstor"; mex = "legmex"; llt = "leglht"; hlt = "legmg"
    wall = "legdrag"; radar = "legrad"; fus = "legmex"; decoy = "legdecom"
  }
}

function RandOffset([double]$Radius) {
  $a = $rng.NextDouble() * 2.0 * [Math]::PI
  $r = $Radius * [Math]::Sqrt($rng.NextDouble())
  return @(([Math]::Cos($a) * $r), ([Math]::Sin($a) * $r))
}

function Clamp01([double]$V) {
  return [Math]::Max(0.02, [Math]::Min(0.98, $V))
}

function InClear($x, $z, $clears) {
  foreach ($clear in @($clears)) {
    if (-not $clear -or -not $clear.bounds) { continue }
    $b = $clear.bounds
    if ($x -ge [double]$b.xMin -and $x -le [double]$b.xMax -and $z -ge [double]$b.zMin -and $z -le [double]$b.zMax) {
      return $true
    }
  }
  return $false
}

function Scale-Count([double]$Base, [double]$Scale) {
  return [Math]::Max(0, [int][Math]::Round($Base * $Scale))
}

function Add-Units($list, [string]$Def, [int]$Count, [double]$Cx, [double]$Cz, [double]$Radius, [string]$ZoneId, [string]$PocketId, [string]$KeepClass, $clears, [string]$Faction) {
  if ($Count -le 0 -or -not $Def) { return }
  for ($i = 0; $i -lt $Count; $i++) {
    $off = RandOffset $Radius
    $x = Clamp01 ($Cx + $off[0])
    $z = Clamp01 ($Cz + $off[1])
    if (InClear $x $z $clears) {
      $x = Clamp01 ($Cx + $off[0] * 1.6)
      $z = Clamp01 ($Cz + $off[1] * 1.6)
      if (InClear $x $z $clears) { continue }
    }
    $list.Add([ordered]@{
      unitDefName = $Def
      x = [Math]::Round($x, 4)
      z = [Math]::Round($z, 4)
      facing = $rng.Next(0, 4)
      zoneId = $ZoneId
      pocketId = $PocketId
      keepClass = $KeepClass
      faction = $Faction
    }) | Out-Null
  }
}

function Resolve-Faction($start) {
  if ($start.PSObject.Properties["faction"] -and $start.faction) {
    $f = ([string]$start.faction).ToLowerInvariant()
    if ($KITS.ContainsKey($f)) { return $f }
  }
  if ($recipe.PSObject.Properties["faction"] -and $recipe.faction) {
    $f = ([string]$recipe.faction).ToLowerInvariant()
    if ($KITS.ContainsKey($f)) { return $f }
  }
  return "armada"
}

$units = New-Object System.Collections.Generic.List[object]
$pockets = @()
$radius = if ($dens.scatterRadius) { [double]$dens.scatterRadius } else { 0.055 }
$clears = @()
if ($recipe.playerClear) { $clears += $recipe.playerClear }
if ($recipe.PSObject.Properties["playerClearExtra"] -and $recipe.playerClearExtra) {
  foreach ($extra in @($recipe.playerClearExtra)) { $clears += $extra }
}

foreach ($start in @($recipe.starts)) {
  $cx = [double]$start.x
  $cz = [double]$start.z
  $pocketKey = [string]$start.pocketId
  $zid = [string]$start.zoneId
  $kind = if ($start.kind) { [string]$start.kind } else { "mixed" }
  $faction = Resolve-Faction $start
  $kit = $KITS[$faction]
  $scale = 1.0
  if ($start.PSObject.Properties["densityScale"] -and $null -ne $start.densityScale) {
    $scale = [double]$start.densityScale
  }
  $growProfile = "hold"
  if ($start.PSObject.Properties["growProfile"] -and $start.growProfile) {
    $growProfile = [string]$start.growProfile
  } elseif ($recipe.PSObject.Properties["aiShortName"] -and [string]$recipe.aiShortName -eq "SimpleAI") {
    $growProfile = "sprawl"
  }
  $gmul = Get-GrowMul $growProfile
  $before = $units.Count

  # Kind multipliers (character, not new lore) x grow-profile (BARb vs SimpleAI rate).
  $defMul = 1.0; $ecoMul = 1.0; $mexMul = 1.0; $wallMul = 1.0; $hltMul = 1.0
  switch ($kind) {
    "citadel"  { $defMul = 1.6; $ecoMul = 0.9; $wallMul = 1.3; $hltMul = 1.4 }
    "fortress" { $defMul = 1.35; $ecoMul = 1.1; $wallMul = 1.2; $hltMul = 1.25 }
    "gate"     { $defMul = 1.4; $ecoMul = 0.7; $wallMul = 1.25; $hltMul = 1.2 }
    "fusion_fort" { $defMul = 1.8; $ecoMul = 0.15; $wallMul = 1.4; $hltMul = 2.2 }
    "rim"      { $defMul = 1.15; $ecoMul = 0.65 }
    "lane"     { $defMul = 1.2; $ecoMul = 0.75; $mexMul = 1.1; $wallMul = 1.15 }
    "scrap"    { $defMul = 0.9; $ecoMul = 0.55; $mexMul = 0.7 }
    "thin"     { $defMul = 0.6; $ecoMul = 0.4; $mexMul = 0.4 }
    "wind"     { $ecoMul = 1.0 }
    "solar"    { $ecoMul = 1.0 }
    default    { }
  }
  $ecoMul *= [double]$gmul.eco
  $defMul *= [double]$gmul.def
  $wallMul *= [double]$gmul.wall
  $mexMul *= [double]$gmul.mex
  $hltMul *= [double]$gmul.hlt

  # Tight center forts use a smaller scatter so teeth sit on the choke.
  $pocketRadius = $radius
  if ($kind -eq "fusion_fort") { $pocketRadius = [Math]::Min($radius, 0.028) }

  $solarN = Scale-Count ([double]$dens.solarPerPocket) ($scale * $ecoMul)
  $windN = Scale-Count ([double]$dens.windPerPocket) ($scale * $ecoMul)
  if ($kind -eq "wind") { $windN = Scale-Count $windN 1.35; $solarN = Scale-Count $solarN 0.65 }
  if ($kind -eq "solar") { $solarN = Scale-Count $solarN 1.35; $windN = Scale-Count $windN 0.65 }
  if ($kind -eq "fusion_fort") { $solarN = 0; $windN = 0 }
  $convN = Scale-Count ([double]$(if ($null -ne $dens.converterPerPocket) { $dens.converterPerPocket } else { 0 })) ($scale * $ecoMul)
  $advN = Scale-Count ([double]$(if ($null -ne $dens.advSolarPerPocket) { $dens.advSolarPerPocket } else { 0 })) ($scale * $ecoMul)
  $estorN = Scale-Count ([double]$(if ($null -ne $dens.estorPerPocket) { $dens.estorPerPocket } else { 0 })) $scale
  $mexN = Scale-Count ([double]$(if ($null -ne $dens.mexPerPocket) { $dens.mexPerPocket } else { 0 })) ($scale * $mexMul)
  $lltN = Scale-Count ([double]$dens.lltPerPocket) ($scale * $defMul)
  $hltN = Scale-Count ([double]$(if ($null -ne $dens.hltPerPocket) { $dens.hltPerPocket } else { 0 })) ($scale * $defMul * $hltMul)
  $wallN = Scale-Count ([double]$(if ($null -ne $dens.wallPerPocket) { $dens.wallPerPocket } else { 0 })) ($scale * $defMul * $wallMul)
  $radN = Scale-Count ([double]$(if ($null -ne $dens.radarPerPocket) { $dens.radarPerPocket } else { 0 })) $scale
  if ($kind -eq "fusion_fort") {
    # Beamer ring around one fusion — high value, optional, heavily defended.
    $convN = 0; $advN = 0; $estorN = 0; $mexN = 0
    $lltN = 2
    $hltN = 6
    $wallN = 10
    $radN = 1
  }

  Add-Units $units $kit.solar $solarN $cx $cz $pocketRadius $zid $pocketKey "energy" $clears $faction
  Add-Units $units $kit.wind $windN $cx $cz $pocketRadius $zid $pocketKey "energy" $clears $faction
  if ($convN -gt 0 -and $kit.conv -and $kit.conv -ne $kit.mex) {
    Add-Units $units $kit.conv $convN $cx $cz ($pocketRadius * 0.7) $zid $pocketKey "converter" $clears $faction
  }
  Add-Units $units $kit.advsolar $advN $cx $cz ($pocketRadius * 0.5) $zid $pocketKey "energy" $clears $faction
  Add-Units $units $kit.estor $estorN $cx $cz ($pocketRadius * 0.4) $zid $pocketKey "storage" $clears $faction
  Add-Units $units $kit.mex $mexN $cx $cz ($pocketRadius * 0.85) $zid $pocketKey "mex" $clears $faction
  Add-Units $units $kit.llt $lltN $cx $cz ($pocketRadius * 1.1) $zid $pocketKey "defense" $clears $faction
  Add-Units $units $kit.hlt $hltN $cx $cz ($pocketRadius * 0.85) $zid $pocketKey "defense" $clears $faction
  Add-Units $units $kit.wall $wallN $cx $cz ($pocketRadius * 1.15) $zid $pocketKey "wall" $clears $faction
  Add-Units $units $kit.radar $radN $cx $cz ($pocketRadius * 0.3) $zid $pocketKey "intel" $clears $faction
  if ($kind -eq "citadel" -or $kind -eq "fortress") {
    Add-Units $units $kit.fus 1 $cx $cz ($pocketRadius * 0.25) $zid $pocketKey "energy" $clears $faction
  }
  if ($kind -eq "fusion_fort") {
    # Fusion is the optional high-value mark; beamers are teeth, not the mark.
    Add-Units $units $kit.fus 1 $cx $cz ($pocketRadius * 0.12) $zid $pocketKey "high_value" $clears $faction
  }
  # Autonomous decoy commander nodes (occupation flavor). Sims still use real coms.
  # Skip decoys on optional fusion forts — the fusion itself is the mark.
  $wantDecoy = $true
  if ($recipe.occupation -and $null -ne $recipe.occupation.decoyCommanders) {
    $wantDecoy = [bool]$recipe.occupation.decoyCommanders
  }
  if ($kind -eq "fusion_fort" -or $kind -eq "thin") { $wantDecoy = $false }
  if ($wantDecoy -and $kit.decoy) {
    Add-Units $units $kit.decoy 1 $cx $cz ($pocketRadius * 0.15) $zid $pocketKey "decoy_node" $clears $faction
  }

  $aiShort = "SimpleAI"
  $barbProf = $null
  if ($growCatalog.ContainsKey($growProfile)) {
    $gp = $growCatalog[$growProfile]
    if ($gp.aiShortName) { $aiShort = [string]$gp.aiShortName }
    if ($gp.barbProfile) { $barbProf = [string]$gp.barbProfile }
  }

  $pocketMeta = [ordered]@{
    pocketId = $pocketKey
    zoneId = $zid
    label = [string]$start.label
    kind = $kind
    faction = $faction
    growProfile = $growProfile
    growAI = $aiShort
    barbProfile = $barbProf
    center = @([Math]::Round($cx, 4), [Math]::Round($cz, 4))
    unitCount = ($units.Count - $before)
    primaryCandidate = [bool]$start.primaryCandidate
    densityScale = $scale
  }
  if ($start.PSObject.Properties["optionalTarget"] -and $start.optionalTarget) {
    $pocketMeta.optionalTarget = $true
  }
  if ($start.PSObject.Properties["highValue"] -and $start.highValue) {
    $pocketMeta.highValue = $true
  }
  if ($kind -eq "fusion_fort") {
    $pocketMeta.optionalTarget = $true
    $pocketMeta.highValue = $true
  }
  $pockets += $pocketMeta
}

$factionName = if ($recipe.PSObject.Properties["faction"] -and $recipe.faction) { [string]$recipe.faction } else { "mixed" }
$profileSummary = @($pockets | ForEach-Object { "$($_.pocketId)=$($_.growProfile)" }) -join "; "
$card = $null
if ($recipe.PSObject.Properties["characterCard"] -and $recipe.characterCard) {
  $card = $recipe.characterCard
}
$template = [ordered]@{
  schemaVersion = "verdance-living-shell/1.1"
  mapId = $MapId
  templateId = [IO.Path]::GetFileNameWithoutExtension($OutName)
  source = "placeholder"
  faction = $factionName
  character = if ($recipe.character) { [string]$recipe.character } else { "" }
  characterCard = if ($card) { $card } else { $null }
  # Force array (PowerShell ConvertTo-Json flattens single-element @() without this).
  arcKinds = [string[]]@(if ($recipe.PSObject.Properties["arcKinds"] -and $recipe.arcKinds) { @($recipe.arcKinds) } else { @() })
  raidHint = if ($recipe.PSObject.Properties["raidHint"] -and $recipe.raidHint) { [string]$recipe.raidHint } else { "" }
  captureLater = if ($recipe.PSObject.Properties["captureLater"] -and $recipe.captureLater) { [string]$recipe.captureLater } else { "" }
  occupation = [ordered]@{
    decoyCommanders = $true
    notes = "Decoy com nodes (armdecom/cordecom/legdecom) stand in for Armada autonomous eco farmers. Sims use real commanders."
  }
  bake = [ordered]@{
    growMinutes = [int]$recipe.growMinutes
    teams = [int]$recipe.teamCount
    seed = $seed
    peacefulCoGrow = [bool]$(if ($null -ne $recipe.peacefulCoGrow) { $recipe.peacefulCoGrow } else { $true })
    growProfiles = $profileSummary
    simCommanders = "normal"
    occupationCommanders = "decoy"
    note = "Placeholder density with BARb/SimpleAI rate character + decoy swarm nodes. Replace by bake_living_shell.ps1 for real grow."
  }
  generatedAt = (Get-Date).ToString("s")
  unitCount = [int]$units.Count
  pockets = @($pockets)
  units = @($units.ToArray())
}
# Drop null characterCard so JSON stays clean when recipe has no card yet.
if ($null -eq $template.characterCard) {
  $template.Remove("characterCard")
}

$outDir = Join-Path $Workspace "data\base_templates\$MapId"
New-Item -ItemType Directory -Force -Path $outDir | Out-Null
$outPath = Join-Path $outDir $OutName
($template | ConvertTo-Json -Depth 8) | Set-Content -Encoding UTF8 -LiteralPath $outPath
Write-Host "Wrote placeholder shell: $outPath ($($units.Count) units, $($pockets.Count) pockets) map=$MapId"
return $outPath
