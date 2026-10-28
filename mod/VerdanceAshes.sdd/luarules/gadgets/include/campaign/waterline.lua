-- campaign/waterline.lua: the waterline (hydrology) and zone flow
-- Part of game_verdance_campaign.lua, loaded into that gadget's environment
-- (VFS.Include with the gadget table), so its globals are the gadget's globals.
-- Provides: VA_TRANSLATION, VA_WATER_TICK, configureZoneFlowSample, getZoneHydroType,
-- vaBeginWaterline, vaInitWaterline, vaRecordZonePresence, vaSampleZoneFlow, vaStepWaterline,
-- vaWaterApplied, vaWaterElevation, vaWaterLevel, vaWaterTarget, vaZoneAdjacency,
-- vaZoneAdjacencyCache, vaZoneFlow, vaZoneFlowJson, vaZoneFlowSample, vaZoneSubmerged
-- Uses: state, telemetry

-- ============================================================
-- VERDANCE TRANSLATION MATRIX ENGINE
-- Consumes real zoneBuckets, runs Hermitian math, emits packet.
-- ============================================================

-- Tuning constants packed into one gadget-env table (main-chunk local budget).
VA_TRANSLATION = {
  BASE_COUPLING = 0.3,
  BASE_HYDRO_COUPLING = 0.6,
  ENTANGLEMENT_THRESHOLD = 0.1,
  DENSITY_HOTSPOT = 0.8,
  HYDRO_HAZARD_THRESHOLD = 0.4,
}

-- Determine zone hydro type from zone tags
function getZoneHydroType(zone)
  -- Measured first: a zone is low-flood if the campaign's waterline can
  -- actually take it. Tags are the fallback for legacy rect zone maps.
  local hydro = zone and zone.hydrology
  local floodsAt = hydro and tonumber(hydro.floodsAt)
  if floodsAt then
    return (floodsAt <= 0.7) and "low-flood" or "high-dry"
  end
  if not zone or not zone.tags then return "high-dry" end
  for _, tag in ipairs(zone.tags) do
    if tag == "swamp" or tag == "flood" or tag == "low" then return "low-flood" end
  end
  return "high-dry"
end

-- ------------------------------------------------------------
-- Hydrology and zone geography for the density matrix.
--
-- These are gadget-env GLOBALS on purpose: the main chunk sits at 194/200 Lua
-- locals and one more would stop the whole gadget loading.
--
-- Spring has no synced water-level setter, so a rising waterline is realised by
-- sinking the world: lowering the entire heightmap by D drowns everything below
-- elevation D. The shift is uniform, so no slope and no relative height changes
-- -- only the shore moves -- and one AdjustHeightMap call does the whole map.
-- ------------------------------------------------------------

VA_WATER_TICK = 6           -- frames between waterline steps while ramping
vaWaterLevel = 0.0          -- normalized 0..1 along the map's measured ladder
vaWaterApplied = 0.0        -- elmos the world is currently sunk by
vaWaterTarget = nil         -- ramp destination, when a flood beat is running
vaWaterStep = 0.0
vaUnitZone = nil            -- unitID -> zoneId, for measuring border crossings
vaZoneFlow = nil            -- "A|B" -> crossings since the last packet
vaZoneFlowTotals = nil      -- "A|B" -> crossings for the whole match (never reset)
vaZoneAdjacencyCache = nil

