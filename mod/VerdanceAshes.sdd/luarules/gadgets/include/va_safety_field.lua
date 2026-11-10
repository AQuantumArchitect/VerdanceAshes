-- va_safety_field.lua: where it is safe for a named hero to stand, reasoned from geometry.
--
-- Owner call 2026-11-09: no leashes and no magic numbers. Every quantity here comes from the units'
-- own definitions (weapon damage, reload, range; health; speed; cost; build and rez speed), from where
-- things stand, and from what the company has seen. A hero weighs each place it could go by the
-- chance it lives through getting there and staying, times what it keeps and gains there, and goes to
-- the best. Ketha (a rez hero) keeps out of harm until the army has made a place safe, then goes in
-- and raises what fell there.
--
-- The model, in four parts:
--   fire      an enemy gun with range R covers the ground within R of it. Seen now, its edge is as
--             sharp as the time the hero takes to react (both move for one refresh); remembered, it
--             blurs by how far it could have walked since it was seen (its speed x the time). A turret
--             seen once stays where it was. Its fire is split over the company units it can reach, so
--             standing among the army shares the fire out.
--   unknown   the enemy's guns the company has not located are spread over the ground it has not seen
--             (or saw long enough ago that anything could have walked in since): the unknown is
--             dangerous in proportion to how much of the enemy is unaccounted for.
--   hazard    the fire that would reach the hero at a point, over the hero's health now: the share of
--             its life lost per second there. A hurt hero weighs the same ground as more dangerous.
--   choice    U = S x (V + G): S = exp(-(hazard along the way + hazard while there)), the chance it
--             survives the plan; V = what the company loses with it (its unit's worth at its level, and
--             for a rez hero its share of the raising still to do); G = what the plan gains (a raised
--             unit's worth; a fighter's damage, valued at what it destroys). The best plan wins.
--
-- The numbers below that are not read from the game are numerical, not behavioural: the normal
-- CDF's coefficients, the tail beyond which a gun's reach is negligible, how finely a path is sampled.

local M = {}
M.__index = M

local exp, sqrt, max, min, floor, ceil, abs = math.exp, math.sqrt, math.max, math.min, math.floor, math.ceil, math.abs
local FRAMES_PER_SECOND = 30

-- the standard normal CDF (Abramowitz & Stegun 26.2.17; error below 7.5e-8)
local function Phi(x)
  local t = 1 / (1 + 0.2316419 * abs(x))
  local d = 0.3989422804014327 * exp(-x * x / 2)
  local p = d * t * (0.319381530 + t * (-0.356563782 + t * (1.781477937 + t * (-1.821255978 + t * 1.330274429))))
  if x >= 0 then return 1 - p end
  return p
end
M.Phi = Phi

-- past this many standard deviations a blurred gun's reach is below 0.1% (Phi(-3.09) = 0.001)
local TAIL = 3.09

-- The chance a gun of range R, last known at distance d, can reach: its position is a 2-D normal of
-- spread sigma about where it was known. Exact at the centre (1 - exp(-R^2 / 2 sigma^2)); across, the
-- radial edge Phi((R - d) / sigma) scaled to match it. Sharp (a step at R) as sigma -> 0; thin and wide
-- (about R^2/sigma^2) when the gun could be anywhere in a walk much longer than its reach.
local function reach(d, R, sigma)
  if R <= 0 then return 0 end
  if sigma <= 0 then
    if d < R then return 1 elseif d > R then return 0 end
    return 0.5
  end
  local centre = 1 - exp(-(R * R) / (2 * sigma * sigma))
  return Phi((R - d) / sigma) * centre / Phi(R / sigma)
end
M.reach = reach

