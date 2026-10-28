-- campaign/hero_spawn.lua: a hero's unit on the field: modifiers, tags, registration
-- Part of game_verdance_campaign.lua, loaded into that gadget's environment
-- (VFS.Include with the gadget table), so its globals are the gadget's globals.
-- Provides: HeroTags, VA_HERO_HP_MULT, applyHeroModifiers, registerHeroSpawn
-- Uses: crew, heroes, mentors, mission_data, units

-- Procedural hero tags (Runner = speed perk, not a career rank).
HeroTags = nil
do
  local ok, mod = pcall(VFS.Include, "luarules/gadgets/include/va_hero_tags.lua")
  if not ok or type(mod) ~= "table" then
    ok, mod = pcall(VFS.Include, "LuaRules/gadgets/include/va_hero_tags.lua")
  end
  if ok and type(mod) == "table" then
    HeroTags = mod
    Spring.Echo("VA_HERO_TAGS_LOADED tags=" .. tostring(mod.TAGS and (function()
      local n = 0; for _ in pairs(mod.TAGS) do n = n + 1 end; return n
    end)() or 0))
  else
    Spring.Echo("VA_HERO_TAGS_MISSING")
    HeroTags = {
      DEFAULT_RANK = "Green",
      normalizeRank = function(r)
        r = tostring(r or "")
        if r == "" or r == "Runner" then return "Green" end
        return r
      end,
      collectFromHero = function() return {} end,
      applyToHero = function() return { tags = {}, labels = {} } end,
    }
  end
end

-- Named heroes are flat-tough: 2× stock HP before field-effect folds (owner call, 2026-10-24;
-- was 3×). Level, wounds and the campaign's own hpMult no longer move it.
VA_HERO_HP_MULT = 2.0

-- Spring GetUnitRulesParam can return *no value*; tonumber() with zero args
-- aborts LuaRules (LUA_ERRRUN). Never pass a bare Get* into tonumber().
local function rulesNum(unitID, key)
  local v = Spring.GetUnitRulesParam(unitID, key)
  if v == nil then return nil end
  return tonumber(v)
end

function applyHeroModifiers(unitID, rec)
  local hpMult = tonumber(rec.hpMult) or VA_HERO_HP_MULT or 2.0
  if Spring.GetUnitHealth and Spring.SetUnitMaxHealth and Spring.GetUnitDefID then
    local cur, maxH = Spring.GetUnitHealth(unitID)
    if maxH ~= nil then maxH = tonumber(maxH) end
    maxH = maxH or 0
    if cur ~= nil then cur = tonumber(cur) end
    local dID = Spring.GetUnitDefID(unitID)
    local ud = dID and UnitDefs[dID]
    local stock = 0
    if ud then
      local h = ud.health or ud.maxDamage
      if h ~= nil then stock = tonumber(h) or 0 end
    end
    local stored = rulesNum(unitID, "va_hero_hp_base")
    local base = stored or ((stock > 0) and stock) or maxH
    if stored == nil and base > 0 then
      Spring.SetUnitRulesParam(unitID, "va_hero_hp_base", base, { public = true })
    end
    if base > 0 then
      local newMax = base * hpMult
      local frac = (maxH > 0) and (((cur or maxH) / maxH)) or 1
      pcall(Spring.SetUnitMaxHealth, unitID, newMax)
      pcall(Spring.SetUnitHealth, unitID, newMax * frac)
    end
  end
  Spring.SetUnitRulesParam(unitID, "va_hero_hp_mult", hpMult, { public = true })
  -- Ketha is a field rez-bot, not a passive marker. BAR exposes the synced
  -- build-speed mutator on supported Spring/Recoil builds; keep the rules
  -- param as a readable compatibility view for older clients.
  local bpMult = tonumber(rec.buildPowerMult) or 1.0
  Spring.SetUnitRulesParam(unitID, "va_hero_build_power_mult", bpMult, { public = true })
  if bpMult > 1.0 and Spring.SetUnitBuildSpeed and Spring.GetUnitDefID then
    local defID = Spring.GetUnitDefID(unitID)
    local ud = defID and UnitDefs[defID]
    local base = ud and tonumber(ud.buildSpeed)
    if base and base > 0 then
      local ok = pcall(Spring.SetUnitBuildSpeed, unitID, base * bpMult)
      if ok then
        Spring.Echo("VA_HERO_BUILDPOWER id=" .. tostring(rec.id)
          .. " mult=" .. tostring(bpMult) .. " base=" .. tostring(base))
      end
    end
  end
  -- Re-baseline quantum veterancy AFTER campaign toughness so HP layers stack cleanly.
  if GG and GG.VA_VetRebaseline then
    pcall(GG.VA_VetRebaseline, unitID)
  elseif GG and GG.VA_VetRefresh then
    pcall(GG.VA_VetRefresh, unitID)
  end
