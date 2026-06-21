param(
  [string]$Workspace = "$env:USERPROFILE\Documents\BAR_Verdance_Workspace",
  [switch]$ForceNext,
  [switch]$AllowReplay
)
$ErrorActionPreference = "Stop"
. (Join-Path (Split-Path -Parent $MyInvocation.MyCommand.Path) "_common.ps1")
$config = Get-VerdanceConfig -Workspace $Workspace
$resultPath = $config.resultInbox
$statePath = $config.campaignState
$ledgerPath = if ($config.processedLedger) { $config.processedLedger } else { Join-Path $Workspace "ledger\processed_results.json" }

if (!(Test-Path $resultPath)) { throw "No result JSON at $resultPath. Run extract_latest_result first." }
if (!(Test-Path $statePath)) { throw "No campaign state at $statePath. Run install_v06.bat first." }

$resultRaw = Get-Content $resultPath -Raw
$result = $resultRaw | ConvertFrom-Json
$state = Get-Content $statePath -Raw | ConvertFrom-Json

Ensure-Obj $state "graph"
Ensure-Obj $state "reputation"
Ensure-Obj $state "economy"
Ensure-Obj $state "companion"
Ensure-ArrayProp $state "history"

$defaultLedger = [pscustomobject]@{
  schemaVersion = "0.6"
  createdAt = (Get-Date).ToString("s")
  processedMissionKeys = @()
  processedResults = @()
  latestActiveTelemetry = $null
}
$ledger = Read-JsonOrDefault -Path $ledgerPath -Default $defaultLedger
Ensure-ArrayProp $ledger "processedMissionKeys"
Ensure-ArrayProp $ledger "processedResults"
if (-not $ledger.PSObject.Properties["latestActiveTelemetry"]) { $ledger | Add-Member -NotePropertyName latestActiveTelemetry -NotePropertyValue $null }

# Bootstrap idempotency from existing campaign history so upgrading from v0.5 cannot double-process old beads.
$processedKeys = @($ledger.processedMissionKeys)
foreach ($h in @($state.history)) {
  $hStatus = [string]$h.status
  if (Is-TerminalVerdanceStatus $hStatus) {
    $hMission = [string]$h.missionId
    $hNumber = if ($h.PSObject.Properties['missionNumber'] -and $h.missionNumber) { [int]$h.missionNumber } else { Get-MissionNumberFromId $hMission }
    $hKey = "$($state.campaignId)|$hMission|$hNumber"
    if ($processedKeys -notcontains $hKey) { $processedKeys += $hKey }
  }
}
$ledger.processedMissionKeys = $processedKeys

$status = [string]$result.status
$pathSignal = if ($result.pathSignal) { [string]$result.pathSignal } else { [string]$state.pathSignal }
$resultKey = New-VerdanceResultKey $result
$resultHash = Get-ResultHash $result
$isTerminal = Is-TerminalVerdanceStatus $status
$alreadyProcessed = (@($ledger.processedMissionKeys) -contains $resultKey)

function Apply-MissingTelemetryOnly {
  param($State, $Result)
  if ($Result.graph) {
    foreach ($p in $Result.graph.PSObject.Properties) {
      if (-not $State.graph.PSObject.Properties[$p.Name]) { $State.graph | Add-Member -NotePropertyName $p.Name -NotePropertyValue ([double]$p.Value) }
    }
  }
  if ($Result.economy) {
    foreach ($p in $Result.economy.PSObject.Properties) {
      if (-not $State.economy.PSObject.Properties[$p.Name]) { $State.economy | Add-Member -NotePropertyName $p.Name -NotePropertyValue ([double]$p.Value) }
      else { $State.economy.($p.Name) = [double]$p.Value }
    }
  }
  if ($Result.reputation) {
    foreach ($p in $Result.reputation.PSObject.Properties) {
      if (-not $State.reputation.PSObject.Properties[$p.Name]) { $State.reputation | Add-Member -NotePropertyName $p.Name -NotePropertyValue ([double]$p.Value) }
    }
  }
  if ($Result.primaryCompanion) {
    foreach ($p in $Result.primaryCompanion.PSObject.Properties) {
      if (-not $State.companion.PSObject.Properties[$p.Name]) { $State.companion | Add-Member -NotePropertyName $p.Name -NotePropertyValue $p.Value }
    }
  }
}

