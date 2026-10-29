-- campaign/telemetry.lua: zone cells, per-zone metrics, dev telemetry and the headless/profiling options
-- Part of game_verdance_campaign.lua, loaded into that gadget's environment
-- (VFS.Include with the gadget table), so its globals are the gadget's globals.
-- Provides: addUnitToBucket, armDevTelemetry, classifyCmd, configureHeadlessClient, devTel,
-- emptyMetrics, logTelemetry, makeTeamBucket, readProfilingOptions, tickDevTelemetry,
-- tickProfiling, vaZoneCellIndex, zoneDvJson, zoneDvTable, zoneForPosition
-- Uses: mission_data, result, setup, state, terminal, translation, units, waterline

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

-- Presence per zone per faction, right now: AV + DV, the metal in every side's armed units and
-- armed structures (and pad teeth), the company's and everyone else's alike (owner call,
-- 2026-10-29; include/va_claim.lua has the ownership rule). The live answer to "who holds this
-- zone": reinforcements read it, the objective's claim check and the extraction points read it
-- (GG.VA_ZoneDv), and so does Python at home.
function zoneDvTable()
  local byZone = {}
  for _, unitID in ipairs(Spring.GetAllUnits() or {}) do
    local teamID = Spring.GetUnitTeam(unitID)
    local defID = Spring.GetUnitDefID(unitID)
    if teamID and teamID ~= gaiaTeamID and defID and (canFight(defID) or unitIsPadTooth(unitID)) then
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
GG.VA_ZoneDv = zoneDvTable   -- the exfil gadget's extraction points (game_verdance_exfil.lua)

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

-- Balance export, the Fibonacci milestones and the headless quit. Called by gadget:GameFrame.
function tickProfiling(frame)
  if balance.exportFrame and not balance.exported and frame >= balance.exportFrame then
    balance.exported = true
    logTelemetry()
    Spring.Echo("VA_ZONE_FLOW_JSON " .. vaZoneFlowJson())
    logAndBroadcastTranslation()
    if balance.quitAfterExport then
      headless.quitFrame = frame + 2
    end
  end

  -- Fibonacci multi-milestone profiler
  if #fib.milestones > 0 and fib.idx <= #fib.milestones then
    local due = fib.milestones[fib.idx]
    if frame >= due then
      Spring.Echo("VA_FIB_MILESTONE idx=" .. tostring(fib.idx) .. " frame=" .. tostring(frame) .. " target=" .. tostring(due))
      logTelemetry()
      Spring.Echo("VA_ZONE_FLOW_JSON " .. vaZoneFlowJson())
      logAndBroadcastTranslation()
      fib.idx = fib.idx + 1
      if fib.idx > #fib.milestones and fib.quitAfterLast then
        headless.quitFrame = frame + 2
      end
    end
  end

  if headless.quitFrame and frame >= headless.quitFrame then
    Spring.Echo("VA_HEADLESS_QUIT")
    Spring.SendCommands("quitforce")
    headless.quitFrame = nil
  end
end

-- Called by gadget:GameFrame.
function tickDevTelemetry(frame)
  -- Dense human-player telemetry for dev launch learning loop.
  if devTel.enabled and status == "active" and not terminal then
    if (frame - devTel.lastSample) >= devTel.period then
      logDevSample()
    end
  end
end

-- Called by gadget:Initialize.
function armDevTelemetry(modOptions)
  -- Dev telemetry arm: mission seed, modoption, or generated flag file.
  do
    local flag = nil
    local okF, dataF = pcall(VFS.Include, "singleplayer/verdance_ashes/generated/dev_telemetry_flag.lua")
    if okF and type(dataF) == "table" then flag = dataF end
    local fromMission = mission and (mission.devTelemetry == true or (mission.dev and mission.dev.telemetry == true))
    -- va_play_track is the player-facing name for the same arm. The playtest
    -- launcher sets it; va_dev_telemetry stays for the dev_launch/flag-file path.
    local fromOpt = truthy(modOptions.va_dev_telemetry) or truthy(modOptions.va_play_track)
    local fromFlag = flag and truthy(flag.enabled)
    devTel.enabled = fromMission or fromOpt or fromFlag
    local period = tonumber(mission and mission.dev and mission.dev.samplePeriodFrames)
      or tonumber(flag and flag.samplePeriodFrames)
      or tonumber(modOptions.va_dev_sample_period)
      or 150
    if period and period >= 30 then devTel.period = math.floor(period) end
    if devTel.enabled then
      Spring.Echo("VA_DEV_TELEMETRY_ARMED period=" .. tostring(devTel.period)
        .. " mission=" .. tostring(fromMission)
        .. " opt=" .. tostring(fromOpt)
        .. " flag=" .. tostring(fromFlag))
    end
  end
