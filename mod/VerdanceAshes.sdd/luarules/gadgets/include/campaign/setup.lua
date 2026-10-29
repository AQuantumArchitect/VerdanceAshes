-- campaign/setup.lua: the playable setup: camps, forces and the player's start
-- Part of game_verdance_campaign.lua, loaded into that gadget's environment
-- (VFS.Include with the gadget table), so its globals are the gadget's globals.
-- Provides: resourceIncome, spawnPlayableSetup
-- Uses: crew, field_recruits, mission_data, objectives, reinforcements, spawn, state

local playableSetupSpawned = false

function spawnPlayableSetup()
  vaDryClaims = {}
  vaDryMoves = 0
  if playableSetupSpawned then
    Spring.Echo("VA_PLAYABLE_SETUP already_spawned")
    return
  end
  local setup = mission and mission.playableSetup
  if not setup or setup.enabled == false then
    Spring.Echo("VA_PLAYABLE_SETUP none — seed missing playableSetup; BAR Initial Spawn will leave a stock com")
    Spring.SetGameRulesParam("va_playable_setup", 0, { public = true })
    return
  end
  playableSetupSpawned = true
  VA_CREW_loadRoster()
  -- Muster lives on the HTML hub. BAR only receives a sealed crew packet
  -- (mission.crewBand / deployAces). No in-game selection board.
  -- Chapter >1 (same-map continue) keeps surviving units. Hub packet only
  -- seeds chapter 1; empty-field recovery below re-drops if nobody is left.
  local freshChapter = (tonumber(sortieChapter) or 1) <= 1
  local hubHasCrew = false
  do
    local band = mission and (mission.crewBand or (mission.crew and mission.crew.band))
    local aces = mission and mission.deployAces
    if type(band) == "table" and #band > 0 then hubHasCrew = true end
    if type(aces) == "table" and #aces > 0 then hubHasCrew = true end
  end
  local useCrewKit = freshChapter and hubHasCrew
  if freshChapter and not hubHasCrew then
    -- No sealed packet: still run the kit path so autoConfirm can fill.
    useCrewKit = true
  end
  local hotToken = mission and type(mission.hotDrop) == "table" and mission.hotDrop.token
  VA_HOT.token = hotToken and tostring(hotToken) or nil
  VA_HOT.pending = VA_HOT.token ~= nil
  VA_HOT.reserve = {}
  VA_CREW_SELECT.pending = false
  VA_CREW_SELECT.confirmed = not useCrewKit
  local forces = setup.forces or {}
  local claimedMetalSpots = {}
  local totalSpawned = 0
  local enemyCampTeamID = nil
  for _, force in ipairs(forces) do
    local teamID = tonumber(force.teamID or 0) or 0
    if force.faction and force.faction ~= "" then
      teamFaction[teamID] = tostring(force.faction)
    end
    -- Pillar B: remember which teams reinforcements/mercs come from.
    if force.role == "objective_target" and not objectiveTeamID then objectiveTeamID = teamID end
    if (force.faction == "armada" or force.faction == "cortex") and not enemyCampTeamID then enemyCampTeamID = teamID end
    if (force.faction == "nullmercs" or force.role == "merc_foothold") and not mercTeamID then mercTeamID = teamID end
    local base = force.base or {}
    local baseX = normalizedToElmos(base.x or 0.5, Game.mapSizeX or 0)
    local baseZ = normalizedToElmos(base.z or 0.5, Game.mapSizeZ or 0)
    if force.role == "player_anchor" or force.id == "player_deployment" then
      -- The company lands on the pad. One point: the exfil gadget publishes it (va_pad_x/z)
      -- from the pad file, and the radar, the ground outline and extraction use the same one.
      local px, pz = tonumber((Spring.GetGameRulesParam("va_pad_x"))), tonumber((Spring.GetGameRulesParam("va_pad_z")))
      if px and pz and px >= 0 and pz >= 0 then
        if math.abs(px - baseX) + math.abs(pz - baseZ) > 64 then
          Spring.Echo("VA_LANDING_ON_PAD force was " .. math.floor(baseX) .. "," .. math.floor(baseZ) .. " pad " .. math.floor(px) .. "," .. math.floor(pz))
        end
        baseX, baseZ = px, pz
      end
      VA_CREW_SELECT.anchorX = baseX
      VA_CREW_SELECT.anchorZ = baseZ
    end
    if type(force.bank) == "table" then
      vaWarBanks = vaWarBanks or {}
      vaWarBanks[teamID] = force.bank
    end
    local forceSpawned = 0
    for _, group in ipairs(force.groups or {}) do
      local groupX = tonumber(group.dx or group.x or 0) or 0
      local groupZ = tonumber(group.dz or group.z or 0) or 0
      for _, spec in ipairs(group.units or {}) do
        local isPlayer = (force.role == "player_anchor" or force.id == "player_deployment")
        if isPlayer and VA_CREW_isCommerceKitSpec(spec) then
          -- Commerce deploy bag: spawned ONCE by VA_LOGISTICS.spawnCommerceDeployKit at
          -- GameStart from mission.commerce.deploy. Never from the layout force
          -- (see VA_CREW_isCommerceKitSpec for the rule).
        elseif useCrewKit and isPlayer and not spec.reserve then
          -- The company is what the hub sealed: the heroes' packs (spawn below), the reserve the
          -- player chose (spec.reserve, Add-ReserveToKit) and the shop's kit. Nothing else from the
          -- layout lands with it: no spare rez bots, no starter mex, winds or radar (the pad's own
          -- radar, placed below, marks the drop).
        elseif VA_HOT.pending and isPlayer and spec.reserve then
          -- Hot drop: the reserve waits with the company; the drop says how many board.
          VA_HOT.reserve[#VA_HOT.reserve + 1] = { spec = spec, teamID = teamID, baseX = baseX, baseZ = baseZ,
            groupX = groupX, groupZ = groupZ, force = force }
        else
          forceSpawned = forceSpawned + spawnUnitSpec(spec, teamID, baseX, baseZ, groupX, groupZ, claimedMetalSpots, force)
        end
      end
    end
    totalSpawned = totalSpawned + forceSpawned
    Spring.Echo("VA_PLAYABLE_FORCE id=" .. tostring(force.id or "?") .. " team=" .. tostring(teamID) .. " role=" .. tostring(force.role or "") .. " units=" .. tostring(forceSpawned))
  end
  local function collectHubPicks()
    local picks = {}
    local si = mission and mission.storyIntent
    local band = mission and (mission.crewBand or (mission.crew and mission.crew.band))
    if (not band or (type(band) == "table" and #band == 0)) and type(si) == "table" then
      band = si.crewBand or (si.crew and si.crew.band)
    end
    if type(band) == "table" then
      for _, id in ipairs(band) do
        if id and tostring(id) ~= "" then picks[#picks + 1] = tostring(id) end
      end
    end
    if #picks == 0 then
      local aces = mission and mission.deployAces
      if (not aces or (type(aces) == "table" and #aces == 0)) and type(si) == "table" then
        aces = si.deployAces
      end
      if type(aces) == "table" then
        local roster = VA_CREW_loadRoster()
        for _, id in ipairs(aces) do
          id = tostring(id or "")
          if id ~= "" and not (roster.isCore and roster.isCore(id)) then
            picks[#picks + 1] = id
          end
        end
      end
    end
    return picks
  end
  if VA_HOT.pending then
    -- Nobody of ours lands until the drop (VA_HOT_drop); the hot-drop widget holds the pause.
    Spring.SetGameRulesParam("va_hotdrop_pending", 1, { public = true })
    Spring.SetGameRulesParam("va_hotdrop_token", VA_HOT.token, { public = true })
    Spring.Echo("VA_HOTDROP_WAITING token=" .. VA_HOT.token .. " reserveSpecs=" .. tostring(#VA_HOT.reserve))
    VA_CREW_publish()
  elseif useCrewKit then
    -- Prefer hub-sealed band; fall back to deployAces (minus core); else defaults.
    local picks = collectHubPicks()
    -- Allow re-drop if a prior chapter left confirmed=true with zero units.
    if VA_CREW_SELECT.confirmed and not freshChapter then
      VA_CREW_SELECT.confirmed = false
      Spring.Echo("VA_CREW_REARM chapter=" .. tostring(sortieChapter) .. " hub_packet_present=1")
    end
    local sheetPresent = (mission and type(mission.crewBand) == "table")
      or (mission and type(mission.deployAces) == "table")
    if #picks > 0 then
      VA_CREW_confirm(picks)
    elseif sheetPresent then
      -- Explicit empty sheet: core only. Do not invent a default band.
      Spring.Echo("VA_CREW_PACKET_CORE_ONLY")
      VA_CREW_confirm({})
    else
      Spring.Echo("VA_CREW_PACKET_EMPTY core_only (no invented band)")
      VA_CREW_confirm({})
    end
    Spring.Echo("VA_CREW_FROM_PACKET picks=" .. table.concat(VA_CREW_SELECT.selected or picks, ",")
      .. " chapter=" .. tostring(sortieChapter)
      .. " fresh=" .. tostring(freshChapter))
  else
    VA_CREW_publish()
  end
  -- Empty-field safety: buggy extract / continue left nobody — drop the kit.
  if not VA_HOT.pending then
    local alive = 0
    if Spring.GetTeamUnits then
      local units = Spring.GetTeamUnits(playerTeamID) or {}
      for i = 1, #units do
        local u = units[i]
        if Spring.ValidUnitID(u) and not Spring.GetUnitIsDead(u) then
          alive = alive + 1
        end
      end
    end
    if alive == 0 then
      Spring.Echo("VA_CREW_EMPTY_FIELD recovering_hub_kit chapter=" .. tostring(sortieChapter))
      VA_CREW_SELECT.confirmed = false
      local picks = collectHubPicks()
      local sheetPresent = (mission and type(mission.crewBand) == "table")
        or (mission and type(mission.deployAces) == "table")
      if #picks > 0 then
        VA_CREW_confirm(picks)
      else
        Spring.Echo("VA_CREW_PACKET_CORE_ONLY")
        VA_CREW_confirm({})
      end
    end
  end
  -- Presence objectives have no objective_target force; fall back to the camp.
  objectiveTeamID = objectiveTeamID or enemyCampTeamID
  -- Wild company pool: named recruitables on this map (wreck + rez to join).
  VA_FIELD_spawnRecruits(objectiveTeamID or enemyCampTeamID)
  if mercTeamID and Spring.AreTeamsAllied(playerTeamID, mercTeamID) then mercsAllied = true end
  Spring.SetGameRulesParam("va_mercs_available", (mercsAllied and not mercWaveUsed) and 1 or 0, { public = true })
  Spring.SetGameRulesParam("va_objective_total", objectiveTargetCount, { public = true })
  Spring.SetGameRulesParam("va_objective_destroyed", 0, { public = true })
  -- Drop 4: enrich marks from seed meta, arm purge, publish HUD ledger once.
  MarksLib.enrichFromMission(marks, mission and mission.secondaries, Game.mapSizeX, Game.mapSizeZ)
  MarksLib.publish(marks)
  if MarksLib.count(marks) > 0 then
    Spring.Echo("VA_SECONDARY_ARMED groups=" .. tostring(MarksLib.count(marks))
      .. " required=" .. tostring(MarksLib.requiredLeft(marks)))
  end
  if mission and mission.objective and tostring(mission.objective.strength or "") == "purge" then
    extraObj.purge = true
    local purgeCount = 0
    for _, force in ipairs(forces) do
      if force.faction == "armada" or force.faction == "cortex" then
        local tid = tonumber(force.teamID or -1) or -1
        if tid >= 0 and not extraObj.purgeTeams[tid]
            and not Spring.AreTeamsAllied(playerTeamID, tid) then
          extraObj.purgeTeams[tid] = true
          purgeCount = purgeCount + 1
        end
      end
    end
    Spring.SetGameRulesParam("va_purge_armed", 1, { public = true })
    Spring.SetGameRulesParam("va_purge_done", 0, { public = true })
    Spring.Echo("VA_PURGE_ARMED teams=" .. tostring(purgeCount))
  end
  -- The centre of the drop zone is marked by a T1 radar (the exfil gadget published the pad
  -- point at load). It is ours and it stays: left behind, it is a holding like any structure.
  do
    local px, pz = tonumber((Spring.GetGameRulesParam("va_pad_x"))), tonumber((Spring.GetGameRulesParam("va_pad_z")))
    if px and pz and px >= 0 and pz >= 0 and UnitDefNames and UnitDefNames["armrad"] then
      local py = Spring.GetGroundHeight(px, pz) or 0
      local radar = Spring.CreateUnit("armrad", px, py, pz, 0, playerTeamID)
      Spring.Echo("VA_PAD_RADAR unit=" .. tostring(radar) .. " @ " .. math.floor(px) .. "," .. math.floor(pz))
    end
  end
  Spring.SetGameRulesParam("va_playable_setup", 1, { public = true })
  Spring.SetGameRulesParam("va_playable_units", totalSpawned, { public = true })
  Spring.Echo("VA_PLAYABLE_SETUP spawned forces=" .. tostring(#forces) .. " units=" .. tostring(totalSpawned))
  Spring.Echo("VA_ESCALATION_SETUP enemyTeam=" .. tostring(objectiveTeamID) .. " mercTeam=" .. tostring(mercTeamID) .. " mercsAllied=" .. tostring(mercsAllied))
  Spring.Echo("VA_OBJECTIVE_ARMED kind=" .. tostring(mission.objective and mission.objective.kind or "none") .. " targets=" .. tostring(objectiveTargetCount))
  do
    local kind = tostring(mission.objective and mission.objective.kind or "")
    local shell = mission.livingShell
    local hasShell = type(shell) == "table" and shell.enabled ~= false
    Spring.Echo("VA_OBJECTIVE_KIND kind=" .. (kind ~= "" and kind or "none")
      .. " mode=" .. vaObjectiveMode(kind)
      .. " targets=" .. tostring(objectiveTargetCount)
      .. " zone=" .. tostring(targetZoneRect and "yes" or "no")
      .. " shell=" .. tostring(hasShell and 1 or 0))
  end
end

function resourceIncome(teamID, resourceName)
  local ok, a, b, c, income = pcall(Spring.GetTeamResources, teamID, resourceName)
  if ok then return tonumber(income or c or 0) or 0 end
  return 0
end
