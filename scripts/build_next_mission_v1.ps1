param(
  [string]$Workspace = "",
  [string]$IntentPath = "",
  [string]$StatePath = "",
  [switch]$Launch,
  [switch]$SaveGame,
  [string]$SaveName = "",
  [int]$TimeoutSeconds = 300
)

$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
. (Join-Path $ScriptDir "_common.ps1")
$Workspace = Get-VerdanceWorkspaceRoot -Workspace $Workspace

function Add-OrSetProperty {
  param($Object, [string]$Name, $Value)
  if ($Object.PSObject.Properties[$Name]) {
    $Object.$Name = $Value
  } else {
    $Object | Add-Member -NotePropertyName $Name -NotePropertyValue $Value
  }
}

function Get-ZoneById {
  param($ZoneMap, [string]$ZoneId)
  if (-not $ZoneMap -or -not $ZoneMap.zones -or -not $ZoneId) { return $null }
  return @($ZoneMap.zones) | Where-Object { $_.zoneId -eq $ZoneId } | Select-Object -First 1
}

function Get-ZoneCenter {
  param($Zone, [double[]]$Fallback)
  if (-not $Zone) { return $Fallback }
  # Schema 2.0 zones carry a MEASURED anchor: buildable, dry, flat ground.
  # A rect centre is a guess that can land in water or on a cliff face, which
  # is how camps ended up spawning where nothing can be built.
  if ($Zone.PSObject.Properties["anchor"] -and $Zone.anchor -and
      $null -ne $Zone.anchor.x -and $null -ne $Zone.anchor.z) {
    return @(
      [Math]::Max(0.02, [Math]::Min(0.98, [double]$Zone.anchor.x)),
      [Math]::Max(0.02, [Math]::Min(0.98, [double]$Zone.anchor.z))
    )
  }
  if (-not $Zone.bounds) { return $Fallback }
  $b = $Zone.bounds
  return @(
    [Math]::Max(0.02, [Math]::Min(0.98, (([double]$b.xMin + [double]$b.xMax) / 2.0))),
    [Math]::Max(0.02, [Math]::Min(0.98, (([double]$b.zMin + [double]$b.zMax) / 2.0)))
  )
}

function New-StartRect {
  param([double[]]$Center, [double]$Radius = 0.22)
  $x = [double]$Center[0]
  $z = [double]$Center[1]
  return @(
    [Math]::Max(0.0, $x - $Radius),
    [Math]::Max(0.0, $z - $Radius),
    [Math]::Min(1.0, $x + $Radius),
    [Math]::Min(1.0, $z + $Radius)
  )
}

function Get-MapEntry {
  param($Pool, [string]$MapId)
  return @($Pool.maps) | Where-Object { $_.id -eq $MapId } | Select-Object -First 1
}

function Get-EnemySide {
  param([string]$MapId, $Intent)
  # Faction comes from the CRAFTED world (data/map_pool/seven_maps.json), not a
  # guess off the zone name. The standing war is Null Mercs vs Armada; Cortex is
  # an accent that holds only its own authored maps. A camp is one faction.
  # 1) Honor the objective's explicit faction when the engine set one.
  if ($Intent.objectiveTarget -and $Intent.objectiveTarget.enemyFaction) {
    switch ([string]$Intent.objectiveTarget.enemyFaction) {
      "cortex" { return "Cortex" }
      "armada" { return "Armada" }
    }
  }
  # 2) Derive from the authored campaignForces: Cortex only where it alone holds
  #    economy; Armada wherever it has authored forces.
  if ($Intent.enemyInfrastructure -and $Intent.enemyInfrastructure.campaignForces) {
    $cf = $Intent.enemyInfrastructure.campaignForces
    $arm = if ($cf.PSObject.Properties["ARM"]) { [string]$cf.ARM } else { "" }
    $cor = if ($cf.PSObject.Properties["COR"]) { [string]$cf.COR } else { "" }
    if ($cor.Trim() -and -not $arm.Trim()) { return "Cortex" }
    if ($arm.Trim()) { return "Armada" }
  }
  # 3) Fallbacks for maps without crafted forces.
  if ($MapId -eq "eye_of_horus") { return "Cortex" }
  return "Armada"
}

function Get-EnemyRecipeName {
  param([string]$Side)
  if ($Side -eq "Cortex") { return "cortex_sortie_target" }
  return "armada_sortie_target"
}

function Get-EnemyRgb {
  param([string]$Side)
  if ($Side -eq "Cortex") { return @(1.0, 0.20, 0.16) }
  return @(0.25, 0.48, 1.0)
}

function Get-ObjectiveDescription {
  param($Intent)
  $target = $Intent.objectiveTarget
  if ($target -and $target.label) { return [string]$target.label }
  if ($Intent.storyReason) { return [string]$Intent.storyReason }
  return "Complete the local Verdance sortie objective, then extract."
}

function Get-RequiredFrames {
  param($Intent)
  # Drop 2 finale: a full unconstrained game of BAR gets a ~40 minute clock.
  if ($Intent.PSObject.Properties["finale"] -and $Intent.finale) { return 72000 }
  # WO-004: contracts target ~10 minutes (18000 frames @ 30fps), not 20.
  $td = if ($Intent.environment -and $Intent.environment.targetDuration) { [string]$Intent.environment.targetDuration } else { "" }
  # Soft clocks are REAL mission ends (gadget checkSoftClock). Keep them tight.
  $ok = if ($Intent.objectiveTarget -and $Intent.objectiveTarget.kind) { [string]$Intent.objectiveTarget.kind } else { [string]$Intent.objective }
  $missionNum = if ($Intent.missionNumber) { [int]$Intent.missionNumber } else { 1 }
  # Arc A raids: ~7.5 min walk-up + blow eco + extract. Not 11 min of "chilling".
  if ($ok -eq "eco_raid" -or $missionNum -le 3) { return 13500 }
  if ($td -match '10\s*min' -or $td -eq "10min") { return 18000 }  # ~10 min soft clock
  # Contract missions (any with contractActive or targetDuration) stay front-band.
  if ($Intent.PSObject.Properties["contractActive"] -and $Intent.contractActive) { return 19800 }
  $family = if ($Intent.environment -and $Intent.environment.mapFamily) { [string]$Intent.environment.mapFamily } else { "tempo" }
  switch ($family) {
    "siege" { return 27000 }
    "wild" { return 24000 }
    "economy" { return 21600 }
    default { return 19800 }
  }
}

function Get-ArcProfile {
  # WO-030: single knob table for Arc A/B/C fantasy. Compiler + gadget honor this.
  param([int]$MissionNumber, [string]$ObjectiveKind)
  $n = [Math]::Max(1, $MissionNumber)
  $id = if ($n -le 3) { "raid_tactics" } elseif ($n -le 6) { "contested_front" } else { "strike_lead" }
  # Tactics objectives stay commander-free even mid-campaign (seize/raid/strike).
  $tacticsKinds = @("seize_lane", "eco_raid", "economy_disrupt", "strike_relay", "gate_control", "destroy_key_structure")
  $isTactics = $tacticsKinds -contains $ObjectiveKind
  $playerCommanders = if ($id -eq "raid_tactics" -or $isTactics) { 0 } elseif ($id -eq "contested_front") { 0 } else { 1 }
  $allyPower = if ($n -le 1) { 0.95 } elseif ($n -eq 2) { 0.55 } elseif ($n -eq 3) { 0.35 } elseif ($n -le 5) { 0.25 } else { 0.15 }
  $escalation = if ($id -eq "raid_tactics") { "off" } elseif ($id -eq "contested_front") { "light" } else { "full" }
  $enemyMode = if ($id -eq "raid_tactics") { "static_bases" } elseif ($id -eq "contested_front") { "static_bases" } else { "light_qrf" }
  $printer = if ($playerCommanders -le 0) {
    # Arc A prints Phobos (legcen), not Ballistas. Goblins only if we need cheap filler later.
    [ordered]@{ def = "leglab"; product = "legcen"; count = 1; metalIncome = 10; energyIncome = 50 }
  } else { $null }
  return [ordered]@{
    id = $id
    playerCommanders = $playerCommanders
    playerEco = ($playerCommanders -gt 0)
    unitPrinter = $printer
    enemyMode = $enemyMode
    enemyAI = "simple"   # WO-036: "simple" | "barbarian" (hard)
    allyPower = [Math]::Round($allyPower, 2)
    escalation = $escalation
    objectiveAdjacency = if ($id -eq "raid_tactics") { "required" } else { "preferred" }
    sweepEnemyCommanders = ($enemyMode -eq "static_bases")
    allowEnemyProduction = ($id -eq "strike_lead")
    flavor = $null       # WO-037: "com_solar_farm" for GF sandbox
  }
}

function Add-CommerceDeployToKit {
  # WO-043: broker deployables — loan packs (damaged Thugs), Crash of Brutes,
  # Cortex grunt fab printer, faction constructors, fab nanos.
  param($Kit, $Commerce)
  $kit = @($Kit)
  if (-not $Commerce -or -not $Commerce.PSObject.Properties["deploy"]) { return $kit }
  $deploy = @($Commerce.deploy)
  if ($deploy.Count -eq 0) { return $kit }
  $i = 0
  foreach ($d in $deploy) {
    if (-not $d) { continue }
    $kind = if ($d.kind) { [string]$d.kind } else { "package" }
    $ox = -200 + (55 * ($i % 5))
    $oz = -280 - (40 * [Math]::Floor($i / 5))
    if ($kind -eq "unit_printer") {
      $fac = if ($d.factoryDef) { [string]$d.factoryDef } else { "corlab" }
      $product = if ($d.product) { [string]$d.product } else { "corak" }
      $printer = Spec $fac 1 ($ox - 40) ($oz + 20) 100
      $printer.unitPrinter = $true
      $printer.printerProduct = $product
      $printer.printerMetalIncome = if ($null -ne $d.metalIncome) { [double]$d.metalIncome } else { 8 }
      $printer.printerEnergyIncome = if ($null -ne $d.energyIncome) { [double]$d.energyIncome } else { 40 }
      if ($d.listingId) { $printer.packageTag = [string]$d.listingId }
      $kit += $printer
      $seed = if ($null -ne $d.seedCount) { [Math]::Max(0, [int]$d.seedCount) } else { 4 }
      if ($seed -gt 0) {
        $seedSpec = Spec $product $seed ($ox + 80) $oz 70
        if ($d.listingId) { $seedSpec.packageTag = [string]$d.listingId }
        $kit += $seedSpec
      }
    } elseif ($kind -eq "nano") {
      $ndef = if ($d.unitDef) { [string]$d.unitDef } else { "cornanotc" }
      $nc = if ($null -ne $d.count) { [Math]::Max(1, [int]$d.count) } else { 1 }
      $kit += (Spec $ndef $nc ($ox - 80) ($oz + 40) 90)
    } elseif ($kind -eq "constructor") {
      $cdef = if ($d.unitDef) { [string]$d.unitDef } else { "armck" }
      $cc = if ($null -ne $d.count) { [Math]::Max(1, [int]$d.count) } else { 1 }
      $cSpec = Spec $cdef $cc $ox ($oz + 60) 90
      if ($d.listingId) { $cSpec.packageTag = [string]$d.listingId }
      $kit += $cSpec
    } else {
      # package / loan pack
      $udef = if ($d.unitDef) { [string]$d.unitDef } else { $null }
      $cnt = if ($null -ne $d.count) { [Math]::Max(1, [int]$d.count) } else { 1 }
      if (-not $udef) { continue }
      $pSpec = Spec $udef $cnt $ox $oz 85
      if ($null -ne $d.healthFrac) { $pSpec.healthFrac = [double]$d.healthFrac }
      if ($null -ne $d.healthFracMin) { $pSpec.healthFracMin = [double]$d.healthFracMin }
      if ($null -ne $d.healthFracMax) { $pSpec.healthFracMax = [double]$d.healthFracMax }
      if ($d.loan -eq $true -or $d.loan -eq 1) { $pSpec.loanPackage = $true }
      if ($d.packageTag) { $pSpec.packageTag = [string]$d.packageTag }
      elseif ($d.listingId) { $pSpec.packageTag = [string]$d.listingId }
      $kit += $pSpec
    }
    $i += 1
  }
  return $kit
}

function New-TacticsPlayerKit {
  # Arc A/B ground-tactics kit: NO commander. Same doctrine as strike team:
  # Wheelies + Phobos army + rez bots. No Ballistas (missile bots). Vane = Karkinos.
  param([string]$Family, $Roster, [double]$ResourceMod = 1.0, $UnitPrinter = $null, $Commerce = $null)
  $kit = @(
    (Spec "legrad" 1 40 -60 100),
    (Spec "leglht" 2 -120 -120 130),
    (Spec "legscout" 4 -60 130 90),
    (Spec "legcen" 10 80 -210 85),
    (Spec "legkark" 1 140 -180 100),
    (Spec "legrezbot" 5 -170 60 80)
  )
  # Thin metal trickle so rez bots can work; not a full expand base.
  $kit += @(
    (Spec "legmex" 1 -140 120 120 $true),
    (Spec "legwin" 2 120 160 90)
  )
  # WO-033: unit printer - lab locked to Phobos (gadget enforces).
  # Skip default legion printer when commerce already fields a bought Cortex grunt fab.
  $hasCommercePrinter = $false
  if ($Commerce -and $Commerce.PSObject.Properties["deploy"]) {
    foreach ($d in @($Commerce.deploy)) {
      if ($d -and [string]$d.kind -eq "unit_printer") { $hasCommercePrinter = $true; break }
    }
  }
  if ($UnitPrinter -and $UnitPrinter.def -and -not $hasCommercePrinter) {
    $pCount = 1
    if ($null -ne $UnitPrinter.count) { $pCount = [Math]::Max(1, [int]$UnitPrinter.count) }
    $printer = Spec ([string]$UnitPrinter.def) $pCount -220 40 100
    $printer.unitPrinter = $true
    $printer.printerProduct = if ($UnitPrinter.product) { [string]$UnitPrinter.product } else { "legcen" }
    $printer.printerMetalIncome = if ($null -ne $UnitPrinter.metalIncome) { [double]$UnitPrinter.metalIncome } else { 10 }
    $printer.printerEnergyIncome = if ($null -ne $UnitPrinter.energyIncome) { [double]$UnitPrinter.energyIncome } else { 50 }
    $kit += $printer
    # Seed a few Phobos so player is not waiting on the first print.
    $kit += (Spec $printer.printerProduct 6 100 -100 70)
  }
  $kit = Add-CommerceDeployToKit $kit $Commerce
  if ($Roster -and $Roster.cadre) {
    foreach ($p in $Roster.cadre.PSObject.Properties) {
      $def = [string]$p.Name
      $cnt = [int]$p.Value
      if ($cnt -gt 0 -and -not ($def -like "*com") -and -not ($def -like "*lab") -and -not ($def -like "*ck") -and -not ($def -like "*ca") -and $def -ne "legbal") {
        $kit += (Spec $def ([Math]::Min($cnt, 3)) -130 -150 90)
      }
    }
  }
  switch ($Family) {
    "tempo" { $kit += (Spec "legcen" 2 -60 -260 90) }
    "siege" { $kit += (Spec "legcen" 2 -200 -200 90) }
    "wild"  { $kit += (Spec "leglht" 1 200 -140 130) }
    default { $kit += (Spec "legcen" 2 140 -260 90) }
  }
  $heroes = if ($Roster -and $Roster.PSObject.Properties["heroes"]) { $Roster.heroes } else { $null }
  return (Add-HeroSpecs $kit $heroes)
}

function Get-ZoneAdjacencyMap {
  param([string]$Workspace, [string]$MapId)
  $path = Join-Path $Workspace "data\zone_maps\authored\zone_adjacency.json"
  if (!(Test-Path $path)) { return $null }
  $all = Get-Content -Raw -LiteralPath $path | ConvertFrom-Json
  if ($all.PSObject.Properties[$MapId]) { return $all.$MapId }
  return $null
}

function Get-ZoneCentroid {
  param($Zone)
  if (-not $Zone -or -not $Zone.bounds) { return ,@(0.5, 0.5) }
  $b = $Zone.bounds
  $cx = ([double]$b.xMin + [double]$b.xMax) * 0.5
  $cz = ([double]$b.zMin + [double]$b.zMax) * 0.5
  return ,@($cx, $cz)
}

function Enforce-AdjacentZones {
  # WO-039: deploy adjacent to target; extract = deploy or another neighbor (short walk).
  param($ZoneMap, $AdjForMap, [string]$DeployId, [string]$TargetId, [string]$ExtractId, [string]$Mode)
  if (-not $AdjForMap -or -not $TargetId -or ($Mode -ne "required" -and $Mode -ne "preferred")) {
    return @{ deploy = $DeployId; extract = $ExtractId; changed = $false }
  }
  $neighbors = @()
  if ($AdjForMap.PSObject.Properties[$TargetId]) {
    $neighbors = @($AdjForMap.$TargetId)
  }
  if ($neighbors.Count -eq 0) {
    return @{ deploy = $DeployId; extract = $ExtractId; changed = $false }
  }
  $deployOk = $neighbors -contains $DeployId
  $newDeploy = $DeployId
  if (-not $deployOk) {
    # Pick neighbor closest to old deploy (or first neighbor).
    $oldC = Get-ZoneCentroid (Get-ZoneById $ZoneMap $DeployId)
    $best = $neighbors[0]
    $bestD = 99.0
    foreach ($n in $neighbors) {
      $c = Get-ZoneCentroid (Get-ZoneById $ZoneMap $n)
      $d = [Math]::Sqrt(($c[0] - $oldC[0]) * ($c[0] - $oldC[0]) + ($c[1] - $oldC[1]) * ($c[1] - $oldC[1]))
      if ($d -lt $bestD) { $bestD = $d; $best = $n }
    }
    $newDeploy = $best
  }
  # Extract: short walk. Prefer deploy itself (hit target, walk back), or the
  # NEAREST other neighbor of target to deploy - never the far opposite shelf.
  $newExtract = $newDeploy
  $extractNeighbors = @($neighbors | Where-Object { $_ -ne $newDeploy })
  if ($extractNeighbors.Count -gt 0 -and $Mode -eq "preferred") {
    # Contested front: allow a slightly different LZ, but still near deploy.
    $dC = Get-ZoneCentroid (Get-ZoneById $ZoneMap $newDeploy)
    $bestE = $newDeploy
    $bestD = 0.0
    $found = $false
    foreach ($n in $extractNeighbors) {
      $c = Get-ZoneCentroid (Get-ZoneById $ZoneMap $n)
      $d = [Math]::Sqrt(($c[0] - $dC[0]) * ($c[0] - $dC[0]) + ($c[1] - $dC[1]) * ($c[1] - $dC[1]))
      # Cap: only accept extract neighbors within ~0.35 normalized of deploy.
      if ($d -le 0.35 -and (-not $found -or $d -lt $bestD)) {
        $bestD = $d; $bestE = $n; $found = $true
      }
    }
    $newExtract = $bestE
  }
  $changed = ($newDeploy -ne $DeployId) -or ($newExtract -ne $ExtractId)
  return @{ deploy = $newDeploy; extract = $newExtract; changed = $changed }
}

