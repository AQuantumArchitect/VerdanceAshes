-- Run with Lua 5.4 from the workspace root. The safety field (va_safety_field.lua): fire from what
-- the company knows, shared over its crowd; the unknown as danger; and a hero's choice of where to be.
local SF = dofile("mod/VerdanceAshes.sdd/luarules/gadgets/include/va_safety_field.lua")

Game = { mapSizeX = 8192, mapSizeZ = 8192 }
WeaponDefs = {
  [1] = { damages = { [0] = 100 }, reload = 1, range = 300 },                       -- a rifle
  [2] = { damages = { [0] = 300 }, reload = 1, range = 500 },                       -- a turret's gun
  [3] = { damages = { [0] = 900 }, reload = 1, range = 900, canAttackGround = false }, -- anti-air
  [4] = { damages = { [0] = 2000 }, reload = 10, range = 4000 },                    -- an LRPC
}
UnitDefs = {
  [1] = { name = "gun", speed = 50, health = 1000, metalCost = 100, sightDistance = 400, weapons = { { weaponDef = 1 } } },
  [2] = { name = "rez", speed = 50, health = 500, metalCost = 200, sightDistance = 400, canResurrect = true, buildSpeed = 100 },
  [3] = { name = "turret", speed = 0, health = 3000, metalCost = 300, sightDistance = 400, buildTime = 3000, weapons = { { weaponDef = 2 } } },
  [4] = { name = "aa", speed = 0, health = 1000, metalCost = 100, weapons = { { weaponDef = 3 } } },
  [5] = { name = "lrpc", speed = 0, health = 4000, metalCost = 4500, weapons = { { weaponDef = 4 } } },
  [6] = { name = "tank", speed = 60, health = 2000, metalCost = 400, buildTime = 4000, weapons = { { weaponDef = 1 } } },
}
UnitDefNames = {}
for id, ud in pairs(UnitDefs) do ud.id = id; UnitDefNames[ud.name] = ud end

local function near(a, b, tol) return math.abs(a - b) <= tol end

-- 1. Profiles come from the defs.
do
  local g = SF.profile(1)
  assert(g.dps == 100 and g.range == 300 and g.hp == 1000 and g.cost == 100, "the rifle's profile")
  assert(SF.profile(4).dps == 0, "anti-air does not threaten a walking hero")
  assert(SF.profile(2).rez == 100, "a rez bot raises at its build speed")
  assert(near(SF.profile(1).fight, math.sqrt(100 * 1000), 1e-9), "fighting value is (dps x hp)^1/2")
  assert(near(SF.Phi(0), 0.5, 1e-7) and near(SF.Phi(1.96), 0.975, 1e-4) and near(SF.Phi(-3.09), 0.001, 1e-4), "the normal CDF")
end