-- ------------------------------------------------------------------ unit profiles (from the defs)
local profiles = {}
function M.profile(defID)
  local p = defID and profiles[defID]
  if p then return p end
  local ud = defID and UnitDefs and UnitDefs[defID]
  p = { dps = 0, range = 0, hp = 1, speed = 0, cost = 0, sight = 0, buildTime = 0, rez = 0 }
  if ud then
    p.hp = tonumber(ud.health) or 1
    p.speed = tonumber(ud.speed) or 0
    p.cost = tonumber(ud.metalCost or ud.buildCostMetal) or 0
    p.sight = tonumber(ud.sightDistance or ud.losRadius) or 0
    p.buildTime = tonumber(ud.buildTime) or 0
    if ud.canResurrect then p.rez = tonumber(ud.resurrectSpeed) or tonumber(ud.buildSpeed) or 0 end
    for _, w in ipairs(ud.weapons or {}) do
      local wd = WeaponDefs and WeaponDefs[w.weaponDef]
      -- guns that can hit the ground (anti-air and paralyzers do not threaten a walking hero)
      if wd and wd.canAttackGround ~= false and not wd.paralyzer then
        local dmg = wd.damages and (wd.damages[0] or wd.damages.default) or 0
        local reload = max(tonumber(wd.reload) or 0, 1 / FRAMES_PER_SECOND)   -- a gun fires at most once a frame
        p.dps = p.dps + dmg * (tonumber(wd.salvoSize) or 1) * (tonumber(wd.projectiles) or 1) / reload
        p.range = max(p.range, tonumber(wd.range) or 0)
      end
    end
  end
  -- Lanchester: an army's fighting strength grows with the sum of (firepower x staying power)^1/2
  p.fight = sqrt(p.dps * p.hp)
  if defID then profiles[defID] = p end
  return p
end

-- ------------------------------------------------------------------ the field
-- api: the engine calls this uses (Spring by default; the harness passes its own)
function M.new(allyTeam, api)
  local self = setmetatable({}, M)
  self.S = api or Spring
  self.ally = allyTeam
  self.frame = nil
  self.dt = 1          -- seconds between refreshes (measured)
  self.mem = {}        -- enemy unitID -> { x, z, frame, defID }
  self.seen = {}       -- cell -> last frame it was in sight
  self.heroValue = {}  -- hero id -> worth while it lived (to value raising its wreck)
  return self
end

local function cellOf(self, x, z)
  local c = min(self.cols - 1, max(0, floor(x / self.cell)))
  local r = min(self.rows - 1, max(0, floor(z / self.cell)))
  return r * self.cols + c, c, r
end

-- The hot lookups below walk the grid in place: a table built per lookup (the cell list, the enemies
-- near, an empty "or {}") was garbage the collector could not keep up with. In Koom Valley's act-2 war
-- the synced heap climbed 250 MB a minute to 1.2 GB, and four sorties hit LuaRules' 1.6 GB cap (11-10).
local NONE = {}
-- the grid's index range covering (x, z) +- r: c0, c1, r0, r1
local function cellRange(self, x, z, r)
  return max(0, floor((x - r) / self.cell)), min(self.cols - 1, floor((x + r) / self.cell)),
    max(0, floor((z - r) / self.cell)), min(self.rows - 1, floor((z + r) / self.cell))
end

