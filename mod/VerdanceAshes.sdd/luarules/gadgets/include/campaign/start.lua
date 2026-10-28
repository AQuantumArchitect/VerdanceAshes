-- campaign/start.lua: start of the sortie: doctrine, commanders, perks, start resources, Tenebrium
-- Part of game_verdance_campaign.lua, loaded into that gadget's environment
-- (VFS.Include with the gadget table), so its globals are the gadget's globals.
-- Provides: VA_FIELD_spawnPeople, applyCommanderPerks, applyCommerceStartResources,
-- applyFirstDropEcoSoftener, configureDoctrine, doctrine, isCommanderUnitDef,
-- playerCommanderDestroyed, playerCommanders, publishObjectiveMarker, sweepPlayerCommanders,
-- tenebLoot, tickCommanderSweeps, tickTenebrium, trackPlayerCommanderCreated, vaApplyWarBanks
-- Uses: crew, crew_packs, crew_storage, mission_data, objectives, state, terminal

playerCommanders = {}             -- unitID -> true

-- Raid / Arc A tactics doctrine: no player commander. Sweep engine free coms;
-- static_bases also sweeps enemy free commanders (prevents commander soup).
doctrine = {
  strikeTeam = false,
  commanderSwept = false,
  sweepEnemy = false,
  enemySwept = false,
  hotExtractOnly = false,
  playerComsAllowed = 0,
  sawPlayerCom = false,
  actNumber = 0, -- story label only; Tnb and build power are the only fabrication gate
}

-- WO-043c: Tenebrium is a full in-mission resource (not engine metal).
-- • Every unit with build power costs ≥1 Tnb to finish; that stake lives on the unit.
-- • Wrecks / heaps / debris keep the stake until reclaimed (→ bank) or truly gone (→ lost).
-- • Bank: infinite storage, display-only number (GameRulesParam va_tenebrium_bank).
-- • Q7 (resource scarcity) reads this stock. Armada crisis: faction bank locked at 0
--   (they spent it on a continent of farming decoy coms for wind/solar/converters).
tenebLoot = {
  bank = 0,                  -- player team liquid Tenebrium (infinite cap)
  looted = 0,                -- lifetime reclaimed this sortie (result field)
  spent = 0,                 -- spent on builds this sortie
  lost = 0,                  -- destroyed wrecks without reclaim
  amountPerDecoy = 1,
  metalBonus = 45,
  pending = {},              -- deadUnitID -> { x,y,z, frame, amount }
  byFeature = {},            -- featureID -> { amount, amountRemaining, looted }
  byUnit = {},               -- unitID -> invested amount
  heapTransfer = {},         -- "x|z" -> amount (wreck→heap same frame)
  heapTransferFrame = -1,
  events = {},
  claimEvents = {},          -- must exist before first reclaim (tryLoot appends)
  teamBanks = {},
  wrecksCreated = 0,
  wrecksClaimed = 0,
  wrecksLost = 0,
  pendingLoss = {},
  armadaCrisis = true,       -- default on: Armada has no Tnb
  factionBank = { armada = 0, cortex = 0 },
  enabled = true,
}

-- What a commander is: include/va_commanders.lua, shared by every Verdance gadget.
VA_COM = VFS.Include("luarules/gadgets/include/va_commanders.lua")
function isCommanderUnitDef(ud)
  return VA_COM.isCommander(ud)
end

-- WO-043c handlers: physical split (include/va_tenebrium_handlers.lua).
-- IIFE so pack/ok/err locals stay nested (main-chunk 200-local budget).
(function()
  local pack = { ok = false, attach = nil, err = nil }
  pack.ok, pack.attach = pcall(VFS.Include, "luarules/gadgets/include/va_tenebrium_handlers.lua")
  if not pack.ok then
    Spring.Echo("VA_TENEBRIUM_HANDLERS_INCLUDE_FAIL " .. tostring(pack.attach))
    return
  end
  pack.ok, pack.err = pcall(pack.attach, tenebLoot, {
    jnum = jnum,
    jstr = jstr,
    teamFaction = teamFaction,
    SendToUnsynced = SendToUnsynced,
    playerTeamID = function() return playerTeamID end,
    playerAllyTeamID = function() return playerAllyTeamID end,
    mission = function() return mission end,
    -- single writer of the va_tenebrium_* rules params (see publishTenebriumRules)
    publishRules = function() publishTenebriumRules() end,
  })
  if not pack.ok then
    Spring.Echo("VA_TENEBRIUM_HANDLERS_ATTACH_FAIL " .. tostring(pack.err))
    return
  end
  Spring.Echo("VA_TENEBRIUM_HANDLERS_ATTACHED")
  -- Mid-reload: GameStart already passed — restore bank from published params.
  if tenebLoot.initFromMission and (Spring.GetGameFrame and Spring.GetGameFrame() or 0) > 0 then
    pcall(tenebLoot.initFromMission)
  end
end)()