function Write-CurrentSeedFromState {
  param($State, $Config)
  $nextNumber = if ($State.missionNumber) { [int]$State.missionNumber } else { 1 }
  $nextMissionId = if ($State.currentMissionId) { [string]$State.currentMissionId } else { "va_{0:D3}" -f $nextNumber }
  $pathSignalLocal = if ($State.pathSignal) { [string]$State.pathSignal } else { "B" }
  $zones = @("Ashfields", "Verdant Canopy", "Scaffold Ruins", "Surge Flats", "The Scar")
  $zone = $zones[($nextNumber - 1) % $zones.Count]
  $requiredFrames = 600 + (($nextNumber - 1) * 150)
  if ($requiredFrames -gt 1800) { $requiredFrames = 1800 }
  $title = "Verdance Bridge Mission {0:D3}" -f $nextNumber
  function LuaNum($x) { Format-LuaNumber ([double]$x) }
  $lua = @"
return {
  schemaVersion = "0.6",
  campaignId = "verdance_ashes",
  missionId = "$nextMissionId",
  missionNumber = $nextNumber,
  pathSignal = "$pathSignalLocal",
  title = "$title",
  zone = "$zone",
  objective = {
    id = "hold_bridge_area_$nextNumber",
    kind = "debug_hold",
    requiredFrames = $requiredFrames,
    description = "Hold $zone long enough to thread the next bead."
  },
  economy = {
    metalIncome = $(LuaNum $State.economy.metalIncome),
    energyIncome = $(LuaNum $State.economy.energyIncome),
    buildPower = $(LuaNum $State.economy.buildPower)
  },
  graph = {
    q0_armada_cortex = $(LuaNum $State.graph.q0_armada_cortex),
    q2_void_structure = $(LuaNum $State.graph.q2_void_structure),
    q3_biogenesis_memory = $(LuaNum $State.graph.q3_biogenesis_memory),
    q4_ai_human = $(LuaNum $State.graph.q4_ai_human),
    q6_contested = $(LuaNum $State.graph.q6_contested),
    q6_independent = $(LuaNum $State.graph.q6_independent),
    q7_scarcity = $(LuaNum $State.graph.q7_scarcity)
  },
  reputation = {
    armada = $(LuaNum $State.reputation.armada),
    cortex = $(LuaNum $State.reputation.cortex),
    clans = $(LuaNum $State.reputation.clans),
    nullmercs = $(LuaNum $State.reputation.nullmercs),
    sev = $(LuaNum $State.reputation.sev)
  },
  companions = {
    {
      id = "$($State.companion.id)",
      displayName = "$($State.companion.displayName)",
      unitDefName = "$($State.companion.unitDefName)",
      xp = $(LuaNum $State.companion.xp),
      morale = $(LuaNum $State.companion.morale),
      loyalty = $(LuaNum $State.companion.loyalty),
      stress = $(LuaNum $State.companion.stress),
      autonomy = $(LuaNum $State.companion.autonomy),
      commandMode = "$($State.companion.commandMode)"
    }
  }
}
"@
  New-Item -ItemType Directory -Force -Path (Split-Path -Parent $Config.seedOutbox) | Out-Null
  Set-Content -Encoding ASCII -Path $Config.seedOutbox -Value $lua
  New-Item -ItemType Directory -Force -Path (Split-Path -Parent $Config.seedDestination) | Out-Null
  Set-Content -Encoding ASCII -Path $Config.seedDestination -Value $lua
  Install-VerdanceZoneMap -Config $Config | Out-Null
}

Apply-MissingTelemetryOnly -State $state -Result $result

if ($isTerminal -and $alreadyProcessed -and -not $AllowReplay) {
  Write-Host "Duplicate terminal result detected. No campaign mutation performed."
  Write-Host "Result key: $resultKey"
  Write-Host "Result hash: $resultHash"
  Write-CurrentSeedFromState -State $state -Config $config
  Save-Json $ledger $ledgerPath
  Save-Json $state $statePath
  Write-Host "Reinstalled current seed from existing state: $($state.currentMissionId)"
  exit 0
}

if (-not $isTerminal -and -not $ForceNext) {
  $ledger.latestActiveTelemetry = [pscustomobject]@{
    time = (Get-Date).ToString("s")
    resultKey = $resultKey
    resultHash = $resultHash
    missionId = $result.missionId
    status = $status
    holdFrames = [int]$result.holdFrames
    requiredFrames = [int]$result.requiredFrames
  }
  Save-Json $ledger $ledgerPath
  Save-Json $state $statePath
  Write-CurrentSeedFromState -State $state -Config $config
  Write-Host "Active/nonterminal result recorded as telemetry only. No mission increment."
  Write-Host "Result key: $resultKey"
  exit 0
}

# Apply terminal outcome deltas. ForceNext can also pass through here for active debug advancement.
$g = $state.graph
$r = $state.reputation
$c = $state.companion

