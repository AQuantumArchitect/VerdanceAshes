if not VFS.Include("LuaRules/Configs/va_active.lua") then return false end -- plain BAR unless the hub launched this
local gadget = gadget

function gadget:GetInfo()
  return {
    name = "Verdance Campaign Bridge",
    desc = "Campaign bridge and objective automation for Verdance's Ashes",
    author = "ChatGPT / Claude / Luke Spooner",
    date = "2026-07-05",
    license = "GPL v2 or later",
    -- Layer 2: run GameStart *after* BAR Team Resourcing (layer 1) so its
    -- storage-cap reset cannot wipe Solarium / pad M+E storages.
    layer = 2,
    enabled = true,
  }
end

if not gadgetHandler:IsSyncedCode() then
  VFS.Include("luarules/gadgets/include/campaign/unsynced.lua", gadget)
  return
end

-- ---------------------------------------------------------------------------
-- The campaign gadget, in parts (luarules/gadgets/include/campaign/, README.md there).
--
-- This file is the core: GetInfo, the synced/unsynced split, the engine call-ins (Initialize,
-- GameStart, GameFrame, the Unit*/Feature* events, TextCommand, RecvLuaMsg) and the order the
-- parts load in. Each part is one area of the sortie, loaded with VFS.Include(path, gadget): it
-- runs in this gadget's own environment, so a part's globals are this gadget's globals. They
-- never leak into other gadgets; GG.* is the only cross-gadget surface. A part keeps its own
-- helpers `local`, and lists in its header what it shares with the other parts. Each part is its
-- own chunk with Lua 5.1's 200-local budget to itself. Load order matters only for load-time
-- code; everything else runs from the call-ins below, after every part is in.
--
--   state           the sortie itself (mission, zone map, status, teams), the marks registry and the JSON helpers
--   result          the sortie result: every JSON part, chunked logging, the headless finish
--   mission_data    reading the mission seed and the zone map
--   units           unit-def helpers and metal spots
--   mentors         pack mentors (Spoke, the leads): subordinate XP and field effects
--   hero_spawn      a hero's unit on the field: modifiers, tags, registration
--   spawn           placing units: dry landing, standable ground, spawnOneUnit / spawnUnitSpec
--   crew            the company on the field: roster, hero packs, bonds, crew confirm, the hot drop
--   field_recruits  wild heroes: recruit wrecks, field factories, who waits where
--   setup           the playable setup: camps, forces and the player's start
--   telemetry       zone cells, per-zone metrics and dev telemetry
--   waterline       the waterline (hydrology) and zone flow
--   translation     the translation matrix packet
--   objectives      the objective: kind and mode, the pad, living-shell claims, presence / fortify / wipe / soft clock
--   reinforcements  enemy response waves and where they enter
--   heroes          hero lifecycle: down, wreck, rez, lost, recovered, field joins
--   beats           in-mission beats (authored triggers)
--   terminal        ending the sortie: the terminal crunch and the GG entry points
--   start           start of the sortie: commanders, perks, start resources, Tenebrium handlers
--   logistics       mercenary logistics: the deploy kit, pending deliveries, the brute crash
--   devcmd          the /luarules va* playtest commands
-- ---------------------------------------------------------------------------
VFS.Include("luarules/gadgets/include/campaign/state.lua", gadget)
VFS.Include("luarules/gadgets/include/campaign/result.lua", gadget)
VFS.Include("luarules/gadgets/include/campaign/mission_data.lua", gadget)

function startMission()
  status = "active"
  vaInitWaterline()
  holdFrames = 0
  debugAutoProgress = debugAutoProgressAllowed and 1 or 0
  if tenebLoot.initFromMission then tenebLoot.initFromMission() end
  Spring.SetGameRulesParam("va_status", status, { public = true })
  Spring.Echo("VA_START " .. tostring(mission.missionId) .. " zone=" .. tostring(mission.zone or "unknown"))
  echoStatus()
end

VFS.Include("luarules/gadgets/include/campaign/units.lua", gadget)

VFS.Include("luarules/gadgets/include/campaign/mentors.lua", gadget)

VFS.Include("luarules/gadgets/include/campaign/hero_spawn.lua", gadget)

VFS.Include("luarules/gadgets/include/campaign/spawn.lua", gadget)
VFS.Include("luarules/gadgets/include/campaign/crew.lua", gadget)

VFS.Include("luarules/gadgets/include/campaign/field_recruits.lua", gadget)

VFS.Include("luarules/gadgets/include/campaign/setup.lua", gadget)

VFS.Include("luarules/gadgets/include/campaign/telemetry.lua", gadget)

VFS.Include("luarules/gadgets/include/campaign/waterline.lua", gadget)
VFS.Include("luarules/gadgets/include/campaign/translation.lua", gadget)