-- Pillar C: turn the commander's earned level/perks into tangible start-of-
-- mission bonuses. Perks the compiler cannot bake into the seed (resources,
-- commander experience/toughness) are applied live here once units exist.
function applyCommanderPerks()
  local roster = mission and mission.storyIntent and mission.storyIntent.roster
  local commander = roster and roster.commander
  if not commander then return end
  local perks = commander.activePerks or {}
  local set = {}
  for _, p in ipairs(perks) do set[p] = true end
  local level = tonumber(commander.level or 1) or 1
  if set.field_repair then
    pcall(Spring.AddTeamResource, playerTeamID, "metal", 250)
    pcall(Spring.AddTeamResource, playerTeamID, "energy", 600)
  end
  local units = Spring.GetTeamUnits(playerTeamID) or {}
  for i = 1, #units do
    local uID = units[i]
    local dID = Spring.GetUnitDefID(uID)
    local ud = dID and UnitDefs[dID]
    if ud and ud.customParams and ud.customParams.iscommander then
      if Spring.SetUnitExperience then pcall(Spring.SetUnitExperience, uID, math.max(0, (level - 1) * 0.25)) end
      if set.ash_resolve and Spring.SetUnitMaxHealth then
        local _, maxH = Spring.GetUnitHealth(uID)
        if maxH then
          pcall(Spring.SetUnitMaxHealth, uID, maxH * 1.25)
          pcall(Spring.SetUnitHealth, uID, maxH * 1.25)
        end
      end
      Spring.SetUnitRulesParam(uID, "va_commander_level", level, { public = true })
      break
    end
  end
  Spring.Echo("VA_COMMANDER_PERKS level=" .. tostring(level) .. " perks=" .. table.concat(perks, ","))
end

-- Publish where the objective actually is so the HUD can mark it: centroid of
-- the spawned objective structures, or the target zone center for zone-holds.
function publishObjectiveMarker()
  local ox, oz, n = 0, 0, 0
  for unitID in pairs(objectiveTargets) do
    local x, _, z = Spring.GetUnitPosition(unitID)
    if x then ox, oz, n = ox + x, oz + z, n + 1 end
  end
  if n > 0 then
    ox, oz = ox / n, oz / n
  elseif targetZoneRect then
    ox = (targetZoneRect[1] + targetZoneRect[3]) * 0.5
    oz = (targetZoneRect[2] + targetZoneRect[4]) * 0.5
  else
    return
  end
  Spring.SetGameRulesParam("va_objective_x", math.floor(ox), { public = true })
  Spring.SetGameRulesParam("va_objective_z", math.floor(oz), { public = true })
end

-- BAR always drops one free faction commander. That start unit is the only
-- player commander. Strike sorties reclaim it. Commander sorties keep it and
-- reclaim every extra (a kit legcom, a late engine respawn). No explosion.
function sweepPlayerCommanders(why)
  local allowed = 0
  if not (doctrine.strikeTeam or (tonumber(doctrine.playerComsAllowed) or 0) <= 0) then
    allowed = math.floor(tonumber(doctrine.playerComsAllowed) or 0)
  end
  local keep = allowed
  local removed = 0
  local units = Spring.GetTeamUnits(playerTeamID) or {}
  for i = 1, #units do
    local uID = units[i]
    local dID = Spring.GetUnitDefID(uID)
    local ud = dID and UnitDefs[dID]
    if isCommanderUnitDef(ud) then
      if keep > 0 then
        keep = keep - 1
      else
        playerCommanders[uID] = nil
        Spring.DestroyUnit(uID, false, true)
        removed = removed + 1
      end
    end
  end
  if removed > 0 then
    if allowed <= 0 then doctrine.sawPlayerCom = false end
    Spring.Echo("VA_SWEEP_PLAYER_COMMANDERS count=" .. tostring(removed)
      .. " keep=" .. tostring(allowed) .. " why=" .. tostring(why or "sweep"))
  end
  return removed
end

