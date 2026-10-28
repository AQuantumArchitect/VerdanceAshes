-- campaign/telemetry.lua: zone cells, per-zone metrics and dev telemetry
-- Part of game_verdance_campaign.lua, loaded into that gadget's environment
-- (VFS.Include with the gadget table), so its globals are the gadget's globals.
-- Provides: addUnitToBucket, classifyCmd, devTel, emptyMetrics, logDevSample, logTelemetry,
-- makeTeamBucket, vaZoneCellIndex, zoneDvJson, zoneDvTable, zoneForPosition
-- Uses: mission_data, result, setup, state, units, waterline

-- Dev telemetry: one table so GameFrame stays under Lua 5.1's 60-upvalue cap.
-- Armed by singleplayer/.../generated/dev_telemetry_flag.lua or mission.devTelemetry.
devTel = {
  enabled = false,
  period = 150,          -- ~5s @ 30fps
  lastSample = -999999,
  cmds = { move = 0, fight = 0, attack = 0, patrol = 0, build = 0, reclaim = 0, guard = 0, other = 0 },
  cmdTotal = 0,
}

-- Gadget-env global (the main chunk is at its 200-local ceiling). Builds the
-- cell -> zone lookup once from schema 2.0 cell masks; returns nil for legacy
-- rect-only zone maps so the old path still works.
function vaZoneCellIndex()
  if vaZoneCellIndexCache == false then return nil end
  if vaZoneCellIndexCache then return vaZoneCellIndexCache end
  vaZoneCellIndexCache = false
  if not zoneMap or type(zoneMap.zones) ~= "table" then return nil end
  local res = nil
  if zoneMap.grid and tonumber(zoneMap.grid.res) then
    res = math.floor(tonumber(zoneMap.grid.res))
  end
  for _, zone in ipairs(zoneMap.zones) do
    if not res and zone.cellGrid and tonumber(zone.cellGrid.cols) then
      res = math.floor(tonumber(zone.cellGrid.cols))
    end
  end
  if not res or res < 2 then return nil end
  local owner = {}
  local claimed = 0
  for _, zone in ipairs(zoneMap.zones) do
    if type(zone.cells) == "table" then
      for _, run in ipairs(zone.cells) do
        local start = tonumber(run[1])
        local length = tonumber(run[2])
        if start and length and length > 0 then
          for i = start, start + length - 1 do
            if owner[i] == nil then
              owner[i] = zone
              claimed = claimed + 1
            end
          end
        end
      end
    end
  end
  if claimed == 0 then return nil end
  vaZoneCellIndexCache = { res = res, owner = owner, claimed = claimed }
  return vaZoneCellIndexCache
end

function zoneForPosition(x, z)
  if not zoneMap or type(zoneMap.zones) ~= "table" then return nil end
  local sx = Game.mapSizeX or 0
  local sz = Game.mapSizeZ or 0
  -- Schema 2.0: zones own an explicit set of grid cells, so a position belongs
  -- to exactly one zone. The old rect scan returned whichever overlapping
  -- rectangle happened to be earlier in the file.
  local cellIndex = vaZoneCellIndex()
  if cellIndex then
    local res = cellIndex.res
    local col = math.floor((x / (sx > 0 and sx or 1)) * res)
    local row = math.floor((z / (sz > 0 and sz or 1)) * res)
    if col < 0 then col = 0 elseif col >= res then col = res - 1 end
    if row < 0 then row = 0 elseif row >= res then row = res - 1 end
    local owner = cellIndex.owner[row * res + col]
    return owner -- Unassigned cells stay unassigned; do not invent AABB ownership.
  end
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

function emptyMetrics()
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

function addUnitToBucket(bucket, defID, unitID)
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
    -- Structures always DV; area_control pad rings (Beamers/LLTs/Thistles) too.
    if isStructure(defID) or unitIsPadTooth(unitID) then
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

function makeTeamBucket(teamID)
  local _, leader, isDead, isAiTeam, side, allyTeam = Spring.GetTeamInfo(teamID, false)
  return {
    teamId = teamID,
    allyTeamId = tonumber(allyTeam or -1) or -1,
    side = side or "",
    faction = teamFaction[teamID] or "",
    isDead = isDead and true or false,
    isAi = isAiTeam and true or false,
    metrics = emptyMetrics(),
    unitCountsByDef = {}
  }
end

