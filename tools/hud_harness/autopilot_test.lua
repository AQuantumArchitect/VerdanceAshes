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
CMD = { ANY = -1, FIGHT = 16, MOVE = 10, RESURRECT = 125, REPAIR = 40, ATTACK = 20 }
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
  if path:find("va_commanders") then return dofile("mod/VerdanceAshes.sdd/luarules/gadgets/include/va_commanders.lua") end
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
    orders[#orders + 1] = { cmd = cmd, params = params, units = units }
  end,
}

local function find(cmd) for _, o in ipairs(orders) do if o.cmd == cmd then return o end end end
-- 0. The company's commander is never nudged into the fight (the king of the showdown, the suit).
do
  reset()
  UnitDefs[7] = { speed = 30, isBuilder = true, canAttack = true, name = "legcom", buildOptions = { 1 } }
  local was = Spring.GetTeamUnits
  Spring.GetTeamUnits = function() return { 1, 7 } end
  positions[7] = { 0, 0 }
  gadget:GameFrame(11)
  local fight = find(CMD.FIGHT)
  assert(fight, "an idle gun is nudged")
  for _, uid in ipairs(fight.units) do assert(uid ~= 7, "the commander is left to BARb") end
  Spring.GetTeamUnits = was
  UnitDefs[7] = nil
end

-- 1. No HUD (the Windows headless rig): the rescue, then straight out once everyone is aboard.
reset()
assert(registered == CMD.ANY)
gadget:GameFrame(311)
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

-- 3. A capture in its hold, the company short of presence: the guns go to the hold's centre and stay.
reset()
rules.va_capture_phase = "hold"; rules.va_hold_cx = 700; rules.va_hold_cz = 800
rules.va_claim_value = 140; rules.va_claim_need = 1501
gadget:GameFrame(611)
local hold = find(CMD.FIGHT)
assert(hold and hold.params[1] == 700 and hold.params[3] == 800, "the guns fight to the hold's centre")
assert(not gadget:AllowCommand(1), "BARb must not pull them off the hold")
assert(gadget:AllowCommand(2), "builders are not sent to hold")
reset()
rules.va_capture_phase = "hold"; rules.va_hold_cx = 700; rules.va_hold_cz = 800
rules.va_claim_value = 1800; rules.va_claim_need = 1501
gadget:GameFrame(611)
assert(gadget:AllowCommand(1), "enough presence there already: the guns stay BARb's")