function applyCommerceStartResources()
  -- Campaign metal bag (commerce.metalK) stays HOME. Sortie gets a small
  -- operating allotment (fieldStartMetalK) so mex/eco can spin up; end-of-
  -- sortie settle ADDS net export to the faction bag (does not replace it).
  -- 1km$ = 1000 BAR metal. Tenebrium still seeds from commerce.tenebrium.
  if playerTeamID == nil then return end
  local com = (mission and mission.commerce) or {}
  local fieldK = math.floor(tonumber(com.fieldStartMetalK or com.metalKFieldStart or 1) or 1)
  if fieldK < 0 then fieldK = 0 end
  local metal = fieldK * 1000 + (tonumber(VA_SCOUT_BONUS_METAL) or 0)   -- the scout bays' own thousand
  VA_SCOUT_BONUS_METAL = 0
  VA_COMMERCE_APPLIED = true
  -- Flat energy seed (not scaled from campaign bag — bag no longer enters).
  local energy = math.floor(tonumber(com.fieldStartEnergy or 3000) or 3000)
  if energy < 0 then energy = 0 end
  if metal <= 0 and energy <= 0 then
    Spring.Echo("VA_COMMERCE_START skip (no field allotment; bag stays home)")
    return
  end
  -- Remember targets so VA_STORAGE_REFRESH can restore after BAR's GameStart
  -- storage wipe (and so AddTeamResource is not clipped to a 1k cap).
  VA_CREW_SELECT = VA_CREW_SELECT or {}
  local mCur = select(1, Spring.GetTeamResources(playerTeamID, "metal")) or 0
  local eCur = select(1, Spring.GetTeamResources(playerTeamID, "energy")) or 0
  VA_CREW_SELECT.wantMetal = mCur + metal
  VA_CREW_SELECT.wantEnergy = eCur + energy
  VA_CREW_SELECT.storageRefreshUntil = 3
  VA_refreshPlayerStorageCaps("pre_commerce")
  if metal > 0 then pcall(Spring.AddTeamResource, playerTeamID, "metal", metal) end
  if energy > 0 then pcall(Spring.AddTeamResource, playerTeamID, "energy", energy) end
  Spring.Echo("VA_COMMERCE_START fieldStartMetalK=" .. tostring(fieldK)
    .. " metal=+" .. tostring(metal)
    .. " energy=+" .. tostring(energy)
    .. " bagMetalK=" .. tostring(math.floor(tonumber(com.metalK or 0) or 0))
    .. " (bag stays home)")
end

-- Drop-1 eco softener: first chapter always gets a playable BP cushion so
-- scarcity bites later, not on the tutorial sortie.
function applyFirstDropEcoSoftener()
  if playerTeamID == nil then return end
  local chapter = tonumber(sortieChapter) or 1
  local missionNo = tonumber(mission and mission.missionNumber) or 1
  if chapter > 1 or missionNo > 1 then return end
  local metal = 450
  local energy = 1800
  pcall(Spring.AddTeamResource, playerTeamID, "metal", metal)
  pcall(Spring.AddTeamResource, playerTeamID, "energy", energy)
  Spring.SetGameRulesParam("va_eco_softener", 1, { public = true })
  Spring.Echo("VA_ECO_SOFTENER drop1 metal=+" .. tostring(metal) .. " energy=+" .. tostring(energy))
end

-- The people the company left on this map (mission.fieldPeople, from camp.people) are still where
-- they stood, alone: bring them to the pad (a building hero lifts from where it stands).
function VA_FIELD_spawnPeople()
  local sx, sz = Game.mapSizeX or 0, Game.mapSizeZ or 0
  for _, p in ipairs((mission and mission.fieldPeople) or {}) do
    if type(p) == "table" and p.heroId then
      local n = VA_CREW_spawnHeroPack(tostring(p.heroId), normalizedToElmos(p.x or 0.5, sx), normalizedToElmos(p.z or 0.5, sz) - 40, 0, true)
      Spring.Echo("VA_FIELD_PERSON hero=" .. tostring(p.heroId) .. " zone=" .. tostring(p.zoneId) .. " spawned=" .. tostring(n))
    end
  end
end

-- A baked field's banks (Koom's war): what each side held when the sim was frozen. BAR's team
-- resourcing wipes the banks at GameStart, so they are set once the first frames are through.
function vaApplyWarBanks()
  for teamID, bank in pairs(vaWarBanks) do
    pcall(Spring.SetTeamResource, teamID, "metal", tonumber(bank.metal) or 0)
    pcall(Spring.SetTeamResource, teamID, "energy", tonumber(bank.energy) or 0)
    Spring.Echo(string.format("VA_WAR_BANK team=%d metal=%d energy=%d", teamID, tonumber(bank.metal) or 0, tonumber(bank.energy) or 0))
  end
  vaWarBanks = nil
end

-- Called by gadget:GameFrame.
function tickTenebrium(frame)
  -- WO-043c: shard spawn + wreck-gone loss timeout.
  if frame % 5 == 0 then
    tenebLoot.tickPending(frame)
  end
  -- Tnb top bar feed (va_tenebrium_bank/looted/spent/wrecks_unclaimed).
  if frame % 30 == 0 then
    publishTenebriumRules()
  end
end

