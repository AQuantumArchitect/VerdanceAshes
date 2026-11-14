-- The base's footprint keeps a mentor's mint (playtest 2026-11-13: "my build turrets are gone").
-- Loads campaign/result_company.lua with a stubbed Spring and walks playerUnitFacts over a nano
-- turret Solarium minted, a nano turret of Solarium's own pack, a hero body and a plain build.
local defs = {
  [1] = { name = "armnanotc", speed = 0, isBuilding = false, buildSpeed = 200, customParams = {} },
  [2] = { name = "armadvsol", speed = 0, isBuilding = true, customParams = {} },
  [3] = { name = "legnanotc", speed = 0, isBuilding = false, buildSpeed = 200, customParams = {} },
}
UnitDefs = defs
local units = {
  [101] = { def = 1, params = { va_pack_id = "solarium", va_pack_leader = "solarium", va_pack_role = "mate", va_mentor_mint = 1 } },
  [102] = { def = 1, params = { va_pack_id = "solarium", va_pack_role = "mate" } },     -- pack kit: travels
  [103] = { def = 2, params = { va_hero_id = "solarium" } },                            -- hero body: travels
  [104] = { def = 3, params = {} },                                                     -- plain build
}
Spring = {
  GetTeamUnits = function() return { 101, 102, 103, 104 } end,
  ValidUnitID = function(u) return units[u] ~= nil end,
  GetUnitIsDead = function() return false end,
  GetUnitDefID = function(u) return units[u].def end,
  GetUnitPosition = function(u) return 100 * u, 0, 50 * u end,
  GetUnitHealth = function() return 100, 100 end,
  GetUnitRulesParam = function(u, k) return units[u].params[k] end,
  GetUnitBuildFacing = function() return 0 end,
  GetUnitExperience = function() return 0 end,
  Echo = function() end,
}
Game = { mapSizeX = 8192, mapSizeZ = 8192 }
playerTeamID = 0
mission = { deploymentZoneId = "TRJ_NW_GATE", deploymentMapId = "the_rock_jungle" }
function jstr(s) return '"' .. tostring(s) .. '"' end
function jnum(v) return tostring(v) end
function normalizedToElmos(v, s) return (tonumber(v) or 0) * s end
dofile("mod/VerdanceAshes.sdd/luarules/gadgets/include/campaign/result_company.lua")
local facts = playerUnitFacts()
local text = table.concat(facts.footprint, ",")
local function count(name)
  local n = 0
  for _ in text:gmatch('"unitDefName":"' .. name .. '"') do n = n + 1 end
  return n
end
assert(count("armnanotc") == 1, "the minted nano turret stays with the base, the pack's travels: " .. text)
assert(count("armadvsol") == 0, "the hero body travels: " .. text)
assert(count("legnanotc") == 1, "a plain build stays: " .. text)
assert(text:find('"x":10100', 1, true), "it is the minted one (unit 101) that stays: " .. text)
print("ok   a mentor's minted nano turret stays in the footprint")