VFS.Include("luarules/gadgets/include/campaign/objectives.lua", gadget)
VFS.Include("luarules/gadgets/include/campaign/reinforcements.lua", gadget)

VFS.Include("luarules/gadgets/include/campaign/heroes.lua", gadget)

VFS.Include("luarules/gadgets/include/campaign/beats.lua", gadget)

VFS.Include("luarules/gadgets/include/campaign/terminal.lua", gadget)

VFS.Include("luarules/gadgets/include/campaign/start.lua", gadget)

function gadget:Initialize()
  -- Offline bakes (the shell grow, the Koom war) are pure BARb sims: no sortie, no hot drop, no start
  -- pause. Without this the installed mission drops the company in and holds the game at frame 30.
  if truthy((Spring.GetModOptions() or {}).va_shell_bake) then
    Spring.Echo("VA_CAMPAIGN_SKIP bake mode - no sortie")
    gadgetHandler:RemoveGadget(self)
    return
  end
  Spring.Echo("VA_CAMPAIGN_BRIDGE_LOADED")
  mission = readMission()
  zoneMap = readZoneMap()
  local modOptions = Spring.GetModOptions() or {}
  -- Dev telemetry arm: mission seed, modoption, or generated flag file.
  do
    local flag = nil
    local okF, dataF = pcall(VFS.Include, "singleplayer/verdance_ashes/generated/dev_telemetry_flag.lua")
    if okF and type(dataF) == "table" then flag = dataF end
    local fromMission = mission and (mission.devTelemetry == true or (mission.dev and mission.dev.telemetry == true))
    -- va_play_track is the player-facing name for the same arm. The playtest
    -- launcher sets it; va_dev_telemetry stays for the dev_launch/flag-file path.
    local fromOpt = truthy(modOptions.va_dev_telemetry) or truthy(modOptions.va_play_track)
    local fromFlag = flag and truthy(flag.enabled)
    devTel.enabled = fromMission or fromOpt or fromFlag
    local period = tonumber(mission and mission.dev and mission.dev.samplePeriodFrames)
      or tonumber(flag and flag.samplePeriodFrames)
      or tonumber(modOptions.va_dev_sample_period)
      or 150
    if period and period >= 30 then devTel.period = math.floor(period) end
    if devTel.enabled then
      Spring.Echo("VA_DEV_TELEMETRY_ARMED period=" .. tostring(devTel.period)
        .. " mission=" .. tostring(fromMission)
        .. " opt=" .. tostring(fromOpt)
        .. " flag=" .. tostring(fromFlag))
    end
  end
  headless.autoStart = truthy(modOptions.va_headless_autostart)
  -- The absent modoption is nil, which matches none of the three false-y tests, so
  -- this read "true" in EVERY human session -- not just headless ones. That set
  -- debugAutoProgressAllowed, which ticks holdFrames up by 30 every 30 frames whether
  -- or not the player is holding anything, stamps auto=1 on VA_STATUS, and puts
  -- "debugAutoProgress":1 in the result JSON. It has not been stealing wins only
  -- because checkSoftClock runs first and every authored requiredFrames divides by 30;
  -- a seed missing requiredFrames falls through to 600 and fires a bogus victory.
  -- fastWin is a headless-batch concept, so scope it to a headless batch.
  headless.fastWin = headless.autoStart
    and not (modOptions.va_headless_fastwin == false or modOptions.va_headless_fastwin == 0 or modOptions.va_headless_fastwin == "0")
  headless.quit = truthy(modOptions.va_headless_quit)
  balance.exportFrame = tonumber(modOptions.va_balance_export_frame or "")
  balance.quitAfterExport = truthy(modOptions.va_balance_quit)

  -- Parse Fibonacci milestone list: va_fib_export_frames=900,1800,2700,4500,...
  local fibRaw = tostring(modOptions.va_fib_export_frames or "")
  if fibRaw ~= "" then
    for s in fibRaw:gmatch("[^,]+") do
      local n = tonumber(s:match("^%s*(.-)%s*$"))
      if n and n > 0 then fib.milestones[#fib.milestones+1] = math.floor(n) end
    end
    table.sort(fib.milestones)
    fib.quitAfterLast = truthy(modOptions.va_fib_quit)
  end

  -- Objective automation setup
  local arc = mission.arcProfile or {}
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
  gaiaTeamID = Spring.GetGaiaTeamID()
  for _, tid in ipairs(Spring.GetTeamList()) do
    local _, _, _, _, _, at = Spring.GetTeamInfo(tid, false)
    teamAllyTeam[tid] = tonumber(at or -1) or -1
  end
  -- The installed seed outlives the startscript that produced it: headless
  -- matrices and smoke runs reuse whatever va_current.lua is on disk against a
  -- different team layout. A balance.playerTeamID naming a team this match does
  -- not have turns every GetTeamUnits/GetTeamResources call into a hard "Bad
  -- teamID" error inside UnitCreated/GameStart/GameFrame, which kills the run
  -- with no result and no obvious cause. Clamp to a team that exists.
  playerTeamID = tonumber(mission.balance and mission.balance.playerTeamID) or 0
  if teamAllyTeam[playerTeamID] == nil then
    local seeded = playerTeamID
    local fallback = nil
    for _, tid in ipairs(Spring.GetTeamList()) do
      if tid ~= gaiaTeamID and (fallback == nil or tid < fallback) then
        fallback = tid
      end
    end
    playerTeamID = fallback or 0
    Spring.Echo("VA_WARN_TEAM seed playerTeamID=" .. tostring(seeded)
      .. " absent from this match; using team " .. tostring(playerTeamID))
  end
  playerAllyTeamID = teamAllyTeam[playerTeamID] or 0
  debugAutoProgressAllowed = headless.fastWin or truthy(modOptions.va_debug_autoprogress)
  -- The player's team is a fact other gadgets need (craft_xp, veterancy,
  -- unit_behavior resolve it at GameStart); publish it once, clamped.
  Spring.SetGameRulesParam("va_player_team", playerTeamID, { public = true })
  -- Headless spins forever building the unit-icon texture atlas at frame 30.
  -- The shell-bake and cartography gadgets both learned this the hard way and
  -- carry the same guard; every va_* probe runs through THIS gadget, so it
  -- belongs here too. Only under an explicitly headless/profiling run -- a real
  -- session needs its icons.
  --
  -- va_no_ui exists to separate "this process has no screen" from "this is a
  -- profiling run". They were the same predicate, which made the human code path
  -- untestable: verifying it headlessly meant setting a profiling flag, and every
  -- profiling flag also forces 20x sim, disables waves and beats, grants an
  -- instant win and skips Spring.GameOver -- so the thing under test was never the
  -- thing that would run. Without it, spring-headless builds the full widget set
  -- and icon atlas and never reaches frame 0. Absent in a real session, so the
  -- player keeps their UI.
  local noUi = (headless.autoStart or balance.exportFrame or #fib.milestones > 0)
    or truthy(modOptions.va_no_ui)
  -- The third argument is useOverlay, and it is load-bearing, not a nicety. The
  -- engine documents it as "the value will only be set in memory, and not be
  -- restored for the next game" -- meaning WITHOUT it these three writes persist
  -- into the player's real springsettings.cfg and outlive the process. That is
  -- not hypothetical: an earlier headless probe on this machine left LuaUI = 0
  -- and UnitIconDist = 99999 sitting in the live config, which would have opened
  -- the next GUI session with no LuaUI at all -- no widgets, no HUD, and no
  -- recorder -- with nothing in game to explain why.
  if noUi and Spring.SetConfigInt then
    Spring.SetConfigInt("UnitIconsAsUI", 0, true)
    Spring.SetConfigInt("UnitIconDist", 99999, true)
    Spring.SetConfigInt("LuaUI", 0, true)
  end

  -- Headless sims at 1x unless the host is told otherwise, so a 21-minute
  -- profiling milestone costs 21 real minutes and an overnight matrix cannot
  -- finish. The shell-bake and cartography gadgets already force the sim clock
  -- up for their unattended batches; profiling runs come through this gadget and
  -- need the same. Guarded by the profiling condition, so a real session is
  -- untouched. va_headless_speed=0 opts out.
  if (headless.autoStart or balance.exportFrame or #fib.milestones > 0)
      and Spring.SendCommands then
    local simSpeed = tonumber(modOptions.va_headless_speed or "") or 20
    if simSpeed > 0 then
      Spring.SendCommands("setmaxspeed " .. simSpeed)
      Spring.SendCommands("setminspeed " .. simSpeed)
    end
  end

  -- Border-crossing sampler cadence. Defaults on only under profiling: a real
  -- session gets it only if it explicitly asks.
  vaZoneFlowSample = tonumber(modOptions.va_zone_flow_sample or "")
    or ((headless.autoStart or balance.exportFrame or #fib.milestones > 0) and 150 or 0)
  -- A tracked human session is asking. Without this the whole AI-duel measurement
  -- -- which corridors carry traffic, which sit inert -- has no human counterpart:
  -- the sampler stays at 0 and every crossing goes unrecorded.
  --
  -- Pinned to the same 150 the profiling runs used, NOT to devTel.period. A crossing
  -- count is a function of how often you look: sample every 1800 frames instead of
  -- every 150 and a unit that goes A->B->A between looks records nothing at all.
  -- Human and AI crossing counts are only comparable at one shared rate, so the
  -- emission cadence (devTel.period) and the observation cadence are separate knobs.
  if vaZoneFlowSample <= 0 and devTel.enabled then
    vaZoneFlowSample = 150
  end

  -- Escalation: mission.escalation.mode / waves.max wins; modoption force still works.
  local profiling = headless.autoStart or balance.exportFrame or (#fib.milestones > 0)
  local escOpt = modOptions.va_escalation
  local escMode = tostring((mission.escalation and mission.escalation.mode) or arc.escalation or "")
  local maxFromSeed = tonumber(mission.escalation and mission.escalation.maxWaves)
  if escOpt ~= nil and tostring(escOpt) ~= "" then
    waves.enabled = truthy(escOpt)
  elseif escMode == "off" or (maxFromSeed ~= nil and maxFromSeed <= 0) then
    waves.enabled = false
  else
    waves.enabled = not profiling
  end
  local escScale = tonumber(mission.difficulty and mission.difficulty.enemyScale) or 1.0
  waves.baseSize = math.max(2, math.floor(4 * math.min(1.5, escScale) + 0.5))
  waves.max = maxFromSeed or 4
  waves.interval = tonumber(mission.escalation and mission.escalation.intervalFrames) or 2700
  waves.nextFrame = tonumber(mission.escalation and mission.escalation.firstWaveFrame) or 1800
  local wi = tonumber(modOptions.va_wave_interval or ""); if wi and wi > 0 then waves.interval = wi end
  local wf = tonumber(modOptions.va_first_wave or ""); if wf and wf > 0 then waves.nextFrame = wf end
  local obj = mission.objective or {}
  targetZoneRect = zoneRectFor(obj.targetZoneId)
  -- One pad (pass five): the company lands and lifts from the same point — the deployment
  -- zone's anchor. Deploy beacon, bought kit (infilAnchor) and extraction all read it.
  extractLoop.applyPad(mission.deploymentZoneId or mission.extractionZoneId or obj.extractionZoneId)

  -- In-mission beats ride the same profiling gate as escalation waves;
  -- va_beats forces them either way.
  local beatOpt = modOptions.va_beats
  if beatOpt ~= nil and tostring(beatOpt) ~= "" then
    beatsEnabled = truthy(beatOpt)
  else
    beatsEnabled = not profiling
  end
  if beatsEnabled then compileBeats() end

  Spring.SetGameRulesParam("va_bridge_loaded", 1, { public = true })
  Spring.SetGameRulesParam("va_mission_number", mission.missionNumber or 0, { public = true })
  Spring.SetGameRulesParam("va_hold_frames", holdFrames, { public = true })
  Spring.SetGameRulesParam("va_required_frames", mission.objective and mission.objective.requiredFrames or 600, { public = true })
  Spring.SetGameRulesParam("va_status", status, { public = true })
  Spring.SetGameRulesParam("va_objective_complete", 0, { public = true })
  Spring.SetGameRulesParam("va_objective_failed", 0, { public = true })
  Spring.SetGameRulesParam("va_objective_fail_reason", "", { public = true })
  Spring.SetGameRulesParam("va_objective_fail_hero", "", { public = true })
  Spring.SetGameRulesParam("va_terminal", 0, { public = true })
  Spring.SetGameRulesParam("va_arc_id", tostring(arc.id or ""), { public = true })
  Spring.SetGameRulesParam("va_player_commanders", doctrine.playerComsAllowed, { public = true })
  Spring.SetGameRulesParam("va_continue_chapter", sortieChapter, { public = true })
  -- Mid-reload / soft-continue: restore sticky field joins so /vawin and later
  -- chapter results still export recruitedHeroIds.
  if (Spring.GetGameFrame and Spring.GetGameFrame() or 0) > 0 then
    restoreRecruitedHeroIdsFromRules()
  end
  Spring.Echo("VA_BRIDGE_LOADED mission=" .. tostring(mission.missionId)
    .. " arc=" .. tostring(arc.id or "?")
    .. " playerComs=" .. tostring(doctrine.playerComsAllowed)
    .. " esc=" .. tostring(escMode ~= "" and escMode or (waves.enabled and "on" or "off"))
    .. " schema=" .. tostring(mission.schemaVersion or "unknown"))
  if headless.autoStart then Spring.Echo("VA_HEADLESS_AUTOSTART enabled") end
  if balance.exportFrame then Spring.Echo("VA_BALANCE_AUTORUN exportFrame=" .. tostring(balance.exportFrame) .. " quit=" .. tostring(balance.quitAfterExport)) end
  if #fib.milestones > 0 then
    Spring.Echo("VA_FIB_PROFILER milestones=" .. tostring(#fib.milestones) .. " first=" .. tostring(fib.milestones[1]) .. " last=" .. tostring(fib.milestones[#fib.milestones]) .. " quitAfterLast=" .. tostring(fib.quitAfterLast))
  end
  if zoneMap then Spring.Echo("VA_ZONES_LOADED mapId=" .. tostring(zoneMap.mapId or "unknown") .. " count=" .. tostring(zoneCount())) end
end

function gadget:GameStart()
  -- Bank + crisis flags before any unit stamps/charges.
  if tenebLoot.initFromMission then tenebLoot.initFromMission() end
  -- Sink the waterline before anyone is placed, so the dry search sees the
  -- shore the company will actually stand on.
  vaInitWaterline()
  spawnPlayableSetup()
  VA_FIELD_spawnPeople()
  -- One player commander. Strike sorties reclaim the free start unit;
  -- commander sorties keep it and drop any second body.
  sweepPlayerCommanders("gamestart")
  applyCommerceStartResources()
  applyFirstDropEcoSoftener()
  applyCommanderPerks()
  publishObjectiveMarker()
  if headless.autoStart and not headless.started then
    headless.started = true
    startMission()
    if headless.fastWin then
      finishHeadlessResult("victory")
    end
  elseif not headless.autoStart then
    -- Playable session: the mission is live immediately, no /vastart needed.
    startMission()
  end
  -- Paid hub kit first (punch / constructors / fabs), then arm mid-sortie inbound.
  if VA_LOGISTICS and VA_LOGISTICS.spawnCommerceDeployKit then
    VA_LOGISTICS.spawnCommerceDeployKit()
  end
  armPendingDeliveries()
  publishTenebriumRules()
end

function gadget:GameFrame(frame)
  if vaWarBanks and frame >= 5 then vaApplyWarBanks() end
  -- Deferred exfil crunch (loading screen paints first). One call = one upvalue.
  -- Field-recruit wreck seeds: kill the live unit so BAR leaves a normal rez corpse.
  tickFieldRecruitPendingDeath(frame)
  -- Re-apply M/E storage caps after BAR Team Resourcing's GameStart wipe.
  do
    local untilF = VA_CREW_SELECT and tonumber(VA_CREW_SELECT.storageRefreshUntil)
    if untilF and frame >= 1 and frame <= untilF then
      VA_refreshPlayerStorageCaps("frame_" .. tostring(frame))
      if frame >= untilF then
        VA_CREW_SELECT.storageRefreshUntil = nil
        -- Drop temporary commerce floors; ongoing caps come from buildings.
        VA_CREW_SELECT.wantMetal = nil
        VA_CREW_SELECT.wantEnergy = nil
        VA_refreshPlayerStorageCaps("post_commerce_settle")
      end
    end
  end

  if vaWaterTarget and frame % VA_WATER_TICK == 0 then
    vaStepWaterline()
  end

  if headless.autoStart and not headless.started and frame >= 1 then
    headless.started = true
    startMission()
    if VA_LOGISTICS and VA_LOGISTICS.spawnCommerceDeployKit then
      VA_LOGISTICS.spawnCommerceDeployKit()
    end
    armPendingDeliveries()
    if headless.fastWin then
      finishHeadlessResult("victory")
    end
  end

  if vaZoneFlowSample > 0 and frame > 0 and frame % vaZoneFlowSample == 0 then
    vaSampleZoneFlow()
  end
  tickPendingDeliveries(frame)

  if balance.exportFrame and not balance.exported and frame >= balance.exportFrame then
    balance.exported = true
    logTelemetry()
    Spring.Echo("VA_ZONE_FLOW_JSON " .. vaZoneFlowJson())
    logAndBroadcastTranslation()
    if balance.quitAfterExport then
      headless.quitFrame = frame + 2
    end
  end

  -- Fibonacci multi-milestone profiler
  if #fib.milestones > 0 and fib.idx <= #fib.milestones then
    local due = fib.milestones[fib.idx]
    if frame >= due then
      Spring.Echo("VA_FIB_MILESTONE idx=" .. tostring(fib.idx) .. " frame=" .. tostring(frame) .. " target=" .. tostring(due))
      logTelemetry()
      Spring.Echo("VA_ZONE_FLOW_JSON " .. vaZoneFlowJson())
      logAndBroadcastTranslation()
      fib.idx = fib.idx + 1
      if fib.idx > #fib.milestones and fib.quitAfterLast then
        headless.quitFrame = frame + 2
      end
    end
  end

  if headless.quitFrame and frame >= headless.quitFrame then
    Spring.Echo("VA_HEADLESS_QUIT")
    Spring.SendCommands("quitforce")
    headless.quitFrame = nil
  end

  -- WO-043c: shard spawn + wreck-gone loss timeout.
  if frame % 5 == 0 then
    tenebLoot.tickPending(frame)
  end
  -- Tnb top bar feed (va_tenebrium_bank/looted/spent/wrecks_unclaimed).
  if frame % 30 == 0 then
    publishTenebriumRules()
  end

  -- WO-033 unit printer metal/energy trickle (per-frame).
  if next(printerUnits) and frame % 30 == 0 then
    for uID, rec in pairs(printerUnits) do
      if not Spring.ValidUnitID(uID) then
        printerUnits[uID] = nil
      else
        pcall(Spring.AddTeamResource, rec.team, "metal", rec.metal * 30)
        pcall(Spring.AddTeamResource, rec.team, "energy", rec.energy * 30)
      end
    end
  end

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

  -- Living shell spawns ~frame 8; claim objective eco + optional high-value marks.
  -- Retry past the first window when the primary pad still has no eco
  -- (hub marks like GF_NE_PLATEAU with no pocket used to leave the pocket at 0).
  if frame >= 20 and frame % 10 == 0 then
    if not shellObjectivesClaimed and frame <= 180 then
      claimLivingShellObjectives()
      claimOptionalHighValueSecondaries()
    elseif shellObjectivesClaimed and objectiveTargetCount <= 0 and frame <= 240 and frame % 30 == 0 then
      shellObjectivesClaimed = false
      claimLivingShellObjectives()
      claimOptionalHighValueSecondaries()
    end
  end

  -- Objective automation checks (playable sessions)
  if status == "active" and not terminal and frame % CHECK_PERIOD == 0 then
    checkPresenceObjective(frame)
    vaCheckPurge(frame)
    checkPlayerWipe(frame)
    checkHeroWreckTimeouts(frame)
    checkSoftClock(frame)
    if beatsEnabled then checkBeats(frame) end
    pollMentorSubordinateXp(frame)
  end

  -- Pillar B: enemy reinforcements on a steady timer.
  if waves.enabled and status == "active" and not terminal and not objectiveComplete and objectiveTeamID then
    if frame >= waves.nextFrame and waves.spawned < waves.max then
      local px, pz = enemyResponseTarget()
      spawnWave(objectiveTeamID, waves.baseSize, px, pz, "escalation")
      waves.spawned = waves.spawned + 1
      waves.nextFrame = frame + waves.interval
      Spring.SetGameRulesParam("va_waves_spawned", waves.spawned, { public = true })
    end
  end

  -- Debug/fastwin auto-progress timer (only armed via modoption)
  if status == "active" and debugAutoProgress == 1 and frame % 30 == 0 then
    holdFrames = holdFrames + 30
    Spring.SetGameRulesParam("va_hold_frames", holdFrames, { public = true })
    local req = mission.objective and mission.objective.requiredFrames or 600
    if holdFrames >= req then
      Spring.Echo("VA_OBJECTIVE_COMPLETE mission=" .. tostring(mission.missionId))
      setTerminal("extracted", "debug_autoprogress")
    end
  end

  -- Dense human-player telemetry for dev launch learning loop.
  if devTel.enabled and status == "active" and not terminal then
    if (frame - devTel.lastSample) >= devTel.period then
      logDevSample()
    end
  end
end

function gadget:UnitCommand(unitID, unitDefID, unitTeam, cmdID, cmdParams, cmdOpts, cmdTag)
  if not devTel.enabled then return end
  if unitTeam ~= playerTeamID then return end
  local key = classifyCmd(cmdID)
  devTel.cmds[key] = (devTel.cmds[key] or 0) + 1
  devTel.cmdTotal = devTel.cmdTotal + 1
end

function gadget:UnitCreated(unitID, unitDefID, unitTeam, builderID)
  -- Strike-team missions field no commander; do not track one (and never let a
  -- transient auto-commander arm the commander-lost defeat before it is swept).
  if unitTeam == playerTeamID and not doctrine.strikeTeam then
    local ud = UnitDefs[unitDefID]
    if isCommanderUnitDef(ud) then
      playerCommanders[unitID] = true
      doctrine.sawPlayerCom = true
    end
  end
  -- A rez bot consuming a tracked hero wreck brings the hero back.
  heroOnUnitCreated(unitID, unitDefID, unitTeam, builderID)
  -- Factory bay rez/capture landing on the player team.
  maybeFieldFactoryJoin(unitID, unitDefID, unitTeam, builderID)
  -- Mentor factories / scout mints: new player units inherit banked XP + field.
  if unitTeam == playerTeamID and next(packMentors) and not heroByUnitID[unitID] then
    local ud = UnitDefs[unitDefID]
    local defName = ud and ud.name
    if defName then
      for heroId, bag in pairs(packMentors) do
        local products = bag.productDefs or mentorProductDefs()[heroId]
        if products and products[defName] then
          stampMentorSubordinate(unitID, heroId)
          break
        elseif heroId == "spoke" and isWheelieDef(defName) then
          stampMentorSubordinate(unitID, "spoke")
          break
        end
      end
    end
  end
  -- Hearth: newly built sister fusions inherit the energy field.
  if unitTeam == playerTeamID and heroes and heroes.hearth and HeroTags then
    local hRec = heroes.hearth
    if hRec and hRec.field and hRec.field.primaryStat == "energy"
        and hRec.unitID and Spring.ValidUnitID(hRec.unitID) then
      local ud = UnitDefs[unitDefID]
      if HeroTags.isFusionDef and HeroTags.isFusionDef(ud) then
        HeroTags.applyFusionEnergyAura(hRec.unitID, hRec.field, unitTeam)
      end
    end
  end
  -- Pavise: newly built Centurions inherit the HP ward (self + nearby armwar).
  if unitTeam == playerTeamID and heroes and heroes.pavise and HeroTags then
    local hRec = heroes.pavise
    if hRec and hRec.field and hRec.field.primaryStat == "hp"
        and hRec.unitID and Spring.ValidUnitID(hRec.unitID) then
      local ud = UnitDefs[unitDefID]
      if HeroTags.isCenturionDef and HeroTags.isCenturionDef(ud) then
        HeroTags.applyCenturionHpAura(hRec.unitID, hRec.field, unitTeam)
      end
    end
  end
  -- WO-043c: charge / stamp Tenebrium for build-power units.
  tenebLoot.onUnitCreated(unitID, unitDefID, unitTeam, builderID)
end

function gadget:AllowUnitCreation(unitDefID, builderID, builderTeam, x, y, z, facing)
  return tenebLoot.allowCreate(unitDefID, builderTeam, builderID)
end

function gadget:FeatureCreated(featureID, allyTeamID, sourceID)
  heroOnFeatureCreated(featureID, allyTeamID, sourceID)
  -- Legion factory seeds: stamp the engine wreck so rez keeps the hero link.
  if sourceID and VA_FIELD_RECRUIT.fabByUnit and VA_FIELD_RECRUIT.fabByUnit[sourceID] then
    local hid = VA_FIELD_RECRUIT.fabByUnit[sourceID]
    VA_FIELD_RECRUIT.fabByUnit[sourceID] = nil
    VA_FIELD_RECRUIT.fabByFeature[featureID] = hid
    if Spring.SetFeatureRulesParam then
      Spring.SetFeatureRulesParam(featureID, "va_field_factory_for", hid, { public = true })
    end
    Spring.Echo("VA_FIELD_FACTORY_WRECK hero=" .. tostring(hid)
      .. " feature=" .. tostring(featureID))
  end
  tenebLoot.onFeatureCreated(featureID, allyTeamID, sourceID)
end

function gadget:FeatureDestroyed(featureID, allyTeamID)
  if VA_FIELD_RECRUIT.fabByFeature then
    VA_FIELD_RECRUIT.fabByFeature[featureID] = nil
  end
  heroOnFeatureDestroyed(featureID)
  tenebLoot.onFeatureDestroyed(featureID)
end

-- Reclaim of builder/decoy wrecks pulls durable Tenebrium into the bank.
function gadget:AllowFeatureBuildStep(builderID, builderTeam, featureID, featureDefID, step)
  if tenebLoot.tryLoot then
    local ok, err = pcall(tenebLoot.tryLoot, builderID, builderTeam, featureID, step)
    if not ok then
      Spring.Echo("VA_TENEBRIUM_LOOT_ERR " .. tostring(err))
    end
  end
  return true
end

function gadget:UnitGiven(unitID, unitDefID, newTeam, oldTeam)
  if newTeam == playerTeamID then
    local ud = UnitDefs[unitDefID]
    if isCommanderUnitDef(ud) then
      playerCommanders[unitID] = true
      doctrine.sawPlayerCom = true
    end
    -- Decoy capture (and any capture) is the standard unit-conversion path.
    heroOnUnitGiven(unitID, unitDefID, newTeam, oldTeam)
  elseif playerCommanders[unitID] then
    playerCommanders[unitID] = nil
  end
end

function gadget:UnitDestroyed(unitID, unitDefID, unitTeam)
  -- Pack mentors harvest subordinate XP *before* hero cleanup clears maps.
  if unitTeam == playerTeamID and next(packMentors) then
    local lead = Spring.GetUnitRulesParam(unitID, "va_pack_leader")
      or Spring.GetUnitRulesParam(unitID, "va_pack_id")
    lead = tostring(lead or "")
    if lead ~= "" and packMentors[lead] then
      harvestMentorXp(unitID, lead)
    elseif isWheelieDef((UnitDefs[unitDefID] or {}).name) and packMentors["spoke"] then
      harvestMentorXp(unitID, "spoke")
    end
  end
  heroOnUnitDestroyed(unitID)
  tenebLoot.onDead(unitID, unitDefID, unitTeam)
  if recordShellScar then recordShellScar(unitID, unitDefID) end
  local forceId = objectiveTargets[unitID]
  if forceId then
    objectiveTargets[unitID] = nil
    objectiveTargetsDestroyed = objectiveTargetsDestroyed + 1
    Spring.SetGameRulesParam("va_objective_destroyed", objectiveTargetsDestroyed, { public = true })
    Spring.Echo("VA_OBJECTIVE_TARGET_DOWN force=" .. forceId .. " destroyed=" .. tostring(objectiveTargetsDestroyed) .. "/" .. tostring(objectiveTargetCount))
    if not objectiveComplete and status == "active" and not terminal then
      local kind = objectiveKind()
      if VA_KINDS.capture[kind] or capture.mode then
        -- Capture: destruction only clears the pocket; hold under regrow is required.
        -- Do not auto-complete on last structure kill.
        if capture.mode and capture.phase == "clear" then
          local need = math.max(1, math.ceil(math.max(1, objectiveTargetCount) * CLEAR_FRACTION))
          if objectiveTargetsDestroyed >= need and not capture.pocketCleared then
            -- Phase advance happens on next presence check; publish progress now.
            Spring.SetGameRulesParam("va_pocket_clear_frac",
              objectiveTargetsDestroyed / math.max(1, objectiveTargetCount), { public = true })
          end
        end
      elseif objectiveTargetsDestroyed >= objectiveTargetCount then
        onObjectiveComplete("target_destroyed")
      end
    end
  end
  -- Drop 4: structure/vault marks tick via the registry (never the primary pool).
  local secId, g, newlyDone = MarksLib.onTargetDestroyed(marks, unitID)
  if newlyDone and g then
    local sx, _, sz = Spring.GetUnitPosition(unitID)
    if sx then
      Spring.SetGameRulesParam("va_secondary_last_x", sx, { public = true })
      Spring.SetGameRulesParam("va_secondary_last_z", sz, { public = true })
    end
    marksCommit("secondary_complete", secId)
    Spring.Echo("VA_SECONDARY_COMPLETE id=" .. tostring(secId)
      .. " required=" .. tostring(g.required == true)
      .. " left=" .. tostring(MarksLib.requiredLeft(marks)))
    if SendToUnsynced and sx then
      local label = tostring(g.label or g.description or secId)
      SendToUnsynced("VERDANCE_BEAT", "narrative", sx, sz,
        "SECONDARY|" .. label .. "|640|4.5|1", "")
    end
    vaMaybeAnnounceAllDone()
  elseif secId then
    marksCommit("secondary_changed", secId)
  end
  if playerCommanders[unitID] then
    playerCommanders[unitID] = nil
    if doctrine.sawPlayerCom and next(playerCommanders) == nil and status == "active" and not terminal then
      Spring.Echo("VA_COMMANDER_LOST")  -- a fact for the result; the sortie goes on
    end
  end
end

function gadget:GameOver(winningAllyTeams)
  if terminal then return end
  -- The engine ended the game without a manifest (resign / external). Record the facts.
  setTerminal("closed", "gameover_external")
end
VFS.Include("luarules/gadgets/include/campaign/logistics.lua", gadget)
VFS.Include("luarules/gadgets/include/campaign/devcmd.lua", gadget)

function gadget:TextCommand(command)
  if type(command) ~= "string" then return false end
  -- Allow full-string commands with args (vatnb 8, vabrutecrash 4, vacrewconfirm …).
  if command:match("^vatnb") or command:match("^vabrutecrash")
      or command:match("^vacrewconfirm") or command:match("^vapack") then
    if command:match("^vacrewconfirm") then
      local rest = command:match("^vacrewconfirm[%s:]+(.+)$") or ""
      local picks = {}
      for id in string.gmatch(rest, "[%w_]+") do picks[#picks + 1] = id end
      VA_CREW_confirm(picks)
      return true
    end
    if runVerdanceCommand(command) then return true end
  end
  local cmd = command:match("^(%S+)")
  if not cmd then return false end
  if runVerdanceCommand(cmd) then return true end
  return false
end

function gadget:RecvLuaMsg(msg, playerID)
  if type(msg) ~= "string" or msg:sub(1, 7) ~= "VA_CMD:" then return end
  local cmd = msg:sub(8)
  if cmd:match("^vahotdrop ") then
    VA_HOT_drop(cmd:sub(11))
    return true
  end
  if type(cmd) == "string" and cmd:match("^vacrewconfirm") then
    local rest = cmd:match("^vacrewconfirm[%s:]+(.+)$") or ""
    local picks = {}
    for id in string.gmatch(rest, "[%w_]+") do picks[#picks + 1] = id end
    VA_CREW_confirm(picks)
    return
  end
  if (cmd == "manifest" or cmd:match("^extract:")) and GG.VA_ExfilCmd then
    GG.VA_ExfilCmd(cmd)
    return true
  end
  if not runVerdanceCommand(cmd) then
    Spring.Echo("VA_UNKNOWN_CMD " .. tostring(cmd))
  end
end
