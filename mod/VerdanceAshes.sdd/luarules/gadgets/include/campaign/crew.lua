-- campaign/crew.lua: the company on the field: roster, hero packs, bonds, crew confirm, the hot drop
-- Part of game_verdance_campaign.lua, loaded into that gadget's environment
-- (VFS.Include with the gadget table), so its globals are the gadget's globals.
-- Provides: VA_CREW_SELECT, VA_CREW_confirm, VA_CREW_isAnchorKeep, VA_CREW_isCommerceKitSpec,
-- VA_CREW_loadRoster, VA_CREW_publish, VA_CREW_spawnHeroPack, VA_HOT, VA_HOT_drop,
-- VA_refreshPlayerStorageCaps
-- Uses: hero_spawn, heroes, spawn, start, state

-- Muster the Band: packed table (Lua 5.1 local budget). Fresh chapter only.
VA_CREW_SELECT = {
  pending = false,
  confirmed = false,
  selected = {},
  wallet = 5,
  spent = 0,
  anchorX = nil,
  anchorZ = nil,
  roster = nil,
}
-- Hot drop (tools/verdance_kernel/hot_drop.py): the kernel launched before the player chose who
-- goes. The company waits off the field; the drop names the packs and the reserve that board.
VA_HOT = {
  token = nil,     -- mission.hotDrop.token; a drop must carry it
  pending = false, -- loaded and waiting for the drop
  reserve = {},    -- reserve specs held back: { spec, teamID, baseX, baseZ, groupX, groupZ, force }
}

-- Muster the Band helpers (globals — keep main-chunk locals free).
function VA_CREW_loadRoster()
  if VA_CREW_SELECT.roster then return VA_CREW_SELECT.roster end
  local ok, mod = pcall(VFS.Include, "luarules/gadgets/include/va_crew_roster.lua")
  if not ok or type(mod) ~= "table" then
    ok, mod = pcall(VFS.Include, "LuaRules/gadgets/include/va_crew_roster.lua")
  end
  if ok and type(mod) == "table" then
    VA_CREW_SELECT.roster = mod
    VA_CREW_SELECT.wallet = tonumber(mod.START_WALLET_TNB) or 5
  else
    Spring.Echo("VA_CREW_ROSTER_MISSING")
    VA_CREW_SELECT.roster = { CORE = { "vane", "ketha" }, HEROES = {}, BAND_ORDER = {}, SEAT_CAP = 3,
      START_WALLET_TNB = 5, defaultAutoPick = function() return {} end, get = function() return nil end,
      isCore = function() return false end, hireCost = function() return 1 end, hireKmCost = function() return 0 end,
      isMentor = function() return false end, MENTOR_PRODUCTS = {} }
  end
  GG = GG or {}
  GG.VA_CrewIsMentor = function(heroId)
    local r = VA_CREW_SELECT.roster
    return r and r.isMentor and r.isMentor(heroId) or false
  end
  -- Cortex packs spend km$ (1km$ = 1000 metal). Prefer mission commerce bag.
  local com = mission and mission.commerce
  local km = com and tonumber(com.metalK)
  VA_CREW_SELECT.walletKm = (km ~= nil) and math.max(0, math.floor(km)) or 7
  return VA_CREW_SELECT.roster
end

-- Eco / support defs that still drop with the hub crew kit (not replaced by heroes).
-- Mex + storage + nano matter for Consul / Twitcher dig-in sorties.
local VA_CREW_ANCHOR_KEEP = {
  legmex = true, armmex = true, cormex = true,
  legwin = true, legsolar = true, armsolar = true, corsolar = true,
  legrad = true, armrad = true, corrad = true,
  legestor = true, legmstor = true, armestor = true, armmstor = true, corestor = true, cormstor = true,
  legck = true, legcv = true, legca = true, corck = true, armck = true,
  legnanotc = true, armnanotc = true, cornanotc = true,
}

function VA_CREW_isAnchorKeep(spec)
  if not spec then return false end
  if spec.heroId or spec.hero then return false end -- heroes wait for muster
  local defName = tostring(spec.unitDefName or spec.def or spec[1] or "")
  if VA_CREW_ANCHOR_KEEP[defName] then return true end
  if spec.atMetalSpots or spec.nearestMetalSpots then return true end
  -- Generic rez still allowed as a spare until Ketha drops (no hero tag).
  if defName == "legrezbot" then return true end
  return false