-- Elevation of a normalized waterline, from the ladder the zone map carries.
function vaWaterElevation(level)
  local line = zoneMap and zoneMap.waterline
  local elevations = line and line.elevations
  if not elevations or #elevations == 0 then return nil end
  local levels = line.levels or {}
  local t = math.max(0, math.min(1, tonumber(level) or 0))
  for i = 1, #elevations do
    local at = tonumber(levels[i]) or ((i - 1) / math.max(1, #elevations - 1))
    if at >= t then
      if i == 1 then return elevations[1] end
      local prev = tonumber(levels[i - 1]) or 0
      local span = (at - prev)
      local f = (span > 0) and ((t - prev) / span) or 0
      return elevations[i - 1] + (elevations[i] - elevations[i - 1]) * f
    end
  end
  return elevations[#elevations]
end

-- Fraction of a zone under water at a normalized level, from its measured curve.
function vaZoneSubmerged(zone, level)
  local hydro = zone and zone.hydrology
  local curve = hydro and hydro.submergedAt
  if not curve or #curve == 0 then return 0.0 end
  local levels = (zoneMap and zoneMap.waterline and zoneMap.waterline.levels) or {}
  local t = math.max(0, math.min(1, tonumber(level) or 0))
  for i = 1, #curve do
    local at = tonumber(levels[i]) or ((i - 1) / math.max(1, #curve - 1))
    if at >= t then
      if i == 1 then return curve[1] or 0.0 end
      local prev = tonumber(levels[i - 1]) or 0
      local span = (at - prev)
      local f = (span > 0) and ((t - prev) / span) or 0
      return (curve[i - 1] or 0) + ((curve[i] or 0) - (curve[i - 1] or 0)) * f
    end
  end
  return curve[#curve] or 0.0
end

-- Which zones actually touch, and how much border they share. Derived once from
-- the cell mask; a coupling between zones that do not touch is not a coupling.
function vaZoneAdjacency()
  if vaZoneAdjacencyCache then return vaZoneAdjacencyCache end
  local index = vaZoneCellIndex and vaZoneCellIndex()
  if not index then return nil end
  local res, owner = index.res, index.owner
  local shared, perimeter = {}, {}
  for row = 0, res - 1 do
    for col = 0, res - 1 do
      -- vaZoneCellIndex stores the zone TABLE per cell, not its id; comparing
      -- those directly is a runtime error, and it takes the whole GameFrame
      -- callin down with it.
      local az = owner[row * res + col]
      local a = az and az.zoneId
      if a then
        perimeter[a] = (perimeter[a] or 0) + 1
        -- Checked one at a time: ipairs over {nil, x} stops at the first hole
        -- and would silently drop every south border on the map's east edge.
        local rz = (col < res - 1) and owner[row * res + col + 1] or nil
        local dz = (row < res - 1) and owner[(row + 1) * res + col] or nil
        local rb = rz and rz.zoneId
        if rb and rb ~= a then
          local key = (a < rb) and (a .. "|" .. rb) or (rb .. "|" .. a)
          shared[key] = (shared[key] or 0) + 1
        end
        local db = dz and dz.zoneId
        if db and db ~= a then
          local key = (a < db) and (a .. "|" .. db) or (db .. "|" .. a)
          shared[key] = (shared[key] or 0) + 1
        end
      end
    end
  end
  vaZoneAdjacencyCache = { shared = shared, perimeter = perimeter }
  return vaZoneAdjacencyCache
end

-- Units crossing a border are the live half of "entanglement".
function vaRecordZonePresence(unitID, zoneId, teamID)
  -- Gaia's wildlife wanders the whole map. On greenest_fields eight critter_gulls
  -- flying laps produced border "crossings" between zones no ground unit can move
  -- between (NE plateau straight to SW bastion). Wildlife is not a front. The
  -- guard lives here rather than in the sampler because telemetryJson walks every
  -- team's units, gaia included, and calls straight into this function.
  if teamID and teamID == gaiaTeamID then return end
  vaUnitZone = vaUnitZone or {}
  local was = vaUnitZone[unitID]
  vaUnitZone[unitID] = zoneId
  if was and zoneId and was ~= zoneId then
    vaZoneFlow = vaZoneFlow or {}
    local key = (was < zoneId) and (was .. "|" .. zoneId) or (zoneId .. "|" .. was)
    vaZoneFlow[key] = (vaZoneFlow[key] or 0) + 1
    vaZoneFlowTotals = vaZoneFlowTotals or {}
    local row = vaZoneFlowTotals[key]
    if not row then
      row = { total = 0, byTeam = {} }
      vaZoneFlowTotals[key] = row
    end
    row.total = row.total + 1
    if teamID then row.byTeam[teamID] = (row.byTeam[teamID] or 0) + 1 end
  end
end

-- vaRecordZonePresence only ever ran from inside telemetryJson, which fires at
-- export milestones. Sampling a unit's zone five times in eight minutes cannot
-- observe a border crossing, so vaZoneFlow -- the live half of "entanglement" --
-- was always ~0 and every front read as uncoupled no matter how hard the armies
-- were actually moving. Sample on its own clock instead. Globals, not locals:
-- this file is already against Lua 5.1's 200-local ceiling.
vaZoneFlowSample = 0
function vaSampleZoneFlow()
  local units = Spring.GetAllUnits()
  if not units then return end
  for i = 1, #units do
    local unitID = units[i]
    local teamID = Spring.GetUnitTeam(unitID)
    -- Gaia's wildlife wanders the whole map. On greenest_fields the first pass of
    -- this sampler measured eight critter_gulls flying laps and reported it as
    -- army traffic between zones. Wildlife is not a front.
    if teamID and teamID ~= gaiaTeamID then
      local x, _, z = Spring.GetUnitPosition(unitID)
      if x then
        local zone = zoneForPosition(x, z)
        if zone and zone.zoneId then
          vaRecordZonePresence(unitID, zone.zoneId, teamID)
        end
      end
    end
  end
end

-- Cumulative border traffic for the whole match, so an offline analysis can see
-- which zones actually feed each other. vaZoneFlow itself is reset after every
-- translation packet (it means "crossings since the last packet"); this is not.
function vaZoneFlowJson()
  local parts = {}
  for key, row in pairs(vaZoneFlowTotals or {}) do
    local a, b = key:match("^(.-)|(.*)$")
    if a and b then
      local teamParts = {}
      for teamID, count in pairs(row.byTeam or {}) do
        teamParts[#teamParts + 1] = '{"team":' .. jnum(teamID) .. ',"crossings":' .. jnum(count) .. '}'
      end
      parts[#parts + 1] = '{"from":' .. jstr(a) .. ',"to":' .. jstr(b)
        .. ',"crossings":' .. jnum(row.total or 0)
        .. ',"byTeam":[' .. table.concat(teamParts, ",") .. ']}'
    end
  end
  return '{"frame":' .. jnum(Spring.GetGameFrame() or 0)
    .. ',"sampleEvery":' .. jnum(vaZoneFlowSample or 0)
    .. ',"edges":[' .. table.concat(parts, ",") .. ']}'
end

-- Move the world relative to the sea. Idempotent: it only ever applies the
-- DIFFERENCE between where the waterline is and where it should be.
function vaApplyWaterline(level)
  local elevation = vaWaterElevation(level)
  if not elevation then return false end
  local resting = vaWaterElevation(0) or 0
  local wanted = elevation - resting
  -- The LOGICAL level always tracks, even when the physical shift is too small
  -- to bother the engine with. Deferring both would stall a slow ramp forever:
  -- the level would never advance, so the next step would ask for the same
  -- sub-threshold delta again.
  vaWaterLevel = level
  local delta = wanted - vaWaterApplied
  if math.abs(delta) < 0.05 then return false end
  if Spring.AdjustHeightMap then
    Spring.AdjustHeightMap(0, 0, Game.mapSizeX or 0, Game.mapSizeZ or 0, -delta)
  end
  vaWaterApplied = wanted
  Spring.SetGameRulesParam("va_water_level", level)
  Spring.SetGameRulesParam("va_water_sunk", vaWaterApplied)
  return true
end

-- Ramp the waterline over time so a flood reads as an event, not a teleport.
function vaStepWaterline()
  if not vaWaterTarget then return end
  local remaining = vaWaterTarget - vaWaterLevel
  if math.abs(remaining) <= math.abs(vaWaterStep) or vaWaterStep == 0 then
    vaApplyWaterline(vaWaterTarget)
    Spring.Echo(string.format("VA_HYDRO_DONE level=%.3f sunk=%.1f", vaWaterLevel, vaWaterApplied))
    vaWaterTarget = nil
    vaWaterStep = 0
    return
  end
  vaApplyWaterline(vaWaterLevel + vaWaterStep)
end

-- The waterline the campaign handed this mission. Applied once at start, so a
-- mission on a flooded map begins flooded rather than flooding on camera.
function vaInitWaterline()
  local hydro = mission and mission.hydrology
  local level = hydro and tonumber(hydro.level) or 0
  vaWaterLevel = 0.0
  vaWaterApplied = 0.0
  vaWaterTarget = nil
  vaZoneFlow = {}
  vaUnitZone = {}
  if level > 0 then
    vaApplyWaterline(level)
  end
  Spring.SetGameRulesParam("va_water_level", vaWaterLevel)
  Spring.Echo(string.format("VA_HYDRO_INIT level=%.3f sunk=%.1f amplitude=%s",
    vaWaterLevel, vaWaterApplied,
    tostring(hydro and hydro.amplitude or "n/a")))
end

function vaBeginWaterline(target, seconds)
  local to = math.max(0, math.min(1, tonumber(target) or 0))
  local span = math.max(1, math.floor((tonumber(seconds) or 20) * 30 / VA_WATER_TICK))
  vaWaterTarget = to
  vaWaterStep = (to - vaWaterLevel) / span
  Spring.Echo(string.format("VA_HYDRO_BEGIN from=%.3f to=%.3f seconds=%s",
    vaWaterLevel, to, tostring(seconds)))
end

-- Called by gadget:Initialize.
function configureZoneFlowSample(modOptions)
  -- Border-crossing sampler cadence. Defaults on only under profiling: a real
  -- session gets it only if it explicitly asks.
  vaZoneFlowSample = tonumber(modOptions.va_zone_flow_sample or "")
    or ((headless.autoStart or balance.exportFrame or #fib.milestones > 0) and 150 or 0)
  -- A tracked human session is asking. Without this the whole AI-duel measurement
  -- -- which corridors carry traffic, which sit inert -- has no human counterpart:
  -- the sampler stays at 0 and every crossing goes unrecorded.
  --
  -- Pinned to the same 150 the profiling runs used, NOT to devTel.period. A crossing
  -- count is a function of how often you look: sample every 1800 frames instead of
  -- every 150 and a unit that goes A->B->A between looks records nothing at all.
  -- Human and AI crossing counts are only comparable at one shared rate, so the
  -- emission cadence (devTel.period) and the observation cadence are separate knobs.
  if vaZoneFlowSample <= 0 and devTel.enabled then
    vaZoneFlowSample = 150
  end
end