-- cells whose centres lie within reach r of (x, z), as (index, centre x, centre z)
local function cellsNear(self, x, z, r)
  local out = {}
  local c0, c1 = max(0, floor((x - r) / self.cell)), min(self.cols - 1, floor((x + r) / self.cell))
  local r0, r1 = max(0, floor((z - r) / self.cell)), min(self.rows - 1, floor((z + r) / self.cell))
  for rr = r0, r1 do
    for cc = c0, c1 do
      out[#out + 1] = rr * self.cols + cc
    end
  end
  return out
end

-- Refresh what the company knows: its units, the enemy it sees or remembers, the ground it has seen.
-- Cheap to call twice in a frame (the second is a no-op), so every gadget that reads it may call it.
function M:refresh(frame)
  if self.frame == frame then return end
  local S = self.S
  if self.frame then self.dt = max(1 / FRAMES_PER_SECOND, (frame - self.frame) / FRAMES_PER_SECOND) end
  self.frame = frame
  local gaia = S.GetGaiaTeamID and S.GetGaiaTeamID()
  -- (records are kept per unit and refreshed in place, each stamped with the frame it was last
  -- seen, so a refresh makes next to no garbage; see NONE above)
  self._aobj, self._eobj, self._alive = self._aobj or {}, self._eobj or {}, self._alive or {}
  local aobj, eobj, alive = self._aobj, self._eobj, self._alive

  -- the company and its allies
  local allies, sights = self.allies or {}, nil
  local na = 0
  if not self.cell then sights = {} end
  for _, team in ipairs(S.GetTeamList(self.ally) or NONE) do
    for _, u in ipairs(S.GetTeamUnits(team) or NONE) do
      local x, _, z = S.GetUnitPosition(u)
      if x then
        local p = M.profile(S.GetUnitDefID(u))
        local hid = S.GetUnitRulesParam(u, "va_hero_id")
        local hp = S.GetUnitHealth(u)
        local a = aobj[u]
        if not a then a = { uid = u }; aobj[u] = a end
        a.x, a.z, a.p, a.hp, a.gen = x, z, p, tonumber(hp) or p.hp, frame
        a.hero = hid ~= nil and hid ~= "" and hid ~= 0
        na = na + 1
        allies[na] = a
        if sights and p.sight > 0 then sights[#sights + 1] = p.sight end
      end
    end
  end
  for i = #allies, na + 1, -1 do allies[i] = nil end
  for u, a in pairs(aobj) do if a.gen ~= frame then aobj[u] = nil end end
  self.allies = allies

  -- the grid: one cell is what one of the company's units sees (the median sight), so "seen" means
  -- what the company's eyes actually cover
  if not self.cell then
    table.sort(sights)
    local med = sights[ceil(#sights / 2)] or 0
    local mx, mz = (Game and Game.mapSizeX) or 8192, (Game and Game.mapSizeZ) or 8192
    self.cell = max(med, sqrt(mx * mz) / 64)   -- (an eyeless company still gets a coarse grid)
    self.cols, self.rows = ceil(mx / self.cell), ceil(mz / self.cell)
    self.cellArea = self.cell * self.cell
  end
  for r = 0, self.rows - 1 do
    for c = 0, self.cols - 1 do
      local cx, cz = (c + 0.5) * self.cell, (r + 0.5) * self.cell
      if S.IsPosInLos(cx, S.GetGroundHeight(cx, cz) or 0, cz, self.ally) then self.seen[r * self.cols + c] = frame end
    end
  end

  -- the enemy: what is in sight or on radar now is remembered where it is; the whole roster's sum is
  -- the briefing (how much enemy there is, not where)
  local rosterDps, rosterFight, rosterSpeedW, rosterRangeW, rosterN = 0, 0, 0, 0, 0
  for _, at in ipairs(S.GetAllyTeamList() or NONE) do
    if at ~= self.ally then
      for _, team in ipairs(S.GetTeamList(at) or NONE) do
        if team ~= gaia then
          for _, u in ipairs(S.GetTeamUnits(team) or NONE) do
            local def = S.GetUnitDefID(u)
            local p = M.profile(def)
            if p.dps > 0 then
              alive[u] = frame
              rosterDps, rosterFight, rosterN = rosterDps + p.dps, rosterFight + p.fight, rosterN + 1
              rosterSpeedW, rosterRangeW = rosterSpeedW + p.speed * p.dps, rosterRangeW + p.range * p.dps
              local los = S.GetUnitLosState(u, self.ally)
              if los and (los.los or los.radar) then
                local x, _, z = S.GetUnitPosition(u)
                if x then
                  local m = self.mem[u]
                  if not m then m = {}; self.mem[u] = m end
                  m.x, m.z, m.frame = x, z, frame
                  if los.los or los.typed then m.defID = def end
                end
              end
            end
          end
        end
      end
    end
  end
  self.rosterDps, self.rosterFight = rosterDps, rosterFight
  -- the enemy's typical gun (fire-weighted): how far it reaches, how fast it walks
  self.rbar = rosterDps > 0 and rosterRangeW / rosterDps or 0
  self.vbar = rosterDps > 0 and rosterSpeedW / rosterDps or 0
  local typical = self._typical or {}
  self._typical = typical
  typical.dps, typical.range, typical.speed = rosterN > 0 and rosterDps / rosterN or 0, self.rbar, self.vbar
  typical.hp, typical.cost, typical.fight = 1, 0, rosterN > 0 and rosterFight / rosterN or 0

  -- forget a remembered gun whose ground is in sight now and it is not there (it moved, or it died)
  for u, m in pairs(self.mem) do
    local idx = cellOf(self, m.x, m.z)
    if m.frame < frame and self.seen[idx] == frame then self.mem[u] = nil end
    if alive[u] ~= frame and self.seen[idx] == frame then self.mem[u] = nil end
  end
  for u, f in pairs(alive) do if f ~= frame then alive[u] = nil end end

  -- the known enemy: guns whose reach spans a couple of cells are bucketed by cell; the long guns
  -- (artillery, an LRPC) are few and kept in one list, so a lookup never scans the map for them
  -- (a lookup cost split, not a behaviour)
  local enemies, buckets, far = self.enemies or {}, self.buckets or {}, self.far or {}
  for _, b in pairs(buckets) do for i = #b, 1, -1 do b[i] = nil end end
  for i = #far, 1, -1 do far[i] = nil end
  local ne, knownDps, knownFight, rmax, rmin = 0, 0, 0, 0, math.huge
  for u, m in pairs(self.mem) do
    local p = m.defID and M.profile(m.defID) or typical
    local age = (frame - m.frame) / FRAMES_PER_SECOND
    local e = eobj[u]
    if not e then e = { uid = u }; eobj[u] = e end
    e.x, e.z, e.p, e.dps, e.range, e.speed = m.x, m.z, p, p.dps, p.range, p.speed
    e.sigma, e.load, e.gen = p.speed * age, 0, frame
    ne = ne + 1
    enemies[ne] = e
    local span = e.range + TAIL * (e.sigma + e.speed * self.dt)
    if span > 2 * self.cell then
      far[#far + 1] = e
    else
      local idx = cellOf(self, e.x, e.z)
      local b = buckets[idx]
      if not b then b = {}; buckets[idx] = b end
      b[#b + 1] = e
      rmax = max(rmax, span)
    end
    knownDps, knownFight = knownDps + p.dps, knownFight + p.fight
    if e.range > 0 then rmin = min(rmin, e.range) end
  end
  for i = #enemies, ne + 1, -1 do enemies[i] = nil end
  for u, e in pairs(eobj) do if e.gen ~= frame then eobj[u] = nil end end
  self.enemies, self.buckets, self.far, self.rmax = enemies, buckets, far, rmax
  self.rmin = rmin < math.huge and rmin or self.rbar

  -- allies bucketed too (for the share of fire each gun spreads over them)
  local abuckets = self.abuckets or {}
  for _, b in pairs(abuckets) do for i = #b, 1, -1 do b[i] = nil end end
  for i = 1, na do
    local a = allies[i]
    local idx = cellOf(self, a.x, a.z)
    local b = abuckets[idx]
    if not b then b = {}; abuckets[idx] = b end
    b[#b + 1] = a
  end
  self.abuckets = abuckets
  -- each gun's load: how many of the company's (non-hero) units it can reach, each by its chance
  for i = 1, ne do
    local e = enemies[i]
    local s = e.sigma + e.speed * self.dt
    local reachR = e.range + TAIL * s
    local c0, c1, r0, r1 = cellRange(self, e.x, e.z, reachR)
    for rr = r0, r1 do
      for cc = c0, c1 do
        local b = abuckets[rr * self.cols + cc]
        if b then
          for k = 1, #b do
            local a = b[k]
            if not a.hero then
              e.load = e.load + reach(sqrt((a.x - e.x) ^ 2 + (a.z - e.z) ^ 2), e.range, s + a.p.speed * self.dt)
            end
          end
        end
      end
    end
  end

  -- the unknown: ground never seen, or seen long enough ago that the enemy's typical walker could have
  -- crossed it since (weight 1 - exp(-age / (cell / vbar)))
  local tau = self.vbar > 0 and self.cell / self.vbar or math.huge
  local unseen, unseenArea = self.unseen or {}, 0
  for idx = 0, self.cols * self.rows - 1 do
    local f = self.seen[idx]
    local u = 1
    if f then u = (tau < math.huge) and (1 - exp(-((frame - f) / FRAMES_PER_SECOND) / tau)) or 0 end
    unseen[idx] = u
    unseenArea = unseenArea + u * self.cellArea
  end
  self.unseen = unseen
  self.unseenDps = max(0, rosterDps - knownDps)
  self.unseenFight = max(0, rosterFight - knownFight)
  self.rhoDps = unseenArea > 0 and self.unseenDps / unseenArea or 0
  self.rhoFight = unseenArea > 0 and self.unseenFight / unseenArea or 0
end

-- How many of the company's (non-hero) units stand within the enemy's typical reach of (x, z): the
-- crowd an unseen gun would have to choose from.
function M:crowdAt(x, z)
  local n = 0
  local c0, c1, r0, r1 = cellRange(self, x, z, self.rbar)
  for rr = r0, r1 do
    for cc = c0, c1 do
      local b = self.abuckets[rr * self.cols + cc]
      if b then
        for i = 1, #b do
          local a = b[i]
          if not a.hero then n = n + reach(sqrt((a.x - x) ^ 2 + (a.z - z) ^ 2), self.rbar, 0) end
        end
      end
    end
  end
  return n
end

-- The unseen ground within the enemy's typical reach of (x, z), in square elmos.
function M:unseenNear(x, z)
  local area = 0
  local c0, c1, r0, r1 = cellRange(self, x, z, self.rbar)
  for rr = r0, r1 do
    for cc = c0, c1 do
      local idx = rr * self.cols + cc
      local cx, cz = (cc + 0.5) * self.cell, (rr + 0.5) * self.cell
      area = area + (self.unseen[idx] or 1) * self.cellArea * reach(sqrt((cx - x) ^ 2 + (cz - z) ^ 2), self.rbar, self.cell / 2)
    end
  end
  return area
end

-- The known enemy guns that could reach (x, z) at all, plus `extra` elmos (bucketed near ones, and
-- every long gun).
function M:nearEnemies(x, z, extra)
  local out = {}
  for _, idx in ipairs(cellsNear(self, x, z, self.rmax + (extra or 0))) do
    for _, e in ipairs(self.buckets[idx] or NONE) do out[#out + 1] = e end
  end
  for _, e in ipairs(self.far) do out[#out + 1] = e end
  return out
end

-- Fire (damage per second) that would reach one more unit standing at (x, z), moving at vSelf.
function M:incoming(x, z, vSelf)
  local total = 0
  vSelf = vSelf or 0
  local dt = self.dt
  local c0, c1, r0, r1 = cellRange(self, x, z, self.rmax)
  for rr = r0, r1 do
    for cc = c0, c1 do
      local b = self.buckets[rr * self.cols + cc]
      if b then
        for i = 1, #b do
          local e = b[i]
          local k = reach(sqrt((x - e.x) ^ 2 + (z - e.z) ^ 2), e.range, e.sigma + (e.speed + vSelf) * dt)
          if k > 0 then total = total + e.dps * k * (k / (k + e.load)) end
        end
      end
    end
  end
  local far = self.far
  for i = 1, #far do
    local e = far[i]
    local k = reach(sqrt((x - e.x) ^ 2 + (z - e.z) ^ 2), e.range, e.sigma + (e.speed + vSelf) * dt)
    if k > 0 then total = total + e.dps * k * (k / (k + e.load)) end
  end
  if self.rhoDps > 0 then total = total + self.rhoDps * self:unseenNear(x, z) / (1 + self:crowdAt(x, z)) end
  return total
end

-- Enemy fighting strength covering (x, z) (Lanchester's sum of (dps x hp)^1/2), seen and unseen.
function M:enemyFightAt(x, z)
  local total = 0
  for _, e in ipairs(self:nearEnemies(x, z)) do
    total = total + e.p.fight * reach(sqrt((x - e.x) ^ 2 + (z - e.z) ^ 2), e.range, e.sigma + e.speed * self.dt)
  end
  if self.rhoFight > 0 then total = total + self.rhoFight * self:unseenNear(x, z) end
  return total
end

-- Hazard along a straight walk from (x1, z1) to (x2, z2) for a hero: the share of its life it expects
-- to lose on the way. Sampled every half of the shortest enemy reach (the finest detail the field has:
-- a gun's disc is crossed in at least two samples).
function M:walkHazard(h, x1, z1, x2, z2)
  local len = sqrt((x2 - x1) ^ 2 + (z2 - z1) ^ 2)
  if len <= 0 then return 0 end
  if h.speed <= 0 then return math.huge end
  local step = (self.rmin or 0) / 2
  if step <= 0 then step = h.speed * self.dt end
  local n = max(1, ceil(len / step))
  local acc = 0
  for i = 1, n do
    local t = (i - 0.5) / n
    acc = acc + self:incoming(x1 + (x2 - x1) * t, z1 + (z2 - z1) * t, h.speed)
  end
  return (acc / n) * (len / h.speed) / max(h.hp, 1)
end

-- ------------------------------------------------------------------ worth and gains
-- The campaign: a named hero who dies is gone for every sortie still to come (the finale is the one
-- after act 2's last mission). The gadgets pass the mission's own numbers.
function M:setCampaign(missionNumber, act2EndMission)
  local n, last = tonumber(missionNumber), tonumber(act2EndMission)
  if n and last then self.sortiesLeft = max(0, last + 1 - n) end
end

-- What the company loses with this hero: its unit's worth at its level (cost x its health over the
-- def's), and for a rez hero its share of the raising still to do (every known wreck's worth x its
-- share of the company's rez speed); for a named hero, all of that again for every sortie it would
-- still have served.
function M:heroWorth(h)
  local v = h.p.cost * (h.maxHp / max(h.p.hp, 1))
  if h.p.rez > 0 then
    local mine, all = h.p.rez, 0
    for _, a in ipairs(self.allies) do all = all + a.p.rez end
    local share = all > 0 and mine / all or 1
    v = v + share * self:wreckWorth()
  end
  if h.hid then v = v * (1 + (self.sortiesLeft or 0)) end
  return v
end

-- Wrecks the company knows of (on ground it has seen) that can be raised: { fid, x, z, worth, work }
function M:wrecks()
  if self._wreckFrame == self.frame then return self._wrecks end
  local S = self.S
  local out, total = {}, 0
  for _, f in ipairs(S.GetAllFeatures() or {}) do
    local name = S.GetFeatureResurrect and S.GetFeatureResurrect(f)
    if name and name ~= "" and UnitDefNames and UnitDefNames[name] then
      local x, _, z = S.GetFeaturePosition(f)
      if x and self.seen[cellOf(self, x, z)] then
        local p = M.profile(UnitDefNames[name].id)
        local hid = S.GetFeatureRulesParam and S.GetFeatureRulesParam(f, "va_hero_wreck")
        local worth = p.cost
        if hid and hid ~= "" and self.heroValue[tostring(hid)] then worth = self.heroValue[tostring(hid)] end
        out[#out + 1] = { fid = f, x = x, z = z, worth = worth, buildTime = p.buildTime, hero = hid and hid ~= "" and tostring(hid) or nil }
        total = total + worth
      end
    end
  end
  self._wrecks, self._wreckTotal, self._wreckFrame = out, total, self.frame
  return out
end

function M:wreckWorth()
  self:wrecks()
  return self._wreckTotal or 0
end

-- A fighter's gain at (x, z) over t seconds: its fire on the enemy in its reach, valued at what that
-- enemy is worth per point of health.
function M:combatGain(h, x, z, t)
  if h.p.dps <= 0 or h.p.range <= 0 then return 0 end
  local worth, health = 0, 0
  for _, e in ipairs(self:nearEnemies(x, z, h.p.range)) do
    local k = reach(sqrt((x - e.x) ^ 2 + (z - e.z) ^ 2), h.p.range, e.sigma + (e.speed + h.speed) * self.dt)
    worth, health = worth + k * e.p.cost, health + k * e.p.hp
  end
  if health <= 0 then return 0 end
  return h.p.dps * t * (worth / health)
end

-- ------------------------------------------------------------------ the choice
-- How long a plan commits a unit: the time to walk across the enemy's typical reach.
function M:horizon(h)
  h.p = h.p or M.profile(h.defID)
  h.speed = h.p.speed
  if h.speed <= 0 then return 0 end
  return (self.rbar > 0 and self.rbar or h.p.range) / h.speed
end

-- One plan's worth: walk to (x, z) and stay t seconds there for `gain`. Returns U, S.
-- Temper (verdance.company.temper, on Umwelt): a hero sees danger e^-nerve as large (shaken, larger;
-- steady, smaller) and gains e^drive as large. nerve, drive in [-1, 1]; 0 when unknown.
function M:planValue(h, V, x, z, gain, t)
  h.p = h.p or M.profile(h.defID)
  h.speed = h.p.speed
  local risk = self:walkHazard(h, h.x, h.z, x, z) + self:incoming(x, z, h.speed) / max(h.hp, 1) * t
  local S = exp(-risk * exp(-(h.nerve or 0)))
  return S * (V + gain * exp(h.drive or 0)), S
end

-- h = { uid, x, z, hp, maxHp, defID, hid, plan = { x, z } (where its current orders take it) }
-- padX, padZ: the company's pad. Returns the best plan, the list it was chosen from, and the hero's
-- worth: { kind = "stay" | "refuge" | "rez", x, z, fid, U, S }
function M:choose(h, padX, padZ)
  local H = self:horizon(h)
  if h.speed <= 0 then return { kind = "stay", x = h.x, z = h.z, U = 0, S = 1 }, {}, 0 end
  local V = self:heroWorth(h)
  if h.hid then self.heroValue[tostring(h.hid)] = V end
  local function hazardHere(x, z) return self:incoming(x, z, h.speed) / max(h.hp, 1) end
  local list = {}
  local function add(kind, x, z, gain, t, fid)
    x = min(max(x, 0), (Game and Game.mapSizeX) or x)
    z = min(max(z, 0), (Game and Game.mapSizeZ) or z)
    local U, S = self:planValue(h, V, x, z, gain, t)
    list[#list + 1] = { kind = kind, x = x, z = z, fid = fid, S = S, U = U }
  end
  -- its own orders (BARb's, or the player's): where they take it, and what it does there
  local px, pz = (h.plan and h.plan.x) or h.x, (h.plan and h.plan.z) or h.z
  add("stay", px, pz, self:combatGain(h, px, pz, H), H)
  -- refuges: where it stands (first: among equally safe places it does not walk for nothing); the pad;
  -- the middle of the company's strength; a ring as far as it walks in H
  add("refuge", h.x, h.z, 0, H)
  add("refuge", padX or h.x, padZ or h.z, 0, H)
  local fx, fz, fw = 0, 0, 0
  for _, a in ipairs(self.allies) do
    if not a.hero and a.p.fight > 0 then fx, fz, fw = fx + a.x * a.p.fight, fz + a.z * a.p.fight, fw + a.p.fight end
  end
  if fw > 0 then add("refuge", fx / fw, fz / fw, 0, H) end
  local ring = h.speed * H
  for i = 0, 7 do
    local a = i * math.pi / 4
    add("refuge", h.x + ring * math.cos(a), h.z + ring * math.sin(a), 0, H)
  end
  -- raising wrecks (a rez hero): best first by an upper bound, walked only while one could still win
  if h.p.rez > 0 then
    local cands = {}
    for _, w in ipairs(self:wrecks()) do
      local work = w.buildTime / h.p.rez
      local ub = exp(-hazardHere(w.x, w.z) * work) * (V + w.worth)
      cands[#cands + 1] = { w = w, work = work, ub = ub }
    end
    table.sort(cands, function(a, b) return a.ub > b.ub end)
    local best = 0
    for _, l in ipairs(list) do best = max(best, l.U) end
    for _, c in ipairs(cands) do
      if c.ub <= best then break end
      add("rez", c.w.x, c.w.z, c.w.worth, c.work, c.w.fid)
      best = max(best, list[#list].U)
    end
  end
  -- the best; its own orders win a tie, then staying where it is (the hero is not taken from its orders,
  -- or walked about, for nothing). A tie is equal to float precision: a gun's normal tail never reaches
  -- exactly zero, and 1e-16 is not a reason to walk.
  local best = list[1]
  for i = 2, #list do if list[i].U > best.U * (1 + 1e-9) then best = list[i] end end
  return best, list, V
end

return M