function New-NextMissionCandidates {
  # WO-042 / occupied-map doctrine: debrief picks should point at LIVE camps
  # already on the field (preplaced occupation), not empty grass mock-contracts.
  param($ZoneMap, $AdjForMap, [string]$MapId, [string]$CurrentTarget, [int]$MissionNumber, $Occupation = $null, [string]$ExtractZone = "")
  $cands = @()
  $from = if ($CurrentTarget) { @($CurrentTarget) } else { @() }

  # 1) Pre-placed occupation nodes (raid the next eco scar that is already built).
  if ($Occupation) {
    foreach ($node in @($Occupation)) {
      if ($cands.Count -ge 3) { break }
      $zid = [string]$node.zoneId
      if (-not $zid -or $zid -eq $CurrentTarget) { continue }
      $label = if ($node.label) { [string]$node.label } else { $zid }
      $flavor = if ($node.kind) { [string]$node.kind } else { "eco_pocket" }
      $cands += [ordered]@{
        id = "cand_occ_$zid"
        # Hub language (G4): theater verbs, not raw candidate ids
        title = "Push $label"
        plain = "Same map. Raid the $flavor already on the field at $label, then extract."
        mapId = $MapId
        targetZoneId = $zid
        fromZoneIds = $from
        objectiveArchetype = "eco_raid"
        patron = "nullmercs"
        against = "armada"
        preplaced = $true
        occupationKind = $flavor
        hubLabel = "Push $label"
      }
    }
  }

  # 2) Adjacent zone contracts (fallback when occupation list is thin).
  $neighbors = @()
  if ($AdjForMap -and $CurrentTarget -and $AdjForMap.PSObject.Properties[$CurrentTarget]) {
    $neighbors = @($AdjForMap.$CurrentTarget)
  }
  $kinds = @("eco_raid", "seize_lane", "strike_relay")
  $i = 0
  foreach ($n in $neighbors) {
    if ($cands.Count -ge 3) { break }
    if ($cands | Where-Object { $_.targetZoneId -eq $n }) { continue }
    $z = Get-ZoneById $ZoneMap $n
    if (-not $z) { continue }
    $kind = $kinds[$i % $kinds.Count]
    $i += 1
    $label = if ($z.label) { [string]$z.label } else { $n }
    $verb = switch ($kind) {
      "eco_raid" { "Raid" }
      "seize_lane" { "Seize" }
      "strike_relay" { "Strike" }
      default { "Mark" }
    }
    $cands += [ordered]@{
      id = "cand_$($cands.Count + 1)_$n"
      title = "$verb $label"
      plain = "Next chapter: $verb $label ($kind). Same map if you stay; camp refreshes if the zone is empty."
      mapId = $MapId
      targetZoneId = $n
      fromZoneIds = $from
      objectiveArchetype = $kind
      patron = "nullmercs"
      against = "armada"
      preplaced = $false
      hubLabel = "$verb $label"
    }
  }

  # 3) Extract / leave the map (always offer when we have occupation doctrine).
  if ($ExtractZone -or $CurrentTarget) {
    $ex = if ($ExtractZone) { $ExtractZone } else { $CurrentTarget }
    $cands += [ordered]@{
      id = "cand_extract_$ex"
      title = "Extract - bank the scar"
      plain = "Bank the raid. Pull the warband out. Hub reopens for the next board mark."
      mapId = $MapId
      targetZoneId = $ex
      fromZoneIds = $from
      objectiveArchetype = "extract_leave"
      patron = "nullmercs"
      against = "armada"
      preplaced = $true
      extractOnly = $true
      hubLabel = "Extract - bank the scar"
    }
  }

  return @($cands | Select-Object -First 4)
}

function New-MissionCard {
  # WO-031: plain-English mission card (not Ketha flavor dump).
  # Difficulty + XP lines stay explicit so tuning never hides behind fog.
  param($Intent, $ArcProfile, [string]$MapTitle, [string]$Description, [string]$DeployZone, [string]$TargetZone, [string]$ExtractZone, [string]$DifficultyLine = "", [string]$XpLine = "", [string]$HeroLine = "")
  $kind = if ($Intent.objectiveTarget -and $Intent.objectiveTarget.kind) { [string]$Intent.objectiveTarget.kind } else { [string]$Intent.objective }
  $objLine = switch ($kind) {
    "seize_lane" { "Clear the living-shell pocket (~60% eco+teeth), hold under regrow pressure to claim the node, then extract. Claim does not mint free Tnb." }
    "gate_control" { "Clear the gate pocket on the living shell, hold under regrow pressure to claim, then extract. No free Tnb mint." }
    "hold_plateau" { "Clear the plateau shell pocket, hold under regrow pressure to claim the step, then extract. No free Tnb mint." }
    "eco_raid" { "Raid the marked energy works (wreck ~60%), then extract before Armada wrath piles on. The rest of the map is already occupied -- pick another scar later if you want." }
    "economy_disrupt" { "Destroy the enemy economy centerpiece, then extract." }
    "strike_relay" { "Destroy the key relay structure, then extract." }
    "destroy_key_structure" { "Destroy the marked key structure, then extract." }
    "farm_patrol" { "Farm sortie: clear the patrol camp for XP, then extract. Campaign clock barely moves." }
    default { "Complete the marked objective, then extract." }
  }
  $enemyLine = switch ([string]$ArcProfile.enemyMode) {
    "static_bases" { "Pre-built enemy energy works and guns. Static defenders -- not endless off-map waves." }
    "warband" { "Enemy warbands rove this ground -- mobile patrol packs over a thin static shell, not a fortress." }
    "light_qrf" { "Pre-built bases plus light reaction forces." }
    default { "Enemy pressure scales with the front." }
  }
  if ($DifficultyLine) { $enemyLine = "$DifficultyLine  |  $enemyLine" }
  $allyPct = [int]([double]$ArcProfile.allyPower * 100)
  $allyLine = if ($allyPct -ge 80) {
    "Allies are strong this sortie - you are the adjunct. Help the push."
  } elseif ($allyPct -ge 40) {
    "Allies help, but will not win it alone. Stay in the fight."
  } elseif ($allyPct -ge 20) {
    "Light ally support only. You are the main effort."
  } else {
    "You are the strike force. Allies, if any, are secondary."
  }
  $tools = if ([int]$ArcProfile.playerCommanders -le 0) {
    "No commanders. Lead with named heroes and ground units. Blow the base - do not expand."
  } else {
    "Commander available. Still prioritize the objective over a full eco race."
  }
  if ($XpLine) { $tools = "$tools  |  $XpLine" }
  if ($HeroLine) { $tools = "$tools  |  $HeroLine" }
  $mins = if ($kind -eq "eco_raid" -or [int]($Intent.missionNumber) -le 3) { 7 } else { 10 }
  $timerLine = "Soft clock about $mins minutes -- when it hits zero the sortie ends. Objective first, then extract."
  return [ordered]@{
    situation = "Map: $MapTitle. Deploy $DeployZone. Target $TargetZone. Extract $ExtractZone."
    objective = $objLine
    howToWin = $tools
    howItEnds = $timerLine
    threats = $enemyLine
    allies = $allyLine
    plainObjective = $Description
    difficulty = $DifficultyLine
    xp = $XpLine
    heroes = $HeroLine
  }
}

# ============================================================================
# THEMED FORCE CONSTRUCTION
# Camps are assembled from faction rings (eco / perimeter / production /
# patrol) around an objective CENTERPIECE. Only the centerpiece force carries
# role=objective_target, so destruction missions are surgical strikes into a
# defended camp instead of base-wipes. Armada camps read as ordered garrisons
# (walls, turret arcs, Guardians); Cortex camps as industrial works (dense
# energy, converter farms, Thud/AK packs, Punishers).
# ============================================================================

$FACTION = @{
  Armada = @{
    mex = "armmex"; wind = "armwin"; solar = "armsolar"; advsolar = "armadvsol"
    llt = "armllt"; hlt = "armbeamer"; aa = "armrl"; radar = "armrad"; wall = "armdrag"
    mstor = "armmstor"; estor = "armestor"; conv = "armmakr"; lab = "armlab"; nano = "armnanotc"
    raider = "armpw"; skirm = "armham"; assault = "armwar"
    bigGun = "armguard"; popup = "armpb"; fus = "armfus"; arad = "armarad"; targ = "armtarg"
    fort = "armfort"; lrpc = "armbrtha"
    rgb = @(0.25, 0.48, 1.0)
  }
  Cortex = @{
    mex = "cormex"; wind = "corwin"; solar = "corsolar"; advsolar = "coradvsol"
    llt = "corllt"; hlt = "corhlt"; aa = "corrl"; radar = "corrad"; wall = "cordrag"
    mstor = "cormstor"; estor = "corestor"; conv = "cormakr"; lab = "corlab"; nano = "cornanotc"
    raider = "corak"; skirm = "corthud"; assault = "corstorm"
    bigGun = "corpun"; popup = "corvipe"; fus = "corfus"; arad = "corarad"; targ = "cortarg"
    fort = "corfort"; lrpc = "corint"
    rgb = @(1.0, 0.20, 0.16)
  }
}

# Null Mercs field Legion-family scrap-line chassis like the player's clans -
# outsider tech on both - but fly ash-grey null colors. Their camps are lean:
# quick eco, light teeth, and patrols that press the Armada approaches.
$MERC = @{
  mex = "legmex"; wind = "legwin"; solar = "legsolar"; radar = "legrad"
  llt = "leglht"; mg = "legmg"; aa = "legrl"; wall = "legdrag"; mstor = "legmstor"
  lab = "leglab"; nano = "legnanotc"
  raider = "leggat"; skirm = "legcen"; assault = "legjav"
  rgb = @(0.63, 0.62, 0.66)
}

function Get-ScaledCount {
  param([int]$Base, [double]$Scale)
  return [int][Math]::Max(1, [Math]::Round($Base * $Scale))
}

function Spec {
  param([string]$Def, [int]$Count, [int]$Dx, [int]$Dz, [int]$Spacing = 90, [bool]$AtSpots = $false, $PatrolX = $null, $PatrolZ = $null, $Patrol = $null)
  $s = [ordered]@{ unitDefName = $Def; count = [Math]::Max(1, $Count); dx = $Dx; dz = $Dz; spacing = $Spacing }
  if ($AtSpots) { $s.atMetalSpots = $true }
  if ($null -ne $Patrol) { $s.patrol = @($Patrol) }
  elseif ($null -ne $PatrolX) { $s.patrolX = [double]$PatrolX; $s.patrolZ = [double]$PatrolZ }
  return $s
}

function PatrolSweep {
  # Two waypoints straddling a screen point: with CMD.PATROL the unit loops
  # spawn -> wp1 -> wp2 -> spawn, an actual sweep instead of a one-way clump.
  param([double]$PX, [double]$PZ)
  @(
    @{ x = [Math]::Max(0.03, [Math]::Min(0.97, $PX - 0.05)); z = [Math]::Max(0.03, [Math]::Min(0.97, $PZ + 0.05)) },
    @{ x = [Math]::Max(0.03, [Math]::Min(0.97, $PX + 0.05)); z = [Math]::Max(0.03, [Math]::Min(0.97, $PZ - 0.05)) }
  )
}

function Add-HeroSpecs {
  # Pillar C heroes: named Fire-Emblem roster units riding with the kit. Each
  # hero replaces one generic unit of its type when possible so total force
  # size stays balance-neutral. Cracked-farm carries level/rank into seed.
  param($Kit, $Heroes)
  $kit = @($Kit)
  if (-not $Heroes) { return $kit }
  $i = 0
  foreach ($h in $Heroes) {
    # Locked / reserved contracts (e.g. Spoke) do not deploy until unlocked.
    if ([string]$h.status -eq "locked") { continue }
    $def = [string]$h.unitDef
    $hid = [string]$h.heroId
    # Doctrine: Ash-Captain Vane always rides a Karkinos (never Ballista / com).
    if ($hid -eq "vane" -or ([string]$h.name -match "Vane")) { $def = "legkark" }
    # Spoke — wheelie scout tech specialist
    if ($hid -eq "spoke" -or ([string]$h.trait -eq "wheelie_mentor")) { $def = "legscout" }
    if (-not $def -or $def -like "*com") { $def = "legkark" }
    foreach ($s in $kit) {
      if ($s.unitDefName -eq $def -and [int]$s.count -gt 1) { $s.count = [int]$s.count - 1; break }
    }
    $spec = Spec $def 1 (-40 + 90 * $i) (50 + 45 * $i) 100
    $spec.heroId = [string]$h.heroId
    $spec.heroName = [string]$h.name
    $spec.missionCritical = [bool]$h.missionCritical
    $spec.heroHpMult = if ($null -ne $h.hpMult) { [double]$h.hpMult } else { 1.4 }
    $spec.heroXp = if ($null -ne $h.xp) { [double]$h.xp } else { 0.25 }
    if ($null -ne $h.level) { $spec.heroLevel = [int]$h.level }
    if ($null -ne $h.rank) { $spec.heroRank = [string]$h.rank }
    if ($null -ne $h.campaignXp) { $spec.heroCampaignXp = [double]$h.campaignXp }
    if ($h.trait) { $spec.heroTrait = [string]$h.trait }
    if ($h.traits) { $spec.heroTraits = @($h.traits) }
    $kit += $spec
    $i += 1
  }
  return $kit
}

function New-PlayerKit {
  param([string]$Family)
  $kit = @(
    (Spec "legmex" 3 -140 120 120 $true),
    (Spec "legwin" 4 120 160 90),
    (Spec "legsolar" 2 240 80 90),
    (Spec "legrad" 1 40 -60 100),
    (Spec "leglht" 2 -120 -120 130),
    (Spec "legmg" 1 60 -160 100),
    (Spec "legcen" 3 80 -210 95),
    (Spec "legjav" 2 260 -230 110)
  )
  switch ($Family) {
    "economy" { $kit += @((Spec "legck" 2 180 240 90), (Spec "legwin" 2 320 200 85)) }
    "tempo"   { $kit += @((Spec "leggat" 2 -60 -260 90), (Spec "legcen" 1 140 -260 95)) }
    "siege"   { $kit += @((Spec "legjav" 2 -200 -200 110), (Spec "legrl" 1 -40 -60 100)) }
    "wild"    { $kit += @((Spec "legmg" 1 -180 -60 100), (Spec "leglht" 1 200 -140 130)) }
  }
  return $kit
}

function New-PlayerKitFromRoster {
  # Pillar C: the player's starting force IS their persistent warband - a
  # commander hero plus the veteran cadre they carried out of prior sorties -
  # on top of an economy floor so a wiped roster still yields a playable base.
  param([string]$Family, $Roster, [double]$ResourceMod = 1.0, $Commerce = $null)
  # q7 scarcity thins the economy floor (resourceModifier from the graph).
  $wind = [Math]::Max(2, [int][Math]::Round(4 * $ResourceMod))
  $kit = @(
    (Spec "legmex" 3 -140 120 120 $true),
    (Spec "legwin" $wind 120 160 90),
    (Spec "legsolar" 2 240 80 90),
    (Spec "legrad" 1 40 -60 100)
  )
  $comDef = if ($Roster.commander -and $Roster.commander.unitDef) { [string]$Roster.commander.unitDef } else { "legcom" }
  $kit += (Spec $comDef 1 0 40 100)
  $cadreTotal = 0
  if ($Roster.cadre) {
    foreach ($p in $Roster.cadre.PSObject.Properties) {
      $cnt = [int]$p.Value
      if ($cnt -gt 0) { $kit += (Spec ([string]$p.Name) $cnt -120 -160 95); $cadreTotal += $cnt }
    }
  }
  # Floor: a thin cadre (fresh campaign or a rout) still fields a minimum strike element.
  if ($cadreTotal -lt 4) { $kit += (Spec "legcen" (4 - $cadreTotal) 80 -210 95) }
  $active = @(); if ($Roster.commander -and $Roster.commander.activePerks) { $active = @($Roster.commander.activePerks) }
  if ($active -contains "rapid_deploy") { $kit += (Spec "legjav" 1 200 -230 110) }
  switch ($Family) {
    "economy" { $kit += (Spec "legck" 1 180 240 90) }
    "tempo"   { $kit += (Spec "leggat" 1 -60 -260 90) }
    "siege"   { $kit += (Spec "legrl" 1 -40 -60 100) }
    "wild"    { $kit += (Spec "leglht" 1 200 -140 130) }
  }
  # A rez bot rides with every warband: hero wrecks must be recoverable.
  $kit += (Spec "legrezbot" 1 -170 60 80)
  $kit = Add-CommerceDeployToKit $kit $Commerce
  $heroes = if ($Roster -and $Roster.PSObject.Properties["heroes"]) { $Roster.heroes } else { $null }
  return (Add-HeroSpecs $kit $heroes)
}

function New-FinaleKitFromRoster {
  # Drop 2 Act 3: massive starting conditions — the whole campaign walks out.
  # Commander + established economy + factory floor + defenses + a real army,
  # then the full carried cadre (uncapped) and every living hero on top.
  # Verified Legion defs only (same vocabulary as the rest of the compiler).
  param([string]$Family, $Roster, [double]$ResourceMod = 1.0, $Commerce = $null)
  $kit = @(
    (Spec "legmex" 5 -160 130 120 $true),
    (Spec "legwin" 10 140 180 85),
    (Spec "legsolar" 6 260 90 90),
    (Spec "legmstor" 1 60 250 100),
    (Spec "legrad" 2 40 -60 160),
    (Spec "leglab" 1 -300 -140 130),
    (Spec "legnanotc" 3 -210 -230 90),
    (Spec "legdrag" 10 -60 -320 40),
    (Spec "leglht" 4 -140 -140 140),
    (Spec "legmg" 2 60 -170 110),
    (Spec "legrl" 2 -40 -80 150),
    (Spec "legscout" 6 -70 140 85),
    (Spec "legcen" 16 90 -220 80),
    (Spec "leggat" 6 -90 -260 90),
    (Spec "legjav" 6 240 -240 100),
    (Spec "legkark" 2 170 40 110),
    (Spec "legrezbot" 6 -170 70 80)
  )
  $comDef = if ($Roster -and $Roster.commander -and $Roster.commander.unitDef) { [string]$Roster.commander.unitDef } else { "legcom" }
  $kit += (Spec $comDef 1 0 40 100)
  if ($Roster -and $Roster.cadre) {
    foreach ($p in $Roster.cadre.PSObject.Properties) {
      $cnt = [int]$p.Value
      if ($cnt -gt 0) { $kit += (Spec ([string]$p.Name) $cnt -130 -160 90) }
    }
  }
  $kit = Add-CommerceDeployToKit $kit $Commerce
  $heroes = if ($Roster -and $Roster.PSObject.Properties["heroes"]) { $Roster.heroes } else { $null }
  return (Add-HeroSpecs $kit $heroes)
}

