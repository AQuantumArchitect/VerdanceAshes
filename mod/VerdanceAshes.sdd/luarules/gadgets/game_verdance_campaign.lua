local gadget = gadget

function gadget:GetInfo()
  return {
    name = "Verdance Campaign Bridge",
    desc = "Campaign bridge and objective automation for Verdance's Ashes",
    author = "ChatGPT / Claude / Luke Spooner",
    date = "2026-07-05",
    license = "GPL v2 or later",
    layer = 0,
    enabled = true,
  }
end

if not gadgetHandler:IsSyncedCode() then
  -- Unsynced bridge: forward synced telemetry/mission events to LuaUI widgets.
  function gadget:Initialize()
    gadgetHandler:AddSyncAction("VERDANCE_TELEMETRY", function(_, jsonStr)
      if Script.LuaUI and Script.LuaUI.VerdanceTelemetry then
        Script.LuaUI.VerdanceTelemetry(jsonStr)
      end
    end)
    gadgetHandler:AddSyncAction("VERDANCE_MISSION_EVENT", function(_, eventStatus, reason)
      if Script.LuaUI and Script.LuaUI.VerdanceMissionEvent then
        Script.LuaUI.VerdanceMissionEvent(eventStatus, reason)
      end
    end)
  end
  function gadget:Shutdown()
    gadgetHandler:RemoveSyncAction("VERDANCE_TELEMETRY")
    gadgetHandler:RemoveSyncAction("VERDANCE_MISSION_EVENT")
  end
  return
end

local mission
local zoneMap
local status = "inactive"
local holdFrames = 0
local debugAutoProgress = 0
local spawnedCompanions = {}
local lastProgressFrame = 0
local headlessAutoStart = false
local headlessFastWin = false
local headlessQuit = false
local headlessStarted = false
local headlessQuitFrame = nil
local playableSetupSpawned = false
local balanceExportFrame = nil
local balanceExported = false
local balanceQuitAfterExport = false
-- Fibonacci multi-milestone profiler
local fibMilestones = {}    -- sorted list of frame numbers
local fibMilestoneIdx = 1   -- pointer to next due milestone
local fibQuitAfterLast = false

-- Objective automation
local CHECK_PERIOD = 30                 -- frames between objective checks
local EXTRACTION_HOLD_FRAMES = 450      -- 15s presence in extraction zone
local PRESENCE_HOLD_DEFAULT = 900       -- 30s hold for seize/gate objectives
local WIPE_GRACE_FRAMES = 900           -- no wipe-defeat before 30s

local DESTRUCTION_KINDS = {
  strike_relay = true,
  destroy_key_structure = true,
  economy_disrupt = true,
  hive_clear_or_bypass = true,
}
local PRESENCE_KINDS = { seize_lane = true, gate_control = true }
local CHOICE_KINDS = { choose_target_then_extract = true }

local playerTeamID = 0
local playerAllyTeamID = 0
local gaiaTeamID = -1
local gaiaAllyTeamID = -1
local teamAllyTeam = {}                 -- teamID -> allyTeamID
local objectiveTargets = {}             -- unitID -> forceId (objective_target structures)
local objectiveTargetCount = 0
local objectiveTargetsDestroyed = 0
local targetForceStructures = {}        -- forceId -> live structure count
local objectiveComplete = false
local objectiveBypassed = false
local chosenTargetForceId = nil
local zoneHoldFrames = 0
local extractionHoldFrames = 0
local extractionClean = true
local playerLeftExtraction = false
local playerCommanders = {}             -- unitID -> true
local sawPlayerCommander = false
local terminal = false
local terminalReason = ""
local targetZoneRect = nil              -- {x1, z1, x2, z2} in elmos
local extractionZoneRect = nil
local debugAutoProgressAllowed = false

local function clamp(x, lo, hi)
  if x < lo then return lo end
  if x > hi then return hi end
  return x
end

local function truthy(v)
  if v == true or v == 1 then return true end
  if type(v) == "string" then
    v = v:lower()
    return v == "1" or v == "true" or v == "yes" or v == "enabled"
  end
  return false
end

local function esc(s)
  s = tostring(s or "")
  s = s:gsub('\\', '\\\\')
  s = s:gsub('"', '\\"')
  return s
end

local function jstr(s) return '"' .. esc(s) .. '"' end
local function jnum(x, digits)
  x = tonumber(x) or 0
  if digits then return string.format("%." .. digits .. "f", x) end
  return tostring(math.floor(x + 0.5))
end

local function readMission()
  local ok, data = pcall(VFS.Include, "singleplayer/verdance_ashes/generated/va_current.lua")
  if ok and type(data) == "table" then return data end
  ok, data = pcall(VFS.Include, "singleplayer/verdance_ashes/generated/va_001.lua")
  if ok and type(data) == "table" then return data end
  return {
    schemaVersion = "0.6",
    campaignId = "verdance_ashes",
    missionId = "va_missing_seed",
    missionNumber = 0,
    pathSignal = "B",
    zone = "Unknown",
    objective = { requiredFrames = 600, description = "Missing mission seed fallback" },
    economy = { metalIncome = 0, energyIncome = 0, buildPower = 0 },
    graph = {},
    reputation = {},
    companions = {}
  }
end

local function readZoneMap()
  local ok, data = pcall(VFS.Include, "singleplayer/verdance_ashes/generated/zone_map_current.lua")
  if ok and type(data) == "table" then return data end
  return nil
end

local function zoneCount()
  if not zoneMap or type(zoneMap.zones) ~= "table" then return 0 end
  return #zoneMap.zones
end

local function normalizedToElmos(v, size)
  v = tonumber(v) or 0
  if v <= 1 then return math.floor(v * (size or 0) + 0.5) end
  return math.floor(v + 0.5)
end

local function zoneMapJson()
  return table.concat({
    '"mapId":' .. jstr(zoneMap and zoneMap.mapId or ""),
    '"mapName":' .. jstr(zoneMap and zoneMap.mapName or ""),
    '"coordinateSystem":' .. jstr(zoneMap and zoneMap.coordinateSystem or ""),
    '"zoneCount":' .. jnum(zoneCount())
  }, ',')
end

