local gadget = gadget

function gadget:GetInfo()
  return {
    name = "Verdance Cartography",
    desc = "Zone survey instrument: terrain raster + behaviour raster dumps for empirical zone mapping",
    author = "Verdance",
    date = "2026-08-24",
    license = "GPL v2 or later",
    layer = 6,
    enabled = true,
  }
end

if not gadgetHandler:IsSyncedCode() then
  return
end

-- Deliberately a SEPARATE gadget from game_verdance_campaign.lua: that chunk sits
-- at 194/200 Lua locals and must not absorb survey instrumentation.
--
-- Armed only by modoption va_cartography=1. Two channels:
--   A) terrain raster  -- one pass at frame 30, what the ENGINE thinks the map is
--      (height, slope, water, buildability, metal, per-move-class speeds, wreck
--      fields, authored start positions, BAR's own metal spot list)
--   B) behaviour raster -- position-binned accumulation over an AI-vs-AI match
--      (presence, structures, losses, mobile traffic, first-contact frame),
--      emitted at milestone frames
--
-- Both land in the infolog as parseable lines; tools/parse_cartography_log_v1.py
-- turns them into data/terrain/<map>.terrain.json and
-- data/behavior/<map>/<config>.raster.json.

local function modRaw(name)
  local mo = Spring.GetModOptions and Spring.GetModOptions() or {}
  return mo[name]
end

local function modFlag(name)
  local v = modRaw(name)
  if v == true or v == 1 then return true end
  if type(v) == "string" then
    v = v:lower()
    return v == "1" or v == "true" or v == "yes" or v == "enabled"
  end
  return false
end

local function modInt(name, default)
  local v = modRaw(name)
  if v == nil then return default end
  return tonumber(v) or default
end

local function modStr(name, default)
  local v = modRaw(name)
  if v == nil or v == "" then return default end
  return tostring(v)
end

local enabled = false
local res = 48                 -- grid resolution (res x res cells)
local cellW, cellH = 0, 0
local mapX, mapZ = 0, 0
local mapId = ""
local configId = ""
local sampleEvery = 300        -- 10s at 30fps
local terrainOnly = false
local quitAfterLast = false
local terrainFrame = 30
local terrainDone = false
local milestones = {}          -- [frame] = true
local lastMilestone = 0
local sampleCount = 0

-- Behaviour accumulation. acc[idx] = { [allyID] = {p, s, l, t}, contact = frame }
local acc = {}
local allySeen = {}

local SUB = 3                  -- sub-samples per cell axis
local buildDefID = nil

local function cellIndex(x, z)
  if cellW <= 0 or cellH <= 0 then return nil end
  local col = math.floor(x / cellW)
  local row = math.floor(z / cellH)
  if col < 0 then col = 0 elseif col >= res then col = res - 1 end
  if row < 0 then row = 0 elseif row >= res then row = res - 1 end
  return row * res + col
end

local function bucket(idx, allyID)
  local cell = acc[idx]
  if not cell then
    cell = { contact = 0 }
    acc[idx] = cell
  end
  local b = cell[allyID]
  if not b then
    -- p presence, s structures, l losses, t mobile traffic, d defences
    b = { p = 0, s = 0, l = 0, t = 0, d = 0 }
    cell[allyID] = b
  end
  allySeen[allyID] = true
  return cell, b
end

local function pickBuildDef()
  local names = { "armsolar", "corsolar", "legsolar", "armllt", "corllt" }
  for _, n in ipairs(names) do
    local ud = UnitDefNames and UnitDefNames[n]
    if ud then return ud.id end
  end
  return nil
end

--------------------------------------------------------------------------------
-- Channel A: terrain raster
--------------------------------------------------------------------------------

local function round(v, places)
  local mult = 10 ^ (places or 0)
  return math.floor((v or 0) * mult + 0.5) / mult
end

local function featureRaster()
  -- Wrecks/rocks/trees: BAR bots chase reclaim, so feature mass is real terrain
  -- economy. Returns count[idx], metal[idx].
  local counts, metals = {}, {}
  local features = Spring.GetAllFeatures() or {}
  for _, fID in ipairs(features) do
    local x, _, z = Spring.GetFeaturePosition(fID)
    if x then
      local idx = cellIndex(x, z)
      if idx then
        counts[idx] = (counts[idx] or 0) + 1
        local m = Spring.GetFeatureResources and select(1, Spring.GetFeatureResources(fID)) or 0
        metals[idx] = (metals[idx] or 0) + (m or 0)
      end
    end
  end
  return counts, metals
end