if ($status -eq "victory" -or ($ForceNext -and -not $isTerminal)) {
  $g.q6_contested = Clamp-Number ([double]$g.q6_contested - 0.06) 0 1
  if ($pathSignal -eq "B") { $g.q6_independent = Clamp-Number ([double]$g.q6_independent + 0.05) 0 1 }
  $r.clans = Clamp-Number ([double]$r.clans + 4) 0 100
  $r.nullmercs = Clamp-Number ([double]$r.nullmercs + 2) 0 100
  $r.sev = Clamp-Number ([double]$r.sev + 2) 0 100
  $c.xp = Clamp-Number ([double]$c.xp + 0.08) 0 99
  $c.morale = Clamp-Number ([double]$c.morale + 4) 0 100
  $c.loyalty = Clamp-Number ([double]$c.loyalty + 2) 0 100
  $c.stress = Clamp-Number ([double]$c.stress - 3) 0 100
} elseif ($status -eq "partial") {
  $g.q6_contested = Clamp-Number ([double]$g.q6_contested - 0.02) 0 1
  if ($pathSignal -eq "B") { $g.q6_independent = Clamp-Number ([double]$g.q6_independent + 0.02) 0 1 }
  $r.clans = Clamp-Number ([double]$r.clans + 1) 0 100
  $r.sev = Clamp-Number ([double]$r.sev + 1) 0 100
  $c.xp = Clamp-Number ([double]$c.xp + 0.04) 0 99
  $c.morale = Clamp-Number ([double]$c.morale + 1) 0 100
  $c.stress = Clamp-Number ([double]$c.stress + 2) 0 100
} elseif ($status -eq "defeat" -or $status -eq "failed" -or $status -eq "aborted") {
  $g.q6_contested = Clamp-Number ([double]$g.q6_contested + 0.04) 0 1
  if ($pathSignal -eq "B") { $g.q6_independent = Clamp-Number ([double]$g.q6_independent - 0.03) 0 1 }
  $r.clans = Clamp-Number ([double]$r.clans - 3) 0 100
  $r.sev = Clamp-Number ([double]$r.sev - 2) 0 100
  $c.xp = Clamp-Number ([double]$c.xp + 0.02) 0 99
  $c.morale = Clamp-Number ([double]$c.morale - 5) 0 100
  $c.stress = Clamp-Number ([double]$c.stress + 6) 0 100
}

$bead = [ordered]@{
  time = (Get-Date).ToString("s")
  resultKey = $resultKey
  resultHash = $resultHash
  missionId = $result.missionId
  missionNumber = Get-ResultMissionNumber $result
  status = $status
  pathSignal = $pathSignal
  holdFrames = [int]$result.holdFrames
  requiredFrames = [int]$result.requiredFrames
  q6_contested = [double]$g.q6_contested
  q6_independent = [double]$g.q6_independent
  companionXp = [double]$c.xp
}
$history = @($state.history)
$history += [pscustomobject]$bead
$state.history = $history

$currentNumber = if ($state.missionNumber) { [int]$state.missionNumber } else { Get-ResultMissionNumber $result }
$resultNumber = Get-ResultMissionNumber $result
$nextNumber = [Math]::Max($currentNumber, $resultNumber + 1)
$nextMissionId = "va_{0:D3}" -f $nextNumber
if ($state.PSObject.Properties["schemaVersion"]) { $state.schemaVersion = "0.6" } else { $state | Add-Member -NotePropertyName schemaVersion -NotePropertyValue "0.6" }
$state.missionNumber = $nextNumber
$state.currentMissionId = $nextMissionId
$state.pathSignal = $pathSignal

if ($isTerminal) {
  $keys = @($ledger.processedMissionKeys)
  if ($keys -notcontains $resultKey) { $keys += $resultKey }
  $ledger.processedMissionKeys = $keys
}
$records = @($ledger.processedResults)
$records += [pscustomobject]@{
  time = (Get-Date).ToString("s")
  resultKey = $resultKey
  resultHash = $resultHash
  missionId = $result.missionId
  missionNumber = $resultNumber
  status = $status
  advancedTo = $nextMissionId
}
$ledger.processedResults = $records

Write-CurrentSeedFromState -State $state -Config $config
Save-Json $state $statePath
Save-Json $ledger $ledgerPath

Write-Host "Campaign cycle complete."
Write-Host "Processed result key: $resultKey"
Write-Host "Result status: $status"
Write-Host "Current mission seed: $nextMissionId"
Write-Host "Wrote state: $statePath"
Write-Host "Wrote seed outbox: $($config.seedOutbox)"
Write-Host "Installed seed to BAR: $($config.seedDestination)"
