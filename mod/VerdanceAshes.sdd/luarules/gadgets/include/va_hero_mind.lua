-- va_hero_mind.lua: the named heroes' minds in the field, on Umwelt's dynamics (va_umwelt_lite.lua).
--
-- The mind is specified in Python (verdance.company.hero_mind) and shipped as mission.heroMind: each
-- hero a node with nerve, drive (its temper from camp), threat and pain; a bridge for each bond on the
-- drop, carrying mood; the drop split into the clusters its bonds make, each stepped apart. Plan:
-- docs/PLAN_pathway_and_umwelt_minds.md, Part 2. LIVE by default (owner call, 2026-11-12): each think it
-- also writes the hero's nerve and drive (2v - 1) into GG.VA_HeroTemper, the rows the doctrine and
-- the autopilot's caution read as the temper from camp, so a hero's caution moves with what happens to it and its friends.
-- SHADOW (modoption va_hero_mind_live=0, for paired trials): it observes, steps and publishes only.
--
-- What it sees, each think (the doctrine's period, which is the mind's hold: one Umwelt step):
--   pain    the share of its health it has lost (it knows its own health: confidence 1)
--   threat  the chance it does not live through standing where it is for the field's horizon,
--           1 - exp(-incoming fire / health x horizon) (the safety field's own reading of staying)
-- and, as it happens, a hero going down: its node despairs (nerve 0), and the bonds carry it to its
-- friends on the drop (rivals take it the other way), as grief does at camp.
-- What it publishes, on each hero unit (the interface the HUD already reads, like va_doctrine):
--   va_mind_<role> = value in [0, 1], va_mind_<role>_c = confidence, rounded to a thousandth.

local Lite = VFS.Include("luarules/gadgets/include/va_umwelt_lite.lua")

local M = {}
local exp, floor, max = math.exp, math.floor, math.max
local SAY_EVERY = 900   -- a VA_HERO_MIND line per hero every 30 game seconds, for the logs

function M.load(mission, live)
  local t = type(mission) == "table" and mission.heroMind or nil
  if type(t) ~= "table" or type(t.clusters) ~= "table" or #t.clusters == 0 then return nil end
  local ok, mind = pcall(Lite.new, t)
  if not ok or not mind then return nil end
  local st = { mind = mind, dirty = {}, h = {}, said = -SAY_EVERY, published = {}, live = live and true or false }
  for ci = 1, #mind.clusters do st.dirty[ci] = false end
  Spring.Echo("VA_HERO_MIND armed heroes=" .. #mind.heroes .. " clusters=" .. #mind.clusters
    .. " roles=" .. table.concat(mind.roles, ",") .. (st.live and " live" or " shadow"))
  return st
end

local function see(st, hid, role, v, eta)
  if Lite.observe(st.mind, hid, role, v, eta) then
    st.dirty[Lite.clusterOf(st.mind, hid)] = true
  end
end

-- heroes: array of { unitID, heroId } on the field now; field: the safety field (or nil)
function M.think(st, frame, heroes, field)
  if not st then return end
  for i = 1, #heroes do
    local uid, hid = heroes[i][1], heroes[i][2]
    if Lite.clusterOf(st.mind, hid) then
      local hp, maxHp = Spring.GetUnitHealth(uid)
      hp, maxHp = tonumber(hp) or 0, tonumber(maxHp) or 0
      if maxHp > 0 then
        see(st, hid, "pain", 1 - hp / maxHp, 1)
        if field then
          local h = st.h[hid] or {}
          st.h[hid] = h
          h.defID = Spring.GetUnitDefID(uid)
          local x, _, z = Spring.GetUnitPosition(uid)
          if x and h.defID then
            local horizon = field:horizon(h)
            local risk = field:incoming(x, z, 0) / max(hp, 1) * horizon
            see(st, hid, "threat", 1 - exp(-risk), 1)
          end
        end
      end
    end
  end
  -- every cluster steps each think (a heartbeat at its hold), its readings in
  for ci = 1, #st.mind.clusters do
    Lite.ingest(st.mind, ci, frame)
    st.dirty[ci] = false
  end
  M.publish(st, frame, heroes)
end

-- A hero went down (its unit destroyed): its node despairs, and its cluster steps now, so the bonds
-- carry it to the living before the next think.
function M.down(st, frame, hid)
  if not st or not Lite.clusterOf(st.mind, hid) then return end
  see(st, hid, "nerve", 0, 1)
  local ci = Lite.clusterOf(st.mind, hid)
  Lite.ingest(st.mind, ci, frame)
  st.dirty[ci] = false
  Spring.Echo("VA_HERO_MIND down hero=" .. tostring(hid) .. " frame=" .. frame)
end

local function round3(v) return floor(v * 1000 + 0.5) / 1000 end

function M.publish(st, frame, heroes)
  local say = frame - st.said >= SAY_EVERY
  if say then st.said = frame end
  local roles = st.mind.roles
  for i = 1, #heroes do
    local uid, hid = heroes[i][1], heroes[i][2]
    if Lite.clusterOf(st.mind, hid) then
      local line = say and { "VA_HERO_MIND hero=" .. tostring(hid) } or nil
      for r = 1, #roles do
        local v, c = Lite.belief(st.mind, hid, roles[r])
        v, c = round3(v), round3(c)
        Spring.SetUnitRulesParam(uid, "va_mind_" .. roles[r], v, { public = true })
        Spring.SetUnitRulesParam(uid, "va_mind_" .. roles[r] .. "_c", c, { public = true })
        if line then line[#line + 1] = roles[r] .. "=" .. v .. "/" .. c end
      end
      if line then Spring.Echo(table.concat(line, " ") .. " frame=" .. frame) end
      if st.live and GG and GG.VA_HeroTemper then
        local row = GG.VA_HeroTemper[hid]
        if not row then row = {}; GG.VA_HeroTemper[hid] = row end
        local nv = Lite.belief(st.mind, hid, "nerve")
        local dv = Lite.belief(st.mind, hid, "drive")
        if nv then row.nerve = 2 * nv - 1 end
        if dv then row.drive = 2 * dv - 1 end
      end
    end
  end
end

return M
