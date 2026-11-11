-- Run with Lua 5.4 from the workspace root. A build refused for want of Tenebrium says so once per
-- builder and unit type every 30 seconds, not every frame: the engine asks AllowUnitCreation again
-- each frame a factory keeps the build at the front of its queue, and on Luke's PC (2026-11-03) the
-- every-frame line filled one finale's log with 1.6 million copies until LuaUI ran out of memory.
local lines, frame = {}, 0
Spring = {
  Echo = function(s) lines[#lines + 1] = s end,
  GetGameFrame = function() return frame end,
}
UnitDefs = { [7] = { name = "legck" } }
VFS = { Include = function()
  return { costOf = function(def) return def == 7 and 1 or 0 end, BP_PER_TNB = 150 }
end }
local attach = dofile("mod/VerdanceAshes.sdd/luarules/gadgets/include/va_tenebrium_handlers.lua")
local tenebLoot = { bank = 0, enabled = true, blockedSaid = {} }
attach(tenebLoot, {
  jnum = tostring, jstr = tostring, teamFaction = {}, SendToUnsynced = function() end,
  playerTeamID = function() return 0 end, playerAllyTeamID = function() return 0 end,
  mission = function() return {} end, publishRules = function() end,
})

for f = 1, 899 do
  frame = f
  assert(tenebLoot.allowCreate(7, 0, 42) == false, "no Tenebrium, no constructor")
end
assert(#lines == 1, "one line for 899 refused frames, got " .. #lines)
assert(lines[1]:find("unit=legck", 1, true), lines[1])
frame = 901
tenebLoot.allowCreate(7, 0, 42)
assert(#lines == 2 and lines[2]:find("tries=899", 1, true), "thirty seconds on, it says again with the count: " .. tostring(lines[2]))
tenebLoot.allowCreate(7, 0, 43)
assert(#lines == 3, "another builder says so for itself")
assert(tenebLoot.allowCreate(8, 0, 42) == true, "a build with no Tenebrium cost goes ahead")
tenebLoot.bank = 1
assert(tenebLoot.allowCreate(7, 0, 42) == true, "with the Tenebrium it goes ahead")
print("ok: a refused build says so once per builder and unit type every 30 seconds")

-- The kings' showdown seeds tenebrium.gate = false: a straight game of BAR, every build goes ahead.
local free = { bank = 0, enabled = true, blockedSaid = {}, publish = function() end }
attach(free, {
  jnum = tostring, jstr = tostring, teamFaction = {}, SendToUnsynced = function() end,
  playerTeamID = function() return 0 end, playerAllyTeamID = function() return 0 end,
  mission = function() return { tenebrium = { playerBank = 0, gate = false } } end, publishRules = function() end,
})
Spring.GetGameRulesParam = function() return nil end
pcall(free.initFromMission)
assert(free.enabled == false, "gate = false turns the gate off")
assert(free.allowCreate(7, 0, 42) == true, "with no gate a constructor goes ahead on an empty bank")
print("ok: the showdown's seed turns the Tenebrium gate off")

-- Exfil gives back what was paid, not what a kit unit was stamped with (2026-11-11): the mission's
-- own constructor carries a stake only to mark the shard it leaves if it dies. Refunding that stamp
-- minted a Tenebrium per surviving kit builder per sortie.
local params = {}
Spring.SetUnitRulesParam = function(u, k, v) params[u] = params[u] or {}; params[u][k] = v end
Spring.GetUnitRulesParam = function(u, k) return params[u] and params[u][k] end
Spring.GetTeamUnits = function() return { 101, 102, 103 } end
UnitDefs[7].name = "legck"
local stake = { bank = 3, enabled = true, blockedSaid = {}, events = {}, byUnit = {}, paid = {} }
attach(stake, {
  jnum = tostring, jstr = tostring, teamFaction = {}, SendToUnsynced = function() end,
  playerTeamID = function() return 0 end, playerAllyTeamID = function() return 0 end,
  mission = function() return {} end, publishRules = function() end,
})
stake.onUnitCreated(101, 7, 0, nil)        -- the muster's kit constructor: no builder, stamped
assert(stake.bank == 3, "a kit unit is not charged: bank " .. stake.bank)
assert(params[101].va_tenebrium_invested == 1, "but it carries its stake, for the shard")
stake.onUnitCreated(102, 7, 0, 101)        -- built by it in the field: the bank pays
assert(stake.bank == 2, "a field build is charged: bank " .. stake.bank)
stake.onUnitCreated(103, 7, 0, nil)        -- the broker's delivery, paid at the hub
params[103].va_package_tag = "armada_constructor"
local back, n = stake.refundLivingStakesOnExfil(0)
assert(back == 2 and n == 2, "the field build and the delivery come back, the kit stamp does not: " .. back .. "/" .. n)
assert(stake.bank == 4, "bank after exfil " .. stake.bank)
assert(params[101].va_tenebrium_invested == 0, "every stake is cleared at exfil")
print("ok: exfil refunds what the bank or the broker paid, never a kit unit's stamp")

-- An AI's builder does not sit on a refused build (2026-11-11: BARb's plant asked for a constructor
-- 8,000 times every 30 s and printed no army). The refused build comes off its queue the next frame:
-- one from a factory's queue, every order to build it from a mobile builder. A player's queue is theirs.
local given = {}
CMD = CMD or {}
CMD.REMOVE = 2
Spring.GiveOrderToUnit = function(u, cmd, params, opts) given[#given + 1] = { u = u, cmd = cmd, params = params, opts = opts } end
Spring.ValidUnitID = function() return true end
Spring.GetUnitIsDead = function() return false end
Spring.GetUnitDefID = function(u) return u == 500 and 50 or 51 end
UnitDefs[50] = { name = "legvp", isFactory = true }
UnitDefs[51] = { name = "legck" }
local aiTeam = { [0] = true, [3] = false }
Spring.GetTeamInfo = function(team) return team, 0, false, aiTeam[team] end
local ai = { bank = 0, enabled = true, blockedSaid = {}, publish = function() end }
local playerIsAi = true
attach(ai, {
  jnum = tostring, jstr = tostring, teamFaction = {}, SendToUnsynced = function() end,
  playerTeamID = function() return playerIsAi and 0 or 3 end, playerAllyTeamID = function() return 0 end,
  mission = function() return {} end, publishRules = function() end,
})
assert(ai.allowCreate(7, 0, 500) == false and ai.allowCreate(7, 0, 600) == false)
ai.tickUnqueue()
table.sort(given, function(a, b) return a.u < b.u end)
assert(#given == 2, "two refused builds, two orders: " .. #given)
assert(given[1].u == 500 and given[1].cmd == -7 and given[1].opts[1] == "right", "the factory drops one from its queue")
assert(given[2].u == 600 and given[2].cmd == CMD.REMOVE and given[2].params[1] == -7 and given[2].opts[1] == "alt",
  "the constructor drops its orders to build it")
ai.tickUnqueue()
assert(#given == 2, "and only once")
given = {}
playerIsAi = false
assert(ai.allowCreate(7, 3, 500) == false)
ai.tickUnqueue()
assert(#given == 0, "a player's queue is left alone")
print("ok: an AI's refused build comes off its queue; a player's stays")
