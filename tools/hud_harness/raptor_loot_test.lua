-- Raptors drop nothing (Luke, 2026-11-13: "the raptor turrets should not drop tenebrium ... I don't
-- even think they should drop anything"). va_tnb_cost.dropOf is the shard a death leaves.
UnitDefs = {
  [1] = { name = "raptor_turret_basic_t2_v1", buildSpeed = 300, customParams = {} },
  [2] = { name = "raptor_hive", buildSpeed = 600, customParams = { subfolder = "other/raptors" } },
  [3] = { name = "va_wild_thing", buildSpeed = 300, customParams = { subfolder = "other/raptors" } },
  [4] = { name = "legnanotc", buildSpeed = 200, customParams = {} },
  [5] = { name = "legck", buildSpeed = 80, customParams = {} },
}
local M = dofile("mod/VerdanceAshes.sdd/luarules/gadgets/include/va_tnb_cost.lua")
assert(M.dropOf(1) == 0, "a raptor turret drops no Tenebrium")
assert(M.dropOf(2) == 0, "a hive drops no Tenebrium")
assert(M.dropOf(3) == 0, "anything in the raptor subfolder drops none")
assert(M.dropOf(4) == 1, "a nano turret still leaves its shard")
assert(M.dropOf(5) == 1, "a constructor still leaves its shard")
local src = io.open("mod/VerdanceAshes.sdd/luarules/gadgets/raptor_spawner_defense.lua"):read("a")
assert(src:find("if config.useEggs and config.vaRaptorEggs then", 1, true), "raptor deaths lay no eggs")
print("ok   raptors drop nothing")
