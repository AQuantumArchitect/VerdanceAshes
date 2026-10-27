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

-- All That Simmers is a classic game of BAR: Armada, Null Mercs and the company each start with
-- one commander (mission.kings, from verdance.world.theaters). A king falls when its team has no
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

function gadget:Initialize()
  local ok, mission = pcall(VFS.Include, "singleplayer/verdance_ashes/generated/va_current.lua")
  if not ok or type(mission) ~= "table" or type(mission.kings) ~= "table" or #mission.kings == 0 then
    gadgetHandler:RemoveGadget(self)
    return
  end
  playerTeamID = tonumber(mission.balance and mission.balance.playerTeamID) or 0
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

function gadget:UnitDestroyed(unitID, unitDefID, unitTeam, attackerID, attackerDefID, attackerTeam)
  if kings[unitTeam] and isCommander(unitDefID) and attackerTeam and attackerTeam ~= unitTeam then
    local by = kings[attackerTeam]
    lastKiller[unitTeam] = by and by.faction or "other"
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
