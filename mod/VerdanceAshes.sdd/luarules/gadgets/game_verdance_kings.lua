if not VFS.Include("LuaRules/Configs/va_active.lua") then return false end -- plain BAR unless the hub launched this
local gadget = gadget

function gadget:GetInfo()
  return {
    name = "Verdance Kings",
    desc = "The kings' showdown: watches each king's commander and reports who falls, when and to whom",
    author = "Verdance",
    date = "2026-10-23",
    license = "GPL v2 or later",
    layer = 8,
    enabled = true,
  }
end

if not gadgetHandler:IsSyncedCode() then
  return
end

-- All That Simmers is a game of BAR in four corners: the company, Armada and Cortex each start with
-- one commander (mission.kings, from verdance.world.theaters), and a raptor den holds the fourth
-- corner (no king; the raptors fight everyone). A king falls when its team has no
-- commander left. This gadget reports facts only:
--
--   GG.VA_KingsJson() -> [{"faction":"armada","teamID":1,"fallen":true,"minute":12.4,"by":"ashwalkers"}, ...]
--   GameRulesParam "va_king_<faction>" = 1 standing, 0 fallen (public, for the HUD)
--   VA_KING_FALLS faction=<f> minute=<m> by=<f>   in the log
--
-- When every rival king has fallen and the company's stands, the sortie's objective is done
-- (GG.VA_ObjectiveComplete, the campaign gadget's own completion path). Who holds the throne is
-- Python's reading of these facts (verdance.belief.manifest), not this gadget's.

local CHECK_EVERY = 15                 -- frames

local kings = {}                       -- teamID -> { faction, label, seen, fallen, minute, by }
local order = {}
local lastKiller = {}                  -- teamID -> faction that last killed one of its commanders
local playerTeamID = 0
local done = false

local function jstr(s)
  s = tostring(s or "")
  s = s:gsub('\\', '\\\\'):gsub('"', '\\"'):gsub('\n', ' ')
  return '"' .. s .. '"'
end

local COM = VFS.Include("luarules/gadgets/include/va_commanders.lua")
local function isCommander(defID) return COM.isCommander(defID) end

local function commanders(teamID)
  local n = 0
  for _, uID in ipairs(Spring.GetTeamUnits(teamID) or {}) do
    if isCommander(Spring.GetUnitDefID(uID)) and not Spring.GetUnitIsDead(uID) then n = n + 1 end
  end
  return n
end

-- A king who starts under the sea is a king nobody can reach: the Southeast Shore seat stands in the
-- water (the Armada commander started at y -47 on the container rig, 2026-11-03), and through six
-- 90-minute rehearsals no army but torpedoes could touch it while the other two kings fell. In the
-- first frames every rival king standing in water walks inland, onto the nearest dry ground toward the
-- middle of the map that a bot could stand on, and on ground that stays dry a little further in (not a
-- sandbar on the map's edge). The company's own commander lands where the drop puts it.
local DRY = 10                          -- elmos above sea level
-- ...and above the tide still to come: the waterline rises during the match (game_verdance_campaign's
-- waterline sinks the world from mission.hydrology.level toward nextLevel). The first try put the
-- Armada king on ground 41 high, and the tide took it to -13 by minute 22.
local riseAhead = 0
local function tideStillToCome(mission)
  local hydro = type(mission) == "table" and mission.hydrology or nil
  local okz, zm = pcall(VFS.Include, "singleplayer/verdance_ashes/generated/zone_map_current.lua")
  local line = okz and type(zm) == "table" and zm.waterline or nil
  local elev = line and line.elevations
  if not hydro or type(elev) ~= "table" or #elev == 0 then return 0 end
  local levels = line.levels or {}
  local function at(level)
    local t = math.max(0, math.min(1, tonumber(level) or 0))
    for i = 1, #elev do
      local l = tonumber(levels[i]) or ((i - 1) / math.max(1, #elev - 1))
      if l >= t then
        if i == 1 then return tonumber(elev[1]) or 0 end
        local p = tonumber(levels[i - 1]) or 0
        local f = (l - p) > 0 and (t - p) / (l - p) or 0
        return elev[i - 1] + (elev[i] - elev[i - 1]) * f
      end
    end
    return tonumber(elev[#elev]) or 0
  end
  local now = tonumber(hydro.level) or 0
  local top = math.max(now, tonumber(hydro.nextLevel) or now)
  return math.max(0, at(top) - at(now))
end

local function dryGround(x, z)
  local DRY = DRY + riseAhead
  local walker = UnitDefNames["armpw"] or UnitDefNames["legcen"]
  local cx, cz = Game.mapSizeX / 2, Game.mapSizeZ / 2
  local inward = math.atan2(cz - z, cx - x)
  local function dry(px, pz)
    if px < 64 or pz < 64 or px > Game.mapSizeX - 64 or pz > Game.mapSizeZ - 64 then return false end
    return (Spring.GetGroundHeight(px, pz) or -1) >= DRY
  end
  local function ok(px, pz, a)
    if not (dry(px, pz) and dry(px + math.cos(a) * 256, pz + math.sin(a) * 256)) then return false end
    if walker and Spring.TestMoveOrder then
      local okm, can = pcall(Spring.TestMoveOrder, walker.id, px, Spring.GetGroundHeight(px, pz), pz)
      if okm and can == false then return false end
    end
    return true
  end
  for _, cone in ipairs({ 6, 12 }) do      -- within 90 degrees either side of the way inland, then anywhere
    for r = 64, 5000, 64 do
      for i = -cone, cone do
        local a = inward + i / 6 * (math.pi / 2)
        local px, pz = x + math.cos(a) * r, z + math.sin(a) * r
        if ok(px, pz, a) then return px, pz end
      end
    end
  end
  return nil
end

local ashoreChecked = {}                 -- unitID -> true: each king's commander is looked at once
local function kingsAshore()
  for _, tid in ipairs(order) do
    for _, uID in ipairs(tid ~= playerTeamID and Spring.GetTeamUnits(tid) or {}) do
      if not ashoreChecked[uID] and isCommander(Spring.GetUnitDefID(uID)) then
        ashoreChecked[uID] = true
        local x, _, z = Spring.GetUnitPosition(uID)
        if x and (Spring.GetGroundHeight(x, z) or 0) < DRY + riseAhead then
          local px, pz = dryGround(x, z)
          if px then
            Spring.SetUnitPosition(uID, px, pz)
            Spring.GiveOrderToUnit(uID, CMD.STOP, {}, 0)
            Spring.Echo("VA_KING_ASHORE faction=" .. kings[tid].faction .. " from=" .. math.floor(x) .. "," .. math.floor(z)
              .. " to=" .. math.floor(px) .. "," .. math.floor(pz) .. " tide_to_come=" .. math.floor(riseAhead))
          else
            Spring.Echo("VA_KING_ASHORE faction=" .. kings[tid].faction .. " no dry ground within 5000 of "
              .. math.floor(x) .. "," .. math.floor(z) .. " tide_to_come=" .. math.floor(riseAhead))
          end
        end
      end
    end
  end
end

function gadget:Initialize()
  local ok, mission = pcall(VFS.Include, "singleplayer/verdance_ashes/generated/va_current.lua")
  if not ok or type(mission) ~= "table" or type(mission.kings) ~= "table" or #mission.kings == 0 then
    gadgetHandler:RemoveGadget(self)
    return
  end
  playerTeamID = tonumber(mission.balance and mission.balance.playerTeamID) or 0
  riseAhead = tideStillToCome(mission)
  for _, k in ipairs(mission.kings) do
    local tid = tonumber(k.teamID)
    if tid then
      kings[tid] = { faction = tostring(k.faction or tid), label = tostring(k.label or k.faction or tid),
                     seen = false, fallen = false }
      order[#order + 1] = tid
      Spring.SetGameRulesParam("va_king_" .. kings[tid].faction, 1, { public = true })
    end
  end
  Spring.Echo("VA_KINGS " .. tostring(#order))
end

-- The rival kings still standing, for the autopilot rig (game_verdance_autopilot.lua): unitID -> teamID.
GG.VA_RivalKings = function()
  local out = {}
  for tid, k in pairs(kings) do
    if tid ~= playerTeamID and not k.fallen then
      for _, uID in ipairs(Spring.GetTeamUnits(tid) or {}) do
        if isCommander(Spring.GetUnitDefID(uID)) and not Spring.GetUnitIsDead(uID) then out[uID] = tid end
      end
    end
  end
  return out
end

function gadget:UnitDestroyed(unitID, unitDefID, unitTeam, attackerID, attackerDefID, attackerTeam)
  if kings[unitTeam] and isCommander(unitDefID) and attackerTeam and attackerTeam ~= unitTeam then
    local by = kings[attackerTeam]
    lastKiller[unitTeam] = by and by.faction or "other"
  end
  if kings[unitTeam] and isCommander(unitDefID) then
    -- what took the commander, and where: one Armada king fell at 1.2 minutes to "the company",
    -- whose army was nowhere near it (Luke's PC, 2026-11-03)
    local x, _, z = Spring.GetUnitPosition(unitID)
    local ad = attackerDefID and UnitDefs[attackerDefID]
    local ax, _, az
    if attackerID then ax, _, az = Spring.GetUnitPosition(attackerID) end
    Spring.Echo("VA_KING_COMMANDER_DOWN team=" .. tostring(unitTeam) .. " at=" .. math.floor(x or -1) .. "," .. math.floor(z or -1)
      .. " by_team=" .. tostring(attackerTeam) .. " by_unit=" .. tostring(ad and ad.name or attackerDefID)
      .. (ax and (" from=" .. math.floor(ax) .. "," .. math.floor(az)) or ""))
  end
end

local function fall(tid, frame)
  local k = kings[tid]
  k.fallen = true
  k.minute = math.floor(frame / 30 / 60 * 10 + 0.5) / 10
  k.by = lastKiller[tid] or "unknown"
  Spring.SetGameRulesParam("va_king_" .. k.faction, 0, { public = true })
  Spring.Echo("VA_KING_FALLS faction=" .. k.faction .. " minute=" .. tostring(k.minute) .. " by=" .. k.by)
end

function gadget:GameFrame(frame)
  -- each king as it appears: with StartPosType 3 BAR spawns the commanders a few frames after 1
  if frame <= 900 and (frame <= 5 or frame % CHECK_EVERY == 0) then kingsAshore() end
  if done or frame % CHECK_EVERY ~= 0 then return end
  for _, tid in ipairs(order) do
    local k = kings[tid]
    if not k.fallen then
      local n = commanders(tid)
      if n > 0 then k.seen = true
      elseif k.seen then fall(tid, frame) end
    end
  end
  local ours = kings[playerTeamID]
  if ours and ours.fallen then return end
  for _, tid in ipairs(order) do
    if tid ~= playerTeamID and not kings[tid].fallen then return end
  end
  done = true
  Spring.Echo("VA_KINGS_LAST_STANDING faction=" .. tostring(ours and ours.faction or "ashwalkers"))
  if GG and GG.VA_ObjectiveComplete then GG.VA_ObjectiveComplete("kings_fallen") end
end

function GG.VA_KingsJson()
  local parts = {}
  for _, tid in ipairs(order) do
    local k = kings[tid]
    parts[#parts + 1] = "{" .. table.concat({
      '"faction":' .. jstr(k.faction), '"label":' .. jstr(k.label), '"teamID":' .. tostring(tid),
      '"fallen":' .. tostring(k.fallen == true),
      '"minute":' .. (k.minute and tostring(k.minute) or "null"),
      '"by":' .. (k.by and jstr(k.by) or "null"),
    }, ",") .. "}"
  end
  return "[" .. table.concat(parts, ",") .. "]"
end
