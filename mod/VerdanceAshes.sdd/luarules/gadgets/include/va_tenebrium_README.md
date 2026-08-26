# va_tenebrium module split (Phase 6)

`tenebLoot.*` method bodies live in `va_tenebrium_handlers.lua` (Lua 5.1
200-local ceiling — methods on one table; physical file split via VFS.Include).

**Split layout:**
1. `game_verdance_campaign.lua` keeps `local tenebLoot = { ... }` state + all call sites.
2. After helpers `jnum`/`jstr` and locals `playerTeamID`/`playerAllyTeamID`/`mission`/`teamFaction` exist, parent attaches methods:
   ```lua
   local attach = VFS.Include("luarules/gadgets/include/va_tenebrium_handlers.lua")
   attach(tenebLoot, {
     jnum = jnum,
     jstr = jstr,
     teamFaction = teamFaction,
     SendToUnsynced = SendToUnsynced,
     playerTeamID = function() return playerTeamID end,
     playerAllyTeamID = function() return playerAllyTeamID end,
     mission = function() return mission end,
   })
   ```
3. Include returns `function(tenebLoot, api)` and assigns `tenebLoot.publish`, `.eventsJson`, `.costOf`, `.isDecoy`, `.initFromMission`, `.addBank`, `.stampUnit`, `.tagFeature`, `.spawnShard`, `.posKey`, `.onDead`, `.onFeatureCreated`, `.onFeatureDestroyed`, `.tickPending`, `.tryLoot`, `.teamIsArmada`, `.allowCreate`, `.onUnitCreated`.

**Why api getters:** VFS.Include cannot close over parent chunk locals. Getters keep reassigned `mission` / `playerTeamID` / `playerAllyTeamID` live at call time (behavior-identical to the pre-split upvalues).

**Smoke:** expect `VA_TENEBRIUM_HANDLERS_ATTACHED` in infolog after LuaRules loads the campaign gadget.
