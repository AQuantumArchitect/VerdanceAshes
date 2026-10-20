local gadget = gadget

function gadget:GetInfo()
  return {
    name = "Verdance Belief Observe",
    desc = "How hard the company looked at each zone (line-of-sight share, recency weighted) and what it saw there; exported on the result as observedZones / beliefExport",
    author = "Verdance",
    date = "2026-10-19",
    license = "GPL v2 or later",
    layer = 7,
    enabled = true,
  }
end

if not gadgetHandler:IsSyncedCode() then
  return
end

-- A SEPARATE gadget from game_verdance_campaign.lua on purpose: that chunk sits at
-- the Lua local limit. We publish two functions on GG that resultJson() splices in:
--
--   GG.VA_ObservedZonesJson()  -> {"GF_S_PLATEAU":0.83, ...}      eta per zone, 0..1
--   GG.VA_BeliefExportJson()   -> {"GF_S_PLATEAU":{"ours":..,"held":..,"strength":..,"threat":..}, ...}
--
-- eta is the share of a zone's cells inside the player's line of sight, with a
-- recency half-life: a zone fully seen eight minutes ago reads 0.5 now. The campaign
-- engine (tools/belief_homecoming_v1.py) observes the Drop's truth for each zone at
-- exactly that eta, so a zone we drove through is known and a zone we only glanced at
-- stays a rumour. beliefExport is what the HUD could honestly have believed at exit
-- about zones it saw only partly: units and structures spotted, by side.
--
-- Live, for the overlay widget: GameRulesParam "va_obs_<zoneId>" = eta (public),
-- "va_obs_enemy_<zoneId>" = enemy units seen recently, "va_obs_tick" = sample count.

local SAMPLE_EVERY = 60            -- frames (2 s)
local HALF_LIFE_FRAMES = 8 * 60 * 30
local MAX_POINTS_PER_ZONE = 36
local RECENT_DECAY = 0.85          -- per sample, for "enemy seen recently"

local zones = {}      -- zoneId -> { id, label, points = {{x,y,z},...}, cellIndex = {} }
local zoneOrder = {}
local cellToZone = {} -- row*cols+col -> zoneId
local cols, rows = 96, 96
local mapX, mapZ = 1, 1
local playerTeamID, playerAllyTeamID = 0, 0
local gaiaTeamID = -1
local teamAlly = {}
local ready = false
local tick = 0

local obs = {}        -- zoneId -> { eta, lastShare, enemyRecent, enemyPeak, friendNow, enemyStructPeak, friendStructPeak, seenAny }

local function clamp01(v)
  if v ~= v then return 0 end
  if v < 0 then return 0 end
  if v > 1 then return 1 end
  return v
end

local function jnum(v, digits)
  v = tonumber(v) or 0
  local m = 10 ^ (digits or 3)
  return tostring(math.floor(v * m + 0.5) / m)
end

local function jstr(s)
  s = tostring(s or "")
  s = s:gsub('\\', '\\\\'):gsub('"', '\\"'):gsub('\n', ' ')
  return '"' .. s .. '"'
end

local function readLua(path)
  local ok, data = pcall(VFS.Include, path)
  if ok and type(data) == "table" then return data end
  return nil
end

