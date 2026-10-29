if not VFS.Include("LuaRules/Configs/va_active.lua") then return false end -- plain BAR unless the hub launched this
local gadget = gadget

function gadget:GetInfo()
  return {
    name = "Verdance Exfil",
    desc = "The manifest: what goes, what stays, where to. The sortie ends when the player confirms it (or when nobody is left to confirm).",
    author = "Verdance",
    date = "2026-10-20",
    license = "GPL v2 or later",
    layer = 8,
    enabled = true,
  }
end

-- Law: Lua reports facts, Python interprets. There is no verdict in here.
--
--   widget  --VA_CMD:manifest-->            this gadget builds the manifest (pad headcount, what is
--                                           left and where, what we looked at) and sends it up as
--                                           VERDANCE_MANIFEST json; the exfil widget pauses and shows it.
--   widget  --VA_CMD:extract:<dest>-->      the manifest (with its destination) is stamped on the
--                                           result and the campaign gadget ends the sortie: one
--                                           result, no timer, no hold, no soft-continue.
--   widget  (cancel)                        nothing to tell synced; the widget unpauses.
--   campaign gadget --wiped-->              GG.VA_Manifest() with an empty pad is stamped instead.
--
-- The pad is the zone anchor of mission.pad (Python, pass five) or of the deployment zone,
-- radius 560: in and out from the same ground, like raiders. mission.pad.links are the places
-- the company can extract TO (the camp, a holding of ours, a map link); Python moves the
-- company accordingly on the clock.

if gadgetHandler:IsSyncedCode() then

local PAD_RADIUS = 560

