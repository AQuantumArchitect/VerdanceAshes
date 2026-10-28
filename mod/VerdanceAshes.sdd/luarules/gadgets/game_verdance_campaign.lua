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
-- code; everything else runs from the call-ins below, after every part is in. The call-ins are
-- short on purpose: each step is a named function in its part ("Called by gadget:GameFrame.").
--
--   state           the sortie itself (mission, zone map, status, teams), the marks registry and the JSON helpers
--   result          the sortie result: every JSON part, chunked logging, the headless finish
--   mission_data    reading the mission seed and the zone map
--   units           unit-def helpers and metal spots
--   mentors         pack mentors (Spoke, the leads): subordinate XP and field effects
--   hero_spawn      a hero's unit on the field: modifiers, tags, registration, auras
--   spawn           placing units: dry landing, standable ground, spawnOneUnit / spawnUnitSpec
--   crew            the company on the field: roster, hero packs, bonds, crew confirm, the hot drop
--   field_recruits  wild heroes: recruit wrecks, field factories, unit printers
--   setup           the playable setup: camps, forces and the player's start
--   telemetry       zone cells, per-zone metrics, dev telemetry and the headless/profiling options
--   waterline       the waterline (hydrology) and zone flow
--   translation     the translation matrix packet
--   objectives      the objective: kind and mode, the pad, living-shell claims, presence / fortify / wipe / soft clock
--   reinforcements  enemy response waves and where they enter
--   heroes          hero lifecycle: down, wreck, rez, lost, recovered, field joins
--   beats           in-mission beats (authored triggers)
--   terminal        ending the sortie: the terminal crunch and the GG entry points
--   start           start of the sortie: doctrine, commanders, perks, start resources, Tenebrium
--   logistics       mercenary logistics: the deploy kit, pending deliveries, the brute crash
--   devcmd          the /luarules va* playtest commands, the headless start and debug auto-progress
-- ---------------------------------------------------------------------------
VFS.Include("luarules/gadgets/include/campaign/state.lua", gadget)
VFS.Include("luarules/gadgets/include/campaign/result.lua", gadget)
VFS.Include("luarules/gadgets/include/campaign/mission_data.lua", gadget)
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
VFS.Include("luarules/gadgets/include/campaign/logistics.lua", gadget)
VFS.Include("luarules/gadgets/include/campaign/devcmd.lua", gadget)

-- The sortie goes live (GameStart in a played session, frame 1 or /vastart in a headless one).
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

-- The sortie starts here: read the seed, set every part up, publish the bridge's rules.
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
  armDevTelemetry(modOptions)
  readProfilingOptions(modOptions)
  local arc = mission.arcProfile or {}
  configureDoctrine(arc)
  resolveTeams()
  debugAutoProgressAllowed = headless.fastWin or truthy(modOptions.va_debug_autoprogress)
  -- The player's team is a fact other gadgets need (craft_xp, veterancy,
  -- unit_behavior resolve it at GameStart); publish it once, clamped.
  Spring.SetGameRulesParam("va_player_team", playerTeamID, { public = true })
  configureHeadlessClient(modOptions)
  configureZoneFlowSample(modOptions)
  -- Escalation: mission.escalation.mode / waves.max wins; modoption force still works.
  local profiling = headless.autoStart or balance.exportFrame or (#fib.milestones > 0)
  local escMode = configureWaves(modOptions, arc, profiling)
  placeTargetAndPad()
  configureBeats(modOptions, profiling)
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

-- Every frame, in this order. Each tick lives in the part named in its own comment.
function gadget:GameFrame(frame)
  if vaWarBanks and frame >= 5 then vaApplyWarBanks() end
  -- Field-recruit wreck seeds: kill the live unit so BAR leaves a normal rez corpse.
  tickFieldRecruitPendingDeath(frame)
  tickStorageRefresh(frame)
  if vaWaterTarget and frame % VA_WATER_TICK == 0 then
    vaStepWaterline()
  end
  tickHeadlessStart(frame)
  if vaZoneFlowSample > 0 and frame > 0 and frame % vaZoneFlowSample == 0 then
    vaSampleZoneFlow()
  end
  tickPendingDeliveries(frame)
  tickProfiling(frame)
  tickTenebrium(frame)
  tickPrinterUnits(frame)
  tickCommanderSweeps(frame)
  tickShellClaims(frame)
  tickObjectiveChecks(frame)
  tickWaves(frame)
  tickDebugAutoProgress(frame)
  tickDevTelemetry(frame)
end

function gadget:UnitCommand(unitID, unitDefID, unitTeam, cmdID, cmdParams, cmdOpts, cmdTag)
  if not devTel.enabled then return end
  if unitTeam ~= playerTeamID then return end
  local key = classifyCmd(cmdID)
  devTel.cmds[key] = (devTel.cmds[key] or 0) + 1
  devTel.cmdTotal = devTel.cmdTotal + 1
end

function gadget:UnitCreated(unitID, unitDefID, unitTeam, builderID)
  trackPlayerCommanderCreated(unitID, unitDefID, unitTeam)
  -- A rez bot consuming a tracked hero wreck brings the hero back.
  heroOnUnitCreated(unitID, unitDefID, unitTeam, builderID)
  -- Factory bay rez/capture landing on the player team.
  maybeFieldFactoryJoin(unitID, unitDefID, unitTeam, builderID)
  mentorsOnUnitCreated(unitID, unitDefID, unitTeam)
  heroAurasOnUnitCreated(unitID, unitDefID, unitTeam)
  -- WO-043c: charge / stamp Tenebrium for build-power units.
  tenebLoot.onUnitCreated(unitID, unitDefID, unitTeam, builderID)
end

function gadget:AllowUnitCreation(unitDefID, builderID, builderTeam, x, y, z, facing)
  return tenebLoot.allowCreate(unitDefID, builderTeam, builderID)
end

function gadget:FeatureCreated(featureID, allyTeamID, sourceID)
  heroOnFeatureCreated(featureID, allyTeamID, sourceID)
  fieldFactoryOnFeatureCreated(featureID, sourceID)
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
  mentorsOnUnitDestroyed(unitID, unitDefID, unitTeam)
  heroOnUnitDestroyed(unitID)
  tenebLoot.onDead(unitID, unitDefID, unitTeam)
  if recordShellScar then recordShellScar(unitID, unitDefID) end
  objectiveTargetDestroyed(unitID)
  marksOnUnitDestroyed(unitID)
  playerCommanderDestroyed(unitID)
end

function gadget:GameOver(winningAllyTeams)
  if terminal then return end
  -- The engine ended the game without a manifest (resign / external). Record the facts.
  setTerminal("closed", "gameover_external")
end

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
