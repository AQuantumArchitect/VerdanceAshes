-- va_field_engine.lua: field effects v2 (2026-10-29).
--
-- Once a second, for the player's company:
--   * SELF  each hero's own effect on itself and its pack (20-40%), maybe conditional
--           (moving, still, hurt, enemy_near, unseen, on_water, crowd), maybe scaled by allies near;
--           grows with the hero's XP (nothing green, all of it at 2.4 XP) and with home ground
--           (the map's pressure on the hero's strong axes).
--   * AURAS reach the other company units that match them: hero tags, axes, unit names, unit kinds.
--           Units without a hero match by what they are (air = sky, boats/hovers = water, builders =
--           craft, structures = pad and hold, fusions = kind fusion). All auras on one stat on one
--           unit add up to at most +15%.
--   * BONDS a bonded hero's pack always takes the aura, x1.5. A rival's pack never takes it; inside
--           the radius it takes friction instead (a small minus).
--   * KINDS stat multipliers, plus income (metal/energy), xp (veterancy trickle), repair (heal).
--
-- Stats are applied through the gadgets that own them, so nothing clobbers anything: HP, reload and
-- range compose inside veterancy (va_fx_* rules params), build power inside craft XP, speed inside
-- the shared mobility composer. What none of them owns (vision, splash, energy, and HP/range/reload
-- of units veterancy skips) is applied here from the unit's own def values.
--
-- Pure module: E.tick(ctx) with ctx = { teamID, heroes = { id -> rec }, xpOf(id, rec), mapId, dt }.

local E = {}

local function load(path)
  if VFS and VFS.Include then
    local ok, mod = pcall(VFS.Include, path)
    if ok and type(mod) == "table" then return mod end
  end
  local here = debug and debug.getinfo and debug.getinfo(1, "S")
  local dir = here and here.source and here.source:match("^@(.*[/\\])") or ""
  local ok, mod = pcall(dofile, dir .. path:match("[^/]+$"))
  if ok and type(mod) == "table" then return mod end
  return nil
end

E.FX = load("luarules/gadgets/include/va_field_effects.lua")
E.Tags = nil -- va_hero_tags (fieldXpScale, isFusionDef); set by the caller
if not E.FX then return E end

local FX = E.FX
local R = FX.RULES
local STATS = { "hp", "speed", "range", "reload", "build", "vision", "energy", "splash" }
local PUBLIC = { public = true }

-- per-unit state: last applied mult per stat, direct-apply bases
E.applied = {}
E.lastReport = {}
E.income = { metal = 0, energy = 0 }

local tagset = {}
for hid, h in pairs(FX.HEROES) do
  local s = {}
  for _, t in ipairs(h.tags or {}) do s[t] = true end
  tagset[hid] = s
end
E.tagset = tagset

-- What a unit without a hero is ------------------------------------------------------------
local defInfo = {}
local function infoOf(defID)
  local c = defInfo[defID]
  if c then return c end
  local ud = UnitDefs and UnitDefs[defID]
  c = { tags = {}, name = "", fusion = false, armed = false }
  if ud then
    local n = string.lower(tostring(ud.name or ""))
    c.name = n
    if ud.canFly or ud.isAirUnit then c.tags.sky = true end
    local md = ud.moveDef and string.lower(tostring(ud.moveDef.name or "")) or ""
    if (tonumber(ud.minWaterDepth) or 0) > 0 or ud.floatOnWater or md:find("hover", 1, true)
        or md:find("boat", 1, true) or md:find("amph", 1, true) or md:find("uboat", 1, true) then
      c.tags.water = true
    end
    if ud.isBuilder and (tonumber(ud.buildSpeed) or 0) > 0 and not ud.isFactory then c.tags.craft = true end
    if ud.isBuilding or ud.isImmobile then c.tags.pad = true; c.tags.hold = true end
    c.fusion = (E.Tags and E.Tags.isFusionDef and E.Tags.isFusionDef(ud)) and true or false
    c.armed = type(ud.weapons) == "table" and ud.weapons[1] ~= nil
  end
  defInfo[defID] = c
  return c
end
E.infoOf = infoOf

-- Home ground --------------------------------------------------------------------------------
function E.terrainFactor(heroId, mapId)
  local h = FX.HEROES[heroId]
  local mp = mapId and FX.MAPS[mapId]
  if not h or not mp then return 1 end
  local sum, n = 0, 0
  for axis, v in pairs(h.axes or {}) do
    if axis ~= "offense" and v >= 0.5 then
      sum = sum + (mp[axis] or 0)
      n = n + 1
    end
  end
  if n == 0 then return 1 end
  local f = 1 + (R.terrainGain or 0.35) * (sum / n)
  local lo, hi = 1 + (R.terrainFloor or -0.15), 1 + (R.terrainGain or 0.35)
  if f < lo then f = lo elseif f > hi then f = hi end
  return f
