-- Procedural hero tags + ONE field-effect stat per hero.
-- Career rank stays separate ("Green" / "Proven" / …). Legacy "Blooded" → Proven.
-- Mobility cohesion (pack +50% / drag) lives in va_pack_overlay — NOT here.
-- Field effects scale with mentor XP (scout/factory heroes bank subordinate XP).

local M = {}

M.DEFAULT_RANK = "Green"

-- φ saturation for field-effect strength from banked XP.
local PHI = (1 + math.sqrt(5)) * 0.5

-- Tag catalog: each tag is ONE stat, matched to what the hero is (owner pass, 2026-10-24):
-- artillery reaches farther, gunships and skirmishers fire faster, scouts see farther, the two
-- siege walkers (Fatboy, Bro) and Thresh's bombs hit a wider area, builders build faster.
-- The value is the bonus at 2.4 XP; it is nothing at no XP and grows with experience
-- (M.fieldXpScale). Mults multiply; missing keys = 1.0.
M.TAGS = {
  -- health
  shieldline = { label = "Shieldline", hp = 1.15, fiction = "Holds the gate so someone else can be clever." },
  pavise_ward = { label = "Pavise Ward", hp = 1.15, fiction = "Standing shield: Centurions in the aura remember the war together." },
  stubborn = { label = "Stubborn", hp = 1.15, fiction = "Will not be moved. Sometimes that is the plan." },
  fordbreaker = { label = "Fordbreaker", hp = 1.15, fiction = "Refuses to dry out." },
  riot_breaker = { label = "Riot Breaker", hp = 1.15, fiction = "Closes distance like an argument already won." },
  merc_debt = { label = "Merc Debt", hp = 1.15, fiction = "Unpaid for three wars, still breaks lines." },
  parade_ground = { label = "Parade Ground", hp = 1.15, fiction = "Two Bulls that take the hit so the order arrives." },
  weather_tithe = { label = "Weather Tithe", hp = 1.15, fiction = "The circle holds because the ledger will not close." },
  believer = { label = "Believer", hp = 1.15, fiction = "Sixteen Pawns who think he is the real thing, and fight like it." },
  shell_game = { label = "Shell Game", hp = 1.15, fiction = "Two Turtles, one floor, no door." },
  -- weapon range: artillery and the long reach
  long_arc = { label = "Long Arc", range = 1.15, fiction = "Shoots map coordinates. The targets keep being there." },
  sparkle_battery = { label = "Sparkle Battery", range = 1.15, fiction = "Confetti doctrine: the parade hits farther when she is having fun." },
  fog_invoice = { label = "Fog Invoice", range = 1.15, fiction = "Rockets from the static, paid before the target learns the sender." },
  kiln_doctrine = { label = "Kiln Doctrine", range = 1.12, fiction = "Burned his name off the hull so the enemy would learn it slow." },
  area_control = { label = "Area Control", range = 1.12, fiction = "Owns a circle of dirt. Argues with anything that crosses it." },
  ledger_reach = { label = "Ledger Reach", range = 1.12, fiction = "Writes range into the dirt." },
  sky_saint = { label = "Sky Saint", range = 1.12, fiction = "Keeps the air honest so the battery can play." },
  -- attack speed: gunships, skirmishers, snipers
  roof_brawl = { label = "Roof Brawl", reload = 0.85, fiction = "Five Roughnecks that treat the ceiling like a suggestion." },
  rotor_ducks = { label = "Rotor Ducks", reload = 0.85, fiction = "Cutlasses off the water, guns already turning." },
  ghost_shot = { label = "Ghost Shot", reload = 0.85, fiction = "Whisper is a suggestion; the shot is a fact, and the next one is sooner." },
  razorback_twins = { label = "Razorback Twins", reload = 0.85, fiction = "Two Javelins, two cockpits, one count." },
  glass_cadence = { label = "Glass Cadence", reload = 0.85, fiction = "Hits on the beat. Speed is baked into the chassis." },
  fuse = { label = "Fuse", reload = 0.85, fiction = "Burn, bail, burn again, a little faster each time." },
  -- splash: siege walkers and bombs
  house_call = { label = "House Call", splash = 1.30, fiction = "Knocks until there is no door, and the walls next to it." },
  wrecking_ball = { label = "Wrecking Ball", splash = 1.30, fiction = "Point at a wall; the wall and its neighbours reconsider." },
  hailstorm = { label = "Hailstorm", splash = 1.30, fiction = "She has never once looked at what she hits, so she hits all of it." },
  -- vision: scouts and eyes
  tick_eyes = { label = "Tick Eyes", vision = 1.20, mentor = true, fiction = "The company's eyes. Vision grows with the XP the swarm harvests." },
  wheelie_eyes = { label = "Wheelie Eyes", vision = 1.20, mentor = true, fiction = "Banks XP from every wheelie, and sees farther for it." },
  night_bay = { label = "Night Bay", vision = 1.20, mentor = true, fiction = "Dreams flight paths; wakes as a cloud of eyes." },
  veil_eyes = { label = "Veil Eyes", vision = 1.20, fiction = "Jammer haze with a radar eye: the fog works for you." },
  burn_mark = { label = "Burn Mark", vision = 1.20, fiction = "Sees by hurting. Leaves a scar on the map." },
  payroll = { label = "Payroll", vision = 1.20, fiction = "Knows who is on whose books, and where they stand." },
  -- build power
  field_surgeon = { label = "Field Surgeon", build = 1.20, fiction = "Nobody stays dead near an honest chassis." },
  combat_engineer = { label = "Combat Engineer", build = 1.20, fiction = "Builds trouble in equal measure." },
  field_office = { label = "Field Office", build = 1.20, fiction = "Armada paperwork that somehow digs trenches." },
  eco_lab = { label = "Eco Lab", build = 1.20, fiction = "Nano, sun, converter, Butlers: wind like wheat." },
  geo_tithe = { label = "Geo Tithe", build = 1.20, fiction = "Raises what the garden needs, and calls the surplus holy." },
  hive_growth = { label = "Hive Growth", build = 1.20, fiction = "Infestors mint Infestors: the garden tends itself." },
  -- speed and energy
  trapper_pace = { label = "Trapper Pace", speed = 1.12, fiction = "Pets keep up with Cinder Hook." },
  pad_heart = { label = "Pad Heart", energy = 1.35, fiction = "Hearth feeds the pad: self and sister fusions burn hotter." },
}