function New-StrikeTeam {
  # Arc A raid pack (player feedback):
  #   - Wheelies (legscout) for the player
  #   - Army of Phobos (legcen) -- NOT Ballistas (legbal / missile bots)
  #   - Pack of Zagreus rez bots (legrezbot)
  #   - Ash-Captain Vane in a Karkinos (forced in Add-HeroSpecs)
  #   - No commander suit, no base economy
  #   - WO-043: commerce packs (Punch of Thugs, grunt fab if bought) ride along
  param($Roster, [double]$ResourceMod = 1.0, $Commerce = $null)
  $kit = @(
    (Spec "legscout"  4 -60 130 90),
    (Spec "legcen"   12 40 -40 80),
    (Spec "legkark"   1 170 30 100),
    (Spec "legrezbot" 6 -150 70 80)
  )
  $kit = Add-CommerceDeployToKit $kit $Commerce
  # Veteran cadre carried from prior sorties (combat only; never com / Ballista).
  if ($Roster -and $Roster.cadre) {
    foreach ($p in $Roster.cadre.PSObject.Properties) {
      $def = [string]$p.Name
      $cnt = [int]$p.Value
      if ($cnt -gt 0 -and -not ($def -like "*com") -and $def -ne "legbal") {
        $kit += (Spec $def $cnt -130 -150 90)
      }
    }
  }
  $heroes = if ($Roster -and $Roster.PSObject.Properties["heroes"] -and $Roster.heroes) { $Roster.heroes } else { $null }
  if ($heroes) {
    $kit = Add-HeroSpecs $kit $heroes
  } else {
    $hero = Spec "legkark" 1 0 0 100
    $hero.hero = $true
    $hero.heroName = if ($Roster -and $Roster.commander -and $Roster.commander.name) { [string]$Roster.commander.name } else { "Ash-Captain Vane" }
    $kit += $hero
  }
  return $kit
}

function Ring-Eco {
  param($T, [double]$S)
  @(
    (Spec $T.mex 4 -160 120 120 $true),
    (Spec $T.wind (Get-ScaledCount 4 $S) 140 170 85),
    (Spec $T.solar (Get-ScaledCount 2 $S) 260 60 95),
    (Spec $T.mstor 1 60 240 100),
    (Spec $T.conv (Get-ScaledCount 2 $S) 320 170 95)
  )
}

function Ring-Perimeter {
  param($T, [double]$S, [int]$FX, [int]$FZ)
  # FX/FZ point from the camp toward the player: defenses face the approach.
  @(
    (Spec $T.llt (Get-ScaledCount 4 $S) (170 * $FX) (150 * $FZ) 150),
    (Spec $T.wall (Get-ScaledCount 8 $S) (270 * $FX) (240 * $FZ) 40),
    (Spec $T.aa 2 (-90 * $FX) (60 * $FZ) 170),
    (Spec $T.radar 1 0 -80 100)
  )
}

function Ring-Production {
  param($T)
  @((Spec $T.lab 1 -300 -150 120), (Spec $T.nano 2 -210 -240 90))
}

function Ring-Patrol {
  param($T, [double]$S, [double]$PX, [double]$PZ, [switch]$FrontBand)
  # WO-004: front-band sorties field a thin screen at start; packs arrive as waves.
  $sweep = PatrolSweep $PX $PZ
  if ($FrontBand) {
    @(
      (Spec $T.raider (Get-ScaledCount 3 $S) 120 -300 80 -Patrol $sweep),
      (Spec $T.skirm (Get-ScaledCount 2 $S) -140 -320 90 -Patrol $sweep),
      (Spec $T.assault (Get-ScaledCount 1 $S) 20 -390 95 -Patrol $sweep)
    )
  } else {
    @(
      (Spec $T.raider (Get-ScaledCount 4 $S) 120 -300 80 -Patrol $sweep),
      (Spec $T.skirm (Get-ScaledCount 3 $S) -140 -320 90 -Patrol $sweep),
      (Spec $T.assault (Get-ScaledCount 3 $S) 20 -390 95 -Patrol $sweep)
    )
  }
}

function Ring-Fortify {
  param($T, [int]$FX, [int]$FZ)
  @(
    (Spec $T.hlt 2 (110 * $FX) (-70 * $FZ) 180),
    (Spec $T.popup 1 (200 * $FX) (120 * $FZ) 100),
    (Spec $T.bigGun 1 -50 40 100)
  )
}

function Ring-Jammers {
  # Cortex hideout flavor: radar jammer towers + a cloaking field so the base
  # reads as hidden/desolate until you are on top of it (eye_of_horus).
  param($T)
  @(
    (Spec "corjamt" 2 -60 120 160),
    (Spec "corjamt" 1 180 -40 160),
    (Spec "corshroud" 1 0 -30 100)
  )
}

# Surgical objectives are honest: exactly ONE structure is "the relay"/"the
# gun" (role=objective_target); its support hardware defends the camp as
# garrison instead of padding the kill counter.
function Centerpiece-Relay {
  param($T)
  @((Spec $T.targ 1 0 0 100))
}

function Support-Relay {
  param($T)
  @((Spec $T.arad 1 120 60 100), (Spec $T.fus 1 -130 70 110))
}

function Centerpiece-LRPC {
  param($T)
  @((Spec $T.lrpc 1 0 0 100))
}

function Support-LRPC {
  param($T)
  @((Spec $T.fus 1 140 80 110), (Spec $T.fort 6 -90 -120 42))
}

function Centerpiece-EcoWorks {
  param($T, [double]$S)
  @(
    (Spec $T.fus 1 0 0 110),
    (Spec $T.advsolar (Get-ScaledCount 3 $S) 150 60 100),
    (Spec $T.conv (Get-ScaledCount 4 $S) -150 80 90),
    (Spec $T.estor 1 40 180 100)
  )
}

function Centerpiece-CommandPost {
  param($T)
  @((Spec $T.arad 1 0 0 100), (Spec $T.fus 1 130 60 110), (Spec $T.hlt 1 -110 -60 120))
}

function Centerpiece-Hives {
  param([double]$Hazard)
  $specs = @(
    (Spec "raptor_hive" 1 -120 -40 240),
    (Spec "raptor_hive" 1 140 80 240)
  )
  if ($Hazard -gt 0.5) { $specs += (Spec "raptor_hive" 1 0 -220 240) }
  return $specs
}

function New-MercFoothold {
  # WO-038: allyPower scales kit. High = javelin shred (M1 adjunct). Low = light guns.
  param([double]$S, [double]$PX, [double]$PZ, [int]$FX, [int]$FZ, [double]$AllyPower = 1.0)
  $p = [Math]::Max(0.1, [Math]::Min(1.0, $AllyPower))
  $specs = @(
    (Spec $MERC.radar 1 0 -70 100),
    (Spec $MERC.llt (Get-ScaledCount ([Math]::Max(1, [int](3 * $p))) $S) (160 * $FX) (140 * $FZ) 150),
    (Spec $MERC.wall (Get-ScaledCount ([Math]::Max(2, [int](6 * $p))) $S) (260 * $FX) (220 * $FZ) 40),
    (Spec $MERC.raider (Get-ScaledCount ([Math]::Max(1, [int](3 * $p))) $S) 110 -290 80 -Patrol (PatrolSweep $PX $PZ)),
    (Spec $MERC.skirm (Get-ScaledCount ([Math]::Max(1, [int](2 * $p))) $S) -130 -310 90 -Patrol (PatrolSweep $PX $PZ))
  )
  # Heavy assault (javelins) only when allies are meant to carry early missions.
  if ($p -ge 0.7) {
    $specs += (Spec $MERC.assault (Get-ScaledCount 2 $S) 10 -370 95 -Patrol (PatrolSweep $PX $PZ))
    $specs += (Spec $MERC.mg 1 (230 * $FX) (90 * $FZ) 110)
    $specs += (Spec $MERC.lab 1 -290 -140 120)
    $specs += (Spec $MERC.nano 1 -200 -230 90)
    $specs += (Spec $MERC.mex 2 -140 110 120 $true)
    $specs += (Spec $MERC.wind (Get-ScaledCount 3 $S) 130 160 85)
  } elseif ($p -ge 0.4) {
    $specs += (Spec $MERC.assault 1 10 -370 95 -Patrol (PatrolSweep $PX $PZ))
    $specs += (Spec $MERC.aa 1 (-80 * $FX) (60 * $FZ) 160)
    $specs += (Spec $MERC.mex 1 -140 110 120 $true)
    $specs += (Spec $MERC.wind 2 130 160 85)
  } else {
    # Peer/strike-lead: thin support screen, no lab, no javelin blob.
    $specs += (Spec $MERC.aa 1 (-80 * $FX) (60 * $FZ) 160)
    $specs += (Spec $MERC.mg 1 (230 * $FX) (90 * $FZ) 110)
  }
  return $specs
}

function Ring-RaptorGarrison {
  param([double]$Hazard)
  $swarmScale = 1.0 + (2.0 * [Math]::Max(0.0, [Math]::Min(1.0, $Hazard)))
  @(
    (Spec "raptor_turret_basic_t2_v1" 3 -140 90 150),
    (Spec "raptor_land_swarmer_basic_t1_v1" (Get-ScaledCount 10 $swarmScale) 130 -100 70),
    (Spec "raptor_land_swarmer_basic_t2_v1" (Get-ScaledCount 4 $swarmScale) -200 -150 80)
  )
}

# ============================================================================
# ECO-RAID: an ESTABLISHED Armada energy economy (Pillar / get-back-on-track).
# Read from the crafted campaignForces (data/map_pool/seven_maps.json) instead
# of a generic combat camp: solar/wind farms + energy converters + a fusion
# crown, scattered organically across the objective zone, only lightly defended.
# The economy itself is the objective - damage % is the fraction of the works
# the strike team wrecks before it extracts.
# ============================================================================

function Scatter {
  # Emit several small Specs of one def spread deterministically (golden-angle
  # spiral, no RNG) so buildings read as organic sprawl rather than a tidy grid.
  param([string]$Def, [int]$Total, [double]$Spread = 520, [int]$PerCluster = 2, [int]$Phase = 0, [int]$Spacing = 60, [bool]$AtSpots = $false)
  $specs = @()
  if (-not $Def -or $Total -le 0) { return $specs }
  $clusters = [Math]::Max(1, [Math]::Ceiling($Total / [double]$PerCluster))
  $placed = 0
  $i = 0
  while ($placed -lt $Total) {
    $n = [Math]::Min($PerCluster, $Total - $placed)
    $ang = ($i * 2.399963) + ($Phase * 0.7)
    $rad = $Spread * [Math]::Sqrt(($i + 0.5) / $clusters)
    $dx = [int][Math]::Round($rad * [Math]::Cos($ang))
    $dz = [int][Math]::Round($rad * [Math]::Sin($ang))
    $specs += (Spec $Def $n $dx $dz $Spacing $AtSpots)
    $placed += $n
    $i += 1
  }
  return $specs
}

function Get-InfraCount {
  param($Parsed, [string]$Key)
  if ($Parsed -and $Parsed.PSObject.Properties[$Key] -and $null -ne $Parsed.$Key) { return [int]$Parsed.$Key }
  return 0
}

function Build-EcoSprawl {
  # The energy economy (objective_target). Counts come from the crafted per-map
  # Armada composition, multiplied so the works read as established, and scaled
  # by mission difficulty. On Greenest Fields the authored data has NO mex (a
  # no-metal converter economy), so mex appear only where the crafted data lists
  # them - the sprawl is solar, wind, and converters.
  param($Parsed, [double]$Scale)
  $T = $FACTION["Armada"]
  $mul = 2.0
  $solarN = [Math]::Max(4, [int][Math]::Round((Get-InfraCount $Parsed "solar") * $mul * $Scale))
  $windN  = [Math]::Max(3, [int][Math]::Round((Get-InfraCount $Parsed "wind")  * $mul * $Scale))
  $mexN   = [int][Math]::Round((Get-InfraCount $Parsed "mex") * $mul * $Scale)
  $convN  = [Math]::Max(3, [int][Math]::Round(($solarN + $windN) * 0.4))
  $advN   = [Math]::Max(2, [int][Math]::Round($solarN * 0.25))
  $specs = @()
  if ($mexN -gt 0) { $specs += (Spec $T.mex $mexN -120 120 120 $true) }
  $specs += Scatter $T.solar    $solarN 560 3 0 60
  $specs += Scatter $T.wind     $windN  620 2 3 70
  $specs += Scatter $T.conv     $convN  440 2 6 70
  $specs += Scatter $T.advsolar $advN   300 1 9 90
  # No constructors (armck) -- static works only. SimpleAI + cons = commander soup.
  $specs += @(
    (Spec $T.fus 1 0 0 110),
    (Spec $T.estor 2 90 -60 90),
    (Spec $T.mstor 1 -80 70 90)
  )
  return $specs
}

function Build-EcoGuard {
  # Beefier static ring so allied Javelins get stalled on the approach.
  # Mobile screen is bots only -- leave Wheelies (legscout) for the player.
  # NOT objective-tagged: killing the guard is not the raid win condition.
  param($Parsed, [double]$Scale, [int]$FX, [int]$FZ)
  $T = $FACTION["Armada"]
  $s = [Math]::Max(0.9, $Scale)
  $lltN = [Math]::Max(7, [int][Math]::Round((Get-InfraCount $Parsed "defense") * 3.0 * $s))
  if ($lltN -lt 8) { $lltN = 8 }
  $specs = @()
  $specs += Scatter $T.llt $lltN 460 1 2 140
  $specs += @(
    (Spec $T.hlt 2 (160 * $FX) (130 * $FZ) 180),
    (Spec $T.hlt 1 (-140 * $FX) (90 * $FZ) 180),
    (Spec $T.wall (Get-ScaledCount 10 $s) (240 * $FX) (200 * $FZ) 38),
    (Spec $T.wall (Get-ScaledCount 6 $s) (90 * $FX) (260 * $FZ) 38),
    (Spec $T.aa 2 (-100 * $FX) (40 * $FZ) 160),
    (Spec $T.radar 1 0 -80 100),
    # Infantry screen only (no wheeled/scout vehicles for the enemy).
    (Spec $T.raider (Get-ScaledCount 4 $s) (140 * $FX) (120 * $FZ) 80),
    (Spec $T.skirm  (Get-ScaledCount 3 $s) (-120 * $FX) (100 * $FZ) 90),
    (Spec $T.assault (Get-ScaledCount 2 $s) (20 * $FX) (160 * $FZ) 95)
  )
  return $specs
}

function Build-EcoSprawlLight {
  # Secondary occupation pocket: mostly eco, thinner than the primary works.
  param($Parsed, [double]$Scale, [string]$Flavor = "mixed")
  $T = $FACTION["Armada"]
  $s = [Math]::Max(0.45, [Math]::Min(0.85, $Scale))
  $specs = @()
  if ($Flavor -eq "wind") {
    $specs += Scatter $T.wind ([Math]::Max(5, [int](8 * $s))) 480 2 1 70
    $specs += Scatter $T.conv ([Math]::Max(2, [int](3 * $s))) 300 2 4 70
    $specs += (Spec $T.estor 1 40 -40 90)
  } elseif ($Flavor -eq "solar") {
    $specs += Scatter $T.solar ([Math]::Max(5, [int](8 * $s))) 480 3 0 60
    $specs += Scatter $T.advsolar ([Math]::Max(1, [int](2 * $s))) 280 1 5 90
    $specs += Scatter $T.conv ([Math]::Max(2, [int](3 * $s))) 320 2 3 70
  } else {
    $specs += Scatter $T.solar ([Math]::Max(3, [int](5 * $s))) 420 2 0 60
    $specs += Scatter $T.wind ([Math]::Max(3, [int](5 * $s))) 420 2 2 70
    $specs += Scatter $T.conv ([Math]::Max(2, [int](3 * $s))) 300 2 4 70
    $specs += (Spec $T.fus 1 0 0 110)
  }
  return $specs
}

function Build-EcoGuardLight {
  param([double]$Scale, [int]$FX, [int]$FZ)
  $T = $FACTION["Armada"]
  $s = [Math]::Max(0.5, $Scale)
  @(
    (Spec $T.llt (Get-ScaledCount 4 $s) (150 * $FX) (120 * $FZ) 140),
    (Spec $T.llt 2 (-120 * $FX) (80 * $FZ) 140),
    (Spec $T.wall (Get-ScaledCount 6 $s) (220 * $FX) (180 * $FZ) 38),
    (Spec $T.radar 1 0 -50 100),
    (Spec $T.raider (Get-ScaledCount 2 $s) (100 * $FX) (90 * $FZ) 80),
    (Spec $T.skirm  (Get-ScaledCount 2 $s) (-90 * $FX) (70 * $FZ) 90)
  )
}

function Add-EcoSprawlCamp {
  param(
    [double[]]$Center, $Parsed, [double]$Scale, [int]$FX, [int]$FZ, [string]$Label,
    [switch]$OccupationOnly,
    [string]$ZoneId = "",
    [string]$Flavor = "mixed"
  )
  $teamID = $script:nextTeam; $script:nextTeam += 1
  $allyID = $script:nextAllyTeam; $script:nextAllyTeam += 1
  $script:allyTeams += [ordered]@{ id = $allyID; startRect = New-StartRect $Center 0.22 }
  $script:teams += [ordered]@{ id = $teamID; side = "Armada"; allyTeam = $allyID; base = @($Center[0], $Center[1]); rgb = $FACTION["Armada"].rgb; label = "Armada - $Label"; faction = "armada" }
  # occupation = pre-placed world eco (not yet the active objective).
  # objective_target = this sortie`s raid credit structures.
  $worksRole = if ($OccupationOnly) { "occupation" } else { "objective_target" }
  $worksRecipe = if ($OccupationOnly) { @(Build-EcoSprawlLight $Parsed $Scale $Flavor) } else { @(Build-EcoSprawl $Parsed $Scale) }
  $guardRecipe = if ($OccupationOnly) { @(Build-EcoGuardLight $Scale $FX $FZ) } else { @(Build-EcoGuard $Parsed $Scale $FX $FZ) }
  $script:baseRecipes["camp${teamID}_works"] = $worksRecipe
  $script:forces += [ordered]@{
    id = "camp${teamID}_works"
    label = $Label
    teamID = $teamID
    side = "Armada"
    faction = "armada"
    role = $worksRole
    zoneId = $ZoneId
    occupationKind = $Flavor
    base = [ordered]@{ x = $Center[0]; z = $Center[1] }
    recipe = "camp${teamID}_works"
  }
  $script:baseRecipes["camp${teamID}_guard"] = $guardRecipe
  $script:forces += [ordered]@{
    id = "camp${teamID}_guard"
    label = "$Label guard"
    teamID = $teamID
    side = "Armada"
    faction = "armada"
    role = "garrison"
    zoneId = $ZoneId
    base = [ordered]@{ x = $Center[0]; z = $Center[1] }
    recipe = "camp${teamID}_guard"
  }
  # No AI on eco occupation: static world, not commander soup.
  if (-not $OccupationOnly -and $null -eq $script:primaryEnemyTeamID) {
    $script:primaryEnemyTeamID = $teamID; $script:primaryEnemySide = "Armada"
  }
  return [ordered]@{
    zoneId = $ZoneId
    label = $Label
    kind = $Flavor
    teamID = $teamID
    preplaced = $true
    primary = (-not $OccupationOnly)
  }
}