local function echoZones()
  if not zoneMap or type(zoneMap.zones) ~= "table" then
    Spring.Echo("VA_ZONES none loaded")
    return
  end
  local sx = Game.mapSizeX or 0
  local sz = Game.mapSizeZ or 0
  Spring.Echo("VA_ZONES mapId=" .. tostring(zoneMap.mapId or "unknown") .. " map=" .. tostring(Game.mapName or "unknown") .. " count=" .. tostring(#zoneMap.zones) .. " size=" .. tostring(sx) .. "x" .. tostring(sz))
  for _, z in ipairs(zoneMap.zones) do
    local b = z.bounds or {}
    local x1 = normalizedToElmos(b.xMin, sx)
    local x2 = normalizedToElmos(b.xMax, sx)
    local z1 = normalizedToElmos(b.zMin, sz)
    local z2 = normalizedToElmos(b.zMax, sz)
    Spring.Echo("VA_ZONE " .. tostring(z.zoneId or "?") .. " label=" .. tostring(z.label or "") .. " bounds=" .. x1 .. "," .. z1 .. ".." .. x2 .. "," .. z2)
  end
end

local function companionCounts()
  local total = 0
  local alive = 0
  if mission and mission.companions then total = #mission.companions end
  if total == 0 then return 0, 0 end
  for _, comp in ipairs(mission.companions) do
    if comp._unitID and Spring.ValidUnitID(comp._unitID) and not Spring.GetUnitIsDead(comp._unitID) then
      alive = alive + 1
    elseif not comp._unitID then
      alive = alive + 1
    end
  end
  return alive, total
end

local function primaryCompanionJson()
  local c = mission and mission.companions and mission.companions[1] or {}
  return table.concat({
    '"id":' .. jstr(c.id or ""),
    '"displayName":' .. jstr(c.displayName or ""),
    '"unitDefName":' .. jstr(c.unitDefName or ""),
    '"xp":' .. jnum(c.xp or 0, 4),
    '"morale":' .. jnum(c.morale or 0, 2),
    '"loyalty":' .. jnum(c.loyalty or 0, 2),
    '"stress":' .. jnum(c.stress or 0, 2),
    '"autonomy":' .. jnum(c.autonomy or 0, 4),
    '"commandMode":' .. jstr(c.commandMode or "hybrid")
  }, ',')
end

local function graphJson()
  local g = mission.graph or {}
  return table.concat({
    '"q0_armada_cortex":' .. jnum(g.q0_armada_cortex or 0, 4),
    '"q2_void_structure":' .. jnum(g.q2_void_structure or 0, 4),
    '"q3_biogenesis_memory":' .. jnum(g.q3_biogenesis_memory or 0, 4),
    '"q4_ai_human":' .. jnum(g.q4_ai_human or 0, 4),
    '"q6_contested":' .. jnum(g.q6_contested or 0, 4),
    '"q6_independent":' .. jnum(g.q6_independent or 0, 4),
    '"q7_scarcity":' .. jnum(g.q7_scarcity or 0, 4)
  }, ',')
end

local function reputationJson()
  local r = mission.reputation or {}
  return table.concat({
    '"armada":' .. jnum(r.armada or 0, 2),
    '"cortex":' .. jnum(r.cortex or 0, 2),
    '"clans":' .. jnum(r.clans or 0, 2),
    '"nullmercs":' .. jnum(r.nullmercs or 0, 2),
    '"sev":' .. jnum(r.sev or 0, 2)
  }, ',')
end

local function economyJson()
  local e = mission.economy or {}
  return table.concat({
    '"metalIncome":' .. jnum(e.metalIncome or 0, 2),
    '"energyIncome":' .. jnum(e.energyIncome or 0, 2),
    '"buildPower":' .. jnum(e.buildPower or 0, 2)
  }, ',')
end

local objectiveCompleteHow = ""

local function extractionStatusString()
  if not terminal then return "" end
  if extractionHoldFrames >= EXTRACTION_HOLD_FRAMES then
    return extractionClean and "clean" or "contested"
  end
  return ""
end

-- Objective credit is only reported on non-defeat outcomes: the story engine
-- treats any completed/destroyed objective as a success signal for graph deltas.
local function objectiveCredited()
  return objectiveComplete and status ~= "defeat"
end

local function destroyedObjectiveIdsJson()
  local oid = mission.objective and mission.objective.id
  if oid and objectiveCredited() and objectiveCompleteHow ~= "zone_held" then
    return '[' .. jstr(oid) .. ']'
  end
  return '[]'
end

local function objectiveResultsJson()
  local obj = mission.objective or {}
  if not obj.id then return '[]' end
  local objStatus = "incomplete"
  if objectiveCredited() then
    objStatus = (objectiveCompleteHow == "zone_held") and "complete" or "destroyed"
  end
  local damage = 0
  if objectiveTargetCount > 0 then
    damage = objectiveTargetsDestroyed / objectiveTargetCount
  elseif objectiveCredited() then
    damage = 1
  end
  return '[{' .. table.concat({
    '"objectiveId":' .. jstr(obj.id),
    '"kind":' .. jstr(obj.kind or ""),
    '"status":' .. jstr(objStatus),
    '"damage":' .. jnum(damage, 3),
  }, ',') .. '}]'
end

local function resultJson()
  local alive, total = companionCounts()
  local req = mission.objective and mission.objective.requiredFrames or 600
  local frame = Spring.GetGameFrame() or 0
  return '{' .. table.concat({
    '"schemaVersion":' .. jstr(mission.schemaVersion or "0.6"),
    '"campaignId":' .. jstr(mission.campaignId or "verdance_ashes"),
    '"missionId":' .. jstr(mission.missionId or "va_unknown"),
    '"missionNumber":' .. jnum(mission.missionNumber or 0),
    '"pathSignal":' .. jstr(mission.pathSignal or "B"),
    '"status":' .. jstr(status),
    '"resultKey":' .. jstr((mission.campaignId or "verdance_ashes") .. "|" .. (mission.missionId or "va_unknown") .. "|" .. tostring(mission.missionNumber or 0)),
    '"holdFrames":' .. jnum(holdFrames),
    '"requiredFrames":' .. jnum(req),
    '"frame":' .. jnum(frame),
    '"elapsedMinutes":' .. jnum(frame / 1800.0, 2),
    '"deploymentMapId":' .. jstr(mission.deploymentMapId or ""),
    '"mapId":' .. jstr(mission.deploymentMapId or ""),
    '"terminalReason":' .. jstr(terminalReason),
    '"objectiveComplete":' .. tostring(objectiveComplete == true),
    '"objectiveBypassed":' .. tostring(objectiveBypassed == true),
    '"extractionStatus":' .. jstr(extractionStatusString()),
    '"extractionZoneId":' .. jstr(mission.extractionZoneId or (mission.objective and mission.objective.extractionZoneId) or ""),
    '"chosenTargetForceId":' .. jstr(chosenTargetForceId or ""),
    '"destroyedObjectiveIds":' .. destroyedObjectiveIdsJson(),
    '"objectiveResults":' .. objectiveResultsJson(),
    '"companionsAlive":' .. jnum(alive),
    '"companionsTotal":' .. jnum(total),
    '"debugAutoProgress":' .. jnum(debugAutoProgress),
    '"map":{"name":' .. jstr(Game.mapName or "") .. ',"sizeX":' .. jnum(Game.mapSizeX or 0) .. ',"sizeZ":' .. jnum(Game.mapSizeZ or 0) .. '}',
    '"zoneMap":{' .. zoneMapJson() .. '}',
    '"economy":{' .. economyJson() .. '}',
    '"graph":{' .. graphJson() .. '}',
    '"reputation":{' .. reputationJson() .. '}',
    '"primaryCompanion":{' .. primaryCompanionJson() .. '}'
  }, ',') .. '}'
end

local function echoStatus()
  local req = mission.objective and mission.objective.requiredFrames or 600
  Spring.Echo("VA_STATUS mission=" .. tostring(mission.missionId) .. " status=" .. status .. " hold=" .. holdFrames .. "/" .. req .. " auto=" .. debugAutoProgress)
end

local function logJsonChunked(prefix, json)
  local chunkSize = 180
  local total = math.ceil(#json / chunkSize)
  if total < 1 then total = 1 end
  Spring.Echo(prefix .. "_BEGIN")
  for i = 1, total do
    local a = ((i - 1) * chunkSize) + 1
    local b = i * chunkSize
    Spring.Echo(prefix .. "_CHUNK " .. tostring(i) .. "/" .. tostring(total) .. " " .. json:sub(a, b))
  end
  Spring.Echo(prefix .. "_END")
end

local function logResult()
  local json = resultJson()
  Spring.Echo("VA_RESULT_JSON_COMPACT " .. json)
  logJsonChunked("VA_RESULT_JSON", json)
  echoStatus()
end

local function finishHeadlessResult(outcome)
  local req = mission.objective and mission.objective.requiredFrames or 600
  status = outcome or "victory"
  holdFrames = req
  debugAutoProgress = 0
  terminal = true
  terminalReason = "headless_fastwin"
  Spring.SetGameRulesParam("va_hold_frames", holdFrames, { public = true })
  Spring.Echo("VA_HEADLESS_RESULT_READY mission=" .. tostring(mission.missionId) .. " status=" .. status)
  logResult()
  if headlessQuit then
    headlessQuitFrame = Spring.GetGameFrame() + 2
  end
end

local function startMission()
  status = "active"
  holdFrames = 0
  debugAutoProgress = debugAutoProgressAllowed and 1 or 0
  lastProgressFrame = Spring.GetGameFrame()
  Spring.SetGameRulesParam("va_status", status, { public = true })
  Spring.Echo("VA_START " .. tostring(mission.missionId) .. " zone=" .. tostring(mission.zone or "unknown"))
  echoStatus()
end

local function progress(frames)
  if status == "inactive" then status = "active" end
  holdFrames = holdFrames + (frames or 300)
  local req = mission.objective and mission.objective.requiredFrames or 600
  if holdFrames >= req and status == "active" then status = "victory" end
  echoStatus()
end

local function spawnCompanions()
  if not mission.companions then return end
  local teamID = 0
  local x, y, z = 1000, 100, 1000
  for i, comp in ipairs(mission.companions) do
    local defName = comp.unitDefName or "armwar"
    local unitID = Spring.CreateUnit(defName, x + i * 80, y, z + i * 80, 0, teamID)
    comp._unitID = unitID
    if unitID then
      Spring.SetUnitRulesParam(unitID, "va_companion", 1, { public = true })
      Spring.SetUnitRulesParam(unitID, "va_companion_xp", comp.xp or 0, { public = true })
      Spring.SetUnitRulesParam(unitID, "va_companion_morale", comp.morale or 0, { public = true })
      if Spring.SetUnitExperience then Spring.SetUnitExperience(unitID, comp.xp or 0) end
    end
  end
  Spring.Echo("VA_SPAWN companions=" .. tostring(#mission.companions))
end

local function unitDefName(defID)
  local ud = UnitDefs[defID]
  return ud and ud.name or tostring(defID or "unknown")
end

local function unitDefMetal(defID)
  local ud = UnitDefs[defID]
  return tonumber(ud and ud.metalCost or 0) or 0
end

local function isBuilder(defID)
  local ud = UnitDefs[defID]
  return ud and (tonumber(ud.buildSpeed or 0) or 0) > 0
end

local function isStructure(defID)
  local ud = UnitDefs[defID]
  return ud and (ud.isBuilding or ud.isFactory or ud.speed == 0)
end

local function canFight(defID)
  local ud = UnitDefs[defID]
  if not ud then return false end
  if ud.canAttack then return true end
  return ud.weapons and #ud.weapons > 0
end

local function metalSpotKey(spot)
  return tostring(math.floor((spot.x or 0) + 0.5)) .. "|" .. tostring(math.floor((spot.z or 0) + 0.5))
end

local function metalSpotHasUnit(spot)
  if not spot or not Spring.GetUnitsInCylinder then return false end
  local units = Spring.GetUnitsInCylinder(spot.x, spot.z, 96)
  return units and #units > 0
end

local function nearestOpenMetalSpot(anchorX, anchorZ, claimedMetalSpots)
  local spots = GG and GG["resource_spot_finder"] and GG["resource_spot_finder"].metalSpotsList or nil
  if not spots then return nil end
  local best, bestDist
  for i = 1, #spots do
    local spot = spots[i]
    local key = metalSpotKey(spot)
    if not claimedMetalSpots[key] and not metalSpotHasUnit(spot) then
      local dx, dz = anchorX - spot.x, anchorZ - spot.z
      local dist = dx * dx + dz * dz
      if not bestDist or dist < bestDist then
        best = spot
        bestDist = dist
      end
    end
  end
  return best
end

local function spawnOneUnit(defName, x, z, facing, teamID, spec, force)
  local y = Spring.GetGroundHeight(x, z)
  local unitID = Spring.CreateUnit(defName, x, y, z, facing, teamID)
  if unitID then
    Spring.SetUnitRulesParam(unitID, "va_playable_proxy", 1, { public = true })
    if force and force.role then
      Spring.SetUnitRulesParam(unitID, "va_force_role", tostring(force.role), { public = true })
      if force.role == "objective_target" then
        local defID = Spring.GetUnitDefID(unitID)
        if isStructure(defID) then
          local forceId = tostring(force.id or "objective")
          objectiveTargets[unitID] = forceId
          objectiveTargetCount = objectiveTargetCount + 1
          targetForceStructures[forceId] = (targetForceStructures[forceId] or 0) + 1
        end
      end
    end
    if spec and spec.patrolX and spec.patrolZ and CMD and CMD.FIGHT then
      local px = normalizedToElmos(spec.patrolX, Game.mapSizeX or 0)
      local pz = normalizedToElmos(spec.patrolZ, Game.mapSizeZ or 0)
      Spring.GiveOrderToUnit(unitID, CMD.FIGHT, { px, Spring.GetGroundHeight(px, pz), pz }, {})
    end
    return 1
  end
  return 0
end

local function spawnUnitSpec(spec, teamID, baseX, baseZ, groupX, groupZ, claimedMetalSpots, force)
  if type(spec) ~= "table" then return 0 end
  local defName = spec.unitDefName or spec.def or spec[1]
  if not defName or not UnitDefNames[defName] then
    Spring.Echo("VA_PLAYABLE_MISSING_UNIT " .. tostring(defName))
    return 0
  end
  local count = tonumber(spec.count or 1) or 1
  local spacing = tonumber(spec.spacing or 90) or 90
  local spawned = 0
  local dx = tonumber(spec.dx or spec.x or 0) or 0
  local dz = tonumber(spec.dz or spec.z or 0) or 0
  local facing = tonumber(spec.facing or 0) or 0
  local anchorX = baseX + groupX + dx
  local anchorZ = baseZ + groupZ + dz

  if spec.atMetalSpots or spec.nearestMetalSpots then
    for i = 1, count do
      local spot = nearestOpenMetalSpot(anchorX, anchorZ, claimedMetalSpots)
      if not spot then
        Spring.Echo("VA_PLAYABLE_NO_METAL_SPOT unitDef=" .. tostring(defName) .. " anchorX=" .. tostring(math.floor(anchorX)) .. " anchorZ=" .. tostring(math.floor(anchorZ)))
        break
      end
      claimedMetalSpots[metalSpotKey(spot)] = true
      spawned = spawned + spawnOneUnit(defName, spot.x, spot.z, facing, teamID, spec, force)
    end
    return spawned
  end

  for i = 1, count do
    local row = math.floor((i - 1) / 4)
    local col = (i - 1) % 4
    local x = anchorX + ((col - 1.5) * spacing)
    local z = anchorZ + (row * spacing)
    spawned = spawned + spawnOneUnit(defName, x, z, facing, teamID, spec, force)
  end
  return spawned
end

local function spawnPlayableSetup()
  if playableSetupSpawned then
    Spring.Echo("VA_PLAYABLE_SETUP already_spawned")
    return
  end
  local setup = mission and mission.playableSetup
  if not setup or setup.enabled == false then
    Spring.Echo("VA_PLAYABLE_SETUP none")
    return
  end
  playableSetupSpawned = true
  local forces = setup.forces or {}
  local claimedMetalSpots = {}
  local totalSpawned = 0
  for _, force in ipairs(forces) do
    local teamID = tonumber(force.teamID or 0) or 0
    local base = force.base or {}
    local baseX = normalizedToElmos(base.x or 0.5, Game.mapSizeX or 0)
    local baseZ = normalizedToElmos(base.z or 0.5, Game.mapSizeZ or 0)
    local forceSpawned = 0
    for _, group in ipairs(force.groups or {}) do
      local groupX = tonumber(group.dx or group.x or 0) or 0
      local groupZ = tonumber(group.dz or group.z or 0) or 0
      for _, spec in ipairs(group.units or {}) do
        forceSpawned = forceSpawned + spawnUnitSpec(spec, teamID, baseX, baseZ, groupX, groupZ, claimedMetalSpots, force)
      end
    end
    totalSpawned = totalSpawned + forceSpawned
    Spring.Echo("VA_PLAYABLE_FORCE id=" .. tostring(force.id or "?") .. " team=" .. tostring(teamID) .. " role=" .. tostring(force.role or "") .. " units=" .. tostring(forceSpawned))
  end
  Spring.SetGameRulesParam("va_objective_total", objectiveTargetCount, { public = true })
  Spring.SetGameRulesParam("va_objective_destroyed", 0, { public = true })
  Spring.Echo("VA_PLAYABLE_SETUP spawned forces=" .. tostring(#forces) .. " units=" .. tostring(totalSpawned))
  Spring.Echo("VA_OBJECTIVE_ARMED kind=" .. tostring(mission.objective and mission.objective.kind or "none") .. " targets=" .. tostring(objectiveTargetCount))
end

local function resourceIncome(teamID, resourceName)
  local ok, a, b, c, income = pcall(Spring.GetTeamResources, teamID, resourceName)
  if ok then return tonumber(income or c or 0) or 0 end
  return 0
end

local function zoneForPosition(x, z)
  if not zoneMap or type(zoneMap.zones) ~= "table" then return nil end
  local sx = Game.mapSizeX or 0
  local sz = Game.mapSizeZ or 0
  for _, zone in ipairs(zoneMap.zones) do
    local b = zone.bounds or {}
    local xMin = normalizedToElmos(b.xMin, sx)
    local xMax = normalizedToElmos(b.xMax, sx)
    local zMin = normalizedToElmos(b.zMin, sz)
    local zMax = normalizedToElmos(b.zMax, sz)
    if x >= xMin and x <= xMax and z >= zMin and z <= zMax then
      return zone
    end
  end
  return nil
end

local function emptyMetrics()
  return {
    armyValue = 0,
    buildPower = 0,
    defensiveValue = 0,
    totalUnitValue = 0,
    unitCount = 0,
    combatUnitCount = 0,
    builderUnitCount = 0,
    structureCount = 0
  }
end

local function addUnitToBucket(bucket, defID)
  local name = unitDefName(defID)
  local metal = unitDefMetal(defID)
  local ud = UnitDefs[defID]
  bucket.metrics.totalUnitValue = bucket.metrics.totalUnitValue + metal
  bucket.metrics.unitCount = bucket.metrics.unitCount + 1
  bucket.unitCountsByDef[name] = (bucket.unitCountsByDef[name] or 0) + 1
  if isStructure(defID) then bucket.metrics.structureCount = bucket.metrics.structureCount + 1 end
  if isBuilder(defID) then
    bucket.metrics.builderUnitCount = bucket.metrics.builderUnitCount + 1
    bucket.metrics.buildPower = bucket.metrics.buildPower + (tonumber(ud and ud.buildSpeed or 0) or 0)
  end
  if canFight(defID) then
    bucket.metrics.combatUnitCount = bucket.metrics.combatUnitCount + 1
    if isStructure(defID) then
      bucket.metrics.defensiveValue = bucket.metrics.defensiveValue + metal
    else
      bucket.metrics.armyValue = bucket.metrics.armyValue + metal
    end
  end
end

local function countsJson(counts)
  local parts = {}
  for name, count in pairs(counts or {}) do
    parts[#parts + 1] = jstr(name) .. ':' .. jnum(count)
  end
  return '{' .. table.concat(parts, ',') .. '}'
end

local function metricsJson(m)
  return '{' .. table.concat({
    '"armyValue":' .. jnum(m.armyValue or 0, 2),
    '"buildPower":' .. jnum(m.buildPower or 0, 2),
    '"defensiveValue":' .. jnum(m.defensiveValue or 0, 2),
    '"totalUnitValue":' .. jnum(m.totalUnitValue or 0, 2),
    '"metalIncome":' .. jnum(m.metalIncome or 0, 2),
    '"energyIncome":' .. jnum(m.energyIncome or 0, 2),
    '"unitCount":' .. jnum(m.unitCount or 0),
    '"combatUnitCount":' .. jnum(m.combatUnitCount or 0),
    '"builderUnitCount":' .. jnum(m.builderUnitCount or 0),
    '"structureCount":' .. jnum(m.structureCount or 0)
  }, ',') .. '}'
end

local function makeTeamBucket(teamID)
  local _, leader, isDead, isAiTeam, side, allyTeam = Spring.GetTeamInfo(teamID, false)
  return {
    teamId = teamID,
    allyTeamId = tonumber(allyTeam or -1) or -1,
    side = side or "",
    isDead = isDead and true or false,
    isAi = isAiTeam and true or false,
    metrics = emptyMetrics(),
    unitCountsByDef = {}
  }
end

local function teamBucketJson(bucket)
  return '{' .. table.concat({
    '"teamId":' .. jnum(bucket.teamId),
    '"allyTeamId":' .. jnum(bucket.allyTeamId),
    '"side":' .. jstr(bucket.side or ""),
    '"isDead":' .. tostring(bucket.isDead == true),
    '"isAi":' .. tostring(bucket.isAi == true),
    '"metrics":' .. metricsJson(bucket.metrics),
    '"unitCountsByDef":' .. countsJson(bucket.unitCountsByDef)
  }, ',') .. '}'
end

local function zoneBucketJson(zone, teams)
  local teamParts = {}
  for _, bucket in pairs(teams or {}) do
    teamParts[#teamParts + 1] = teamBucketJson(bucket)
  end
  return jstr(zone.zoneId or "unknown") .. ':{' .. table.concat({
    '"zoneId":' .. jstr(zone.zoneId or ""),
    '"label":' .. jstr(zone.label or ""),
    '"teams":[' .. table.concat(teamParts, ',') .. ']'
  }, ',') .. '}'
end

local function telemetryJson()
  local frame = Spring.GetGameFrame()
  local teamBuckets = {}
  local teamParts = {}
  local zoneBuckets = {}
  local playerTeam = tonumber(mission and mission.balance and mission.balance.playerTeamID or 3) or 3

  for _, teamID in ipairs(Spring.GetTeamList()) do
    teamBuckets[teamID] = makeTeamBucket(teamID)
  end

  for teamID, bucket in pairs(teamBuckets) do
    local units = Spring.GetTeamUnits(teamID) or {}
    for _, unitID in ipairs(units) do
      if Spring.ValidUnitID(unitID) and not Spring.GetUnitIsDead(unitID) then
        local defID = Spring.GetUnitDefID(unitID)
        addUnitToBucket(bucket, defID)
        local x, _, z = Spring.GetUnitPosition(unitID)
        if x and z then
          local zone = zoneForPosition(x, z)
          if zone and zone.zoneId then
            zoneBuckets[zone.zoneId] = zoneBuckets[zone.zoneId] or { zone = zone, teams = {} }
            if not zoneBuckets[zone.zoneId].teams[teamID] then
              local zb = makeTeamBucket(teamID)
              zb.metrics = emptyMetrics()
              zb.unitCountsByDef = {}
              zoneBuckets[zone.zoneId].teams[teamID] = zb
            end
            addUnitToBucket(zoneBuckets[zone.zoneId].teams[teamID], defID)
          end
        end
      end
    end
    bucket.metrics.metalIncome = resourceIncome(teamID, "metal")
    bucket.metrics.energyIncome = resourceIncome(teamID, "energy")
    teamParts[#teamParts + 1] = teamBucketJson(bucket)
  end

  local playerValue = teamBuckets[playerTeam] and teamBuckets[playerTeam].metrics.totalUnitValue or 0
  local enemyValue = 0
  local enemyUnitCount = 0
  for teamID, bucket in pairs(teamBuckets) do
    if teamID ~= playerTeam and teamID ~= 0 then
      enemyValue = enemyValue + bucket.metrics.totalUnitValue
      enemyUnitCount = enemyUnitCount + bucket.metrics.unitCount
    end
  end
  local playerUnitCount = teamBuckets[playerTeam] and teamBuckets[playerTeam].metrics.unitCount or 0
  local valueRatio = enemyValue > 0 and (playerValue / enemyValue) or playerValue
  local verdict = "active"
  if playerUnitCount <= 0 then verdict = "player_dead"
  elseif enemyUnitCount <= 0 then verdict = "player_clear"
  elseif valueRatio >= 1.25 then verdict = "player_advantage"
  elseif valueRatio <= 0.55 then verdict = "player_stalled"
  end

  local zoneParts = {}
  if zoneMap and type(zoneMap.zones) == "table" then
    for _, zone in ipairs(zoneMap.zones) do
      local entry = zoneBuckets[zone.zoneId] or { zone = zone, teams = {} }
      zoneParts[#zoneParts + 1] = zoneBucketJson(entry.zone, entry.teams)
    end
  end

  return '{' .. table.concat({
    '"schemaVersion":"bar-zone-telemetry/1.0"',
    '"exportId":' .. jstr("va-" .. tostring(frame)),
    '"matchId":' .. jstr(Game.gameID or ""),
    '"missionId":' .. jstr(mission and mission.missionId or ""),
    '"variantId":' .. jstr(mission and mission.playableSetup and mission.playableSetup.variantId or ""),
    '"frame":' .. jnum(frame),
    '"seconds":' .. jnum(frame / 30, 2),
    '"map":{"name":' .. jstr(Game.mapName or "") .. ',"mapId":' .. jstr(zoneMap and zoneMap.mapId or "") .. ',"size":{"x":' .. jnum(Game.mapSizeX or 0) .. ',"z":' .. jnum(Game.mapSizeZ or 0) .. '}}',
    '"terminal":{"isTerminal":false,"status":"active","winnerAllyTeamId":null}',
    '"balance":{"playerTeamId":' .. jnum(playerTeam) .. ',"playerValue":' .. jnum(playerValue, 2) .. ',"enemyValue":' .. jnum(enemyValue, 2) .. ',"valueRatio":' .. jnum(valueRatio, 4) .. ',"playerUnitCount":' .. jnum(playerUnitCount) .. ',"enemyUnitCount":' .. jnum(enemyUnitCount) .. ',"verdict":' .. jstr(verdict) .. '}',
    '"teams":[' .. table.concat(teamParts, ',') .. ']',
    '"zones":{' .. table.concat(zoneParts, ',') .. '}'
  }, ',') .. '}'
end

local function logTelemetry()
  local json = telemetryJson()
  Spring.Echo("VA_TELEMETRY_JSON_COMPACT " .. json)
  logJsonChunked("VA_TELEMETRY_JSON", json)
  Spring.Echo("VA_TELEMETRY_EXPORT_OK frame=" .. tostring(Spring.GetGameFrame()))
end

-- ============================================================
-- VERDANCE TRANSLATION MATRIX ENGINE
-- Consumes real zoneBuckets, runs Hermitian math, emits packet.
-- ============================================================

local MAX_WATER_HEIGHT = 250.0
local BASE_COUPLING = 0.3
local BASE_HYDRO_COUPLING = 0.6
local ENTANGLEMENT_THRESHOLD = 0.1
local DENSITY_HOTSPOT = 0.8
local HYDRO_HAZARD_THRESHOLD = 0.4

-- Determine zone hydro type from zone tags
local function getZoneHydroType(zone)
  if not zone or not zone.tags then return "high-dry" end
  for _, tag in ipairs(zone.tags) do
    if tag == "swamp" or tag == "flood" or tag == "low" then return "low-flood" end
  end
  return "high-dry"
end

-- Sum metrics across all teams in a zone bucket (total military presence)
local function sumZoneMetrics(zoneEntry)
  local av, bp, dp = 0, 0, 0
  if not zoneEntry or not zoneEntry.teams then return av, bp, dp end
  for _, bucket in pairs(zoneEntry.teams) do
    av = av + (bucket.metrics.armyValue or 0)
    bp = bp + (bucket.metrics.buildPower or 0)
    dp = dp + (bucket.metrics.defensiveValue or 0)
  end
  return av, bp, dp
end

local function generateTranslationPacket(zoneBuckets)
  if not zoneMap or type(zoneMap.zones) ~= "table" or #zoneMap.zones == 0 then
    Spring.Echo("VA_TRANSLATION_SKIP no zone map loaded")
    return nil
  end

  local N = #zoneMap.zones
  local waterLevel = math.max(0, math.min(tonumber(Spring.GetMapWaterLevel and Spring.GetMapWaterLevel() or 0) or 0, MAX_WATER_HEIGHT))
  local rho_H = waterLevel / MAX_WATER_HEIGHT

  -- Build flat zone list from real data
  local zones = {}
  for i, zone in ipairs(zoneMap.zones) do
    local entry = zoneBuckets[zone.zoneId] or { zone = zone, teams = {} }
    local av, bp, dp = sumZoneMetrics(entry)
    zones[i] = {
      id      = i,
      zoneId  = zone.zoneId,
      name    = zone.label or zone.zoneId,
      type    = getZoneHydroType(zone),
      av      = av,
      bp      = bp,
      dp      = dp,
    }
  end

  -- Instantiate (N+1) x (N+1) Hermitian matrix
  local matrix = {}
  for i = 1, N + 1 do
    matrix[i] = {}
    for j = 1, N + 1 do matrix[i][j] = 0 end
  end

  -- Step 1: Diagonals (zone density)
  for k = 1, N do
    local z = zones[k]
    matrix[k][k] = math.tanh((z.av + z.bp + z.dp) / 5735.0)
  end
  matrix[N+1][N+1] = rho_H  -- Environmental hydrology anchor

  -- Step 2: Off-diagonals (zone entanglement by AV disparity)
  for i = 1, N do
    for j = 1, N do
      if i ~= j then
        matrix[i][j] = BASE_COUPLING * (1.0 - math.tanh(math.abs(zones[i].av - zones[j].av) / 4915.0))
      end
    end
    -- Step 3: Hydrological coupling (last col/row)
    if zones[i].type == "high-dry" then
      matrix[i][N+1] = 0.05
      matrix[N+1][i] = 0.05
    else
      matrix[i][N+1] = BASE_HYDRO_COUPLING * rho_H
      matrix[N+1][i] = BASE_HYDRO_COUPLING * rho_H
    end
  end

  -- Build canonical packet
  local packet = {
    protocol = "VERDANCE_TRANSLATION_V1",
    frame    = Spring.GetGameFrame(),
    global   = { hydrology = { level = waterLevel, saturation = tonumber(string.format("%.3f", rho_H)) } },
    nodes    = {},
    entanglements = {},
    factoids = {},
  }

  for i = 1, N do
    local z = zones[i]
    table.insert(packet.nodes, {
      id           = z.id,
      zoneId       = z.zoneId,
      name         = z.name,
      type         = z.type,
      raw          = { av = z.av, bp = z.bp, dp = z.dp },
      density      = tonumber(string.format("%.3f", matrix[i][i])),
      hydroCoupling= tonumber(string.format("%.3f", matrix[i][N+1])),
    })
  end

  for i = 1, N do
    for j = i + 1, N do
      local coupling = matrix[i][j]
      if coupling > ENTANGLEMENT_THRESHOLD then
        table.insert(packet.entanglements, {
          zoneIds  = { zones[i].zoneId, zones[j].zoneId },
          names    = { zones[i].name, zones[j].name },
          coupling = tonumber(string.format("%.3f", coupling)),
        })
      end
    end
  end

  for _, node in ipairs(packet.nodes) do
    if node.type == "low-flood" and node.hydroCoupling > HYDRO_HAZARD_THRESHOLD then
      table.insert(packet.factoids, {
        type    = "HAZARD",
        zoneId  = node.zoneId,
        message = node.name .. " is critically exposed to current hydrology levels.",
      })
    end
    if node.density > DENSITY_HOTSPOT then
      table.insert(packet.factoids, {
        type    = "HOTSPOT",
        zoneId  = node.zoneId,
        message = node.name .. " has reached critical military density.",
      })
    end
  end

  return packet
end

-- Minimal table -> JSON serializer for the canonical packet
local function serializeTranslationPacket(p)
  if not p then return nil end

  local nodeParts = {}
  for _, n in ipairs(p.nodes) do
    table.insert(nodeParts, string.format(
      '{"id":%d,"zoneId":%s,"name":%s,"type":%s,"raw":{"av":%.0f,"bp":%.0f,"dp":%.0f},"density":%.3f,"hydroCoupling":%.3f}',
      n.id, jstr(n.zoneId), jstr(n.name), jstr(n.type), n.raw.av, n.raw.bp, n.raw.dp, n.density, n.hydroCoupling
    ))
  end

  local entParts = {}
  for _, e in ipairs(p.entanglements) do
    table.insert(entParts, string.format(
      '{"zoneIds":[%s,%s],"names":[%s,%s],"coupling":%.3f}',
      jstr(e.zoneIds[1]), jstr(e.zoneIds[2]), jstr(e.names[1]), jstr(e.names[2]), e.coupling
    ))
  end

  local factParts = {}
  for _, f in ipairs(p.factoids) do
    table.insert(factParts, string.format(
      '{"type":%s,"zoneId":%s,"message":%s}',
      jstr(f.type), jstr(f.zoneId), jstr(f.message)
    ))
  end

  return string.format(
    '{"protocol":%s,"frame":%d,"global":{"hydrology":{"level":%.1f,"saturation":%.3f}},"nodes":[%s],"entanglements":[%s],"factoids":[%s]}',
    jstr(p.protocol), p.frame,
    p.global.hydrology.level, p.global.hydrology.saturation,
    table.concat(nodeParts, ","),
    table.concat(entParts, ","),
    table.concat(factParts, ",")
  )
end

local function logAndBroadcastTranslation()
  -- We need fresh zoneBuckets - rebuild them inline
  local zoneBucketsLive = {}
  if zoneMap and type(zoneMap.zones) == "table" then
    -- Build fresh per-zone buckets from current unit positions
    for _, teamID in ipairs(Spring.GetTeamList()) do
      local units = Spring.GetTeamUnits(teamID) or {}
      for _, unitID in ipairs(units) do
        if Spring.ValidUnitID(unitID) and not Spring.GetUnitIsDead(unitID) then
          local defID = Spring.GetUnitDefID(unitID)
          local x, _, z = Spring.GetUnitPosition(unitID)
          if x and z then
            local zone = zoneForPosition(x, z)
            if zone and zone.zoneId then
              zoneBucketsLive[zone.zoneId] = zoneBucketsLive[zone.zoneId] or { zone = zone, teams = {} }
              if not zoneBucketsLive[zone.zoneId].teams[teamID] then
                local zb = makeTeamBucket(teamID)
                zb.metrics = emptyMetrics()
                zb.unitCountsByDef = {}
                zoneBucketsLive[zone.zoneId].teams[teamID] = zb
              end
              addUnitToBucket(zoneBucketsLive[zone.zoneId].teams[teamID], defID)
            end
          end
        end
      end
    end
  end

  local packet = generateTranslationPacket(zoneBucketsLive)
  local json   = serializeTranslationPacket(packet)
  if not json then
    Spring.Echo("VA_TRANSLATION_ERROR failed to serialize packet")
    return
  end

  -- Log to infolog (chunked, readable in headless output)
  Spring.Echo("VA_TRANSLATION_PACKET_COMPACT " .. json)
  logJsonChunked("VA_TRANSLATION_PACKET", json)

  -- Broadcast to LuaUI Overmind Widget (no-op in headless, active in playable)
  if SendToUnsynced then
    SendToUnsynced("VERDANCE_TELEMETRY", json)
  end

  Spring.Echo(string.format(
    "VA_TRANSLATION_OK frame=%d zones=%d entanglements=%d factoids=%d",
    packet.frame, #packet.nodes, #packet.entanglements, #packet.factoids
  ))
end

-- ============================================================
-- OBJECTIVE AUTOMATION
-- Real win/loss detection: target destruction, zone holds,
-- extraction, commander loss, player wipe.
-- ============================================================

local function objectiveKind()
  return mission and mission.objective and mission.objective.kind or ""
end

local function zoneRectFor(zoneId)
  if not zoneId or not zoneMap or type(zoneMap.zones) ~= "table" then return nil end
  local sx = Game.mapSizeX or 0
  local sz = Game.mapSizeZ or 0
  for _, z in ipairs(zoneMap.zones) do
    if z.zoneId == zoneId then
      local b = z.bounds or {}
      return {
        normalizedToElmos(b.xMin, sx),
        normalizedToElmos(b.zMin, sz),
        normalizedToElmos(b.xMax, sx),
        normalizedToElmos(b.zMax, sz),
      }, z.label
    end
  end
  return nil
end

local function scanZoneRect(rect)
  local playerPresent, enemyCombat = false, false
  if not rect then return playerPresent, enemyCombat end
  local units = Spring.GetUnitsInRectangle(rect[1], rect[2], rect[3], rect[4])
  for i = 1, #units do
    local uid = units[i]
    if Spring.ValidUnitID(uid) and not Spring.GetUnitIsDead(uid) then
      local team = Spring.GetUnitTeam(uid)
      if team == playerTeamID then
        playerPresent = true
      elseif team ~= gaiaTeamID and teamAllyTeam[team] ~= playerAllyTeamID then
        if canFight(Spring.GetUnitDefID(uid)) then enemyCombat = true end
      end
    end
  end
  return playerPresent, enemyCombat
end

local function onObjectiveComplete(how)
  if objectiveComplete then return end
  objectiveComplete = true
  objectiveCompleteHow = how or "complete"
  Spring.SetGameRulesParam("va_objective_complete", 1, { public = true })
  Spring.Echo("VA_OBJECTIVE_COMPLETE mission=" .. tostring(mission.missionId) .. " how=" .. objectiveCompleteHow)
  if SendToUnsynced then SendToUnsynced("VERDANCE_MISSION_EVENT", "objective_complete", objectiveCompleteHow) end
end

local function setTerminal(newStatus, reason)
  if terminal then return end
  terminal = true
  terminalReason = tostring(reason or "")
  status = newStatus
  debugAutoProgress = 0
  Spring.SetGameRulesParam("va_terminal", 1, { public = true })
  Spring.SetGameRulesParam("va_result_code", (newStatus == "victory" and 1) or (newStatus == "defeat" and 2) or 3, { public = true })
  Spring.SetGameRulesParam("va_status", newStatus, { public = true })
  Spring.Echo("VA_TERMINAL status=" .. status .. " reason=" .. terminalReason)
  logResult()
  if SendToUnsynced then SendToUnsynced("VERDANCE_MISSION_EVENT", status, terminalReason) end
  local profilingRun = headlessAutoStart or balanceExportFrame or (#fibMilestones > 0)
  if profilingRun then
    if headlessQuit then
      headlessQuitFrame = Spring.GetGameFrame() + 60
    end
  else
    local winners = {}
    if newStatus == "defeat" then
      for _, at in ipairs(Spring.GetAllyTeamList()) do
        if at ~= playerAllyTeamID and at ~= gaiaAllyTeamID then winners[#winners + 1] = at end
      end
    else
      winners = { playerAllyTeamID }
    end
    Spring.GameOver(winners)
  end
end

local function checkPresenceObjective(frame)
  if objectiveComplete then return end
  local kind = objectiveKind()
  -- Presence kinds hold the target zone; destruction kinds with zero spawned
  -- targets fall back to the same zone-hold rule so missions stay winnable.
  local presenceMode = PRESENCE_KINDS[kind] or (objectiveTargetCount == 0 and targetZoneRect ~= nil)
  if not presenceMode or not targetZoneRect then return end
  local playerPresent, enemyCombat = scanZoneRect(targetZoneRect)
  if playerPresent and not enemyCombat then
    zoneHoldFrames = zoneHoldFrames + CHECK_PERIOD
  else
    zoneHoldFrames = 0
  end
  Spring.SetGameRulesParam("va_zone_hold", zoneHoldFrames, { public = true })
  local required = tonumber(mission.objective and mission.objective.requiredHoldFrames) or PRESENCE_HOLD_DEFAULT
  if zoneHoldFrames >= required then
    onObjectiveComplete("zone_held")
  end
end

local function checkExtraction(frame)
  local kind = objectiveKind()
  local allowBypass = (kind == "hive_clear_or_bypass") and playerLeftExtraction
  if not (objectiveComplete or allowBypass) then
    -- Track leaving the deployment/extraction zone; that arms the bypass path.
    if extractionZoneRect and not playerLeftExtraction then
      local playerPresent = scanZoneRect(extractionZoneRect)
      if not playerPresent then playerLeftExtraction = true end
    end
    return
  end
  if not extractionZoneRect then
    if objectiveComplete then setTerminal("victory", "objective_complete_no_extraction_zone") end
    return
  end
  local playerPresent, enemyCombat = scanZoneRect(extractionZoneRect)
  if playerPresent then
    extractionHoldFrames = extractionHoldFrames + CHECK_PERIOD
    if enemyCombat then extractionClean = false end
  else
    playerLeftExtraction = true
    extractionHoldFrames = 0
  end
  Spring.SetGameRulesParam("va_extraction_hold", extractionHoldFrames, { public = true })
  if extractionHoldFrames >= EXTRACTION_HOLD_FRAMES then
    if objectiveComplete then
      setTerminal("victory", "extracted")
    else
      objectiveBypassed = true
      setTerminal("partial", "extracted_bypass")
    end
  end
end

local function checkPlayerWipe(frame)
  if frame < WIPE_GRACE_FRAMES then return end
  local count = Spring.GetTeamUnitCount(playerTeamID) or 0
  if count <= 0 then
    setTerminal("defeat", "player_wiped")
  end
end

function gadget:Initialize()
  mission = readMission()
  zoneMap = readZoneMap()
  local modOptions = Spring.GetModOptions() or {}
  headlessAutoStart = truthy(modOptions.va_headless_autostart)
  headlessFastWin = not (modOptions.va_headless_fastwin == false or modOptions.va_headless_fastwin == 0 or modOptions.va_headless_fastwin == "0")
  headlessQuit = truthy(modOptions.va_headless_quit)
  balanceExportFrame = tonumber(modOptions.va_balance_export_frame or "")
  balanceQuitAfterExport = truthy(modOptions.va_balance_quit)

  -- Parse Fibonacci milestone list: va_fib_export_frames=900,1800,2700,4500,...
  local fibRaw = tostring(modOptions.va_fib_export_frames or "")
  if fibRaw ~= "" then
    for s in fibRaw:gmatch("[^,]+") do
      local n = tonumber(s:match("^%s*(.-)%s*$"))
      if n and n > 0 then fibMilestones[#fibMilestones+1] = math.floor(n) end
    end
    table.sort(fibMilestones)
    fibQuitAfterLast = truthy(modOptions.va_fib_quit)
  end

  -- Objective automation setup
  playerTeamID = tonumber(mission.balance and mission.balance.playerTeamID) or 0
  gaiaTeamID = Spring.GetGaiaTeamID()
  for _, tid in ipairs(Spring.GetTeamList()) do
    local _, _, _, _, _, at = Spring.GetTeamInfo(tid, false)
    teamAllyTeam[tid] = tonumber(at or -1) or -1
  end
  playerAllyTeamID = teamAllyTeam[playerTeamID] or 0
  gaiaAllyTeamID = teamAllyTeam[gaiaTeamID] or -1
  debugAutoProgressAllowed = headlessFastWin or truthy(modOptions.va_debug_autoprogress)
  local obj = mission.objective or {}
  targetZoneRect = zoneRectFor(obj.targetZoneId)
  extractionZoneRect = zoneRectFor(mission.extractionZoneId or obj.extractionZoneId)

  Spring.SetGameRulesParam("va_bridge_loaded", 1, { public = true })
  Spring.SetGameRulesParam("va_mission_number", mission.missionNumber or 0, { public = true })
  Spring.SetGameRulesParam("va_hold_frames", holdFrames, { public = true })
  Spring.SetGameRulesParam("va_required_frames", mission.objective and mission.objective.requiredFrames or 600, { public = true })
  Spring.SetGameRulesParam("va_status", status, { public = true })
  Spring.SetGameRulesParam("va_objective_complete", 0, { public = true })
  Spring.SetGameRulesParam("va_terminal", 0, { public = true })
  Spring.Echo("VA_BRIDGE_LOADED mission=" .. tostring(mission.missionId) .. " schema=" .. tostring(mission.schemaVersion or "unknown"))
  if headlessAutoStart then Spring.Echo("VA_HEADLESS_AUTOSTART enabled") end
  if balanceExportFrame then Spring.Echo("VA_BALANCE_AUTORUN exportFrame=" .. tostring(balanceExportFrame) .. " quit=" .. tostring(balanceQuitAfterExport)) end
  if #fibMilestones > 0 then
    Spring.Echo("VA_FIB_PROFILER milestones=" .. tostring(#fibMilestones) .. " first=" .. tostring(fibMilestones[1]) .. " last=" .. tostring(fibMilestones[#fibMilestones]) .. " quitAfterLast=" .. tostring(fibQuitAfterLast))
  end
  if zoneMap then Spring.Echo("VA_ZONES_LOADED mapId=" .. tostring(zoneMap.mapId or "unknown") .. " count=" .. tostring(zoneCount())) end
end

function gadget:GameStart()
  spawnPlayableSetup()
  if headlessAutoStart and not headlessStarted then
    headlessStarted = true
    startMission()
    if headlessFastWin then
      finishHeadlessResult("victory")
    end
  elseif not headlessAutoStart then
    -- Playable session: the mission is live immediately, no /vastart needed.
    startMission()
  end
end

function gadget:GameFrame(frame)
  if headlessAutoStart and not headlessStarted and frame >= 1 then
    headlessStarted = true
    startMission()
    if headlessFastWin then
      finishHeadlessResult("victory")
    end
  end

  if balanceExportFrame and not balanceExported and frame >= balanceExportFrame then
    balanceExported = true
    logTelemetry()
    logAndBroadcastTranslation()
    if balanceQuitAfterExport then
      headlessQuitFrame = frame + 2
    end
  end

  -- Fibonacci multi-milestone profiler
  if #fibMilestones > 0 and fibMilestoneIdx <= #fibMilestones then
    local due = fibMilestones[fibMilestoneIdx]
    if frame >= due then
      Spring.Echo("VA_FIB_MILESTONE idx=" .. tostring(fibMilestoneIdx) .. " frame=" .. tostring(frame) .. " target=" .. tostring(due))
      logTelemetry()
      logAndBroadcastTranslation()
      fibMilestoneIdx = fibMilestoneIdx + 1
      if fibMilestoneIdx > #fibMilestones and fibQuitAfterLast then
        headlessQuitFrame = frame + 2
      end
    end
  end

  if headlessQuitFrame and frame >= headlessQuitFrame then
    Spring.Echo("VA_HEADLESS_QUIT")
    Spring.SendCommands("quitforce")
    headlessQuitFrame = nil
  end

  -- Objective automation checks (playable sessions)
  if status == "active" and not terminal and frame % CHECK_PERIOD == 0 then
    checkPresenceObjective(frame)
    checkExtraction(frame)
    checkPlayerWipe(frame)
  end

  -- Debug/fastwin auto-progress timer (only armed via modoption)
  if status == "active" and debugAutoProgress == 1 and frame % 30 == 0 then
    holdFrames = holdFrames + 30
    Spring.SetGameRulesParam("va_hold_frames", holdFrames, { public = true })
    local req = mission.objective and mission.objective.requiredFrames or 600
    if holdFrames >= req then
      Spring.Echo("VA_OBJECTIVE_COMPLETE mission=" .. tostring(mission.missionId))
      setTerminal("victory", "debug_autoprogress")
    end
  end
end

function gadget:UnitCreated(unitID, unitDefID, unitTeam)
  if unitTeam == playerTeamID then
    local ud = UnitDefs[unitDefID]
    if ud and ud.customParams and ud.customParams.iscommander then
      playerCommanders[unitID] = true
      sawPlayerCommander = true
    end
  end
end

function gadget:UnitGiven(unitID, unitDefID, newTeam, oldTeam)
  if newTeam == playerTeamID then
    local ud = UnitDefs[unitDefID]
    if ud and ud.customParams and ud.customParams.iscommander then
      playerCommanders[unitID] = true
      sawPlayerCommander = true
    end
  elseif playerCommanders[unitID] then
    playerCommanders[unitID] = nil
  end
end

function gadget:UnitDestroyed(unitID, unitDefID, unitTeam)
  local forceId = objectiveTargets[unitID]
  if forceId then
    objectiveTargets[unitID] = nil
    objectiveTargetsDestroyed = objectiveTargetsDestroyed + 1
    targetForceStructures[forceId] = math.max(0, (targetForceStructures[forceId] or 1) - 1)
    Spring.SetGameRulesParam("va_objective_destroyed", objectiveTargetsDestroyed, { public = true })
    Spring.Echo("VA_OBJECTIVE_TARGET_DOWN force=" .. forceId .. " destroyed=" .. tostring(objectiveTargetsDestroyed) .. "/" .. tostring(objectiveTargetCount))
    if not objectiveComplete and status == "active" and not terminal then
      if CHOICE_KINDS[objectiveKind()] then
        if (targetForceStructures[forceId] or 0) <= 0 then
          chosenTargetForceId = forceId
          onObjectiveComplete("target_destroyed")
        end
      elseif objectiveTargetsDestroyed >= objectiveTargetCount then
        onObjectiveComplete("target_destroyed")
      end
    end
  end
  if playerCommanders[unitID] then
    playerCommanders[unitID] = nil
    if sawPlayerCommander and next(playerCommanders) == nil and status == "active" and not terminal then
      setTerminal("defeat", "commander_lost")
    end
  end
end

function gadget:GameOver(winningAllyTeams)
  if terminal then return end
  -- Safety net: the game ended without our own terminal path (resign, quit,
  -- external gameover). Derive a status and guarantee a result marker.
  local won = false
  for _, at in ipairs(winningAllyTeams or {}) do
    if at == playerAllyTeamID then won = true end
  end
  terminal = true
  terminalReason = "gameover_external"
  if won then
    status = objectiveComplete and "victory" or "partial"
  else
    status = "defeat"
  end
  debugAutoProgress = 0
  Spring.SetGameRulesParam("va_terminal", 1, { public = true })
  Spring.SetGameRulesParam("va_status", status, { public = true })
  Spring.Echo("VA_TERMINAL status=" .. status .. " reason=" .. terminalReason)
  logResult()
end

local function runVerdanceCommand(cmd)
  if cmd == "vastart" then startMission()
  elseif cmd == "vastatus" then echoStatus()
  elseif cmd == "vaprogress" then progress(300)
  elseif cmd == "vaprogressbig" then progress(99999)
  elseif cmd == "vawin" then setTerminal("victory", "debug_command")
  elseif cmd == "vafail" then setTerminal("defeat", "debug_command")
  elseif cmd == "vapartial" then setTerminal("partial", "debug_command")
  elseif cmd == "vatest_killobjective" then
    if Spring.IsCheatingEnabled() then
      local ids = {}
      for unitID in pairs(objectiveTargets) do ids[#ids + 1] = unitID end
      for _, unitID in ipairs(ids) do Spring.DestroyUnit(unitID, false, false) end
      Spring.Echo("VA_TEST_KILLOBJECTIVE destroyed=" .. tostring(#ids))
    else
      Spring.Echo("VA_TEST_DENIED cheats required for vatest_killobjective")
    end
  elseif cmd == "vaspawn" then spawnCompanions()
  elseif cmd == "vaspawnlayout" then spawnPlayableSetup()
  elseif cmd == "vazones" then echoZones()
  elseif cmd == "vatelemetry" or cmd == "vabalance" then logTelemetry()
  elseif cmd == "vatranslation" then logAndBroadcastTranslation()
  elseif cmd == "varesult" or cmd == "vaexport" then logResult()
  elseif cmd == "vaheadless" then startMission(); finishHeadlessResult("victory")
  elseif cmd == "vareset" then status = "inactive"; holdFrames = 0; debugAutoProgress = 0; echoStatus()
  else return false end
  return true
end

function gadget:TextCommand(command)
  if type(command) ~= "string" then return false end
  local cmd = command:match("^(%S+)")
  if not cmd then return false end
  if runVerdanceCommand(cmd) then return true end
  return false
end

function gadget:RecvLuaMsg(msg, playerID)
  if type(msg) ~= "string" or msg:sub(1, 7) ~= "VA_CMD:" then return end
  local cmd = msg:sub(8)
  if not runVerdanceCommand(cmd) then
    Spring.Echo("VA_UNKNOWN_CMD " .. tostring(cmd))
  end
end











