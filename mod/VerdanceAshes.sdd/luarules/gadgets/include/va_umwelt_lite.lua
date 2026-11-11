-- va_umwelt_lite.lua: Umwelt's belief dynamics, run in the engine for the heroes' minds.
--
-- The mind is specified once, in Python (tools/verdance/company/hero_mind.py: mind_tables), and comes
-- here as plain tables (mission.heroMind). This file is a faithful port of what Umwelt (a00a0e7, the
-- GameHost path with learning frozen) does to each role of each node, and tests/test_umwelt_lite_parity.py
-- holds it to Umwelt itself on recorded streams. Owner direction (2026-11-11): sparse clusters with a few
-- bridges, run apart ("if they all connect it becomes a giant matrix"); coarse steps as the field changes;
-- the resolver lives in the engine and the HUD reads the results through the same interface.
--
-- Per role, a Bloch vector r = (x, y, z); value (z + 1) / 2, confidence |r|. Per ingest of a cluster:
--   1. catch-up: min(floor(gap / hold) - 1, catchupMax) field steps for the quiet since its last ingest
--      (none on its first), then one more (engine.py:1070-1089, 1118)
--   2. a field step: every role relaxes toward its centre by RK4's step on the dissipator,
--      z <- z P(-gd h), (x, y) <- (x, y) P(-gd h / 2), P(s) = 1 + s + s^2/2 + s^3/6 + s^4/24
--      (batched_evolve.py:361-399); then each bridge in order nudges both ends toward their mean,
--      alpha = bridgeStrength |c|, the far end mirrored (x, -y, -z) when c < 0 (field.py:286-339)
--   3. what was seen since the last ingest (the last reading of a role wins) blends in after the step:
--      r <- (1 - a) r + a (0, 0, rObs (2 v - 1)), a = eta (engine.py:1128-1179; ingress.py:501-568)
-- No learning (the Python side learns between sorties), and no physicality clamp: every state here is
-- a product of physical single-role states, which the clamp leaves alone.
--
-- Allocation-free after M.new: state and pending readings live in flat arrays indexed
-- (hero - 1) * R + role, reused for the whole match (the 11-10 out-of-memory crash was per-call tables).

local M = {}

local function P(s) return 1 + s * (1 + s * (0.5 + s * (1 / 6 + s / 24))) end

local function clamp(v, lo, hi)
  if v < lo then return lo end
  if v > hi then return hi end
  return v
end