-- 4. The Spire Gate (finale C): builders finish the frame, then build fusions around it, then the
--    heroes walk onto its pad one at a time.
local units, unitDef, heroOf, queues, built = {}, {}, {}, {}, {}
local function gateWorld()
  reset()
  UnitDefs[4] = { speed = 40, isBuilder = true, buildOptions = { 50 } }      -- a T2 constructor
  UnitDefs[5] = { speed = 40, isBuilder = true, buildOptions = { 51 } }      -- a T1 constructor: no fusion
  UnitDefNames = { legafus = { id = 50 } }
  units = { 1, 4, 5, 6 }
  unitDef = { [1] = 1, [4] = 4, [5] = 5, [6] = 1 }
  heroOf = { [1] = "halbard", [6] = "vane" }
  positions[4], positions[5], positions[6] = { 900, 900 }, { 900, 950 }, { 2000, 2000 }
  queues, built = {}, {}
  Spring.GetTeamUnits = function() return units end
  Spring.GetUnitDefID = function(uid) return unitDef[uid] end
  Spring.GetUnitRulesParam = function(uid, k) if k == "va_hero_id" then return heroOf[uid] end end
  Spring.GetUnitCommands = function(uid) return queues[uid] or {} end
  Spring.TestBuildOrder = function() return 2 end
  Spring.GetUnitHealth = function() return 1, 1, 0, 0, 1 end
  Spring.GiveOrderToUnit = function(uid, cmd, params) assert(gadget:AllowCommand(uid)); built[#built + 1] = { uid = uid, cmd = cmd, x = params[1] } end
  rules.va_gate_x, rules.va_gate_z, rules.va_gate_unit, rules.va_gate_pad_r = 1000, 1000, 77, 220
end
gateWorld()
rules.va_gate_state = "frame"
gadget:GameFrame(41)
local rep = find(CMD.REPAIR)
assert(rep and rep.params[1] == 77, "the builders finish the gate's frame")
assert(not gadget:AllowCommand(5), "BARb must not pull the gate crew off the frame")
assert(gadget:AllowCommand(4), "half the builders (the nearest to the gate) are its crew: the rest stay BARb's, for the economy")
-- the guns stand at the gate, not at the hive (objective targets on the far side of the map)
gateWorld()
rules.va_gate_state = "frame"
GG.VA_ObjectiveTargets = function() return { [90] = true } end
positions[90] = { 5000, 5000 }
UnitDefs[1].canAttack = true
gadget:GameFrame(611)
local guard = find(CMD.FIGHT)
assert(guard and math.abs(guard.params[1] - 1318) < 2 and math.abs(guard.params[3] - 1318) < 2,
  "in the Spire Jump the guns guard the gate, 450 off it toward the middle of the map (off its pad)")
-- before the gate gadget publishes the gate (frame 30), the siege must not take the army to the hive
local function nestWorld(jump)
  gateWorld()
  mission.jumpGate = jump
  rules.va_gate_state = nil
  units = {}
  for i = 100, 111 do units[#units + 1] = i; unitDef[i] = 1; positions[i] = { 900, 900 } end
  positions[90] = { 5000, 5000 }   -- the hive (an objective target)
  Spring.ValidUnitID = function() return true end
  gadget:GameFrame(11)
  mission.jumpGate = nil
  local f = find(CMD.FIGHT)
  return f and f.params[1] == 5000
end
assert(nestWorld(nil), "(without a gate the siege goes for the objective targets)")
assert(not nestWorld({ zoneId = "TRJ_NW_MUSTER" }), "the Spire Jump: no march on the nests in the first second")
GG.VA_ObjectiveTargets = nil
gateWorld()
rules.va_gate_state = "unpowered"; rules.va_gate_afus = 1; rules.va_gate_afus_need = 4
gadget:GameFrame(41)
assert(#built == 1 and built[1].uid == 4 and built[1].cmd == -50, "the T2 constructor builds a fusion near the gate")
assert(math.abs(built[1].x - 1000) <= 1600, "...near it")
queues[4] = { { id = -50 } }
built = {}
gadget:GameFrame(71)
assert(#built == 0, "a builder already on a fusion is left to it")
-- power (2026-11-03): the crew builds the strongest generator BAR lets it place near the gate, and
-- stops ordering once what stands and what is going up covers the need
gateWorld()
UnitDefs[60] = { speed = 0, energyMake = 300 }          -- a geothermal: no vent near the gate
UnitDefs[61] = { speed = 0, energyMake = 100 }          -- an advanced solar
UnitDefs[62] = { speed = 0, energyUpkeep = -20 }        -- a solar
UnitDefs[5] = { speed = 40, isBuilder = true, buildOptions = { 62, 60, 61 } }
Spring.TestBuildOrder = function(def) return def == 60 and 0 or 2 end
rules.va_gate_state = "unpowered"; rules.va_gate_power = 200; rules.va_gate_power_need = 1500
gadget:GameFrame(41)
assert(#built == 1 and built[1].uid == 5 and built[1].cmd == -61, "the gate crew builds the strongest generator it can place")
queues[5] = { { id = -61 } }
built = {}
rules.va_gate_power = 1600
gadget:GameFrame(71)
assert(#built == 0, "enough power standing: no more orders")
gateWorld()
rules.va_gate_state = "open"
gadget:GameFrame(41)
local moves = {}
for _, o in ipairs(orders) do if o.cmd == CMD.MOVE then moves[#moves + 1] = o end end
assert(moves[1] and moves[1].params[1] == 1000 and moves[1].params[3] == 1000, "the nearest hero walks onto the pad")
assert(moves[2] and moves[2].params[1] ~= 1000, "the others wait off the pad")

-- 5. Nobody can build an advanced fusion yet: the rig climbs the tech ladder, one rung per order.
local function ladderWorld(have)
  gateWorld()
  UnitDefs[10] = { isFactory = true, buildOptions = { 11 } }               -- a T1 lab
  UnitDefs[11] = { speed = 40, isBuilder = true, buildOptions = { 12 } }   -- a T1 constructor
  UnitDefs[12] = { isFactory = true, buildOptions = { 13 } }               -- an advanced lab
  UnitDefs[13] = { speed = 40, isBuilder = true, buildOptions = { 50 } }   -- an advanced constructor
  UnitDefs[4], UnitDefs[5] = nil, nil
  units, unitDef = {}, {}
  for uid, def in pairs(have) do units[#units + 1] = uid; unitDef[uid] = def; positions[uid] = { 900, 900 } end
  Spring.GetUnitHealth = function() return 1, 1, 0, 0, 1 end
  rules.va_gate_state = "unpowered"; rules.va_gate_afus = 0; rules.va_gate_afus_need = 4
  rules.va_tenebrium_bank = 5
end
local function ordered(uid, cmd) for _, b in ipairs(built) do if b.uid == uid and b.cmd == cmd then return true end end return false end
ladderWorld({ [20] = 10 })
gadget:GameFrame(41)
assert(ordered(20, -11), "the T1 lab makes a constructor")
ladderWorld({ [20] = 10, [21] = 11 })
gadget:GameFrame(41)
assert(ordered(21, -12), "the constructor builds an advanced lab by the gate")
assert(ordered(20, -11), "and with fewer than four builders the lab makes more")
ladderWorld({ [20] = 10, [21] = 11 })
rules.va_tenebrium_bank = 0
gadget:GameFrame(41)
assert(not ordered(20, -11), "no Tenebrium, no constructor queued (the factory would ask every frame)")
ladderWorld({ [20] = 10, [21] = 11, [22] = 12 })
gadget:GameFrame(41)
local made = false
for _, b in ipairs(built) do if b.uid == 22 and b.cmd == -13 then made = true end end
assert(made, "the advanced lab makes a constructor that can build the fusion")
ladderWorld({ [23] = 13 })
gadget:GameFrame(41)
assert(ordered(23, -50), "and that one builds the fusion")
for _, id in ipairs({ 10, 11, 12, 13 }) do UnitDefs[id] = nil end

-- 6. Targets to break (the Overthrow): with enough guns, they all fight to the nearest target.
reset()
local guns = {}
for i = 100, 111 do guns[#guns + 1] = i; positions[i] = { 0, 0 } end
Spring.GetTeamUnits = function() return guns end
Spring.GetUnitDefID = function() return 1 end
Spring.ValidUnitID = function() return true end
positions[900], positions[901] = { 5000, 5000 }, { 800, 600 }
GG.VA_ObjectiveTargets = function() return { [900] = "keep", [901] = "keep" } end
gadget:GameFrame(611)
local s = find(CMD.FIGHT)
assert(s and s.params[1] == 800 and s.params[3] == 600, "the guns go for the nearest target")
assert(not gadget:AllowCommand(100), "and BARb leaves them on it")
reset()
guns = { 100, 101 }
Spring.GetTeamUnits = function() return guns end
Spring.GetUnitDefID = function() return 1 end
gadget:GameFrame(611)
assert(gadget:AllowCommand(100), "too few guns: no siege yet")
GG.VA_ObjectiveTargets = nil
-- the kings' showdown is BARb's war: the rig goes only for the last king, with forty guns, and
-- attacks the commander itself once it can see it
Spring.IsUnitInLos = function() return true end
reset()
guns = {}
for i = 100, 139 do guns[#guns + 1] = i; positions[i] = { 0, 0 } end
Spring.GetTeamUnits = function() return guns end
Spring.GetUnitDefID = function() return 1 end
Spring.ValidUnitID = function() return true end
positions[950], positions[951] = { 3000, 100 }, { 100, 3000 }
GG.VA_RivalKings = function() return { [950] = 1, [951] = 2 } end
gadget:GameFrame(611)
assert(not find(CMD.ATTACK) and gadget:AllowCommand(100), "two kings standing: the rig leaves the war to BARb")
Spring.GetGameFrame = function() return 31 * 60 * 30 end   -- half an hour on, two kings still stand
gadget:GameFrame(611)
local near = find(CMD.ATTACK)
assert(near and (near.params[1] == 950 or near.params[1] == 951), "after half an hour the rig goes for the nearest king")
reset()
local few = {}
for i = 100, 124 do few[#few + 1] = i; positions[i] = { 0, 0 } end
Spring.GetTeamUnits = function() return few end
Spring.GetUnitDefID = function() return 1 end
Spring.ValidUnitID = function() return true end
positions[950], positions[951] = { 3000, 100 }, { 100, 3000 }
Spring.GetGameFrame = function() return 31 * 60 * 30 end
gadget:GameFrame(611)
assert(not find(CMD.ATTACK), "twenty-five guns at half an hour: not yet")
Spring.GetGameFrame = function() return 46 * 60 * 30 end
gadget:GameFrame(1211)
assert(find(CMD.ATTACK), "after 45 minutes the army there is goes")
Spring.GetGameFrame = nil
reset()
for i = 100, 139 do positions[i] = { 0, 0 } end
Spring.GetTeamUnits = function() return guns end
Spring.GetUnitDefID = function() return 1 end
Spring.ValidUnitID = function() return true end
positions[950], positions[951] = { 3000, 100 }, { 100, 3000 }
GG.VA_RivalKings = function() return { [951] = 2 } end
gadget:GameFrame(1211)
local k = find(CMD.ATTACK)
assert(k and k.params[1] == 951, "the last king: the guns attack the commander itself")
assert(not gadget:AllowCommand(100), "and BARb leaves them on it")
Spring.IsUnitInLos = function() return false end
orders = {}
gadget:GameFrame(611)
local walk = find(CMD.FIGHT)
assert(not find(CMD.ATTACK) and walk and walk.params[1] == 100 and walk.params[3] == 3000,
  "a king out of sight: the guns fight their way to where it stands")
Spring.IsUnitInLos = function() return true end
-- too few guns left: the siege lets go of them
guns = { 100, 101 }
gadget:GameFrame(11)   -- (the harness clock is one minute: frame 1800 would be the departure)
assert(gadget:AllowCommand(100), "a siege too thin to break anything goes back to BARb")
GG.VA_RivalKings = nil

print("ok: rescue squad, protected orders, departure to the real pad radius, leaving with and without a HUD, holding a capture, the Spire Gate and its tech ladder, the siege")
