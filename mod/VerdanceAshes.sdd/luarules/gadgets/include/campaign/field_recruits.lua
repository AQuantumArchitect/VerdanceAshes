-- campaign/field_recruits.lua: wild heroes: recruit wrecks, field factories, who waits where
-- Part of game_verdance_campaign.lua, loaded into that gadget's environment
-- (VFS.Include with the gadget table), so its globals are the gadget's globals.
-- Provides: VA_FIELD_RECRUIT, VA_FIELD_spawnRecruits, claimFieldFactoriesForHero,
-- enableFieldFactoryPrinter, tickFieldRecruitPendingDeath
-- Uses: crew, hero_spawn, heroes, mission_data, reinforcements, spawn, state, units

-- Field recruits: wild heroes seeded on this map; wreck+rez joins the company.
VA_FIELD_RECRUIT = {
  spawned = {},   -- heroId -> true
  recruited = {}, -- ordered list of heroIds rezzed this sortie
  pendingDeath = {}, -- unitIDs to quiet-kill next frame (engine leaves rez corpse)
  fabByUnit = {}, -- unitID -> heroId (factory seed awaiting wreck / capture)
  fabByFeature = {}, -- featureID -> heroId (Legion bay wreck awaiting rez)
}

-- Contracted rescue vs opportunistic join. One rule: optionalJoin = free
-- pickup; everything else is the sortie contract (destroy → fail → EXTRACT).
local function fieldRecruitIsSortieLinked(fr)
  if type(fr) ~= "table" then return false end
  if fr.optionalJoin == true or fr.optionalJoin == 1 then return false end
  return true
end