local function expandRuns(z)
  local out = {}
  local runs = z.cells
  if type(runs) == "table" and #runs > 0 and z.shape == "cells" then
    for _, run in ipairs(runs) do
      local start = tonumber(run[1]) or tonumber(run.start) or 0
      local len = tonumber(run[2]) or tonumber(run.length) or 0
      for i = 0, len - 1 do
        out[#out + 1] = start + i
      end
    end
    return out
  end
  -- rect fallback: rasterise bounds onto the grid
  local b = z.bounds or {}
  local function n(v) v = tonumber(v) or 0; if v > 1 then return v / (mapX > mapZ and mapX or mapZ) end; return v end
  local c1, c2 = math.floor(n(b.xMin) * cols), math.ceil(n(b.xMax) * cols) - 1
  local r1, r2 = math.floor(n(b.zMin) * rows), math.ceil(n(b.zMax) * rows) - 1
  for r = math.max(0, r1), math.min(rows - 1, r2) do
    for c = math.max(0, c1), math.min(cols - 1, c2) do
      out[#out + 1] = r * cols + c
    end
  end
  return out
end

local function build()
  zones, zoneOrder, cellToZone, obs = {}, {}, {}, {}
  local zm = readLua("singleplayer/verdance_ashes/generated/zone_map_current.lua")
  if not zm or type(zm.zones) ~= "table" then
    Spring.Echo("VA_OBS zone map missing; belief observe idle")
    return false
  end
  mapX = Game.mapSizeX or 1
  mapZ = Game.mapSizeZ or 1
  local g = (zm.zones[1] and zm.zones[1].cellGrid) or zm.grid or {}
  cols = tonumber(g.cols) or 96
  rows = tonumber(g.rows) or 96
  local cw, ch = mapX / cols, mapZ / rows
  for _, z in ipairs(zm.zones) do
    local id = tostring(z.zoneId or "")
    if id ~= "" then
      local idx = expandRuns(z)
      local rec = { id = id, label = tostring(z.label or id), points = {}, n = #idx }
      for _, ci in ipairs(idx) do
        if cellToZone[ci] == nil then cellToZone[ci] = id end
      end
      local stride = math.max(1, math.floor(#idx / MAX_POINTS_PER_ZONE))
      for k = 1, #idx, stride do
        local ci = idx[k]
        local c = ci % cols
        local r = math.floor(ci / cols)
        local x = (c + 0.5) * cw
        local zz = (r + 0.5) * ch
        rec.points[#rec.points + 1] = { x, Spring.GetGroundHeight(x, zz) or 0, zz }
      end
      zones[id] = rec
      zoneOrder[#zoneOrder + 1] = id
      obs[id] = { eta = 0, lastShare = 0, enemyRecent = 0, enemyPeak = 0, friendNow = 0, enemyStructPeak = 0, friendStructPeak = 0, seenAny = false, enemyNow = 0 }
    end
  end
  Spring.Echo("VA_OBS zones=" .. tostring(#zoneOrder) .. " grid=" .. cols .. "x" .. rows)
  return #zoneOrder > 0
end

local function resolvePlayerTeam()
  gaiaTeamID = Spring.GetGaiaTeamID()
  for _, tid in ipairs(Spring.GetTeamList()) do
    local _, _, _, _, _, at = Spring.GetTeamInfo(tid, false)
    teamAlly[tid] = tonumber(at or -1) or -1
  end
  local mission = readLua("singleplayer/verdance_ashes/generated/va_current.lua")
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

local function zoneOfPos(x, z)
  if not x or not z then return nil end
  local c = math.floor(x / mapX * cols)
  local r = math.floor(z / mapZ * rows)
  if c < 0 or r < 0 or c >= cols or r >= rows then return nil end
  return cellToZone[r * cols + c]
end

local function sample(frame)
  if next(teamAlly) == nil then resolvePlayerTeam() end  -- loaded mid-game (/luarules reload)
  tick = tick + 1
  local decay = 0.5 ^ (SAMPLE_EVERY / HALF_LIFE_FRAMES)
  -- 1. line of sight share per zone
  for _, id in ipairs(zoneOrder) do
    local rec, o = zones[id], obs[id]
    local seen = 0
    for i = 1, #rec.points do
      local p = rec.points[i]
      if Spring.IsPosInLos(p[1], p[2], p[3], playerAllyTeamID) then seen = seen + 1 end
    end
    local share = (#rec.points > 0) and (seen / #rec.points) or 0
    o.lastShare = share
    o.eta = math.max(o.eta * decay, share)
    o.enemyRecent = o.enemyRecent * RECENT_DECAY
    o.friendNow = 0
    o.enemyNow = 0
    if share > 0 then o.seenAny = true end
  end
  -- 2. what is standing in the zones we can see
  local units = Spring.GetAllUnits() or {}
  local friendStruct, enemyStruct = {}, {}
  for i = 1, #units do
    local uid = units[i]
    local team = Spring.GetUnitTeam(uid)
    if team ~= nil and team ~= gaiaTeamID then
      local ally = teamAlly[team]
      local friendly = (ally == playerAllyTeamID)
      if friendly or Spring.IsUnitInLos(uid, playerAllyTeamID) then
        local x, _, z = Spring.GetUnitPosition(uid)
        local id = zoneOfPos(x, z)
        if id and obs[id] then
          local dID = Spring.GetUnitDefID(uid)
          local ud = dID and UnitDefs[dID]
          local structure = ud and (ud.isBuilding or ud.isFactory or ((ud.speed or 1) == 0))
          local o = obs[id]
          if friendly then
            o.friendNow = o.friendNow + 1
            if structure then friendStruct[id] = (friendStruct[id] or 0) + 1 end
          else
            o.enemyNow = o.enemyNow + 1
            if structure then enemyStruct[id] = (enemyStruct[id] or 0) + 1 end
          end
        end
      end
    end
  end
  for _, id in ipairs(zoneOrder) do
    local o = obs[id]
    o.enemyRecent = math.max(o.enemyRecent, o.enemyNow)
    if o.enemyNow > o.enemyPeak then o.enemyPeak = o.enemyNow end
    local es, fs = enemyStruct[id] or 0, friendStruct[id] or 0
    if es > o.enemyStructPeak then o.enemyStructPeak = es end
    if fs > o.friendStructPeak then o.friendStructPeak = fs end
    o.friendStructNow, o.enemyStructNow = fs, es
    Spring.SetGameRulesParam("va_obs_" .. id, math.floor(o.eta * 1000 + 0.5) / 1000, { public = true })
    Spring.SetGameRulesParam("va_obs_enemy_" .. id, math.floor(o.enemyRecent + 0.5), { public = true })
  end
  Spring.SetGameRulesParam("va_obs_tick", tick, { public = true })
end

-- What the HUD could honestly believe about a zone from what it saw there.
local function belief(o)
  local ours, held, strength, threat
  local anyStruct = (o.friendStructPeak + o.enemyStructPeak) > 0
  if (o.friendStructNow or 0) > 0 and (o.enemyStructNow or 0) == 0 then
    ours = 1.0
  elseif (o.enemyStructNow or 0) > 0 then
    ours = 0.0
  elseif o.friendNow > o.enemyNow and o.friendNow > 0 then
    ours = 0.6
  else
    ours = 0.15
  end
  if anyStruct or o.enemyPeak > 0 or o.friendNow > 0 then
    held = 1.0
  else
    -- fully seen and empty is a real finding; a glance at nothing is not
    held = (o.lastShare >= 0.6) and 0.1 or 0.4
  end
  strength = clamp01(o.enemyStructPeak / 8 + o.enemyPeak / 16)
  threat = clamp01(o.enemyRecent / 10)
  return ours, held, strength, threat
end

function GG.VA_ObservedZonesJson()
  if not ready then return 'null' end
  local parts = {}
  for _, id in ipairs(zoneOrder) do
    local o = obs[id]
    if o.eta > 0.005 then
      parts[#parts + 1] = jstr(id) .. ':' .. jnum(o.eta, 3)
    end
  end
  return '{' .. table.concat(parts, ',') .. '}'
end

function GG.VA_BeliefExportJson()
  if not ready then return 'null' end
  local parts = {}
  for _, id in ipairs(zoneOrder) do
    local o = obs[id]
    if o.seenAny and o.eta > 0.005 then
      local ours, held, strength, threat = belief(o)
      parts[#parts + 1] = jstr(id) .. ':{"ours":' .. jnum(ours, 3) .. ',"held":' .. jnum(held, 3)
        .. ',"strength":' .. jnum(strength, 3) .. ',"threat":' .. jnum(threat, 3)
        .. ',"enemyPeak":' .. jnum(o.enemyPeak, 0) .. ',"enemyStructPeak":' .. jnum(o.enemyStructPeak, 0) .. '}'
    end
  end
  return '{' .. table.concat(parts, ',') .. '}'
end

function gadget:Initialize()
  ready = build()
end

function gadget:GameStart()
  resolvePlayerTeam()
  if not ready then ready = build() end
end

function gadget:GameFrame(frame)
  if not ready then return end
  if frame % SAMPLE_EVERY == 7 then
    local ok, err = pcall(sample, frame)
    if not ok then Spring.Echo("VA_OBS_ERR " .. tostring(err)) end
  end
end

function gadget:Shutdown()
  GG.VA_ObservedZonesJson = nil
  GG.VA_BeliefExportJson = nil
end