end

-- Bought broker kit (punch / fabs / constructors / nanos from mission.commerce.deploy).
-- RULE (one owner): VA_LOGISTICS.spawnCommerceDeployKit spawns the commerce deploy
-- bag at GameStart, straight from mission.commerce.deploy. The layout force in
-- playableSetup may still carry copies of those items (scripts/build_next_mission_v1.ps1
-- Add-CommerceDeployToKit composes them into the player kit for previews); the setup
-- spawn must skip every one of them or the kit lands twice. The PS1 stamps each such
-- spec with commerceDeploy=true and a packageTag; the tag heuristics below cover
-- seeds built before the stamp existed.
function VA_CREW_isCommerceKitSpec(spec)
  if not spec then return false end
  if spec.commerceDeploy == true or spec.commerceDeploy == 1 then return true end
  if spec.unitPrinter == true or spec.unitPrinter == 1 then return true end
  local tag = tostring(spec.packageTag or "")
  if tag == "" then return false end
  if tag:match("^pad_") or tag:match("^crew_") then return false end
  return true
end

-- BAR Team Resourcing (layer 1) SetTeamResource(ms/es) on GameStart wipes the
-- engine sum of storage buildings. Recompute from live player units and restore
-- caps; optionally top up commerce bag metal/energy if an earlier clip ate it.
function VA_refreshPlayerStorageCaps(reason)
  if playerTeamID == nil then return false end
  local unitMs, unitEs = 0, 0
  local units = Spring.GetTeamUnits(playerTeamID) or {}
  for i = 1, #units do
    local uid = units[i]
    if Spring.ValidUnitID(uid) and not Spring.GetUnitIsDead(uid) then
      local defID = Spring.GetUnitDefID(uid)
      local ud = defID and UnitDefs[defID]
      if ud then
        unitMs = unitMs + (tonumber(ud.metalStorage) or 0)
        unitEs = unitEs + (tonumber(ud.energyStorage) or 0)
      end
    end
  end
  local wantM = tonumber(VA_CREW_SELECT and VA_CREW_SELECT.wantMetal) or 0
  local wantE = tonumber(VA_CREW_SELECT and VA_CREW_SELECT.wantEnergy) or 0
  -- Cap = building/com sum (BAR floor 1000). Commerce bag may temporarily lift
  -- the floor so the km$ dump is not clipped before storages finish applying.
  local ms = math.max(1000, unitMs)
  local es = math.max(1000, unitEs)
  if wantM > ms then ms = wantM + 500 end
  if wantE > es then es = wantE + 500 end
  pcall(Spring.SetTeamResource, playerTeamID, "ms", ms)
  pcall(Spring.SetTeamResource, playerTeamID, "es", es)
  local mCur = select(1, Spring.GetTeamResources(playerTeamID, "metal")) or 0
  local eCur = select(1, Spring.GetTeamResources(playerTeamID, "energy")) or 0
  if wantM > 0 and mCur + 1 < wantM then
    pcall(Spring.AddTeamResource, playerTeamID, "metal", wantM - mCur)
  end
  if wantE > 0 and eCur + 1 < wantE then
    pcall(Spring.AddTeamResource, playerTeamID, "energy", wantE - eCur)
  end
  local mNow, mStor = Spring.GetTeamResources(playerTeamID, "metal")
  local eNow, eStor = Spring.GetTeamResources(playerTeamID, "energy")
  Spring.Echo("VA_STORAGE_REFRESH reason=" .. tostring(reason or "")
    .. " ms=" .. tostring(math.floor(tonumber(mStor) or 0))
    .. " es=" .. tostring(math.floor(tonumber(eStor) or 0))
    .. " metal=" .. tostring(math.floor(tonumber(mNow) or 0))
    .. " energy=" .. tostring(math.floor(tonumber(eNow) or 0))
    .. " fromUnits_m=" .. tostring(math.floor(unitMs))
    .. " fromUnits_e=" .. tostring(math.floor(unitEs)))
  return true
end

