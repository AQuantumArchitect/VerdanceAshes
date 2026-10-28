-- Run with Lua 5.4 from the workspace root. Exercises the autopilot's orders, not simulated wins:
-- the rescue squad on a hero's wreck, orders BARb cannot undo, the departure to the real pad, and
-- leaving both ways (directly without a HUD; through the HUD, with its fallback, when it is there).
local GADGET = "mod/VerdanceAshes.sdd/luarules/gadgets/game_verdance_autopilot.lua"
local mission = { missionId = "test", objective = { targetZoneId = "wound" } }
local rules, positions, orders, extracted, registered, threats

local function reset()
  rules = { va_pad_x = 0, va_pad_z = 0, va_pad_r = 100 }
  positions = { [1] = { 150, 0 }, [2] = { 0, 0 } }
  orders, extracted, registered, threats = {}, false, false, {}
  gadget = {}
  dofile(GADGET)
  gadget:Initialize()
end

gadgetHandler = {
  IsSyncedCode = function() return true end,
  RegisterAllowCommand = function(_, id) registered = id end,
}
CMD = { ANY = -1, FIGHT = 16, MOVE = 10, RESURRECT = 125 }
Game = { maxUnits = 10000, mapSizeX = 8192, mapSizeZ = 8192 }
UnitDefs = {
  [1] = { speed = 50, canAttack = true },
  [2] = { speed = 50, isBuilder = true, canResurrect = true },
  [3] = { weapons = { 1 } },
}
GG = {
  VA_ExfilCmd = function(cmd) assert(cmd == "extract:home"); extracted = true end,
  VA_ZoneAnchor = function() return 999, 999 end,
}
VFS = { Include = function(path)
  if path:find("va_active") then return true end
  return mission
end }
Spring = {
  GetModOptions = function() return { va_autopilot = "1", va_autopilot_minutes = "1", va_autopilot_settle = "1" } end,
  Echo = function() end,
  GetGameRulesParam = function(k) return rules[k] end,
  SetGameRulesParam = function(k, v) rules[k] = v end,
  GetAllFeatures = function() return { 9 } end,
  ValidFeatureID = function(f) return f == 9 end,
  GetFeatureRulesParam = function(_, k) if k == "va_hero_wreck" then return "pilot" end end,
  GetFeaturePosition = function() return 200, 0, 200 end,
  GetUnitsInCylinder = function() return threats end,
  GetUnitTeam = function() return 1 end,
  GetGaiaTeamID = function() return 9 end,
  GetUnitIsDead = function() return false end,
  GetTeamInfo = function(team) return 0, 0, 0, 0, 0, team end,
  GetTeamUnits = function() return { 1, 2 } end,
  GetUnitDefID = function(uid) return uid end,
  GetUnitRulesParam = function() return 0 end,
  GetGroundHeight = function() return 0 end,
  GetUnitPosition = function(uid) return positions[uid][1], 0, positions[uid][2] end,
  GetUnitCommands = function() return {} end,
  GetAllUnits = function() return { 1, 2 } end,
  GiveOrderToUnitArray = function(units, cmd, params)
    for _, uid in ipairs(units) do assert(gadget:AllowCommand(uid)) end
    orders[#orders + 1] = { cmd = cmd, params = params }
  end,
}

-- 1. No HUD (the Windows headless rig): the rescue, then straight out once everyone is aboard.
reset()
assert(registered == CMD.ANY)
gadget:GameFrame(311)
local function find(cmd) for _, o in ipairs(orders) do if o.cmd == cmd then return o end end end
assert(find(CMD.FIGHT) and find(CMD.FIGHT).params[1] == 200, "the squad must go to the actual wreck")
assert(find(CMD.RESURRECT) and find(CMD.RESURRECT).params[1] == 10009, "the rez bots raise the wreck")
assert(not gadget:AllowCommand(2), "BARb must not overwrite the rescue order")
assert(gadget:AllowCommand(3), "units the rig never ordered stay BARb's")
threats = { 3 }
gadget:GameFrame(911)
assert(not gadget:AllowCommand(2), "incoming threats must not release an active rescue order")
gadget:GameFrame(1811)
assert(orders[#orders].cmd == CMD.MOVE, "the clock must regroup before extracting")
assert(not extracted)
gadget:GameFrame(1841)
assert(not extracted, "150 is outside the real pad radius 100")
positions[1] = { 50, 0 }
gadget:GameFrame(1871)
assert(extracted, "the company on the pad leaves directly when there is no HUD")
assert(rules.va_autopilot_leave == nil, "no HUD: nothing to tell it")

-- 2. A HUD (the rig player widget said VA_RIG:hud): leave is said, the HUD gets its turn.
reset()
assert(gadget:RecvLuaMsg("VA_RIG:hud"))
positions[1] = { 50, 0 }
gadget:GameFrame(1811)
gadget:GameFrame(1841)
assert(rules.va_autopilot_leave == "clock", "with a HUD the autopilot says leave: " .. tostring(rules.va_autopilot_leave))
assert(not extracted, "...and waits for the HUD")
gadget:GameFrame(1841 + 300)
assert(not extracted, "still the HUD's turn")
gadget:GameFrame(1841 + 600)
assert(extracted, "a silent HUD: the autopilot extracts by itself")

print("ok: rescue squad, protected orders, departure to the real pad radius, leaving with and without a HUD")
