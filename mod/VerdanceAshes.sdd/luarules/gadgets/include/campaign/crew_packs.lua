-- campaign/crew_packs.lua: a hero's pack on the field (VA_CREW_spawnHeroPack) and the bonds between heroes who drop together
-- Part of game_verdance_campaign.lua, loaded into that gadget's environment
-- (VFS.Include with the gadget table), so its globals are the gadget's globals.
-- Provides: VA_BOND_apply, VA_CREW_spawnHeroPack
-- Uses: crew, hero_spawn, heroes, spawn, state

function VA_CREW_spawnHeroPack(heroId, baseX, baseZ, dx0, heroOnly)
  local roster = VA_CREW_loadRoster()
  local h = roster.get and roster.get(heroId) or (roster.HEROES and roster.HEROES[heroId])
  if not h then
    Spring.Echo("VA_CREW_UNKNOWN_HERO " .. tostring(heroId))
    return 0
  end
  if h.deprecated == true or (roster.isDeprecated and roster.isDeprecated(heroId)) then
    Spring.Echo("VA_CREW_SKIP_DEPRECATED " .. tostring(heroId))
    return 0
  end
  local defName = tostring(h.unitDef or "legcen")
  if not UnitDefNames or not UnitDefNames[defName] then
    Spring.Echo("VA_CREW_MISSING_DEF " .. defName .. " hero=" .. tostring(heroId))
    return 0
  end
  local spawned = 0
  local dx = tonumber(dx0) or 0
  -- Named hero
  local heroSpec = {
    unitDefName = defName,
    count = 1,
    dx = dx,
    dz = 40,
    spacing = 100,
    heroId = tostring(heroId),
    heroName = tostring(h.fieldName or h.name or heroId),
    -- you (the first company pick, mission.you) are mission-critical, like Ketha
    missionCritical = h.missionCritical == true or (mission ~= nil and tostring(mission.you or "") == tostring(heroId)),
    heroTrait = h.heroTrait,
    heroTags = h.tags or h.traits,
    packageTag = "crew_" .. tostring(heroId),
  }
  -- Pull XP/level from mission.heroes if present; else roster startXp (explicit 0 is green).
  -- Named heroes are flat 2× HP (VA_HERO_HP_MULT); the field effect may add to it.
  heroSpec.heroHpMult = VA_HERO_HP_MULT or 2.0
  if mission and type(mission.heroes) == "table" then
    for _, mh in ipairs(mission.heroes) do
      if mh and tostring(mh.id or mh.heroId) == tostring(heroId) then
        heroSpec.heroXp = mh.xp
        heroSpec.heroLevel = mh.level
        heroSpec.heroRank = mh.rank
        heroSpec.heroCampaignXp = mh.campaignXp
        if mh.trait then heroSpec.heroTrait = mh.trait end
        break
      end
    end
  end
  -- Starting XP: prefer authored startXp (power-inverse curve). Mission carry only
  -- wins when it is a real banked floor above the green seed.
  local greenXp = tonumber(h.startXp)
  if greenXp == nil then greenXp = 0 end
  local carried = tonumber(heroSpec.heroXp)
  if carried == nil or carried <= greenXp then
    heroSpec.heroXp = greenXp
  end
  local formation = tostring(h.formation or "")
  local triSpan = 120
  if formation == "triangle" then
    -- Tip of the triangle = named hero.
    heroSpec.dx = dx
    heroSpec.dz = 80
  end
  spawned = spawned + spawnUnitSpec(heroSpec, playerTeamID, baseX, baseZ, 0, 0, {}, { role = "player_crew" })
  if spawned > 0 then vaNoteDropped(heroId) end
  if heroOnly then return spawned end   -- a person left in the field: their pack went home
  -- Pack / escort XP floor: majority of the hero's banked XP (or cadreXp for def).
  local heroXpFloor = tonumber(heroSpec.heroXp) or 0
  local function cadreXpFor(def)
    if mission and type(mission.cadreXp) == "table" then
      local bag = mission.cadreXp[def]
      if type(bag) == "table" then
        return tonumber(bag.xp or bag.avgXp or bag.peakXp) or 0
      elseif type(bag) == "number" then
        return bag
      end
    end
    return 0
  end
  local function packXpFor(def)
    local fromCadre = cadreXpFor(def)
    local fromHero = heroXpFloor * 0.85
    if fromCadre > 0 and fromHero > 0 then return math.max(fromCadre, fromHero * 0.75) end
    if fromCadre > 0 then return fromCadre end
    return fromHero
  end
  local function packCraftFor(def)
    if mission and type(mission.cadreXp) == "table" then
      local bag = mission.cadreXp[def]
      if type(bag) == "table" then
        return tonumber(bag.craftXp or bag.avgCraftXp or bag.peakCraftXp) or 0
      end
    end
    return 0
  end
  local extras = tonumber(h.extras) or 0
  -- A pair (Verse & Adder, Anvil & Mire): each partner is a named hero too, as tough as the lead,
  -- with the pack's field effect. The campaign keeps one record for the pair (the lead's id).
  for pi, pname in ipairs(h.partners or {}) do
    if extras <= 0 then break end
    local pSpec = {}
    for k, v in pairs(heroSpec) do pSpec[k] = v end
    pSpec.heroId = tostring(heroId) .. "#" .. tostring(pi)
    pSpec.heroName = tostring(pname)
    pSpec.missionCritical = false
    pSpec.dx = dx + 110 * pi
    pSpec.packageTag = "crew_pack_" .. tostring(heroId)
    spawned = spawned + spawnUnitSpec(pSpec, playerTeamID, baseX, baseZ, 0, 0, {}, { role = "player_crew" })
    extras = extras - 1
  end
  if extras > 0 then
    if formation == "triangle" then
      -- Base corners of the triangle (hero is the tip).
      local corners = {
        { dx - triSpan, 80 + triSpan },
        { dx + triSpan, 80 + triSpan },
      }
      local placed = 0
      for ci = 1, math.min(extras, #corners) do
        local off = corners[ci]
        local mateSpec = {
          unitDefName = defName,
          count = 1,
          dx = off[1],
          dz = off[2],
          spacing = 95,
          packageTag = "crew_pack_" .. tostring(heroId),
          xp = packXpFor(defName),
          craftXp = packCraftFor(defName),
        }
        spawned = spawned + spawnUnitSpec(mateSpec, playerTeamID, baseX, baseZ, 0, 0, {}, { role = "player_crew" })
        placed = placed + 1
      end
      local remain = extras - placed
      if remain > 0 then
        local packSpec = {
          unitDefName = defName,
          count = remain,
          dx = dx,
          dz = 80 + triSpan * 2,
          spacing = 95,
          formation = "triangle",
          packageTag = "crew_pack_" .. tostring(heroId),
          xp = packXpFor(defName),
          craftXp = packCraftFor(defName),
        }
        spawned = spawned + spawnUnitSpec(packSpec, playerTeamID, baseX, baseZ, 0, 0, {}, { role = "player_crew" })
      end
    else
      local packSpec = {
        unitDefName = defName,
        count = extras,
        dx = dx,
        dz = 140,
        spacing = 95,
        packageTag = "crew_pack_" .. tostring(heroId),
        xp = packXpFor(defName),
        craftXp = packCraftFor(defName),
      }
      spawned = spawned + spawnUnitSpec(packSpec, playerTeamID, baseX, baseZ, 0, 0, {}, { role = "player_crew" })
    end
  end
  -- Mixed escorts (Whisper spies, Veil radar/mines, Warder LLT ring, etc.)
  local escorts = h.escorts
  if type(escorts) == "table" then
    local escortDz = (formation == "triangle") and (80 + triSpan + 40) or 140
    for ei, esc in ipairs(escorts) do
      if type(esc) == "table" then
        local escDef = tostring(esc.unitDef or esc.unitDefName or "")
        local escCount = tonumber(esc.count or 0) or 0
        if escDef ~= "" and escCount > 0 and UnitDefNames and UnitDefNames[escDef] then
          escortDz = escortDz + 90
          local escSpec = {
            unitDefName = escDef,
            count = escCount,
            dx = dx + (ei - 1) * 40,
            dz = escortDz,
            spacing = 85,
            xp = packXpFor(escDef),
            packageTag = "crew_escort_" .. tostring(heroId) .. "_" .. tostring(ei),
          }
          -- Perimeter turrets / AA: ring around the beamer triangle.
          if formation == "triangle"
              and (escDef == "armllt" or escDef == "corrl" or escDef == "armrl")
              and escCount >= 3 then
            escSpec.formation = "ring"
            -- Thistles sit a bit farther out than LLTs.
            local rad = (escDef == "armllt") and 150 or 200
            escSpec.spacing = rad
            escSpec.dx = dx
            escSpec.dz = 80 + math.floor(triSpan * 0.5)
          end
          spawned = spawned + spawnUnitSpec(escSpec, playerTeamID, baseX, baseZ, 0, 0, {}, { role = "player_crew" })
        else
          Spring.Echo("VA_CREW_ESCORT_SKIP hero=" .. tostring(heroId) .. " def=" .. escDef)
        end
      end
    end
  end
  -- Factory / mint (scout seats: Spoke legvp, Tick armlab, Noctua hero-is-bay)
  if h.factory and roster.FACTORIES then
    local fab = roster.FACTORIES[h.factory]
    local fabDef = fab and tostring(fab.structureDef or "") or ""
    if fab and fabDef ~= "" and UnitDefNames and UnitDefNames[fabDef] then
      local fabSpec = {
        unitDefName = fabDef,
        count = 1,
        dx = dx + 180,
        dz = -80,
        spacing = 120,
        packageTag = "crew_escort_" .. tostring(heroId) .. "_factory",
      }
      if fab.product then
        fabSpec.unitPrinter = true
        fabSpec.printerProduct = fab.product
        fabSpec.printerMetalIncome = 6
        fabSpec.printerEnergyIncome = 40
      end
      local nFab = spawnUnitSpec(fabSpec, playerTeamID, baseX, baseZ, 0, 0, {}, { role = "player_crew" })
      spawned = spawned + nFab
      Spring.Echo("VA_CREW_FACTORY hero=" .. tostring(heroId)
        .. " fab=" .. tostring(h.factory) .. " def=" .. fabDef
        .. " spawned=" .. tostring(nFab)
        .. " product=" .. tostring(fab.product or ""))
    elseif fab and (fabDef == "" or fabDef == "nil") then
      -- Hero-is-the-bay (Noctua legap): stamp the named hero unit as the printer.
      -- (enableFieldFactoryPrinter is a later local — inline the stamp here.)
      local rec = heroes[tostring(heroId)]
      local heroUID = rec and rec.unitID
      if heroUID and Spring.ValidUnitID(heroUID) then
        Spring.SetUnitRulesParam(heroUID, "va_field_factory_for", tostring(heroId), { public = true })
        Spring.SetUnitRulesParam(heroUID, "va_force_role", "field_factory", { public = true })
        if fab.product then
          local product = tostring(fab.product)
          Spring.SetUnitRulesParam(heroUID, "va_unit_printer", 1, { public = true })
          Spring.SetUnitRulesParam(heroUID, "va_printer_product", product, { public = true })
          if Spring.EditUnitCmdDesc and Spring.GetUnitCmdDescs and Spring.RemoveUnitCmdDesc then
            local descs = Spring.GetUnitCmdDescs(heroUID) or {}
            for i = #descs, 1, -1 do
              local c = descs[i]
              if c and c.id and c.id < 0 then
                local bud = UnitDefs[-c.id]
                if not bud or bud.name ~= product then
                  pcall(Spring.RemoveUnitCmdDesc, heroUID, i)
                end
              end
            end
          end
          printerUnits = printerUnits or {}
          printerUnits[heroUID] = { metal = 6 / 30, energy = 40 / 30, team = playerTeamID }
          -- The scout paradigm (owner, 2026-10-28): the bay lands already printing, on repeat.
          local pdef = UnitDefNames and UnitDefNames[product]
          if pdef then
            pcall(Spring.GiveOrderToUnit, heroUID, CMD.REPEAT, { 1 }, 0)
            for _ = 1, math.max(1, tonumber(fab.repeatQueue) or 4) do
              pcall(Spring.GiveOrderToUnit, heroUID, -pdef.id, {}, 0)
            end
          end
        end
        -- ...and with an extra thousand metal in the storage that came with it. Before the
        -- commerce allotment lands it rides on it (so the storage refresh keeps it); after a hot
        -- drop it is added straight away.
        local bonus = tonumber(fab.startMetal) or 0
        if bonus > 0 then
          if VA_COMMERCE_APPLIED then
            pcall(Spring.AddTeamResource, playerTeamID, "metal", bonus)
          else
            VA_SCOUT_BONUS_METAL = (VA_SCOUT_BONUS_METAL or 0) + bonus
          end
        end
        Spring.Echo("VA_CREW_FACTORY_HERO_IS_BAY hero=" .. tostring(heroId)
          .. " fab=" .. tostring(h.factory) .. " unit=" .. tostring(heroUID)
          .. " product=" .. tostring(fab.product or ""))
      else
        Spring.Echo("VA_CREW_FACTORY_SKIP hero=" .. tostring(heroId)
          .. " fab=" .. tostring(h.factory) .. " reason=hero_bay_no_unit")
      end
    else
      Spring.Echo("VA_CREW_FACTORY_SKIP hero=" .. tostring(heroId)
        .. " fab=" .. tostring(h.factory) .. " def=" .. fabDef
        .. " reason=missing_structureDef_or_unitdef")
    end
    local mint = h.factoryMint
    if mint and mint.unitDef and tonumber(mint.seedCount or 0) > 0 then
      local mintSpec = {
        unitDefName = tostring(mint.unitDef),
        count = tonumber(mint.seedCount) or 0,
        dx = dx + 80,
        dz = 220,
        spacing = 70,
        packageTag = "crew_mint_" .. tostring(heroId),
      }
      spawned = spawned + spawnUnitSpec(mintSpec, playerTeamID, baseX, baseZ, 0, 0, {}, { role = "player_crew" })
    end
  end
  -- Mechanical pack overlay (speed share + stamps) — not tag-driven.
  do
    local rec = heroes[tostring(heroId)]
    local heroUID = rec and rec.unitID
    if heroUID and Spring.ValidUnitID(heroUID) and GG and GG.VA_PackOverlayRefresh then
      local n = GG.VA_PackOverlayRefresh(heroUID, heroId)
      Spring.Echo("VA_PACK_OVERLAY_POST_SPAWN hero=" .. tostring(heroId)
        .. " mates_sped=" .. tostring(n or 0))
    end
  end
  Spring.Echo("VA_CREW_SPAWN hero=" .. tostring(heroId) .. " units=" .. tostring(spawned))
  return spawned
end

-- Bonds worth something on the field (verdance.company.synergy, on the mission): rank-B XP and a
-- rank-A pair's gift, a unit neither pack already has. A row counts only when both heroes of the
-- pair are on this drop.
function VA_BOND_apply(present, baseX, baseZ, dx0)
  local here = {}
  for _, id in ipairs(present or {}) do here[tostring(id)] = true end
  for _, row in ipairs((mission and mission.bondXp) or {}) do
    if here[tostring(row.a)] and here[tostring(row.b)] then
      for _, hid in ipairs({ tostring(row.a), tostring(row.b) }) do
        local uid = heroes[hid] and heroes[hid].unitID
        if uid and Spring.ValidUnitID(uid) and Spring.GetUnitExperience and Spring.SetUnitExperience then
          Spring.SetUnitExperience(uid, (Spring.GetUnitExperience(uid) or 0) + (tonumber(row.xp) or 0))
        end
      end
      Spring.Echo("VA_BOND_XP pair=" .. tostring(row.a) .. "__" .. tostring(row.b) .. " rank=" .. tostring(row.rank) .. " xp=" .. tostring(row.xp))
    end
  end
  local spawned = 0
  for gi, g in ipairs((mission and mission.bondGifts) or {}) do
    local def = tostring(g.unitDef or "")
    if here[tostring(g.a)] and here[tostring(g.b)] and def ~= "" and UnitDefNames and UnitDefNames[def] then
      spawned = spawned + spawnUnitSpec({ unitDefName = def, count = tonumber(g.count) or 1, dx = (dx0 or 0) + (gi - 1) * 160,
        dz = 260, spacing = 90, packageTag = "bond_gift_" .. tostring(g.a) .. "__" .. tostring(g.b) },
        playerTeamID, baseX, baseZ, 0, 0, {}, { role = "player_crew" })
      Spring.Echo("VA_BOND_GIFT pair=" .. tostring(g.a) .. "__" .. tostring(g.b) .. " def=" .. def .. " n=" .. tostring(g.count))
    end
  end
  return spawned
end