-- Exactly ONE field-effect tag per hero: this table is the source of truth (roster traits are
-- fiction, not mechanics). Self and pack.
M.HERO_DEFAULTS = {
  vane = { "shieldline" }, rusk = { "shieldline" }, pavise = { "pavise_ward" },
  halbard = { "stubborn" }, odessa = { "fordbreaker" }, cauter = { "riot_breaker" },
  grath = { "merc_debt" }, quill = { "parade_ground" }, nox = { "weather_tithe" },
  mask = { "believer" }, anvil = { "shell_game" },
  halq = { "long_arc" }, mira = { "sparkle_battery" }, vale = { "fog_invoice" },
  brakhov = { "kiln_doctrine" }, warder = { "area_control" }, auditor = { "ledger_reach" },
  kettle = { "sky_saint" },
  ceil = { "roof_brawl" }, gale = { "rotor_ducks" }, yeva = { "ghost_shot" },
  verse = { "razorback_twins" }, stride = { "glass_cadence" }, kit = { "fuse" },
  fatboy = { "house_call" }, bro = { "wrecking_ball" }, thresh = { "hailstorm" },
  tick = { "tick_eyes" }, spoke = { "wheelie_eyes" }, noctua = { "night_bay" },
  veil = { "veil_eyes" }, volt = { "burn_mark" }, rumor = { "payroll" },
  ketha = { "field_surgeon" }, twitch = { "combat_engineer" }, consul = { "field_office" },
  solarium = { "eco_lab" }, lumen = { "geo_tithe" }, infestor = { "hive_growth" },
  commando = { "trapper_pace" }, hearth = { "pad_heart" },
}

-- Rare dual-effect exceptions. Primary still comes from HERO_DEFAULTS;
-- these extra stats also XP-scale and push to the pack.
M.HERO_SECONDARIES = {
  -- vane captain_stride speed retired; shieldline HP is the captain mark.
}

-- Fallback mentor ids if roster Include is unavailable. Prefer roster.isMentor.
M.MENTOR_HEROES = {
  spoke = true,
  tick = true,
  noctua = true,
  consul = true,
  twitch = true,
  solarium = true,
}