-- tables: { roles = {...}, shared = {...}, clusters = { { heroes = {...}, bridges = { {a, b, c}, ... } } },
--           start = { [hero] = { [role] = value } }, umwelt = { h, gammaDiss, bridgeStrength, rObs,
--           catchupMax }, holdS = seconds }
function M.new(tables)
  local u = tables.umwelt or {}
  local mind = {
    roles = {}, roleIx = {}, R = 0, shared = {},
    heroes = {}, heroIx = {}, heroCluster = {},
    x = {}, y = {}, z = {}, pendV = {}, pendE = {}, pendOn = {},
    clusters = {},
    hold = tonumber(tables.holdS) or 0,
    fps = (Game and tonumber(Game.gameSpeed)) or 30,   -- BAR's sim frames per game second
    gdh = (tonumber(u.gammaDiss) or 0) * (tonumber(u.h) or 0),
    bs = tonumber(u.bridgeStrength) or 0,
    rObs = tonumber(u.rObs) or 0,
    cmax = tonumber(u.catchupMax) or 0,
  }
  mind.fz, mind.fxy = P(-mind.gdh), P(-mind.gdh / 2)
  for i, r in ipairs(tables.roles or {}) do
    mind.roles[i] = tostring(r)
    mind.roleIx[tostring(r)] = i
  end
  mind.R = #mind.roles
  for _, r in ipairs(tables.shared or tables.roles or {}) do
    local ri = mind.roleIx[tostring(r)]
    if ri then mind.shared[#mind.shared + 1] = ri end
  end
  local start = tables.start or {}
  for ci, cl in ipairs(tables.clusters or {}) do
    local c = { heroes = {}, bridges = {}, last = nil, pk = {}, np = 0 }
    for _, h in ipairs(cl.heroes or {}) do
      h = tostring(h)
      local hi = #mind.heroes + 1
      mind.heroes[hi], mind.heroIx[h], mind.heroCluster[hi] = h, hi, ci
      c.heroes[#c.heroes + 1] = hi
      for ri = 1, mind.R do
        local k = (hi - 1) * mind.R + ri
        local v = tonumber((start[h] or {})[mind.roles[ri]]) or 0.5
        mind.x[k], mind.y[k], mind.z[k] = 0, 0, 2 * v - 1
        mind.pendV[k], mind.pendE[k], mind.pendOn[k] = 0, 0, false
      end
    end
    for _, b in ipairs(cl.bridges or {}) do
      local a, bb = mind.heroIx[tostring(b[1])], mind.heroIx[tostring(b[2])]
      if a and bb then c.bridges[#c.bridges + 1] = { a, bb, tonumber(b[3]) or 0 } end
    end
    mind.clusters[ci] = c
  end
  return mind
end

-- Something seen about a hero: a reading in [0, 1] at a confidence eta in [0, 1]. It waits for its
-- cluster's next ingest; a later reading of the same role before then replaces it.
function M.observe(mind, hero, role, value, eta)
  local hi, ri = mind.heroIx[tostring(hero)], mind.roleIx[tostring(role)]
  if not hi or not ri then return false end
  local k = (hi - 1) * mind.R + ri
  mind.pendV[k], mind.pendE[k] = clamp(tonumber(value) or 0.5, 0, 1), clamp(tonumber(eta) or 0, 0, 1)
  if not mind.pendOn[k] then
    mind.pendOn[k] = true
    local c = mind.clusters[mind.heroCluster[hi]]
    c.np = c.np + 1
    c.pk[c.np] = k
  end
  return true
end

local function fieldStep(mind, c)
  local x, y, z, R, fz, fxy = mind.x, mind.y, mind.z, mind.R, mind.fz, mind.fxy
  for _, hi in ipairs(c.heroes) do
    local base = (hi - 1) * R
    for ri = 1, R do
      local k = base + ri
      x[k], y[k], z[k] = x[k] * fxy, y[k] * fxy, z[k] * fz
    end
  end
  local bs = mind.bs
  for _, br in ipairs(c.bridges) do
    local cpl = br[3]
    local a = bs * math.abs(cpl)
    local s = cpl < 0 and -1 or 1     -- the far end mirrored (sigma-x conjugation) for a negative coupling
    for _, ri in ipairs(mind.shared) do
      local ka, kb = (br[1] - 1) * R + ri, (br[2] - 1) * R + ri
      local xa, ya, za, xb, yb, zb = x[ka], y[ka], z[ka], x[kb], y[kb], z[kb]
      x[ka] = xa + a * ((xa + xb) / 2 - xa)
      y[ka] = ya + a * ((ya + s * yb) / 2 - ya)
      z[ka] = za + a * ((za + s * zb) / 2 - za)
      x[kb] = xb + a * ((xb + xa) / 2 - xb)
      y[kb] = yb + a * ((yb + s * ya) / 2 - yb)
      z[kb] = zb + a * ((zb + s * za) / 2 - zb)
    end
  end
end

-- Step one cluster to game frame `frame` and take in what was seen. Returns the steps it ran.
-- Time is whole frames: the gap in seconds is frames / gameSpeed, the same correctly rounded number
-- Umwelt gets from its clock's whole microseconds, so the catch-up count agrees even on an exact
-- multiple of the hold (2.4 s / 0.6 s is 3.9999999999999996 to both: three holds, not four).
function M.ingest(mind, ci, frame)
  local c = mind.clusters[ci]
  if not c then return 0 end
  local steps = 1
  if c.last and mind.hold > 0 then
    local extra = math.min(math.floor((frame - c.last) / mind.fps / mind.hold) - 1, mind.cmax)
    if extra > 0 then steps = steps + extra end
  end
  c.last = frame
  for _ = 1, steps do fieldStep(mind, c) end
  local x, y, z, rObs = mind.x, mind.y, mind.z, mind.rObs
  for i = 1, c.np do
    local k = c.pk[i]
    local a, t = mind.pendE[k], rObs * clamp(2 * mind.pendV[k] - 1, -1, 1)
    x[k], y[k], z[k] = (1 - a) * x[k], (1 - a) * y[k], (1 - a) * z[k] + a * t
    mind.pendOn[k] = false
  end
  c.np = 0
  return steps
end

-- The cluster a hero is in (to ingest it when something happens to that hero), or nil.
function M.clusterOf(mind, hero)
  local hi = mind.heroIx[tostring(hero)]
  return hi and mind.heroCluster[hi] or nil
end

-- A role's belief: value in [0, 1] and confidence in [0, 1].
function M.belief(mind, hero, role)
  local hi, ri = mind.heroIx[tostring(hero)], mind.roleIx[tostring(role)]
  if not hi or not ri then return nil, nil end
  local k = (hi - 1) * mind.R + ri
  local x, y, z = mind.x[k], mind.y[k], mind.z[k]
  return (z + 1) / 2, math.sqrt(x * x + y * y + z * z)
end

return M