local function emitStartPositions()
  -- Map-authored start positions (what the map designer considers a base).
  -- The engine hands us the map's own list directly; mapinfo.lua is only a
  -- fallback for maps whose positions live nowhere else. Measured 2026-08-24:
  -- reading mapinfo alone returned nothing on Greenest Fields.
  local emitted = 0
  if Spring.GetMapStartPositions then
    local okPos, positions = pcall(Spring.GetMapStartPositions)
    if okPos and type(positions) == "table" then
      for i, pos in ipairs(positions) do
        local px = pos and (pos.x or pos[1])
        local pz = pos and (pos.z or pos[3])
        if px and pz and (px > 0 or pz > 0) then
          Spring.Echo(string.format("VA_TERRAIN_STARTPOS %s %.1f %.1f", tostring(i - 1), px, pz))
          emitted = emitted + 1
        end
      end
    end
  end
  if emitted == 0 then
    local ok, info = pcall(VFS.Include, "mapinfo.lua")
    if ok and type(info) == "table" and type(info.teams) == "table" then
      for i, team in pairs(info.teams) do
        local sp = team and team.startPos
        if sp and sp.x and sp.z then
          Spring.Echo(string.format("VA_TERRAIN_STARTPOS %s %.1f %.1f", tostring(i), sp.x, sp.z))
          emitted = emitted + 1
        end
      end
    end
  end
  Spring.Echo("VA_TERRAIN_STARTPOS_COUNT " .. tostring(emitted))
  local allyCount = Spring.GetAllyTeamList and #(Spring.GetAllyTeamList() or {}) or 0
  for a = 0, math.max(0, allyCount - 1) do
    if Spring.GetAllyTeamStartBox then
      local x1, z1, x2, z2 = Spring.GetAllyTeamStartBox(a)
      if x1 then
        Spring.Echo(string.format("VA_TERRAIN_STARTBOX %d %.1f %.1f %.1f %.1f", a, x1, z1, x2, z2))
      end
    end
  end
end

local function emitMetalSpots()
  local finder = GG and GG["resource_spot_finder"]
  local spots = finder and finder.metalSpotsList
  -- BAR sets metalSpotsList=false on whole-map-metal maps; a zero count on a
  -- discrete-spot map means the finder had not run yet, so record which it was.
  local isMetalMap = finder and finder.isMetalMap and "true" or "false"
  if type(spots) ~= "table" then
    local source = finder and "resource_spot_finder" or "none"
    Spring.Echo("VA_TERRAIN_SPOTS count=0 source=" .. source .. " metalMap=" .. isMetalMap)
    return
  end
  Spring.Echo("VA_TERRAIN_SPOTS count=" .. tostring(#spots) ..
    " source=resource_spot_finder metalMap=" .. isMetalMap)
  for _, spot in ipairs(spots) do
    if spot and spot.x and spot.z then
      Spring.Echo(string.format("VA_TERRAIN_SPOT %.1f %.1f %.4f", spot.x, spot.z, spot.metal or 0))
    end
  end
end

local function dumpTerrain()
  local msq = Game.metalMapSquareSize or 16
  -- Map names contain spaces, so they get their own line rather than a key=value.
  Spring.Echo("VA_TERRAIN_MAPNAME " .. tostring(Game.mapName or "unknown"))
  Spring.Echo(string.format(
    "VA_TERRAIN_META mapId=%s sx=%d sz=%d res=%d cellW=%.2f cellH=%.2f squareSize=%d metalSquare=%d",
    mapId, mapX, mapZ, res, cellW, cellH, Game.squareSize or 8, msq
  ))
  -- Per cell: height, slope, waterFrac, buildFrac, metal, tankSpeed, shipSpeed,
  -- featureCount, featureMetal.
  local featCount, featMetal = featureRaster()
  for row = 0, res - 1 do
    local parts = {}
    for col = 0, res - 1 do
      local idx = row * res + col
      local hSum, slopeMax, waterHits, buildHits, metalSum = 0, 0, 0, 0, 0
      local tankSum, shipSum, samples = 0, 0, 0
      for sz = 0, SUB - 1 do
        for sx = 0, SUB - 1 do
          local x = (col + (sx + 0.5) / SUB) * cellW
          local z = (row + (sz + 0.5) / SUB) * cellH
          local h = Spring.GetGroundHeight(x, z) or 0
          hSum = hSum + h
          if h < 0 then waterHits = waterHits + 1 end
          local _, _, _, slope = Spring.GetGroundNormal(x, z, true)
          if (slope or 0) > slopeMax then slopeMax = slope or 0 end
          if buildDefID then
            local blocking = Spring.TestBuildOrder(buildDefID, x, h, z, 0)
            -- 0 blocked, 1 mobile unit in the way, 2 reclaimable, 3 open
            if (blocking or 0) >= 2 then buildHits = buildHits + 1 end
          end
          metalSum = metalSum + (Spring.GetMetalAmount(math.floor(x / msq), math.floor(z / msq)) or 0)
          local _, _, _, _, _, _, tankSpeed, _, _, shipSpeed = Spring.GetGroundInfo(x, z)
          tankSum = tankSum + (tankSpeed or 1)
          shipSum = shipSum + (shipSpeed or 0)
          samples = samples + 1
        end
      end
      parts[#parts + 1] = table.concat({
        round(hSum / samples, 1),
        round(slopeMax, 3),
        round(waterHits / samples, 2),
        round(buildHits / samples, 2),
        round(metalSum / samples, 4),
        round(tankSum / samples, 2),
        round(shipSum / samples, 2),
        featCount[idx] or 0,
        round(featMetal[idx] or 0, 0),
      }, ",")
    end
    Spring.Echo("VA_TERRAIN_ROW " .. row .. " " .. table.concat(parts, "|"))
  end
  emitMetalSpots()
  emitStartPositions()
  Spring.Echo("VA_TERRAIN_END rows=" .. res)
