param(
  [string]$Workspace = "",
  [string]$IntentPath = "",
  [string]$StatePath = "",
  [switch]$Launch,
  [switch]$SaveGame,
  [string]$SaveName = "",
  [int]$TimeoutSeconds = 300,
  # Passed straight through to install_playable_slice.ps1's [MODOPTIONS] block.
  # Semicolon-separated key=value pairs.
  [string]$ExtraModOptions = ""
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
  # 0) Wild / Rock Jungle home dig-ins are raptor shelves — never Armada.
  $againstHint = ""
  if ($Intent.PSObject.Properties["against"] -and $Intent.against) {
    $againstHint = [string]$Intent.against
  } elseif ($Intent.PSObject.Properties["worldConflict"] -and $Intent.worldConflict -and $Intent.worldConflict.primaryEnemy) {
    $againstHint = [string]$Intent.worldConflict.primaryEnemy
  }
  if ($againstHint -eq "wild" -or $MapId -eq "the_rock_jungle") {
    return "Armada"  # unused when wild home skips faction camps; keep table key valid
  }
  # 1) Honor the objective's explicit faction when the engine set one.
  if ($Intent.objectiveTarget -and $Intent.objectiveTarget.enemyFaction) {
    switch ([string]$Intent.objectiveTarget.enemyFaction) {
      "cortex" { return "Cortex" }
      "armada" { return "Armada" }
      "wild" { return "Armada" }
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
  $ok = if ($Intent.objectiveTarget -and $Intent.objectiveTarget.kind) {
    [string]$Intent.objectiveTarget.kind
  } else { [string]$Intent.objective }
  if ($ok -in @("fortify_zone", "home_founding")) {
    $zid = if ($Intent.objectiveTarget -and $Intent.objectiveTarget.targetZoneId) {
      [string]$Intent.objectiveTarget.targetZoneId
    } elseif ($Intent.targetZoneId) { [string]$Intent.targetZoneId } else { "the zone" }
    return "Fortify $zid — raise defense, build power, army, and storage. Defense is what 'secured' means."
  }
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
  # The sortie clock does not field a commander. Story sets that after this profile.
  $playerCommanders = 0
  $allyPower = if ($n -le 1) { 0.95 } elseif ($n -eq 2) { 0.55 } elseif ($n -eq 3) { 0.35 } elseif ($n -le 5) { 0.25 } else { 0.15 }
  $escalation = if ($id -eq "raid_tactics") { "off" } elseif ($id -eq "contested_front") { "light" } else { "full" }
  $enemyMode = if ($id -eq "raid_tactics") { "static_bases" } elseif ($id -eq "contested_front") { "static_bases" } else { "light_qrf" }
  # Arc A prints Phobos (legcen), not Ballistas. Later acts clear this printer.
  $printer = [ordered]@{ def = "leglab"; product = "legcen"; count = 1; metalIncome = 10; energyIncome = 50 }
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
  #
  # SPAWN RULE (one owner): in BAR these units are spawned ONCE, by
  # VA_LOGISTICS.spawnCommerceDeployKit in game_verdance_campaign.lua, straight
  # from mission.commerce.deploy. The copies composed into the player kit here are
  # for the layout / previews only; every one of them is stamped commerceDeploy=true
  # plus a packageTag, and the gadget's setup spawn skips any spec carrying that
  # stamp (VA_CREW_isCommerceKitSpec). An untagged nano or constructor used to pass
  # the gadget's anchor-keep filter and land twice.
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
    # Same fallback id the gadget uses for an unlisted item (kit_<1-based index>).
    $tag = if ($d.packageTag) { [string]$d.packageTag } elseif ($d.listingId) { [string]$d.listingId } else { "kit_" + ($i + 1) }
    if ($kind -eq "unit_printer") {
      $fac = if ($d.factoryDef) { [string]$d.factoryDef } else { "corlab" }
      $product = if ($d.product) { [string]$d.product } else { "corak" }
      $printer = Spec $fac 1 ($ox - 40) ($oz + 20) 100
      $printer.unitPrinter = $true
      $printer.printerProduct = $product
      $printer.printerMetalIncome = if ($null -ne $d.metalIncome) { [double]$d.metalIncome } else { 8 }
      $printer.printerEnergyIncome = if ($null -ne $d.energyIncome) { [double]$d.energyIncome } else { 40 }
      $printer.packageTag = $tag
      $printer.commerceDeploy = $true
      $kit += $printer
      $seed = if ($null -ne $d.seedCount) { [Math]::Max(0, [int]$d.seedCount) } else { 4 }
      if ($seed -gt 0) {
        $seedSpec = Spec $product $seed ($ox + 80) $oz 70
        $seedSpec.packageTag = $tag + "_seed"
        $seedSpec.commerceDeploy = $true
        $kit += $seedSpec
      }
    } elseif ($kind -eq "nano") {
      $ndef = if ($d.unitDef) { [string]$d.unitDef } else { "cornanotc" }
      $nc = if ($null -ne $d.count) { [Math]::Max(1, [int]$d.count) } else { 1 }
      $nSpec = Spec $ndef $nc ($ox - 80) ($oz + 40) 90
      $nSpec.packageTag = $tag
      $nSpec.commerceDeploy = $true
      $kit += $nSpec
    } elseif ($kind -eq "constructor") {
      $cdef = if ($d.unitDef) { [string]$d.unitDef } else { "armck" }
      $cc = if ($null -ne $d.count) { [Math]::Max(1, [int]$d.count) } else { 1 }
      $cSpec = Spec $cdef $cc $ox ($oz + 60) 90
      $cSpec.packageTag = $tag
      $cSpec.commerceDeploy = $true
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
      $pSpec.packageTag = $tag
      $pSpec.commerceDeploy = $true
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
  switch ($Family) {
    "tempo" { $kit += (Spec "legcen" 2 -60 -260 90) }
    "siege" { $kit += (Spec "legcen" 2 -200 -200 90) }
    "wild"  { $kit += (Spec "leglht" 1 200 -140 130) }
    default { $kit += (Spec "legcen" 2 140 -260 90) }
  }
  # Heroes sealed by hub muster / gadget packs — do not bake roster into seed.
  return $kit
}

function Get-ZoneAdjacencyMap {
  param([string]$Workspace, [string]$MapId)
  $path = Join-Path $Workspace "data\zone_maps\authored\zone_adjacency.json"
  if (!(Test-Path $path)) { return $null }
  $all = Get-Content -Raw -LiteralPath $path | ConvertFrom-Json
  if ($all.PSObject.Properties[$MapId]) { return $all.$MapId }
  return $null
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
      $installationId = if ($node.installationId) { [string]$node.installationId } else { "$($MapId)::$zid" }
      $candidateSlug = $installationId -replace '[^A-Za-z0-9_-]', '_'
      $cands += [ordered]@{
        id = "cand_occ_$candidateSlug"
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
        installationId = $installationId
        pocketId = if ($node.pocketId) { [string]$node.pocketId } else { "" }
        hubLabel = "Push $label"
      }
    }
  }

  # 2) Adjacent zone contracts (fallback when occupation list is thin).
  $neighbors = @()
  if (-not $Occupation) {
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
      plain = "Legacy adjacent contract: $verb $label ($kind)."
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
  }

  # 3) Extract / leave the map (always offer when we have occupation doctrine).
  if ($ExtractZone -or $CurrentTarget) {
    $ex = if ($ExtractZone) { $ExtractZone } else { $CurrentTarget }
    $cands += [ordered]@{
      id = "cand_extract_$ex"
      title = "EXIT - bank and close"
      plain = "Bank the raid. Pull the warband out. Hub reopens for the next board mark."
      mapId = $MapId
      targetZoneId = $ex
      fromZoneIds = $from
      objectiveArchetype = "extract_leave"
      kind = "extract"
      accent = "exit"
      quitPrompt = $true
      patron = "nullmercs"
      against = "armada"
      preplaced = $true
      extractOnly = $true
      hubLabel = "EXIT - bank and close"
    }
  }

  return @($cands | Select-Object -First 4)
}

function New-MissionCard {
  # WO-031: plain-English mission card (not Ketha flavor dump).
  # Difficulty + XP lines stay explicit so tuning never hides behind fog.
  param($Intent, $ArcProfile, [string]$MapTitle, [string]$Description, [string]$DeployZone, [string]$TargetZone, [string]$DifficultyLine = "", [string]$XpLine = "", [string]$HeroLine = "")
  $kind = if ($Intent.objectiveTarget -and $Intent.objectiveTarget.kind) { [string]$Intent.objectiveTarget.kind } else { [string]$Intent.objective }
  $objLine = switch ($kind) {
    "seize_lane" { "Clear the living-shell pocket (~60% eco+teeth), hold under regrow pressure to claim the node, then extract. Claim does not mint free Tnb." }
    "gate_control" { "Clear the gate pocket on the living shell, hold under regrow pressure to claim, then extract. No free Tnb mint." }
    "hold_plateau" { "Clear the plateau shell pocket, hold under regrow pressure to claim the step, then extract. No free Tnb mint." }
    "eco_raid" { "Raid the marked energy works (wreck ~60%), then extract before Armada's answer arrives. The rest of the map is already occupied -- pick another scar later if you want." }
    "economy_disrupt" { "Destroy the enemy economy centerpiece, then extract." }
    "strike_relay" { "Destroy the key relay structure, then extract." }
    "destroy_key_structure" { "Destroy the marked key structure, then extract." }
    "farm_patrol" { "Farm sortie: clear the patrol camp for XP, then extract. Campaign clock barely moves." }
    "fortify_zone" { "Nobody holds $TargetZone. Establish presence: build defences there until its defensive value reaches the goal, then extract." }
    default { "Complete the marked objective, then extract." }
  }
  if ($Intent.openingMission) {
    $objLine = "Raid Armada decoy farms in Greenest Fields. Damage the works, then leave before the response builds."
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
    "The command walker is scrap. Lead with the company."
  } else {
    "The command walker walks with you. Still take the objective."
  }
  if ($Intent.openingMission) {
    $tools = "Mercenary pre-buy: Punch of Thugs (6 damaged Cortex Thugs). Support: 2 Legion Karkinos and 6 rez bots."
  }
  if ($XpLine) { $tools = "$tools  |  $XpLine" }
  if ($HeroLine) { $tools = "$tools  |  $HeroLine" }
  $timerLine = "No clock. Get who and what you want onto the pad, then press EXTRACT. What is off the pad stays."
  return [ordered]@{
    situation = "Map: $MapTitle. Land on $DeployZone. Target $TargetZone. Leave from the same pad."
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
  param([string]$Def, [int]$Count, [int]$Dx, [int]$Dz, [int]$Spacing = 90, [bool]$AtSpots = $false, $PatrolX = $null, $PatrolZ = $null, $Patrol = $null, $At = $null)
  $s = [ordered]@{ unitDefName = $Def; count = [Math]::Max(1, $Count); dx = $Dx; dz = $Dz; spacing = $Spacing }
  if ($AtSpots) { $s.atMetalSpots = $true }
  # A baked field (Koom's war): flat [x, z, facing, hp%] per unit, x and z normalized. The gadget
  # stands each unit exactly there, as hurt as the war left it.
  if ($null -ne $At) { $s.at = @($At); $s.exact = $true }
  if ($null -ne $Patrol) { $s.patrol = @($Patrol) }
  elseif ($null -ne $PatrolX) { $s.patrolX = [double]$PatrolX; $s.patrolZ = [double]$PatrolZ }
  return $s
}

function Add-ReserveToKit {
  # The company's reserve: roster.cadre is what the player chose to bring this drop (the hub's
  # Reserve panel, clamped to the lift limit in Python). Every kit gets it the same way, all of
  # it, any unit type but a commander.
  param($Kit, $Roster)
  if (-not $Roster -or -not $Roster.cadre) { return $Kit }
  $i = 0
  foreach ($p in $Roster.cadre.PSObject.Properties) {
    $def = [string]$p.Name
    $cnt = [int]$p.Value
    if ($cnt -gt 0 -and $def -notmatch '^(arm|cor|leg)com$') {
      $r = Spec $def $cnt (-130 - 70 * ($i % 3)) (-160 - 70 * [Math]::Floor($i / 3)) 90
      $r.reserve = $true  # the gadget lands reserve specs with the company
      $Kit += $r
      $i++
    }
  }
  return $Kit
}

function Get-CadreXpBag {
  # roster.cadreXp[def] -> seed xp / craftXp for the next drop.
  param($Roster, [string]$Def)
  if (-not $Roster -or -not $Def) { return $null }
  $bank = $null
  if ($Roster.PSObject.Properties["cadreXp"] -and $Roster.cadreXp) { $bank = $Roster.cadreXp }
  if (-not $bank) { return $null }
  $bag = $null
  if ($bank.PSObject.Properties[$Def]) { $bag = $bank.$Def }
  elseif ($bank -is [System.Collections.IDictionary] -and $bank.Contains($Def)) { $bag = $bank[$Def] }
  if (-not $bag) { return $null }
  $xp = 0.0
  $craft = 0.0
  if ($null -ne $bag.xp) { $xp = [double]$bag.xp }
  elseif ($null -ne $bag.avgXp) { $xp = [double]$bag.avgXp }
  elseif ($null -ne $bag.peakXp) { $xp = [double]$bag.peakXp * 0.85 }
  if ($null -ne $bag.craftXp) { $craft = [double]$bag.craftXp }
  elseif ($null -ne $bag.avgCraftXp) { $craft = [double]$bag.avgCraftXp }
  if ($xp -le 0 -and $craft -le 0) { return $null }
  return [ordered]@{ xp = $xp; craftXp = $craft }
}

function Set-SpecCadreXp {
  param($SpecObj, $Roster)
  if (-not $SpecObj -or -not $Roster) { return $SpecObj }
  # Named heroes carry their own xp via heroId path — do not overwrite.
  if ($SpecObj.PSObject.Properties["heroId"] -and $SpecObj.heroId) { return $SpecObj }
  if ($SpecObj.heroId) { return $SpecObj }
  $def = [string]$SpecObj.unitDefName
  $bag = Get-CadreXpBag $Roster $def
  if (-not $bag) { return $SpecObj }
  if ($bag.xp -gt 0) { $SpecObj.xp = [double]$bag.xp }
  if ($bag.craftXp -gt 0) { $SpecObj.craftXp = [double]$bag.craftXp }
  return $SpecObj
}

function Apply-CadreXpToKit {
  # Stamp banked veteran XP onto every non-hero kit unit so BAR SetUnitExperience
  # restores the majority of field XP between rounds.
  param($Kit, $Roster)
  $out = @()
  foreach ($s in @($Kit)) {
    if ($s) { $out += ,(Set-SpecCadreXp $s $Roster) }
  }
  return $out
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
    # Alpha opening roles: Vane is the named Phobos (legcen) striker and Ketha
    # is the named field rez-bot. Neither role is a commander suit.
    if ($hid -eq "vane" -or ([string]$h.name -match "Vane")) { $def = "legcen" }
    if ($hid -eq "ketha" -or ([string]$h.name -match "Ketha")) { $def = "legrezbot" }
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
    if ($hid -eq "ketha" -or ([string]$h.name -match "Ketha")) {
      $spec.heroHpMult = [Math]::Max(2.5, [double]$spec.heroHpMult)
      $spec.heroBuildPowerMult = 3.0
      $spec.heroRole = "field_rez_support"
    } elseif ($hid -eq "vane" -or ([string]$h.name -match "Vane")) {
      $spec.heroRole = "phobos_striker"
    }
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
  # Economy floor plus the veteran cadre. The commander, when the arc allows
  # one, is BAR's single start unit. This kit must not spawn a second legcom.
  param([string]$Family, $Roster, [double]$ResourceMod = 1.0, $Commerce = $null)
  # q7 scarcity thins the economy floor (resourceModifier from the graph).
  $wind = [Math]::Max(2, [int][Math]::Round(4 * $ResourceMod))
  $kit = @(
    (Spec "legmex" 3 -140 120 120 $true),
    (Spec "legwin" $wind 120 160 90),
    (Spec "legsolar" 2 240 80 90),
    (Spec "legrad" 1 40 -60 100)
  )
  $cadreTotal = 0
  if ($Roster.cadre) {
    foreach ($p in $Roster.cadre.PSObject.Properties) {
      $cnt = [int]$p.Value
      $def = [string]$p.Name
      if ($cnt -gt 0 -and $def -notmatch '^(arm|cor|leg)com') { $cadreTotal += $cnt }  # spawned by Add-ReserveToKit
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
  # Heroes sealed by hub muster / gadget packs — do not bake roster into seed.
  return $kit
}

function New-FinaleKitFromRoster {
  # Drop 2 Act 3: massive starting conditions — the whole campaign walks out.
  # Established economy + factory floor + defenses + a real army, then the
  # full carried cadre (uncapped) and every living hero. One commander only:
  # BAR's start unit, not a second spec in this kit.
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
  $kit = Add-CommerceDeployToKit $kit $Commerce
  # Finale: still spawn named heroes from roster (full company walks out).
  $heroes = if ($Roster -and $Roster.PSObject.Properties["heroes"]) { $Roster.heroes } else { $null }
  return (Add-HeroSpecs $kit $heroes)
}

function New-StrikeTeam {
  # Arc A raid pack (player feedback):
  #   - Wheelies (legscout) for the player
  #   - Army of Phobos (legcen) -- NOT Ballistas (legbal / missile bots)
  #   - Pack of Zagreus rez bots (legrezbot)
  #   - Ash-Captain Vane as the named Phobos hero
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
  # Heroes + balance packs are sealed by the HTML hub muster and spawned by the
  # campaign gadget from mission.crewBand / deployAces — never bake the roster here.
  return $kit
}

function New-OpeningStrikeTeam {
  # Mission one is a mercenary pre-bought punch, not a persistent commander
  # deployment. Keep this explicit so progressed/stale campaign state cannot
  # leak a second commander, Incinerator, or generic Javelins into the opener.
  param($Commerce)
  $vane = Spec "legcen" 1 -70 -80 90
  $vane.heroId = "vane"
  $vane.heroName = "Ash-Captain Vane"
  $vane.heroRole = "phobos_striker"
  $vane.heroHpMult = 1.65
  $vane.heroXp = 0.25

  $ketha = Spec "legrezbot" 1 -150 70 80
  $ketha.heroId = "ketha"
  $ketha.heroName = "Ketha"
  $ketha.heroRole = "field_rez_support"
  $ketha.heroHpMult = 2.5
  $ketha.heroBuildPowerMult = 3.0
  $ketha.heroXp = 0.05

  $kit = @(
    (Spec "legkark" 2 120 20 105),
    $vane,
    $ketha,
    (Spec "legrezbot" 5 -150 70 80)
  )
  # Buy-everything: no free Punch. Owned packs (Punch, Crash, fabs, constructors)
  # ride only via commerce.deploy → Add-CommerceDeployToKit / gadget logistics.
  return (Add-CommerceDeployToKit $kit $Commerce)
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
  # Two roosts and the Queen's Nest. Burning the roosts is fine; the queen wakes when her nest
  # falls (or her anger fills), never because the roost count ran low (raptor_spawner_defense.lua).
  $null = $Hazard
  @(
    (Spec "raptor_hive" 1 -120 -40 240),
    (Spec "raptor_hive" 1 140 80 240),
    (Spec "va_queen_nest" 1 0 -240 300)
  )
}

function New-MercFoothold {
  # WO-038: allyPower scales kit. High = javelin shred (M1 adjunct). Low = light guns.
  param([double]$S, [double]$PX, [double]$PZ, [int]$FX, [int]$FZ, [double]$AllyPower = 1.0)
  $p = [Math]::Max(0.1, [Math]::Min(1.0, $AllyPower))
  $specs = @(
    (Spec $MERC.radar 1 0 -70 100),
    (Spec $MERC.llt (Get-ScaledCount ([Math]::Max(1, [int](3 * $p))) $S) (160 * $FX) (140 * $FZ) 150),
    (Spec $MERC.raider (Get-ScaledCount ([Math]::Max(1, [int](3 * $p))) $S) 110 -290 80 -Patrol (PatrolSweep $PX $PZ)),
    (Spec $MERC.skirm (Get-ScaledCount ([Math]::Max(1, [int](2 * $p))) $S) -130 -310 90 -Patrol (PatrolSweep $PX $PZ))
  )
  # Keep the foothold readable as a SimpleAI builder. Do not leak the old
  # generic Javelin blob into the opener; named Phobos Vane is the only elite
  # assault signature in the first sortie.
  if ($p -ge 0.7) {
    $specs += (Spec $MERC.skirm (Get-ScaledCount 2 $S) 10 -370 95 -Patrol (PatrolSweep $PX $PZ))
    $specs += (Spec $MERC.mg 1 (230 * $FX) (90 * $FZ) 110)
    $specs += (Spec $MERC.lab 1 -290 -140 120)
    $specs += (Spec $MERC.nano 1 -200 -230 90)
    $specs += (Spec $MERC.mex 2 -140 110 120 $true)
    $specs += (Spec $MERC.wind (Get-ScaledCount 3 $S) 130 160 85)
  } elseif ($p -ge 0.4) {
    $specs += (Spec $MERC.skirm 1 10 -370 95 -Patrol (PatrolSweep $PX $PZ))
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
if (!(Test-Path $IntentPath)) { throw "No next mission intent at $IntentPath. Drop from the hub (PLAY.bat), or run scripts\advance_campaign_v1.ps1 first." }

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
# Drop 2 act structure labels pacing. It does not field the command walker.
#   Act 1 ground control keeps the existing profile.
#   Act 2 is base building. The walker stays scrap until a story beat.
#   Act 3 finale: full unconstrained BAR with massive starting conditions.
$actNum = if ($intent.PSObject.Properties["act"] -and $intent.act -and $intent.act.act) { [int]$intent.act.act }
          elseif ($missionNumber -le 5) { 1 } elseif ($missionNumber -le 10) { 2 } else { 3 }
$actName = if ($intent.PSObject.Properties["act"] -and $intent.act -and $intent.act.name) { [string]$intent.act.name }
           elseif ($actNum -eq 1) { "ground_control" } elseif ($actNum -eq 2) { "constrained_rts" } else { "unbound_finale" }
$isFinale = [bool]($intent.PSObject.Properties["finale"] -and $intent.finale)
$finaleKind = if ($isFinale -and $intent.finale.kind) { [string]$intent.finale.kind } else { "" }
if ($actNum -ge 3) {
  $arcProfile.id = "unbound_finale"
  $arcProfile.playerEco = $true
  $arcProfile.unitPrinter = $null
  $arcProfile.enemyMode = "light_qrf"
  $arcProfile.escalation = "full"
  $arcProfile.allowEnemyProduction = $true
  $arcProfile.objectiveAdjacency = "forward"
  $arcProfile.sweepEnemyCommanders = $false
} elseif ($actNum -eq 2) {
  $arcProfile.id = "constrained_rts"
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
Write-Host ("Act structure: act={0} ({1}) finale={2}" -f $actNum, $actName, $finaleKind)
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
} elseif ($actNum -ge 2 -or ([string]$intent.mapId) -eq "tabula") {
  # Tabula and everything after: a BARbarian opponent with its real commander, so the map has
  # threat and motion as the company's army grows.
  $arcProfile.enemyAI = "barbarian"
  $arcProfile.sweepEnemyCommanders = $false
}
if ($arcProfile.flavor -eq "com_solar_farm") {
  $arcProfile.sweepEnemyCommanders = $false
  $arcProfile.allowEnemyProduction = $true
  $arcProfile.enemyMode = "com_solar_farm"
  $arcProfile.unitPrinter = $null
}
# Story owns the walker. A missing or false flag is scrap. Level and perks do not field it.
$commanderUnlocked = $false
$commanderRow = $null
if ($state -and $state.roster -and $state.roster.commander) { $commanderRow = $state.roster.commander }
if (-not $commanderRow -and $intent.roster -and $intent.roster.commander) { $commanderRow = $intent.roster.commander }
if ($commanderRow -and $commanderRow.PSObject.Properties["unlocked"] -and $commanderRow.unlocked -eq $true) {
  $commanderUnlocked = $true
}
$arcProfile.playerCommanders = $(if ($commanderUnlocked) { 1 } else { 0 })
Write-Host ("Command walker: {0}" -f $(if ($commanderUnlocked) { "unlocked" } else { "scrap" }))
# The field's standing set piece (verdance.world.theaters, on the intent): Koom's standing war,
# All That Simmers' kings' showdown. The engine decides it; this script only places it.
$theater = if ($intent.PSObject.Properties["theater"] -and $intent.theater) { $intent.theater } else { $null }
$isKings = [bool]($theater -and [string]$theater.kind -eq "kings_showdown")
$isStandingWar = [bool]($theater -and [string]$theater.kind -eq "standing_war")
# A young war on a big field keeps the map's living shell beside it (theaters: recipe keepShell).
$keepShell = [bool]($isStandingWar -and $theater.PSObject.Properties["keepShell"] -and $theater.keepShell)
$script:shellAllyId = $null; $script:shellFaction = $null
$script:kings = @()
if ($isKings) {
  # A classic game of BAR: every king starts with its commander and nothing else, and keeps it.
  $arcProfile.playerCommanders = 1
  $arcProfile.sweepEnemyCommanders = $false
  $arcProfile.enemyAI = "barbarian"
  $arcProfile.allowEnemyProduction = $true
  $arcProfile.escalation = "off"
  Write-Host "Kings' showdown: one commander each, last one standing takes the throne."
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
$targetZoneId = if ($intent.objectiveTarget -and $intent.objectiveTarget.targetZoneId) { [string]$intent.objectiveTarget.targetZoneId } else { "" }
$adjForMap = Get-ZoneAdjacencyMap -Workspace $Workspace -MapId ([string]$intent.mapId)
# The pad is the zone the player chose on the hub (legality is judged there, from belief). The
# builder never moves it: no route snap, no slide toward the target. Infil, pad, radar and
# extraction are one place.
$openingMission = [bool]($intent.PSObject.Properties["openingMission"] -and $intent.openingMission)

$deployZone = Get-ZoneById $zoneMap $deployZoneId
$targetZone = Get-ZoneById $zoneMap $targetZoneId
$deployCenter = Get-ZoneCenter $deployZone @(0.16, 0.16)
$enemyCenter = Get-ZoneCenter $targetZone @(0.84, 0.84)
$isContract = ($intent.PSObject.Properties["contractActive"] -and $intent.contractActive) -or ($intent.PSObject.Properties["fromZoneIds"] -and $intent.fromZoneIds -and @($intent.fromZoneIds).Count -gt 0)
$frontBand = $isContract -or ($intent.objective -in @("seize_lane", "gate_control"))

$enemySide = Get-EnemySide ([string]$intent.mapId) $intent
$enemyRecipe = Get-EnemyRecipeName $enemySide
$enemyRgb = Get-EnemyRgb $enemySide
$hasWild = ($map.PSObject.Properties["wilds"] -and $map.wilds) -or ($map.PSObject.Properties["raptors"] -and $map.raptors) -or ($intent.hazardPolicy -and $intent.hazardPolicy -ne "none")
# Rock Jungle is always a raptor shelf — even if map_pool forgot the wilds flag.
if ([string]$intent.mapId -eq "the_rock_jungle") { $hasWild = $true }

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
$script:wildTeamID = $null   # the raptor team the Rock Jungle dens ride (Add-RaptorCamp)
$script:primaryEnemySide = $null
$script:warWrecks = @()
$script:scoutParties = @()   # the Eye's Armada scout parties (game_verdance_scouts.lua)
$script:eyeStory = if ($intent.PSObject.Properties["eyeStory"] -and $intent.eyeStory) { $intent.eyeStory } else { $null }   # the standing war's dead (wrecks and heaps), laid by game_verdance_war_wrecks.lua
$script:secondaryMeta = @()  # Drop 4: placed secondary-objective camps (id/zone/required/x/z)
$nextMissionCandidates = @()  # rebuilt after occupation so picks point at live camps
$script:livingShellPayload = $null

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

function Test-HighValueUnitDef {
  param([string]$DefName)
  if (-not $DefName) { return $false }
  $n = $DefName.ToLowerInvariant()
  # Fusion makers — the optional high-value prize core.
  return ($n -match 'fus' -or $n -match 'fusion' -or $n -match 'afus' -or $n -match 'cafus')
}

function Test-HighValueAdjacentDef {
  param([string]$DefName)
  if (-not $DefName) { return $false }
  $n = $DefName.ToLowerInvariant()
  # Beamers / anni sit on GF fusion vaults; destroying the ring is vault death.
  if (Test-HighValueUnitDef $n) { return $true }
  return ($n -match 'beamer' -or $n -match 'annihilator' -or $n -match '^arman[ni]' -or $n -match 'cordoom')
}

function Get-DestroyedHighValuePockets {
  param($State, [string]$MapId)
  # Suppress a fusion vault when the maker died, the beamer ring died hard,
  # heldInstallations says destroyed, or secondaryResults completed bonus_fus_*.
  $dead = @{}
  if (-not $State -or -not $MapId) { return $dead }
  $bucket = $null
  if ($State.PSObject.Properties["shellScars"] -and $State.shellScars) {
    $bucket = $State.shellScars.$MapId
  }
  $units = @()
  if ($bucket -and $bucket.units) { $units = @($bucket.units) }
  $adjacentHits = @{}
  foreach ($rec in $units) {
    if (-not $rec) { continue }
    if ($rec.destroyed -eq $false) { continue }
    $def = [string]$(if ($rec.unitDefName) { $rec.unitDefName } else { "" })
    $pocketId = [string]$(if ($rec.pocketId) { $rec.pocketId } else { "" })
    if (-not $pocketId) { continue }
    $flagged = $false
    if ($rec.PSObject.Properties["highValue"] -and $rec.highValue) { $flagged = $true }
    if (Test-HighValueUnitDef $def) {
      $dead[$pocketId] = $true
      continue
    }
    if ($flagged -or (Test-HighValueAdjacentDef $def)) {
      if (-not $adjacentHits.ContainsKey($pocketId)) { $adjacentHits[$pocketId] = 0 }
      $adjacentHits[$pocketId] = [int]$adjacentHits[$pocketId] + 1
    }
  }
  # Beamer ring wipe: enough HV-adjacent destroys on the pocket ⇒ vault dead.
  foreach ($pocketId in @($adjacentHits.Keys)) {
    if ([int]$adjacentHits[$pocketId] -ge 3) { $dead[$pocketId] = $true }
  }
  # Held installs explicitly marked lost also count.
  if ($State.PSObject.Properties["heldInstallations"] -and $State.heldInstallations) {
    $mapHeld = $State.heldInstallations.$MapId
    if ($mapHeld) {
      foreach ($p in @($mapHeld.PSObject.Properties)) {
        $rec = $p.Value
        if ($rec -and [string]$rec.status -eq "destroyed") {
          $pocketId = [string]$(if ($rec.pocketId) { $rec.pocketId } else { $p.Name })
          if ($pocketId) { $dead[$pocketId] = $true }
        }
      }
    }
  }
  # Completed bonus_fus secondaries from last processed results / history.
  $hist = @()
  if ($State.PSObject.Properties["history"] -and $State.history) { $hist = @($State.history) }
  foreach ($h in $hist) {
    if (-not $h) { continue }
    $hMap = [string]$(if ($h.mapId) { $h.mapId } else { "" })
    if ($hMap -and $hMap -ne $MapId) { continue }
    $secs = @()
    if ($h.PSObject.Properties["secondaryResults"] -and $h.secondaryResults) {
      $secs = @($h.secondaryResults)
    }
    foreach ($sr in $secs) {
      if (-not $sr) { continue }
      $sid = [string]$(if ($sr.id) { $sr.id } elseif ($sr.objectiveId) { $sr.objectiveId } else { "" })
      if (-not ($sid -like "bonus_fus_*")) { continue }
      $done = $false
      if ($sr.completed -eq $true) { $done = $true }
      if ($null -ne $sr.destroyed -and [int]$sr.destroyed -gt 0) { $done = $true }
      if ($null -ne $sr.destroyedCount -and [int]$sr.destroyedCount -gt 0) { $done = $true }
      if (-not $done) { continue }
      $pocketId = [string]$(if ($sr.pocketId) { $sr.pocketId } else { ($sid -replace '^bonus_fus_','') })
      if ($pocketId) { $dead[$pocketId] = $true }
    }
  }
  return $dead
}

function Get-ScarredZoneSet {
  param($State, [string]$MapId)
  # Continuity: pads the player already claimed / scarred must not fully respawn.
  $scarred = @{}
  if (-not $State -or -not $MapId) { return $scarred }
  $claimed = $null
  if ($State.PSObject.Properties["claimedNodes"] -and $State.claimedNodes) {
    $claimed = $State.claimedNodes.$MapId
  }
  if ($claimed) {
    foreach ($p in @($claimed.PSObject.Properties)) {
      $rec = $p.Value
      if ($rec -and ($rec.pocketCleared -or $rec.nodeClaimed)) {
        $scarred[[string]$p.Name] = [ordered]@{ reason = "claimed"; scar = 1.0 }
      }
    }
  }
  $zm = $null
  if ($State.PSObject.Properties["zoneMemory"] -and $State.zoneMemory) {
    $zm = $State.zoneMemory.$MapId
  }
  if ($zm) {
    foreach ($p in @($zm.PSObject.Properties)) {
      $zid = [string]$p.Name
      $mem = $p.Value
      if (-not $mem) { continue }
      $ctrl = [string]$(if ($mem.controllingFaction) { $mem.controllingFaction } else { "" })
      $scar = 0.0
      if ($mem.abstract -and $null -ne $mem.abstract.shellScar) { $scar = [double]$mem.abstract.shellScar }
      if ($ctrl -in @("ashwalkers", "nullmercs") -or $scar -ge 0.25) {
        if (-not $scarred.ContainsKey($zid)) {
          $scarred[$zid] = [ordered]@{ reason = $(if ($ctrl -in @("ashwalkers", "nullmercs")) { "player_bloc" } else { "shell_scar" }); scar = [Math]::Max($scar, 0.25) }
        }
      }
    }
  }
  $ledger = $null
  if ($State.PSObject.Properties["shellScars"] -and $State.shellScars) {
    $bucket = $State.shellScars.$MapId
    if ($bucket -and $bucket.byZone) { $ledger = $bucket.byZone }
  }
  if ($ledger) {
    foreach ($p in @($ledger.PSObject.Properties)) {
      $zid = [string]$p.Name
      $z = $p.Value
      $destroyed = 0
      if ($z -and $null -ne $z.destroyedCount) { $destroyed = [int]$z.destroyedCount }
      # Ambient zone thin only — exact unitDef+pocket suppress lives in
      # Get-ScarSuppressSet. Keep ≥3 so a single stray kill does not haze the whole pad.
      if ($destroyed -ge 3) {
        $scarred[$zid] = [ordered]@{ reason = "destroyed_ledger"; scar = [Math]::Min(1.0, 0.2 * $destroyed) }
      }
    }
  }
  # Vivarium: the world remembers, and has the last word over the ledger's partial thinning.
  # Ground the company or the Mercs hold is ours (player_bloc); ground the campaign says no
  # empire holds (cleared, empty, wild) is vacant and gets no enemy base from the template.
  # Anyone who comes back was moved there by the simulation, and is in zoneMemory as holder.
  if ($zm) {
    foreach ($p in @($zm.PSObject.Properties)) {
      $mem = $p.Value
      if (-not $mem) { continue }
      $ctrl = [string]$(if ($mem.controllingFaction) { $mem.controllingFaction } else { "" })
      if (-not $ctrl) { continue }
      if ($ctrl -in @("ashwalkers", "nullmercs")) {
        $scarred[[string]$p.Name] = [ordered]@{ reason = "player_bloc"; scar = 1.0 }
      } elseif ($ctrl -notin @("armada", "cortex")) {
        $scarred[[string]$p.Name] = [ordered]@{ reason = "vacant"; scar = 1.0 }
      }
    }
  }
  return $scarred
}

function Get-ScarSuppressSet {
  param($State, [string]$MapId)
  # Exact burned pads: unitDefName|pocketId (fallback unitDefName|zoneId).
  # Light raids that never cross destroyed≥3 still stay burned on re-Drop.
  $suppress = @{}
  if (-not $State -or -not $MapId) { return $suppress }
  $bucket = $null
  if ($State.PSObject.Properties["shellScars"] -and $State.shellScars) {
    $bucket = $State.shellScars.$MapId
  }
  $units = @()
  if ($bucket -and $bucket.units) { $units = @($bucket.units) }
  foreach ($rec in $units) {
    if (-not $rec) { continue }
    if ($rec.destroyed -eq $false) { continue }
    $def = [string]$(if ($rec.unitDefName) { $rec.unitDefName } else { "" })
    if (-not $def) { continue }
    $defKey = $def.ToLowerInvariant()
    $pocketId = [string]$(if ($rec.pocketId) { $rec.pocketId } else { "" })
    $zoneId = [string]$(if ($rec.zoneId) { $rec.zoneId } else { "" })
    if ($pocketId) {
      $suppress["$defKey|$pocketId"] = $true
    } elseif ($zoneId) {
      $suppress["$defKey|$zoneId"] = $true
    }
  }
  return $suppress
}

function Test-LivingShellPocketOptional {
  param($Pocket)
  if (-not $Pocket) { return $false }
  if ($Pocket.PSObject.Properties["optionalTarget"] -and $Pocket.optionalTarget) { return $true }
  if ($Pocket.PSObject.Properties["highValue"] -and $Pocket.highValue) { return $true }
  $kind = [string]$(if ($Pocket.kind) { $Pocket.kind } else { "" })
  return ($kind -eq "fusion_fort")
}

function Build-LivingShellFromTemplate {
  param($Template, [int]$TeamId, [string]$PrimaryZoneId, [double[]]$PrimaryCenter, [string]$CommanderPolicy = "", $ScarredZones = $null, $DestroyedHvPockets = $null, $HeldInstalls = $null, $ScarSuppress = $null)
  if (-not $DestroyedHvPockets) { $DestroyedHvPockets = @{} }
  if (-not $HeldInstalls) { $HeldInstalls = @{} }
  if (-not $ScarSuppress) { $ScarSuppress = @{} }
  $primaryPocket = $null
  $matchedZone = $false
  $combatPockets = @(@($Template.pockets) | Where-Object { -not (Test-LivingShellPocketOptional $_) })
  if ($combatPockets.Count -lt 1) { $combatPockets = @($Template.pockets) }
  foreach ($pk in @($combatPockets)) {
    if ($pk.primaryCandidate) { $primaryPocket = [string]$pk.pocketId; break }
  }
  if (-not $primaryPocket -and $combatPockets.Count -gt 0) {
    $primaryPocket = [string]($combatPockets[0].pocketId)
  }
  # Prefer pocket whose zone matches the mission target (never a fusion bonus).
  if ($PrimaryZoneId) {
    foreach ($pk in @($combatPockets)) {
      if ([string]$pk.zoneId -eq $PrimaryZoneId) {
        $primaryPocket = [string]$pk.pocketId
        $matchedZone = $true
        break
      }
    }
  }
  # Templates can retain legacy zone ids while the authored map has migrated
  # to a more precise graph. Select the physically nearest combat pocket instead of
  # silently spawning a fusion vault / first pocket at an unrelated objective.
  if (-not $matchedZone -and $PrimaryCenter -and @($PrimaryCenter).Count -ge 2) {
    $bestDistance = [double]::PositiveInfinity
    foreach ($pk in @($combatPockets)) {
      if (-not $pk.center -or @($pk.center).Count -lt 2) { continue }
      $dx = [double]$pk.center[0] - [double]$PrimaryCenter[0]
      $dz = [double]$pk.center[1] - [double]$PrimaryCenter[1]
      $distance = ($dx * $dx) + ($dz * $dz)
      if ($distance -lt $bestDistance) {
        $bestDistance = $distance
        $primaryPocket = [string]$pk.pocketId
      }
    }
    if ($primaryPocket) {
      Write-Host ("Living shell: zone {0} has no pocket — nearest combat pad {1}" -f $PrimaryZoneId, $primaryPocket)
    }
  }
  $selectedPocketCenter = $null
  foreach ($pk in @($Template.pockets)) {
    if ([string]$pk.pocketId -eq [string]$primaryPocket -and $pk.center -and @($pk.center).Count -ge 2) {
      $selectedPocketCenter = @([double]$pk.center[0], [double]$pk.center[1])
      break
    }
  }
  $rebaseDx = 0.0
  $rebaseDz = 0.0
  if ($PrimaryCenter -and $selectedPocketCenter) {
    $rebaseDx = [double]$PrimaryCenter[0] - $selectedPocketCenter[0]
    $rebaseDz = [double]$PrimaryCenter[1] - $selectedPocketCenter[1]
  }
  $pocketCenters = @{}
  foreach ($pk in @($Template.pockets)) {
    if ($pk -and $pk.pocketId -and $pk.center -and @($pk.center).Count -ge 2) {
      $pocketCenters[[string]$pk.pocketId] = @([double]$pk.center[0], [double]$pk.center[1])
    }
  }
  # Pocket zone lookup for scar continuity.
  $pocketZone = @{}
  $pocketMeta = @{}
  foreach ($pk in @($Template.pockets)) {
    if (-not $pk -or -not $pk.pocketId) { continue }
    $pocketZone[[string]$pk.pocketId] = [string]$pk.zoneId
    $pocketMeta[[string]$pk.pocketId] = $pk
  }
  $suppressedPockets = @{}
  $thinnedUnits = 0
  $units = @()
  $coordinateRepairs = 0
  $shellIndex = 0
  $thinIndex = 0
  foreach ($u in @($Template.units)) {
    $uPocket = if ($u.pocketId) { [string]$u.pocketId } else { "" }
    $uZone = if ($u.zoneId) { [string]$u.zoneId } else { "" }
    if (-not $uZone -and $uPocket -and $pocketZone.ContainsKey($uPocket)) {
      $uZone = [string]$pocketZone[$uPocket]
    }
    $uDef = [string]$(if ($u.unitDefName) { $u.unitDefName } elseif ($u.def) { $u.def } else { "" })
    $uDefKey = $uDef.ToLowerInvariant()
    # Exact scar suppress: burned unitDef+pocket stays burned (light raids too).
    if ($uDefKey -and $ScarSuppress -and $ScarSuppress.Count -gt 0) {
      $hit = $false
      if ($uPocket -and $ScarSuppress.ContainsKey("$uDefKey|$uPocket")) { $hit = $true }
      elseif ($uZone -and $ScarSuppress.ContainsKey("$uDefKey|$uZone")) { $hit = $true }
      if ($hit) {
        if ($uPocket) { $suppressedPockets[$uPocket] = $true }
        $thinnedUnits++
        continue
      }
    }
    $scarInfo = $null
    if ($ScarredZones -and $uZone -and $ScarredZones.ContainsKey($uZone)) {
      $scarInfo = $ScarredZones[$uZone]
    }
    $pkMeta = if ($uPocket -and $pocketMeta.ContainsKey($uPocket)) { $pocketMeta[$uPocket] } else { $null }
    $isOptional = $false
    if ($pkMeta) {
      $isOptional = ($pkMeta.PSObject.Properties["optionalTarget"] -and $pkMeta.optionalTarget) `
        -or ($pkMeta.PSObject.Properties["highValue"] -and $pkMeta.highValue) `
        -or ([string]$pkMeta.kind -eq "fusion_fort")
    }
    # Fusion vault continuity: only despawn when the vault itself died.
    # Ambient zone scars / player_bloc used to wipe the whole beamer ring —
    # that felt like the prize teleported out between sorties.
    $hvDead = ($uPocket -and $DestroyedHvPockets.ContainsKey($uPocket))
    $heldByPlayer = $false
    if ($isOptional -and $hvDead) {
      $suppressedPockets[$uPocket] = $true
      $thinnedUnits++
      continue
    }
    if ($scarInfo) {
      $scar = 0.25
      if ($scarInfo.scar) { $scar = [double]$scarInfo.scar }
      $reason = [string]$(if ($scarInfo.reason) { $scarInfo.reason } else { "" })
      if ($reason -eq "vacant") {
        # Nobody holds this ground: no enemy unit of the template stands on it, prize or not.
        if ($uPocket) { $suppressedPockets[$uPocket] = $true }
        $thinnedUnits++
        continue
      }
      if ($isOptional) {
        if ($reason -in @("player_bloc", "claimed")) {
          # Prize stays; ownership flips to the company on re-entry.
          $heldByPlayer = $true
        }
        # Else: contested vault still standing — keep enemy-owned unless HV-dead above.
      } elseif ($reason -in @("claimed", "player_bloc")) {
        # Owned dirt: full wipe enemy occupation. Company pads come back via
        # playerFootprints merge — do not leave residual enemy on the same pad.
        $suppressedPockets[$uPocket] = $true
        $thinnedUnits++
        continue
      } else {
        # Partial combat scars (shell_scar / destroyed_ledger):
        # ALWAYS leave a thin residual — never empty the whole map because a
        # few solars died. Cap effective scar so keepChance stays ≥ ~28%.
        # Use a per-unit thin index (not shellIndex): shellIndex only advances
        # on kept units, so a sticky hash used to wipe the entire remainder.
        $effScar = [Math]::Min([double]$scar, 0.70)
        $keepChance = [Math]::Max(0.28, 1.0 - $effScar)
        $thinIndex++
        $hash = ([Math]::Abs(($thinIndex * 2654435761) % 1000) / 1000.0)
        if ($hash -gt $keepChance) {
          $thinnedUnits++
          continue
        }
      }
    }
    # heldInstallations.owner=player even without claim/scar reason → flip.
    if (-not $heldByPlayer -and $uPocket -and $HeldInstalls) {
      $heldRec = $null
      try { $heldRec = $HeldInstalls.$uPocket } catch { $heldRec = $null }
      if ($heldRec -and [string]$heldRec.owner -eq "player" -and [string]$heldRec.status -ne "destroyed") {
        $heldByPlayer = $true
      }
    }
    $x = [double]$u.x
    $z = [double]$u.z
    # A shell template is normalized to 0..1. Older Rock Jungle data carried
    # a few accidental 1.x coordinates, which put every affected unit beyond
    # the map and made the game appear to spawn them underwater.
    $needsRepair = ($x -lt 0.0 -or $x -gt 1.0 -or $z -lt 0.0 -or $z -gt 1.0)
    if ($needsRepair) {
      $center = $null
      if ($u.pocketId -and $pocketCenters.ContainsKey([string]$u.pocketId)) {
        $center = $pocketCenters[[string]$u.pocketId]
      }
      if ($center) {
        $slot = $shellIndex % 12
        $x = [double]$center[0] + (0.014 * (($slot % 4) - 1.5))
        $z = [double]$center[1] + (0.014 * ([Math]::Floor($slot / 4) - 1.0))
      }
      $coordinateRepairs++
    }
    if ($u.pocketId -and [string]$u.pocketId -eq [string]$primaryPocket -and $selectedPocketCenter) {
      # Keep a selected legacy pocket's formation together, but center it on
      # the current authored target anchor after zone-id migration.
      $x += $rebaseDx
      $z += $rebaseDz
    }
    $x = [Math]::Max(0.04, [Math]::Min(0.96, $x))
    $z = [Math]::Max(0.04, [Math]::Min(0.96, $z))
    $unitDefName = [string]$u.unitDefName
    $keepClass = if ($u.keepClass) { [string]$u.keepClass } else { "static" }
    if ($CommanderPolicy -eq "decoy" -and $unitDefName -match "^(arm|cor|leg)com$") {
      # Greenest is a farm of decoy command nodes. Real commanders would turn
      # the visual fiction into an extra autonomous player and duplicate the
      # economy/AI role. Preserve the installation as a decoy instead.
      $unitDefName = if ($unitDefName -match "^arm") { "armdecom" }
                      elseif ($unitDefName -match "^cor") { "cordecom" }
                      else { "legdecom" }
      $keepClass = "decoy_node"
    }
    $unitRow = [ordered]@{
      unitDefName = $unitDefName
      x = $x
      z = $z
      facing = if ($null -ne $u.facing) { [int]$u.facing } else { 0 }
      zoneId = if ($uZone) { $uZone } elseif ($u.zoneId) { [string]$u.zoneId } else { "" }
      pocketId = if ($u.pocketId) { [string]$u.pocketId } else { "" }
      keepClass = $keepClass
      faction = if ($u.faction) { [string]$u.faction } else { "" }
    }
    if ($heldByPlayer) {
      $unitRow.heldByPlayer = $true
      $unitRow.forceRole = "held_install"
    }
    $units += $unitRow
    $shellIndex++
  }
  if ($thinnedUnits -gt 0) {
    Write-Host ("Living shell continuity: suppressed {0} units on scarred/claimed pads ({1} pockets)" -f `
      $thinnedUnits, $suppressedPockets.Count)
  }
  $pockets = @()
  foreach ($pk in @($Template.pockets)) {
    $zid = [string]$pk.zoneId
    $pocketId = [string]$pk.pocketId
    $scarredPocket = ($ScarredZones -and $zid -and $ScarredZones.ContainsKey($zid))
    $isOptionalPk = ($pk.PSObject.Properties["optionalTarget"] -and $pk.optionalTarget) `
      -or ($pk.PSObject.Properties["highValue"] -and $pk.highValue) `
      -or ([string]$pk.kind -eq "fusion_fort")
    $hvDeadPocket = ($DestroyedHvPockets -and $pocketId -and $DestroyedHvPockets.ContainsKey($pocketId))
    # Drop optional fusion/HV marks only when the vault itself is dead — not
    # when a neighboring combat pad is scarred (that left blown vaults highlighted).
    if ($isOptionalPk -and $hvDeadPocket) { continue }
    $pocketRow = [ordered]@{
      pocketId = $pocketId
      zoneId = [string]$pk.zoneId
      label = [string]$pk.label
      kind = if ($pk.kind) { [string]$pk.kind } else { "mixed" }
      growProfile = if ($pk.growProfile) { [string]$pk.growProfile } else { "" }
      center = @([double]$pk.center[0], [double]$pk.center[1])
      unitCount = if ($null -ne $pk.unitCount) { [int]$pk.unitCount } else { 0 }
      primaryCandidate = [bool]$pk.primaryCandidate
      scarred = [bool]$scarredPocket
    }
    if ($pk.PSObject.Properties["optionalTarget"] -and $pk.optionalTarget) {
      $pocketRow.optionalTarget = $true
    }
    if ($pk.PSObject.Properties["highValue"] -and $pk.highValue) {
      $pocketRow.highValue = $true
    }
    if ([string]$pocketRow.kind -eq "fusion_fort") {
      $pocketRow.optionalTarget = $true
      $pocketRow.highValue = $true
    }
    $pockets += $pocketRow
  }
  return [ordered]@{
    enabled = $true
    templateId = [string]$Template.templateId
    source = if ($Template.source) { [string]$Template.source } else { "unknown" }
    teamID = $TeamId
    primaryZoneId = $PrimaryZoneId
    primaryPocketId = $primaryPocket
    unitCount = $units.Count
    coordinateRepairs = $coordinateRepairs
    # Persistent battlefield doctrine: every authored pocket exists before the
    # first contract starts. Same-map selection only promotes surviving units.
    localPocketOnly = $false
    units = $units
    pockets = $pockets
  }
}

# Kinds that load living-shell occupation when a template exists (outbound 38).
$script:shellCapableKinds = @(
  "eco_raid", "eco_expand", "economy_disrupt", "destroy_key_structure",
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
    $script:shellAllyId = $allyID
    $script:shellFaction = $(if ($sideName -eq "Cortex") { "cortex" } elseif ($sideName -eq "Legion") { "nullmercs" } else { "armada" })
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
    $commanderPolicy = if ([string]$MapId -eq "greenest_fields") { "decoy" } else { "" }
    $scarredZones = Get-ScarredZoneSet -State $state -MapId $MapId
    $destroyedHv = Get-DestroyedHighValuePockets -State $state -MapId $MapId
    $scarSuppress = Get-ScarSuppressSet -State $state -MapId $MapId
    $mapHeld = $null
    if ($state -and $state.PSObject.Properties["heldInstallations"] -and $state.heldInstallations) {
      $mapHeld = $state.heldInstallations.$MapId
    }
    if ($scarredZones.Count -gt 0) {
      Write-Host ("Shell scars on {0}: {1}" -f $MapId, (($scarredZones.Keys | ForEach-Object { "$_=$($scarredZones[$_].reason)" }) -join ", "))
    }
    if ($destroyedHv.Count -gt 0) {
      Write-Host ("Destroyed HV pockets on {0}: {1}" -f $MapId, ($destroyedHv.Keys -join ", "))
    }
    if ($scarSuppress.Count -gt 0) {
      Write-Host ("Exact scar suppress on {0}: {1} keys" -f $MapId, $scarSuppress.Count)
    }
    $script:livingShellPayload = Build-LivingShellFromTemplate -Template $shellTpl `
      -TeamId $teamID -PrimaryZoneId $PrimaryZoneId -PrimaryCenter $EnemyCenter `
      -CommanderPolicy $commanderPolicy -ScarredZones $scarredZones `
      -DestroyedHvPockets $destroyedHv -HeldInstalls $mapHeld `
      -ScarSuppress $scarSuppress
    $script:livingShellPayload = Merge-PlayerFootprintIntoShell -State $state -MapId $MapId `
      -ShellPayload $script:livingShellPayload
    $script:livingShellPayload.commanderPolicy = if ($commanderPolicy) { $commanderPolicy } else { "normal" }
    $script:livingShellPayload.spawnLimit = [int]$script:livingShellPayload.unitCount
    if ($script:livingShellPayload.spawnLimit -lt 1) { $script:livingShellPayload.spawnLimit = 51 }
    if ($intent.openingMission) {
      # Builder historically wrote openingPocketOnly; gadget reads both.
      $script:livingShellPayload.openingPocketOnly = $true
      $script:livingShellPayload.localPocketOnly = $true
    }
    # Prefer payload pockets (already HV-dead filtered) over raw template.
    $occPockets = @($script:livingShellPayload.pockets)
    if ($occPockets.Count -lt 1) { $occPockets = @($shellTpl.pockets) }
    foreach ($pk in $occPockets) {
      $pocketId = [string]$pk.pocketId
      if ($destroyedHv -and $pocketId -and $destroyedHv.ContainsKey($pocketId)) { continue }
      $isPrimary = ($script:livingShellPayload.primaryPocketId -and $pocketId -eq [string]$script:livingShellPayload.primaryPocketId)
      $occ = [ordered]@{
        zoneId = [string]$pk.zoneId
        label = [string]$pk.label
        kind = if ($pk.kind) { [string]$pk.kind } else { "mixed" }
        growProfile = if ($pk.growProfile) { [string]$pk.growProfile } else { "" }
        teamID = $teamID
        preplaced = $true
        primary = [bool]$isPrimary
        pocketId = $pocketId
        livingShell = $true
        commanderPolicy = if ($commanderPolicy) { $commanderPolicy } else { "normal" }
      }
      $isOptional = ($pk.PSObject.Properties["optionalTarget"] -and $pk.optionalTarget) `
        -or ($pk.PSObject.Properties["highValue"] -and $pk.highValue) `
        -or ([string]$pk.kind -eq "fusion_fort")
      if ($isOptional) {
        $occ.optionalTarget = $true
        $occ.highValue = $true
      }
      $script:mapOccupation += $occ
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
# Difficulty by act (data/escalation/difficulty.json): enemy aggression x the act's scale.
$difficultyPath = Join-Path $Workspace "data\escalation\difficulty.json"
if (Test-Path $difficultyPath) {
  try {
    $dif = Get-Content -Raw -LiteralPath $difficultyPath | ConvertFrom-Json
    $actKey = if ($missionNumber -le 5) { "1" } elseif ($missionNumber -le 10) { "2" } else { "3" }
    $arcS = [double]$dif.actScale.$actKey
    if (-not $arcS -or $arcS -le 0) { $arcS = 1.0 }
    $aggro = [double]$dif.enemyAggro
    if (-not $aggro -or $aggro -le 0) { $aggro = 1.0 }
    $arcRamp = 1.0 + 0.03 * [Math]::Max(0, $missionNumber - 5)
    $enemyScale = [Math]::Round([Math]::Min(1.95, [Math]::Max(0.55, $enemyScale * $aggro * $arcS * $arcRamp)), 3)
    Write-Host "Difficulty: act=$actKey aggro=$aggro actScale=$arcS -> enemyScale=$enemyScale"
  } catch { Write-Warning "difficulty.json unreadable: $($_.Exception.Message)" }
}
$devTelemetry = $false
$devPeriod = 150
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
# Aiming at ground where no enemy base stands is establishing presence there: build defensive
# value in that zone (fortify_zone; the gadget measures DV). The target never moves. The enemy
# still stands where its bases are, and anchors on the nearest of them, not on the empty zone.
function Get-StandingPocketZones {
  param([string]$MapId)
  $path = Resolve-LivingShellTemplatePath -Ws $Workspace -MapId $MapId
  if (-not $path) { return $null }  # no template: cannot judge, leave the job alone
  $tpl = Get-Content -Raw -LiteralPath $path | ConvertFrom-Json
  $scarred = Get-ScarredZoneSet -State $state -MapId $MapId
  $deadHv = Get-DestroyedHighValuePockets -State $state -MapId $MapId
  $zones = @{}
  foreach ($pk in @($tpl.pockets)) {
    $zid = [string]$pk.zoneId
    if ($zid -and -not $scarred.ContainsKey($zid) -and -not $deadHv.ContainsKey([string]$pk.pocketId)) { $zones[$zid] = $true }
  }
  return $zones
}
$script:presenceFrom = $null
if (-not $isFinale -and $targetZoneId -and ($script:shellCapableKinds -contains $objectiveKind) -and $objectiveKind -ne "survive_wilds") {
  $standing = Get-StandingPocketZones -MapId ([string]$intent.mapId)
  if ($standing -and $standing.Count -gt 0 -and -not $standing.ContainsKey($targetZoneId)) {
    $script:presenceFrom = $objectiveKind
    $objectiveKind = "fortify_zone"
    $tzLabel = if ($targetZone -and $targetZone.label) { [string]$targetZone.label } else { $targetZoneId }
    if ($intent.objectiveTarget) {
      $intent.objectiveTarget.kind = "fortify_zone"
      $intent.objectiveTarget | Add-Member -NotePropertyName label -NotePropertyValue "Establish presence in $tzLabel" -Force
    }
    $best = $null; $bestD = [double]::MaxValue
    foreach ($zid in @($standing.Keys)) {
      $zc = Get-ZoneCenter (Get-ZoneById $zoneMap $zid) $null
      if ($zc) {
        $d = [Math]::Pow($zc[0] - $enemyCenter[0], 2) + [Math]::Pow($zc[1] - $enemyCenter[1], 2)
        if ($d -lt $bestD) { $best = $zc; $bestD = $d }
      }
    }
    if ($best) { $enemyCenter = $best }
    Write-Host ("Presence: nothing stands in {0}; the job is to establish presence there (was {1})." -f $targetZoneId, $script:presenceFrom)
  }
}
$presenceKind = $objectiveKind -in @("seize_lane", "gate_control", "hold_plateau")
$fortifyKind = $objectiveKind -in @("fortify_zone", "home_founding")
$mapFamily = if ($intent.environment -and $intent.environment.mapFamily) { [string]$intent.environment.mapFamily } else { "tempo" }
# Rock Jungle founding / dig-in: empty deep wilds (raptors only). No Armada/Cortex camps,
# no living-shell scrap occupation, no Null Merc foothold on the shelf.
$againstFaction = ""
if ($intent.PSObject.Properties["against"] -and $intent.against) {
  $againstFaction = [string]$intent.against
} elseif ($intent.PSObject.Properties["worldConflict"] -and $intent.worldConflict -and $intent.worldConflict.primaryEnemy) {
  $againstFaction = [string]$intent.worldConflict.primaryEnemy
}
$journeyId = ""
if ($intent.PSObject.Properties["journey"] -and $intent.journey) { $journeyId = [string]$intent.journey }
$isRockJungle = ([string]$intent.mapId -eq "the_rock_jungle")
$isWildHomeFounding = $isRockJungle -and (
  $fortifyKind -or
  $againstFaction -eq "wild" -or
  $journeyId -eq "home_founding" -or
  $objectiveKind -eq "survive_wilds"
)
if ($isWildHomeFounding) {
  Write-Host "Rock Jungle wild home: empty shelf (raptors only; no empire camps / living-shell scrap)."
}

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
$mercsPresent = ($objectiveKind -ne "hive_clear_or_bypass") -and (-not $isWildHomeFounding)
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

# Same rim rule as player infil — reinforcements / footholds / wild nests stay on edges.
function EdgeScoreNorm([double]$x, [double]$z) {
  return [Math]::Min([Math]::Min($x, 1.0 - $x), [Math]::Min($z, 1.0 - $z))
}
function PushToRim([double[]]$c, [double]$threshold = 0.28) {
  $x = [double]$c[0]; $z = [double]$c[1]
  if ((EdgeScoreNorm $x $z) -le $threshold) { return @((Clamp01 $x), (Clamp01 $z)) }
  for ($i = 0; $i -lt 24; $i++) {
    $toLeft = $x; $toRight = 1.0 - $x; $toTop = $z; $toBottom = 1.0 - $z
    $min = [Math]::Min([Math]::Min($toLeft, $toRight), [Math]::Min($toTop, $toBottom))
    if ($min -eq $toLeft) { $x -= 0.04 }
    elseif ($min -eq $toRight) { $x += 0.04 }
    elseif ($min -eq $toTop) { $z -= 0.04 }
    else { $z += 0.04 }
    $x = Clamp01 $x; $z = Clamp01 $z
    if ((EdgeScoreNorm $x $z) -le $threshold) { break }
  }
  return @($x, $z)
}
$wildCenter = PushToRim @(0.08, 0.50)
# The Rock Jungle's hive stands in its south-west corner (owner call, 2026-10-23): the nest,
# the queen and every new burrow (the raptor startbox) all sit there.
$jungleHiveCenter = Get-ZoneCenter (Get-ZoneById $zoneMap "TRJ_SW_LANE") @(0.14, 0.84)
if ($isRockJungle) { $wildCenter = $jungleHiveCenter }

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
if ($isKings) {
  $playerKit = @()      # the start commander is the company's king; nobody else walks out
} elseif ($openingMission) {
  $playerKit = New-OpeningStrikeTeam $commerce
  Write-Host "Opening kit: mercenary Punch of Thugs + 2 Karkinos + Phobos Vane + durable rez-bot Ketha; no commander suit."
} elseif ($actNum -ge 3 -or $isFinale) {
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
$playerKit = Add-ReserveToKit $playerKit $roster
if ($commerce) {
  $tnb = if ($null -ne $commerce.tenebrium) { $commerce.tenebrium } else { 0 }
  $mk = if ($null -ne $commerce.metalK) { $commerce.metalK } elseif ($null -ne $commerce.credits) { $commerce.credits } else { 0 }
  $depN = if ($commerce.deploy) { @($commerce.deploy).Count } else { 0 }
  Write-Host ("Commerce: Tenebrium={0} metalK={1} deployables={2}" -f $tnb, $mk, $depN)
}
# Stamp banked veteran XP onto kit units (majority retain between rounds).
if ($roster) {
  $playerKit = Apply-CadreXpToKit $playerKit $roster
  $xpStamped = 0
  foreach ($s in @($playerKit)) {
    if ($s -and $null -ne $s.xp -and [double]$s.xp -gt 0) { $xpStamped += 1 }
  }
  if ($xpStamped -gt 0) {
    Write-Host ("Cadre XP stamped on {0} kit unit groups (majority retain)." -f $xpStamped)
  }
}
# Chassis side stays Legion (BAR unit tree); presentation is Ashwalkers.
$baseRecipes = [ordered]@{ ashwalker_player_kit = @($playerKit); legion_player_kit = @($playerKit) }
# Final band after merc / farm modifiers so the card matches the field.
$diffBand = if ($enemyScale -ge 1.6) { "heavy" } elseif ($enemyScale -ge 1.2) { "reinforced" } elseif ($enemyScale -le 0.85) { "light" } else { "standard" }
$difficultyLine = "Expected opposition: $diffBand (scale $enemyScale) | dial $([Math]::Round($difficultyDial, 2))"
if ($isFarmSortie) { $difficultyLine = "$difficultyLine | FARM SORTIE (bonus XP, lighter camp)" }
$extractZone = Get-ZoneById $zoneMap ([string]$intent.extractionZoneId)
$deployLabel = if ($deployZone -and $deployZone.label) { [string]$deployZone.label } else { [string]$intent.deploymentZoneId }
$targetLabel = if ($targetZone -and $targetZone.label) { [string]$targetZone.label } else { [string]$targetZoneId }
$missionCard = New-MissionCard $intent $arcProfile $map.title $description `
  $deployLabel $targetLabel `
  -DifficultyLine $difficultyLine -XpLine $xpLine -HeroLine $heroLine
# G4: stamp hub C&C language onto the in-BAR briefing card
if ($intent.hubChoiceId -or $intent.captureZoneIds -or $intent.deployAces) {
  $capBits = @()
  if ($intent.captureZoneIds) { $capBits = @($intent.captureZoneIds) }
  $secBits = @()
  if ($intent.secondaryCaptureZoneIds) { $secBits = @($intent.secondaryCaptureZoneIds) }
  $aceBits = @()
  if ($intent.deployAces) { $aceBits = @($intent.deployAces) }
  $hubLine = "Required target: $($targetZoneId)"
  if ($secBits.Count -gt 0) { $hubLine = "$hubLine · secondary $($secBits -join ', ')" }
  if ($aceBits.Count -gt 0) { $hubLine = "$hubLine · aces $($aceBits -join '+')" }
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
if ($intent.operationSummary) {
  $missionCard["howItEnds"] = "$($missionCard['howItEnds']) $($intent.operationSummary.bringHome)"
  if ($intent.narrativeContext) {
    $missionCard["situation"] = [string]$intent.narrativeContext.purpose
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
  $swarmSpecs = @(Ring-RaptorGarrison $maxHazard)
  if (-not $AsObjective) {
    # Wild pressure has no objective heart. Same three hives, so the jungle is already occupied.
    $swarmSpecs += Centerpiece-Hives $maxHazard
  }
  $script:baseRecipes["camp${teamID}_swarm"] = $swarmSpecs
  $script:forces += [ordered]@{ id = "camp${teamID}_swarm"; label = "Raptor swarm"; teamID = $teamID; side = "Raptors"; faction = "wild"; role = $(if ($AsObjective) { "garrison" } else { "wild_pressure" }); base = [ordered]@{ x = $Center[0]; z = $Center[1] }; recipe = "camp${teamID}_swarm" }
  $script:ai += [ordered]@{ name = "RaptorsDefenseAI(Verdance)"; shortName = "RaptorsAI"; team = $teamID; version = "<not-versioned>" }
  if ($null -eq $script:wildTeamID) { $script:wildTeamID = $teamID }
}

function Get-HotDrop {
  # outbox\hot_drop.json exists only for a hot-drop launch; its token keeps a stale drop file out.
  $p = Join-Path $Workspace "outbox\hot_drop.json"
  if (!(Test-Path $p)) { return $null }
  try { $hd = Get-Content -Raw -LiteralPath $p | ConvertFrom-Json } catch { return $null }
  if (-not $hd.token) { return $null }
  Write-Host "Hot drop: the company waits off the field until the drop."
  return [ordered]@{ token = [string]$hd.token }
}

function Add-WildDens {
  # Wild ground (the Rock Jungle end to end, the Eye's crater rim): the engine names every den on
  # the intent (intent.wildDens: zone, label, point; none on the hive, none near the pad). Each is
  # a raptor turret -- the wild's defensive value there, so the zone is the wild's until someone
  # out-builds it -- with a pack that moseys between it and the nearest den and a gunship looping
  # wider. Packs carry patrol orders only, so the raptor AI's waves stay its own and these never
  # march on the pad unprompted.
  $dens = @()
  if ($intent.PSObject.Properties["wildDens"] -and $intent.wildDens) { $dens = @($intent.wildDens) }
  if ($dens.Count -eq 0) { return }
  if ($null -eq $script:wildTeamID) { Add-RaptorCamp @([double]$dens[0].x, [double]$dens[0].z) $false "Raptor wild ground" }
  $scale = 1.0 + [Math]::Max(0.0, [Math]::Min(1.0, $maxHazard))
  $n = 0
  foreach ($den in $dens) {
    $c = @([double]$den.x, [double]$den.z)
    $near = @($dens | Where-Object { $_ -ne $den } | Sort-Object { ([double]$_.x - $c[0]) * ([double]$_.x - $c[0]) + ([double]$_.z - $c[1]) * ([double]$_.z - $c[1]) })
    $denPoint = @{ x = $c[0]; z = $c[1] }
    $walk = @($denPoint)
    $fly = @($denPoint)
    if ($near.Count -ge 1) { $walk += @{ x = [double]$near[0].x; z = [double]$near[0].z }; $fly += @{ x = [double]$near[0].x; z = [double]$near[0].z } }
    if ($near.Count -ge 2) { $fly += @{ x = [double]$near[1].x; z = [double]$near[1].z } }
    $n += 1
    $recipe = "wild_den_{0}_{1}" -f [string]$den.zoneId, $n
    $script:baseRecipes[$recipe] = @(
      (Spec "raptor_turret_basic_t2_v1" 1 0 0 120),
      (Spec "raptor_land_swarmer_basic_t1_v1" (Get-ScaledCount 5 $scale) 90 -60 70 -Patrol $walk),
      (Spec "raptor_land_swarmer_basic_t2_v1" (Get-ScaledCount 2 $scale) -110 70 80 -Patrol $walk),
      (Spec "raptor_air_gunship_basic_t2_v1" 1 0 -160 90 -Patrol $fly)
    )
    $label = if ($den.label) { [string]$den.label } else { [string]$den.zoneId }
    $script:forces += [ordered]@{ id = $recipe; label = "Wild den: $label"; teamID = $script:wildTeamID; side = "Raptors"; faction = "wild"; role = "wild_pressure"; zoneId = [string]$den.zoneId; base = [ordered]@{ x = $c[0]; z = $c[1] }; recipe = $recipe }
  }
  Write-Host ("Wild ground: {0} dens." -f $dens.Count)
}

function Get-WarFaction {
  param([string]$Faction)
  if ($Faction -eq "nullmercs") { return @{ T = $MERC; side = "Legion"; label = "Null Mercs" } }
  if ($Faction -eq "cortex") { return @{ T = $FACTION["Cortex"]; side = "Cortex"; label = "Cortex" } }
  return @{ T = $FACTION["Armada"]; side = "Armada"; label = "Armada" }
}

function New-WarTeam {
  param([string]$Faction, [double[]]$Center, [string]$Label, [double]$Rect = 0.16)
  $W = Get-WarFaction $Faction
  $teamID = $script:nextTeam; $script:nextTeam += 1
  $allyID = $script:nextAllyTeam; $script:nextAllyTeam += 1
  $script:allyTeams += [ordered]@{ id = $allyID; startRect = New-StartRect $Center $Rect }
  $script:teams += [ordered]@{ id = $teamID; side = $W.side; allyTeam = $allyID; base = @($Center[0], $Center[1]); rgb = $W.T.rgb; label = "$($W.label) - $Label"; faction = $Faction }
  $script:ai += [ordered]@{ name = "BARb($($W.label) $Label)"; shortName = "BARb"; team = $teamID; version = "<not-versioned>" }
  if ($Faction -eq "armada" -and $null -eq $script:primaryEnemyTeamID) { $script:primaryEnemyTeamID = $teamID; $script:primaryEnemySide = "Armada" }
  return @{ teamID = $teamID; allyID = $allyID; W = $W }
}

function Add-StandingWar {
  # A standing war (Koom, Greenest Fields, Tabula, the Bastion, the Eye): each seat is a BARbarian on
  # its own seat, and the war was baked (tools/war_bake_v1.py), so each seat's units stand exactly
  # where the sim left them, as hurt as it left them, with the bank it held. The company takes the
  # seat the war left empty. Seats on one side are allied; the Mercs are the company's allies or not
  # as its standing with them says.
  param($Theater)
  $camps = @($Theater.camps)
  if ($Theater.PSObject.Properties["wrecks"] -and $Theater.wrecks) { $script:warWrecks = @($Theater.wrecks) }
  $sideAllies = @{}
  foreach ($camp in $camps) {
    $c = @([double]$camp.x, [double]$camp.z)
    $wt = New-WarTeam ([string]$camp.faction) $c ([string]$camp.label)
    if ($camp.PSObject.Properties["profile"] -and $camp.profile) {
      $script:ai[$script:ai.Count - 1].options = [ordered]@{ profile = [string]$camp.profile }
    }
    $byDef = [ordered]@{}
    foreach ($u in @($camp.units)) {
      $d = [string]$u[0]
      if (-not $byDef.Contains($d)) { $byDef[$d] = New-Object System.Collections.Generic.List[double] }
      $byDef[$d].Add([double]$u[1]); $byDef[$d].Add([double]$u[2]); $byDef[$d].Add([double]$u[3]); $byDef[$d].Add([double]$u[4])
    }
    $specs = @()
    foreach ($d in $byDef.Keys) { $specs += (Spec $d ($byDef[$d].Count / 4) 0 0 0 $false $null $null $null $byDef[$d].ToArray()) }
    $field = "war$($wt.teamID)_field"
    $script:baseRecipes[$field] = $specs
    # The Eye (verdance.world.eye_story): Armada's job makes the Cortex camp the target; Cortex's job
    # makes it the company's ally.
    $warRole = "standing_war"
    if ($script:eyeStory -and [string]$camp.faction -eq "cortex") {
      if ([string]$script:eyeStory.kind -eq "raze_camp") { $warRole = "objective_target" }
      if ([string]$script:eyeStory.alliedWith -eq "cortex") {
        $script:alliances += [ordered]@{ allyTeamA = 0; allyTeamB = $wt.allyID; allied = $true }
      }
    }
    $force = [ordered]@{ id = $field; label = "$($wt.W.label) field"; teamID = $wt.teamID; side = $wt.W.side; faction = [string]$camp.faction; role = $warRole; zoneId = [string]$camp.zoneId; base = [ordered]@{ x = $c[0]; z = $c[1] }; recipe = $field }
    if ($camp.PSObject.Properties["bank"] -and $camp.bank) {
      $force.bank = [ordered]@{ metal = [double]$camp.bank.metal; energy = [double]$camp.bank.energy }
    }
    $script:forces += $force
    $f = [string]$camp.faction
    if (-not $sideAllies.ContainsKey($f)) { $sideAllies[$f] = @() }
    $sideAllies[$f] += $wt.allyID
    if ($f -eq "nullmercs" -and $mercsAllied) {
      $script:alliances += [ordered]@{ allyTeamA = 0; allyTeamB = $wt.allyID; allied = $true }
    }
  }
  foreach ($f in $sideAllies.Keys) {
    $ids = @($sideAllies[$f])
    for ($i = 0; $i -lt $ids.Count; $i++) { for ($j = $i + 1; $j -lt $ids.Count; $j++) {
      $script:alliances += [ordered]@{ allyTeamA = $ids[$i]; allyTeamB = $ids[$j]; allied = $true }
    } }
  }
  # The living shell kept beside the war (keepShell) fights on the war's side of its faction.
  if ($null -ne $script:shellAllyId -and $script:shellFaction -and $sideAllies.ContainsKey($script:shellFaction)) {
    foreach ($id in @($sideAllies[$script:shellFaction])) {
      $script:alliances += [ordered]@{ allyTeamA = $script:shellAllyId; allyTeamB = $id; allied = $true }
    }
    if ($script:shellFaction -eq "nullmercs" -and $mercsAllied) {
      $script:alliances += [ordered]@{ allyTeamA = 0; allyTeamB = $script:shellAllyId; allied = $true }
    }
    Write-Host ("Living shell kept beside the war: {0} shell allied to the war's {0}" -f $script:shellFaction)
  }
  Write-Host ("Standing war: {0}" -f (($camps | ForEach-Object { "$($_.faction)@$($_.zoneId)" }) -join " vs "))
  if ($script:eyeStory) { Add-EyeScouts $script:eyeStory }
}

function Add-EyeScouts {
  # The Eye's Armada scouts (verdance.world.eye_story): one Simple AI team per corner the company did
  # not land in, empty at the start (game_verdance_scouts.lua strips the engine's commander and walks
  # the party in at its arrival time). Allied to the company when Armada is the patron.
  param($Story)
  foreach ($p in @($Story.scoutParties)) {
    $c = @([double]$p.x, [double]$p.z)
    $wt = New-WarTeam "armada" $c ("scouts " + [string]$p.zoneId) 0.06
    $script:ai[$script:ai.Count - 1].name = "SimpleAI(Armada scouts $([string]$p.zoneId))"
    $script:ai[$script:ai.Count - 1].shortName = "SimpleAI"
    if ([string]$Story.alliedWith -eq "armada") {
      $script:alliances += [ordered]@{ allyTeamA = 0; allyTeamB = $wt.allyID; allied = $true }
    }
    # The camp the party built over five minutes (tools/eye_scouts_bake_v1.py), placed as it stood.
    $camp = @($p.camp)
    if ($camp.Count -gt 0) {
      $byDef = [ordered]@{}
      foreach ($u in $camp) {
        $d = [string]$u[0]
        if (-not $byDef.Contains($d)) { $byDef[$d] = New-Object System.Collections.Generic.List[double] }
        $byDef[$d].Add([double]$u[1]); $byDef[$d].Add([double]$u[2]); $byDef[$d].Add([double]$u[3]); $byDef[$d].Add([double]$u[4])
      }
      $specs = @()
      foreach ($d in $byDef.Keys) { $specs += (Spec $d ($byDef[$d].Count / 4) 0 0 0 $false $null $null $null $byDef[$d].ToArray()) }
      $rid = "scout$($wt.teamID)_camp"
      $script:baseRecipes[$rid] = $specs
      $script:forces += [ordered]@{ id = $rid; label = "Armada scout camp $([string]$p.zoneId)"; teamID = $wt.teamID; side = "Armada"; faction = "armada"; role = "scout_camp"; zoneId = [string]$p.zoneId; base = [ordered]@{ x = $c[0]; z = $c[1] }; recipe = $rid }
    }
    $script:scoutParties += [ordered]@{
      teamID = $wt.teamID; zoneId = [string]$p.zoneId; x = $c[0]; z = $c[1]
      arriveSeconds = [int]$p.arriveSeconds; units = @($p.units)
    }
  }
  Write-Host ("Eye scouts: {0} Armada parties ({1} hires the company)" -f @($Story.scoutParties).Count, [string]$Story.patron)
}

function Add-Kings {
  # All That Simmers, the kings' showdown: a classic game of BAR. Each rival is a BARbarian on its
  # own seat with its start commander and nothing else; the company's commander is the third
  # king. Everyone is at war with everyone. The kings gadget reports who falls.
  param($Theater)
  $script:kings = @([ordered]@{ teamID = 0; faction = "ashwalkers"; label = "The company" })
  foreach ($k in @($Theater.kings)) {
    $wt = New-WarTeam ([string]$k.faction) @([double]$k.x, [double]$k.z) ([string]$k.label) 0.12
    $script:kings += [ordered]@{ teamID = $wt.teamID; faction = [string]$k.faction; label = "$($wt.W.label) king"; zoneId = [string]$k.zoneId }
  }
  Write-Host ("Kings: {0}" -f (($script:kings | ForEach-Object { $_.faction }) -join ", "))
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
  # SimpleAI supplies its own single commander at game start. Do not add a
  # second commander to the authored recipe: the engine commander is the
  # foothold's builder anchor, while the Ashwalker player kit stays
  # commander-free until the campaign explicitly reaches a base-building act.
  $mercRecipe = @(New-MercFoothold $Scale $patrolTarget[0] $patrolTarget[1] $mfx $mfz $allyP)
  $script:baseRecipes["camp${teamID}_mercs"] = $mercRecipe
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
      (Spec $T.radar 1 0 0 100)
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

function Get-CompanyTravelStructureDefs {
  # Hero bodies and the structures that ship inside their pack. Those travel
  # with the dropping list. Rehydrating them paints a second Solarium (and
  # the rest of that nest) onto wherever they stood last time, often the target.
  param($State)
  $skip = New-Object 'System.Collections.Generic.HashSet[string]'
  if (-not $State -or -not $State.company) { return $skip }
  $packPath = Join-Path $script:Workspace "data\story\crew_packs.json"
  if (-not (Test-Path -LiteralPath $packPath)) { return $skip }
  $doc = $null
  try { $doc = Get-Content -Raw -LiteralPath $packPath | ConvertFrom-Json } catch { return $skip }
  $heroes = $doc.heroes
  if (-not $heroes) { return $skip }
  $ids = @()
  foreach ($k in @("core", "band", "joinedLater")) {
    $bag = $State.company.$k
    if ($bag) { $ids += @($bag) }
  }
  foreach ($raw in $ids) {
    $id = [string]$raw
    if (-not $id -or -not $heroes.PSObject.Properties[$id]) { continue }
    $h = $heroes.$id
    if ($h.unitDef) { [void]$skip.Add(([string]$h.unitDef).ToLower()) }
    if ($h.escorts) {
      foreach ($e in @($h.escorts)) {
        if ($e -and $e.unitDef) { [void]$skip.Add(([string]$e.unitDef).ToLower()) }
      }
    }
  }
  return $skip
}

function Merge-PlayerFootprintIntoShell {
  # Concrete SoT for company-built pads. Living-shell scars/claims suppress
  # enemy occupation; this appends the player's own structures so claimed
  # zones are not empty dirt on the next Drop. Coords are Spring elmos
  # (living_shell.lua shellCoord accepts elmos when value > 1.5).
  # Hero packs are not pads. They spawn from the dropping list, once.
  param($State, [string]$MapId, $ShellPayload)
  if (-not $State -or -not $MapId) { return $ShellPayload }
  $fp = $null
  if ($State.PSObject.Properties["playerFootprints"] -and $State.playerFootprints) {
    $fp = $State.playerFootprints.$MapId
  }
  if (-not $fp -or -not $fp.units) { return $ShellPayload }
  # Footprint-only shell when occupation path skipped (kind/template miss).
  if (-not $ShellPayload) {
    $ShellPayload = [ordered]@{
      enabled = $true
      templateId = "player_footprint_only"
      source = "player_footprints"
      teamID = 1
      primaryZoneId = [string]$(if ($fp.deploymentZoneId) { $fp.deploymentZoneId } else { "" })
      primaryPocketId = ""
      unitCount = 0
      localPocketOnly = $false
      units = @()
      pockets = @()
      spawnLimit = 400
    }
  }
  $units = @()
  if ($ShellPayload.units) { $units = @($ShellPayload.units) }
  $added = 0
  $skippedTravel = 0
  $skippedLattice = 0
  $fpSizeX = 0.0
  $fpSizeZ = 0.0
  $fpBaseline = Join-Path $Workspace "data\scenarios\authored\$MapId.authored_baseline.json"
  if (Test-Path -LiteralPath $fpBaseline) {
    try {
      $fpAuthored = Get-Content -Raw -LiteralPath $fpBaseline | ConvertFrom-Json
      if ($fpAuthored.map) {
        $fpSizeX = [double]$fpAuthored.map.sizeX
        $fpSizeZ = [double]$fpAuthored.map.sizeZ
      }
    } catch {}
  }
  $travelDefs = Get-CompanyTravelStructureDefs $State
  foreach ($u in @($fp.units)) {
    if (-not $u) { continue }
    $def = [string]$(if ($u.unitDefName) { $u.unitDefName } elseif ($u.def) { $u.def } else { "" })
    if (-not $def) { continue }
    if ($travelDefs.Contains($def.ToLower())) {
      $skippedTravel++
      continue
    }
    $x = 0.0; $z = 0.0
    try { $x = [double]$u.x } catch { continue }
    try { $z = [double]$u.z } catch { continue }
    if ($fpSizeX -gt 512 -and $fpSizeZ -gt 512 -and $x -gt 1.5 -and $z -gt 1.5) {
      $dx = [Math]::Abs($x / $fpSizeX - 0.5)
      $dz = [Math]::Abs($z / $fpSizeZ - 0.5)
      $hitX = ([Math]::Abs($dx - 0.007) -lt 0.002) -or ([Math]::Abs($dx - 0.021) -lt 0.002)
      $hitZ = ([Math]::Abs($dz - 0.007) -lt 0.002) -or ([Math]::Abs($dz - 0.021) -lt 0.002)
      if ($hitX -and $hitZ) {
        $skippedLattice++
        continue
      }
    }
    $facing = 0
    try { $facing = [int]$u.facing } catch { $facing = 0 }
    $zoneId = [string]$(if ($u.zoneId) { $u.zoneId } else { "" })
    $units += [ordered]@{
      unitDefName = $def
      x = $x
      z = $z
      facing = $facing
      zoneId = $zoneId
      pocketId = ""
      keepClass = "static"
      heldByPlayer = $true
      forceRole = "player_footprint"
      faction = "ashwalkers"
    }
    $added++
    if ($added -ge 400) { break }
  }
  if ($added -gt 0) {
    $ShellPayload.units = $units
    $ShellPayload.unitCount = $units.Count
    $ShellPayload.enabled = $true
    $curLimit = 0
    try { $curLimit = [int]$ShellPayload.spawnLimit } catch { $curLimit = 0 }
    $ShellPayload.spawnLimit = [Math]::Max($curLimit, $units.Count)
    Write-Host ("Player footprint: rehydrating {0} structures onto living shell" -f $added)
  }
  if ($skippedTravel -gt 0) {
    Write-Host ("Player footprint: left {0} hero-pack structures with the company (not painted onto the map)" -f $skippedTravel)
  }
  if ($skippedLattice -gt 0) {
    Write-Host ("Player footprint: left {0} center-snap ghosts off the map" -f $skippedLattice)
  }
  return $ShellPayload
}

function Ensure-PlayerFootprintShell {
  # When Try-ApplyLivingShell did not run (kind/template miss), still emit a
  # minimal livingShell so company pads from playerFootprints respawn.
  param($State, [string]$MapId, [string]$PrimaryZoneId)
  if ($script:livingShellPayload) {
    $script:livingShellPayload = Merge-PlayerFootprintIntoShell -State $State -MapId $MapId `
      -ShellPayload $script:livingShellPayload
    return $false
  }
  $fp = $null
  if ($State -and $State.PSObject.Properties["playerFootprints"] -and $State.playerFootprints) {
    $fp = $State.playerFootprints.$MapId
  }
  if (-not $fp -or -not $fp.units -or @($fp.units).Count -lt 1) { return $false }
  $payload = Merge-PlayerFootprintIntoShell -State $State -MapId $MapId -ShellPayload $null
  if (-not $payload -or -not $payload.units -or @($payload.units).Count -lt 1) { return $false }
  if ($PrimaryZoneId -and -not $payload.primaryZoneId) {
    $payload.primaryZoneId = $PrimaryZoneId
  }
  $script:livingShellPayload = $payload
  $script:usedShell = $true
  Write-Host ("Player footprint: footprint-only living shell ({0} units)" -f @($payload.units).Count)
  return $true
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
# $usedShell: anything shell-shaped stands (occupation or only the company's footprint).
# $shellOccupied: the living shell's enemy bases stand. Hand-built camps are the fallback for
# the second, not the first: a company footprint is not an enemy base.
$usedShell = $false
$shellOccupied = $false
if ($isWildHomeFounding) {
  # Founding shelf stays empty — player builds the Ashwalker pad; raptors are the only pressure.
  Write-Host "Skipping living-shell occupation on Rock Jungle wild home founding."
} elseif ($theater -and ($isKings -or ($isStandingWar -and -not $keepShell))) {
  Write-Host ("Set piece {0}: no living-shell occupation." -f [string]$theater.kind)
} elseif (($script:shellCapableKinds -contains $objectiveKind) -or $script:presenceFrom) {
  # The enemy's bases stand whatever the job is; a presence job still has the world around it.
  $anchorSide = $enemySide
  if ($objectiveKind -eq "eco_raid" -or $objectiveKind -eq "eco_expand") { $anchorSide = "Armada" }
  if ($objectiveKind -eq "survive_wilds") { $anchorSide = "Legion" }
  if (([string]$intent.mapId) -eq "eye_of_horus" -and $objectiveKind -eq "strike_relay") { $anchorSide = "Cortex" }
  if (([string]$intent.mapId) -eq "ancient_bastion") { $anchorSide = "Armada" }
  $usedShell = Try-ApplyLivingShell -Ws $Workspace -MapId ([string]$intent.mapId) `
    -PrimaryZoneId $targetZoneId -Description $description -EnemyCenter $enemyCenter -AnchorSide $anchorSide
  $shellOccupied = [bool]$usedShell
}
# DRY: company pads always rehydrate when we have a footprint bag — even if
# the occupation shell path skipped (non-capable kind / missing template).
if (-not $usedShell) {
  $fpOnly = Ensure-PlayerFootprintShell -State $state -MapId ([string]$intent.mapId) `
    -PrimaryZoneId $targetZoneId
  if ($fpOnly) { $usedShell = $true }
}

# The field's set piece replaces the usual camps; then the finale setpieces, authored by path
# (no living shell: designed closing battles, not procedural occupation).
if ($isKings) {
  Add-Kings $theater
} elseif ($isStandingWar) {
  Add-StandingWar $theater
} elseif ($isFinale) {
  switch ($finaleKind) {
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
    if (-not $shellOccupied) {
      # The dealer relay sits in a desolate Cortex hideout: jammers everywhere.
      $T = $FACTION[$enemySide]
      $jam = $enemySide -eq "Cortex"
      Add-FactionCamp $enemySide $enemyCenter (Centerpiece-Relay $T) $description -WithEco $true -WithJammers $jam -SupportSpecs (Support-Relay $T) -FrontBand $frontBand
    }
  }
  "destroy_key_structure" {
    # The shell's works in the target zone are the structure to break; the LRPC fort is the
    # fallback when no shell stands there.
    if (-not $shellOccupied) {
      $T = $FACTION[$enemySide]
      Add-FactionCamp $enemySide $enemyCenter (Centerpiece-LRPC $T) $description -WithEco $true -WithProduction $true -SupportSpecs (Support-LRPC $T) -FrontBand $frontBand
    }
  }
  "economy_disrupt" {
    if (-not $shellOccupied) {
      $T = $FACTION[$enemySide]
      Add-FactionCamp $enemySide $enemyCenter (Centerpiece-EcoWorks $T $enemyScale) $description -WithEco $true -FrontBand $frontBand
    }
  }
  "eco_raid" {
    # Living-shell doctrine (outbound 37/44): frozen AI-grown template is required path.
    # Fallback = hand-scattered occupation pockets (36) — DEPRECATED, log loudly.
    if (-not $shellOccupied) {
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
    }
  }
  "hive_clear_or_bypass" {
    # On the Rock Jungle the hive is the south-west nest, wherever the card aimed.
    Add-RaptorCamp $(if ($isRockJungle) { $jungleHiveCenter } else { $enemyCenter }) $true $description
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
    if ($isWildHomeFounding -or $againstFaction -eq "wild") {
      # Empty wilds dig-in / fortify: raptor pressure only (added below via hasWild).
      Write-Host ("Wild objective {0}: no empire faction camp." -f $objectiveKind)
    } elseif (-not $shellOccupied) {
      # Presence objectives (seize_lane / gate_control / siege): shell preferred above.
      # Fallback = thin front-band garrison + reinforcement packs (WO-004).
      $T = $FACTION[$enemySide]
      Add-FactionCamp $enemySide $enemyCenter $null $description -WithEco $false -FrontBand $true
    }
  }
}
}

# Visit tier wardens (verdance.world.visit_tiers): on a living-shell field's second and later visits,
# Armada BARbarians (va_warden) start on the shell's richest pockets and fortify them as the drop runs.
$tierWardens = if ($intent.visitTier -and $intent.visitTier.PSObject.Properties["wardens"]) { @($intent.visitTier.wardens) } else { @() }
if ($shellOccupied -and $tierWardens.Count -gt 0 -and -not $isFinale -and -not $theater) {
  foreach ($wd in $tierWardens) {
    $wc = @([double]$wd.x, [double]$wd.z)
    $wt = New-WarTeam "armada" $wc ("warden " + [string]$wd.zoneId) 0.08
    $script:ai[$script:ai.Count - 1].options = [ordered]@{ profile = "va_warden" }
    $script:teams[$script:teams.Count - 1].handicap = [int]$wd.handicap
    if ($null -ne $script:shellAllyId) {
      $script:alliances += [ordered]@{ allyTeamA = $script:shellAllyId; allyTeamB = $wt.allyID; allied = $true }
    }
  }
  Write-Host ("Visit tier {0}: {1} Armada warden(s) fortifying {2}" -f $intent.visitTier.tier, $tierWardens.Count, (($tierWardens | ForEach-Object { [string]$_.zoneId }) -join ", "))
}

# Drop 3 act-1 texture: roving warband packs on the approach axis.
if (-not $isFinale -and -not $theater -and -not $shellOccupied -and [string]$arcProfile.enemyMode -eq "warband") {
  Add-WarbandPacks $deployCenter $enemyCenter ([Math]::Max(0.6, $enemyScale * 0.8))
}

# Drop 4 escalation: secondary-objective camps at the plan's resolved zones.
# Skip anything that collides with the deploy/target zones or lacks a center.
if ($escSecondaries.Count -gt 0 -and -not $isFinale -and -not $isKings -and $zoneMap -and $zoneMap.zones) {
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
    if ($shellOccupied -and $script:livingShellPayload) {
      # The mark is the shell's own works in that zone (the gadget tags them); no camp is built.
      # The opening only spawns its primary pocket, and a scarred or vault pocket is no mark.
      if ($script:livingShellPayload.localPocketOnly) { continue }
      $secPk = @($script:livingShellPayload.pockets) | Where-Object {
        $_ -and [string]$_.zoneId -eq $secZid -and -not $_.scarred -and -not $_.optionalTarget -and [int]$_.unitCount -gt 0
      } | Select-Object -First 1
      if (-not $secPk) { continue }
      $secZones = @()
      if ($script:livingShellPayload.Contains("secondaryZones")) { $secZones = @($script:livingShellPayload.secondaryZones) }
      $secZones += [ordered]@{ zoneId = $secZid; id = $secId; required = [bool]$sec.required }
      $script:livingShellPayload.secondaryZones = $secZones
      $secMeta = [ordered]@{
        id = $secId; label = $secLabel; required = [bool]$sec.required
        x = [double]$secPk.center[0]; z = [double]$secPk.center[1]
        pocketId = [string]$secPk.pocketId; source = "living_shell_secondary"
      }
      Write-Host ("Secondary objective: {0} ({1}) on the shell works at {2}" -f $secId, $(if ($sec.required) { "REQUIRED" } else { "bonus" }), $secZid)
    } else {
      $secMeta = Add-SecondaryObjectiveCamp $secSide $secCenter ([Math]::Max(0.4, $enemyScale * 0.5)) $secId ([bool]$sec.required) $secLabel
    }
    if ($secMeta) {
      $secMeta.zoneId = $secZid
      $script:secondaryMeta += $secMeta
    }
  }
}

# Living-shell optional high-value pockets (e.g. Greenest center fusion vaults).
# These are already pre-placed in the shell — register bonus secondary meta only
# (required=false). Lua books the fusion keepClass=high_value into the ledger.
if ($script:livingShellPayload -and $script:livingShellPayload.pockets -and -not $isFinale) {
  $seenSec = @{}
  foreach ($sm in @($script:secondaryMeta)) {
    if ($sm -and $sm.id) { $seenSec[[string]$sm.id] = $true }
  }
  foreach ($pk in @($script:livingShellPayload.pockets)) {
    if (-not $pk) { continue }
    $isOptional = ($pk.PSObject.Properties["optionalTarget"] -and $pk.optionalTarget) `
      -or ($pk.PSObject.Properties["highValue"] -and $pk.highValue) `
      -or ([string]$pk.kind -eq "fusion_fort")
    if (-not $isOptional) { continue }
    $secZid = [string]$pk.zoneId
    if (-not $secZid -or $secZid -eq $targetZoneId -or $secZid -eq $deployZoneId) { continue }
    $secId = "bonus_fus_" + ([string]$pk.pocketId).ToLower()
    if ($seenSec.ContainsKey($secId)) { continue }
    $cx = 0.5; $cz = 0.5
    if ($pk.center -and @($pk.center).Count -ge 2) {
      $cx = [double]$pk.center[0]; $cz = [double]$pk.center[1]
    }
    $secLabel = if ($pk.label) { [string]$pk.label } else { $secZid }
    $script:secondaryMeta += [ordered]@{
      id = $secId
      label = $secLabel
      required = $false
      x = $cx
      z = $cz
      zoneId = $secZid
      pocketId = [string]$pk.pocketId
      source = "living_shell_optional"
      highValue = $true
    }
    $seenSec[$secId] = $true
    Write-Host ("Optional high-value mark: {0} at {1} ({2:n2}, {3:n2}) — bonus, not required" -f $secId, $secZid, $cx, $cz)
  }
}

# Drop 3 finale dressing: persistent-base snapshots walk back onto the field.
# Player-bloc zones return as standing team-0 bases; empire zones as thin
# static camps on the primary enemy team. Deploy/target zones stay untouched.
if ($isFinale -and -not $isKings -and $intent.PSObject.Properties["persistentBaseRehydrate"] -and $intent.persistentBaseRehydrate) {
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

# Null Merc foothold: same rim constraint as player infil — enter from an edge
# lane on the flank, not a mid-map pop-in on the deploy→target axis.
if ($mercsPresent -and -not $theater) {
  $axisX = $enemyCenter[0] - $deployCenter[0]
  $axisZ = $enemyCenter[1] - $deployCenter[1]
  $axisLen = [Math]::Sqrt($axisX * $axisX + $axisZ * $axisZ)
  if ($axisLen -lt 0.001) { $axisLen = 0.001 }
  $perpX = -$axisZ / $axisLen
  $perpZ = $axisX / $axisLen
  $midX = ($deployCenter[0] + $enemyCenter[0]) / 2.0
  $midZ = ($deployCenter[1] + $enemyCenter[1]) / 2.0
  $candidates = @(
    (PushToRim @((Clamp01 ($midX + 0.26 * $perpX)), (Clamp01 ($midZ + 0.26 * $perpZ)))),
    (PushToRim @((Clamp01 ($midX - 0.26 * $perpX)), (Clamp01 ($midZ - 0.26 * $perpZ))))
  )
  $mercCenter = $candidates[0]
  $bestScore = -1.0
  foreach ($cand in $candidates) {
    $dxD = $cand[0] - $deployCenter[0]; $dzD = $cand[1] - $deployCenter[1]
    $dxW = $cand[0] - $wildCenter[0]; $dzW = $cand[1] - $wildCenter[1]
    $rimBonus = 1.0 - (EdgeScoreNorm $cand[0] $cand[1])
    $score = [Math]::Min([Math]::Sqrt($dxD * $dxD + $dzD * $dzD), [Math]::Sqrt($dxW * $dxW + $dzW * $dzW)) + (0.35 * $rimBonus)
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
if ($hasWild -and -not $isKings -and $objectiveKind -ne "hive_clear_or_bypass") {
  Add-RaptorCamp $wildCenter $false "Raptor wild pressure"
}
if (-not $isFinale -and -not $isKings) { Add-WildDens }

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

# Stable installation identity is map + authored pocket. It survives candidate
# regeneration and lets Lua retarget a specific pre-existing installation even
# when several pockets share one authored zone.
$installationOrdinal = 0
foreach ($node in @($script:mapOccupation)) {
  $installationOrdinal += 1
  $pocketKey = if ($node.pocketId) { [string]$node.pocketId } else { "zone_$([string]$node.zoneId)_$installationOrdinal" }
  $stableInstallationId = "$([string]$intent.mapId)::$pocketKey"
  if ($node -is [System.Collections.IDictionary]) {
    $node["installationId"] = $stableInstallationId
  } else {
    Add-OrSetProperty $node "installationId" $stableInstallationId
  }
}

# Debrief picks after occupation is known -- point at live camps / extract.
$occupationForPicks = @($script:mapOccupation | Where-Object { -not $_.primary })
$nextMissionCandidates = New-NextMissionCandidates -ZoneMap $zoneMap -AdjForMap $adjForMap `
  -MapId ([string]$intent.mapId) -CurrentTarget $targetZoneId -MissionNumber $missionNumber `
  -Occupation $occupationForPicks -ExtractZone ([string]$intent.extractionZoneId)

# Held fusion vaults under pending aggression → defend sorties first.
# Taking territory generates these: a justified wave that would wipe the pad
# becomes a playable defend contract instead of a silent offscreen delete.
$defendCands = @()
if ($state -and $state.PSObject.Properties["pendingDefendThreats"] -and $state.pendingDefendThreats) {
  $mapThreats = $state.pendingDefendThreats.([string]$intent.mapId)
  if ($mapThreats) {
    foreach ($tp in @($mapThreats.PSObject.Properties)) {
      $threat = $tp.Value
      if (-not $threat) { continue }
      $tz = [string]$(if ($threat.zoneId) { $threat.zoneId } else { "" })
      $tpocket = [string]$(if ($threat.pocketId) { $threat.pocketId } else { $tp.Name })
      if (-not $tz) { continue }
      $defendCands += [ordered]@{
        id = "cand_defend_$tpocket"
        title = "Defend fusion vault — $tz"
        plain = "A response wave is coming for your vault at $tz. Hold the beamer ring — if it falls, the pad is gone."
        mapId = [string]$intent.mapId
        targetZoneId = $tz
        fromZoneIds = @($targetZoneId)
        objectiveArchetype = "defend_install"
        pocketId = $tpocket
        highValue = $true
        defendInstall = $true
        preplaced = $true
        patron = "nullmercs"
        against = "armada"
        hubLabel = "Defend $tz"
      }
    }
  }
}
if ($defendCands.Count -gt 0) {
  $nextMissionCandidates = @($defendCands) + @($nextMissionCandidates)
  Write-Host ("Defend threats armed: {0}" -f (($defendCands | ForEach-Object { $_.pocketId }) -join ", "))
}

# Hero manifest for the HUD/name tags — the hub dropping list only.
# deployAces is core + the packs on this sheet. Do not union crewBand on top
# of it, and do not invent Vane/Ketha when the sheet left them home.
$heroManifest = @()
$hubDeployAcesEarly = @()
if ($intent.deployAces) { $hubDeployAcesEarly = @($intent.deployAces) }
$hubCrewBand = @()
if ($intent.PSObject.Properties["crewBand"] -and $intent.crewBand) { $hubCrewBand = @($intent.crewBand) }
$deployAllow = New-Object 'System.Collections.Generic.HashSet[string]'
if (@($hubDeployAcesEarly).Count -gt 0) {
  foreach ($id in $hubDeployAcesEarly) { if ($id) { [void]$deployAllow.Add([string]$id) } }
} else {
  foreach ($id in $hubCrewBand) { if ($id) { [void]$deployAllow.Add([string]$id) } }
}
if ($roster -and $roster.PSObject.Properties["heroes"] -and $roster.heroes) {
  foreach ($h in $roster.heroes) {
    $hid = [string]$h.heroId
    if (-not $deployAllow.Contains($hid)) { continue }
    $heroManifest += [ordered]@{
      id = $hid
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
# Ensure every deployAllow id appears on the HUD (core + sealed band).
# Roster sheets sometimes omit band packs; crew_packs / characters fill gaps.
$crewPackHeroes = $null
$crewPackPath = Join-Path $Workspace "data\story\crew_packs.json"
if (Test-Path $crewPackPath) {
  try { $crewPackHeroes = (Get-Content $crewPackPath -Raw | ConvertFrom-Json).heroes } catch { $crewPackHeroes = $null }
}
foreach ($needId in @($deployAllow)) {
  $have = $false
  foreach ($hm in $heroManifest) { if ([string]$hm.id -eq $needId) { $have = $true; break } }
  if ($have) { continue }
  $pack = $null
  if ($crewPackHeroes -and $crewPackHeroes.PSObject.Properties[$needId]) {
    $pack = $crewPackHeroes.$needId
  }
  $ch = $null
  if ($state -and $state.characters -and $state.characters.PSObject.Properties[$needId]) {
    $ch = $state.characters.$needId
  }
  $fallbackName = $(if ($needId -eq "vane") { "Ash-Captain Vane" } elseif ($needId -eq "ketha") { "Ketha" } else { $needId })
  $fallbackDef = $(if ($needId -eq "vane") { "legcen" } elseif ($needId -eq "ketha") { "legrezbot" } else { "legcen" })
  $heroManifest += [ordered]@{
    id = [string]$needId
    name = [string]$(if ($pack -and $pack.name) { $pack.name } elseif ($ch -and $ch.name) { $ch.name } else { $fallbackName })
    unitDefName = [string]$(if ($pack -and $pack.unitDef) { $pack.unitDef } elseif ($ch -and $ch.unitDef) { $ch.unitDef } else { $fallbackDef })
    missionCritical = ($needId -eq "ketha") -or ($pack -and $pack.missionCritical -eq $true)
    level = 1
    rank = "Runner"
    xp = 0.0
    campaignXp = 0.0
    hpMult = $(if ($needId -eq "ketha") { 2.5 } elseif ($needId -eq "vane") { 1.65 } else { 1.35 })
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
  $compDef = if ($state.companion.unitDefName) { [string]$state.companion.unitDefName } else { "legcen" }
  $compXp = if ($null -ne $state.companion.xp) { [double]$state.companion.xp } else { 0.0 }
  $bag = Get-CadreXpBag $roster $compDef
  if ($bag -and $bag.xp -gt $compXp) { $compXp = [double]$bag.xp }
  $companions = @([ordered]@{
    id = $state.companion.id
    displayName = $state.companion.displayName
    unitDefName = $compDef
    xp = $compXp
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
# Preserve hub muster band for the gadget (sealed packet — no in-game select).
if (-not $hubCrewBand) { $hubCrewBand = @() }
if ($intent.PSObject.Properties["crewBand"] -and $intent.crewBand) { $hubCrewBand = @($intent.crewBand) }

# Field recruits: belief-field ranked wild heroes for this sortie.
# Marked hub zones (target / infil) collapse attention onto that pad's hero —
# so a Fatboy zone you clicked actually seeds Fatboy, not two random GF wilds.
# Wreck-rez modes stamp spawnAsWreck so BAR seeds a corpse, not a live poof.
$fieldRecruits = @()
$fieldRecruitCap = 2
$markedRecruitZones = @()
if ($intent.captureZoneIds) { $markedRecruitZones += @($intent.captureZoneIds) }
if ($intent.PSObject.Properties["marks"] -and $intent.marks) {
  if ($intent.marks.captureZoneIds) { $markedRecruitZones += @($intent.marks.captureZoneIds) }
  if ($intent.marks.deployZoneId) { $markedRecruitZones += @([string]$intent.marks.deployZoneId) }
}
if ($intent.deploymentZoneId) { $markedRecruitZones += @([string]$intent.deploymentZoneId) }
if ($targetZoneId) { $markedRecruitZones += @([string]$targetZoneId) }
$markedRecruitZones = @($markedRecruitZones | Where-Object { $_ } | Select-Object -Unique)
if ($state -and $state.PSObject.Properties["fieldPool"] -and $state.fieldPool) {
  $sortieMapId = [string]$intent.mapId
  $ranked = @()
  try {
    $env:PYTHONPATH = (Join-Path $Workspace "tools")
    $archForRecruits = [string]($intent.objectiveArchetype)
    if (-not $archForRecruits -and $intent.PSObject.Properties["contractKind"]) {
      $archForRecruits = [string]$intent.contractKind
    }
    $rankArgs = [ordered]@{
      statePath = $StatePath
      workspace = $Workspace
      mapId = $sortieMapId
      limit = $fieldRecruitCap
      markedZoneIds = @($markedRecruitZones)
      objectiveArchetype = $archForRecruits
    }
    $rankArgsPath = Join-Path $env:TEMP ("va_field_recruit_args_{0}.json" -f [guid]::NewGuid().ToString("N"))
    $rankOutPath = Join-Path $env:TEMP ("va_field_recruit_out_{0}.json" -f [guid]::NewGuid().ToString("N"))
    ($rankArgs | ConvertTo-Json -Compress -Depth 5) | Set-Content -LiteralPath $rankArgsPath -Encoding UTF8
    $pyRank = @(
      "import json, sys"
      "from pathlib import Path"
      "sys.path.insert(0, r'" + (Join-Path $Workspace "tools") + "')"
      "from verdance.company.company import field_recruits_for_map"
      "args = json.loads(Path(r'" + $rankArgsPath + "').read_text(encoding='utf-8-sig'))"
      "state = json.loads(Path(args['statePath']).read_text(encoding='utf-8-sig'))"
      "rows = field_recruits_for_map(state, args['mapId'], workspace=Path(args['workspace']), limit=int(args.get('limit') or 2), marked_zone_ids=list(args.get('markedZoneIds') or []), objective_archetype=args.get('objectiveArchetype') or '')"
      "Path(r'" + $rankOutPath + "').write_text(json.dumps({'rows': rows}), encoding='utf-8')"
    ) -join "; "
    & python -c $pyRank
    if (Test-Path -LiteralPath $rankOutPath) {
      $rankPayload = Get-Content -Raw -LiteralPath $rankOutPath | ConvertFrom-Json
      if ($rankPayload -and $rankPayload.PSObject.Properties["rows"]) {
        $ranked = @($rankPayload.rows)
      } else {
        $ranked = @($rankPayload)
      }
    }
    Remove-Item -LiteralPath $rankArgsPath, $rankOutPath -Force -ErrorAction SilentlyContinue
  } catch {
    Write-Host ("Field recruit belief rank failed ({0}); falling back." -f $_.Exception.Message)
    $ranked = @()
  }
  # Fallback: marked-zone first, then any wild on map (old behavior, but prioritized).
  if (-not $ranked -or $ranked.Count -eq 0) {
    $fallback = @()
    foreach ($prop in @($state.fieldPool.PSObject.Properties)) {
      $entry = $prop.Value
      if (-not $entry) { continue }
      if ([string]$entry.status -ne "wild") { continue }
      $recruit = $entry.recruit
      $homeLoc = @(); if ($entry.home) { $homeLoc = @($entry.home) }
      $rMap = $null
      if ($recruit -and $recruit.mapId) { $rMap = [string]$recruit.mapId }
      elseif ($homeLoc.Count -ge 1) { $rMap = [string]$homeLoc[0] }
      if (-not $rMap -or $rMap -ne $sortieMapId) { continue }
      $rZone = $null
      if ($recruit -and $recruit.zoneId) { $rZone = [string]$recruit.zoneId }
      elseif ($homeLoc.Count -ge 2) { $rZone = [string]$homeLoc[1] }
      $pri = if ($rZone -and ($markedRecruitZones -contains $rZone)) { 0 } else { 1 }
      $fallback += [pscustomobject]@{
        pri = $pri
        heroId = [string]$(if ($entry.heroId) { $entry.heroId } else { $prop.Name })
        name = [string]$(if ($entry.name) { $entry.name } else { $prop.Name })
        unitDef = [string]$(if ($entry.unitDef) { $entry.unitDef } else { "legcen" })
        zoneId = $rZone
        recruitMode = [string]$(if ($recruit -and $recruit.type) { $recruit.type } else { "wreck_rez" })
        requiresVictory = [bool]($recruit -and $recruit.requiresVictory)
        optionalJoin = [bool]($recruit -and $recruit.optionalJoin)
        seedXp = $(if ($recruit -and $null -ne $recruit.seedXp) { [double]$recruit.seedXp } else { 0.2 })
        beliefScore = $(if ($pri -eq 0) { 10.0 } else { 0.15 })
        spawnAsWreck = $true
        blurb = $(if ($recruit -and $recruit.blurb) { [string]$recruit.blurb } else { $null })
      }
    }
    $ranked = @($fallback | Sort-Object pri, heroId | Select-Object -First $fieldRecruitCap)
  }
  # Trust company_v1 ranking (already applied limit + marked-zone floor).
  # Re-capping at 2 here used to drop marked wrecks after belief expanded the seat.
  $rankIndex = 0
  foreach ($row in @($ranked)) {
    if (-not $row) { continue }
    $rankIndex++
    $rZone = if ($row.zoneId) { [string]$row.zoneId } else { $null }
    $nx = 0.55; $nz = 0.55
    if ($rZone -and $zoneMap) {
      $fz = Get-ZoneById $zoneMap $rZone
      if ($fz) {
        $fc = Get-ZoneCenter $fz @($enemyCenter[0], $enemyCenter[1])
        if ($fc) { $nx = [double]$fc[0]; $nz = [double]$fc[1] }
      }
    } elseif ($enemyCenter) {
      $nx = [Math]::Min(0.92, [double]$enemyCenter[0] + 0.04)
      $nz = [Math]::Min(0.92, [double]$enemyCenter[1] + 0.04)
    }
    # Spread stacked same-pad wrecks so CreateUnit does not collide.
    $nx = [Math]::Min(0.96, $nx + (($rankIndex - 1) * 0.012))
    $nz = [Math]::Min(0.96, $nz + (($rankIndex - 1) * 0.008))
    $mode = [string]$(if ($row.recruitMode) { $row.recruitMode } else { "wreck_rez" })
    $asWreck = $true
    if ($null -ne $row.spawnAsWreck) { $asWreck = [bool]$row.spawnAsWreck }
    elseif ($mode -notin @("wreck_rez", "retrieve_stash")) { $asWreck = $false }
    $heroDef = [string]$(if ($row.unitDef) { $row.unitDef } elseif ($row.unitDefName) { $row.unitDefName } else { "legcen" })
    $wreckDef = $null
    if ($row.PSObject.Properties["wreckUnitDef"] -and $row.wreckUnitDef) {
      $wreckDef = [string]$row.wreckUnitDef
    }
    $entry = [ordered]@{
      heroId = [string]$row.heroId
      heroName = [string]$(if ($row.name) { $row.name } elseif ($row.heroName) { $row.heroName } else { $row.heroId })
      unitDefName = $heroDef
      zoneId = $rZone
      x = [Math]::Round($nx, 4)
      z = [Math]::Round($nz, 4)
      recruitable = $true
      recruitMode = $mode
      requiresVictory = [bool]$row.requiresVictory
      optionalJoin = [bool]$row.optionalJoin
      heroHpMult = 1.5
      heroXp = $(
        $sx = 0.2
        try {
          if ($null -ne $row.seedXp -and "$($row.seedXp)" -ne "" -and $row.seedXp -isnot [System.Array]) {
            $sx = [double]$row.seedXp
          }
        } catch { $sx = 0.2 }
        [Math]::Round($sx, 3)
      )
      beliefScore = $(
        $bs = 0.0
        try {
          if ($null -ne $row.beliefScore -and "$($row.beliefScore)" -ne "" -and $row.beliefScore -isnot [System.Array]) {
            $bs = [double]$row.beliefScore
          }
        } catch { $bs = 0.0 }
        [Math]::Round($bs, 3)
      )
      spawnAsWreck = $asWreck
      blurb = $(if ($row.blurb) { [string]$row.blurb } else { $null })
    }
    if ($wreckDef) { $entry["wreckUnitDef"] = $wreckDef }
    $fieldRecruits += $entry
  }
}
# People the company left on this map stand where they stood (verdance.belief.manifest.field_people).
$fieldPeople = @()
foreach ($fp in @($(if ($intent.PSObject.Properties["fieldPeople"]) { $intent.fieldPeople } else { @() }))) {
  if (-not $fp -or -not $fp.heroId) { continue }
  $fz = if ($zoneMap) { Get-ZoneById $zoneMap ([string]$fp.zoneId) } else { $null }
  $fc = Get-ZoneCenter $fz @(0.5, 0.5)
  $fieldPeople += [ordered]@{ heroId = [string]$fp.heroId; zoneId = [string]$fp.zoneId; x = [Math]::Round([double]$fc[0], 4); z = [Math]::Round([double]$fc[1], 4) }
}
# A wreck waiting in the wound is the job: raise that hero and the objective is done.
function Get-RezObjective($Recruits, $WoundZoneIds) {
  $wound = @(@($WoundZoneIds) | Where-Object { $_ } | ForEach-Object { [string]$_ })
  foreach ($fr in @($Recruits)) {
    if ($fr -and $fr.zoneId -and $fr.spawnAsWreck -and ($wound -contains [string]$fr.zoneId)) { return $fr }
  }
  return $null
}
$rezObjective = Get-RezObjective $fieldRecruits (@($hubCaptureIds) + @($targetZoneId))
if ($rezObjective) {
  $description = "Raise {0} from the wreck in the wound and bring them home." -f $rezObjective.heroName
  Write-Host ("Rez objective: {0}@{1}" -f $rezObjective.heroId, $rezObjective.zoneId)
  $missionCard["objective"] = "{0} lies wrecked in the wound. Raise them with a rez bot or constructor: that is the job. Then extract." -f $rezObjective.heroName
  $missionCard["plainObjective"] = $description
}
if ($fieldRecruits.Count -gt 0) {
  Write-Host ("Field recruits on {0}: {1} (marks={2})" -f $intent.mapId, `
    (($fieldRecruits | ForEach-Object { "{0}@{1} b={2}" -f $_.heroId, $_.zoneId, $_.beliefScore }) -join ", "), `
    ($markedRecruitZones -join "|"))
}

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
    # The waterline this mission inherits from the planet's water cycle. The
    # gadget applies it at start and flood beats move it from there.
    hydrology = $(if ($intent.PSObject.Properties["hydrology"] -and $intent.hydrology) { $intent.hydrology }
                  else { [ordered]@{ level = 0.0; amplitude = 0.0 } })
    finale = $(if ($isFinale) { $intent.finale } else { $null })
    # faction -> zones it truly holds here. Reinforcements enter only on the map edge inside one
    # of their own zones, out of the player's sight (game_verdance_campaign.lua enemyEntry).
    entryZones = $(if ($intent.PSObject.Properties["entryZones"] -and $intent.entryZones) { $intent.entryZones } else { [ordered]@{} })
    # Hot drop (tools/verdance_kernel/hot_drop.py): the kernel launched this before the player
    # chose who goes. The company waits off the field until the drop file names them.
    hotDrop = $(Get-HotDrop)
    # The doors on this map (zoneId, farMapName, held): drawn on the in-game board.
    doors = @($(if ($intent.PSObject.Properties["doors"] -and $intent.doors) { $intent.doors } else { @() }))
    # The field's set piece, and for a kings' showdown the kings the kings gadget watches.
    theater = $theater
    kings = @($script:kings)
    # Bonds worth something on the field (verdance.company.synergy): the gadget applies a row only
    # when both heroes of the pair drop.
    bondXp = @($(if ($intent.PSObject.Properties["bondXp"] -and $intent.bondXp) { $intent.bondXp } else { @() }))
    bondGifts = @($(if ($intent.PSObject.Properties["bondGifts"] -and $intent.bondGifts) { $intent.bondGifts } else { @() }))
    battlefieldManifest = [ordered]@{
      schemaVersion = "verdance-battlefield-manifest/1.0"
      initializationEndsFrame = 90
      installations = @($script:mapOccupation)
      staticAfterInitialization = $true
    }
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
      # A field recruit lying in the wound: rezzing them is the objective (game_verdance_campaign.lua).
      rezHeroId = $(if ($rezObjective) { [string]$rezObjective.heroId } else { $null })
      # The presence (metal in armed units and defences) a claim needs here (verdance.world.claim):
      # a zone-taking objective completes only once the company stands there with this much.
      claimValue = $(if ($intent.PSObject.Properties["claimValue"] -and $intent.claimValue) { [double]$intent.claimValue } else { 400 })
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
      # Fortify / secure foothold: defensive value = "secured" signal.
      fortifyDefensiveValue = $(if ($fortifyKind) { $(if ($intent.PSObject.Properties["claimValue"] -and $intent.claimValue) { [double]$intent.claimValue } else { 400 }) } else { $null })
      fortifyBuildPower = $(if ($fortifyKind) { 90 } else { $null })
      fortifyArmyValue = $(if ($fortifyKind) { 500 } else { $null })
      fortifyStorageStructures = $(if ($fortifyKind) { 1 } else { $null })
      # Drop 4: surgical | raze (whole camp tagged) | purge (clear the board).
      strength = $objectiveStrength
    }
    # Drop 4: secondary objectives placed this mission (gadget ledger + HUD).
    secondaries = @($script:secondaryMeta)
    hubChoiceId = $hubChoiceIdVal
    deployAces = @($hubDeployAces)
    crewBand = @($hubCrewBand)
    # The hero the player is (first company pick): mission-critical in the field.
    you = $(if ($state -and $state.company -and $state.company.PSObject.Properties["you"] -and $state.company.you) { [string]$state.company.you } else { $null })
    missionCallIns = $(
      if ($intent.PSObject.Properties["missionCallIns"] -and $intent.missionCallIns) {
        @($intent.missionCallIns)
      } else { @() }
    )
    fieldRecruits = @($fieldRecruits)
    fieldPeople = @($fieldPeople)
    # Taking a door: once it is ours the extraction moves onto it (game_verdance_exfil.lua).
    exitDoorZoneId = $(if ($intent.PSObject.Properties["exitDoorZoneId"] -and $intent.exitDoorZoneId) { [string]$intent.exitDoorZoneId } else { $null })
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
    nextMissionCandidates = @($nextMissionCandidates)
    mapOccupation = @($script:mapOccupation)
    livingShell = $(if ($script:livingShellPayload) { $script:livingShellPayload } else { $null })
    warWrecks = @($script:warWrecks)
    scoutParties = @($script:scoutParties)
    jumpGate = $(if ($intent.PSObject.Properties["jumpGate"] -and $intent.jumpGate) { $intent.jumpGate } else { $null })
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
    # Honest flags only — unread carry*/snap*/metal* keys removed (Mode A is
    # soft-continue in-seat, not a restart carry bag).
    continueRules = [ordered]@{
      sameMapContinue = $true
      # Occupied-map / living shell: promote standing pads; never spawnContinueCamp.
      promoteOccupationOnContinue = $true
      clearEnemyOnContinue = $false
      spawnInfrastructureOnContinue = $false
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
    # Per-def veteran XP bank — gadget seeds SetUnitExperience / craft XP on spawn.
    cadreXp = $(
      $cx = [ordered]@{}
      if ($roster -and $roster.PSObject.Properties["cadreXp"] -and $roster.cadreXp) {
        foreach ($p in $roster.cadreXp.PSObject.Properties) {
          $b = $p.Value
          if (-not $b) { continue }
          $cx[[string]$p.Name] = [ordered]@{
            xp = if ($null -ne $b.xp) { [double]$b.xp } else { 0.0 }
            craftXp = if ($null -ne $b.craftXp) { [double]$b.craftXp } else { 0.0 }
            peakXp = if ($null -ne $b.peakXp) { [double]$b.peakXp } else { 0.0 }
            peakCraftXp = if ($null -ne $b.peakCraftXp) { [double]$b.peakCraftXp } else { 0.0 }
            avgXp = if ($null -ne $b.avgXp) { [double]$b.avgXp } else { 0.0 }
            avgCraftXp = if ($null -ne $b.avgCraftXp) { [double]$b.avgCraftXp } else { 0.0 }
          }
        }
      }
      $cx
    )
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
# One call site, so the modoption passthrough cannot be forgotten on one of the four
# branches this replaced.
#
# HASHTABLE, not an array. This is the whole bug that broke every launch path:
# PowerShell splats an array POSITIONALLY and never re-parses its "-Name" strings as
# parameter names -- only a hashtable splat binds by name. With an array, element 4
# ("-Variant") lands on install_playable_slice.ps1's 5th positional parameter,
# [int]$SimFrames, and the binder throws
#   Cannot convert value "-Variant" to type "System.Int32"
# before the installer executes a single statement. $ErrorActionPreference = "Stop"
# turns that into exit 1, the kernel reports "build failed -- not launching", and BAR
# is never started.
$installerArgs = @{
  Workspace        = $Workspace
  ScenarioPath     = $scenarioPath
  Variant          = "alpha_player"
  PlayerController = "human"
  TimeoutSeconds   = $TimeoutSeconds
}
# Rock Jungle / wild home: ~5 min raptor grace (stock mult 1.0). Other maps keep
# the installer's default 2.5 (~15 min) unless ExtraModOptions already sets it.
$extraMods = @()
if ($ExtraModOptions) { $extraMods += $ExtraModOptions }
# Visit tier (verdance.world.visit_tiers): raptor grace and how far into its clock the hive starts.
$tierRaptor = if ($intent.visitTier -and $intent.visitTier.PSObject.Properties["raptor"]) { $intent.visitTier.raptor } else { $null }
if ($tierRaptor) {
  $extraMods += ("va_raptor_grace_seconds={0}" -f [int]$tierRaptor.graceSeconds)
  $extraMods += ("va_raptor_clock_seconds={0}" -f [int]$tierRaptor.clockSeconds)
  Write-Host ("Raptor pace (visit tier {0}): grace {1}s, clock +{2}s" -f $intent.visitTier.tier, $tierRaptor.graceSeconds, $tierRaptor.clockSeconds)
} elseif ($isWildHomeFounding -or ($isRockJungle -and $againstFaction -eq "wild")) {
  if ($extraMods -notmatch "raptor_graceperiodmult=") {
    $extraMods += "raptor_graceperiodmult=0.85"
    Write-Host "Raptor grace: mult=0.85 (~5 min) for Rock Jungle wild home."
  }
}
if ($extraMods.Count -gt 0) {
  $installerArgs.ExtraModOptions = ($extraMods -join ";")
}
if ($Launch)          { $installerArgs.Launch = $true }
if ($SaveGame)        { $installerArgs.SaveGame = $true; $installerArgs.SaveName = $SaveName }
& $installer @installerArgs

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