end

function registerHeroSpawn(unitID, spec)
  local id = tostring(spec.heroId or "hero")
  local rec = heroes[id]
  -- Explicit 0 must stick (Lua `0 or 0.25` is wrong). Green default = 0.
  local seedXp = tonumber(spec.heroXp)
  if seedXp == nil then seedXp = 0 end
  local seedLevel = tonumber(spec.heroLevel) or 1
  local seedRank = HeroTags.normalizeRank(spec.heroRank or HeroTags.DEFAULT_RANK or "Green")
  if not rec then
    rec = {
      id = id,
      name = tostring(spec.heroName or id),
      unitDefName = tostring(spec.unitDefName or spec.def or ""),
      missionCritical = spec.missionCritical == true,
      hpMult = VA_HERO_HP_MULT,
      baseHpMult = VA_HERO_HP_MULT,
      buildPowerMult = tonumber(spec.heroBuildPowerMult) or 1.0,
      state = "alive",
      everDown = false,
      lastXp = seedXp,
      peakXp = seedXp,
      level = seedLevel,
      rank = seedRank,
      trait = tostring(spec.heroTrait or ""),
    }
    heroes[id] = rec
  else
    -- Keep the higher of carried peak and seed (campaign ladder floor).
    rec.peakXp = math.max(tonumber(rec.peakXp) or 0, tonumber(rec.lastXp) or 0, seedXp)
    rec.lastXp = rec.peakXp
    rec.level = seedLevel
    rec.rank = seedRank
    -- Flat 2× toughness for every named hero (the field effect may add to it).
    rec.baseHpMult = VA_HERO_HP_MULT
    rec.hpMult = VA_HERO_HP_MULT
    if tonumber(spec.heroBuildPowerMult) then rec.buildPowerMult = tonumber(spec.heroBuildPowerMult) end
    if spec.heroTrait then rec.trait = tostring(spec.heroTrait) end
  end
  if rec.baseHpMult == nil then
    rec.baseHpMult = tonumber(rec.hpMult) or VA_HERO_HP_MULT or 2.0
  end
  if (tonumber(rec.baseHpMult) or 0) ~= VA_HERO_HP_MULT then
    rec.baseHpMult = VA_HERO_HP_MULT
    rec.hpMult = rec.baseHpMult
  end
  rec.unitID = unitID
  if (not rec.unitDefName or rec.unitDefName == "") and Spring.GetUnitDefID then
    local dID = Spring.GetUnitDefID(unitID)
    local ud = dID and UnitDefs[dID]
    if ud and ud.name then rec.unitDefName = ud.name end
  end
  -- One field-effect stat per hero; XP (incl. mentor bank) scales that slot only.
  -- pcall: a tag/MoveCtrl fault must not abort GameStart mid-crew spawn.
  do
    local okField, errField = pcall(function()
      local roster = VA_CREW_loadRoster and VA_CREW_loadRoster() or nil
      -- a pair's partner ("verse#1") carries its lead's field effect
      local base = tostring(id):match("^[^#]+") or tostring(id)
      if base ~= tostring(id) then Spring.SetUnitRulesParam(unitID, "va_partner_of", base, { public = true }) end
      local h = roster and ((roster.get and roster.get(base)) or (roster.HEROES and roster.HEROES[base])) or nil
      local tagList = HeroTags.collectFromHero(h, spec, base)
      local field = HeroTags.applyToHero(unitID, rec, tagList, rec.peakXp or seedXp)
      if field and field.tags and #field.tags > 0 then
        Spring.Echo("VA_HERO_FIELD id=" .. id
          .. " stat=" .. tostring(field.primaryStat or "?")
          .. " mult=" .. tostring(field.primaryStat and field[field.primaryStat] or 1)
          .. " tags=" .. table.concat(field.tags, ",")
          .. " xpScale=" .. tostring(field.xpScale or 1))
      end
      if heroIsPackMentor(id, spec, tagList) then
        registerPackMentor(id, rec, rec.peakXp or seedXp)
        Spring.SetUnitRulesParam(unitID, "va_pack_mentor", 1, { public = true })
        Spring.SetUnitRulesParam(unitID, "va_pack_leader", id, { public = true })
        Spring.SetUnitRulesParam(unitID, "va_pack_id", id, { public = true })
        Spring.SetUnitRulesParam(unitID, "va_pack_role", "lead", { public = true })
        if id == "spoke" then
          Spring.SetUnitRulesParam(unitID, "va_wheelie_mentor", 1, { public = true })
        end
      end
    end)
    if not okField then
      Spring.Echo("VA_HERO_FIELD_FAIL id=" .. tostring(id) .. " err=" .. tostring(errField))
    end
  end
  if spec.recruitable == true or spec.recruitable == 1 or spec.va_recruitable == 1 then
    rec.recruitable = true
    rec.recruitMode = tostring(spec.recruitMode or "wreck_rez")
  end
  heroByUnitID[unitID] = id
  Spring.SetUnitRulesParam(unitID, "va_hero", 1, { public = true })
  Spring.SetUnitRulesParam(unitID, "va_hero_id", id, { public = true })
  Spring.SetUnitRulesParam(unitID, "va_hero_name", rec.name, { public = true })
  Spring.SetUnitRulesParam(unitID, "va_hero_critical", rec.missionCritical and 1 or 0, { public = true })
  Spring.SetUnitRulesParam(unitID, "va_hero_level", rec.level or 1, { public = true })
  Spring.SetUnitRulesParam(unitID, "va_hero_rank", rec.rank or "Green", { public = true })
  Spring.SetUnitRulesParam(unitID, "va_hero_xp", rec.peakXp or 0, { public = true })
  stampPadToothIfNeeded(unitID, id)
  if rec.recruitable then
    Spring.SetUnitRulesParam(unitID, "va_recruitable", 1, { public = true })
    Spring.SetUnitRulesParam(unitID, "va_recruit_mode", rec.recruitMode or "wreck_rez", { public = true })
    Spring.SetUnitRulesParam(unitID, "va_force_role", "recruitable", { public = true })
  end
  do
    local okMod, errMod = pcall(applyHeroModifiers, unitID, rec)
    if not okMod then
      Spring.Echo("VA_HERO_MOD_FAIL id=" .. tostring(id) .. " err=" .. tostring(errMod))
    end
  end
  if Spring.SetUnitExperience then pcall(Spring.SetUnitExperience, unitID, rec.peakXp or seedXp) end
  -- Seed XP is applied after toughness; refresh so early HP/RoF match the floor.
  if GG and GG.VA_VetRefresh then
    pcall(GG.VA_VetRefresh, unitID)
  end
  publishHeroRules()
  Spring.Echo("VA_HERO_SPAWNED id=" .. id .. " unit=" .. tostring(unitID)
    .. " def=" .. tostring(rec.unitDefName)
    .. " critical=" .. tostring(rec.missionCritical)
    .. " xp=" .. tostring(rec.peakXp)
    .. " hpMult=" .. tostring(rec.hpMult or VA_HERO_HP_MULT)
    .. " L" .. tostring(rec.level or 1)
    .. " " .. tostring(rec.rank or ""))
end