end

--------------------------------------------------------------------------------
-- Channel B: behaviour raster
--------------------------------------------------------------------------------

local function sampleUnits(frame)
  local units = Spring.GetAllUnits() or {}
  local present = {}
  for _, unitID in ipairs(units) do
    local x, _, z = Spring.GetUnitPosition(unitID)
    local defID = Spring.GetUnitDefID(unitID)
    local ud = defID and UnitDefs[defID]
    if x and ud then
      local idx = cellIndex(x, z)
      if idx then
        local teamID = Spring.GetUnitTeam(unitID)
        local _, _, _, _, _, allyID = Spring.GetTeamInfo(teamID or 0, false)
        allyID = allyID or 0
        local cell, b = bucket(idx, allyID)
        local value = ud.metalCost or 0
        b.p = b.p + value
        if ud.isImmobile or (ud.speed or 0) <= 0 then
          b.s = b.s + value
          -- Armed immobiles are fortification, which is what tells a citadel
          -- apart from an economy sprawl.
          local weapons = ud.weapons
          if weapons and #weapons > 0 then
            b.d = b.d + value
          end
        else
          b.t = b.t + 1
        end
        present[idx] = present[idx] or {}
        present[idx][allyID] = true
        if cell.contact == 0 then
          local n = 0
          for _ in pairs(present[idx]) do n = n + 1 end
          if n >= 2 then cell.contact = frame end
        end
      end
    end
  end
  sampleCount = sampleCount + 1
end

