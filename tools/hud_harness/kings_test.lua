-- Run with Lua 5.4 from the workspace root. The kings' showdown gadget (game_verdance_kings.lua):
-- a rival king who starts in the sea walks inland, above the tide still to come, before the war
-- begins; the company's own commander is left where the drop puts it; a king falls when its team has
-- no commander left.
local GADGET = "mod/VerdanceAshes.sdd/luarules/gadgets/game_verdance_kings.lua"
local lines, rules, pos, moved = {}, {}, {}, {}
local mission = {
  balance = { playerTeamID = 0 },
  kings = { { teamID = 0, faction = "ashwalkers" }, { teamID = 1, faction = "armada" }, { teamID = 2, faction = "cortex" } },
  hydrology = { level = 0.25, nextLevel = 0.75 },
}
local zoneMap = { waterline = { levels = { 0, 0.25, 0.5, 0.75, 1 }, elevations = { 0, 25, 50, 80, 100 } } }

-- The ground: sea (-40) west of x = 3000, a shore strip 10..60 high from 3000 to 3500, high ground
-- (150) beyond it. The tide still to come is 80 - 25 = 55, so the king needs ground above 65.
local function ground(x, z)
  if x < 3000 then return -40 elseif x < 3500 then return 40 else return 150 end
end
local teamUnits = { [0] = { 10 }, [1] = { 11 }, [2] = { 12 } }
pos[10], pos[11], pos[12] = { 1000, 1000 }, { 2600, 4000 }, { 7000, 4000 }   -- ours in the sea too

gadgetHandler = { IsSyncedCode = function() return true end, RemoveGadget = function() error("removed") end }
gadget = {}
GG = {}
CMD = { STOP = 0 }
Game = { mapSizeX = 8192, mapSizeZ = 8192 }
UnitDefs = { [1] = { id = 1, name = "armcom", customParams = { iscommander = true } } }
UnitDefNames = { armpw = { id = 2 } }
VFS = { Include = function(path)
  if path:find("va_active") then return true end
  if path:find("va_commanders") then return dofile("mod/VerdanceAshes.sdd/luarules/gadgets/include/va_commanders.lua") end
  if path:find("zone_map_current") then return zoneMap end
  return mission
end }
Spring = {
  Echo = function(s) lines[#lines + 1] = s end,
  SetGameRulesParam = function(k, v) rules[k] = v end,
  GetTeamUnits = function(t) return teamUnits[t] or {} end,
  GetUnitDefID = function() return 1 end,
  GetUnitIsDead = function() return false end,
  GetUnitPosition = function(u) return pos[u][1], ground(pos[u][1], pos[u][2]), pos[u][2] end,
  GetGroundHeight = ground,
  TestMoveOrder = function() return true end,
  SetUnitPosition = function(u, x, z) pos[u] = { x, z }; moved[u] = true end,
  GiveOrderToUnit = function() end,
}
dofile(GADGET)
gadget:Initialize()
gadget:GameFrame(1)
assert(moved[11], "the Armada king in the sea walks ashore")
assert(ground(pos[11][1], pos[11][2]) > 65, "onto ground the tide still to come leaves dry, got " .. ground(pos[11][1], pos[11][2]))
assert(not moved[10], "the company's commander lands where the drop puts it")
assert(not moved[12], "a king on high ground stays")
local said = false
for _, l in ipairs(lines) do if l:find("VA_KING_ASHORE faction=armada", 1, true) then said = true end end
assert(said, "and the log says where it went")
-- the fall: Cortex's team has no commander left
gadget:GameFrame(15)
teamUnits[2] = {}
gadget:GameFrame(30)
assert(rules.va_king_cortex == 0, "a king falls when its team has no commander left")
print("ok: a king in the sea walks inland above the tide; the company is left to its drop; kings fall")