if (-not $IntentPath) { $IntentPath = Join-Path $Workspace "outbox\next_mission_intent.json" }
if (-not $StatePath) { $StatePath = Join-Path $Workspace "state\campaign_state.json" }
if (!(Test-Path $IntentPath)) { throw "No next mission intent at $IntentPath. Run ADVANCE_CAMPAIGN_V1.bat or scripts\advance_campaign_v1.ps1 first." }

$config = Get-VerdanceConfig -Workspace $Workspace
$intent = Get-Content -Raw -LiteralPath $IntentPath | ConvertFrom-Json
$state = if (Test-Path $StatePath) { Get-Content -Raw -LiteralPath $StatePath | ConvertFrom-Json } else { $null }
$poolPath = Join-Path $Workspace "data\map_pool\seven_maps.json"
if (!(Test-Path $poolPath)) { throw "Missing map pool: $poolPath" }
$pool = Get-Content -Raw -LiteralPath $poolPath | ConvertFrom-Json
$map = Get-MapEntry $pool ([string]$intent.mapId)
if (-not $map) { throw "Unknown campaign map id in intent: $($intent.mapId)" }

$zoneMapRel = "data\zone_maps\authored\$($intent.mapId).authored.zone_map.json"
$zoneMapPath = Join-Path $Workspace $zoneMapRel
if (!(Test-Path $zoneMapPath)) { throw "Missing authored zone map for $($intent.mapId): $zoneMapPath" }
$zoneMap = Get-Content -Raw -LiteralPath $zoneMapPath | ConvertFrom-Json

$missionNumber = if ($intent.missionNumber) { [int]$intent.missionNumber } elseif ($state -and $state.missionNumber) { [int]$state.missionNumber } else { 1 }
$missionId = if ($intent.missionId) { [string]$intent.missionId } else { "va_$('{0:d3}' -f $missionNumber)" }
$objectiveKind = if ($intent.objectiveTarget -and $intent.objectiveTarget.kind) { [string]$intent.objectiveTarget.kind } else { [string]$intent.objective }
# Early arc profile so adjacency + kit can use it before camp assembly.
$arcProfile = Get-ArcProfile -MissionNumber $missionNumber -ObjectiveKind $objectiveKind
# Drop 2 act structure: the engine's act stamp overrides the mission-number arcs.
#   Act 1 ground control (warband, no commander) keeps the existing profile.
#   Act 2 constrained RTS: commander + T1 base building, T2/T3 as earned units.
#   Act 3 finale: full unconstrained BAR with massive starting conditions.
$actNum = if ($intent.PSObject.Properties["act"] -and $intent.act -and $intent.act.act) { [int]$intent.act.act }
          elseif ($missionNumber -le 5) { 1 } elseif ($missionNumber -le 10) { 2 } else { 3 }
$actName = if ($intent.PSObject.Properties["act"] -and $intent.act -and $intent.act.name) { [string]$intent.act.name }
           elseif ($actNum -eq 1) { "ground_control" } elseif ($actNum -eq 2) { "constrained_rts" } else { "unbound_finale" }
$isFinale = [bool]($intent.PSObject.Properties["finale"] -and $intent.finale)
$finaleKind = if ($isFinale -and $intent.finale.kind) { [string]$intent.finale.kind } else { "" }
$techPolicy = if ($intent.PSObject.Properties["techPolicy"] -and $intent.techPolicy) { $intent.techPolicy }
              elseif ($actNum -eq 1) { [ordered]@{ act = 1; mode = "ground_control"; buildTech = 1; buildStructures = $false } }
              elseif ($actNum -eq 2) { [ordered]@{ act = 2; mode = "constrained_rts"; buildTech = 1; buildStructures = $true } }
              else { [ordered]@{ act = 3; mode = "unbound"; buildTech = 3; buildStructures = $true } }
if ($actNum -ge 3) {
  $arcProfile.id = "unbound_finale"
  $arcProfile.playerCommanders = 1
  $arcProfile.playerEco = $true
  $arcProfile.unitPrinter = $null
  $arcProfile.enemyMode = "light_qrf"
  $arcProfile.escalation = "full"
  $arcProfile.allowEnemyProduction = $true
  $arcProfile.objectiveAdjacency = "forward"
  $arcProfile.sweepEnemyCommanders = $false
} elseif ($actNum -eq 2) {
  $arcProfile.id = "constrained_rts"
  $arcProfile.playerCommanders = 1
  $arcProfile.playerEco = $true
  $arcProfile.unitPrinter = $null
  $arcProfile.enemyMode = "light_qrf"
  $arcProfile.escalation = if ($missionNumber -le 7) { "light" } else { "full" }
  $arcProfile.allowEnemyProduction = $true
  $arcProfile.objectiveAdjacency = "preferred"
  $arcProfile.sweepEnemyCommanders = $false
} elseif ([string]$arcProfile.enemyMode -eq "static_bases") {
  # Drop 3: act-1 ground control reads warband-vs-warband — the enemy fields
  # roving patrol packs over a thinned static shell, not a fortress. The
  # com_solar_farm flavor still overrides this below, as before.
  $arcProfile.enemyMode = "warband"
}
Write-Host ("Act structure: act={0} ({1}) finale={2} buildTech={3} buildStructures={4}" -f `
  $actNum, $actName, $finaleKind, $techPolicy.buildTech, $techPolicy.buildStructures)
# WO-037: sandbox flavor from intent or explicit greenest com-soup contracts.
if ($intent.PSObject.Properties["flavor"] -and $intent.flavor) {
  $arcProfile.flavor = [string]$intent.flavor
} elseif ($intent.PSObject.Properties["storyTags"] -and ($intent.storyTags -contains "com_solar_farm")) {
  $arcProfile.flavor = "com_solar_farm"
}
# WO-036 hard mode: intent.difficulty.enemyAI or environment.hardMode
if ($intent.difficulty -and $intent.difficulty.enemyAI) {
  $arcProfile.enemyAI = [string]$intent.difficulty.enemyAI
} elseif ($intent.environment -and $intent.environment.hardMode) {
  $arcProfile.enemyAI = "barbarian"
}
if ($arcProfile.flavor -eq "com_solar_farm") {
  $arcProfile.sweepEnemyCommanders = $false
  $arcProfile.allowEnemyProduction = $true
  $arcProfile.enemyMode = "com_solar_farm"
  $arcProfile.playerCommanders = 1
  $arcProfile.unitPrinter = $null
}
# Drop 4 escalation ladder: the engine's authored plan (scale window,
# objective strength, waves override, secondary objectives). One authority
# for pacing — the compiler honors every field it stamps.
$escPlan = if ($intent.PSObject.Properties["escalationPlan"] -and $intent.escalationPlan) { $intent.escalationPlan } else { $null }
$objectiveStrength = if ($escPlan -and $escPlan.objectiveStrength) { [string]$escPlan.objectiveStrength } else { "surgical" }
if ($objectiveStrength -eq "finale") { $objectiveStrength = "surgical" }
if ($escPlan -and $escPlan.wavesMode) { $arcProfile.escalation = [string]$escPlan.wavesMode }
$escSecondaries = @()
if ($escPlan -and $escPlan.secondaries) { $escSecondaries = @($escPlan.secondaries) }
if ($escPlan) {
  Write-Host ("Escalation plan: strength={0} waves={1} secondaries={2}" -f `
    $objectiveStrength, [string]$arcProfile.escalation, $escSecondaries.Count)
}

$deployZoneId = [string]$intent.deploymentZoneId
$extractZoneId = [string]$intent.extractionZoneId
$targetZoneId = if ($intent.objectiveTarget -and $intent.objectiveTarget.targetZoneId) { [string]$intent.objectiveTarget.targetZoneId } else { "" }
$adjForMap = Get-ZoneAdjacencyMap -Workspace $Workspace -MapId ([string]$intent.mapId)
$adjResult = Enforce-AdjacentZones -ZoneMap $zoneMap -AdjForMap $adjForMap `
  -DeployId $deployZoneId -TargetId $targetZoneId -ExtractId $extractZoneId `
  -Mode ([string]$arcProfile.objectiveAdjacency)