-- A world: team 0 is the company (ally 0), team 1 the enemy (ally 1), team 9 gaia.
local W
local function world()
  W = { units = {}, team = {}, hp = {}, hero = {}, los = {}, seen = function() return false end, features = {} }
  return {
    GetGaiaTeamID = function() return 9 end,
    GetAllyTeamList = function() return { 0, 1 } end,
    GetTeamList = function(at) return at == 0 and { 0 } or { 1 } end,
    GetTeamUnits = function(t)
      local out = {}
      for u, tm in pairs(W.team) do if tm == t then out[#out + 1] = u end end
      table.sort(out)
      return out
    end,
    GetUnitPosition = function(u) local p = W.units[u]; if p then return p.x, 0, p.z end end,
    GetUnitDefID = function(u) return W.units[u] and W.units[u].def end,
    GetUnitHealth = function(u) local p = W.units[u]; return W.hp[u] or UnitDefs[p.def].health, UnitDefs[p.def].health end,
    GetUnitRulesParam = function(u, k) if k == "va_hero_id" then return W.hero[u] end end,
    GetGroundHeight = function() return 0 end,
    IsPosInLos = function(x, _, z) return W.seen(x, z) end,
    GetUnitLosState = function(u) local p = W.units[u]; local s = W.los[u]; if s == nil then s = W.seen(p.x, p.z) end; return { los = s, radar = false } end,
    GetAllFeatures = function() local out = {}; for f in pairs(W.features) do out[#out + 1] = f end; return out end,
    GetFeatureResurrect = function(f) return W.features[f].def end,
    GetFeaturePosition = function(f) local w = W.features[f]; return w.x, 0, w.z end,
    GetFeatureRulesParam = function(f, k) if k == "va_hero_wreck" then return W.features[f].hero end end,
  }
end
local function add(u, team, def, x, z) W.units[u] = { def = def, x = x, z = z }; W.team[u] = team end

-- 2. Fire from a seen turret: all of it on a lone hero inside its reach, none outside; a crowd shares it.
do
  local api = world()
  W.seen = function() return true end
  add(1, 0, 2, 1000, 1000); W.hero[1] = "ketha"  -- the hero (a rez bot; heroes are not the crowd)
  add(50, 1, 3, 1000, 1200)                       -- an enemy turret 200 away (reach 500)
  local f = SF.new(0, api)
  f:refresh(30); f:refresh(60)                    -- a second refresh measures dt (1 s)
  assert(near(f.dt, 1, 1e-9))
  local inside = f:incoming(1000, 1000, 50)
  assert(near(inside, 300, 1), "a lone hero inside the turret's reach takes all of its fire: " .. inside)
  assert(f:incoming(1000, 1900, 50) < 1, "700 from a 500-reach turret: nothing")
  assert(f.rhoDps == 0, "the whole enemy is seen: nothing unknown")
  -- nine of the company's guns standing in its reach share the fire ten ways
  for i = 1, 9 do add(100 + i, 0, 1, 1000 + i * 10, 1000) end
  f:refresh(90)
  local shared = f:incoming(1000, 1000, 50)
  assert(near(shared, 30, 2), "a crowd of nine shares the turret's fire: " .. shared)
end

-- 3. Memory: a turret seen once stays where it was, sharp; a tank seen once blurs as it could walk.
do
  local api = world()
  W.seen = function(x) return x < 4096 end      -- the company sees the west half
  add(1, 0, 2, 1000, 1000); W.hero[1] = "ketha"
  add(50, 1, 3, 3000, 1000)                       -- a turret, seen
  add(51, 1, 6, 3500, 3000)                       -- a tank, seen
  local f = SF.new(0, api)
  f:refresh(30); f:refresh(60)
  W.los[50], W.los[51] = false, false             -- both out of sight now (their ground still seen? no:)
  W.seen = function(x) return x < 2000 end        -- the company pulled back west
  f:refresh(60 + 30 * 60)                         -- a minute later
  assert(f.mem[50] and f.mem[51], "both are remembered")
  local t0, t1 = f:incoming(3000, 1300, 0), f:incoming(3000, 1700, 0)
  assert(t0 > 290 and t1 < 10, "the turret's edge is as sharp as ever: " .. t0 .. " / " .. t1)
  local k0 = f:incoming(3500, 3000, 0)
  -- a minute at 60/s (and this refresh came a minute after the last, so the reaction blur is a minute
  -- too): sigma ~7200, its 300 reach covers (300/7200)^2/2 of that, ~0.09% of 100
  assert(k0 > 0.05 and k0 < 1, "the tank could be anywhere within a minute's walk: its fire is spread thin: " .. k0)
  assert(f:incoming(3500, 3000 + 60 * 60 * 0.9, 0) > 0.01, "...and reaches far past where it was")
  assert(SF.reach(0, 300, 3600) < 0.004 and SF.reach(0, 300, 30) > 0.99, "the blur's exact centre, both ways")
  -- its ground in sight again and nothing there: forgotten
  W.seen = function() return true end
  W.units[51].x = 7000; W.los[51] = false
  f:refresh(60 + 30 * 61)
  assert(not f.mem[51], "a remembered gun whose ground is seen empty is forgotten")
end

-- 4. The unknown is dangerous in proportion to the enemy not yet found.
do
  local api = world()
  W.seen = function(x) return x < 4096 end
  add(1, 0, 2, 1000, 4000); W.hero[1] = "ketha"
  add(60, 1, 3, 7000, 4000)                       -- a turret nobody has seen
  local f = SF.new(0, api)
  f:refresh(30); f:refresh(60)
  assert(f.unseenDps == 300, "the turret is unaccounted for")
  local west, border, east = f:incoming(1000, 4000, 50), f:incoming(4096, 4000, 50), f:incoming(6000, 4000, 50)
  assert(west < 1e-6, "deep in seen ground: no unknown danger: " .. west)
  assert(border > west and east > border, "more unseen ground in reach, more danger: " .. border .. " < " .. east)
  -- found: the unknown's share drops to zero and the turret stands where it is
  W.seen = function() return true end
  f:refresh(90)
  assert(f.unseenDps == 0 and f:incoming(6000, 4000, 50) < 1, "found: no unknown danger left away from it")
end

-- 5. A long gun is kept apart (an LRPC never makes every lookup scan the map) and still counts.
do
  local api = world()
  W.seen = function() return true end
  add(1, 0, 2, 1000, 1000); W.hero[1] = "ketha"
  add(70, 1, 5, 4000, 1000)                       -- an LRPC 3000 away (reach 4000)
  local f = SF.new(0, api)
  f:refresh(30); f:refresh(60)
  assert(#f.far == 1, "the LRPC is a long gun")
  assert(near(f:incoming(1000, 1000, 50), 200, 1), "and it reaches the hero (2000 per 10 s)")
end

-- 6. Ketha's choice: a wreck in the turret's reach, one in safe ground; then the turret falls.
do
  local api = world()
  W.seen = function() return true end
  add(1, 0, 2, 1000, 1000); W.hero[1] = "ketha"
  for i = 1, 6 do add(100 + i, 0, 1, 1200 + i * 20, 1000) end
  add(50, 1, 3, 3000, 1000)
  W.features[901] = { def = "tank", x = 3000, z = 1300 }   -- rich, under the turret
  W.features[902] = { def = "gun", x = 1000, z = 2000 }    -- poorer, in safe ground
  local f = SF.new(0, api)
  f:refresh(30); f:refresh(60)
  local h = { uid = 1, x = 1000, z = 1000, hp = 500, maxHp = 500, defID = 2, hid = "ketha" }
  local best = f:choose(h, 1000, 1000)
  assert(best.kind == "rez" and best.fid == 902, "she raises the safe wreck, not the one under the turret: " .. best.kind .. " " .. tostring(best.fid))
  -- the army breaks the turret
  W.units[50], W.team[50] = nil, nil
  f:refresh(90)
  best = f:choose(h, 1000, 1000)
  assert(best.kind == "rez" and best.fid == 901, "the turret gone, she goes in for the richer wreck: " .. tostring(best.fid))
end

-- 7. Ketha at the start of a drop: only the pad seen, a wreck out in the dark, the enemy not found.
do
  local api = world()
  W.seen = function(x, z) return x < 1500 and z < 1500 end
  add(1, 0, 2, 1000, 1000); W.hero[1] = "ketha"
  add(60, 1, 6, 6000, 6000)                       -- a tank somewhere out there
  add(61, 1, 6, 6500, 6000)
  W.features[903] = { def = "tank", x = 3000, z = 3000 }   -- (not on seen ground: unknown to her)
  W.features[904] = { def = "gun", x = 1400, z = 1400 }    -- at the edge of the seen ground
  local f = SF.new(0, api)
  f:refresh(30); f:refresh(60)
  local h = { uid = 1, x = 1000, z = 1000, hp = 500, maxHp = 500, defID = 2, hid = "ketha" }
  local best = f:choose(h, 1000, 1000)
  assert(best.fid ~= 903, "she does not walk into the dark for a wreck she has not seen")
end

-- 8. A fighter: whole, trading well with a weak gun, it keeps its orders; badly hurt, it takes refuge.
do
  local api = world()
  W.seen = function() return true end
  add(1, 0, 6, 1000, 1000); W.hero[1] = "vane"                -- a tank-hero (dps 100, hp 2000)
  add(50, 1, 1, 1250, 1000)                                   -- one enemy rifle in reach
  W.features = {}
  local f = SF.new(0, api)
  f:refresh(30); f:refresh(60)
  local h = { uid = 1, x = 1000, z = 1000, hp = 2000, maxHp = 2000, defID = 6, hid = "vane" }
  local best = f:choose(h, 0, 0)
  assert(best.kind == "stay", "whole, against one rifle: it keeps fighting (" .. best.kind .. ")")
  h.hp = 150
  best = f:choose(h, 0, 0)
  assert(best.kind == "refuge", "at 150 of 2000 health: out of reach (" .. best.kind .. ")")
  local d = math.sqrt((best.x - 1250) ^ 2 + (best.z - 1000) ^ 2)
  assert(d > 300, "the refuge is out of the rifle's reach: " .. d)
end

print("ok: profiles from defs, fire shared over the crowd, memory sharp for turrets and blurred for walkers, forgetting, the unknown as danger, long guns, Ketha's wrecks, the dark, a fighter's trade")