local function emitBehaviour(frame)
  local allies = {}
  for allyID in pairs(allySeen) do allies[#allies + 1] = allyID end
  table.sort(allies)
  Spring.Echo(string.format(
    "VA_CARTO_MILESTONE mapId=%s config=%s frame=%d seconds=%.1f res=%d samples=%d",
    mapId, configId, frame, frame / 30, res, sampleCount
  ))
  for _, allyID in ipairs(allies) do
    local parts = {}
    local chunk = 0
    for idx, cell in pairs(acc) do
      local b = cell[allyID]
      if b and (b.p > 0 or b.s > 0 or b.l > 0 or b.t > 0) then
        parts[#parts + 1] = string.format("%d,%d,%d,%d,%d,%d", idx,
          math.floor(b.p + 0.5), math.floor(b.s + 0.5),
          math.floor(b.l + 0.5), math.floor(b.t + 0.5), math.floor(b.d + 0.5))
        if #parts >= 40 then
          chunk = chunk + 1
          Spring.Echo(string.format("VA_CARTO_CELLS f=%d a=%d c=%d %s", frame, allyID, chunk, table.concat(parts, ";")))
          parts = {}
        end
      end
    end
    if #parts > 0 then
      chunk = chunk + 1
      Spring.Echo(string.format("VA_CARTO_CELLS f=%d a=%d c=%d %s", frame, allyID, chunk, table.concat(parts, ";")))
    end
  end
  -- First-contact map (where the war actually meets), emitted once per milestone.
  local contacts = {}
  local cchunk = 0
  for idx, cell in pairs(acc) do
    if (cell.contact or 0) > 0 then
      contacts[#contacts + 1] = string.format("%d,%d", idx, cell.contact)
      if #contacts >= 60 then
        cchunk = cchunk + 1
        Spring.Echo(string.format("VA_CARTO_CONTACT f=%d c=%d %s", frame, cchunk, table.concat(contacts, ";")))
        contacts = {}
      end
    end
  end
  if #contacts > 0 then
    cchunk = cchunk + 1
    Spring.Echo(string.format("VA_CARTO_CONTACT f=%d c=%d %s", frame, cchunk, table.concat(contacts, ";")))
  end
  Spring.Echo("VA_CARTO_MILESTONE_END frame=" .. frame)
end

local function emitTeamRoster()
  local teams = Spring.GetTeamList() or {}
  for _, teamID in ipairs(teams) do
    local _, leader, isDead, isAiTeam, side, allyID = Spring.GetTeamInfo(teamID, false)
    Spring.Echo(string.format("VA_CARTO_TEAM team=%d ally=%s side=%s ai=%s dead=%s",
      teamID, tostring(allyID), tostring(side or ""), tostring(isAiTeam == true), tostring(isDead == true)))
  end
end

--------------------------------------------------------------------------------

function gadget:Initialize()
  enabled = modFlag("va_cartography")
  if not enabled then
    gadgetHandler:RemoveGadget(self)
    return
  end
  res = math.max(8, math.min(128, modInt("va_cart_res", 48)))
  mapX = Game.mapSizeX or 0
  mapZ = Game.mapSizeZ or 0
  cellW = mapX / res
  cellH = mapZ / res
  mapId = modStr("va_cart_mapid", "unknown")
  configId = modStr("va_cart_config", "default")
  sampleEvery = math.max(30, modInt("va_cart_sample_frames", 300))
  terrainOnly = modFlag("va_cart_terrain_only")
  quitAfterLast = modFlag("va_cart_quit")
  terrainFrame = math.max(2, modInt("va_cart_terrain_frame", 30))
  buildDefID = pickBuildDef()

  local msList = modStr("va_cart_milestones", "")
  for token in string.gmatch(msList, "([^,]+)") do
    local f = tonumber(token)
    if f and f > 0 then
      milestones[math.floor(f)] = true
      if f > lastMilestone then lastMilestone = math.floor(f) end
    end
  end

  Spring.Echo(string.format(
    "VA_CART_ARMED mapId=%s config=%s res=%d sample=%d terrainOnly=%s milestones=%s",
    mapId, configId, res, sampleEvery, tostring(terrainOnly), (msList ~= "" and msList or "none")
  ))

  -- Headless stalls on IconsAtlas; the shell-bake gadget learned this the hard way.
  -- useOverlay (the third arg) keeps these in memory only. Without it they are
  -- written through to the player's springsettings.cfg and survive the process,
  -- so one survey batch silently disables LuaUI for every later GUI session.
  if Spring.SetConfigInt then
    Spring.SetConfigInt("UnitIconsAsUI", 0, true)
    Spring.SetConfigInt("UnitIconDist", 99999, true)
    Spring.SetConfigInt("LuaUI", 0, true)
  end
  local speed = modInt("va_cart_speed", 20)
  if speed > 0 and Spring.SendCommands then
    Spring.SendCommands("setmaxspeed " .. speed)
    Spring.SendCommands("setminspeed " .. speed)
  end
  -- Belt and braces for unattended batches: a survey run has no human to press
  -- start. Harmless once the game is already running.
  if Spring.SendCommands then
    pcall(Spring.SendCommands, "forcestart")
  end
end

function gadget:GameFrame(frame)
  if not enabled then return end

  if not terrainDone and frame >= terrainFrame then
    terrainDone = true
    emitTeamRoster()
    dumpTerrain()
    if terrainOnly then
      Spring.Echo("VA_CART_COMPLETE mode=terrain")
      if Spring.SendCommands then Spring.SendCommands("quitforce") end
      return
    end
  end

  if terrainOnly then return end

  if frame % sampleEvery == 0 then
    sampleUnits(frame)
  end

  if milestones[frame] then
    emitBehaviour(frame)
    if frame >= lastMilestone then
      Spring.Echo("VA_CART_COMPLETE mode=behaviour frame=" .. frame)
      if quitAfterLast and Spring.SendCommands then
        Spring.SendCommands("quitforce")
      end
    end
  end
end

function gadget:UnitDestroyed(unitID, unitDefID, teamID)
  if not enabled or terrainOnly then return end
  local x, _, z = Spring.GetUnitPosition(unitID)
  if not x then return end
  local idx = cellIndex(x, z)
  if not idx then return end
  local ud = unitDefID and UnitDefs[unitDefID]
  local _, _, _, _, _, allyID = Spring.GetTeamInfo(teamID or 0, false)
  local _, b = bucket(idx, allyID or 0)
  b.l = b.l + ((ud and ud.metalCost) or 0)
end