if ($adjResult.changed) {
  Write-Host ("WO-039 adjacent layout: deploy {0} -> {1}; extract {2} -> {3}" -f `
    $deployZoneId, $adjResult.deploy, $extractZoneId, $adjResult.extract)
  $deployZoneId = [string]$adjResult.deploy
  $extractZoneId = [string]$adjResult.extract
  $intent.deploymentZoneId = $deployZoneId
  $intent.extractionZoneId = $extractZoneId
}

$deployZone = Get-ZoneById $zoneMap $deployZoneId
$targetZone = Get-ZoneById $zoneMap $targetZoneId
$deployCenter = Get-ZoneCenter $deployZone @(0.16, 0.16)
$enemyCenter = Get-ZoneCenter $targetZone @(0.84, 0.84)
# WO-004 front-band: for contracts, slide deploy toward the target border so
# first contact lands in ~90s instead of a long march from a corner shelf.
$isContract = ($intent.PSObject.Properties["contractActive"] -and $intent.contractActive) -or ($intent.PSObject.Properties["fromZoneIds"] -and $intent.fromZoneIds -and @($intent.fromZoneIds).Count -gt 0)
if ($isContract -and $deployZone -and $targetZone) {
  $dx = $deployCenter[0]; $dz = $deployCenter[1]
  $ex = $enemyCenter[0]; $ez = $enemyCenter[1]
  # Adjacent mode: milder slide (already next door).
  $blend = if ([string]$arcProfile.objectiveAdjacency -eq "required") { 0.25 } else { 0.45 }
  $deployCenter = @(((1 - $blend) * $dx + $blend * $ex), ((1 - $blend) * $dz + $blend * $ez))
}
$wildCenter = @(0.50, 0.50)
$frontBand = $isContract -or ($intent.objective -in @("seize_lane", "gate_control"))

$enemySide = Get-EnemySide ([string]$intent.mapId) $intent
$enemyRecipe = Get-EnemyRecipeName $enemySide
$enemyRgb = Get-EnemyRgb $enemySide
$hasWild = ($map.PSObject.Properties["wilds"] -and $map.wilds) -or ($map.PSObject.Properties["raptors"] -and $map.raptors) -or ($intent.hazardPolicy -and $intent.hazardPolicy -ne "none")

$title = if ($intent.PSObject.Properties["title"] -and $intent.title) {
  "$($intent.title) - $($map.title)"
} else {
  "Verdance Alpha: $($map.title)"
}
$requiredFrames = Get-RequiredFrames $intent
$description = Get-ObjectiveDescription $intent
# Occupation list filled during camp assembly (eco_raid Arc A fills the map).
$script:mapOccupation = @()
$script:primaryEnemyTeamID = $null
$script:primaryEnemySide = $null
$script:secondaryMeta = @()  # Drop 4: placed secondary-objective camps (id/zone/required/x/z)
$nextMissionCandidates = @()  # rebuilt after occupation so picks point at live camps
$script:livingShellPayload = $null
$script:wrathPayload = $null

function Resolve-LivingShellTemplatePath {
  param([string]$Ws, [string]$MapId)
  $dir = Join-Path $Ws "data\base_templates\$MapId"
  if (!(Test-Path $dir)) { return $null }
  # Prefer real bake, then map-specific placeholders, then any non-recipe shell json.
  foreach ($name in @(
      "armada_t15_v1.json",
      "living_shell_v1.json",
      "cortex_core_v1.json",
      "armada_placeholder_v1.json",
      "living_placeholder_v1.json"
    )) {
    $p = Join-Path $dir $name
    if (Test-Path $p) { return $p }
  }
  $any = Get-ChildItem -LiteralPath $dir -Filter "*placeholder*.json" -ErrorAction SilentlyContinue |
    Sort-Object Name |
    Select-Object -First 1
  if ($any) { return $any.FullName }
  $any = Get-ChildItem -LiteralPath $dir -Filter "*.json" -ErrorAction SilentlyContinue |
    Where-Object { $_.Name -ne "bake_recipe.json" } |
    Sort-Object Name |
    Select-Object -First 1
  if ($any) { return $any.FullName }
  return $null
}

function Load-WrathPack {
  param([string]$Ws, [string]$PackId = "armada_gunslinger_response_v1")
  $p = Join-Path $Ws "data\base_templates\wrath\$PackId.json"
  if (!(Test-Path $p)) { return $null }
  return (Get-Content -Raw -LiteralPath $p | ConvertFrom-Json)
}

function Build-LivingShellFromTemplate {
  param($Template, [int]$TeamId, [string]$PrimaryZoneId)
  $primaryPocket = $null
  foreach ($pk in @($Template.pockets)) {
    if ($pk.primaryCandidate) { $primaryPocket = [string]$pk.pocketId; break }
  }
  if (-not $primaryPocket -and $Template.pockets -and @($Template.pockets).Count -gt 0) {
    $primaryPocket = [string](@($Template.pockets)[0].pocketId)
  }
  # Prefer pocket whose zone matches the mission target.
  if ($PrimaryZoneId) {
    foreach ($pk in @($Template.pockets)) {
      if ([string]$pk.zoneId -eq $PrimaryZoneId) {
        $primaryPocket = [string]$pk.pocketId
        break
      }
    }
  }
  $units = @()
  foreach ($u in @($Template.units)) {
    $units += [ordered]@{
      unitDefName = [string]$u.unitDefName
      x = [double]$u.x
      z = [double]$u.z
      facing = if ($null -ne $u.facing) { [int]$u.facing } else { 0 }
      zoneId = if ($u.zoneId) { [string]$u.zoneId } else { "" }
      pocketId = if ($u.pocketId) { [string]$u.pocketId } else { "" }
      keepClass = if ($u.keepClass) { [string]$u.keepClass } else { "static" }
      faction = if ($u.faction) { [string]$u.faction } else { "" }
    }
  }
  $pockets = @()
  foreach ($pk in @($Template.pockets)) {
    $pockets += [ordered]@{
      pocketId = [string]$pk.pocketId
      zoneId = [string]$pk.zoneId
      label = [string]$pk.label
      kind = if ($pk.kind) { [string]$pk.kind } else { "mixed" }
      growProfile = if ($pk.growProfile) { [string]$pk.growProfile } else { "" }
      center = @([double]$pk.center[0], [double]$pk.center[1])
      unitCount = if ($null -ne $pk.unitCount) { [int]$pk.unitCount } else { 0 }
      primaryCandidate = [bool]$pk.primaryCandidate
    }
  }
  return [ordered]@{
    enabled = $true
    templateId = [string]$Template.templateId
    source = if ($Template.source) { [string]$Template.source } else { "unknown" }
    teamID = $TeamId
    primaryZoneId = $PrimaryZoneId
    primaryPocketId = $primaryPocket
    unitCount = $units.Count
    units = $units
    pockets = $pockets
  }
}

function Arm-WrathFromRecipe {
  param([string]$Ws, [string]$MapId, [string]$FallbackPack = "armada_gunslinger_response_v1", [int]$MissionNumber = 1)
  $packId = $FallbackPack
  $respSec = 120
  $recipePath = Join-Path $Ws "data\base_templates\$MapId\bake_recipe.json"
  if (Test-Path $recipePath) {
    $bakeRec = Get-Content -Raw -LiteralPath $recipePath | ConvertFrom-Json
    $wd = $bakeRec.wrathDefault
    if (-not $wd -and $bakeRec.characterCard -and $bakeRec.characterCard.wrath) {
      $wd = $bakeRec.characterCard.wrath
    }
    if ($wd) {
      if ($wd.packId) { $packId = [string]$wd.packId }
      if ($wd.responseSeconds) { $respSec = [int]$wd.responseSeconds }
    }
  }
  $wrathPack = Load-WrathPack -Ws $Ws -PackId $packId
  if (-not $wrathPack) { return $null }
  # Playtest: early wrath was ~4x too hot. Delay and thin the pack for first sorties.
  $wrathSoft = if ($MissionNumber -le 1) { 0.25 }
               elseif ($MissionNumber -le 2) { 0.35 }
               elseif ($MissionNumber -le 4) { 0.5 }
               else { 1.0 }
  $respSec = [int][Math]::Max(90, [Math]::Round($respSec / $wrathSoft))
  $units = @($wrathPack.units | ForEach-Object {
    $c = [int][Math]::Max(1, [Math]::Round([int]$_.count * $wrathSoft))
    [ordered]@{ unitDefName = [string]$_.unitDefName; count = $c }
  })
  return [ordered]@{
    enabled = $true
    startOn = "first_contact"
    responseSeconds = $respSec
    packId = [string]$wrathPack.packId
    ephemeral = $true
    telegraph = $true
    telegraphBark = if ($wrathPack.telegraphBark) { [string]$wrathPack.telegraphBark } else { "Contact. Response inbound." }
    scatterElmos = if ($wrathPack.scatterElmos) { [int]$wrathPack.scatterElmos } else { 180 }
    pressureSoft = $wrathSoft
    pack = [ordered]@{
      units = $units
      scatterElmos = if ($wrathPack.scatterElmos) { [int]$wrathPack.scatterElmos } else { 180 }
      telegraphBark = if ($wrathPack.telegraphBark) { [string]$wrathPack.telegraphBark } else { $null }
    }
  }
}

# Kinds that load living-shell occupation when a template exists (outbound 38).
$script:shellCapableKinds = @(
  "eco_raid", "eco_expand", "economy_disrupt",
  "seize_lane", "strike_relay", "hold_plateau",
  "siege", "multipressure", "gate_control", "survive_wilds"
)

function Try-ApplyLivingShell {
  param(
    [string]$Ws,
    [string]$MapId,
    [string]$PrimaryZoneId,
    [string]$Description,
    [double[]]$EnemyCenter,
    [string]$AnchorSide = "Armada"
  )
  $shellPath = Resolve-LivingShellTemplatePath -Ws $Ws -MapId $MapId
  if (-not $shellPath) { return $false }
  try {
    $shellTpl = Get-Content -Raw -LiteralPath $shellPath | ConvertFrom-Json
    $teamID = $script:nextTeam; $script:nextTeam += 1
    $allyID = $script:nextAllyTeam; $script:nextAllyTeam += 1
    $sideName = if ($AnchorSide) { $AnchorSide } else { "Armada" }
    $rgb = if ($FACTION.ContainsKey($sideName)) { $FACTION[$sideName].rgb } else { $FACTION["Armada"].rgb }
    $script:allyTeams += [ordered]@{ id = $allyID; startRect = New-StartRect $EnemyCenter 0.22 }
    $script:teams += [ordered]@{
      id = $teamID; side = $sideName; allyTeam = $allyID
      base = @($EnemyCenter[0], $EnemyCenter[1])
      rgb = $rgb
      label = "$sideName - Living Shell"
      faction = $(if ($sideName -eq "Cortex") { "cortex" } elseif ($sideName -eq "Legion") { "nullmercs" } else { "armada" })
    }
    $script:baseRecipes["shell_anchor"] = @()
    $script:forces += [ordered]@{
      id = "living_shell_anchor"
      label = $Description
      teamID = $teamID
      side = $sideName
      faction = $(if ($sideName -eq "Cortex") { "cortex" } elseif ($sideName -eq "Legion") { "nullmercs" } else { "armada" })
      role = "objective_target"
      zoneId = $PrimaryZoneId
      base = [ordered]@{ x = $EnemyCenter[0]; z = $EnemyCenter[1] }
      recipe = "shell_anchor"
    }
    $script:livingShellPayload = Build-LivingShellFromTemplate -Template $shellTpl -TeamId $teamID -PrimaryZoneId $PrimaryZoneId
    foreach ($pk in @($shellTpl.pockets)) {
      $isPrimary = ($script:livingShellPayload.primaryPocketId -and [string]$pk.pocketId -eq [string]$script:livingShellPayload.primaryPocketId)
      $script:mapOccupation += [ordered]@{
        zoneId = [string]$pk.zoneId
        label = [string]$pk.label
        kind = if ($pk.kind) { [string]$pk.kind } else { "mixed" }
        growProfile = if ($pk.growProfile) { [string]$pk.growProfile } else { "" }
        teamID = $teamID
        preplaced = $true
        primary = [bool]$isPrimary
        pocketId = [string]$pk.pocketId
        livingShell = $true
      }
    }
    $script:wrathPayload = Arm-WrathFromRecipe -Ws $Ws -MapId $MapId -MissionNumber $missionNumber
    if ($script:wrathPayload) {
      Write-Host ("Wrath armed: pack={0} responseSeconds={1} soft={2}" -f `
        $script:wrathPayload.packId, $script:wrathPayload.responseSeconds, $script:wrathPayload.pressureSoft)
    }
    Write-Host ("Living shell: {0} units / {1} pockets from {2}" -f `
      $script:livingShellPayload.unitCount, @($shellTpl.pockets).Count, (Split-Path -Leaf $shellPath))
    return $true
  } catch {
    Write-Host ("Living shell load failed ({0}); falling back." -f $_.Exception.Message)
    return $false
  }
}

# --- Difficulty scaling from campaign state -------------------------------
# expectedEnemyScale.center comes from zone-memory abstract presence; the
# difficulty coefficient already folds the operator dial + softened graph.
# Clarity pass: cap wild zone-memory spikes so the card label stays honest.
$diffCoeff = if ($intent.economy -and $intent.economy.difficultyCoefficient) { [double]$intent.economy.difficultyCoefficient } else { 1.0 }
$difficultyDial = if ($intent.economy -and $null -ne $intent.economy.difficultyDial) { [double]$intent.economy.difficultyDial }
                  elseif ($intent.progression -and $null -ne $intent.progression.difficultyDial) { [double]$intent.progression.difficultyDial }
                  elseif ($state -and $state.progression -and $null -ne $state.progression.difficultyDial) { [double]$state.progression.difficultyDial }
                  else { 1.0 }
$scaleCenter = if ($intent.expectedEnemyScale -and $intent.expectedEnemyScale.center) { [double]$intent.expectedEnemyScale.center } else { 6000.0 }
# Soft-cap zone presence so one bloated map cannot jump to "heavy" by accident.
$scaleCenter = [Math]::Min(11000.0, [Math]::Max(3500.0, $scaleCenter))
# Onboarding ramp: first hours were ~4x too hot (playtest). Soft open, then climb.
$pressureTier = if ($missionNumber -le 1) { 0.25 }
                 elseif ($missionNumber -le 2) { 0.35 }
                 elseif ($missionNumber -le 4) { 0.5 }
                 elseif ($missionNumber -le 7) { 0.75 }
                 else { 1.0 }
$rampFactor = [Math]::Min(1.0, 0.55 + 0.1 * ($missionNumber - 1))
$enemyScale = [Math]::Round(([Math]::Max(0.35, [Math]::Min(2.0, $scaleCenter / 6000.0)) * $diffCoeff * $rampFactor * $pressureTier), 3)
Write-Host ("Pressure soft-open: mission={0} tier={1} ramp={2} → enemyScale={3}" -f $missionNumber, $pressureTier, $rampFactor, $enemyScale)
# Overnight champion craft: enemy_aggro × per-arc scale (app/brain/craft_recipe.json).
$craftStamp = $null
$craftKnobs = $null
$craftPath = Join-Path $Workspace "app\brain\craft_recipe.json"
$campaignCraftPath = Join-Path $Workspace "app\brain\campaign_craft.json"
if (Test-Path $campaignCraftPath) {
  try {
    $cc = Get-Content -Raw -LiteralPath $campaignCraftPath | ConvertFrom-Json
    if ($cc.active -and $cc.knobs) { $craftKnobs = $cc.knobs; $craftStamp = $cc.stamp }
  } catch {}
}
if (-not $craftKnobs -and (Test-Path $craftPath)) {
  try {
    $cr = Get-Content -Raw -LiteralPath $craftPath | ConvertFrom-Json
    if ($cr.knobs) { $craftKnobs = $cr.knobs; $craftStamp = $cr.stamp }
  } catch {}
}
if ($craftKnobs) {
  $arcS = if ($missionNumber -le 5) { [double]$craftKnobs.arc1_scale }
          elseif ($missionNumber -le 10) { [double]$craftKnobs.arc2_scale }
          else { [double]$craftKnobs.arc3_scale }
  if (-not $arcS -or $arcS -le 0) { $arcS = 1.0 }
  $aggro = [double]($craftKnobs.enemy_aggro)
  if (-not $aggro -or $aggro -le 0) { $aggro = 1.0 }
  $arcRamp = 1.0 + 0.03 * [Math]::Max(0, $missionNumber - 5)
  $enemyScale = [Math]::Round([Math]::Min(1.95, [Math]::Max(0.55, $enemyScale * $aggro * $arcS * $arcRamp)), 3)
  Write-Host "CRAFT scale: stamp=$craftStamp aggro=$aggro arcS=$arcS → enemyScale=$enemyScale"
}
# Dev launch: dense player telemetry flag for the campaign gadget.
$devModePath = Join-Path $Workspace "app\brain\dev_mode.json"
$devTelemetry = $false
$devPeriod = 150
if (Test-Path $devModePath) {
  try {
    $dm = Get-Content -Raw -LiteralPath $devModePath | ConvertFrom-Json
    if ($dm.enabled) {
      $devTelemetry = $true
      if ($dm.telemetry -and $dm.telemetry.samplePeriodFrames) {
        $devPeriod = [int]$dm.telemetry.samplePeriodFrames
      }
    }
  } catch {}
}
# Farm sorties (optional XP grind) intentionally run light so power fantasy is clear.
$isFarmSortie = $false
if ($intent.PSObject.Properties["flavor"] -and [string]$intent.flavor -eq "farm_patrol") { $isFarmSortie = $true }
if ($intent.storyTags -and (@($intent.storyTags) -contains "farm")) { $isFarmSortie = $true }
if ($objectiveKind -eq "farm_patrol") { $isFarmSortie = $true }
if ($isFarmSortie) {
  $enemyScale = [Math]::Round([Math]::Max(0.65, $enemyScale * 0.72), 3)
}
# Drop 2 Act 3: massive starting conditions on BOTH sides of the field.
if ($isFinale) {
  $enemyScale = [Math]::Round([Math]::Min(2.6, [Math]::Max(1.35, $enemyScale * 1.6)), 3)
  Write-Host ("Finale scale: kind={0} -> enemyScale={1}" -f $finaleKind, $enemyScale)
}
$maxHazard = if ($intent.offscreenPressureSummary -and $intent.offscreenPressureSummary.maxHazard) { [double]$intent.offscreenPressureSummary.maxHazard } else { 0.0 }
$presenceKind = $objectiveKind -in @("seize_lane", "gate_control")
$mapFamily = if ($intent.environment -and $intent.environment.mapFamily) { [string]$intent.environment.mapFamily } else { "tempo" }

# XP / mode strings (band label recomputed after merc scale just before card).
$xpMode = if ($intent.progression -and $intent.progression.mode) { [string]$intent.progression.mode }
          elseif ($state -and $state.progression -and $state.progression.mode) { [string]$state.progression.mode }
          else { "cracked_farm" }
$xpLine = if ($xpMode -eq "cracked_farm") {
  "XP farm ON - death keeps XP; heroes snowball hard"
} else {
  "XP persists on death (standard rates)"
}
$heroBits = @()
if ($intent.roster -and $intent.roster.heroes) {
  foreach ($hh in @($intent.roster.heroes)) {
    $lvl = if ($null -ne $hh.level) { [int]$hh.level } else { 1 }
    $rnk = if ($hh.rank) { [string]$hh.rank } else { "Runner" }
    $heroBits += ("{0} L{1} {2}" -f [string]$hh.name, $lvl, $rnk)
  }
}
$heroLine = if ($heroBits.Count -gt 0) { "Heroes: " + ($heroBits -join " | ") } else { "" }

# --- The standing war: Null Mercs vs Armada ---------------------------------
# The mercs keep a foothold on every faction-war mission. Reputation decides
# whether their guns tolerate the player (allied) or merely share a target
# (wary, hostile-to-all). Allied mercs tip the field, so the Armada garrison
# scales up slightly to compensate.
$mercInfo = if ($intent.PSObject.Properties["worldConflict"] -and $intent.worldConflict.nullMercs) { $intent.worldConflict.nullMercs } else { $null }
$mercRep = if ($mercInfo -and $null -ne $mercInfo.reputation) { [double]$mercInfo.reputation }
           elseif ($state -and $state.reputation -and $null -ne $state.reputation.nullmercs) { [double]$state.reputation.nullmercs }
           else { 43.0 }
$mercsAllied = if ($mercInfo -and $null -ne $mercInfo.alliedWithPlayer) { [bool]$mercInfo.alliedWithPlayer } else { $mercRep -ge 40.0 }
# Standing scales the merc foothold: allied lines field a fuller camp, wary thinner.
$mercFootholdScale = if ($mercInfo -and $null -ne $mercInfo.footholdScale) { [double]$mercInfo.footholdScale } else { 1.0 }
$mercsPresent = $objectiveKind -ne "hive_clear_or_bypass"
if ($mercsPresent -and $mercsAllied) { $enemyScale = [Math]::Round($enemyScale * 1.1, 3) }
# Drop 4: clamp the final scale into the ladder's authored window. Campaign
# state still moves the needle INSIDE the window; the owner's difficulty dial
# scales the window walls themselves. This kills the mid-campaign plateau
# (zone-memory presence used to pin every act-2 mission at "heavy").
if ($escPlan -and $escPlan.scaleWindow) {
  $escWin = @($escPlan.scaleWindow)
  if ($escWin.Count -ge 2) {
    $escLo = [double]$escWin[0] * $difficultyDial
    $escHi = [double]$escWin[1] * $difficultyDial
    if ($escHi -lt $escLo) { $tmpW = $escLo; $escLo = $escHi; $escHi = $tmpW }
    $preWindow = $enemyScale
    $enemyScale = [Math]::Round([Math]::Min($escHi, [Math]::Max($escLo, $enemyScale)), 3)
    if ($enemyScale -ne $preWindow) {
      Write-Host ("Escalation window: {0} -> {1} (window [{2}, {3}] x dial {4})" -f `
        $preWindow, $enemyScale, $escWin[0], $escWin[1], [Math]::Round($difficultyDial, 2))
    }
  }
}
$fortify = $enemyScale -ge 1.4

# Defenses face the player's approach; patrols defend presence zones or
# pressure the midline on destruction objectives.
$faceX = [Math]::Sign($deployCenter[0] - $enemyCenter[0]); if ($faceX -eq 0) { $faceX = 1 }
$faceZ = [Math]::Sign($deployCenter[1] - $enemyCenter[1]); if ($faceZ -eq 0) { $faceZ = 1 }
$patrolTarget = if ($presenceKind) {
  @($enemyCenter[0], $enemyCenter[1])
} else {
  # Destruction objectives: patrols screen the camp approaches (2/3 toward
  # camp from the midline) rather than camping the middle of the map.
  $midX = ($deployCenter[0] + $enemyCenter[0]) / 2.0
  $midZ = ($deployCenter[1] + $enemyCenter[1]) / 2.0
  @((($midX + 2.0 * $enemyCenter[0]) / 3.0), (($midZ + 2.0 * $enemyCenter[1]) / 3.0))
}

function Clamp01 { param([double]$V) return [Math]::Max(0.03, [Math]::Min(0.97, $V)) }

# --- Camp assembly ---------------------------------------------------------
# Each camp -> one team on its own allyteam (contractor centerpieces share the
# garrison's allyteam). Camps carry a small objective-tagged centerpiece force
# plus an untagged garrison shell. Teams carry an explicit faction tag so
# telemetry reads the world war (nullmercs/armada/cortex), not the chassis.
$roster = if ($intent.PSObject.Properties["roster"] -and $intent.roster) { $intent.roster } else { $null }
$commerce = if ($intent.PSObject.Properties["commerce"] -and $intent.commerce) { $intent.commerce } else { $null }
$resourceMod = if ($intent.economy -and $null -ne $intent.economy.resourceModifier) { [double]$intent.economy.resourceModifier } else { 1.0 }
# arcProfile already computed early (adjacency + flavor). Kit follows it.
$strikeDoctrine = ([int]$arcProfile.playerCommanders -le 0) -or ($objectiveKind -eq "eco_raid")
# Drop 2: act 2+ is base-building doctrine even on raid contracts; act 3 is the
# finale kit (massive start).
if ($actNum -ge 2) { $strikeDoctrine = $false }
if ($actNum -ge 3 -or $isFinale) {
  $playerKit = New-FinaleKitFromRoster $mapFamily $roster $resourceMod $commerce
} elseif ($actNum -ge 2 -and $roster) {
  $playerKit = New-PlayerKitFromRoster $mapFamily $roster $resourceMod $commerce
} elseif ($objectiveKind -eq "eco_raid" -and $actNum -le 1) {
  $playerKit = New-StrikeTeam $roster $resourceMod $commerce
} elseif ($strikeDoctrine) {
  $playerKit = New-TacticsPlayerKit $mapFamily $roster $resourceMod $arcProfile.unitPrinter $commerce
} elseif ($roster) {
  $playerKit = New-PlayerKitFromRoster $mapFamily $roster $resourceMod $commerce
} else {
  $playerKit = New-PlayerKit $mapFamily
  $playerKit = Add-CommerceDeployToKit $playerKit $commerce
}
if ($commerce) {
  $tnb = if ($null -ne $commerce.tenebrium) { $commerce.tenebrium } else { 0 }
  $scr = if ($null -ne $commerce.credits) { $commerce.credits } else { 0 }
  $depN = if ($commerce.deploy) { @($commerce.deploy).Count } else { 0 }
  Write-Host ("Commerce: Tenebrium={0} credits={1} deployables={2}" -f $tnb, $scr, $depN)
}
# Chassis side stays Legion (BAR unit tree); presentation is Ashwalkers.
$baseRecipes = [ordered]@{ ashwalker_player_kit = @($playerKit); legion_player_kit = @($playerKit) }
# Final band after merc / farm modifiers so the card matches the field.
$diffBand = if ($enemyScale -ge 1.6) { "heavy" } elseif ($enemyScale -ge 1.2) { "reinforced" } elseif ($enemyScale -le 0.85) { "light" } else { "standard" }
$difficultyLine = "Expected opposition: $diffBand (scale $enemyScale) | dial $([Math]::Round($difficultyDial, 2))"
if ($isFarmSortie) { $difficultyLine = "$difficultyLine | FARM SORTIE (bonus XP, lighter camp)" }
$missionCard = New-MissionCard $intent $arcProfile $map.title $description `
  ([string]$intent.deploymentZoneId) $targetZoneId ([string]$intent.extractionZoneId) `
  -DifficultyLine $difficultyLine -XpLine $xpLine -HeroLine $heroLine
