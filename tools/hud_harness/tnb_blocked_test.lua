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