-- Called by gadget:GameFrame.
function tickCommanderSweeps(frame)
  -- Re-sweep through frame 90. The engine can place its start commander
  -- late; commander sorties keep one, strike sorties keep none.
  if frame <= 90 then
    if frame == 1 or frame == 2 or frame == 8 or frame == 30 or frame == 90 then
      sweepPlayerCommanders("frame_" .. tostring(frame))
      if frame >= 90 then doctrine.commanderSwept = true end
    end
  elseif not doctrine.commanderSwept and frame >= 2 then
    doctrine.commanderSwept = true
  end
  -- Re-sweep a few times: engine free-com + late AI start units can appear
  -- after frame 3. DestroyUnit(..., false, true) reclaims with no boom.
  if doctrine.sweepEnemy and frame <= 90 then
    if frame == 3 or frame == 8 or frame == 30 or frame == 90 then
      local removed = 0
      for _, tid in ipairs(Spring.GetTeamList() or {}) do
        if tid ~= playerTeamID and tid ~= gaiaTeamID and not Spring.AreTeamsAllied(tid, playerTeamID) then
          local units = Spring.GetTeamUnits(tid) or {}
          for i = 1, #units do
            local uID = units[i]
            local dID = Spring.GetUnitDefID(uID)
            local ud = dID and UnitDefs[dID]
            if isCommanderUnitDef(ud) then
              Spring.DestroyUnit(uID, false, true)
              removed = removed + 1
            end
          end
        end
      end
      if removed > 0 then
        Spring.Echo("VA_SWEEP_ENEMY_COMMANDERS count=" .. tostring(removed)
          .. " frame=" .. tostring(frame))
      end
      if frame >= 90 then doctrine.enemySwept = true end
    end
  end
end

-- Called by gadget:UnitCreated.
function trackPlayerCommanderCreated(unitID, unitDefID, unitTeam)
  -- Strike-team missions field no commander; do not track one (and never let a
  -- transient auto-commander arm the commander-lost defeat before it is swept).
  if unitTeam == playerTeamID and not doctrine.strikeTeam then
    local ud = UnitDefs[unitDefID]
    if isCommanderUnitDef(ud) then
      playerCommanders[unitID] = true
      doctrine.sawPlayerCom = true
    end
  end
end

-- A player commander is gone (a fact for the result; the sortie goes on). Called by gadget:UnitDestroyed.
function playerCommanderDestroyed(unitID)
  if playerCommanders[unitID] then
    playerCommanders[unitID] = nil
    if doctrine.sawPlayerCom and next(playerCommanders) == nil and status == "active" and not terminal then
      Spring.Echo("VA_COMMANDER_LOST")  -- a fact for the result; the sortie goes on
    end
  end
end

-- The sortie's doctrine from its arc: commanders, sweeps, hot extraction, the act label. Called by gadget:Initialize.
function configureDoctrine(arc)
  doctrine.playerComsAllowed = tonumber(arc.playerCommanders)
  if doctrine.playerComsAllowed == nil then
    doctrine.playerComsAllowed = (mission.strikeTeam == true) and 0 or 1
  end
  doctrine.strikeTeam = (mission.strikeTeam == true) or (doctrine.playerComsAllowed <= 0)
  doctrine.sweepEnemy = (arc.sweepEnemyCommanders == true) or (tostring(arc.enemyMode or "") == "static_bases")
  -- Living shells already place armdecom/cordecom/legdecom eco nodes. The
  -- engine still drops a free real commander for SimpleAI/BARb; leaving that
  -- com alive is what produces "decoy" deaths with commanderExplosion + 1250 m
  -- wrecks. Sweep whenever a living shell is in the mission, unless the arc keeps the enemy's
  -- real commander (act II on: a commander is the threat that moves the map).
  if not doctrine.sweepEnemy and arc.sweepEnemyCommanders ~= false then
    local shell = mission.livingShell
    if type(shell) == "table" and type(shell.units) == "table" and #shell.units > 0 then
      doctrine.sweepEnemy = true
      Spring.Echo("VA_SWEEP_ENEMY_COMMANDERS reason=living_shell_decoy_farm")
    end
  end
  doctrine.hotExtractOnly = (mission.escalation and mission.escalation.hotExtractOnly == true)
      or (tostring(arc.escalation or "") == "off")
  -- Act label for the HUD and story (pacing only; nothing is gated on it).
  do
    local actInfo = mission.act
    doctrine.actNumber = tonumber(type(actInfo) == "table" and actInfo.act) or 0
    local actLabel = (type(actInfo) == "table" and actInfo.label) and tostring(actInfo.label) or ""
    Spring.SetGameRulesParam("va_act", doctrine.actNumber, { public = true })
    Spring.SetGameRulesParam("va_act_label", actLabel, { public = true })
  end
end
