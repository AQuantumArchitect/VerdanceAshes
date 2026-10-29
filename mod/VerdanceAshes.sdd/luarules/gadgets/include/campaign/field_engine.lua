-- campaign/field_engine.lua: field effects v2 (self + conditional auras), ticked once a second.
-- Part of game_verdance_campaign.lua, loaded into that gadget's environment.
-- Provides: fieldEngineOnUnitDestroyed, tickFieldEngine
-- Provides: fieldEngineOnUnitDestroyed, tickFieldEngine
-- Uses: hero_spawn, heroes, mentors, state

FieldEngine = nil
do
  local ok, mod = pcall(VFS.Include, "luarules/gadgets/include/va_field_engine.lua")
  if ok and type(mod) == "table" and mod.FX then
    FieldEngine = mod
    FieldEngine.Tags = HeroTags
    -- The engine owns the stats now: the spawn-time path only names the effect.
    if HeroTags then HeroTags.engineOwnsStats = true end
  else
    Spring.Echo("VA_FIELD_ENGINE_OFF err=" .. tostring(mod))
  end
end

local fieldEngineFailed = false

local function fieldXpOf(heroId, rec)
  local xp = tonumber(rec and rec.peakXp) or 0
  local bank = packMentors and packMentors[heroId] and tonumber(packMentors[heroId].bankXp) or 0
  local live = (rec and rec.unitID and Spring.GetUnitExperience and Spring.GetUnitExperience(rec.unitID)) or 0
  return math.max(xp, bank, tonumber(live) or 0)
end

function tickFieldEngine(frame)
  if not FieldEngine or fieldEngineFailed then return end
  local every = FieldEngine.FX.RULES.tickFrames or 30
  if frame < 45 or frame % every ~= 0 then return end
  local ok, res = pcall(FieldEngine.tick, {
    teamID = playerTeamID,
    heroes = heroes,
    mapId = zoneMap and zoneMap.mapId or nil,
    dt = every / 30,
    xpOf = fieldXpOf,
  })
  if not ok then
    fieldEngineFailed = true
    Spring.Echo("VA_FIELD_ENGINE_FAIL err=" .. tostring(res))
    return
  end
  if res and frame % (every * 30) == 0 then
    local on = {}
    for _, r in ipairs(res.report or {}) do
      on[#on + 1] = r.hero .. (r.selfOn and "+" or "-") .. string.format("%.2f", r.terrain or 1)
    end
    Spring.Echo(string.format("VA_FIELD_TICK units=%d heroes=%d changed=%d metal=%.2f energy=%.2f %s",
      res.units or 0, res.heroes or 0, res.changed or 0, res.metal or 0, res.energy or 0, table.concat(on, " ")))
  end
end

function fieldEngineOnUnitDestroyed(unitID)
  if FieldEngine then FieldEngine.forget(unitID) end
end