end

-- Headless, balance-export and Fibonacci-profiler options. Called by gadget:Initialize.
function readProfilingOptions(modOptions)
  headless.autoStart = truthy(modOptions.va_headless_autostart)
  -- The absent modoption is nil, which matches none of the three false-y tests, so
  -- this read "true" in EVERY human session -- not just headless ones. That set
  -- debugAutoProgressAllowed, which ticks holdFrames up by 30 every 30 frames whether
  -- or not the player is holding anything, stamps auto=1 on VA_STATUS, and puts
  -- "debugAutoProgress":1 in the result JSON. It has not been stealing wins only
  -- because checkSoftClock runs first and every authored requiredFrames divides by 30;
  -- a seed missing requiredFrames falls through to 600 and fires a bogus victory.
  -- fastWin is a headless-batch concept, so scope it to a headless batch.
  headless.fastWin = headless.autoStart
    and not (modOptions.va_headless_fastwin == false or modOptions.va_headless_fastwin == 0 or modOptions.va_headless_fastwin == "0")
  headless.quit = truthy(modOptions.va_headless_quit)
  balance.exportFrame = tonumber(modOptions.va_balance_export_frame or "")
  balance.quitAfterExport = truthy(modOptions.va_balance_quit)

  -- Parse Fibonacci milestone list: va_fib_export_frames=900,1800,2700,4500,...
  local fibRaw = tostring(modOptions.va_fib_export_frames or "")
  if fibRaw ~= "" then
    for s in fibRaw:gmatch("[^,]+") do
      local n = tonumber(s:match("^%s*(.-)%s*$"))
      if n and n > 0 then fib.milestones[#fib.milestones+1] = math.floor(n) end
    end
    table.sort(fib.milestones)
    fib.quitAfterLast = truthy(modOptions.va_fib_quit)
  end
end

-- Called by gadget:Initialize.
function configureHeadlessClient(modOptions)
  -- Headless spins forever building the unit-icon texture atlas at frame 30.
  -- The shell-bake and cartography gadgets both learned this the hard way and
  -- carry the same guard; every va_* probe runs through THIS gadget, so it
  -- belongs here too. Only under an explicitly headless/profiling run -- a real
  -- session needs its icons.
  --
  -- va_no_ui exists to separate "this process has no screen" from "this is a
  -- profiling run". They were the same predicate, which made the human code path
  -- untestable: verifying it headlessly meant setting a profiling flag, and every
  -- profiling flag also forces 20x sim, disables waves and beats, grants an
  -- instant win and skips Spring.GameOver -- so the thing under test was never the
  -- thing that would run. Without it, spring-headless builds the full widget set
  -- and icon atlas and never reaches frame 0. Absent in a real session, so the
  -- player keeps their UI.
  local noUi = (headless.autoStart or balance.exportFrame or #fib.milestones > 0)
    or truthy(modOptions.va_no_ui)
  -- The third argument is useOverlay, and it is load-bearing, not a nicety. The
  -- engine documents it as "the value will only be set in memory, and not be
  -- restored for the next game" -- meaning WITHOUT it these three writes persist
  -- into the player's real springsettings.cfg and outlive the process. That is
  -- not hypothetical: an earlier headless probe on this machine left LuaUI = 0
  -- and UnitIconDist = 99999 sitting in the live config, which would have opened
  -- the next GUI session with no LuaUI at all -- no widgets, no HUD, and no
  -- recorder -- with nothing in game to explain why.
  if noUi and Spring.SetConfigInt then
    Spring.SetConfigInt("UnitIconsAsUI", 0, true)
    Spring.SetConfigInt("UnitIconDist", 99999, true)
    Spring.SetConfigInt("LuaUI", 0, true)
  end

  -- Headless sims at 1x unless the host is told otherwise, so a 21-minute
  -- profiling milestone costs 21 real minutes and an overnight matrix cannot
  -- finish. The shell-bake and cartography gadgets already force the sim clock
  -- up for their unattended batches; profiling runs come through this gadget and
  -- need the same. Guarded by the profiling condition, so a real session is
  -- untouched. va_headless_speed=0 opts out.
  if (headless.autoStart or balance.exportFrame or #fib.milestones > 0)
      and Spring.SendCommands then
    local simSpeed = tonumber(modOptions.va_headless_speed or "") or 20
    if simSpeed > 0 then
      Spring.SendCommands("setmaxspeed " .. simSpeed)
      Spring.SendCommands("setminspeed " .. simSpeed)
    end
  end
end