end

-- Matching ---------------------------------------------------------------------------------
local function axesOk(match, leader)
  if not match.axes then return true end
  local h = leader and FX.HEROES[leader]
  if not h then return false end
  for axis, min in pairs(match.axes) do
    if (h.axes[axis] or 0) < min then return false end
  end
  return true
end

-- does unit record u satisfy match (ignoring bonds)?
local function matches(match, u)
  if match.any then return true end
  if match.units then
    for i = 1, #match.units do if match.units[i] == u.name then return true end end
  end
  if match.kinds then
    for i = 1, #match.kinds do if match.kinds[i] == "fusion" and u.fusion then return true end end
  end
  if match.tags then
    local ts = u.leader and tagset[u.leader] or u.defTags
    for i = 1, #match.tags do
      if ts[match.tags[i]] then return axesOk(match, u.leader) end
    end
    return false
  end
  if match.axes then return axesOk(match, u.leader) end
  return false
end
E.matches = matches

local function heroMatches(match, hid)
  if match.any then return true end
  if match.tags then
    for i = 1, #match.tags do if tagset[hid][match.tags[i]] then return axesOk(match, hid) end end
    return false
  end
  if match.axes then return axesOk(match, hid) end
  return false
end

-- Conditions -------------------------------------------------------------------------------
local enemyAllies
local function enemyAllyTeams(teamID)
  if enemyAllies then return enemyAllies end
  enemyAllies = {}
  local mine = Spring.GetTeamInfo and select(6, Spring.GetTeamInfo(teamID)) or nil
  local gaia = Spring.GetGaiaTeamID and Spring.GetGaiaTeamID()
  local gaiaAlly = gaia and Spring.GetTeamInfo and select(6, Spring.GetTeamInfo(gaia)) or nil
  for _, at in ipairs((Spring.GetAllyTeamList and Spring.GetAllyTeamList()) or {}) do
    if at ~= mine and at ~= gaiaAlly then enemyAllies[#enemyAllies + 1] = at end
  end
  return enemyAllies
end

local function cond(when, anchor, ctx, nearCount)
  if not when then return true end
  if when == "moving" or when == "still" then
    local vx, _, vz = Spring.GetUnitVelocity(anchor.id)
    local moving = vx and (vx * vx + vz * vz) > 0.04
    if when == "moving" then return moving and true or false end
    return not moving
  elseif when == "hurt" then
    local hp, mx = Spring.GetUnitHealth(anchor.id)
    return hp and mx and mx > 0 and hp / mx < (R.hurt or 0.5) or false
  elseif when == "enemy_near" then
    return Spring.GetUnitNearestEnemy(anchor.id, R.nearRadius or 600, false) ~= nil
  elseif when == "unseen" then
    if not Spring.IsUnitInLos then return false end
    for _, at in ipairs(enemyAllyTeams(ctx.teamID)) do
      if Spring.IsUnitInLos(anchor.id, at) then return false end
    end
    return true
  elseif when == "on_water" then
    local gh = Spring.GetGroundHeight(anchor.x, anchor.z)
    return gh ~= nil and gh < 0
  elseif when == "crowd" then
    return (nearCount or 0) >= (R.crowd or 3)
  end
  return false
end
E.cond = cond

-- Scaling: a pack counts 1 (by its hero), a unit without a hero counts a quarter.
local function scaleFactor(scale, n)
  if not scale then return 1 end
  local per = tonumber(scale.per) or 1
  local f = n / per
  if f > 1 then f = 1 end
  return 0.4 + 0.6 * f
end

-- Applying ---------------------------------------------------------------------------------
local function defOf(unitID)
  local dID = Spring.GetUnitDefID(unitID)
  return dID and UnitDefs[dID]
end

local function directHp(unitID, mult, st)
  local cur, mx = Spring.GetUnitHealth(unitID)
  mx = tonumber(mx) or 0
  if mx <= 0 or not Spring.SetUnitMaxHealth then return end
  st.hpBase = st.hpBase or (mx / (st.hp or 1))
  local newMax = st.hpBase * mult
  local frac = (tonumber(cur) or mx) / mx
  pcall(Spring.SetUnitMaxHealth, unitID, newMax)
  pcall(Spring.SetUnitHealth, unitID, newMax * frac)
end

local function directWeapons(unitID, key, mult)
  local ud = defOf(unitID)
  if not ud or not ud.weapons then return end
  local maxR = 0
  for i = 1, #ud.weapons do
    local wd = WeaponDefs[ud.weapons[i].weaponDef]
    if wd then
      if key == "range" then
        local r = (tonumber(wd.range) or 0) * mult
        if r > 0 then pcall(Spring.SetUnitWeaponState, unitID, i, "range", r); if r > maxR then maxR = r end end
      else
        local rt = tonumber(wd.reload) or tonumber(wd.reloadTime) or 0
        if rt > 0 then pcall(Spring.SetUnitWeaponState, unitID, i, "reloadTime", rt * mult) end
      end
    end
  end
  if key == "range" and maxR > 0 and Spring.SetUnitMaxRange then pcall(Spring.SetUnitMaxRange, unitID, maxR) end
end

local function directVision(unitID, mult)
  local ud = defOf(unitID)
  if not ud or not Spring.SetUnitSensorRadius then return end
  local los = tonumber(ud.sightDistance) or tonumber(ud.losRadius) or 0
  local air = tonumber(ud.airSightDistance) or tonumber(ud.airLosRadius) or los
  local radar = tonumber(ud.radarDistance) or 0
  if los > 0 then pcall(Spring.SetUnitSensorRadius, unitID, "los", los * mult) end
  if air > 0 then pcall(Spring.SetUnitSensorRadius, unitID, "airLos", air * mult) end
  if radar > 0 then pcall(Spring.SetUnitSensorRadius, unitID, "radar", radar * mult) end
end

local function directSplash(unitID, mult)
  local ud = defOf(unitID)
  if not ud or not ud.weapons or not Spring.SetUnitWeaponDamages then return end
  for i = 1, #ud.weapons do
    local wd = WeaponDefs[ud.weapons[i].weaponDef]
    local aoe = wd and tonumber(wd.damageAreaOfEffect) or 0
    if aoe > 0 then
      pcall(Spring.SetUnitWeaponDamages, unitID, i, "damageAreaOfEffect", aoe * mult)
      pcall(Spring.SetUnitWeaponDamages, unitID, i, "craterAreaOfEffect", (tonumber(wd.craterAreaOfEffect) or aoe) * mult)
    end
  end
end

local function directEnergy(unitID, mult)
  local ud = defOf(unitID)
  local base = tonumber(ud and ud.energyMake) or 0
  if base <= 0 or not Spring.SetUnitResourcing then return end
  pcall(Spring.SetUnitResourcing, unitID, "ue", base * mult)
  Spring.SetUnitRulesParam(unitID, "va_field_energy_make", base * mult, PUBLIC)
end

local function directBuild(unitID, mult)
  local ud = defOf(unitID)
  local base = tonumber(ud and ud.buildSpeed) or 0
  if base <= 0 or not Spring.SetUnitBuildSpeed then return end
  local bp = base * mult
  pcall(Spring.SetUnitBuildSpeed, unitID, bp, bp, bp * 0.15, bp, bp, bp)
end

-- mult is the factor on the stat as the engine reads it (reloadTime for reload).
function E.applyStat(unitID, stat, mult)
  local st = E.applied[unitID]
  if not st then st = {}; E.applied[unitID] = st end
  local last = st[stat] or 1
  if math.abs(mult - last) < 0.004 then return false end
  Spring.SetUnitRulesParam(unitID, "va_fx_" .. stat, mult, PUBLIC)
  if stat == "hp" or stat == "reload" or stat == "range" then
    local owned = GG and GG.VA_VetFieldRefresh and GG.VA_VetFieldRefresh(unitID)
    if not owned then
      if stat == "hp" then directHp(unitID, mult, st) else directWeapons(unitID, stat, mult) end
    end
  elseif stat == "build" then
    local owned = GG and GG.VA_CraftFieldRefresh and GG.VA_CraftFieldRefresh(unitID)
    if not owned then directBuild(unitID, mult) end
  elseif stat == "speed" then
    if GG and GG.VA_MobilitySetField then pcall(GG.VA_MobilitySetField, unitID, mult)
    else Spring.SetUnitRulesParam(unitID, "va_field_speed_mult", mult, PUBLIC) end
  elseif stat == "vision" then
    directVision(unitID, mult)
  elseif stat == "splash" then
    directSplash(unitID, mult)
  elseif stat == "energy" then
    directEnergy(unitID, mult)
  end
  st[stat] = mult
  return true
end

local function multOf(stat, bonus)
  if stat == "reload" then return 1 / (1 + bonus) end
  return 1 + bonus
end
E.multOf = multOf

function E.forget(unitID)
  E.applied[unitID] = nil
end

-- The tick ---------------------------------------------------------------------------------
local pool = {}       -- reused unit records
local acc = {}        -- unitIndex -> { self = {stat=b}, aura = {stat=b} }

local function rec_(i)
  local u = pool[i]
  if not u then u = {}; pool[i] = u end
  return u
end

local function accOf(i)
  local a = acc[i]
  if not a then a = { self = {}, aura = {} }; acc[i] = a end
  for k in pairs(a.self) do a.self[k] = nil end
  for k in pairs(a.aura) do a.aura[k] = nil end
  a.touched = false
  return a
end

local function baseId(id)
  return tostring(id):match("^[^#]+") or tostring(id)
end

function E.tick(ctx)
  if not ctx or not ctx.teamID then return nil end
  local team = ctx.teamID
  local dt = ctx.dt or 1
  local list = Spring.GetTeamUnits(team) or {}
  -- hero anchors
  local anchors, heroUnit = {}, {}
  for id, rec in pairs(ctx.heroes or {}) do
    local u = rec and rec.unitID
    if u and Spring.ValidUnitID(u) and not Spring.GetUnitIsDead(u) then
      local b = baseId(id)
      heroUnit[u] = b
      if FX.HEROES[b] and not anchors[b] then anchors[b] = { id = u, rec = rec, partner = (b ~= tostring(id)) } end
      if FX.HEROES[b] and anchors[b] and anchors[b].partner and b == tostring(id) then
        anchors[b] = { id = u, rec = rec, partner = false }
      end
    end
  end
  -- unit records
  local n = 0
  for i = 1, #list do
    local id = list[i]
    if Spring.ValidUnitID(id) and not Spring.GetUnitIsDead(id) then
      local x, _, z = Spring.GetUnitPosition(id)
      if x then
        n = n + 1
        local u = rec_(n)
        u.id, u.x, u.z = id, x, z
        local lead = heroUnit[id]
        if not lead then
          local l = Spring.GetUnitRulesParam(id, "va_pack_leader")
          lead = l and FX.HEROES[tostring(l)] and tostring(l) or nil
        end
        u.leader = lead
        local info = infoOf(Spring.GetUnitDefID(id))
        u.name, u.fusion, u.defTags = info.name, info.fusion, info.tags
        u.acc = accOf(n)
      end
    end
  end
  for b, a in pairs(anchors) do
    local x, _, z = Spring.GetUnitPosition(a.id)
    a.x, a.z = x, z
  end
  -- which heroes are on the field (for company_tag scaling and income)
  local onField = {}
  for b in pairs(anchors) do onField[#onField + 1] = b end
  table.sort(onField)

  local near2 = (R.nearRadius or 600) ^ 2
  local report = {}
  local incomeM, incomeE = 0, 0

  for _, b in ipairs(onField) do
    local a = anchors[b]
    local H = FX.HEROES[b]
    local xpScale = 1
    if E.Tags and E.Tags.fieldXpScale then
      xpScale = E.Tags.fieldXpScale((ctx.xpOf and ctx.xpOf(b, a.rec)) or (a.rec and a.rec.peakXp) or 0)
    end
    local tf = E.terrainFactor(b, ctx.mapId)
    -- packs near the anchor (allies_near / crowd)
    local nearN, nearPacks = 0, {}
    for i = 1, n do
      local u = pool[i]
      local dx, dz = u.x - a.x, u.z - a.z
      if dx * dx + dz * dz <= near2 and u.leader ~= b then
        if u.leader then
          if not nearPacks[u.leader] then nearPacks[u.leader] = true; nearN = nearN + 1 end
        else
          nearN = nearN + 0.25
        end
      end
    end
    local rep = { hero = b, xpScale = xpScale, terrain = tf, selfOn = false, auras = {} }
    report[#report + 1] = rep

    -- SELF
    local s = H.self
    if s and s.kind == "stat" and cond(s.when, a, ctx, nearN) then
      local sf = 1
      if s.scale then sf = scaleFactor(s.scale, nearN) end
      local bonus = s.bonus * xpScale * tf * sf
      rep.selfOn, rep.selfBonus = true, bonus
      for i = 1, n do
        local u = pool[i]
        if u.leader == b then
          u.acc.self[s.stat] = (u.acc.self[s.stat] or 0) + bonus
          u.acc.touched = true
        end
      end
    end

    -- AURAS
    local ties = FX.TIES[b] or {}
    for ai, au in ipairs(H.auras or {}) do
      local on = cond(au.when, a, ctx, nearN)
      local arep = { on = on, targets = 0 }
      rep.auras[ai] = arep
      if on then
        local company = au.scope == "company"
        local r2 = (au.radius or R.auraRadius or 650) ^ 2
        local m = au.match or {}
        if au.kind == "income" then
          local amount = 0
          if m.self then
            amount = au.bonus
          else
            for _, other in ipairs(onField) do
              local t = ties[other]
              if t ~= -1 and (t == 1 or heroMatches(m, other)) then
                amount = amount + au.bonus * ((t == 1) and (R.bondBoost or 1.5) or 1)
              end
            end
          end
          amount = amount * xpScale * dt
          if au.resource == "energy" then incomeE = incomeE + amount else incomeM = incomeM + amount end
          arep.targets = amount
        else
          -- count matching packs for scale
          local sf = 1
          if au.scale then
            local cnt = 0
            if au.scale.by == "company_tag" then
              for _, other in ipairs(onField) do if tagset[other][au.scale.tag] then cnt = cnt + 1 end end
            elseif au.scale.by == "allies_near" then
              cnt = nearN
            else
              local seen = {}
              for i = 1, n do
                local u = pool[i]
                if u.leader ~= b then
                  local dx, dz = u.x - a.x, u.z - a.z
                  if (company or dx * dx + dz * dz <= r2) and matches(m, u) then
                    if u.leader then
                      if not seen[u.leader] then seen[u.leader] = true; cnt = cnt + 1 end
                    else
                      cnt = cnt + 0.25
                    end
                  end
                end
              end
            end
            sf = scaleFactor(au.scale, cnt)
          end
          for i = 1, n do
            local u = pool[i]
            if u.leader ~= b then
              local dx, dz = u.x - a.x, u.z - a.z
              if company or dx * dx + dz * dz <= r2 then
                local t = u.leader and ties[u.leader] or 0
                local amt = nil
                if t == -1 then
                  if au.kind == "stat" and not company then amt = -au.bonus * (R.frictionFrac or 0.4) * xpScale end
                elseif t == 1 or matches(m, u) then
                  amt = au.bonus * xpScale * sf * ((t == 1) and (R.bondBoost or 1.5) or 1)
                end
                if amt then
                  arep.targets = arep.targets + 1
                  if au.kind == "stat" then
                    u.acc.aura[au.stat] = (u.acc.aura[au.stat] or 0) + amt
                    u.acc.touched = true
                  elseif au.kind == "xp" then
                    local cur = Spring.GetUnitExperience and Spring.GetUnitExperience(u.id) or nil
                    if cur and Spring.SetUnitExperience then pcall(Spring.SetUnitExperience, u.id, cur + amt * dt) end
                  elseif au.kind == "repair" then
                    local hp, mx = Spring.GetUnitHealth(u.id)
                    if hp and mx and mx > 0 and hp / mx < (au.below or 1) and hp > 0 then
                      pcall(Spring.SetUnitHealth, u.id, math.min(mx, hp + mx * amt * dt))
                    end
                  end
                end
              end
            end
          end
        end
      end
    end
    if a.id then
      Spring.SetUnitRulesParam(a.id, "va_fx_self_on", rep.selfOn and 1 or 0, PUBLIC)
      Spring.SetUnitRulesParam(a.id, "va_fx_terrain", tf, PUBLIC)
    end
  end

  -- compose and apply
  local cap, floor = R.auraCap or 0.15, R.frictionFloor or -0.06
  local changed = 0
  for i = 1, n do
    local u = pool[i]
    local st = E.applied[u.id]
    if u.acc.touched or st then
      for _, stat in ipairs(STATS) do
        local au = u.acc.aura[stat] or 0
        if au > cap then au = cap elseif au < floor then au = floor end
        local total = (u.acc.self[stat] or 0) + au
        local want = multOf(stat, total)
        if (st and st[stat]) or math.abs(want - 1) >= 0.004 then
          if E.applyStat(u.id, stat, want) then changed = changed + 1 end
          st = E.applied[u.id]
        end
      end
    end
  end

  if (incomeM > 0 or incomeE > 0) and Spring.AddTeamResource then
    if incomeM > 0 then Spring.AddTeamResource(team, "metal", incomeM) end
    if incomeE > 0 then Spring.AddTeamResource(team, "energy", incomeE) end
  end
  E.income.metal = E.income.metal + incomeM
  E.income.energy = E.income.energy + incomeE
  E.lastReport = report
  return { units = n, heroes = #onField, changed = changed, metal = incomeM, energy = incomeE, report = report }
end

return E