function M.normalizeRank(rank)
  local r = tostring(rank or "")
  local low = string.lower(r)
  -- Legacy career rung read as wounded; keep saves/tags coherent.
  if low == "blooded" or low == "bloodied" then
    return "Proven"
  end
  if r == "" or low == "runner" or low == "green" then
    return M.DEFAULT_RANK
  end
  return r
end

local function mul(a, b)
  return (tonumber(a) or 1) * (tonumber(b) or 1)
end

local STAT_KEYS = { "hp", "speed", "range", "reload", "build", "vision", "energy", "splash" }

local function applyTagStat(out, def, allowPrimary)
  for _, stat in ipairs(STAT_KEYS) do
    local v = def[stat]
    if v and v ~= 1 then
      out[stat] = mul(out[stat], v)
      if allowPrimary and not out.primaryStat then
        out.primaryStat = stat
      elseif not allowPrimary then
        out.secondaryStats = out.secondaryStats or {}
        out.secondaryStats[stat] = true
      end
    end
  end
  if def.mentor then out.mentor = true end
end

function M.resolve(tagList)
  local out = {
    hp = 1, speed = 1, range = 1, reload = 1, build = 1, vision = 1, energy = 1, splash = 1,
    tags = {},
    labels = {},
    mentor = false,
    primaryStat = nil,
    secondaryStats = {},
  }
  if type(tagList) ~= "table" then return out end
  local seen = {}
  for i = 1, #tagList do
    local id = tostring(tagList[i] or ""):lower():gsub("%s+", "_")
    if id ~= "" and not seen[id] then
      seen[id] = true
      local def = M.TAGS[id]
      out.tags[#out.tags + 1] = id
      if def then
        out.labels[#out.labels + 1] = def.label or id
        -- First tag sets primary; later tags (e.g. Vane secondary) add extra stats.
        applyTagStat(out, def, out.primaryStat == nil)
      else
        out.labels[#out.labels + 1] = id
      end
    end
  end
  return out
end

function M.collectFromHero(h, spec, heroId)
  local list = {}
  local function push(v)
    if type(v) == "string" and v ~= "" then
      list[#list + 1] = v
    elseif type(v) == "table" then
      for _, t in ipairs(v) do
        if type(t) == "string" and t ~= "" then list[#list + 1] = t end
      end
    end
  end
  if type(h) == "table" then
    push(h.tags)
    push(h.traits)
    push(h.heroTrait)
    push(h.trait)
    push(h.fieldEffect)
  end
  if type(spec) == "table" then
    push(spec.heroTags)
    push(spec.tags)
    push(spec.traits)
    push(spec.heroTrait)
    push(spec.fieldEffect)
  end
  local id = tostring(heroId or (h and h.id) or (spec and (spec.heroId or spec.id)) or "")
  -- The hero's own tag (HERO_DEFAULTS) decides. Roster traits like "saint" or "captain" are
  -- fiction; only a word that is itself a tag id counts, and only for a hero without one.
  if id ~= "" and M.HERO_DEFAULTS[id] then
    local out = {}
    for _, tag in ipairs(M.HERO_DEFAULTS[id]) do out[#out + 1] = tag end
    for _, tag in ipairs((M.HERO_SECONDARIES and M.HERO_SECONDARIES[id]) or {}) do out[#out + 1] = tag end
    return out
  end
  local known, seen = {}, {}
  for _, tag in ipairs(list) do
    if M.TAGS[tag] and not seen[tag] then seen[tag] = true; known[#known + 1] = tag end
  end
  return known
end

function M.isMentorHero(heroId, tagList)
  local id = tostring(heroId or "")
  -- Roster is mentor SSOT when loaded (campaign / gadgets that Include it).
  if GG and GG.VA_CrewIsMentor then
    local ok, yes = pcall(GG.VA_CrewIsMentor, id)
    if ok and yes then return true end
  end
  if M.MENTOR_HEROES[id] then return true end
  local resolved = M.resolve(tagList)
  return resolved.mentor == true
end

-- XP → how much of the tag's bonus is on: nothing at no XP, all of it at FULL_XP (2.4, a hero
-- the company has carried a long way), a little more past it (×1.19 at 4.0). Saturating, φ-shaped.
M.FULL_XP = 2.4
function M.fieldXpScale(xp)
  xp = math.max(0, tonumber(xp) or 0)
  local theta = function(x) return x / (x + PHI) end
  return theta(xp) / theta(M.FULL_XP)
end

-- Compose final field mults: tag base × XP scale on primary (+ rare secondaries).
function M.composeField(resolved, xp)
  resolved = resolved or M.resolve({})
  local scale = M.fieldXpScale(xp)
  local out = {
    hp = 1, speed = 1, range = 1, reload = 1, build = 1, vision = 1, energy = 1, splash = 1,
    primaryStat = resolved.primaryStat,
    secondaryStats = {},
    tags = resolved.tags,
    labels = resolved.labels,
    mentor = resolved.mentor,
    xpScale = scale,
  }
  -- XP grows the tag's bonus, not the whole stat: Shieldline is +0% HP green, +15% at 2.4 XP.
  -- (It used to multiply the stat, ×1.52, and made reload slower with experience.)
  local function arm(stat)
    if not stat then return end
    out[stat] = 1 + ((tonumber(resolved[stat]) or 1) - 1) * scale
  end
  arm(resolved.primaryStat)
  if type(resolved.secondaryStats) == "table" then
    for stat, on in pairs(resolved.secondaryStats) do
      if on and stat ~= resolved.primaryStat then
        arm(stat)
        out.secondaryStats[stat] = true
      end
    end
  end
  return out
end

local function applyRangeMult(unitID, rangeMult)
  if not rangeMult or math.abs(rangeMult - 1) < 0.01 then return end
  local dID = Spring.GetUnitDefID(unitID)
  local ud = dID and UnitDefs[dID]
  if not ud or not ud.weapons then return end
  local maxR = 0
  for i = 1, #ud.weapons do
    -- from the weapon's own range, never the live one: a refresh must not compound
    local wd = WeaponDefs[ud.weapons[i].weaponDef]
    local cur = wd and tonumber(wd.range) or 0
    if cur and cur > 0 then
      local nr = cur * rangeMult
      pcall(Spring.SetUnitWeaponState, unitID, i, "range", nr)
      if nr > maxR then maxR = nr end
    end
  end
  if maxR > 0 and Spring.SetUnitMaxRange then
    pcall(Spring.SetUnitMaxRange, unitID, maxR)
  end
end

local function applyReloadMult(unitID, reloadMult)
  if not reloadMult or math.abs(reloadMult - 1) < 0.01 then return end
  local dID = Spring.GetUnitDefID(unitID)
  local ud = dID and UnitDefs[dID]
  if not ud or not ud.weapons then return end
  for i = 1, #ud.weapons do
    local wd = WeaponDefs[ud.weapons[i].weaponDef]
    local cur = wd and (tonumber(wd.reload) or tonumber(wd.reloadTime)) or 0
    if cur and cur > 0 then
      pcall(Spring.SetUnitWeaponState, unitID, i, "reloadTime", cur * reloadMult)
    end
  end
end

local function applyVisionMult(unitID, visionMult)
  if not visionMult or math.abs(visionMult - 1) < 0.01 then return end
  if not Spring.SetUnitSensorRadius then return end
  local dID = Spring.GetUnitDefID(unitID)
  local ud = dID and UnitDefs[dID]
  if not ud then return end
  local baseLos = tonumber(ud.sightDistance) or tonumber(ud.losRadius) or 0
  local baseAir = tonumber(ud.airSightDistance) or tonumber(ud.airLosRadius) or baseLos
  local baseRadar = tonumber(ud.radarDistance) or 0
  if baseLos > 0 then
    pcall(Spring.SetUnitSensorRadius, unitID, "los", baseLos * visionMult)
  end
  if baseAir > 0 then
    pcall(Spring.SetUnitSensorRadius, unitID, "airLos", baseAir * visionMult)
  end
  if baseRadar > 0 then
    pcall(Spring.SetUnitSensorRadius, unitID, "radar", baseRadar * visionMult)
  end
  Spring.SetUnitRulesParam(unitID, "va_field_vision_mult", visionMult, { public = true })
end

local function applySpeedMult(unitID, speedMult)
  if not speedMult or math.abs(speedMult - 1) < 0.01 then
    Spring.SetUnitRulesParam(unitID, "va_field_speed_mult", 1, { public = true })
    return
  end
  -- Field leg only — never stamp pack. Compose via shared mobility.
  if GG and GG.VA_MobilitySetField then
    pcall(GG.VA_MobilitySetField, unitID, speedMult)
    return
  end
  Spring.SetUnitRulesParam(unitID, "va_field_speed_mult", speedMult, { public = true })
  if GG and GG.VA_MobilityApply then
    pcall(GG.VA_MobilityApply, unitID)
  end
end

local function applyBuildMult(unitID, buildMult)
  if not buildMult or math.abs(buildMult - 1) < 0.01 then return end
  if not Spring.SetUnitBuildSpeed then return end
  local dID = Spring.GetUnitDefID(unitID)
  local ud = dID and UnitDefs[dID]
  local base = ud and tonumber(ud.buildSpeed) or 0
  if base <= 0 then return end
  local bp = base * buildMult
  pcall(Spring.SetUnitBuildSpeed, unitID, bp, bp, bp * 0.15, bp, bp, bp)
  Spring.SetUnitRulesParam(unitID, "va_field_build_mult", buildMult, { public = true })
end

local function applyHpMultLive(unitID, hpMult, rec)
  if not hpMult or math.abs(hpMult - 1) < 0.01 then return end
  -- HP for the named hero is folded into rec.hpMult by applyToHero.
  -- Pack mates get a lighter live bump (don't stack with campaign toughness).
  if rec and rec.unitID == unitID then return end
  if not Spring.GetUnitHealth or not Spring.SetUnitMaxHealth then return end
  local cur, maxH = Spring.GetUnitHealth(unitID)
  -- Parentheses: GetUnit* can return nothing; tonumber() with zero args aborts LuaRules.
  maxH = tonumber(maxH) or 0
  if maxH <= 0 then return end
  local stored = Spring.GetUnitRulesParam(unitID, "va_field_hp_base")
  local base = tonumber(stored) or maxH
  if stored == nil then
    Spring.SetUnitRulesParam(unitID, "va_field_hp_base", maxH, { public = true })
    base = maxH
  end
  local newMax = base * hpMult
  local frac = (maxH > 0) and ((tonumber(cur) or maxH) / maxH) or 1
  pcall(Spring.SetUnitMaxHealth, unitID, newMax)
  pcall(Spring.SetUnitHealth, unitID, newMax * frac)
  Spring.SetUnitRulesParam(unitID, "va_field_hp_mult", hpMult, { public = true })
end

function M.isFusionDef(ud)
  if not ud then return false end
  local n = string.lower(tostring(ud.name or ""))
  if n == "armfus" or n == "corfus" or n == "legfus"
      or n == "armafus" or n == "corafus" or n == "legafus" then
    return true
  end
  if n:find("fusion", 1, true) or n:find("afus", 1, true) then return true end
  -- energyMake-heavy static gens that play as pad hearts
  local make = tonumber(ud.energyMake) or 0
  if (ud.isBuilding or ud.speed == 0) and make >= 200 and n:find("fus", 1, true) then
    return true
  end
  return false
end

local function applyEnergyMult(unitID, energyMult)
  if not energyMult or math.abs(energyMult - 1) < 0.01 then return end
  local dID = Spring.GetUnitDefID(unitID)
  local ud = dID and UnitDefs[dID]
  local base = tonumber(ud and ud.energyMake) or 0
  if base <= 0 then
    -- Hero fusion / unmarked chassis: seed a pad-scale floor.
    base = 400
  end
  -- Cache UnitDef baseline once so re-applies do not compound.
  local cached = tonumber((Spring.GetUnitRulesParam(unitID, "va_field_energy_base")))
  if not cached then
    Spring.SetUnitRulesParam(unitID, "va_field_energy_base", base, { public = true })
    cached = base
  end
  local make = cached * energyMult
  if Spring.SetUnitResourcing then
    -- "ue" = unit energy make (Recoil / Spring)
    pcall(Spring.SetUnitResourcing, unitID, "ue", make)
  end
  Spring.SetUnitRulesParam(unitID, "va_field_energy_make", make, { public = true })
  Spring.SetUnitRulesParam(unitID, "va_field_energy_mult", energyMult, { public = true })
end

-- Splash: every weapon's damage and crater area, from the weapon's own values.
local function applySplashMult(unitID, splashMult)
  if not splashMult or math.abs(splashMult - 1) < 0.01 or not Spring.SetUnitWeaponDamages then return end
  local dID = Spring.GetUnitDefID(unitID)
  local ud = dID and UnitDefs[dID]
  if not ud or not ud.weapons then return end
  for i = 1, #ud.weapons do
    local wd = WeaponDefs[ud.weapons[i].weaponDef]
    local aoe = wd and tonumber(wd.damageAreaOfEffect) or 0
    if aoe > 0 then
      pcall(Spring.SetUnitWeaponDamages, unitID, i, "damageAreaOfEffect", aoe * splashMult)
      pcall(Spring.SetUnitWeaponDamages, unitID, i, "craterAreaOfEffect", (tonumber(wd.craterAreaOfEffect) or aoe) * splashMult)
    end
  end
  Spring.SetUnitRulesParam(unitID, "va_field_splash_mult", splashMult, { public = true })
end

local function applyOneStat(unitID, stat, mult, rec)
  if not stat or not mult then return end
  if stat == "range" then
    applyRangeMult(unitID, mult)
  elseif stat == "reload" then
    applyReloadMult(unitID, mult)
  elseif stat == "vision" then
    applyVisionMult(unitID, mult)
  elseif stat == "speed" then
    applySpeedMult(unitID, mult)
  elseif stat == "build" then
    applyBuildMult(unitID, mult)
  elseif stat == "hp" then
    applyHpMultLive(unitID, mult, rec)
  elseif stat == "energy" then
    applyEnergyMult(unitID, mult)
  elseif stat == "splash" then
    applySplashMult(unitID, mult)
  end
end

-- Apply composed field effect to a unit (hero or pack mate).
function M.applyFieldToUnit(unitID, field, rec)
  if not unitID or not Spring.ValidUnitID(unitID) or not field then return end
  local primary = field.primaryStat
  if not primary then return end
  applyOneStat(unitID, primary, tonumber(field[primary]) or 1, rec)
  if type(field.secondaryStats) == "table" then
    for stat, on in pairs(field.secondaryStats) do
      if on and stat ~= primary then
        applyOneStat(unitID, stat, tonumber(field[stat]) or 1, rec)
      end
    end
  end
  Spring.SetUnitRulesParam(unitID, "va_field_stat", tostring(primary), { public = true })
  Spring.SetUnitRulesParam(unitID, "va_field_mult", tonumber(field[primary]) or 1, { public = true })
  if field.secondaryStats and field.secondaryStats.speed then
    Spring.SetUnitRulesParam(unitID, "va_field_speed_mult", tonumber(field.speed) or 1, { public = true })
  end
end

-- Hearth: push energy field onto every friendly fusion (self included).
function M.applyFusionEnergyAura(heroUnitID, field, teamID)
  if not field or field.primaryStat ~= "energy" then return 0 end
  if not Spring.GetTeamUnits then return 0 end
  teamID = teamID or (heroUnitID and Spring.GetUnitTeam(heroUnitID))
  if teamID == nil then return 0 end
  local mult = tonumber(field.energy) or 1
  local n = 0
  local units = Spring.GetTeamUnits(teamID) or {}
  for i = 1, #units do
    local u = units[i]
    if Spring.ValidUnitID(u) and not Spring.GetUnitIsDead(u) then
      local dID = Spring.GetUnitDefID(u)
      local ud = dID and UnitDefs[dID]
      if M.isFusionDef(ud) or u == heroUnitID then
        applyEnergyMult(u, mult)
        n = n + 1
      end
    end
  end
  return n
end

function M.isCenturionDef(ud)
  if not ud then return false end
  local n = string.lower(tostring(ud.name or ""))
  return n == "armwar"
end

-- Pavise: HP aura for friendly Centurions (armwar), including self.
M.CENTURION_AURA_RADIUS = 520
function M.applyCenturionHpAura(heroUnitID, field, teamID)
  if not field or field.primaryStat ~= "hp" then return 0 end
  if not heroUnitID or not Spring.ValidUnitID(heroUnitID) then return 0 end
  -- Only the Pavise ward tag owns this aura (avoid every HP-tag hero radiating).
  local tags = field.tags or {}
  local hasWard = false
  for i = 1, #tags do
    if tostring(tags[i]) == "pavise_ward" then hasWard = true break end
  end
  if not hasWard then return 0 end
  teamID = teamID or Spring.GetUnitTeam(heroUnitID)
  if teamID == nil then return 0 end
  local hx, _, hz = Spring.GetUnitPosition(heroUnitID)
  if not hx then return 0 end
  local mult = tonumber(field.hp) or 1
  local r2 = (M.CENTURION_AURA_RADIUS or 520) ^ 2
  local n = 0
  local units = Spring.GetTeamUnits(teamID) or {}
  for i = 1, #units do
    local u = units[i]
    if Spring.ValidUnitID(u) and not Spring.GetUnitIsDead(u) then
      local dID = Spring.GetUnitDefID(u)
      local ud = dID and UnitDefs[dID]
      if M.isCenturionDef(ud) or u == heroUnitID then
        local ux, _, uz = Spring.GetUnitPosition(u)
        if ux then
          local dx, dz = ux - hx, uz - hz
          if (dx * dx + dz * dz) <= r2 then
            -- Self already gets field HP via applyToHero → rec.hpMult; live bump is for other Centurions.
            if u ~= heroUnitID then
              applyHpMultLive(u, mult, nil)
            end
            Spring.SetUnitRulesParam(u, "va_pavise_aura", 1, { public = true })
            n = n + 1
          end
        end
      end
    end
  end
  return n
end

-- Fold resolved tags into hero record + apply live unit mutations.
-- Uses baseHpMult / baseBuildPowerMult so rez / re-register does not stack.
-- Only the primary field-effect stat is mechanical; XP scales that slot.
function M.applyToHero(unitID, rec, tagList, xp)
  local resolved = M.resolve(tagList)
  local field = M.composeField(resolved, xp or (rec and rec.peakXp) or 0)
  rec = rec or {}
  if rec.baseHpMult == nil then
    rec.baseHpMult = tonumber(rec.hpMult) or 1.0
  end
  if rec.baseBuildPowerMult == nil then
    rec.baseBuildPowerMult = tonumber(rec.buildPowerMult) or 1.0
  end
  -- Hero personal toughness: only fold HP/build when that IS the field effect.
  if field.primaryStat == "hp" then
    rec.hpMult = mul(rec.baseHpMult, field.hp)
  else
    rec.hpMult = rec.baseHpMult
  end
  if field.primaryStat == "build" then
    rec.buildPowerMult = mul(rec.baseBuildPowerMult, field.build)
  else
    rec.buildPowerMult = rec.baseBuildPowerMult
  end
  rec.tagSpeedMult = ((field.primaryStat == "speed") or (field.secondaryStats and field.secondaryStats.speed))
    and field.speed or 1
  rec.tagRangeMult = (field.primaryStat == "range") and field.range or 1
  rec.tagReloadMult = (field.primaryStat == "reload") and field.reload or 1
  rec.tagVisionMult = (field.primaryStat == "vision") and field.vision or 1
  rec.tagEnergyMult = (field.primaryStat == "energy") and field.energy or 1
  rec.tagSplashMult = (field.primaryStat == "splash") and field.splash or 1
  rec.fieldStat = field.primaryStat
  rec.fieldMult = field.primaryStat and field[field.primaryStat] or 1
  rec.tags = field.tags
  rec.tagLabels = field.labels
  rec.mentor = field.mentor == true or M.MENTOR_HEROES[tostring(rec.id or "")] == true
  rec.field = field

  if unitID and Spring.ValidUnitID(unitID) then
    Spring.SetUnitRulesParam(unitID, "va_hero_tags", table.concat(field.tags or {}, ","), { public = true })
    Spring.SetUnitRulesParam(unitID, "va_hero_tag_labels", table.concat(field.labels or {}, " · "), { public = true })
    Spring.SetUnitRulesParam(unitID, "va_field_stat", tostring(field.primaryStat or ""), { public = true })
    Spring.SetUnitRulesParam(unitID, "va_field_mult", tonumber(rec.fieldMult) or 1, { public = true })
    Spring.SetUnitRulesParam(unitID, "va_field_xp_scale", field.xpScale or 1, { public = true })
    M.applyFieldToUnit(unitID, field, rec)
    -- Hearth: sister fusions share the energy burn.
    if field.primaryStat == "energy" then
      local hit = M.applyFusionEnergyAura(unitID, field, Spring.GetUnitTeam(unitID))
      Spring.Echo("VA_HEARTH_FUSION_AURA units=" .. tostring(hit)
        .. " mult=" .. tostring(field.energy))
    end
    -- Pavise: Centurion HP ward (self + nearby armwar).
    if field.primaryStat == "hp" then
      local hit = M.applyCenturionHpAura(unitID, field, Spring.GetUnitTeam(unitID))
      if hit and hit > 0 then
        Spring.Echo("VA_PAVISE_CENTURION_AURA units=" .. tostring(hit)
          .. " mult=" .. tostring(field.hp))
      end
    end
  end
  return field
end

return M