local mission, zoneMap
local pad = nil                 -- { zoneId, label, x, z, r }
local playerTeamID, playerAllyTeamID, gaiaTeamID = 0, 0, -1
local teamAlly = {}
local cols, rows, mapX, mapZ = 96, 96, 1, 1
local cellToZone = {}
local zoneLabel = {}
local lastManifest = nil        -- table, stamped on confirm / wipe
local anchorOf = {}             -- zoneId -> { x, z } (the zone's anchor, elmos)
local ready = false

local function jnum(v, d)
  v = tonumber(v) or 0
  local m = 10 ^ (d or 2)
  return tostring(math.floor(v * m + 0.5) / m)
end

local function jstr(s)
  s = tostring(s or "")
  s = s:gsub('\\', '\\\\'):gsub('"', '\\"'):gsub('\n', ' ')
  return '"' .. s .. '"'
end

-- Minimal JSON for plain tables (string/number/boolean/nil, arrays or string-keyed maps).
local function toJson(v)
  local t = type(v)
  if t == "table" then
    if #v > 0 or next(v) == nil then
      local parts = {}
      for i = 1, #v do parts[#parts + 1] = toJson(v[i]) end
      return '[' .. table.concat(parts, ',') .. ']'
    end
    local keys = {}
    for k in pairs(v) do keys[#keys + 1] = tostring(k) end
    table.sort(keys)
    local parts = {}
    for _, k in ipairs(keys) do parts[#parts + 1] = jstr(k) .. ':' .. toJson(v[k]) end
    return '{' .. table.concat(parts, ',') .. '}'
  elseif t == "number" then
    if v ~= v or v == math.huge or v == -math.huge then return 'null' end
    if v == math.floor(v) then return tostring(math.floor(v)) end
    return jnum(v, 3)
  elseif t == "boolean" then
    return v and 'true' or 'false'
  elseif t == "string" then
    return jstr(v)
  end
  return 'null'
end

local function readLua(path)
  local ok, data = pcall(VFS.Include, path)
  if ok and type(data) == "table" then return data end
  return nil
end

local function norm(v, size)
  v = tonumber(v) or 0
  if v <= 1 then return v * size end
  return v
end

local function expandRuns(z)
  local out = {}
  local runs = z.cells
  if type(runs) == "table" and #runs > 0 and z.shape == "cells" then
    for _, run in ipairs(runs) do
      local start = tonumber(run[1]) or tonumber(run.start) or 0
      local len = tonumber(run[2]) or tonumber(run.length) or 0
      for i = 0, len - 1 do out[#out + 1] = start + i end
    end
    return out
  end
  local b = z.bounds or {}
  local function n(v) v = tonumber(v) or 0; if v > 1 then return v / (mapX > mapZ and mapX or mapZ) end; return v end
  local c1, c2 = math.floor(n(b.xMin) * cols), math.ceil(n(b.xMax) * cols) - 1
  local r1, r2 = math.floor(n(b.zMin) * rows), math.ceil(n(b.zMax) * rows) - 1
  for r = math.max(0, r1), math.min(rows - 1, r2) do
    for c = math.max(0, c1), math.min(cols - 1, c2) do out[#out + 1] = r * cols + c end
  end
  return out
end

local function zoneOf(x, z)
  if not x or not z then return nil end
  local c = math.floor(x / mapX * cols)
  local r = math.floor(z / mapZ * rows)
  if c < 0 or r < 0 or c >= cols or r >= rows then return nil end
  return cellToZone[r * cols + c]
end

-- The pad is the whole zone the company leaves from. Publishes it for the HUD.
local homePad = nil   -- where the company landed: always an extraction point

local function placePad(zid, x, z, r)
  pad = { zoneId = zid, label = zoneLabel[zid] or zid, x = x, z = z, r = r }
  if not homePad then homePad = { zoneId = zid, label = zoneLabel[zid] or zid } end
  -- The pad is the whole zone the company landed in (the infil zone), not a circle inside it.
  -- reach: the farthest corner of the zone from the pad point, for the unit queries below.
  local cw, ch, reach, cells = mapX / cols, mapZ / rows, 0, 0
  for ci, owner in pairs(cellToZone) do
    if owner == zid then
      cells = cells + 1
      local cx, cz = (ci % cols) * cw, math.floor(ci / cols) * ch
      for _, k in ipairs({ { 0, 0 }, { 1, 0 }, { 0, 1 }, { 1, 1 } }) do
        local dx, dz = cx + k[1] * cw - x, cz + k[2] * ch - z
        reach = math.max(reach, math.sqrt(dx * dx + dz * dz))
      end
    end
  end
  pad.zoned = cells > 0
  pad.reach = pad.zoned and reach or pad.r
  Spring.SetGameRulesParam("va_pad_x", math.floor(x), { public = true })
  Spring.SetGameRulesParam("va_pad_z", math.floor(z), { public = true })
  Spring.SetGameRulesParam("va_pad_r", math.floor(pad.r), { public = true })
  Spring.SetGameRulesParam("va_pad_zone", zid, { public = true })
  Spring.Echo("VA_EXFIL pad=" .. zid .. " x=" .. math.floor(x) .. " z=" .. math.floor(z))
end

-- Taking a door (mission.exitDoorZoneId): once the objective is done the extraction moves onto the
-- door, so the company leaves by the exit it took.
local function maybeMoveToExit()
  if not pad then return end
  if (tonumber((Spring.GetGameRulesParam("va_objective_complete"))) or 0) ~= 1 then return end
  local exit = mission and mission.exitDoorZoneId and tostring(mission.exitDoorZoneId)
  if exit and pad.zoneId ~= exit and anchorOf[exit] then
    placePad(exit, anchorOf[exit][1], anchorOf[exit][2], PAD_RADIUS)
    Spring.SetGameRulesParam("va_pad_moved", 1, { public = true })
    Spring.Echo("VA_EXFIL pad moved to the exit door " .. exit)
    return
  end
  -- Territory: the company extracts on the ground it took, once it is secured. What it built there
  -- stays (the footprint is the zone's holdings); nobody has to walk back to the drop.
  local zone = nil
  if GG.VA_ExtractRule then rule, zone = GG.VA_ExtractRule() end
  if rule == "territory" and zone and zone ~= "" and pad.zoneId ~= zone and anchorOf[zone] then
    placePad(zone, anchorOf[zone][1], anchorOf[zone][2], PAD_RADIUS)
    Spring.SetGameRulesParam("va_pad_moved", 1, { public = true })
    Spring.SetGameRulesParam("va_pad_territory", 1, { public = true })
    Spring.Echo("VA_EXFIL pad moved onto the secured territory " .. zone)
  end
end

local function build()
  mission = readLua("singleplayer/verdance_ashes/generated/va_current.lua")
  zoneMap = (mission and type(mission.zoneMap) == "table" and mission.zoneMap)
    or readLua("singleplayer/verdance_ashes/generated/zone_map_current.lua")
  if not mission or not zoneMap or type(zoneMap.zones) ~= "table" then
    Spring.Echo("VA_EXFIL idle: mission or zone map missing")
    return false
  end
  mapX, mapZ = Game.mapSizeX or 1, Game.mapSizeZ or 1
  local g = (zoneMap.zones[1] and zoneMap.zones[1].cellGrid) or zoneMap.grid or {}
  cols, rows = tonumber(g.cols) or 96, tonumber(g.rows) or 96
  cellToZone, zoneLabel = {}, {}
  local anchors = {}
  anchorOf = anchors
  for _, z in ipairs(zoneMap.zones) do
    local id = tostring(z.zoneId or "")
    if id ~= "" then
      zoneLabel[id] = tostring(z.label or id)
      for _, ci in ipairs(expandRuns(z)) do
        if cellToZone[ci] == nil then cellToZone[ci] = id end
      end
      local a = z.anchor
      if type(a) == "table" and tonumber(a.x) then
        anchors[id] = { norm(a.x, mapX), norm(a.z, mapZ) }
      else
        local b = z.bounds or {}
        anchors[id] = { (norm(b.xMin, mapX) + norm(b.xMax, mapX)) * 0.5, (norm(b.zMin, mapZ) + norm(b.zMax, mapZ)) * 0.5 }
      end
    end
  end
  -- the pad: Python's single point when present, else the deployment zone's anchor
  local p = type(mission.pad) == "table" and mission.pad or readLua("singleplayer/verdance_ashes/generated/va_pad_current.lua")
  if p and p.mapId and mission.deploymentMapId and tostring(p.mapId) ~= tostring(mission.deploymentMapId) then
    Spring.Echo("VA_EXFIL pad file is for " .. tostring(p.mapId) .. ", mission is " .. tostring(mission.deploymentMapId) .. "; using the deployment zone")
    p = nil
  end
  local zid = tostring((p and p.zoneId) or mission.deploymentZoneId or mission.extractionZoneId or "")
  local x, z
  if p and tonumber(p.x) and tonumber(p.z) then
    x, z = norm(p.x, mapX), norm(p.z, mapZ)
  elseif anchors[zid] then
    x, z = anchors[zid][1], anchors[zid][2]
  end
  if not x then
    Spring.Echo("VA_EXFIL idle: no pad for zone " .. zid)
    return false
  end
  placePad(zid, x, z, tonumber(p and p.radius) or PAD_RADIUS)
  return true
end

local function resolvePlayerTeam()
  gaiaTeamID = Spring.GetGaiaTeamID()
  for _, tid in ipairs(Spring.GetTeamList()) do
    local _, _, _, _, _, at = Spring.GetTeamInfo(tid, false)
    teamAlly[tid] = tonumber(at or -1) or -1
  end
  playerTeamID = tonumber(mission and mission.balance and mission.balance.playerTeamID) or 0
  if teamAlly[playerTeamID] == nil then
    local fallback
    for _, tid in ipairs(Spring.GetTeamList()) do
      if tid ~= gaiaTeamID and (fallback == nil or tid < fallback) then fallback = tid end
    end
    playerTeamID = fallback or 0
  end
  playerAllyTeamID = teamAlly[playerTeamID] or 0
end

-- Extract anywhere (modoption va_extract_anywhere=1; the autopilot turns it on): when the
-- extraction is called, the pad goes to the zone where most of the company stands (a hero
-- weighs five units). Whoever is elsewhere stays in the field, as before. Python reads the
-- pad off the manifest like any other.
local function extractAnywhere()
  local o = Spring.GetModOptions and Spring.GetModOptions() or {}
  if tostring(o.va_extract_anywhere) ~= "1" then return false end
  local rule = GG.VA_ExtractRule and GG.VA_ExtractRule() or "deployment"
  return rule ~= "territory"
end

local function padToCompany()
  if not pad then return false end
  if next(teamAlly) == nil then resolvePlayerTeam() end
  local weight = {}
  for _, uid in ipairs(Spring.GetTeamUnits(playerTeamID) or {}) do
    if Spring.ValidUnitID(uid) and not Spring.GetUnitIsDead(uid) then
      local dID = Spring.GetUnitDefID(uid)
      local ud = dID and UnitDefs[dID]
      local structure = ud and (ud.isBuilding or ud.isFactory or ((ud.speed or 1) == 0))
      if not structure then
        local x, _, z = Spring.GetUnitPosition(uid)
        local zid = zoneOf(x, z)
        if zid and anchorOf[zid] then
          local hid = Spring.GetUnitRulesParam(uid, "va_hero_id")
          local isHero = hid ~= nil and tostring(hid) ~= "" and tostring(hid) ~= "0"
          weight[zid] = (weight[zid] or 0) + (isHero and 5 or 1)
        end
      end
    end
  end
  local best, bw = nil, 0
  for zid, w in pairs(weight) do
    if w > bw or (w == bw and best and zid < best) then best, bw = zid, w end
  end
  if not best or best == pad.zoneId then return false end
  local from = pad.zoneId
  placePad(best, anchorOf[best][1], anchorOf[best][2], PAD_RADIUS)
  Spring.SetGameRulesParam("va_pad_moved", 1, { public = true })
  Spring.Echo("VA_EXFIL extract anywhere: pad " .. tostring(from) .. " -> " .. best .. " weight=" .. bw)
  return true
end

GG.VA_PadToCompany = padToCompany
GG.VA_ZoneAnchor = function(zid) local a = anchorOf[tostring(zid or "")]; if a then return a[1], a[2] end end

local function destinations()
  local out = { { id = "home", label = "Back to camp", kind = "camp" } }
  local links = mission and mission.pad and mission.pad.links
  if type(links) == "table" then
    for _, l in ipairs(links) do
      if type(l) == "table" and l.zoneId then
        out[#out + 1] = { id = tostring(l.zoneId), label = tostring(l.label or l.zoneId), mapId = l.mapId, kind = tostring(l.kind or "link") }
      end
    end
  end
  return out
end

-- On the pad = in the pad zone (falls back to the circle only if the zone has no cells).
local function onPadAt(x, z)
  if not pad or not x or not z then return false end
  if pad.zoned then return zoneOf(x, z) == pad.zoneId end
  local dx, dz = x - pad.x, z - pad.z
  return dx * dx + dz * dz <= pad.r * pad.r
end

-- Extraction points (owner call, 2026-10-29): every zone the company owns. Everything of ours
-- standing in one lifts on extract, rescues included, and goes into the one reserve: the pad
-- zone, where we landed, the zones the engine names as ours (mission.safeZoneIds: held road doors
-- and our own ground), and any zone we own right now by the one rule (include/va_claim.lua: AV+DV
-- over 1500 and over three times everyone else's), ground taken this sortie included.
local VA_CLAIM = VFS.Include("luarules/gadgets/include/va_claim.lua")
local liveOwned, liveOwnedAt = {}, -1000
local function refreshLiveOwned(force)
  local f = Spring.GetGameFrame() or 0
  if not force and f - liveOwnedAt < 30 then return end
  liveOwnedAt = f
  liveOwned = {}
  local need = mission and mission.objective and tonumber(mission.objective.claimValue) or VA_CLAIM.NEED
  local dv = GG.VA_ZoneDv and GG.VA_ZoneDv() or {}
  for zid, row in pairs(dv) do
    if VA_CLAIM.ours(row, need) then liveOwned[tostring(zid)] = true end
  end
end

local function safeZone(zid)
  if not zid or zid == "" or zid == "?" then return false end
  if pad and zid == pad.zoneId then return true end
  if homePad and zid == homePad.zoneId then return true end
  if liveOwned[zid] then return true end
  local ids = mission and mission.safeZoneIds
  if type(ids) == "table" then
    for _, z in ipairs(ids) do if tostring(z) == zid then return true end end
  end
  return false
end

-- The extraction points besides the pad, for the board (va_lift_zones, comma-separated).
local liftZonesSeen = nil
local function publishLiftZones()
  local ids, seen = {}, {}
  local function add(z)
    z = tostring(z or "")
    if z ~= "" and not seen[z] and not (pad and z == pad.zoneId) and anchorOf[z] then seen[z] = true; ids[#ids + 1] = z end
  end
  if homePad then add(homePad.zoneId) end
  for _, z in ipairs((mission and type(mission.safeZoneIds) == "table" and mission.safeZoneIds) or {}) do add(z) end
  for z in pairs(liveOwned) do add(z) end
  table.sort(ids)
  local s = table.concat(ids, ",")
  if s ~= liftZonesSeen then
    liftZonesSeen = s
    Spring.SetGameRulesParam("va_lift_zones", s, { public = true })
  end
end

local function liftsFrom(x, z)
  if onPadAt(x, z) then return true end
  return safeZone(zoneOf(x, z))
end

local function enemiesOnPad()
  local n = 0
  for _, uid in ipairs(Spring.GetUnitsInCylinder(pad.x, pad.z, pad.reach) or {}) do
    local team = Spring.GetUnitTeam(uid)
    if team ~= nil and team ~= gaiaTeamID and not Spring.AreTeamsAllied(playerTeamID, team) then
      -- an enemy that can move; walls and turrets in the zone are not "on the pad"
      local ud = UnitDefs[Spring.GetUnitDefID(uid) or -1]
      local mobile = ud and not ud.isBuilding and (ud.speed or 0) > 0
      local ux, _, uz = Spring.GetUnitPosition(uid)
      if mobile and onPadAt(ux, uz) then n = n + 1 end
    end
  end
  return n
end

-- What lifts: anything mobile on an extraction point, and every hero whose body is a building
-- (Hearth's fusion, the scout bays Spoke, Tick and Noctua, a turret hero, and any building hero
-- to come: the test is the body, not a list) wherever they stand: the company packs a person up,
-- it does not leave them for being a building.
local function lifts(isHero, structure, onPad)
  if isHero and structure then return true end
  return onPad and not structure
end

-- The manifest is a headcount, not a judgement.
local function manifest()
  local m = {
    schema = "verdance-manifest/1",
    frame = Spring.GetGameFrame() or 0,
    pad = pad and { zoneId = pad.zoneId, label = pad.label, x = math.floor(pad.x), z = math.floor(pad.z), radius = pad.r } or nil,
    destinations = destinations(),
    going = { heroes = {}, units = {}, packUnits = {}, hiredUnits = {}, unitCount = 0, structures = 0, metal = 0 },
    staying = { heroes = {}, units = {}, unitCount = 0, structures = {}, structureCount = 0, metal = 0 },
    enemyOnPad = 0,
    seen = {},
  }
  -- Heroes already through the Spire Gate (game_verdance_jump_gate.lua) are going home.
  if GG.VA_JumpPorted then
    for _, h in ipairs(GG.VA_JumpPorted() or {}) do m.going.heroes[#m.going.heroes + 1] = h end
  end
  if not pad then return m end
  refreshLiveOwned(true)
  publishLiftZones()
  m.liftZones = {}
  for z in tostring(liftZonesSeen or ""):gmatch("[^,]+") do m.liftZones[#m.liftZones + 1] = zoneLabel[z] or z end
  local units = Spring.GetTeamUnits(playerTeamID) or {}
  for i = 1, #units do
    local uid = units[i]
    if Spring.ValidUnitID(uid) and not Spring.GetUnitIsDead(uid) then
      local x, _, z = Spring.GetUnitPosition(uid)
      local dID = Spring.GetUnitDefID(uid)
      local ud = dID and UnitDefs[dID]
      local structure = ud and (ud.isBuilding or ud.isFactory or ((ud.speed or 1) == 0))
      local metal = (ud and ud.metalCost) or 0
      local hid = Spring.GetUnitRulesParam(uid, "va_hero_id")
      local hname = Spring.GetUnitRulesParam(uid, "va_hero_name")
      local onPad = liftsFrom(x, z)
      local zid = zoneOf(x, z) or "?"
      -- a pair's partner is named on the field but travels as its lead's pack
      local partner = Spring.GetUnitRulesParam(uid, "va_partner_of")
      local isHero = hid and hid ~= "" and hid ~= 0 and not (partner and partner ~= "")
      if lifts(isHero, structure, onPad) then
        local g = m.going
        if isHero then
          g.heroes[#g.heroes + 1] = { heroId = tostring(hid), name = tostring(hname or hid), unitDef = ud and ud.name or "" }
        else
          g.units[ud and ud.name or "?"] = (g.units[ud and ud.name or "?"] or 0) + 1
          g.unitCount = g.unitCount + 1
          -- A hero's pack and escorts come back with the hero every drop; everything else that
          -- lifts is the company's army and goes into the reserve (units minus packUnits).
          local tag = tostring(Spring.GetUnitRulesParam(uid, "va_package_tag") or "")
          if tag:sub(1, 5) == "crew_" then
            g.packUnits[ud and ud.name or "?"] = (g.packUnits[ud and ud.name or "?"] or 0) + 1
          end
          -- the shop hires for one drop: delivered units lift but never join the reserve
          local hired = tostring(Spring.GetUnitRulesParam(uid, "va_delivery_mode") or "")
          if hired ~= "" and hired ~= "0" then
            g.hiredUnits[ud and ud.name or "?"] = (g.hiredUnits[ud and ud.name or "?"] or 0) + 1
          end
        end
        g.metal = g.metal + metal
      else
        local s = m.staying
        if isHero then
          s.heroes[#s.heroes + 1] = { heroId = tostring(hid), name = tostring(hname or hid), zoneId = zid, label = zoneLabel[zid] or zid }
        elseif structure then
          local row = s.structures[zid] or { count = 0, metal = 0, label = zoneLabel[zid] or zid }
          row.count = row.count + 1
          row.metal = row.metal + metal
          s.structures[zid] = row
          s.structureCount = s.structureCount + 1
        else
          s.units[zid] = (s.units[zid] or 0) + 1
          s.unitCount = s.unitCount + 1
        end
        s.metal = s.metal + metal
      end
    end
  end
  -- who else is standing on our pad
  m.enemyOnPad = enemiesOnPad()
  -- what we looked at (observe gadget), as a map zone -> eta
  if GG and GG.VA_ObservedZonesTable then
    m.seen = GG.VA_ObservedZonesTable() or {}
  end
  m.tenebrium = (GG and GG.VA_TenebriumBank) and GG.VA_TenebriumBank() or nil
  m.objectiveComplete = (tonumber((Spring.GetGameRulesParam("va_objective_complete"))) or 0) == 1
  -- who of the company dropped onto this field (the campaign gadget's va_dropped_heroes)
  m.dropped = {}
  for h in tostring(Spring.GetGameRulesParam("va_dropped_heroes") or ""):gmatch("[^,]+") do m.dropped[#m.dropped + 1] = h end
  return m
end

-- ---------------------------------------------------------------- HUD truth (pass seven)
-- The one scan the HUD reads instead of guessing from its own unit loops, every 30 frames:
--   va_hud_heroes_json  [{id,name,unit,hp,x,z,onPad,zone,crit,level,rank,vet,fx,fxOn,state}] + down wrecks
--   va_pad_people / va_pad_units      what is inside the ring right now (would lift)
--   va_pad_off_units / va_pad_off_structures   what would stay
--   va_pad_enemy_live                 who else stands on our pad (visible to us)
local function hudScan()
  if not pad then return end
  refreshLiveOwned()
  publishLiftZones()
  if next(teamAlly) == nil then resolvePlayerTeam() end
  local heroes = {}
  local onPeople, onUnits, offUnits, offStructures = 0, 0, 0, 0
  for _, uid in ipairs(Spring.GetTeamUnits(playerTeamID) or {}) do
    if Spring.ValidUnitID(uid) and not Spring.GetUnitIsDead(uid) then
      local x, _, z = Spring.GetUnitPosition(uid)
      local dID = Spring.GetUnitDefID(uid)
      local ud = dID and UnitDefs[dID]
      local structure = ud and (ud.isBuilding or ud.isFactory or ((ud.speed or 1) == 0))
      local hid = Spring.GetUnitRulesParam(uid, "va_hero_id")
      local isHero = hid ~= nil and tostring(hid) ~= "" and tostring(hid) ~= "0"
      local onPad = liftsFrom(x, z)
      if isHero and structure then
        onPeople = onPeople + 1
        onPad = true            -- packed up where it stands: it lifts with the company
      elseif structure then
        offStructures = offStructures + 1
      elseif onPad then
        if isHero then onPeople = onPeople + 1 else onUnits = onUnits + 1 end
      elseif not isHero then
        offUnits = offUnits + 1
      end
      if isHero then
        local hp, maxHp = Spring.GetUnitHealth(uid)
        heroes[#heroes + 1] = {
          id = tostring(hid), name = tostring(Spring.GetUnitRulesParam(uid, "va_hero_name") or hid), unit = uid,
          hp = (hp and maxHp and maxHp > 0) and (hp / maxHp) or 1, x = math.floor(x or 0), z = math.floor(z or 0),
          onPad = onPad, zone = zoneOf(x, z) or "", crit = (tonumber((Spring.GetUnitRulesParam(uid, "va_hero_critical"))) or 0) == 1,
          level = tonumber((Spring.GetUnitRulesParam(uid, "va_hero_level"))) or 1, rank = tostring(Spring.GetUnitRulesParam(uid, "va_hero_rank") or ""),
          vet = tostring(Spring.GetUnitRulesParam(uid, "va_vet_rank") or ""), state = "alive",
          fx = tostring(Spring.GetUnitRulesParam(uid, "va_hero_tag_labels") or ""),
          fxOn = (tonumber((Spring.GetUnitRulesParam(uid, "va_fx_self_on"))) or 0) == 1,
          dist = math.floor(math.sqrt(((x or 0) - pad.x) ^ 2 + ((z or 0) - pad.z) ^ 2)),
        }
      end
    end
  end
  -- down heroes: the campaign's own wreck ledger (hero_wrecks.lua), not a walk over every tree
  local function addWreck(fid)
    local name = Spring.GetFeatureRulesParam(fid, "va_hero_wreck_name")
    if type(name) == "string" and name ~= "" then
      local fx, _, fz = Spring.GetFeaturePosition(fid)
      local hid = Spring.GetFeatureRulesParam(fid, "va_hero_wreck")
      heroes[#heroes + 1] = { id = tostring(hid or name), name = name, x = math.floor(fx or 0), z = math.floor(fz or 0), zone = zoneOf(fx, fz) or "", state = "down", feature = fid }
    end
  end
  local wrecks = GG.VA_HeroWreckFeatures
  if type(wrecks) == "table" then
    for fid in pairs(wrecks) do if Spring.ValidFeatureID(fid) then addWreck(fid) end end
  else
    for _, fid in ipairs(Spring.GetAllFeatures() or {}) do addWreck(fid) end
  end
  local enemy = enemiesOnPad()
  Spring.SetGameRulesParam("va_hud_heroes_json", toJson(heroes), { public = true })
  Spring.SetGameRulesParam("va_pad_people", onPeople, { public = true })
  Spring.SetGameRulesParam("va_pad_units", onUnits, { public = true })
  Spring.SetGameRulesParam("va_pad_off_units", offUnits, { public = true })
  Spring.SetGameRulesParam("va_pad_off_structures", offStructures, { public = true })
  Spring.SetGameRulesParam("va_pad_enemy_live", enemy, { public = true })
end

-- Memory watch (a playtest hit BAR's 1.2 GB Lua limit): once a game minute, the synced heap as it
-- stands. It no longer forces a full collection to measure before/after: on a slow machine that
-- was a stall of its own. The LuaUI side is logged by the minimap widget.
local function memWatch(f, side)
  if f % 1800 ~= 900 or not collectgarbage then return end
  Spring.Echo(string.format("VA_LUAMEM %s frame=%d heap=%.0fMB", side, f, collectgarbage("count") / 1024))
end

function gadget:GameFrame(f)
  memWatch(f, "rules")
  if ready and f % 30 == 7 then maybeMoveToExit(); hudScan() end
end

function GG.VA_Manifest()
  if not ready then return nil end
  return manifest()
end

function GG.VA_ManifestJson()
  if lastManifest == nil then return 'null' end
  return toJson(lastManifest)
end

local function endWith(kind, dest)
  local m = manifest()
  m.destination = dest or "home"
  m.kind = kind
  lastManifest = m
  Spring.Echo("VA_MANIFEST " .. kind .. " dest=" .. tostring(m.destination)
    .. " going=" .. tostring(#m.going.heroes) .. "h/" .. tostring(m.going.unitCount)
    .. " staying=" .. tostring(#m.staying.heroes) .. "h/" .. tostring(m.staying.unitCount) .. "u/" .. tostring(m.staying.structureCount) .. "s")
  -- The campaign gadget reads va_pad_enemy inside VA_EndSortie (extractionClean), so it
  -- must be on the board before the call, not after.
  Spring.SetGameRulesParam("va_pad_enemy", tonumber(m.enemyOnPad) or 0, { public = true })
  if GG and GG.VA_EndSortie then
    GG.VA_EndSortie(kind)
  else
    Spring.Echo("VA_EXFIL_ERR campaign gadget did not register VA_EndSortie")
  end
end

-- the campaign gadget calls this when the company is wiped: same manifest, nobody on the pad
function GG.VA_WipedManifest()
  if not ready then return false end -- no pad loaded: the campaign gadget ends the sortie itself
  endWith("wiped", "none")
  return true
end

function gadget:Initialize()
  ready = build()
end

function gadget:GameStart()
  resolvePlayerTeam()
  if not ready then ready = build() end
end

-- The campaign gadget hands us "manifest" and "extract:<dest>" (GG.VA_ExfilCmd): a message
-- sent to every gadget can be swallowed by an earlier one, and in BAR it was.
local function exfilCmd(cmd)
  if cmd == "manifest" then
    if not ready then Spring.Echo("VA_EXFIL_ERR not ready"); return end
    if next(teamAlly) == nil then resolvePlayerTeam() end
    if extractAnywhere() then padToCompany() end
    local m = manifest()
    -- Posted as rules params (how every HUD fact travels); the exfil widget opens on a new seq.
    local seq = (tonumber((Spring.GetGameRulesParam("va_manifest_seq"))) or 0) + 1
    Spring.SetGameRulesParam("va_manifest_json", toJson(m), { public = true })
    Spring.SetGameRulesParam("va_manifest_seq", seq, { public = true })
    Spring.Echo("VA_EXFIL_MANIFEST seq=" .. seq .. " going=" .. #m.going.heroes .. "h/" .. m.going.unitCount
      .. " staying=" .. #m.staying.heroes .. "h/" .. m.staying.unitCount .. "u enemyOnPad=" .. m.enemyOnPad)
    return true
  end
  local dest = cmd:match("^extract:(.+)$")
  if dest then
    if not ready then Spring.Echo("VA_EXFIL_ERR not ready"); return end
    if next(teamAlly) == nil then resolvePlayerTeam() end
    if extractAnywhere() then padToCompany() end
    endWith("extracted", dest)
    return true
  end
  return false
end

GG.VA_ExfilCmd = exfilCmd

function gadget:Shutdown()
  GG.VA_ExfilCmd = nil
  GG.VA_Manifest = nil
  GG.VA_ManifestJson = nil
  GG.VA_WipedManifest = nil
  GG.VA_PadToCompany = nil
  GG.VA_ZoneAnchor = nil
end

else -- unsynced: close the game a few seconds after the sortie ends (the widget shows the card)

local quitAt = nil

function gadget:Update()
  if not quitAt and (tonumber((Spring.GetGameRulesParam("va_terminal"))) or 0) == 1 then
    quitAt = os.clock() + 6.0
  end
  if quitAt and os.clock() >= quitAt then
    quitAt = math.huge
    Spring.Echo("VA_SORTIE_QUIT")
    Spring.SendCommands("quitforce")
  end
end

end