# G4: stamp hub C&C language onto the in-BAR briefing card
if ($intent.hubChoiceId -or $intent.captureZoneIds -or $intent.deployAces) {
  $capBits = @()
  if ($intent.captureZoneIds) { $capBits = @($intent.captureZoneIds) }
  $secBits = @()
  if ($intent.secondaryCaptureZoneIds) { $secBits = @($intent.secondaryCaptureZoneIds) }
  $aceBits = @()
  if ($intent.deployAces) { $aceBits = @($intent.deployAces) }
  $hubLine = "Hub board: primary $($targetZoneId)"
  if ($secBits.Count -gt 0) { $hubLine = "$hubLine · secondary $($secBits -join ', ')" }
  if ($aceBits.Count -gt 0) { $hubLine = "$hubLine · aces $($aceBits -join '+')" }
  if ($intent.hubChoiceId) { $hubLine = "$hubLine · choice $($intent.hubChoiceId)" }
  if ($missionCard -is [hashtable] -or $missionCard -is [System.Collections.IDictionary] -or $missionCard.PSObject) {
    try {
      if ($missionCard.situation) {
        $missionCard.situation = "$($missionCard.situation)  |  $hubLine"
      } else {
        $missionCard | Add-Member -NotePropertyName situation -NotePropertyValue $hubLine -Force
      }
      $missionCard | Add-Member -NotePropertyName hubLine -NotePropertyValue $hubLine -Force
    } catch {
      # OrderedDictionary path
      $missionCard["hubLine"] = $hubLine
      if ($missionCard.Contains("situation")) {
        $missionCard["situation"] = "$($missionCard['situation'])  |  $hubLine"
      }
    }
  }
}
Write-Host ("Arc profile: id={0} playerCommanders={1} enemyMode={2} allyPower={3} escalation={4} ai={5} flavor={6}" -f `
  $arcProfile.id, $arcProfile.playerCommanders, $arcProfile.enemyMode, $arcProfile.allyPower, $arcProfile.escalation, $arcProfile.enemyAI, $arcProfile.flavor)
# WO-036: enemy AI shortName for startscript
# Greenest Fields Armada: SimpleDefenderAI — hold the works, don't roam-deathball.
function Get-EnemyAiShortName {
  if ([string]$arcProfile.enemyAI -eq "barbarian") { return "BARb" }
  if ([string]$arcProfile.enemyAI -in @("defender", "simple_defender", "SimpleDefenderAI")) {
    return "SimpleDefenderAI"
  }
  if ($mapId -eq "greenest_fields") { return "SimpleDefenderAI" }
  return "SimpleAI"
}
$enemyAiShort = Get-EnemyAiShortName
Write-Host ("Enemy AI shortName: {0} (map={1} profile={2})" -f $enemyAiShort, $mapId, $arcProfile.enemyAI)
$allyTeams = @([ordered]@{ id = 0; startRect = New-StartRect $deployCenter 0.20 })
$teams = @([ordered]@{ id = 0; side = "Legion"; allyTeam = 0; base = @($deployCenter[0], $deployCenter[1]); rgb = @(0.25, 0.85, 0.35); label = "Ashwalkers"; faction = "ashwalkers" })
$forces = @([ordered]@{ id = "player_deployment"; label = "Ashwalker drop - $($intent.deploymentZoneId)"; teamID = 0; side = "Legion"; faction = "ashwalkers"; role = "player_anchor"; base = [ordered]@{ x = $deployCenter[0]; z = $deployCenter[1] }; recipe = "ashwalker_player_kit" })
$ai = @()
$alliances = @()
$nextTeam = 1
$nextAllyTeam = 1

function Add-FactionCamp {
  param([string]$Side, [double[]]$Center, $CenterpieceSpecs, [string]$CenterpieceLabel, [bool]$WithEco = $true, [bool]$WithProduction = $false, [bool]$WithJammers = $false, $SupportSpecs = $null, [bool]$FrontBand = $false)
  # A camp is ONE faction end to end - Armada and Cortex are mortal enemies and
  # never share a team or allyteam. The centerpiece (objective) and its garrison
  # are the same side.
  $T = $FACTION[$Side]
  $teamID = $script:nextTeam; $script:nextTeam += 1
  $allyID = $script:nextAllyTeam; $script:nextAllyTeam += 1
  $script:allyTeams += [ordered]@{ id = $allyID; startRect = New-StartRect $Center 0.20 }
  $script:teams += [ordered]@{ id = $teamID; side = $Side; allyTeam = $allyID; base = @($Center[0], $Center[1]); rgb = $T.rgb; label = "$Side - $CenterpieceLabel"; faction = $Side.ToLower() }

  if ($CenterpieceSpecs) {
    $coreRecipe = "camp${teamID}_core"
    $script:baseRecipes[$coreRecipe] = @($CenterpieceSpecs)
    $script:forces += [ordered]@{ id = "camp${teamID}_objective"; label = $CenterpieceLabel; teamID = $teamID; side = $Side; faction = $Side.ToLower(); role = "objective_target"; base = [ordered]@{ x = $Center[0]; z = $Center[1] }; recipe = $coreRecipe }
  }

  # WO-034: static_bases never get production labs (SimpleAI + labs = commander soup).
  $allowProd = $WithProduction -and ($arcProfile.allowEnemyProduction -eq $true)
  # Drop 3: warband doctrine (act-1 ground control) thins the static shell hard
  # and beefs the roving patrols — the camp reads as a war party's foothold.
  $warband = ([string]$arcProfile.enemyMode -eq "warband")
  $garrison = @()
  if ($SupportSpecs) { $garrison += @($SupportSpecs) }
  # WO-004: front-band camps keep light eco (worth exploding) but thinner teeth.
  if ($WithEco) { $garrison += Ring-Eco $T ($(if ($warband) { [Math]::Max(0.45, $enemyScale * 0.55) } elseif ($FrontBand) { [Math]::Max(0.55, $enemyScale * 0.75) } else { $enemyScale })) }
  $garrison += Ring-Perimeter $T ($(if ($warband) { [Math]::Max(0.5, $enemyScale * 0.55) } elseif ($FrontBand) { [Math]::Max(0.6, $enemyScale * 0.8) } else { $enemyScale })) $faceX $faceZ
  if ($allowProd) { $garrison += Ring-Production $T }
  if ($WithJammers) { $garrison += Ring-Jammers $T }
  $patrolScale = if ($warband) { $enemyScale * 1.5 } else { $enemyScale }
  if ($FrontBand -and -not $warband) {
    $garrison += Ring-Patrol $T $patrolScale $patrolTarget[0] $patrolTarget[1] -FrontBand
  } else {
    $garrison += Ring-Patrol $T $patrolScale $patrolTarget[0] $patrolTarget[1]
  }
  if ($fortify -and -not $FrontBand -and -not $warband) { $garrison += Ring-Fortify $T $faceX $faceZ }
  $garrisonRecipe = "camp${teamID}_garrison"
  $script:baseRecipes[$garrisonRecipe] = @($garrison)
  # Drop 4 raze strength: on the PRIMARY camp the whole garrison joins the
  # objective book — the mission is "leave nothing of this camp standing",
  # not a surgical centerpiece strike. (Pool semantics in the gadget already
  # require every tagged unit down for destruction kinds.)
  $garrisonRole = "garrison"
  if ($objectiveStrength -eq "raze" -and $null -eq $script:primaryEnemyTeamID) {
    $garrisonRole = "objective_target"
    Write-Host ("RAZE: {0} camp garrison joins the objective book (team {1})." -f $Side, $teamID)
  }
  $script:forces += [ordered]@{ id = "camp${teamID}_garrison"; label = "$Side garrison"; teamID = $teamID; side = $Side; faction = $Side.ToLower(); role = $garrisonRole; base = [ordered]@{ x = $Center[0]; z = $Center[1] }; recipe = $garrisonRecipe }

  $aiName = switch ($enemyAiShort) {
    "BARb" { "BARb($Side $CenterpieceLabel)" }
    "SimpleDefenderAI" { "SimpleDefender($Side $CenterpieceLabel)" }
    default { "SimpleAI($Side $CenterpieceLabel)" }
  }
  $script:ai += [ordered]@{ name = $aiName; shortName = $enemyAiShort; team = $teamID; version = "<not-versioned>" }
  # Drop 3: the first faction camp anchors roving warband packs (act 1).
  if ($null -eq $script:primaryEnemyTeamID) { $script:primaryEnemyTeamID = $teamID; $script:primaryEnemySide = $Side }
}

function Add-RaptorCamp {
  param([double[]]$Center, [bool]$AsObjective, [string]$Label)
  $teamID = $script:nextTeam; $script:nextTeam += 1
  $allyID = $script:nextAllyTeam; $script:nextAllyTeam += 1
  $script:allyTeams += [ordered]@{ id = $allyID; startRect = New-StartRect $Center 0.18 }
  $script:teams += [ordered]@{ id = $teamID; side = "Armada"; allyTeam = $allyID; base = @($Center[0], $Center[1]); rgb = @(0.78, 0.14, 0.92); label = $Label; faction = "wild" }
  if ($AsObjective) {
    $script:baseRecipes["camp${teamID}_hives"] = @(Centerpiece-Hives $maxHazard)
    $script:forces += [ordered]@{ id = "camp${teamID}_objective"; label = $Label; teamID = $teamID; side = "Raptors"; faction = "wild"; role = "objective_target"; base = [ordered]@{ x = $Center[0]; z = $Center[1] }; recipe = "camp${teamID}_hives" }
  }
  $script:baseRecipes["camp${teamID}_swarm"] = @(Ring-RaptorGarrison $maxHazard)
  $script:forces += [ordered]@{ id = "camp${teamID}_swarm"; label = "Raptor swarm"; teamID = $teamID; side = "Raptors"; faction = "wild"; role = $(if ($AsObjective) { "garrison" } else { "wild_pressure" }); base = [ordered]@{ x = $Center[0]; z = $Center[1] }; recipe = "camp${teamID}_swarm" }
  $script:ai += [ordered]@{ name = "RaptorsDefenseAI(Verdance)"; shortName = "RaptorsAI"; team = $teamID; version = "<not-versioned>" }
}

function Add-NullMercCamp {
  param([double[]]$Center, [double]$Scale, [bool]$Allied)
  $teamID = $script:nextTeam; $script:nextTeam += 1
  $allyID = $script:nextAllyTeam; $script:nextAllyTeam += 1
  $script:allyTeams += [ordered]@{ id = $allyID; startRect = New-StartRect $Center 0.16 }
  $script:teams += [ordered]@{ id = $teamID; side = "Legion"; allyTeam = $allyID; base = @($Center[0], $Center[1]); rgb = $MERC.rgb; label = "Null Mercs foothold"; faction = "nullmercs" }
  $mfx = [Math]::Sign($enemyCenter[0] - $Center[0]); if ($mfx -eq 0) { $mfx = 1 }
  $mfz = [Math]::Sign($enemyCenter[1] - $Center[1]); if ($mfz -eq 0) { $mfz = 1 }
  $allyP = if ($null -ne $arcProfile.allyPower) { [double]$arcProfile.allyPower } else { 1.0 }
  $script:baseRecipes["camp${teamID}_mercs"] = @(New-MercFoothold $Scale $patrolTarget[0] $patrolTarget[1] $mfx $mfz $allyP)
  $script:forces += [ordered]@{ id = "camp${teamID}_mercs"; label = "Null Mercs foothold"; teamID = $teamID; side = "Legion"; faction = "nullmercs"; role = "merc_foothold"; base = [ordered]@{ x = $Center[0]; z = $Center[1] }; recipe = "camp${teamID}_mercs" }
  $script:ai += [ordered]@{ name = "SimpleAI(Null Mercs)"; shortName = "SimpleAI"; team = $teamID; version = "<not-versioned>" }
  if ($Allied) {
    $script:alliances += [ordered]@{ allyTeamA = 0; allyTeamB = $allyID; allied = $true }
  }
}

function Add-WarbandPacks {
  # Drop 3 act-1 texture: roving enemy strike packs sweeping the deploy->target
  # axis. They ride the PRIMARY enemy camp's team (no new allyteam, no extra AI)
  # so the map reads warband-vs-warband without faction-vs-itself accidents.
  param([double[]]$From, [double[]]$To, [double]$Scale)
  if ($null -eq $script:primaryEnemyTeamID -or -not $script:primaryEnemySide) { return }
  # NOTE: PowerShell variables are case-insensitive — nothing in this function
  # may be named $t or it clobbers the faction table.
  $T = $FACTION[$script:primaryEnemySide]
  if (-not $T) { return }
  $axisX = $To[0] - $From[0]; $axisZ = $To[1] - $From[1]
  $len = [Math]::Sqrt($axisX * $axisX + $axisZ * $axisZ); if ($len -lt 0.001) { $len = 0.001 }
  $perpX = -$axisZ / $len; $perpZ = $axisX / $len
  $i = 0
  foreach ($p in @(@(0.42, 0.10), @(0.68, -0.10))) {
    $frac = [double]$p[0]; $off = [double]$p[1]
    $cx = Clamp01 ($From[0] + $axisX * $frac + $perpX * $off)
    $cz = Clamp01 ($From[1] + $axisZ * $frac + $perpZ * $off)
    # Sweep back toward the deploy approach so packs cross the player's path.
    $swx = Clamp01 ($From[0] + $axisX * ($frac - 0.2))
    $swz = Clamp01 ($From[1] + $axisZ * ($frac - 0.2))
    $specs = @(
      (Spec $T.raider (Get-ScaledCount 4 $Scale) 60 -60 80 -Patrol (PatrolSweep $swx $swz)),
      (Spec $T.skirm (Get-ScaledCount 3 $Scale) -70 40 90 -Patrol (PatrolSweep $cx $cz)),
      (Spec $T.assault (Get-ScaledCount 2 $Scale) 0 100 95 -Patrol (PatrolSweep $swx $swz)),
      (Spec $T.radar 1 0 0 100),
      (Spec $T.wall 3 40 70 40)
    )
    $rid = "warband_pack_$i"
    $script:baseRecipes[$rid] = @($specs)
    $script:forces += [ordered]@{
      id = $rid; label = "$($script:primaryEnemySide) warband"; teamID = $script:primaryEnemyTeamID
      side = $script:primaryEnemySide; faction = $script:primaryEnemySide.ToLower(); role = "warband"
      base = [ordered]@{ x = $cx; z = $cz }; recipe = $rid
    }
    $i += 1
  }
  Write-Host ("Warband packs: {0} roving enemy packs on the {1} axis." -f $i, $script:primaryEnemySide)
}

function Add-DefectorCamp {
  # Drop 3 finale dressing: availableAllies defectors become a real allied team
  # on the player's flank — grey-tinted hulls of the empire they walked out of.
  param([string]$Side, [double[]]$Center, [double]$Scale)
  $T = $FACTION[$Side]
  if (-not $T) { return }
  $teamID = $script:nextTeam; $script:nextTeam += 1
  $allyID = $script:nextAllyTeam; $script:nextAllyTeam += 1
  $label = if ($Side -eq "Cortex") { "Cortex defectors" } else { "Armada deserters" }
  $script:allyTeams += [ordered]@{ id = $allyID; startRect = New-StartRect $Center 0.14 }
  $script:teams += [ordered]@{ id = $teamID; side = $Side; allyTeam = $allyID; base = @($Center[0], $Center[1]); rgb = @(0.55, 0.55, 0.5); label = $label; faction = "$($Side.ToLower())_defectors" }
  $specs = @(
    (Spec $T.raider (Get-ScaledCount 4 $Scale) 80 -60 80 -Patrol (PatrolSweep $patrolTarget[0] $patrolTarget[1])),
    (Spec $T.skirm (Get-ScaledCount 3 $Scale) -80 40 90 -Patrol (PatrolSweep $patrolTarget[0] $patrolTarget[1])),
    (Spec $T.assault (Get-ScaledCount 2 $Scale) 0 100 95),
    (Spec $T.radar 1 0 -60 100),
    (Spec $T.aa 1 60 60 150)
  )
  $script:baseRecipes["camp${teamID}_defectors"] = @($specs)
  $script:forces += [ordered]@{ id = "camp${teamID}_defectors"; label = $label; teamID = $teamID; side = $Side; faction = "$($Side.ToLower())_defectors"; role = "defector_allies"; base = [ordered]@{ x = $Center[0]; z = $Center[1] }; recipe = "camp${teamID}_defectors" }
  $script:ai += [ordered]@{ name = "SimpleAI($label)"; shortName = "SimpleAI"; team = $teamID; version = "<not-versioned>" }
  $script:alliances += [ordered]@{ allyTeamA = 0; allyTeamB = $allyID; allied = $true }
  Write-Host ("Defector allies: {0} stand with the clans this finale." -f $label)
}

function Add-SecondaryObjectiveCamp {
  # Drop 4 escalation: a side mark on the board. Small works (the mark itself,
  # role=objective_secondary — the gadget books these into their own ledger)
  # behind a light garrison. Rides its own team; the end-of-camps pact sweep
  # allies it with the primary camp via its faction label.
  param([string]$Side, [double[]]$Center, [double]$Scale, [string]$SecondaryId, [bool]$Required, [string]$Label)
  $T = $FACTION[$Side]
  if (-not $T) { return $null }
  $teamID = $script:nextTeam; $script:nextTeam += 1
  $allyID = $script:nextAllyTeam; $script:nextAllyTeam += 1
  $kindWord = if ($Required) { "Objective" } else { "Bonus mark" }
  $campLabel = "{0} - {1}" -f $kindWord, $Label
  $script:allyTeams += [ordered]@{ id = $allyID; startRect = New-StartRect $Center 0.12 }
  $script:teams += [ordered]@{ id = $teamID; side = $Side; allyTeam = $allyID; base = @($Center[0], $Center[1]); rgb = $T.rgb; label = $campLabel; faction = $Side.ToLower() }
  # The mark: a relay works the player must wreck (all of it).
  $works = @(
    (Spec $T.radar 1 0 0 100),
    (Spec $T.solar 2 -70 60 90),
    (Spec $T.hlt 1 70 -50 110)
  )
  # Teeth + a patrol pair; support hardware, NOT part of the mark.
  $guard = @(
    (Spec $T.llt 2 -90 -70 120),
    (Spec $T.wall 3 100 80 130),
    (Spec $T.raider (Get-ScaledCount 3 $Scale) 40 130 85 -Patrol (PatrolSweep $Center[0] $Center[1])),
    (Spec $T.skirm (Get-ScaledCount 2 $Scale) -40 -130 90)
  )
  $script:baseRecipes["sec${teamID}_works"] = @($works)
  $script:baseRecipes["sec${teamID}_guard"] = @($guard)
  $script:forces += [ordered]@{ id = "sec${teamID}_works"; label = $campLabel; teamID = $teamID; side = $Side; faction = $Side.ToLower(); role = "objective_secondary"; secondaryId = $SecondaryId; required = [bool]$Required; base = [ordered]@{ x = $Center[0]; z = $Center[1] }; recipe = "sec${teamID}_works" }
  $script:forces += [ordered]@{ id = "sec${teamID}_guard"; label = "$campLabel guard"; teamID = $teamID; side = $Side; faction = $Side.ToLower(); role = "garrison"; base = [ordered]@{ x = $Center[0]; z = $Center[1] }; recipe = "sec${teamID}_guard" }
  $script:ai += [ordered]@{ name = "SimpleAI($campLabel)"; shortName = "SimpleAI"; team = $teamID; version = "<not-versioned>" }
  Write-Host ("Secondary objective: {0} ({1}) at ({2:n2}, {3:n2})" -f $SecondaryId, $(if ($Required) { "REQUIRED" } else { "bonus" }), $Center[0], $Center[1])
  return [ordered]@{ id = $SecondaryId; label = $Label; required = [bool]$Required; x = $Center[0]; z = $Center[1]; teamID = $teamID }
}

function New-RehydrateSpecs {
  # Drop 3 finale dressing: turn a persistent-base snapshot (zone telemetry's
  # unitCountsByDef) back into placeable specs. Approximate by design — top
  # defs only, per-def and total caps, faction-prefix filtered so a bloc never
  # spawns another bloc's hardware.
  param($Snapshot, [string]$Prefix)
  if (-not $Snapshot -or -not $Snapshot.PSObject.Properties["teams"] -or -not $Snapshot.teams) { return @() }
  $counts = @{}
  foreach ($snapTeam in @($Snapshot.teams)) {
    if (-not $snapTeam -or -not $snapTeam.PSObject.Properties["unitCountsByDef"] -or -not $snapTeam.unitCountsByDef) { continue }
    foreach ($p in $snapTeam.unitCountsByDef.PSObject.Properties) {
      $def = [string]$p.Name
      if (-not $def.StartsWith($Prefix)) { continue }
      $n = 0; try { $n = [int]$p.Value } catch { $n = 0 }
      if ($n -le 0) { continue }
      if ($counts.ContainsKey($def)) { $counts[$def] = [int]$counts[$def] + $n } else { $counts[$def] = $n }
    }
  }
  if ($counts.Count -eq 0) { return @() }
  $specs = @(); $phase = 0; $total = 0
  foreach ($def in @($counts.Keys | Sort-Object { -[int]$counts[$_] } | Select-Object -First 10)) {
    $n = [Math]::Min(6, [int]$counts[$def])
    if ($total + $n -gt 30) { $n = 30 - $total }
    if ($n -le 0) { break }
    $specs += Scatter $def $n 420 2 $phase 70
    $phase += 2; $total += $n
  }
  return $specs
}

# OCCUPATION MODEL LOCK (outbound 44): living shell + decoy + scars is the ONE path.
# Hand-scattered mapOccupation camps are deprecated fallback when no template exists.
# Prefer living-shell occupation for all shell-capable kinds (outbound 37/38/44).
$usedShell = $false
if ($script:shellCapableKinds -contains $objectiveKind) {
  $anchorSide = $enemySide
  if ($objectiveKind -eq "eco_raid" -or $objectiveKind -eq "eco_expand") { $anchorSide = "Armada" }
  if ($objectiveKind -eq "survive_wilds") { $anchorSide = "Legion" }
  if (([string]$intent.mapId) -eq "eye_of_horus" -and $objectiveKind -eq "strike_relay") { $anchorSide = "Cortex" }
  if (([string]$intent.mapId) -eq "ancient_bastion") { $anchorSide = "Armada" }
  $usedShell = Try-ApplyLivingShell -Ws $Workspace -MapId ([string]$intent.mapId) `
    -PrimaryZoneId $targetZoneId -Description $description -EnemyCenter $enemyCenter -AnchorSide $anchorSide
}