-- Presence per zone per faction, right now: metal in armed structures and pad teeth, and for the
-- company its armed units as well (an army standing on ground is enough to claim it when you
-- lift; verdance.world.claim). The live answer to "who holds this zone": reinforcements read it,
-- the objective's claim check reads it, and so does Python at home.
function zoneDvTable()
  local byZone = {}
  for _, unitID in ipairs(Spring.GetAllUnits() or {}) do
    local teamID = Spring.GetUnitTeam(unitID)
    local defID = Spring.GetUnitDefID(unitID)
    if teamID and teamID ~= gaiaTeamID and defID and canFight(defID)
        and (isStructure(defID) or unitIsPadTooth(unitID) or teamID == playerTeamID) then
      local x, _, z = Spring.GetUnitPosition(unitID)
      local zone = x and zoneForPosition(x, z)
      if zone and zone.zoneId then
        local faction = (teamID == playerTeamID) and "ashwalkers" or tostring(teamFaction[teamID] or "neutral"):lower()
        local row = byZone[tostring(zone.zoneId)] or {}
        row[faction] = (row[faction] or 0) + unitDefMetal(defID)
        byZone[tostring(zone.zoneId)] = row
      end
    end
  end
  return byZone
end

function zoneDvJson()
  local byZone = zoneDvTable()
  local parts = {}
  for zid, row in pairs(byZone) do
    local inner = {}
    for faction, v in pairs(row) do inner[#inner + 1] = jstr(faction) .. ":" .. jnum(math.floor(v)) end
    parts[#parts + 1] = jstr(zid) .. ":{" .. table.concat(inner, ",") .. "}"
  end
  table.sort(parts)
  return "{" .. table.concat(parts, ",") .. "}"
end

local function teamBucketJson(bucket)
  return '{' .. table.concat({
    '"teamId":' .. jnum(bucket.teamId),
    '"allyTeamId":' .. jnum(bucket.allyTeamId),
    '"side":' .. jstr(bucket.side or ""),
    '"faction":' .. jstr(bucket.faction or ""),
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
  -- Same source of truth as the objective/win system. playerTeamID already IS
  -- the seed's balance.playerTeamID, clamped at load to a team this match has;
  -- re-reading the raw seed here would reintroduce a nonexistent team.
  local playerTeam = playerTeamID

  for _, teamID in ipairs(Spring.GetTeamList()) do
    teamBuckets[teamID] = makeTeamBucket(teamID)
  end

  for teamID, bucket in pairs(teamBuckets) do
    local units = Spring.GetTeamUnits(teamID) or {}
    for _, unitID in ipairs(units) do
      if Spring.ValidUnitID(unitID) and not Spring.GetUnitIsDead(unitID) then
        local defID = Spring.GetUnitDefID(unitID)
        addUnitToBucket(bucket, defID, unitID)
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
            addUnitToBucket(zoneBuckets[zone.zoneId].teams[teamID], defID, unitID)
            vaRecordZonePresence(unitID, zone.zoneId, teamID)
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
    if teamID ~= playerTeam and teamID ~= 0 and not Spring.AreTeamsAllied(playerTeam, teamID) then
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

function logTelemetry()
  local json = telemetryJson()
  Spring.Echo("VA_TELEMETRY_JSON_COMPACT " .. json)
  logJsonChunked("VA_TELEMETRY_JSON", json)
  if SendToUnsynced then SendToUnsynced("VERDANCE_TRACK", "telemetry", json) end
  Spring.Echo("VA_TELEMETRY_EXPORT_OK frame=" .. tostring(Spring.GetGameFrame()))
end

local function resetDevCmdCounts()
  devTel.cmds = { move = 0, fight = 0, attack = 0, patrol = 0, build = 0, reclaim = 0, guard = 0, other = 0 }
  devTel.cmdTotal = 0
end

function classifyCmd(cmdID)
  -- Spring CMD IDs: MOVE=-1 FIGHT=16 PATROL=15 GUARD=25 ATTACK=20 RECLAIM=90 REPAIR=40
  if cmdID == CMD.MOVE or cmdID == -1 then return "move" end
  if cmdID == CMD.FIGHT or cmdID == 16 then return "fight" end
  if cmdID == CMD.PATROL or cmdID == 15 then return "patrol" end
  if cmdID == CMD.ATTACK or cmdID == 20 then return "attack" end
  if cmdID == CMD.GUARD or cmdID == 25 then return "guard" end
  if cmdID == CMD.RECLAIM or cmdID == 90 then return "reclaim" end
  if type(cmdID) == "number" and cmdID < 0 then return "build" end  -- negative = build unitdef
  return "other"
end

function logDevSample()
  if not devTel.enabled then return end
  local frame = Spring.GetGameFrame() or 0
  local base = telemetryJson()
  -- Emit the occupancy packet in its own right, not only spliced into the dev
  -- sample below. Without this a played mission produces exactly one snapshot (the
  -- one at terminal) and its "timeline" is a single point, while every AI run has
  -- five. Free: telemetryJson() has already been called.
  Spring.Echo("VA_TELEMETRY_JSON_COMPACT " .. base)
  if SendToUnsynced then SendToUnsynced("VERDANCE_TRACK", "telemetry", base) end
  -- strip outer braces to splice fields
  local inner = base
  if inner:sub(1, 1) == "{" then inner = inner:sub(2) end
  if inner:sub(-1) == "}" then inner = inner:sub(1, -2) end
  local playerTeam = playerTeamID
  local mCurr, mStor = 0, 0
  local eCurr, eStor = 0, 0
  local mInc, eInc = 0, 0
  if Spring.GetTeamResources then
    local mc, ms = Spring.GetTeamResources(playerTeam, "metal")
    local ec, es = Spring.GetTeamResources(playerTeam, "energy")
    mCurr, mStor = tonumber(mc) or 0, tonumber(ms) or 0
    eCurr, eStor = tonumber(ec) or 0, tonumber(es) or 0
  end
  -- income from last full telemetry path is heavy; approximate via rules or 0
  if Spring.GetTeamRulesParam then
    -- Recoil builds differ here: some expose no value for a missing team rule
    -- and the C binding then returns zero Lua values. Calling tonumber(...) on
    -- that result raises "value expected" and aborts the whole GameFrame.
    local okM, rawM = pcall(Spring.GetTeamRulesParam, playerTeam, "metalIncome")
    local okE, rawE = pcall(Spring.GetTeamRulesParam, playerTeam, "energyIncome")
    if okM then mInc = tonumber(rawM) or 0 end
    if okE then eInc = tonumber(rawE) or 0 end
  end
  local cx, cz, n = 0, 0, 0
  local units = Spring.GetTeamUnits(playerTeam) or {}
  for i = 1, #units do
    local u = units[i]
    if Spring.ValidUnitID(u) and not Spring.GetUnitIsDead(u) then
      local x, _, z = Spring.GetUnitPosition(u)
      if x and z then
        cx = cx + x
        cz = cz + z
        n = n + 1
      end
    end
  end
  if n > 0 then cx, cz = cx / n, cz / n end
  local cmdParts = {}
  for k, v in pairs(devTel.cmds) do
    cmdParts[#cmdParts + 1] = jstr(k) .. ":" .. jnum(v)
  end
  local devJson = '{' .. table.concat({
    inner,
    '"dev":{"metal":' .. jnum(mCurr, 1) .. ',"metalStorage":' .. jnum(mStor, 1)
      .. ',"energy":' .. jnum(eCurr, 1) .. ',"energyStorage":' .. jnum(eStor, 1)
      .. ',"metalIncome":' .. jnum(mInc, 2) .. ',"energyIncome":' .. jnum(eInc, 2)
      .. ',"centroid":{"x":' .. jnum(cx, 1) .. ',"z":' .. jnum(cz, 1) .. ',"units":' .. jnum(n) .. '}'
      .. ',"samplePeriodFrames":' .. jnum(devTel.period) .. '}',
    '"playerCommands":{' .. table.concat(cmdParts, ',') .. '}',
    '"playerCommandTotal":' .. jnum(devTel.cmdTotal),
    '"devSample":true',
    '"exportId":' .. jstr("va-dev-" .. tostring(frame)),
  }, ',') .. '}'
  Spring.Echo("VA_DEV_SAMPLE_JSON " .. devJson)
  Spring.Echo("VA_DEV_SAMPLE_OK frame=" .. tostring(frame) .. " cmds=" .. tostring(devTel.cmdTotal))
  if SendToUnsynced then SendToUnsynced("VERDANCE_TRACK", "devsample", devJson) end
  -- Cumulative crossings ride the dev cadence so a session that never reaches a
  -- terminal -- alt-F4, resign, crash, or simply stopping to make dinner -- still
  -- leaves a usable flow record. setTerminal emits the clean final copy; this is the
  -- one that survives not getting there. Global lookup: vaZoneFlowJson is defined
  -- below this function and only resolves at call time.
  if vaZoneFlowJson then
    local flowJson = vaZoneFlowJson()
    Spring.Echo("VA_ZONE_FLOW_JSON " .. flowJson)
    if SendToUnsynced then SendToUnsynced("VERDANCE_TRACK", "zoneflow", flowJson) end
  end
  resetDevCmdCounts()
  devTel.lastSample = frame
end