function VA_CREW_publish()
  local cs = VA_CREW_SELECT
  Spring.SetGameRulesParam("va_crew_pending", cs.pending and 1 or 0, { public = true })
  Spring.SetGameRulesParam("va_crew_ready", cs.confirmed and 1 or 0, { public = true })
  Spring.SetGameRulesParam("va_crew_wallet", tonumber(cs.wallet) or 0, { public = true })
  Spring.SetGameRulesParam("va_crew_wallet_km", tonumber(cs.walletKm) or 0, { public = true })
  Spring.SetGameRulesParam("va_crew_spent", tonumber(cs.spent) or 0, { public = true })
  local parts = {}
  for i = 1, #(cs.selected or {}) do
    parts[#parts + 1] = tostring(cs.selected[i])
  end
  Spring.SetGameRulesParam("va_crew_selected", table.concat(parts, ","), { public = true })
end

-- Who of the company is on this field (va_dropped_heroes, a rules param so it outlives a LuaRules
-- reload): the exfil manifest carries it, and a hero who dropped but is neither going nor staying
-- at extraction did not survive (verdance.campaign.roster).
VA_DROPPED = VA_DROPPED or {}
function vaNoteDropped(heroId)
  heroId = tostring(heroId or "")
  if heroId == "" then return end
  for _, h in ipairs(VA_DROPPED) do if h == heroId then return end end
  local prior = tostring(Spring.GetGameRulesParam("va_dropped_heroes") or "")
  if #VA_DROPPED == 0 and prior ~= "" then
    for h in prior:gmatch("[^,]+") do VA_DROPPED[#VA_DROPPED + 1] = h end
    for _, h in ipairs(VA_DROPPED) do if h == heroId then return end end
  end
  VA_DROPPED[#VA_DROPPED + 1] = heroId
  Spring.SetGameRulesParam("va_dropped_heroes", table.concat(VA_DROPPED, ","), { public = true })
end

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

function VA_CREW_confirm(selectedIds)
  local cs = VA_CREW_SELECT
  if cs.confirmed then
    Spring.Echo("VA_CREW_ALREADY_CONFIRMED")
    return false
  end
  local roster = VA_CREW_loadRoster()
  local seatCap = tonumber(roster.SEAT_CAP) or 3
  -- The hub sheet already chose who ships. Seat cap is the first-run
  -- formation pick, not a second clip that drops the fourth pack.
  local fromSheet = (mission and type(mission.crewBand) == "table")
    or (mission and type(mission.deployAces) == "table")
  local cap = fromSheet and 64 or seatCap
  local picks = {}
  local spent = 0
  local spentKm = 0
  for _, id in ipairs(selectedIds or {}) do
    id = tostring(id or "")
    if id ~= "" and not (roster.isCore and roster.isCore(id)) then
      local cost = (roster.hireCost and roster.hireCost(id)) or 0
      local costKm = (roster.hireKmCost and roster.hireKmCost(id)) or 0
      if #picks < cap then
        picks[#picks + 1] = id
        spent = spent + cost
        spentKm = spentKm + costKm
      end
    end
  end
  local wallet = tonumber(cs.wallet) or (roster.START_WALLET_TNB or 5)
  local walletKm = tonumber(cs.walletKm) or 7
  -- Formation Tnb was paid on the hub. Do not refuse the sheet over the
  -- sortie fab wallet.
  if not fromSheet and spent > wallet then
    Spring.Echo("VA_CREW_OVERBUDGET spent=" .. tostring(spent) .. " wallet=" .. tostring(wallet))
    return false
  end
  if not fromSheet and spentKm > walletKm then
    Spring.Echo("VA_CREW_OVERBUDGET_KM spent=" .. tostring(spentKm) .. " walletKm=" .. tostring(walletKm))
    return false
  end
  local baseX = cs.anchorX or ((Game.mapSizeX or 0) * 0.23)
  local baseZ = cs.anchorZ or ((Game.mapSizeZ or 0) * 0.24)
  local total = 0
  -- Core always, while they live: mission.heroes names the living (dead heroes are not on it)
  local living = nil
  if mission and type(mission.heroes) == "table" and #mission.heroes > 0 then
    living = {}
    for _, mh in ipairs(mission.heroes) do living[tostring(mh.id or mh.heroId or "")] = true end
  end
  local core = {}
  for _, id in ipairs(roster.CORE or { "vane", "ketha" }) do
    if not living or living[tostring(id)] then core[#core + 1] = id
    else Spring.Echo("VA_CREW_CORE_FALLEN " .. tostring(id)) end
  end
  for ci, id in ipairs(core) do
    total = total + VA_CREW_spawnHeroPack(id, baseX, baseZ, (ci - 1) * 200)
  end
  for i, id in ipairs(picks) do
    total = total + VA_CREW_spawnHeroPack(id, baseX, baseZ, 400 + (i - 1) * 220)
  end
  do
    local present = {}
    for _, id in ipairs(core) do present[#present + 1] = id end
    for _, id in ipairs(picks) do present[#present + 1] = id end
    total = total + VA_BOND_apply(present, baseX, baseZ, 400 + #picks * 220)
  end
  -- No free pad M/E storage — Solarium (and bought eco) own that seat.
  cs.selected = picks
  cs.spent = spent
  cs.wallet = wallet - spent
  cs.walletKm = walletKm - spentKm
  cs.confirmed = true
  cs.pending = false
  -- Formation hireTnb / hireKm is paid at the hub (commerce bag). The sortie
  -- Tnb bank is the fab stake for this Drop — never debit it again here.
  Spring.Echo("VA_CREW_HIRE_HUB_PAID spentTnb=" .. tostring(spent)
    .. " spentKm=" .. tostring(spentKm)
    .. " sortieBank=" .. tostring(tenebLoot and tenebLoot.bank or "?"))
  VA_CREW_publish()
  if SendToUnsynced then
    SendToUnsynced("VERDANCE_BEAT", "bark", "Ketha", "Band sealed. Drop them.", 6)
    SendToUnsynced("VERDANCE_BEAT", "crew_ready", table.concat(picks, ","), tostring(spent), tostring(cs.wallet), "")
  end
  Spring.Echo("VA_CREW_CONFIRMED picks=" .. table.concat(picks, ",")
    .. " spentTnb=" .. tostring(spent) .. " spentKm=" .. tostring(spentKm)
    .. " units=" .. tostring(total))
  -- Solarium (and any storage escorts) just landed — restore caps now and
  -- again on frames 1–3 in case BAR Team Resourcing still races us.
  cs.storageRefreshUntil = math.max(tonumber(cs.storageRefreshUntil) or 0, 3)
  VA_refreshPlayerStorageCaps("crew_confirm")
  return true
end

-- The drop: the packs and reserve the player chose on the hub, into the field that is
-- already loaded. Message: "vahotdrop token|pack,pack|unitdef:n,unitdef:n".
function VA_HOT_drop(line)
  if not VA_HOT.pending then
    Spring.Echo("VA_HOTDROP_IGNORED not_pending")
    return false
  end
  local token, packs, units = tostring(line or ""):match("^([^|]*)|([^|]*)|?(.*)$")
  if token ~= VA_HOT.token then
    Spring.Echo("VA_HOTDROP_IGNORED stale_token " .. tostring(token))
    return false
  end
  local picks = {}
  for id in string.gmatch(packs or "", "[%w_]+") do picks[#picks + 1] = id end
  local want = {}
  for def, n in string.gmatch(units or "", "([%w_]+):(%d+)") do want[def] = (want[def] or 0) + tonumber(n) end
  local landed = 0
  for _, held in ipairs(VA_HOT.reserve) do
    local def = tostring(held.spec.unitDefName or "")
    local n = math.min(want[def] or 0, tonumber(held.spec.count) or 1)
    if n > 0 then
      local spec = {}
      for k, v in pairs(held.spec) do spec[k] = v end
      spec.count = n
      want[def] = want[def] - n
      landed = landed + spawnUnitSpec(spec, held.teamID, held.baseX, held.baseZ, held.groupX, held.groupZ, {}, held.force)
    end
  end
  VA_HOT.pending = false
  VA_CREW_confirm(picks)
  sweepPlayerCommanders("hotdrop")
  Spring.SetGameRulesParam("va_hotdrop_pending", 0, { public = true })
  Spring.Echo("VA_HOTDROP_DONE packs=" .. table.concat(picks, ",") .. " reserve=" .. tostring(landed))
  return true
end