# Drop 2 finale setpieces: authored camps keyed by path (no living shell —
# these are designed closing battles, not procedural occupation).
if ($isFinale) {
  switch ($finaleKind) {
    "sovereignty" {
      # Break BOTH empires: two fortified command posts on their authored ground.
      $armZone = Get-ZoneById $zoneMap "ATS_NE_ARMADA_RIDGE"
      $corZone = Get-ZoneById $zoneMap "ATS_SE_CORTEX_BASIN"
      $armC = Get-ZoneCenter $armZone @((Clamp01 ($enemyCenter[0] - 0.14)), (Clamp01 ($enemyCenter[1] - 0.08)))
      $corC = Get-ZoneCenter $corZone @((Clamp01 ($enemyCenter[0] + 0.14)), (Clamp01 ($enemyCenter[1] + 0.10)))
      Add-FactionCamp "Armada" $armC (Centerpiece-CommandPost $FACTION["Armada"]) "Armada command post" -WithEco $true -WithProduction $true -SupportSpecs (Support-Relay $FACTION["Armada"])
      Add-FactionCamp "Cortex" $corC (Centerpiece-CommandPost $FACTION["Cortex"]) "Cortex command post" -WithEco $true -WithProduction $true -WithJammers $true -SupportSpecs (Support-Relay $FACTION["Cortex"])
    }
    "spire_jump" {
      # Burn the hive heart; a deep nest keeps the pressure honest.
      Add-RaptorCamp $enemyCenter $true $description
      $nestC = @((Clamp01 ($enemyCenter[0] + 0.18)), (Clamp01 ($enemyCenter[1] - 0.16)))
      Add-RaptorCamp $nestC $false "Raptor deep nest"
    }
    default {
      # overthrow: the citadel — LRPC crown plus a command post wing; both are
      # objective targets, so the finale requires breaking the whole spine.
      $T = $FACTION[$enemySide]
      Add-FactionCamp $enemySide $enemyCenter (Centerpiece-LRPC $T) $description -WithEco $true -WithProduction $true -SupportSpecs (Support-LRPC $T)
      $postC = @((Clamp01 ($enemyCenter[0] - 0.14)), (Clamp01 ($enemyCenter[1] + 0.12)))
      Add-FactionCamp $enemySide $postC (Centerpiece-CommandPost $T) "Citadel command post" -WithEco $true -WithProduction $true
    }
  }
} else {
switch ($objectiveKind) {
  "strike_relay" {
    if (-not $usedShell) {
      # The dealer relay sits in a desolate Cortex hideout: jammers everywhere.
      $T = $FACTION[$enemySide]
      $jam = $enemySide -eq "Cortex"
      Add-FactionCamp $enemySide $enemyCenter (Centerpiece-Relay $T) $description -WithEco $true -WithJammers $jam -SupportSpecs (Support-Relay $T) -FrontBand $frontBand
    }
  }
  "destroy_key_structure" {
    $T = $FACTION[$enemySide]
    Add-FactionCamp $enemySide $enemyCenter (Centerpiece-LRPC $T) $description -WithEco $true -WithProduction $true -SupportSpecs (Support-LRPC $T) -FrontBand $frontBand
  }
  "economy_disrupt" {
    if (-not $usedShell) {
      $T = $FACTION[$enemySide]
      Add-FactionCamp $enemySide $enemyCenter (Centerpiece-EcoWorks $T $enemyScale) $description -WithEco $true -FrontBand $frontBand
    }
  }
  "eco_raid" {
    # Living-shell doctrine (outbound 37/44): frozen AI-grown template is required path.
    # Fallback = hand-scattered occupation pockets (36) — DEPRECATED, log loudly.
    if (-not $usedShell) {
      Write-Warning "OCCUPATION FALLBACK: no living shell for $(([string]$intent.mapId))/$objectiveKind — using deprecated hand camps."
      $parsed = if ($intent.enemyInfrastructure -and $intent.enemyInfrastructure.parsed) { $intent.enemyInfrastructure.parsed.armada } else { $null }
      $primaryNode = Add-EcoSprawlCamp $enemyCenter $parsed $enemyScale $faceX $faceZ $description -ZoneId $targetZoneId -Flavor "mixed"
      if ($primaryNode) { $script:mapOccupation += $primaryNode }

      if ($missionNumber -le 8 -and $zoneMap -and $zoneMap.zones) {
        $occupiedIds = @{ $targetZoneId = $true; $deployZoneId = $true }
        $pocketFlavors = @("wind", "solar", "mixed")
        $pi = 0
        foreach ($z in @($zoneMap.zones)) {
          $zid = [string]$z.zoneId
          if (-not $zid -or $occupiedIds.ContainsKey($zid)) { continue }
          $tags = @()
          if ($z.tags) { $tags = @($z.tags | ForEach-Object { [string]$_ }) }
          $role = if ($z.role) { [string]$z.role } else { "" }
          $isEco = ($tags -contains "wind") -or ($tags -contains "solar") -or ($tags -contains "economy") -or ($tags -contains "energy") `
            -or ($role -eq "energy_edge") -or ($role -eq "main_field")
          $isStart = ($tags -contains "start") -or ($tags -contains "staging") -or ($role -eq "legion_start")
          if ($isStart -or -not $isEco) { continue }
          $zc = Get-ZoneCenter $z $null
          if (-not $zc) { continue }
          $ddx = $zc[0] - $deployCenter[0]; $ddz = $zc[1] - $deployCenter[1]
          if (($ddx * $ddx + $ddz * $ddz) -lt (0.12 * 0.12)) { continue }
          $flavor = $pocketFlavors[$pi % $pocketFlavors.Count]
          $pi += 1
          $pfx = [Math]::Sign($deployCenter[0] - $zc[0]); if ($pfx -eq 0) { $pfx = 1 }
          $pfz = [Math]::Sign($deployCenter[1] - $zc[1]); if ($pfz -eq 0) { $pfz = 1 }
          $label = if ($z.label) { [string]$z.label } else { $zid }
          $node = Add-EcoSprawlCamp $zc $parsed ([Math]::Max(0.55, $enemyScale * 0.7)) $pfx $pfz $label -OccupationOnly -ZoneId $zid -Flavor $flavor
          if ($node) {
            $script:mapOccupation += $node
            $occupiedIds[$zid] = $true
          }
          if ($script:mapOccupation.Count -ge 4) { break }
        }
        Write-Host ("Occupied map: {0} Armada eco nodes pre-placed (primary + pockets)." -f $script:mapOccupation.Count)
      }
      $script:wrathPayload = Arm-WrathFromRecipe -Ws $Workspace -MapId ([string]$intent.mapId)
      if ($script:wrathPayload) {
        Write-Host ("Wrath armed: pack={0} responseSeconds={1}" -f $script:wrathPayload.packId, $script:wrathPayload.responseSeconds)
      }
    }
  }
  "hive_clear_or_bypass" {
    Add-RaptorCamp $enemyCenter $true $description
  }
  "choose_target_then_extract" {
    # Two rival faction camps flanking the contested center; they are on
    # separate allyteams and will pressure each other while you choose.
    $armadaCenter = @((Clamp01 ($enemyCenter[0] - 0.16)), (Clamp01 ($enemyCenter[1] - 0.05)))
    $cortexCenter = @((Clamp01 ($enemyCenter[0] + 0.16)), (Clamp01 ($enemyCenter[1] + 0.08)))
    Add-FactionCamp "Armada" $armadaCenter (Centerpiece-CommandPost $FACTION["Armada"]) "Armada command post" -WithEco $true
    Add-FactionCamp "Cortex" $cortexCenter (Centerpiece-CommandPost $FACTION["Cortex"]) "Cortex forward works" -WithEco $true
  }
  default {
    # Presence objectives (seize_lane / gate_control / siege): shell preferred above.
    # Fallback = thin front-band garrison + reinforcement packs (WO-004).
    if (-not $usedShell) {
      $T = $FACTION[$enemySide]
      Add-FactionCamp $enemySide $enemyCenter $null $description -WithEco $false -FrontBand $true
    }
  }
}
}

# Drop 3 act-1 texture: roving warband packs on the approach axis.
if (-not $isFinale -and [string]$arcProfile.enemyMode -eq "warband") {
  Add-WarbandPacks $deployCenter $enemyCenter ([Math]::Max(0.6, $enemyScale * 0.8))
}

# Drop 4 escalation: secondary-objective camps at the plan's resolved zones.
# Skip anything that collides with the deploy/target zones or lacks a center.
if ($escSecondaries.Count -gt 0 -and -not $isFinale -and $zoneMap -and $zoneMap.zones) {
  $secSide = if ($script:primaryEnemySide) { [string]$script:primaryEnemySide } else { $enemySide }
  foreach ($sec in $escSecondaries) {
    if (-not $sec -or -not $sec.zoneId) { continue }
    $secZid = [string]$sec.zoneId
    if ($secZid -eq $targetZoneId -or $secZid -eq $deployZoneId) { continue }
    $secZone = @($zoneMap.zones) | Where-Object { [string]$_.zoneId -eq $secZid } | Select-Object -First 1
    if (-not $secZone) { continue }
    $secCenter = Get-ZoneCenter $secZone $null
    if (-not $secCenter) { continue }
    $secLabel = if ($sec.label) { [string]$sec.label } else { $secZid }
    $secId = if ($sec.id) { [string]$sec.id } else { "sec_" + $secZid.ToLower() }
    $secMeta = Add-SecondaryObjectiveCamp $secSide $secCenter ([Math]::Max(0.4, $enemyScale * 0.5)) $secId ([bool]$sec.required) $secLabel
    if ($secMeta) {
      $secMeta.zoneId = $secZid
      $script:secondaryMeta += $secMeta
    }
  }
}

# Drop 3 finale dressing: persistent-base snapshots walk back onto the field.
# Player-bloc zones return as standing team-0 bases; empire zones as thin
# static camps on the primary enemy team. Deploy/target zones stay untouched.
if ($isFinale -and $intent.PSObject.Properties["persistentBaseRehydrate"] -and $intent.persistentBaseRehydrate) {
  $rehydrated = 0
  foreach ($entry in @($intent.persistentBaseRehydrate)) {
    if ($rehydrated -ge 3) { break }
    if (-not $entry -or -not $entry.zoneId) { continue }
    $zid = [string]$entry.zoneId
    if ($zid -eq $deployZoneId -or $zid -eq $targetZoneId) { continue }
    $zone = Get-ZoneById $zoneMap $zid
    if (-not $zone) { continue }
    $zc = Get-ZoneCenter $zone $null
    if (-not $zc) { continue }
    $ctrl = [string]$entry.control
    if ($ctrl -in @("nullmercs", "ashwalkers")) {
      $specs = New-RehydrateSpecs $entry.snapshot "leg"
      if (@($specs).Count -eq 0) { continue }
      $rid = "rehydrate_player_$zid"
      $script:baseRecipes[$rid] = @($specs)
      $script:forces += [ordered]@{ id = $rid; label = "Standing base - $zid"; teamID = 0; side = "Legion"; faction = "ashwalkers"; role = "rehydrated_base"; base = [ordered]@{ x = $zc[0]; z = $zc[1] }; recipe = $rid }
      $rehydrated += 1
    } elseif ($ctrl -in @("armada", "cortex") -and $null -ne $script:primaryEnemyTeamID) {
      # Only rehydrate zones matching the primary enemy's faction — mixing a
      # second empire's hardware onto that team would read as nonsense.
      if ($ctrl -ne ([string]$script:primaryEnemySide).ToLower()) { continue }
      $prefix = if ($ctrl -eq "cortex") { "cor" } else { "arm" }
      $specs = New-RehydrateSpecs $entry.snapshot $prefix
      if (@($specs).Count -eq 0) { continue }
      $rid = "rehydrate_enemy_$zid"
      $script:baseRecipes[$rid] = @($specs)
      $script:forces += [ordered]@{ id = $rid; label = "Standing works - $zid"; teamID = $script:primaryEnemyTeamID; side = $script:primaryEnemySide; faction = $ctrl; role = "rehydrated_base"; base = [ordered]@{ x = $zc[0]; z = $zc[1] }; recipe = $rid }
      $rehydrated += 1
    }
  }
  if ($rehydrated -gt 0) { Write-Host ("Finale rehydration: {0} standing bases restored from campaign memory." -f $rehydrated) }
}

# Null Merc foothold: a flank camp perpendicular to the deploy->target axis,
# kept clear of the player start and the wild center. Their patrols press the
# same Armada approaches the garrison screens - the war happens on the map.
if ($mercsPresent) {
  $axisX = $enemyCenter[0] - $deployCenter[0]
  $axisZ = $enemyCenter[1] - $deployCenter[1]
  $axisLen = [Math]::Sqrt($axisX * $axisX + $axisZ * $axisZ)
  if ($axisLen -lt 0.001) { $axisLen = 0.001 }
  $perpX = -$axisZ / $axisLen
  $perpZ = $axisX / $axisLen
  $midX = ($deployCenter[0] + $enemyCenter[0]) / 2.0
  $midZ = ($deployCenter[1] + $enemyCenter[1]) / 2.0
  $candidates = @(
    @((Clamp01 ($midX + 0.26 * $perpX)), (Clamp01 ($midZ + 0.26 * $perpZ))),
    @((Clamp01 ($midX - 0.26 * $perpX)), (Clamp01 ($midZ - 0.26 * $perpZ)))
  )
  $mercCenter = $candidates[0]
  $bestScore = -1.0
  foreach ($cand in $candidates) {
    $dxD = $cand[0] - $deployCenter[0]; $dzD = $cand[1] - $deployCenter[1]
    $dxW = $cand[0] - $wildCenter[0]; $dzW = $cand[1] - $wildCenter[1]
    $score = [Math]::Min([Math]::Sqrt($dxD * $dxD + $dzD * $dzD), [Math]::Sqrt($dxW * $dxW + $dzW * $dzW))
    if ($score -gt $bestScore) { $bestScore = $score; $mercCenter = $cand }
  }
  # Drop 3: finales field a full-war merc foothold — the standing war shows up.
  $mercScaleBase = if ($isFinale) { [Math]::Max(1.0, $enemyScale * 1.05) } else { [Math]::Max(0.5, $enemyScale * 0.75) }
  Add-NullMercCamp $mercCenter ($mercScaleBase * $mercFootholdScale) $mercsAllied

  # Drop 3 finale dressing: availableAllies defectors materialize on the
  # opposite flank as a real allied team.
  if ($isFinale) {
    $allyNames = @()
    if ($intent.roster -and $intent.roster.PSObject.Properties["availableAllies"] -and $intent.roster.availableAllies) {
      $allyNames = @($intent.roster.availableAllies | ForEach-Object { [string]$_ })
    }
    $defSide = if ($allyNames -contains "cortex_defectors") { "Cortex" }
               elseif ($allyNames -contains "armada_deserters") { "Armada" } else { "" }
    if ($defSide) {
      $defCenter = @((Clamp01 (2.0 * $midX - $mercCenter[0])), (Clamp01 (2.0 * $midZ - $mercCenter[1])))
      Add-DefectorCamp $defSide $defCenter ([Math]::Max(0.5, $enemyScale * 0.45))
    }
  }
}

# Wild pressure nest on wild-family maps whose objective is not already the hive.
if ($hasWild -and $objectiveKind -ne "hive_clear_or_bypass") {
  Add-RaptorCamp $wildCenter $false "Raptor wild pressure"
}

# Same-faction camps must never shoot each other: Spring allies only through
# explicit pacts and every camp rides its own allyteam, so pact all armada-
# armada and cortex-cortex allyteam pairs. Player, mercs, defectors, and
# raptors are deliberately excluded (their stances are authored above).
$sameFactionAllyIds = @{}
foreach ($tm in @($teams)) {
  $fac = [string]$tm.faction
  if ($fac -ne "armada" -and $fac -ne "cortex") { continue }
  if (-not $sameFactionAllyIds.ContainsKey($fac)) { $sameFactionAllyIds[$fac] = @() }
  $sameFactionAllyIds[$fac] = @($sameFactionAllyIds[$fac]) + @([int]$tm.allyTeam)
}
foreach ($fac in @($sameFactionAllyIds.Keys)) {
  $ids = @($sameFactionAllyIds[$fac] | Sort-Object -Unique)
  for ($ii = 0; $ii -lt $ids.Count; $ii++) {
    for ($jj = $ii + 1; $jj -lt $ids.Count; $jj++) {
      $alliances += [ordered]@{ allyTeamA = [int]$ids[$ii]; allyTeamB = [int]$ids[$jj]; allied = $true }
    }
  }
  if ($ids.Count -gt 1) { Write-Host ("Faction pact: {0} camps allied across {1} allyteams." -f $fac, $ids.Count) }
}
# Everyone standing WITH the player also stands with each other (mercs +
# defectors on a finale would otherwise brawl across their own allyteams).
$playerAllied = @()
foreach ($pact in @($alliances)) {
  if ($pact.allied -and [int]$pact.allyTeamA -eq 0) { $playerAllied = @($playerAllied) + @([int]$pact.allyTeamB) }
  elseif ($pact.allied -and [int]$pact.allyTeamB -eq 0) { $playerAllied = @($playerAllied) + @([int]$pact.allyTeamA) }
}
$playerAllied = @($playerAllied | Sort-Object -Unique)
for ($ii = 0; $ii -lt $playerAllied.Count; $ii++) {
  for ($jj = $ii + 1; $jj -lt $playerAllied.Count; $jj++) {
    $alliances += [ordered]@{ allyTeamA = [int]$playerAllied[$ii]; allyTeamB = [int]$playerAllied[$jj]; allied = $true }
  }
}

# Debrief picks after occupation is known -- point at live camps / extract.
$occupationForPicks = @($script:mapOccupation | Where-Object { -not $_.primary })
$nextMissionCandidates = New-NextMissionCandidates -ZoneMap $zoneMap -AdjForMap $adjForMap `
  -MapId ([string]$intent.mapId) -CurrentTarget $targetZoneId -MissionNumber $missionNumber `
  -Occupation $occupationForPicks -ExtractZone ([string]$intent.extractionZoneId)

# Hero manifest for the HUD/name tags (id/name/critical/level/rank/xp).
# Spawnable hero specs already ride inside the player kit recipes.
$heroManifest = @()
if ($roster -and $roster.PSObject.Properties["heroes"] -and $roster.heroes) {
  foreach ($h in $roster.heroes) {
    $heroManifest += [ordered]@{
      id = [string]$h.heroId
      name = [string]$h.name
      unitDefName = [string]$h.unitDef
      missionCritical = [bool]$h.missionCritical
      level = if ($null -ne $h.level) { [int]$h.level } else { 1 }
      rank = if ($h.rank) { [string]$h.rank } else { "Runner" }
      xp = if ($null -ne $h.xp) { [double]$h.xp } else { 0.0 }
      campaignXp = if ($null -ne $h.campaignXp) { [double]$h.campaignXp } else { 0.0 }
      hpMult = if ($null -ne $h.hpMult) { [double]$h.hpMult } else { 1.35 }
    }
  }
}

# Escalation fallback: if the camp's live mobiles are all dead, waves keep
# arriving as the enemy side's standard column instead of silently drying up.
$fbT = $FACTION[$enemySide]
$fallbackWaveDefs = @($fbT.raider, $fbT.skirm, $fbT.assault)
if ($objectiveKind -eq "hive_clear_or_bypass") {
  $fallbackWaveDefs = @("raptor_land_swarmer_basic_t1_v1", "raptor_land_swarmer_basic_t2_v1")
}

$graph = if ($state -and $state.graph) { $state.graph } else { [pscustomobject]@{} }
$reputation = if ($state -and $state.reputation) { $state.reputation } else { [pscustomobject]@{} }
$companions = @()
if ($state -and $state.companion) {
  $companions = @([ordered]@{
    id = $state.companion.id
    displayName = $state.companion.displayName
    unitDefName = if ($state.companion.unitDefName) { $state.companion.unitDefName } else { "legcen" }
    xp = $state.companion.xp
    morale = $state.companion.morale
    loyalty = $state.companion.loyalty
    stress = $state.companion.stress
    autonomy = $state.companion.autonomy
    commandMode = $state.companion.commandMode
  })
}

# Drop 4: escalation lines land on the card after camps are placed (the card
# itself is assembled pre-camp, so mutate it here).
if ($script:secondaryMeta.Count -gt 0) {
  $secBits = @()
  foreach ($sm in $script:secondaryMeta) {
    $secBits += ("{0}{1}" -f $sm.label, $(if ($sm.required) { " (REQUIRED)" } else { " (bonus)" }))
  }
  $missionCard.secondaryLine = "Secondary marks: " + ($secBits -join " | ")
}
if ($objectiveStrength -eq "raze") {
  $missionCard.strengthLine = "RAZE ORDER: the entire camp is the objective -- leave nothing standing."
} elseif ($objectiveStrength -eq "purge") {
  $missionCard.strengthLine = "PURGE ORDER: clear the board -- every enemy faction unit dies before this ends."
}

# Hub multi-capture (arc 2+): primary is targetZoneId; rest are secondary marks
$hubCaptureIds = @()
if ($intent.captureZoneIds) { $hubCaptureIds = @($intent.captureZoneIds) }
elseif ($intent.objectiveTarget -and $intent.objectiveTarget.captureZoneIds) { $hubCaptureIds = @($intent.objectiveTarget.captureZoneIds) }
else { $hubCaptureIds = @($targetZoneId) }
$hubSecondaryIds = @()
if ($intent.secondaryCaptureZoneIds) { $hubSecondaryIds = @($intent.secondaryCaptureZoneIds) }
elseif ($intent.objectiveTarget -and $intent.objectiveTarget.secondaryCaptureZoneIds) {
  $hubSecondaryIds = @($intent.objectiveTarget.secondaryCaptureZoneIds)
}
$hubChoiceIdVal = if ($intent.hubChoiceId) { [string]$intent.hubChoiceId } else { $null }
$hubDeployAces = if ($intent.deployAces) { @($intent.deployAces) } else { @() }

$scenario = [ordered]@{
  schemaVersion = "verdance-playable-scenario/1.0-alpha"
  sourceIntentPath = $IntentPath
  sourceStatePath = $StatePath
  map = [ordered]@{
    id = $map.id
    name = $map.mapName
    sizeX = 0
    sizeZ = 0
    descriptor = $map.descriptor
  }
  zoneMapPath = $zoneMapRel
  defaultVariant = "alpha_player"
  notes = "Generated from Verdance Story Engine v1 mission intent. Human player controls team 0; NPCs use SimpleAI/RaptorsAI."
  missionBase = [ordered]@{
    schemaVersion = "verdance-playable/1.0-alpha"
    campaignId = "verdance_ashes"
    missionId = $missionId
    missionNumber = $missionNumber
    deploymentMapId = $intent.mapId
    deploymentZoneId = $intent.deploymentZoneId
    extractionZoneId = $intent.extractionZoneId
    strikeTeam = $strikeDoctrine
    arcProfile = $arcProfile
    act = $(if ($intent.PSObject.Properties["act"] -and $intent.act) { $intent.act }
            else { [ordered]@{ act = $actNum; name = $actName } })
    techPolicy = $techPolicy
    # The waterline this mission inherits from the planet's water cycle. The
    # gadget applies it at start and flood beats move it from there.
    hydrology = $(if ($intent.PSObject.Properties["hydrology"] -and $intent.hydrology) { $intent.hydrology }
                  else { [ordered]@{ level = 0.0; amplitude = 0.0 } })
    finale = $(if ($isFinale) { $intent.finale } else { $null })
    missionCard = $missionCard
    pathSignal = if ($state -and $state.pathSignal) { $state.pathSignal } else { "B" }
    title = $title
    zone = $map.title
    objective = [ordered]@{
      id = if ($intent.objectiveTarget -and $intent.objectiveTarget.id) { $intent.objectiveTarget.id } else { "$missionId`_objective" }
      kind = if ($intent.objectiveTarget -and $intent.objectiveTarget.kind) { $intent.objectiveTarget.kind } else { $intent.objective }
      requiredFrames = $requiredFrames
      description = $description
      targetZoneId = $targetZoneId
      extractionZoneId = $intent.extractionZoneId
      captureZoneIds = @($hubCaptureIds)
      secondaryCaptureZoneIds = @($hubSecondaryIds)
      # Phase D: capture = clear living-shell pocket + hold under regrow (not empty grass).
      captureMode = $(
        if ($presenceKind -or ($objectiveKind -in @("seize_lane", "gate_control", "hold_plateau"))) {
          "clear_hold_shell"
        } elseif ($intent.objectiveTarget -and $intent.objectiveTarget.captureMode) {
          [string]$intent.objectiveTarget.captureMode
        } elseif ($intent.captureMode) {
          [string]$intent.captureMode
        } else { $null }
      )
      requiredHoldFrames = $(if ($presenceKind) { 900 } else { $null })
      clearFraction = $(if ($presenceKind) { 0.6 } else { $null })
      freeTnbMint = $false
      # Drop 4: surgical | raze (whole camp tagged) | purge (clear the board).
      strength = $objectiveStrength
    }
    # Drop 4: secondary objectives placed this mission (gadget ledger + HUD).
    secondaries = @($script:secondaryMeta)
    hubChoiceId = $hubChoiceIdVal
    deployAces = @($hubDeployAces)
    economy = if ($state -and $state.economy) { $state.economy } else { [ordered]@{ metalIncome = 0; energyIncome = 0; buildPower = 0 } }
    difficulty = [ordered]@{
      enemyScale = $enemyScale
      difficultyCoefficient = $diffCoeff
      difficultyDial = [Math]::Round($difficultyDial, 3)
      band = $diffBand
      hazardLevel = [Math]::Round($maxHazard, 3)
      fortified = $fortify
      enemyAI = [string]$arcProfile.enemyAI
      farmSortie = [bool]$isFarmSortie
      label = $difficultyLine
      craftStamp = $craftStamp
    }
    progression = [ordered]@{
      mode = $xpMode
      xpPersistOnDeath = $true
      farmSortie = [bool]$isFarmSortie
    }
    devTelemetry = [bool]$devTelemetry
    dev = [ordered]@{
      telemetry = [bool]$devTelemetry
      samplePeriodFrames = [int]$devPeriod
      learnFaster = [bool]$devTelemetry
    }
    craft = $(
      if ($craftKnobs) {
        [ordered]@{
          stamp = $craftStamp
          knobs = $craftKnobs
        }
      } else { $null }
    )
    nextMissionCandidates = @($nextMissionCandidates)
    mapOccupation = @($script:mapOccupation)
    livingShell = $(if ($script:livingShellPayload) { $script:livingShellPayload } else { $null })
    wrath = $(if ($script:wrathPayload) { $script:wrathPayload } else { $null })
    occupationModel = "living_shell"
    sessionMode = if ($intent.sessionMode) { [string]$intent.sessionMode } else { "same_map" }
    capture = [ordered]@{
      mode = $(if ($presenceKind) { "clear_hold_shell" } else { "none" })
      clearFraction = 0.6
      holdFrames = 900
      regrowPressure = [bool]$presenceKind
      freeTnbMint = $false
      livingShell = [bool]($null -ne $script:livingShellPayload)
    }
    continueRules = [ordered]@{
      sameMapContinue = $true
      carryHeroes = $true
      carryCombatUnits = $true
      carryWrecks = $true
      snapDistantUnitsToDeploy = $true
      # Occupied-map / living shell: do not wipe the next scar -- promote instead.
      # Capture continues also prefer promote (claim next pocket on same shell).
      clearEnemyOnContinue = ($objectiveKind -ne "eco_raid" -and -not $presenceKind)
      promoteOccupationOnContinue = ($objectiveKind -eq "eco_raid" -or $presenceKind)
      metalCarryFraction = 0.5
    }
    flavor = $arcProfile.flavor
    escalation = $(
      # WO-035: Arc A off (hot extract wave only in gadget); light/full later.
      $escMode = [string]$arcProfile.escalation
      if ($escMode -eq "off") {
        [ordered]@{
          fallbackWaveDefs = $fallbackWaveDefs
          firstWaveFrame = 999999
          intervalFrames = 999999
          maxWaves = 0
          mode = "off"
          frontBand = [bool]$frontBand
          targetDuration = if ($intent.environment -and $intent.environment.targetDuration) { [string]$intent.environment.targetDuration } else { "10min" }
          hotExtractOnly = $true
        }
      } elseif ($escMode -eq "light") {
        [ordered]@{
          fallbackWaveDefs = $fallbackWaveDefs
          firstWaveFrame = 3600
          intervalFrames = 2700
          maxWaves = 3
          mode = "light"
          frontBand = [bool]$frontBand
          targetDuration = if ($intent.environment -and $intent.environment.targetDuration) { [string]$intent.environment.targetDuration } else { "10min" }
        }
      } else {
        [ordered]@{
          fallbackWaveDefs = $fallbackWaveDefs
          firstWaveFrame = 2700
          intervalFrames = 1800
          maxWaves = 8
          mode = "full"
          frontBand = [bool]$frontBand
          targetDuration = if ($intent.environment -and $intent.environment.targetDuration) { [string]$intent.environment.targetDuration } else { "10min" }
        }
      }
    )
    heroes = $heroManifest
    beats = if ($intent.PSObject.Properties["beats"] -and $intent.beats) { @($intent.beats) } else { @() }
    graph = $graph
    reputation = $reputation
    companions = $companions
    # WO-043c: Tenebrium bank + Armada crisis (continent of farming decoys).
    commerce = $(if ($commerce) { $commerce } else { [ordered]@{ tenebrium = 0; credits = 0 } })
    tenebrium = [ordered]@{
      playerBank = if ($commerce -and $null -ne $commerce.tenebrium) { [int]$commerce.tenebrium } else { 0 }
      armadaBank = 0
      cortexBank = 2
      armadaCrisis = $true
      notes = "Build-power units cost >=1 Tnb; wrecks keep Tnb until reclaimed or truly gone. Armada spent theirs on decoy wind/solar/converter farms."
    }
    worldConflict = $(
      $wc = if ($intent.PSObject.Properties["worldConflict"] -and $intent.worldConflict) { $intent.worldConflict } else { [ordered]@{} }
      # Ensure Armada crisis flag is visible to the gadget even on thin intents.
      if ($wc -is [System.Collections.IDictionary] -or $wc -is [hashtable] -or $wc.GetType().Name -match 'OrderedDictionary|PSCustomObject') {
        try { $wc | Add-Member -NotePropertyName armadaTenebriumCrisis -NotePropertyValue $true -Force } catch {}
      }
      $wc
    )
    storyIntent = $intent
  }
  baseRecipes = $baseRecipes
  layout = [ordered]@{
    allyTeams = $allyTeams
    teams = $teams
    alliances = $alliances
  }
  forces = $forces
  variants = @(
    [ordered]@{
      id = "alpha_player"
      label = "Alpha Campaign Player"
      playerTeamID = 0
      playerSide = "Legion"
      playerStartLabel = "Legion Green Player"
      notes = "Human-controlled alpha campaign sortie generated from next_mission_intent.json."
      ai = $ai
    }
  )
}

# install_playable_slice needs explicit dimensions for start positions.
$authoredScenarioPath = Join-Path $Workspace "data\scenarios\authored\$($intent.mapId).authored_baseline.json"
if (Test-Path $authoredScenarioPath) {
  $authored = Get-Content -Raw -LiteralPath $authoredScenarioPath | ConvertFrom-Json
  if ($authored.map) {
    $scenario["map"]["sizeX"] = [int]$authored.map.sizeX
    $scenario["map"]["sizeZ"] = [int]$authored.map.sizeZ
  }
}
if (-not $scenario["map"]["sizeX"] -or -not $scenario["map"]["sizeZ"]) {
  throw "Could not determine map dimensions for $($intent.mapId)."
}

$generatedDir = Join-Path $Workspace "data\scenarios\generated"
New-Item -ItemType Directory -Force -Path $generatedDir | Out-Null
$scenarioPath = Join-Path $generatedDir "next_mission_intent.playable.json"
Save-Json $scenario $scenarioPath

if (-not $SaveName) {
  $safeMission = $missionId -replace '[^A-Za-z0-9_-]', '_'
  $SaveName = "verdance_${safeMission}_alpha"
}

$installer = Join-Path $ScriptDir "install_playable_slice.ps1"
if ($Launch -and $SaveGame) {
  & $installer -Workspace $Workspace -ScenarioPath $scenarioPath -Variant "alpha_player" -PlayerController "human" -TimeoutSeconds $TimeoutSeconds -Launch -SaveGame -SaveName $SaveName
} elseif ($Launch) {
  & $installer -Workspace $Workspace -ScenarioPath $scenarioPath -Variant "alpha_player" -PlayerController "human" -TimeoutSeconds $TimeoutSeconds -Launch
} elseif ($SaveGame) {
  & $installer -Workspace $Workspace -ScenarioPath $scenarioPath -Variant "alpha_player" -PlayerController "human" -TimeoutSeconds $TimeoutSeconds -SaveGame -SaveName $SaveName
} else {
  & $installer -Workspace $Workspace -ScenarioPath $scenarioPath -Variant "alpha_player" -PlayerController "human" -TimeoutSeconds $TimeoutSeconds
}

$manifest = [ordered]@{
  ok = $true
  generatedAt = (Get-Date).ToString("s")
  intentPath = $IntentPath
  statePath = $StatePath
  scenarioPath = $scenarioPath
  missionId = $missionId
  missionNumber = $missionNumber
  mapId = $intent.mapId
  mapName = $map.mapName
  deploymentZoneId = $intent.deploymentZoneId
  objectiveTarget = $intent.objectiveTarget
  act = $actNum
  actName = $actName
  finaleKind = $(if ($isFinale) { $finaleKind } else { $null })
  enemySide = $enemySide
  nullMercs = [ordered]@{ present = [bool]$mercsPresent; allied = [bool]$mercsAllied; reputation = $mercRep }
  hasWild = [bool]$hasWild
  saveName = if ($SaveGame) { $SaveName } else { $null }
  seedOutbox = $config.seedOutbox
  seedDestination = $config.seedDestination
  nextStep = if ($Launch) { "BAR launch requested." } elseif ($SaveGame) { "Load the generated save from BAR Saves." } else { "Launch BAR with playable_runs latest startscript, or use PLAY_NEXT_MISSION_V1.bat." }
}
$manifestPath = Join-Path $Workspace "outbox\next_mission_build_manifest.json"
Save-Json $manifest $manifestPath

Write-Host "Built Verdance alpha mission from v1 intent."
Write-Host "Mission: $missionId on $($map.mapName)"
Write-Host "Scenario: $scenarioPath"
Write-Host "Manifest: $manifestPath"