-- Seed a field recruit as a *normal* BAR wreck: birth a real unit, then kill it
-- so the engine leaves a resurrectable corpse. Hand-placed CreateFeature wrecks
-- are not rez-linked (Fatboy Contract failed this way) — stay on stock BAR rules.
-- Building chassis (geo/fusion/nano/airpad) often fail Gaia CreateUnit; the bake
-- may stamp wreckUnitDef as a mobile proxy while unitDefName stays the hero.
local function spawnFieldRecruitWreck(fr, x, z)
  local hid = tostring(fr.heroId)
  local heroDef = tostring(fr.unitDefName or fr.unitDef or "legcen")
  local seedDef = tostring(fr.wreckUnitDef or heroDef)
  if not UnitDefNames or not UnitDefNames[seedDef] then
    if seedDef ~= heroDef and UnitDefNames and UnitDefNames[heroDef] then
      seedDef = heroDef
    else
      Spring.Echo("VA_FIELD_RECRUIT_WRECK_FAIL id=" .. hid .. " def=" .. seedDef .. " missing_unitdef")
      return false
    end
  end
  local gaia = (Spring.GetGaiaTeamID and Spring.GetGaiaTeamID()) or 0
  -- Ground the hero can be raised on and walk (or drive) away from: a bay where a bay fits.
  local unitID, sx, sz = nil, x, z
  local padX, padZ = tonumber((Spring.GetGameRulesParam("va_pad_x"))), tonumber((Spring.GetGameRulesParam("va_pad_z")))
  local gx, gz = vaStandable(seedDef, x, z, 0, (padX or -1) >= 0 and padX or nil, (padZ or -1) >= 0 and padZ or nil)
  if gx then sx, sz = gx, gz end
  unitID = Spring.CreateUnit(seedDef, sx, Spring.GetGroundHeight(sx, sz) or 0, sz, 0, gaia)
  if not unitID then
    Spring.Echo("VA_FIELD_RECRUIT_WRECK_FAIL id=" .. hid .. " def=" .. seedDef
      .. " heroDef=" .. heroDef .. " create_unit")
    return false
  end
  local seedXp = tonumber(fr.heroXp)
  if seedXp == nil then seedXp = 0 end
  local rec = heroes[hid]
  if not rec then
    rec = {
      id = hid,
      name = tostring(fr.heroName or fr.name or hid),
      unitDefName = heroDef,
      missionCritical = false,
      hpMult = VA_HERO_HP_MULT,
      baseHpMult = VA_HERO_HP_MULT,
      buildPowerMult = 1.0,
      state = "alive",
      everDown = false,
      lastXp = seedXp,
      peakXp = seedXp,
      level = tonumber(fr.heroLevel) or 1,
      rank = HeroTags.normalizeRank(fr.heroRank or "Green"),
      trait = "",
    }
    heroes[hid] = rec
  else
    rec.unitDefName = heroDef
    rec.peakXp = math.max(tonumber(rec.peakXp) or 0, seedXp)
    rec.lastXp = rec.peakXp
  end
  -- Remember proxy seed so post-rez promote can swap to the real chassis.
  if seedDef ~= heroDef then
    rec.wreckSeedDef = seedDef
    rec.needsChassisPromote = true
  end
  rec.unitID = unitID
  rec.deathX, rec.deathZ = sx, sz
  rec.wasFieldRecruit = true
  rec.recruitable = true
  rec.recruitMode = tostring(fr.recruitMode or "wreck_rez")
  rec.beliefScore = tonumber(fr.beliefScore) or 0
  rec.optionalJoin = (fr.optionalJoin == true or fr.optionalJoin == 1)
  rec.zoneId = tostring(fr.zoneId or "")
  rec.sortieLinked = fieldRecruitIsSortieLinked(fr)
  heroByUnitID[unitID] = hid
  Spring.SetUnitRulesParam(unitID, "va_hero", 1, { public = true })
  Spring.SetUnitRulesParam(unitID, "va_hero_id", hid, { public = true })
  Spring.SetUnitRulesParam(unitID, "va_hero_name", rec.name, { public = true })
  stampPadToothIfNeeded(unitID, hid)
  Spring.SetUnitRulesParam(unitID, "va_recruitable", 1, { public = true })
  Spring.SetUnitRulesParam(unitID, "va_recruit_mode", rec.recruitMode, { public = true })
  Spring.SetUnitRulesParam(unitID, "va_field_recruit", 1, { public = true })
  Spring.SetUnitRulesParam(unitID, "va_sortie_linked", rec.sortieLinked and 1 or 0, { public = true })
  if seedDef ~= heroDef then
    Spring.SetUnitRulesParam(unitID, "va_wreck_seed_def", seedDef, { public = true })
    Spring.SetUnitRulesParam(unitID, "va_hero_chassis", heroDef, { public = true })
  end
  if Spring.SetUnitExperience and seedXp > 0 then
    pcall(Spring.SetUnitExperience, unitID, seedXp)
  end
  -- Quiet kill next frame → UnitDestroyed → FeatureCreated with sourceID →
  -- stock BAR resurrectable wreck → registerHeroDownObjective (same surface
  -- as any mid-fight company hero death).
  VA_FIELD_RECRUIT.pendingDeath[#VA_FIELD_RECRUIT.pendingDeath + 1] = unitID
  Spring.Echo("VA_FIELD_RECRUIT_WRECK_SEED id=" .. hid .. " def=" .. seedDef
    .. (seedDef ~= heroDef and (" proxyFor=" .. heroDef) or "")
    .. " unit=" .. tostring(unitID) .. " belief=" .. tostring(rec.beliefScore)
    .. " linked=" .. tostring(rec.sortieLinked and 1 or 0)
    .. " @ " .. tostring(sx) .. "," .. tostring(sz))
  return true
end

function tickFieldRecruitPendingDeath(frame)
  local list = VA_FIELD_RECRUIT.pendingDeath
  if not list or #list == 0 then return end
  if frame < 1 then return end
  for i = 1, #list do
    local uid = list[i]
    if uid and Spring.ValidUnitID(uid) and not Spring.GetUnitIsDead(uid) then
      -- false, false = not self-D, not reclaimed → engine leaves normal corpse.
      Spring.DestroyUnit(uid, false, false)
    end
  end
  VA_FIELD_RECRUIT.pendingDeath = {}
end

-- Factory heroes: Tick's Armada bay is a live opponent (capture). Legion bays
-- (Spoke wheelie lab, Kettle nano, …) seed as engine wrecks (rez). Stock BAR.
function enableFieldFactoryPrinter(unitID, heroId)
  if not unitID or not Spring.ValidUnitID(unitID) then return false end
  local roster = VA_CREW_loadRoster()
  local h = roster.get and roster.get(heroId) or (roster.HEROES and roster.HEROES[heroId])
  local fab = h and h.factory and roster.FACTORIES and roster.FACTORIES[h.factory]
  if not fab then return false end
  Spring.SetUnitRulesParam(unitID, "va_field_factory_for", tostring(heroId), { public = true })
  Spring.SetUnitRulesParam(unitID, "va_force_role", "field_factory", { public = true })
  if fab.product then
    local product = tostring(fab.product)
    Spring.SetUnitRulesParam(unitID, "va_unit_printer", 1, { public = true })
    Spring.SetUnitRulesParam(unitID, "va_printer_product", product, { public = true })
    if Spring.EditUnitCmdDesc and Spring.GetUnitCmdDescs and Spring.RemoveUnitCmdDesc then
      local descs = Spring.GetUnitCmdDescs(unitID) or {}
      for i = #descs, 1, -1 do
        local c = descs[i]
        if c and c.id and c.id < 0 then
          local bud = UnitDefs[-c.id]
          if not bud or bud.name ~= product then
            pcall(Spring.RemoveUnitCmdDesc, unitID, i)
          end
        end
      end
    end
    printerUnits = printerUnits or {}
    printerUnits[unitID] = { metal = 6 / 30, energy = 40 / 30, team = playerTeamID }
    Spring.Echo("VA_FIELD_FACTORY_PRINTER hero=" .. tostring(heroId)
      .. " unit=" .. tostring(unitID) .. " product=" .. product)
  end
  return true
end

local function stampPendingRecruitAsFieldFactory(hid, fab)
  -- Hero-is-the-bay (Noctua): the wreck/live recruit unit *is* the factory.
  hid = tostring(hid or "")
  local stamped = 0
  local pending = VA_FIELD_RECRUIT.pendingDeath or {}
  for i = 1, #pending do
    local uid = pending[i]
    if uid and Spring.ValidUnitID(uid) and not Spring.GetUnitIsDead(uid) then
      local rid = Spring.GetUnitRulesParam(uid, "va_hero_id")
      if tostring(rid or "") == hid then
        Spring.SetUnitRulesParam(uid, "va_field_factory_for", hid, { public = true })
        Spring.SetUnitRulesParam(uid, "va_force_role", "field_factory", { public = true })
        VA_FIELD_RECRUIT.fabByUnit[uid] = hid
        stamped = stamped + 1
        Spring.Echo("VA_FIELD_FACTORY_HERO_IS_BAY hero=" .. hid
          .. " unit=" .. tostring(uid)
          .. " product=" .. tostring((fab and fab.product) or "")
          .. " (pending wreck)")
      end
    end
  end
  local rec = heroes[hid]
  if stamped == 0 and rec and rec.unitID and Spring.ValidUnitID(rec.unitID) then
    Spring.SetUnitRulesParam(rec.unitID, "va_field_factory_for", hid, { public = true })
    Spring.SetUnitRulesParam(rec.unitID, "va_force_role", "field_factory", { public = true })
    VA_FIELD_RECRUIT.fabByUnit[rec.unitID] = hid
    stamped = 1
    Spring.Echo("VA_FIELD_FACTORY_HERO_IS_BAY hero=" .. hid
      .. " unit=" .. tostring(rec.unitID)
      .. " product=" .. tostring((fab and fab.product) or "")
      .. " (live recruit)")
  end
  return stamped
end

local function spawnFieldRecruitFactory(fr, x, z, teamID)
  local hid = tostring(fr.heroId)
  local roster = VA_CREW_loadRoster()
  local h = roster.get and roster.get(hid) or (roster.HEROES and roster.HEROES[hid])
  if not h or not h.factory or not roster.FACTORIES then
    Spring.Echo("VA_FIELD_FACTORY_SKIP hero=" .. hid .. " reason=no_factory_on_hero")
    return 0
  end
  local fab = roster.FACTORIES[h.factory]
  local defName = fab and tostring(fab.structureDef or "") or ""
  if defName == "" or defName == "nil" or not UnitDefNames or not UnitDefNames[defName] then
    -- Noctua / hero-is-bay: stamp the recruit chassis itself.
    local n = stampPendingRecruitAsFieldFactory(hid, fab)
    if n <= 0 then
      Spring.Echo("VA_FIELD_FACTORY_SKIP hero=" .. hid
        .. " fab=" .. tostring(h.factory)
        .. " reason=hero_bay_unstamped def=" .. defName)
    end
    return n
  end
  local fx, fz = x + 140, z - 60
  local y = (Spring.GetGroundHeight and Spring.GetGroundHeight(fx, fz)) or 0
  local spawnTeam = tonumber(teamID) or (Spring.GetGaiaTeamID and Spring.GetGaiaTeamID()) or 0
  -- Legion chassis → wreck (rez). Armada / other → live opponent (capture).
  local asWreck = (defName:sub(1, 3) == "leg")
  local unitID = Spring.CreateUnit(defName, fx, y, fz, 0, spawnTeam)
  if not unitID then
    Spring.Echo("VA_FIELD_FACTORY_FAIL hero=" .. hid .. " def=" .. defName)
    return 0
  end
  Spring.SetUnitRulesParam(unitID, "va_playable_proxy", 1, { public = true })
  Spring.SetUnitRulesParam(unitID, "va_field_factory_for", hid, { public = true })
  Spring.SetUnitRulesParam(unitID, "va_force_role", "field_factory", { public = true })
  Spring.SetUnitRulesParam(unitID, "va_recruitable", 1, { public = true })
  VA_FIELD_RECRUIT.fabByUnit[unitID] = hid
  local label = tostring((fab and fab.label) or defName)
  if asWreck then
    -- Quiet-kill next frame → normal BAR resurrectable wreck.
    -- Map markers: unsynced objectives owns world paint (no synced MarkerAddPoint).
    VA_FIELD_RECRUIT.pendingDeath[#VA_FIELD_RECRUIT.pendingDeath + 1] = unitID
    Spring.Echo("VA_FIELD_FACTORY_WRECK_SEED hero=" .. hid .. " def=" .. defName
      .. " unit=" .. tostring(unitID) .. " label=" .. label)
  else
    -- Live enemy building — capture with stock BAR.
    Spring.Echo("VA_FIELD_FACTORY_OPPONENT hero=" .. hid .. " def=" .. defName
      .. " unit=" .. tostring(unitID) .. " team=" .. tostring(spawnTeam)
      .. " label=" .. label)
  end
  return 1
end

function claimFieldFactoriesForHero(heroId, aroundX, aroundZ)
  heroId = tostring(heroId or "")
  if heroId == "" then return 0 end
  local claimed = 0
  local units = Spring.GetAllUnits() or {}
  for i = 1, #units do
    local uid = units[i]
    if Spring.ValidUnitID(uid) and not Spring.GetUnitIsDead(uid) then
      local forHero = Spring.GetUnitRulesParam(uid, "va_field_factory_for")
      if tostring(forHero or "") == heroId then
        local team = Spring.GetUnitTeam(uid)
        if team ~= playerTeamID and Spring.TransferUnit then
          pcall(Spring.TransferUnit, uid, playerTeamID, false)
        end
        enableFieldFactoryPrinter(uid, heroId)
        claimed = claimed + 1
      end
    end
  end
  if claimed > 0 then
    Spring.Echo("VA_FIELD_FACTORY_CLAIMED hero=" .. heroId .. " count=" .. tostring(claimed))
  end
  return claimed
end

function VA_FIELD_spawnRecruits(enemyTeam)
  local list = mission and mission.fieldRecruits
  if type(list) ~= "table" or #list == 0 then
    Spring.Echo("VA_FIELD_RECRUIT none")
    return 0
  end
  local teamID = tonumber(enemyTeam) or tonumber(objectiveTeamID)
  if not teamID then
    -- Fall back to any non-player team from playable setup.
    for _, force in ipairs((mission.playableSetup and mission.playableSetup.forces) or {}) do
      local tid = tonumber(force.teamID or -1)
      if tid and tid ~= playerTeamID then
        teamID = tid
        break
      end
    end
  end
  if not teamID then
    Spring.Echo("VA_FIELD_RECRUIT no enemy team")
    return 0
  end
  -- Belief-field order: marked / high-score pads spawn first so Fatboy on the
  -- clicked plateau is never dropped behind ambient wild fills.
  local ranked = {}
  for i, fr in ipairs(list) do
    if type(fr) == "table" and fr.heroId then
      ranked[#ranked + 1] = { i = i, fr = fr, belief = tonumber(fr.beliefScore) or 0 }
    end
  end
  table.sort(ranked, function(a, b)
    if a.belief ~= b.belief then return a.belief > b.belief end
    return a.i < b.i
  end)
  local targetZone = tostring((mission.objective and mission.objective.targetZoneId) or "")
  local spawned = 0
  for ri, row in ipairs(ranked) do
    local fr = row.fr
    local hid = tostring(fr.heroId)
    if not VA_FIELD_RECRUIT.spawned[hid] and not heroes[hid] then
      local defName = tostring(fr.unitDefName or fr.unitDef or "legcen")
      local x = normalizedToElmos(tonumber(fr.x) or 0.55, Game.mapSizeX or 0)
      local z = normalizedToElmos(tonumber(fr.z) or 0.55, Game.mapSizeZ or 0)
      -- Nudge each recruit so they do not stack.
      x = x + (ri - 1) * 90
      z = z + (ri - 1) * 40
      local mode = tostring(fr.recruitMode or "wreck_rez")
      local asWreck = (fr.spawnAsWreck == true or fr.spawnAsWreck == 1
        or mode == "wreck_rez" or mode == "retrieve_stash")
      -- Attention collapse: target-zone wrecks get a clearer salvage marker.
      local onTarget = targetZone ~= "" and tostring(fr.zoneId or "") == targetZone
      local ok = false
      if asWreck then
        ok = spawnFieldRecruitWreck(fr, x, z)
        -- If corpse defs are missing, fall through to a live seed rather than lose the recruit.
        if not ok then
          Spring.Echo("VA_FIELD_RECRUIT_WRECK_FALLBACK id=" .. hid)
          asWreck = false
        end
      end
      if not asWreck then
        local spec = {
          unitDefName = defName,
          count = 1,
          dx = 0,
          dz = 0,
          spacing = 80,
          heroId = hid,
          heroName = tostring(fr.heroName or fr.name or hid),
          heroHpMult = VA_HERO_HP_MULT,
          heroXp = tonumber(fr.heroXp) or 0,
          recruitable = true,
          recruitMode = mode,
          missionCritical = false,
        }
        local n = spawnUnitSpec(spec, teamID, x, z, 0, 0, {}, { role = "recruitable", id = "field_recruit_" .. hid })
        ok = n > 0
        if ok then
          local rec = heroes[hid]
          local linked = fieldRecruitIsSortieLinked(fr)
          if rec then
            rec.wasFieldRecruit = true
            rec.recruitable = true
            rec.beliefScore = tonumber(fr.beliefScore) or 0
            rec.optionalJoin = (fr.optionalJoin == true or fr.optionalJoin == 1)
            rec.zoneId = tostring(fr.zoneId or "")
            rec.sortieLinked = linked
            if rec.unitID and Spring.ValidUnitID(rec.unitID) then
              Spring.SetUnitRulesParam(rec.unitID, "va_sortie_linked", linked and 1 or 0, { public = true })
            end
          end
          -- Map markers owned by unsynced objectives (va_sec* / scout), not synced.
          Spring.Echo("VA_FIELD_RECRUIT_SPAWN id=" .. hid .. " def=" .. defName
            .. " team=" .. tostring(teamID) .. " belief=" .. tostring(fr.beliefScore or 0)
            .. " linked=" .. tostring(linked and 1 or 0)
            .. (onTarget and " targetPad=1" or "")
            .. " @ " .. tostring(x) .. "," .. tostring(z))
        else
          Spring.Echo("VA_FIELD_RECRUIT_FAIL id=" .. hid .. " def=" .. defName)
        end
      end
      if ok then
        spawned = spawned + 1
        VA_FIELD_RECRUIT.spawned[hid] = true
        -- Tick (Armada) bay = live opponent (capture). Legion bays = wrecks (rez).
        spawnFieldRecruitFactory(fr, x, z, teamID)
      end
    end
  end
  Spring.Echo("VA_FIELD_RECRUIT spawned=" .. tostring(spawned))
  return spawned
end
