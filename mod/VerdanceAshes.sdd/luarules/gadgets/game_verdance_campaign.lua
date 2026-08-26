local gadget = gadget

function gadget:GetInfo()
  return {
    name = "Verdance Campaign Bridge",
    desc = "Campaign bridge and objective automation for Verdance's Ashes",
    author = "ChatGPT / Claude / Luke Spooner",
    date = "2026-07-05",
    license = "GPL v2 or later",
    layer = 0,
    enabled = true,
  }
end

if not gadgetHandler:IsSyncedCode() then
  -- Unsynced bridge: forward synced telemetry/mission events to LuaUI widgets.
  -- Also owns client-side pause requests (start of sortie + end of sortie).
  local function isHeadless()
    local mo = Spring.GetModOptions and Spring.GetModOptions() or {}
    local v = mo.va_headless_autostart
    if v == true or v == 1 then return true end
    if type(v) == "string" then
      v = v:lower()
      return v == "1" or v == "true" or v == "yes" or v == "enabled"
    end
    return false
  end

  local function requestPause(why)
    if isHeadless() then return end
    -- SendCommands is the portable client pause path on Recoil/BAR.
    pcall(Spring.SendCommands, "pause 1")
    Spring.Echo("VA_PAUSE " .. tostring(why or "request"))
  end

  local startPaused = false
  local endPaused = false

  local function requestUnpause(why)
    if isHeadless() then return end
    pcall(Spring.SendCommands, "pause 0")
    Spring.Echo("VA_UNPAUSE " .. tostring(why or "request"))
  end

  function gadget:Initialize()
    gadgetHandler:AddSyncAction("VERDANCE_TELEMETRY", function(_, jsonStr)
      if Script.LuaUI and Script.LuaUI.VerdanceTelemetry then
        Script.LuaUI.VerdanceTelemetry(jsonStr)
      end
    end)
    gadgetHandler:AddSyncAction("VERDANCE_MISSION_EVENT", function(_, eventStatus, reason)
      -- Terminal outcomes (and objective_complete is mid-sortie, not end).
      if eventStatus == "victory" or eventStatus == "defeat" or eventStatus == "partial" then
        if not endPaused then
          endPaused = true
          requestPause("sortie_end:" .. tostring(eventStatus) .. ":" .. tostring(reason or ""))
        end
      elseif eventStatus == "continue_start" then
        -- Mode A: unpause briefly then re-pause for next briefing card.
        endPaused = false
        requestUnpause("continue_start")
        requestPause("continue_briefing:" .. tostring(reason or ""))
      end
      if Script.LuaUI and Script.LuaUI.VerdanceMissionEvent then
        Script.LuaUI.VerdanceMissionEvent(eventStatus, reason)
      end
    end)
    gadgetHandler:AddSyncAction("VERDANCE_HERO_EVENT", function(_, event, heroId, name, critical, x, z)
      if Script.LuaUI and Script.LuaUI.VerdanceHeroEvent then
        Script.LuaUI.VerdanceHeroEvent(event, heroId, name, critical, x, z)
      end
    end)
    gadgetHandler:AddSyncAction("VERDANCE_BEAT", function(_, kind, a, b, c, d)
      if Script.LuaUI and Script.LuaUI.VerdanceBeat then
        Script.LuaUI.VerdanceBeat(kind, a, b, c, d)
      end
    end)
  end

  function gadget:GameStart()
    if not startPaused then
      startPaused = true
      requestPause("sortie_start")
    end
  end

  -- Backup: some loads fire GameStart before the client is ready to honor pause.
  function gadget:GameFrame(frame)
    if not startPaused and frame >= 0 and frame <= 2 then
      startPaused = true
      requestPause("sortie_start_frame")
    end
  end

  function gadget:Shutdown()
    gadgetHandler:RemoveSyncAction("VERDANCE_TELEMETRY")
    gadgetHandler:RemoveSyncAction("VERDANCE_MISSION_EVENT")
    gadgetHandler:RemoveSyncAction("VERDANCE_HERO_EVENT")
    gadgetHandler:RemoveSyncAction("VERDANCE_BEAT")
  end
  return
end

local mission
local zoneMap
local status = "inactive"
local holdFrames = 0
local debugAutoProgress = 0
local spawnedCompanions = {}
local lastProgressFrame = 0
-- Packed tables: keep main-chunk locals under Lua 5.1's 200-local hard limit
-- (file failed to load with: main function has more than 200 local variables).
local headless = { autoStart = false, fastWin = false, quit = false, started = false, quitFrame = nil }
local playableSetupSpawned = false
local balance = { exportFrame = nil, exported = false, quitAfterExport = false }
local fib = { milestones = {}, idx = 1, quitAfterLast = false }

-- Objective automation
local CHECK_PERIOD = 30                 -- frames between objective checks
local EXTRACTION_HOLD_FRAMES = 450      -- 15s presence in extraction zone
local PRESENCE_HOLD_DEFAULT = 900       -- 30s hold for seize/gate objectives
local WIPE_GRACE_FRAMES = 900           -- no wipe-defeat before 30s
-- Dev telemetry: one table so GameFrame stays under Lua 5.1's 60-upvalue cap.
-- Armed by singleplayer/.../generated/dev_telemetry_flag.lua or mission.devTelemetry.
local devTel = {
  enabled = false,
  period = 150,          -- ~5s @ 30fps
  lastSample = -999999,
  cmds = { move = 0, fight = 0, attack = 0, patrol = 0, build = 0, reclaim = 0, guard = 0, other = 0 },
  cmdTotal = 0,
}

local DESTRUCTION_KINDS = {
  strike_relay = true,
  destroy_key_structure = true,
  economy_disrupt = true,
  hive_clear_or_bypass = true,
}
-- Presence / capture kinds: claim a living shell node (clear pocket + hold under regrow).
local PRESENCE_KINDS = { seize_lane = true, gate_control = true, hold_plateau = true }
-- Capture = clear pocket then hold under regrow pressure (not empty-grass stand).
local CAPTURE_KINDS = { seize_lane = true, gate_control = true, hold_plateau = true }
local CHOICE_KINDS = { choose_target_then_extract = true }

local playerTeamID = 0
local playerAllyTeamID = 0
local gaiaTeamID = -1
local gaiaAllyTeamID = -1
local teamAllyTeam = {}                 -- teamID -> allyTeamID
local teamFaction = {}                  -- teamID -> world faction (nullmercs/armada/cortex/...)
local objectiveTargets = {}             -- unitID -> forceId (objective_target structures)
local objectiveTargetCount = 0
local objectiveTargetsDestroyed = 0
local targetForceStructures = {}        -- forceId -> live structure count
local objectiveComplete = false
local objectiveBypassed = false
local chosenTargetForceId = nil
local zoneHoldFrames = 0
local extractionHoldFrames = 0
local extractionClean = true
local playerLeftExtraction = false
local playerCommanders = {}             -- unitID -> true

-- Pillar B: in-mission dynamism (escalation waves, hot extraction, callable
-- merc reinforcements). Enemy reinforcements are inferred from the enemy team's
-- own composition, so no seed/compiler change is needed. Disabled during
-- headless/balance profiling unless va_escalation forces it on.
local objectiveTeamID = nil             -- team the objective camp belongs to
local mercTeamID = nil                  -- allied Null Merc foothold team, if any
local mercsAllied = false
local mercWaveUsed = false
-- Waves + doctrine packed (Lua 5.1 main-chunk local budget).
local waves = { enabled = false, interval = 2700, nextFrame = 1800, spawned = 0, max = 4, baseSize = 4 }
-- Raid / Arc A tactics doctrine: no player commander. Sweep engine free coms;
-- static_bases also sweeps enemy free commanders (prevents commander soup).
local doctrine = {
  strikeTeam = false,
  commanderSwept = false,
  sweepEnemy = false,
  enemySwept = false,
  hotExtractOnly = false,
  playerComsAllowed = 0,
  sawPlayerCom = false,
  -- Act tech gate (Drop 2): the seed's techPolicy caps what the player may
  -- BUILD. Grants (seed spawns / waves / continues via Spring.CreateUnit)
  -- never pass AllowUnitCreation; resurrection is always allowed.
  techGateEnabled = false,
  techMaxLevel = 3,
  techBuildStructures = true,
  actNumber = 0,
  actMode = "",
  techDenials = 0,
  techLastDenyFrame = -999,
}
local printerUnits = {}  -- unitID -> { metal/frame, energy/frame, team }
-- WO-043c: Tenebrium is a full in-mission resource (not engine metal).
-- • Every unit with build power costs ≥1 Tnb to finish; that stake lives on the unit.
-- • Wrecks / heaps / debris keep the stake until reclaimed (→ bank) or truly gone (→ lost).
-- • Bank: infinite storage, display-only number (GameRulesParam va_tenebrium_bank).
-- • Q7 (resource scarcity) reads this stock. Armada crisis: faction bank locked at 0
--   (they spent it on a continent of farming decoy coms for wind/solar/converters).
local tenebLoot = {
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
  armadaCrisis = true,       -- default on: Armada has no Tnb
  factionBank = { armada = 0, cortex = 0 },
  enabled = true,
}
-- Named hero roster (Fire Emblem doctrine): heroes leave wrecks; a rez bot can
-- bring them back mid-mission. A destroyed wreck is permadeath - and a mission
-- defeat when the hero is mission-critical (the player character, Ketha).
local heroes = {}             -- heroId -> record (state machine below)
local heroByUnitID = {}       -- live unitID -> heroId
local heroPendingWreck = {}   -- dead unitID -> heroId (awaiting corpse FeatureCreated)
local heroByFeatureID = {}    -- wreck featureID -> heroId
local wreckConsumedByRez = {} -- featureID -> true when a resurrection consumed it
local HERO_WRECK_TIMEOUT = 90 -- frames a corpse may lag the death (BAR corpse-link window)
-- Resurrection often destroys the wreck feature before UnitCreated runs; hold
-- permadeath for a short grace so the rezzed unit can reclaim the hero identity.
local HERO_REZ_GRACE = 60     -- 2s at 30fps
local HERO_REZ_MATCH_DIST = 450 -- elmos; rez spawns on the wreck
-- In-mission beats: data-driven WC3-style triggers authored into the seed.
local beats = {}              -- compiled pending beats (all fire once)
local beatsEnabled = false
local beatFiredSet = {}       -- beatId -> true (afterBeat prerequisites)
local secondaryObjectives = {}
-- Drop 4 escalation (ONE table — Lua 5.1 local budget): secondary-objective
-- ledger + strong-objective state. Works with role=objective_secondary book
-- in here (never the primary pool); required groups gate victory alongside
-- the primary objective. purge = "clear the board": every armada/cortex team
-- on the field must be emptied before the mission can end in victory.
local extraObj = {
  targets = {},        -- unitID -> secondary group id
  groups = {},         -- groupId -> {total, destroyed, required, done, label}
  order = {},          -- group ids in seed order (result JSON + HUD params)
  requiredLeft = 0,
  purge = false,
  purgeDone = false,
  purgeTeams = {},     -- teamID -> true
  announced = false,   -- all-objectives-done broadcast latch
}
-- No-fail stalemate guard: a player with no mobile combat power and no way to
-- build any can neither win nor lose; end it instead of hanging forever.
local stalemate = { frames = 0, limit = 5400, warned = false }  -- 3 min force-spent ends mission
local RAID_CREDIT_FRACTION = 0.6        -- wreck this share of the works to credit the raid
local CLEAR_FRACTION = 0.6              -- pocket clear threshold for capture claims
local raidWaveThresholds = { 0.15, 0.35, 0.55, 0.8 }  -- damage % that summons each QRF wave
-- Capture claim state (one table — Lua 5.1 local budget).
-- Fantasy: clear living-shell pocket, then hold it while regrow pressure tries to retake.
local capture = {
  mode = false,             -- armed when living shell + CAPTURE_KIND (or captureMode stamp)
  phase = "idle",           -- idle | clear | hold | claimed
  pocketCleared = false,
  nodeClaimed = false,
  regrowNextFrame = 0,
  regrowInterval = 450,     -- ~15s between pressure pulses during hold
  regrowWaves = 0,
  regrowMax = 6,
  regrowBaseSize = 3,
}
local terminal = false
local terminalReason = ""
-- Mode A chapter tracking (declared early so resultJson can close over them)
local sortieChapter = 1
local softContinueArmed = false
local targetZoneRect = nil              -- {x1, z1, x2, z2} in elmos
local extractionZoneRect = nil
local debugAutoProgressAllowed = false
-- Verification harness state, consolidated into ONE table: Lua 5.1 caps a
-- function at 60 upvalues, and gadget:GameFrame already rides close to it.
-- va_test_killobjective_frame / va_test_killhero_frames=400,3600 /
-- va_test_rezwreck_frame / va_test_destroywreck_frame / va_test_teleport_extract_frame
-- va_test_techgate_frame (Drop 3: spawns a con bot + echoes gate verdicts)
-- va_test_secondary_frame (Drop 4: wrecks all secondary marks)
local testHooks = {
  killObjectiveFrame = nil, killObjectiveDone = false,
  killHeroFrames = {}, killHeroIdx = 1,
  rezWreckFrame = nil, rezWreckDone = false,
  destroyWreckFrame = nil, destroyWreckDone = false,
  teleportExtractFrame = nil, teleportExtractDone = false,
  techGateFrame = nil, techGateDone = false,
  killSecondaryFrame = nil, killSecondaryDone = false,  -- Drop 4: va_test_secondary_frame
  hydroFrame = nil, hydroTo = nil, hydroDone = false, hydroProbe = nil,
}

local function clamp(x, lo, hi)
  if x < lo then return lo end
  if x > hi then return hi end
  return x
end

local function truthy(v)
  if v == true or v == 1 then return true end
  if type(v) == "string" then
    v = v:lower()
    return v == "1" or v == "true" or v == "yes" or v == "enabled"
  end
  return false
end

local function esc(s)
  s = tostring(s or "")
  s = s:gsub('\\', '\\\\')
  s = s:gsub('"', '\\"')
  return s
end

local function jstr(s) return '"' .. esc(s) .. '"' end
local function jnum(x, digits)
  x = tonumber(x) or 0
  if digits then return string.format("%." .. digits .. "f", x) end
  return tostring(math.floor(x + 0.5))
end

-- Several cold-path helpers below are gadget-env globals (no `local`): the main
-- chunk rides Lua 5.1's 200-local cap, and each global here frees one slot.
function heroStatesJson()
  local parts = {}
  for id, rec in pairs(heroes) do
    parts[#parts + 1] = jstr(id) .. ':{' .. table.concat({
      '"name":' .. jstr(rec.name or id),
      '"state":' .. jstr(rec.state or "alive"),
      '"missionCritical":' .. tostring(rec.missionCritical == true),
    }, ',') .. '}'
  end
  return '{' .. table.concat(parts, ',') .. '}'
end

function heroResultsJson()
  local parts = {}
  for id, rec in pairs(heroes) do
    -- peakXp is sticky across death; export max so campaign never loses farmed XP.
    local xpOut = math.max(tonumber(rec.peakXp) or 0, tonumber(rec.lastXp) or 0)
    parts[#parts + 1] = jstr(id) .. ':{' .. table.concat({
      '"status":' .. jstr(rec.result or (rec.everDown and "wounded" or "survived")),
      '"wasDown":' .. tostring(rec.everDown == true),
      '"xp":' .. jnum(xpOut, 4),
      '"level":' .. tostring(tonumber(rec.level) or 1),
      '"rank":' .. jstr(rec.rank or "Runner"),
    }, ',') .. '}'
  end
  return '{' .. table.concat(parts, ',') .. '}'
end

-- DCO-01 / WO-006: named character outcomes for the story engine characters{} registry.
-- Maps gadget hero FSM results onto namedOutcomes: dead | recovered | wounded.
function namedOutcomesJson()
  local parts = {}
  for id, rec in pairs(heroes) do
    local raw = rec.result or (rec.everDown and "wounded" or "survived")
    local outcome = nil
    local cause = rec.diedHow or ""
    if raw == "dead" then
      outcome = "dead"
      if cause == "" then cause = "wreck_destroyed" end
    elseif raw == "wounded" then
      -- recovered in-match via rez vs left wounded at game end
      if rec.everDown and rec.state == "alive" then
        outcome = "recovered"
        cause = "reclaimed_friendly"
      else
        outcome = "wounded"
        if cause == "" then cause = "match_end_wreck" end
      end
    end
    if outcome then
      parts[#parts + 1] = '{' .. table.concat({
        '"charId":' .. jstr(id),
        '"outcome":' .. jstr(outcome),
        '"cause":' .. jstr(cause),
      }, ',') .. '}'
      Spring.Echo("VA_NAMED_" .. string.upper(outcome == "dead" and "DEAD" or (outcome == "recovered" and "RECOVERED" or "WOUNDED"))
        .. " " .. id .. (cause ~= "" and (" cause=" .. cause) or ""))
    end
  end
  return '[' .. table.concat(parts, ',') .. ']'
end

local function publishHeroRules()
  Spring.SetGameRulesParam("va_heroes_json", heroStatesJson(), { public = true })
end

local function readMission()
  local ok, data = pcall(VFS.Include, "singleplayer/verdance_ashes/generated/va_current.lua")
  if ok and type(data) == "table" then return data end
  ok, data = pcall(VFS.Include, "singleplayer/verdance_ashes/generated/va_001.lua")
  if ok and type(data) == "table" then return data end
  return {
    schemaVersion = "0.6",
    campaignId = "verdance_ashes",
    missionId = "va_missing_seed",
    missionNumber = 0,
    pathSignal = "B",
    zone = "Unknown",
    objective = { requiredFrames = 600, description = "Missing mission seed fallback" },
    economy = { metalIncome = 0, energyIncome = 0, buildPower = 0 },
    graph = {},
    reputation = {},
    companions = {}
  }
end

local function readZoneMap()
  vaZoneCellIndexCache = nil    -- rebuild the cell index for the new map
  vaZoneAdjacencyCache = nil    -- and the border graph derived from it
  local ok, data = pcall(VFS.Include, "singleplayer/verdance_ashes/generated/zone_map_current.lua")
  if ok and type(data) == "table" then return data end
  return nil
end

local function zoneCount()
  if not zoneMap or type(zoneMap.zones) ~= "table" then return 0 end
  return #zoneMap.zones
end

local function normalizedToElmos(v, size)
  v = tonumber(v) or 0
  if v <= 1 then return math.floor(v * (size or 0) + 0.5) end
  return math.floor(v + 0.5)
end

function zoneMapJson()
  return table.concat({
    '"mapId":' .. jstr(zoneMap and zoneMap.mapId or ""),
    '"mapName":' .. jstr(zoneMap and zoneMap.mapName or ""),
    '"coordinateSystem":' .. jstr(zoneMap and zoneMap.coordinateSystem or ""),
    '"zoneCount":' .. jnum(zoneCount())
  }, ',')
end

function echoZones()
  if not zoneMap or type(zoneMap.zones) ~= "table" then
    Spring.Echo("VA_ZONES none loaded")
    return
  end
  local sx = Game.mapSizeX or 0
  local sz = Game.mapSizeZ or 0
  local cellIndex = vaZoneCellIndex()
  Spring.Echo("VA_ZONES mapId=" .. tostring(zoneMap.mapId or "unknown") .. " map=" .. tostring(Game.mapName or "unknown") .. " count=" .. tostring(#zoneMap.zones) .. " size=" .. tostring(sx) .. "x" .. tostring(sz)
    .. " cells=" .. tostring(cellIndex and cellIndex.claimed or 0) .. " res=" .. tostring(cellIndex and cellIndex.res or 0))
  for _, z in ipairs(zoneMap.zones) do
    local b = z.bounds or {}
    local x1 = normalizedToElmos(b.xMin, sx)
    local x2 = normalizedToElmos(b.xMax, sx)
    local z1 = normalizedToElmos(b.zMin, sz)
    local z2 = normalizedToElmos(b.zMax, sz)
    Spring.Echo("VA_ZONE " .. tostring(z.zoneId or "?") .. " label=" .. tostring(z.label or "") .. " bounds=" .. x1 .. "," .. z1 .. ".." .. x2 .. "," .. z2)
  end
end

local function companionCounts()
  local total = 0
  local alive = 0
  if mission and mission.companions then total = #mission.companions end
  if total == 0 then return 0, 0 end
  for _, comp in ipairs(mission.companions) do
    if comp._unitID and Spring.ValidUnitID(comp._unitID) and not Spring.GetUnitIsDead(comp._unitID) then
      alive = alive + 1
    elseif not comp._unitID then
      alive = alive + 1
    end
  end
  return alive, total
end

function primaryCompanionJson()
  local c = mission and mission.companions and mission.companions[1] or {}
  return table.concat({
    '"id":' .. jstr(c.id or ""),
    '"displayName":' .. jstr(c.displayName or ""),
    '"unitDefName":' .. jstr(c.unitDefName or ""),
    '"xp":' .. jnum(c.xp or 0, 4),
    '"morale":' .. jnum(c.morale or 0, 2),
    '"loyalty":' .. jnum(c.loyalty or 0, 2),
    '"stress":' .. jnum(c.stress or 0, 2),
    '"autonomy":' .. jnum(c.autonomy or 0, 4),
    '"commandMode":' .. jstr(c.commandMode or "hybrid")
  }, ',')
end

function graphJson()
  local g = mission.graph or {}
  -- q7 = Tenebrium scarcity axis (1=dry, 0=abundant). Live bank softens readout.
  local q7 = tonumber(g.q7_resource_scarcity or g.q7_scarcity or 0) or 0
  local bank = tonumber(tenebLoot.bank) or 0
  local liveQ7 = q7
  if bank > 0 then
    liveQ7 = math.max(0, math.min(1, q7 - math.min(0.35, bank * 0.04)))
  end
  return table.concat({
    '"q0_armada_cortex":' .. jnum(g.q0_armada_cortex or 0, 4),
    '"q2_void_structure":' .. jnum(g.q2_void_structure or 0, 4),
    '"q3_biogenesis_memory":' .. jnum(g.q3_biogenesis_memory or 0, 4),
    '"q4_ai_human":' .. jnum(g.q4_ai_human or 0, 4),
    '"q6_contested":' .. jnum(g.q6_contested or 0, 4),
    '"q6_independent":' .. jnum(g.q6_independent or 0, 4),
    '"q7_scarcity":' .. jnum(liveQ7, 4),
    '"q7_resource_scarcity":' .. jnum(liveQ7, 4),
    '"tenebriumBank":' .. jnum(bank, 0),
    '"armadaTenebriumCrisis":' .. tostring(tenebLoot.armadaCrisis == true)
  }, ',')
end

function reputationJson()
  -- WO-002: clans collapsed into nullmercs. Prefer nullmercs; if only clans is
  -- present on an old seed, emit it under nullmercs (never emit both as distinct).
  local r = mission.reputation or {}
  local merc = r.nullmercs
  if merc == nil then merc = r.clans end
  merc = merc or 0
  return table.concat({
    '"armada":' .. jnum(r.armada or 0, 2),
    '"cortex":' .. jnum(r.cortex or 0, 2),
    '"nullmercs":' .. jnum(merc, 2),
    '"sev":' .. jnum(r.sev or 0, 2)
  }, ',')
end

function economyJson()
  local e = mission.economy or {}
  return table.concat({
    '"metalIncome":' .. jnum(e.metalIncome or 0, 2),
    '"energyIncome":' .. jnum(e.energyIncome or 0, 2),
    '"buildPower":' .. jnum(e.buildPower or 0, 2)
  }, ',')
end

local objectiveCompleteHow = ""

local function extractionStatusString()
  if not terminal then return "" end
  if extractionHoldFrames >= EXTRACTION_HOLD_FRAMES then
    return extractionClean and "clean" or "contested"
  end
  return ""
end

-- Objective credit is only reported on non-defeat outcomes: the story engine
-- treats any completed/destroyed objective as a success signal for graph deltas.
local function objectiveCredited()
  return objectiveComplete and status ~= "defeat"
end

function destroyedObjectiveIdsJson()
  local oid = mission.objective and mission.objective.id
  -- Capture claims (node_claimed / zone_held) still count as objective credit for graph.
  if oid and objectiveCredited() and objectiveCompleteHow ~= "zone_held" and objectiveCompleteHow ~= "node_claimed" then
    return '[' .. jstr(oid) .. ']'
  end
  -- Capture path: report claimed node as destroyedObjective so zone flip + graph fire.
  if oid and objectiveCredited() and (objectiveCompleteHow == "node_claimed" or objectiveCompleteHow == "zone_held") then
    return '[' .. jstr(oid) .. ']'
  end
  return '[]'
end

function objectiveResultsJson()
  local obj = mission.objective or {}
  if not obj.id then return '[]' end
  local objStatus = "incomplete"
  if objectiveCredited() then
    if objectiveCompleteHow == "node_claimed" then
      objStatus = "claimed"
    elseif objectiveCompleteHow == "zone_held" then
      objStatus = "complete"
    else
      objStatus = "destroyed"
    end
  end
  local damage = 0
  if objectiveTargetCount > 0 then
    damage = objectiveTargetsDestroyed / objectiveTargetCount
  elseif objectiveCredited() then
    damage = 1
  end
  return '[{' .. table.concat({
    '"objectiveId":' .. jstr(obj.id),
    '"kind":' .. jstr(obj.kind or ""),
    '"status":' .. jstr(objStatus),
    '"damage":' .. jnum(damage, 3),
  }, ',') .. '}]'
end

-- Drop 4: secondary-objective ledger for the campaign engine (bonus marks pay
-- merc standing; required marks are implied by any victory that got home).
function secondaryResultsJson()
  local parts = {}
  for _, sid in ipairs(extraObj.order) do
    local g = extraObj.groups[sid] or {}
    parts[#parts + 1] = '{' .. table.concat({
      '"id":' .. jstr(sid),
      '"required":' .. tostring(g.required == true),
      '"completed":' .. tostring(g.done == true),
      '"total":' .. jnum(g.total or 0),
      '"destroyed":' .. jnum(g.destroyed or 0),
    }, ',') .. '}'
  end
  return '[' .. table.concat(parts, ',') .. ']'
end

-- Pillar C: the player's surviving mobile combat units by def, so the campaign
-- engine can carry a veteran cadre forward and attrite losses. Self-contained
-- (the shared unit helpers are defined further down, after this function).
-- Also aggregates loan-pack HP quality for broker settle (contract v2 loanUnitHp).
function playerSurvivorsJson()
  local counts = {}
  local units = Spring.GetTeamUnits(playerTeamID) or {}
  for i = 1, #units do
    local uID = units[i]
    local dID = Spring.GetUnitDefID(uID)
    local ud = dID and UnitDefs[dID]
    if ud then
      local structure = ud.isBuilding or ud.isFactory or (ud.speed == 0)
      local commander = ud.customParams and ud.customParams.iscommander
      local fights = ud.canAttack or (ud.weapons and #ud.weapons > 0)
      if (not structure) and (not commander) and fights then
        counts[ud.name] = (counts[ud.name] or 0) + 1
      end
    end
  end
  local parts = {}
  for name, c in pairs(counts) do parts[#parts + 1] = jstr(name) .. ':' .. jnum(c) end
  return '{' .. table.concat(parts, ',') .. '}'
end

function loanUnitHpJson()
  -- unitDef -> { count, avgHpFrac, minHpFrac } for units tagged va_loan_package
  local bags = {}
  local units = Spring.GetTeamUnits(playerTeamID) or {}
  for i = 1, #units do
    local uID = units[i]
    local loan = Spring.GetUnitRulesParam and Spring.GetUnitRulesParam(uID, "va_loan_package")
    if loan == 1 or loan == true or loan == "1" then
      local dID = Spring.GetUnitDefID(uID)
      local ud = dID and UnitDefs[dID]
      if ud and ud.name then
        local hp, maxHp = Spring.GetUnitHealth(uID)
        maxHp = tonumber(maxHp) or 0
        hp = tonumber(hp) or 0
        local frac = (maxHp > 0) and (hp / maxHp) or 0
        local b = bags[ud.name]
        if not b then
          b = { count = 0, sum = 0, min = 1 }
          bags[ud.name] = b
        end
        b.count = b.count + 1
        b.sum = b.sum + frac
        if frac < b.min then b.min = frac end
      end
    end
  end
  local parts = {}
  for name, b in pairs(bags) do
    local avg = (b.count > 0) and (b.sum / b.count) or 0
    parts[#parts + 1] = jstr(name) .. ':{'
      .. '"count":' .. jnum(b.count)
      .. ',"avgHpFrac":' .. jnum(avg, 3)
      .. ',"minHpFrac":' .. jnum(b.min, 3)
      .. '}'
  end
  return '{' .. table.concat(parts, ',') .. '}'
end

-- Living-shell scar events this sortie (occupation model lock — wrath not listed).
local shellScarEvents = {}
local function recordShellScar(unitID, unitDefID)
  if not unitID then return end
  local role = Spring.GetUnitRulesParam and Spring.GetUnitRulesParam(unitID, "va_force_role")
  local pocket = Spring.GetUnitRulesParam and Spring.GetUnitRulesParam(unitID, "va_shell_pocket")
  -- Living shell stamps va_shell_zone; accept legacy va_zone_id if present.
  local zone = Spring.GetUnitRulesParam and (
    Spring.GetUnitRulesParam(unitID, "va_shell_zone")
    or Spring.GetUnitRulesParam(unitID, "va_zone_id")
  )
  local shell = Spring.GetUnitRulesParam and Spring.GetUnitRulesParam(unitID, "va_living_shell")
  if not (shell == 1 or shell == true or shell == "1" or pocket or role == "occupation" or role == "shell") then
    return
  end
  local ud = unitDefID and UnitDefs[unitDefID]
  local targetZone = (mission and mission.objective and mission.objective.targetZoneId)
    or (mission and mission.targetZoneId) or ""
  shellScarEvents[#shellScarEvents + 1] = {
    zoneId = zone and tostring(zone) or tostring(targetZone),
    pocketId = pocket and tostring(pocket) or "",
    unitDefName = ud and ud.name or "",
    destroyed = true,
    damageFrac = 1.0,
  }
end

function shellScarsJson()
  local parts = {}
  for i = 1, #shellScarEvents do
    local e = shellScarEvents[i]
    parts[#parts + 1] = '{'
      .. '"zoneId":' .. jstr(e.zoneId or "")
      .. ',"pocketId":' .. jstr(e.pocketId or "")
      .. ',"unitDefName":' .. jstr(e.unitDefName or "")
      .. ',"destroyed":true'
      .. ',"damageFrac":1'
      .. '}'
  end
  return '[' .. table.concat(parts, ',') .. ']'
end

local function resultJson()
  local alive, total = companionCounts()
  local req = mission.objective and mission.objective.requiredFrames or 600
  local frame = Spring.GetGameFrame() or 0
  local obj = mission.objective or {}
  local targetZone = mission.targetZoneId or obj.targetZoneId or ""
  local patron = mission.patron or (mission.worldConflict and mission.worldConflict.patron) or ""
  -- Node claim = capture clear+hold completed. Never free-mints Tnb (reclaim only).
  local nodeClaimed = capture.nodeClaimed or (objectiveCompleteHow == "node_claimed")
  -- Protocol: zone flip eligible only on claim (capture) or full victory (non-capture).
  -- partial never empty-grass flips.
  local zoneFlipEligible = false
  if capture.mode then
    zoneFlipEligible = nodeClaimed == true and (status == "victory" or status == "partial")
  else
    zoneFlipEligible = (status == "victory") and (objectiveCredited() or objectiveComplete) and targetZone ~= ""
  end
  local zoneFlipped = zoneFlipEligible
  local extStatus = extractionStatusString()
  local cleanExtract = (extStatus == "clean")
  local chapter = sortieChapter or 1
  local reasonSafe = tostring(terminalReason or "none"):gsub("|", "_")
  local cid = mission.campaignId or "verdance_ashes"
  local mid = mission.missionId or "va_unknown"
  local mn = tostring(mission.missionNumber or 0)
  -- Hardened resultKey: unique across Mode A chapters and re-tries
  local rkey = cid .. "|" .. mid .. "|" .. mn
    .. "|ch" .. tostring(chapter)
    .. "|" .. tostring(status)
    .. "|" .. reasonSafe
    .. "|f" .. tostring(frame)
  local sortieId = mission.hubChoiceId or mission.choiceId or mission.sortieId or ""
  return '{' .. table.concat({
    '"schemaVersion":' .. jstr("verdance-match-result/2.0"),
    '"campaignId":' .. jstr(cid),
    '"missionId":' .. jstr(mid),
    '"missionNumber":' .. jnum(mission.missionNumber or 0),
    '"chapterIndex":' .. jnum(chapter),
    '"pathSignal":' .. jstr(mission.pathSignal or "B"),
    '"status":' .. jstr(status),
    '"verdict":' .. jstr(status),
    '"resultKey":' .. jstr(rkey),
    '"sortieId":' .. jstr(tostring(sortieId)),
    '"holdFrames":' .. jnum(holdFrames),
    '"requiredFrames":' .. jnum(req),
    '"frame":' .. jnum(frame),
    '"elapsedMinutes":' .. jnum(frame / 1800.0, 2),
    '"deploymentMapId":' .. jstr(mission.deploymentMapId or ""),
    '"mapId":' .. jstr(mission.deploymentMapId or ""),
    '"deploymentZoneId":' .. jstr(mission.deploymentZoneId or ""),
    '"targetZoneId":' .. jstr(targetZone),
    '"patron":' .. jstr(patron),
    '"zoneFlipped":' .. tostring(zoneFlipped == true),
    '"zoneFlipEligible":' .. tostring(zoneFlipEligible == true),
    '"nodeClaimed":' .. tostring(nodeClaimed == true),
    '"pocketCleared":' .. tostring(capture.pocketCleared == true),
    '"capturePhase":' .. jstr(capture.phase or "idle"),
    '"captureMode":' .. tostring(capture.mode == true),
    '"regrowWaves":' .. jnum(capture.regrowWaves or 0),
    '"terminalReason":' .. jstr(terminalReason),
    '"objectiveComplete":' .. tostring(objectiveComplete == true),
    '"objectiveBypassed":' .. tostring(objectiveBypassed == true),
    '"extractionStatus":' .. jstr(extStatus),
    '"cleanExtract":' .. tostring(cleanExtract == true),
    '"extractionZoneId":' .. jstr(mission.extractionZoneId or obj.extractionZoneId or ""),
    '"chosenTargetForceId":' .. jstr(chosenTargetForceId or ""),
    '"playerSurvivors":' .. playerSurvivorsJson(),
    '"loanUnitHp":' .. loanUnitHpJson(),
    '"shellScars":' .. shellScarsJson(),
    '"heroResults":' .. heroResultsJson(),
    '"namedOutcomes":' .. namedOutcomesJson(),
    '"destroyedObjectiveIds":' .. destroyedObjectiveIdsJson(),
    '"objectiveResults":' .. objectiveResultsJson(),
    '"secondaryResults":' .. secondaryResultsJson(),
    '"purge":{"armed":' .. tostring(extraObj.purge == true)
      .. ',"done":' .. tostring(extraObj.purgeDone == true) .. '}',
    '"companionsAlive":' .. jnum(alive),
    '"companionsTotal":' .. jnum(total),
    '"debugAutoProgress":' .. jnum(debugAutoProgress),
    '"farmSortie":' .. tostring((mission.difficulty and mission.difficulty.farmSortie) or (mission.progression and mission.progression.farmSortie) or false),
    '"sessionMode":' .. jstr(mission.sessionMode or "same_map"),
    '"occupationModel":' .. jstr(mission.occupationModel or "living_shell"),
    '"softContinueArmed":' .. tostring(softContinueArmed == true),
    '"credits":{'
      .. '"objectiveComplete":' .. tostring(objectiveComplete == true)
      .. ',"nodeClaimed":' .. tostring(nodeClaimed == true)
      .. ',"pocketCleared":' .. tostring(capture.pocketCleared == true)
      .. ',"zoneFlipEligible":' .. tostring(zoneFlipEligible == true)
      .. ',"cleanExtract":' .. tostring(cleanExtract == true)
      .. ',"raidCredit":' .. tostring((not capture.mode) and objectiveComplete == true)
      .. '}',
    '"map":{"name":' .. jstr(Game.mapName or "") .. ',"sizeX":' .. jnum(Game.mapSizeX or 0) .. ',"sizeZ":' .. jnum(Game.mapSizeZ or 0) .. '}',
    '"zoneMap":{' .. zoneMapJson() .. '}',
    '"economy":{' .. economyJson() .. '}',
    '"graph":{' .. graphJson() .. '}',
    '"reputation":{' .. reputationJson() .. '}',
    '"primaryCompanion":{' .. primaryCompanionJson() .. '}',
    '"tenebriumLooted":' .. jnum(tenebLoot.looted or tenebLoot.total or 0),
    '"tenebriumBank":' .. jnum(tenebLoot.bank or 0),
    '"tenebriumSpent":' .. jnum(tenebLoot.spent or 0),
    '"tenebriumLost":' .. jnum(tenebLoot.lost or 0),
    '"tenebriumLootEvents":' .. (tenebLoot.eventsJson and tenebLoot.eventsJson() or '[]'),
    '"armadaTenebriumCrisis":' .. tostring(tenebLoot.armadaCrisis == true),
    '"freeTnbMint":false'
  }, ',') .. '}'
end

local function echoStatus()
  local req = mission.objective and mission.objective.requiredFrames or 600
  Spring.Echo("VA_STATUS mission=" .. tostring(mission.missionId) .. " status=" .. status .. " hold=" .. holdFrames .. "/" .. req .. " auto=" .. debugAutoProgress)
end

local function logJsonChunked(prefix, json)
  local chunkSize = 180
  local total = math.ceil(#json / chunkSize)
  if total < 1 then total = 1 end
  Spring.Echo(prefix .. "_BEGIN")
  for i = 1, total do
    local a = ((i - 1) * chunkSize) + 1
    local b = i * chunkSize
    Spring.Echo(prefix .. "_CHUNK " .. tostring(i) .. "/" .. tostring(total) .. " " .. json:sub(a, b))
  end
  Spring.Echo(prefix .. "_END")
end

-- Forward declaration: the Hermitian-observable emitter is defined later (it
-- depends on the zone-scan helpers), but the terminal paths above need to call
-- it. Assigning to this file-scope local at its definition site wires them up.
local logAndBroadcastTranslation

local function logResult()
  local json = resultJson()
  Spring.Echo("VA_RESULT_JSON_COMPACT " .. json)
  logJsonChunked("VA_RESULT_JSON", json)
  echoStatus()
end

local function finishHeadlessResult(outcome)
  local req = mission.objective and mission.objective.requiredFrames or 600
  status = outcome or "victory"
  holdFrames = req
  debugAutoProgress = 0
  terminal = true
  terminalReason = "headless_fastwin"
  Spring.SetGameRulesParam("va_hold_frames", holdFrames, { public = true })
  Spring.Echo("VA_HEADLESS_RESULT_READY mission=" .. tostring(mission.missionId) .. " status=" .. status)
  logResult()
  if logAndBroadcastTranslation then logAndBroadcastTranslation() end
  if headless.quit then
    headless.quitFrame = Spring.GetGameFrame() + 2
  end
end

local function startMission()
  status = "active"
  vaInitWaterline()
  holdFrames = 0
  debugAutoProgress = debugAutoProgressAllowed and 1 or 0
  lastProgressFrame = Spring.GetGameFrame()
  if tenebLoot.initFromMission then tenebLoot.initFromMission() end
  Spring.SetGameRulesParam("va_status", status, { public = true })
  Spring.Echo("VA_START " .. tostring(mission.missionId) .. " zone=" .. tostring(mission.zone or "unknown"))
  echoStatus()
end

local function progress(frames)
  if status == "inactive" then status = "active" end
  holdFrames = holdFrames + (frames or 300)
  local req = mission.objective and mission.objective.requiredFrames or 600
  if holdFrames >= req and status == "active" then status = "victory" end
  echoStatus()
end

function spawnCompanions()
  if not mission.companions then return end
  local teamID = 0
  local x, y, z = 1000, 100, 1000
  for i, comp in ipairs(mission.companions) do
    local defName = comp.unitDefName or "armwar"
    local unitID = Spring.CreateUnit(defName, x + i * 80, y, z + i * 80, 0, teamID)
    comp._unitID = unitID
    if unitID then
      Spring.SetUnitRulesParam(unitID, "va_companion", 1, { public = true })
      Spring.SetUnitRulesParam(unitID, "va_companion_xp", comp.xp or 0, { public = true })
      Spring.SetUnitRulesParam(unitID, "va_companion_morale", comp.morale or 0, { public = true })
      if Spring.SetUnitExperience then Spring.SetUnitExperience(unitID, comp.xp or 0) end
    end
  end
  Spring.Echo("VA_SPAWN companions=" .. tostring(#mission.companions))
end

local function unitDefName(defID)
  local ud = UnitDefs[defID]
  return ud and ud.name or tostring(defID or "unknown")
end

local function unitDefMetal(defID)
  local ud = UnitDefs[defID]
  return tonumber(ud and ud.metalCost or 0) or 0
end

local function isBuilder(defID)
  local ud = UnitDefs[defID]
  return ud and (tonumber(ud.buildSpeed or 0) or 0) > 0
end

local function isStructure(defID)
  local ud = UnitDefs[defID]
  return ud and (ud.isBuilding or ud.isFactory or ud.speed == 0)
end

local function canFight(defID)
  local ud = UnitDefs[defID]
  if not ud then return false end
  if ud.canAttack then return true end
  return ud.weapons and #ud.weapons > 0
end

local function metalSpotKey(spot)
  return tostring(math.floor((spot.x or 0) + 0.5)) .. "|" .. tostring(math.floor((spot.z or 0) + 0.5))
end

local function metalSpotHasUnit(spot)
  if not spot or not Spring.GetUnitsInCylinder then return false end
  local units = Spring.GetUnitsInCylinder(spot.x, spot.z, 96)
  return units and #units > 0
end

local function nearestOpenMetalSpot(anchorX, anchorZ, claimedMetalSpots)
  local spots = GG and GG["resource_spot_finder"] and GG["resource_spot_finder"].metalSpotsList or nil
  if not spots then return nil end
  local best, bestDist
  for i = 1, #spots do
    local spot = spots[i]
    local key = metalSpotKey(spot)
    if not claimedMetalSpots[key] and not metalSpotHasUnit(spot) then
      local dx, dz = anchorX - spot.x, anchorZ - spot.z
      local dist = dx * dx + dz * dz
      if not bestDist or dist < bestDist then
        best = spot
        bestDist = dist
      end
    end
  end
  return best
end

-- Register a named hero on its freshly spawned unit: identity rules params for
-- the HUD/name tags, the toughness multiplier, and carried experience.
-- XP peak is sticky: death/rez never drops lastXp below the mission high-water.
-- Spoke / wheelie mentor: bank XP from every player Wheelie (legscout) death
-- into the mentor hero, then stamp that floor onto newly minted scouts.
local wheelieMentor = {
  heroId = nil,       -- "spoke" when present
  bankXp = 0,         -- peak XP harvested from dead wheelies this sortie (+ seed)
  minted = 0,
  harvested = 0,
}

local function isWheelieDef(defName)
  if not defName then return false end
  local n = string.lower(tostring(defName))
  return n == "legscout" or n:find("wheel", 1, true) ~= nil
end

local function heroHasWheelieMentor(spec)
  if not spec then return false end
  local trait = tostring(spec.heroTrait or "")
  if trait == "wheelie_mentor" or trait == "scout_tech" then return true end
  local traits = spec.heroTraits or spec.traits
  if type(traits) == "table" then
    for _, t in ipairs(traits) do
      if tostring(t) == "wheelie_mentor" or tostring(t) == "scout_tech" then return true end
    end
  end
  local id = tostring(spec.heroId or "")
  return id == "spoke"
end

local function stampWheelieXp(unitID)
  if not wheelieMentor.heroId then return end
  local floor = tonumber(wheelieMentor.bankXp) or 0
  if floor <= 0 then return end
  if Spring.SetUnitExperience then pcall(Spring.SetUnitExperience, unitID, floor) end
  Spring.SetUnitRulesParam(unitID, "va_wheelie_mint", 1, { public = true })
  Spring.SetUnitRulesParam(unitID, "va_wheelie_xp_floor", floor, { public = true })
  wheelieMentor.minted = (wheelieMentor.minted or 0) + 1
end

local function harvestWheelieXp(unitID)
  if not wheelieMentor.heroId then return end
  if heroByUnitID[unitID] then return end -- named hero death handled elsewhere
  local xp = 0
  if Spring.GetUnitExperience then xp = Spring.GetUnitExperience(unitID) or 0 end
  if xp <= 0 then return end
  local prev = tonumber(wheelieMentor.bankXp) or 0
  if xp > prev then
    wheelieMentor.bankXp = xp
    wheelieMentor.harvested = (wheelieMentor.harvested or 0) + 1
    local rec = heroes[wheelieMentor.heroId]
    if rec then
      rec.peakXp = math.max(tonumber(rec.peakXp) or 0, xp)
      rec.lastXp = rec.peakXp
      if rec.unitID and Spring.ValidUnitID(rec.unitID) and Spring.SetUnitExperience then
        pcall(Spring.SetUnitExperience, rec.unitID, rec.peakXp)
        Spring.SetUnitRulesParam(rec.unitID, "va_hero_xp", rec.peakXp, { public = true })
      end
    end
    Spring.Echo("VA_WHEELIE_HARVEST xp=" .. tostring(xp) .. " bank=" .. tostring(wheelieMentor.bankXp)
      .. " mentor=" .. tostring(wheelieMentor.heroId))
  end
end

local function registerHeroSpawn(unitID, spec)
  local id = tostring(spec.heroId or "hero")
  local rec = heroes[id]
  local seedXp = tonumber(spec.heroXp) or 0.25
  local seedLevel = tonumber(spec.heroLevel) or 1
  local seedRank = tostring(spec.heroRank or "Runner")
  if not rec then
    rec = {
      id = id,
      name = tostring(spec.heroName or id),
      unitDefName = tostring(spec.unitDefName or spec.def or ""),
      missionCritical = spec.missionCritical == true,
      hpMult = tonumber(spec.heroHpMult) or 1.4,
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
    if tonumber(spec.heroHpMult) then rec.hpMult = tonumber(spec.heroHpMult) end
    if spec.heroTrait then rec.trait = tostring(spec.heroTrait) end
  end
  rec.unitID = unitID
  if (not rec.unitDefName or rec.unitDefName == "") and Spring.GetUnitDefID then
    local dID = Spring.GetUnitDefID(unitID)
    local ud = dID and UnitDefs[dID]
    if ud and ud.name then rec.unitDefName = ud.name end
  end
  if heroHasWheelieMentor(spec) then
    wheelieMentor.heroId = id
    wheelieMentor.bankXp = math.max(tonumber(wheelieMentor.bankXp) or 0, tonumber(rec.peakXp) or seedXp)
    Spring.SetUnitRulesParam(unitID, "va_wheelie_mentor", 1, { public = true })
    Spring.Echo("VA_WHEELIE_MENTOR online id=" .. id .. " bank=" .. tostring(wheelieMentor.bankXp))
  end
  heroByUnitID[unitID] = id
  Spring.SetUnitRulesParam(unitID, "va_hero", 1, { public = true })
  Spring.SetUnitRulesParam(unitID, "va_hero_id", id, { public = true })
  Spring.SetUnitRulesParam(unitID, "va_hero_name", rec.name, { public = true })
  Spring.SetUnitRulesParam(unitID, "va_hero_critical", rec.missionCritical and 1 or 0, { public = true })
  Spring.SetUnitRulesParam(unitID, "va_hero_level", rec.level or 1, { public = true })
  Spring.SetUnitRulesParam(unitID, "va_hero_rank", rec.rank or "Runner", { public = true })
  Spring.SetUnitRulesParam(unitID, "va_hero_xp", rec.peakXp or 0, { public = true })
  if Spring.GetUnitHealth and Spring.SetUnitMaxHealth then
    local _, maxH = Spring.GetUnitHealth(unitID)
    if maxH then
      pcall(Spring.SetUnitMaxHealth, unitID, maxH * rec.hpMult)
      pcall(Spring.SetUnitHealth, unitID, maxH * rec.hpMult)
    end
  end
  if Spring.SetUnitExperience then pcall(Spring.SetUnitExperience, unitID, rec.peakXp or seedXp) end
  publishHeroRules()
  Spring.Echo("VA_HERO_SPAWNED id=" .. id .. " unit=" .. tostring(unitID)
    .. " def=" .. tostring(rec.unitDefName)
    .. " critical=" .. tostring(rec.missionCritical)
    .. " xp=" .. tostring(rec.peakXp)
    .. " L" .. tostring(rec.level or 1)
    .. " " .. tostring(rec.rank or ""))
end

local function spawnOneUnit(defName, x, z, facing, teamID, spec, force)
  local y = Spring.GetGroundHeight(x, z)
  local unitID = Spring.CreateUnit(defName, x, y, z, facing, teamID)
  if unitID then
    Spring.SetUnitRulesParam(unitID, "va_playable_proxy", 1, { public = true })
    -- Minted wheelies inherit Spoke's banked XP floor (even when the mentor is down).
    if teamID == playerTeamID and isWheelieDef(defName) and not (spec and (spec.heroId or spec.hero)) then
      stampWheelieXp(unitID)
    end
    if force and force.role then
      Spring.SetUnitRulesParam(unitID, "va_force_role", tostring(force.role), { public = true })
      if force.role == "objective_target" then
        local defID = Spring.GetUnitDefID(unitID)
        if isStructure(defID) then
          local forceId = tostring(force.id or "objective")
          objectiveTargets[unitID] = forceId
          objectiveTargetCount = objectiveTargetCount + 1
          targetForceStructures[forceId] = (targetForceStructures[forceId] or 0) + 1
        end
      elseif force.role == "objective_secondary" then
        -- Drop 4: secondary marks keep their own ledger, never the primary
        -- pool (a capture mission's clear fraction must not count them).
        local defID = Spring.GetUnitDefID(unitID)
        if isStructure(defID) then
          local sid = tostring(force.secondaryId or force.id or "secondary")
          local g = extraObj.groups[sid]
          if not g then
            g = { total = 0, destroyed = 0, required = (force.required == true), done = false }
            extraObj.groups[sid] = g
            extraObj.order[#extraObj.order + 1] = sid
            if g.required then extraObj.requiredLeft = extraObj.requiredLeft + 1 end
          end
          g.total = g.total + 1
          extraObj.targets[unitID] = sid
        end
      end
    end
    -- Patrols actually patrol: a waypoint list (or the legacy single point)
    -- becomes a CMD.PATROL loop from the spawn position, so garrisons sweep
    -- their ground instead of fight-moving once and clumping.
    if spec and type(spec.patrol) == "table" and CMD and CMD.PATROL then
      local opts = {}
      for _, wp in ipairs(spec.patrol) do
        local px = normalizedToElmos(wp.x, Game.mapSizeX or 0)
        local pz = normalizedToElmos(wp.z, Game.mapSizeZ or 0)
        Spring.GiveOrderToUnit(unitID, CMD.PATROL, { px, Spring.GetGroundHeight(px, pz), pz }, opts)
        opts = { "shift" }
      end
    elseif spec and spec.patrolX and spec.patrolZ and CMD and CMD.PATROL then
      local px = normalizedToElmos(spec.patrolX, Game.mapSizeX or 0)
      local pz = normalizedToElmos(spec.patrolZ, Game.mapSizeZ or 0)
      Spring.GiveOrderToUnit(unitID, CMD.PATROL, { px, Spring.GetGroundHeight(px, pz), pz }, {})
    end
    -- Named heroes (and the legacy single-hero flag): the persistent warband
    -- leaders, not commander suits - tougher and blooded on the field.
    if spec and (spec.heroId or spec.hero) then
      registerHeroSpawn(unitID, spec)
    end
    -- WO-043: loan packs / smoking thugs spawn damaged so repair bots eat early downtime.
    if spec and (spec.healthFrac or spec.healthFracMin or spec.healthFracMax or spec.loanPackage) then
      local hmin = tonumber(spec.healthFracMin)
      local hmax = tonumber(spec.healthFracMax)
      local hfrac = tonumber(spec.healthFrac)
      if not hfrac then
        if hmin and hmax then
          hfrac = (hmin + hmax) * 0.5
        elseif hmin then
          hfrac = hmin
        else
          hfrac = 0.45
        end
      end
      if hfrac > 1 then hfrac = 1 end
      if hfrac < 0.05 then hfrac = 0.05 end
      if Spring.GetUnitHealth and Spring.SetUnitHealth then
        local cur, maxH = Spring.GetUnitHealth(unitID)
        if maxH and maxH > 0 then
          pcall(Spring.SetUnitHealth, unitID, maxH * hfrac)
        end
      end
      Spring.SetUnitRulesParam(unitID, "va_health_frac", hfrac, { public = true })
      if spec.loanPackage == true or spec.loanPackage == 1 then
        Spring.SetUnitRulesParam(unitID, "va_loan_package", 1, { public = true })
      end
      if spec.packageTag then
        Spring.SetUnitRulesParam(unitID, "va_package_tag", tostring(spec.packageTag), { public = true })
      end
      Spring.Echo("VA_DAMAGED_SPAWN unit=" .. tostring(unitID) .. " frac=" .. tostring(hfrac)
        .. " package=" .. tostring(spec.packageTag or ""))
    elseif spec and spec.packageTag then
      Spring.SetUnitRulesParam(unitID, "va_package_tag", tostring(spec.packageTag), { public = true })
    end
    -- WO-033 unit printer: lock factory to a single product and trickle resources.
    if spec and (spec.unitPrinter == true or spec.unitPrinter == 1) then
      local product = tostring(spec.printerProduct or "leggob")
      Spring.SetUnitRulesParam(unitID, "va_unit_printer", 1, { public = true })
      Spring.SetUnitRulesParam(unitID, "va_printer_product", product, { public = true })
      if Spring.EditUnitCmdDesc and Spring.GetUnitCmdDescs and Spring.RemoveUnitCmdDesc then
        local descs = Spring.GetUnitCmdDescs(unitID) or {}
        for i = #descs, 1, -1 do
          local c = descs[i]
          if c and c.id and c.id < 0 then
            local buildDefID = -c.id
            local bud = UnitDefs[buildDefID]
            if not bud or bud.name ~= product then
              pcall(Spring.RemoveUnitCmdDesc, unitID, i)
            end
          end
        end
      end
      local mInc = tonumber(spec.printerMetalIncome) or 8
      local eInc = tonumber(spec.printerEnergyIncome) or 40
      if mInc > 0 then pcall(Spring.SetTeamResource, teamID, "metal", (Spring.GetTeamResources(teamID, "metal") or 0) + 200) end
      if eInc > 0 then pcall(Spring.SetTeamResource, teamID, "energy", (Spring.GetTeamResources(teamID, "energy") or 0) + 400) end
      -- Ongoing trickle via GameFrame table.
      printerUnits = printerUnits or {}
      printerUnits[unitID] = { metal = mInc / 30, energy = eInc / 30, team = teamID }
      Spring.Echo("VA_UNIT_PRINTER unit=" .. tostring(unitID) .. " product=" .. product)
    end
    return 1
  end
  return 0
end

local function spawnUnitSpec(spec, teamID, baseX, baseZ, groupX, groupZ, claimedMetalSpots, force)
  if type(spec) ~= "table" then return 0 end
  local defName = spec.unitDefName or spec.def or spec[1]
  if not defName or not UnitDefNames[defName] then
    Spring.Echo("VA_PLAYABLE_MISSING_UNIT " .. tostring(defName))
    return 0
  end
  local count = tonumber(spec.count or 1) or 1
  local spacing = tonumber(spec.spacing or 90) or 90
  local spawned = 0
  local dx = tonumber(spec.dx or spec.x or 0) or 0
  local dz = tonumber(spec.dz or spec.z or 0) or 0
  local facing = tonumber(spec.facing or 0) or 0
  local anchorX = baseX + groupX + dx
  local anchorZ = baseZ + groupZ + dz

  if spec.atMetalSpots or spec.nearestMetalSpots then
    for i = 1, count do
      local spot = nearestOpenMetalSpot(anchorX, anchorZ, claimedMetalSpots)
      if not spot then
        Spring.Echo("VA_PLAYABLE_NO_METAL_SPOT unitDef=" .. tostring(defName) .. " anchorX=" .. tostring(math.floor(anchorX)) .. " anchorZ=" .. tostring(math.floor(anchorZ)))
        break
      end
      claimedMetalSpots[metalSpotKey(spot)] = true
      spawned = spawned + spawnOneUnit(defName, spot.x, spot.z, facing, teamID, spec, force)
    end
    return spawned
  end

  for i = 1, count do
    local row = math.floor((i - 1) / 4)
    local col = (i - 1) % 4
    local x = anchorX + ((col - 1.5) * spacing)
    local z = anchorZ + (row * spacing)
    spawned = spawned + spawnOneUnit(defName, x, z, facing, teamID, spec, force)
  end
  return spawned
end

local function spawnPlayableSetup()
  if playableSetupSpawned then
    Spring.Echo("VA_PLAYABLE_SETUP already_spawned")
    return
  end
  local setup = mission and mission.playableSetup
  if not setup or setup.enabled == false then
    Spring.Echo("VA_PLAYABLE_SETUP none")
    return
  end
  playableSetupSpawned = true
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
    local forceSpawned = 0
    for _, group in ipairs(force.groups or {}) do
      local groupX = tonumber(group.dx or group.x or 0) or 0
      local groupZ = tonumber(group.dz or group.z or 0) or 0
      for _, spec in ipairs(group.units or {}) do
        forceSpawned = forceSpawned + spawnUnitSpec(spec, teamID, baseX, baseZ, groupX, groupZ, claimedMetalSpots, force)
      end
    end
    totalSpawned = totalSpawned + forceSpawned
    Spring.Echo("VA_PLAYABLE_FORCE id=" .. tostring(force.id or "?") .. " team=" .. tostring(teamID) .. " role=" .. tostring(force.role or "") .. " units=" .. tostring(forceSpawned))
  end
  -- Presence objectives have no objective_target force; fall back to the camp.
  objectiveTeamID = objectiveTeamID or enemyCampTeamID
  if mercTeamID and Spring.AreTeamsAllied(playerTeamID, mercTeamID) then mercsAllied = true end
  Spring.SetGameRulesParam("va_mercs_available", (mercsAllied and not mercWaveUsed) and 1 or 0, { public = true })
  Spring.SetGameRulesParam("va_objective_total", objectiveTargetCount, { public = true })
  Spring.SetGameRulesParam("va_objective_destroyed", 0, { public = true })
  -- Drop 4: enrich secondary groups from the seed meta, arm purge strength,
  -- and publish the HUD ledger (indexed marker params in group order).
  local secMetaById = {}
  for _, m in ipairs((mission and mission.secondaries) or {}) do
    if m and m.id then secMetaById[tostring(m.id)] = m end
  end
  for i, sid in ipairs(extraObj.order) do
    local g = extraObj.groups[sid]
    local m = secMetaById[sid]
    if m then
      g.label = m.label
      if m.required == true and not g.required then
        g.required = true
        extraObj.requiredLeft = extraObj.requiredLeft + 1
      end
      Spring.SetGameRulesParam("va_sec" .. i .. "_x", math.floor((tonumber(m.x) or 0.5) * (Game.mapSizeX or 0)), { public = true })
      Spring.SetGameRulesParam("va_sec" .. i .. "_z", math.floor((tonumber(m.z) or 0.5) * (Game.mapSizeZ or 0)), { public = true })
    end
    Spring.SetGameRulesParam("va_sec" .. i .. "_id", sid, { public = true })
    Spring.SetGameRulesParam("va_sec" .. i .. "_label", tostring(g.label or sid), { public = true })
    Spring.SetGameRulesParam("va_sec" .. i .. "_req", g.required and 1 or 0, { public = true })
    Spring.SetGameRulesParam("va_sec" .. i .. "_done", 0, { public = true })
  end
  if #extraObj.order > 0 then
    Spring.SetGameRulesParam("va_secondary_total", #extraObj.order, { public = true })
    Spring.SetGameRulesParam("va_secondary_done", 0, { public = true })
    Spring.SetGameRulesParam("va_secondary_required_left", extraObj.requiredLeft, { public = true })
    Spring.Echo("VA_SECONDARY_ARMED groups=" .. tostring(#extraObj.order)
      .. " required=" .. tostring(extraObj.requiredLeft))
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
  Spring.Echo("VA_PLAYABLE_SETUP spawned forces=" .. tostring(#forces) .. " units=" .. tostring(totalSpawned))
  Spring.Echo("VA_ESCALATION_SETUP enemyTeam=" .. tostring(objectiveTeamID) .. " mercTeam=" .. tostring(mercTeamID) .. " mercsAllied=" .. tostring(mercsAllied))
  Spring.Echo("VA_OBJECTIVE_ARMED kind=" .. tostring(mission.objective and mission.objective.kind or "none") .. " targets=" .. tostring(objectiveTargetCount))
end

local function resourceIncome(teamID, resourceName)
  local ok, a, b, c, income = pcall(Spring.GetTeamResources, teamID, resourceName)
  if ok then return tonumber(income or c or 0) or 0 end
  return 0
end

-- Gadget-env global (the main chunk is at its 200-local ceiling). Builds the
-- cell -> zone lookup once from schema 2.0 cell masks; returns nil for legacy
-- rect-only zone maps so the old path still works.
function vaZoneCellIndex()
  if vaZoneCellIndexCache == false then return nil end
  if vaZoneCellIndexCache then return vaZoneCellIndexCache end
  vaZoneCellIndexCache = false
  if not zoneMap or type(zoneMap.zones) ~= "table" then return nil end
  local res = nil
  if zoneMap.grid and tonumber(zoneMap.grid.res) then
    res = math.floor(tonumber(zoneMap.grid.res))
  end
  for _, zone in ipairs(zoneMap.zones) do
    if not res and zone.cellGrid and tonumber(zone.cellGrid.cols) then
      res = math.floor(tonumber(zone.cellGrid.cols))
    end
  end
  if not res or res < 2 then return nil end
  local owner = {}
  local claimed = 0
  for _, zone in ipairs(zoneMap.zones) do
    if type(zone.cells) == "table" then
      for _, run in ipairs(zone.cells) do
        local start = tonumber(run[1])
        local length = tonumber(run[2])
        if start and length and length > 0 then
          for i = start, start + length - 1 do
            if owner[i] == nil then
              owner[i] = zone
              claimed = claimed + 1
            end
          end
        end
      end
    end
  end
  if claimed == 0 then return nil end
  vaZoneCellIndexCache = { res = res, owner = owner, claimed = claimed }
  return vaZoneCellIndexCache
end

local function zoneForPosition(x, z)
  if not zoneMap or type(zoneMap.zones) ~= "table" then return nil end
  local sx = Game.mapSizeX or 0
  local sz = Game.mapSizeZ or 0
  -- Schema 2.0: zones own an explicit set of grid cells, so a position belongs
  -- to exactly one zone. The old rect scan returned whichever overlapping
  -- rectangle happened to be earlier in the file.
  local cellIndex = vaZoneCellIndex()
  if cellIndex then
    local res = cellIndex.res
    local col = math.floor((x / (sx > 0 and sx or 1)) * res)
    local row = math.floor((z / (sz > 0 and sz or 1)) * res)
    if col < 0 then col = 0 elseif col >= res then col = res - 1 end
    if row < 0 then row = 0 elseif row >= res then row = res - 1 end
    local owner = cellIndex.owner[row * res + col]
    if owner then return owner end
  end
  for _, zone in ipairs(zoneMap.zones) do
    local b = zone.bounds or {}
    local xMin = normalizedToElmos(b.xMin, sx)
    local xMax = normalizedToElmos(b.xMax, sx)
    local zMin = normalizedToElmos(b.zMin, sz)
    local zMax = normalizedToElmos(b.zMax, sz)
    if x >= xMin and x <= xMax and z >= zMin and z <= zMax then
      return zone
    end
  end
  return nil
end

local function emptyMetrics()
  return {
    armyValue = 0,
    buildPower = 0,
    defensiveValue = 0,
    totalUnitValue = 0,
    unitCount = 0,
    combatUnitCount = 0,
    builderUnitCount = 0,
    structureCount = 0
  }
end

local function addUnitToBucket(bucket, defID)
  local name = unitDefName(defID)
  local metal = unitDefMetal(defID)
  local ud = UnitDefs[defID]
  bucket.metrics.totalUnitValue = bucket.metrics.totalUnitValue + metal
  bucket.metrics.unitCount = bucket.metrics.unitCount + 1
  bucket.unitCountsByDef[name] = (bucket.unitCountsByDef[name] or 0) + 1
  if isStructure(defID) then bucket.metrics.structureCount = bucket.metrics.structureCount + 1 end
  if isBuilder(defID) then
    bucket.metrics.builderUnitCount = bucket.metrics.builderUnitCount + 1
    bucket.metrics.buildPower = bucket.metrics.buildPower + (tonumber(ud and ud.buildSpeed or 0) or 0)
  end
  if canFight(defID) then
    bucket.metrics.combatUnitCount = bucket.metrics.combatUnitCount + 1
    if isStructure(defID) then
      bucket.metrics.defensiveValue = bucket.metrics.defensiveValue + metal
    else
      bucket.metrics.armyValue = bucket.metrics.armyValue + metal
    end
  end
end

local function countsJson(counts)
  local parts = {}
  for name, count in pairs(counts or {}) do
    parts[#parts + 1] = jstr(name) .. ':' .. jnum(count)
  end
  return '{' .. table.concat(parts, ',') .. '}'
end

local function metricsJson(m)
  return '{' .. table.concat({
    '"armyValue":' .. jnum(m.armyValue or 0, 2),
    '"buildPower":' .. jnum(m.buildPower or 0, 2),
    '"defensiveValue":' .. jnum(m.defensiveValue or 0, 2),
    '"totalUnitValue":' .. jnum(m.totalUnitValue or 0, 2),
    '"metalIncome":' .. jnum(m.metalIncome or 0, 2),
    '"energyIncome":' .. jnum(m.energyIncome or 0, 2),
    '"unitCount":' .. jnum(m.unitCount or 0),
    '"combatUnitCount":' .. jnum(m.combatUnitCount or 0),
    '"builderUnitCount":' .. jnum(m.builderUnitCount or 0),
    '"structureCount":' .. jnum(m.structureCount or 0)
  }, ',') .. '}'
end

local function makeTeamBucket(teamID)
  local _, leader, isDead, isAiTeam, side, allyTeam = Spring.GetTeamInfo(teamID, false)
  return {
    teamId = teamID,
    allyTeamId = tonumber(allyTeam or -1) or -1,
    side = side or "",
    faction = teamFaction[teamID] or "",
    isDead = isDead and true or false,
    isAi = isAiTeam and true or false,
    metrics = emptyMetrics(),
    unitCountsByDef = {}
  }
end

local function teamBucketJson(bucket)
  return '{' .. table.concat({
    '"teamId":' .. jnum(bucket.teamId),
    '"allyTeamId":' .. jnum(bucket.allyTeamId),
    '"side":' .. jstr(bucket.side or ""),
    '"faction":' .. jstr(bucket.faction or ""),
    '"isDead":' .. tostring(bucket.isDead == true),
    '"isAi":' .. tostring(bucket.isAi == true),
    '"metrics":' .. metricsJson(bucket.metrics),
    '"unitCountsByDef":' .. countsJson(bucket.unitCountsByDef)
  }, ',') .. '}'
end

local function zoneBucketJson(zone, teams)
  local teamParts = {}
  for _, bucket in pairs(teams or {}) do
    teamParts[#teamParts + 1] = teamBucketJson(bucket)
  end
  return jstr(zone.zoneId or "unknown") .. ':{' .. table.concat({
    '"zoneId":' .. jstr(zone.zoneId or ""),
    '"label":' .. jstr(zone.label or ""),
    '"teams":[' .. table.concat(teamParts, ',') .. ']'
  }, ',') .. '}'
end

local function telemetryJson()
  local frame = Spring.GetGameFrame()
  local teamBuckets = {}
  local teamParts = {}
  local zoneBuckets = {}
  -- Same source of truth as the objective/win system (playerTeamID, default 0);
  -- a seed missing balance.playerTeamID must not diverge the two systems.
  local playerTeam = tonumber(mission and mission.balance and mission.balance.playerTeamID or playerTeamID) or playerTeamID

  for _, teamID in ipairs(Spring.GetTeamList()) do
    teamBuckets[teamID] = makeTeamBucket(teamID)
  end

  for teamID, bucket in pairs(teamBuckets) do
    local units = Spring.GetTeamUnits(teamID) or {}
    for _, unitID in ipairs(units) do
      if Spring.ValidUnitID(unitID) and not Spring.GetUnitIsDead(unitID) then
        local defID = Spring.GetUnitDefID(unitID)
        addUnitToBucket(bucket, defID)
        local x, _, z = Spring.GetUnitPosition(unitID)
        if x and z then
          local zone = zoneForPosition(x, z)
          if zone and zone.zoneId then
            zoneBuckets[zone.zoneId] = zoneBuckets[zone.zoneId] or { zone = zone, teams = {} }
            if not zoneBuckets[zone.zoneId].teams[teamID] then
              local zb = makeTeamBucket(teamID)
              zb.metrics = emptyMetrics()
              zb.unitCountsByDef = {}
              zoneBuckets[zone.zoneId].teams[teamID] = zb
            end
            addUnitToBucket(zoneBuckets[zone.zoneId].teams[teamID], defID)
            vaRecordZonePresence(unitID, zone.zoneId)
          end
        end
      end
    end
    bucket.metrics.metalIncome = resourceIncome(teamID, "metal")
    bucket.metrics.energyIncome = resourceIncome(teamID, "energy")
    teamParts[#teamParts + 1] = teamBucketJson(bucket)
  end

  local playerValue = teamBuckets[playerTeam] and teamBuckets[playerTeam].metrics.totalUnitValue or 0
  local enemyValue = 0
  local enemyUnitCount = 0
  for teamID, bucket in pairs(teamBuckets) do
    if teamID ~= playerTeam and teamID ~= 0 and not Spring.AreTeamsAllied(playerTeam, teamID) then
      enemyValue = enemyValue + bucket.metrics.totalUnitValue
      enemyUnitCount = enemyUnitCount + bucket.metrics.unitCount
    end
  end
  local playerUnitCount = teamBuckets[playerTeam] and teamBuckets[playerTeam].metrics.unitCount or 0
  local valueRatio = enemyValue > 0 and (playerValue / enemyValue) or playerValue
  local verdict = "active"
  if playerUnitCount <= 0 then verdict = "player_dead"
  elseif enemyUnitCount <= 0 then verdict = "player_clear"
  elseif valueRatio >= 1.25 then verdict = "player_advantage"
  elseif valueRatio <= 0.55 then verdict = "player_stalled"
  end

  local zoneParts = {}
  if zoneMap and type(zoneMap.zones) == "table" then
    for _, zone in ipairs(zoneMap.zones) do
      local entry = zoneBuckets[zone.zoneId] or { zone = zone, teams = {} }
      zoneParts[#zoneParts + 1] = zoneBucketJson(entry.zone, entry.teams)
    end
  end

  return '{' .. table.concat({
    '"schemaVersion":"bar-zone-telemetry/1.0"',
    '"exportId":' .. jstr("va-" .. tostring(frame)),
    '"matchId":' .. jstr(Game.gameID or ""),
    '"missionId":' .. jstr(mission and mission.missionId or ""),
    '"variantId":' .. jstr(mission and mission.playableSetup and mission.playableSetup.variantId or ""),
    '"frame":' .. jnum(frame),
    '"seconds":' .. jnum(frame / 30, 2),
    '"map":{"name":' .. jstr(Game.mapName or "") .. ',"mapId":' .. jstr(zoneMap and zoneMap.mapId or "") .. ',"size":{"x":' .. jnum(Game.mapSizeX or 0) .. ',"z":' .. jnum(Game.mapSizeZ or 0) .. '}}',
    '"terminal":{"isTerminal":false,"status":"active","winnerAllyTeamId":null}',
    '"balance":{"playerTeamId":' .. jnum(playerTeam) .. ',"playerValue":' .. jnum(playerValue, 2) .. ',"enemyValue":' .. jnum(enemyValue, 2) .. ',"valueRatio":' .. jnum(valueRatio, 4) .. ',"playerUnitCount":' .. jnum(playerUnitCount) .. ',"enemyUnitCount":' .. jnum(enemyUnitCount) .. ',"verdict":' .. jstr(verdict) .. '}',
    '"teams":[' .. table.concat(teamParts, ',') .. ']',
    '"zones":{' .. table.concat(zoneParts, ',') .. '}'
  }, ',') .. '}'
end

local function logTelemetry()
  local json = telemetryJson()
  Spring.Echo("VA_TELEMETRY_JSON_COMPACT " .. json)
  logJsonChunked("VA_TELEMETRY_JSON", json)
  Spring.Echo("VA_TELEMETRY_EXPORT_OK frame=" .. tostring(Spring.GetGameFrame()))
end

local function resetDevCmdCounts()
  devTel.cmds = { move = 0, fight = 0, attack = 0, patrol = 0, build = 0, reclaim = 0, guard = 0, other = 0 }
  devTel.cmdTotal = 0
end

local function classifyCmd(cmdID)
  -- Spring CMD IDs: MOVE=-1 FIGHT=16 PATROL=15 GUARD=25 ATTACK=20 RECLAIM=90 REPAIR=40
  if cmdID == CMD.MOVE or cmdID == -1 then return "move" end
  if cmdID == CMD.FIGHT or cmdID == 16 then return "fight" end
  if cmdID == CMD.PATROL or cmdID == 15 then return "patrol" end
  if cmdID == CMD.ATTACK or cmdID == 20 then return "attack" end
  if cmdID == CMD.GUARD or cmdID == 25 then return "guard" end
  if cmdID == CMD.RECLAIM or cmdID == 90 then return "reclaim" end
  if type(cmdID) == "number" and cmdID < 0 then return "build" end  -- negative = build unitdef
  return "other"
end

local function logDevSample()
  if not devTel.enabled then return end
  local frame = Spring.GetGameFrame() or 0
  local base = telemetryJson()
  -- strip outer braces to splice fields
  local inner = base
  if inner:sub(1, 1) == "{" then inner = inner:sub(2) end
  if inner:sub(-1) == "}" then inner = inner:sub(1, -2) end
  local playerTeam = tonumber(mission and mission.balance and mission.balance.playerTeamID or playerTeamID) or playerTeamID
  local mCurr, mStor = 0, 0
  local eCurr, eStor = 0, 0
  local mInc, eInc = 0, 0
  if Spring.GetTeamResources then
    local mc, ms = Spring.GetTeamResources(playerTeam, "metal")
    local ec, es = Spring.GetTeamResources(playerTeam, "energy")
    mCurr, mStor = tonumber(mc) or 0, tonumber(ms) or 0
    eCurr, eStor = tonumber(ec) or 0, tonumber(es) or 0
  end
  -- income from last full telemetry path is heavy; approximate via rules or 0
  if Spring.GetTeamRulesParam then
    mInc = tonumber(Spring.GetTeamRulesParam(playerTeam, "metalIncome")) or 0
    eInc = tonumber(Spring.GetTeamRulesParam(playerTeam, "energyIncome")) or 0
  end
  local cx, cz, n = 0, 0, 0
  local units = Spring.GetTeamUnits(playerTeam) or {}
  for i = 1, #units do
    local u = units[i]
    if Spring.ValidUnitID(u) and not Spring.GetUnitIsDead(u) then
      local x, _, z = Spring.GetUnitPosition(u)
      if x and z then
        cx = cx + x
        cz = cz + z
        n = n + 1
      end
    end
  end
  if n > 0 then cx, cz = cx / n, cz / n end
  local cmdParts = {}
  for k, v in pairs(devTel.cmds) do
    cmdParts[#cmdParts + 1] = jstr(k) .. ":" .. jnum(v)
  end
  local devJson = '{' .. table.concat({
    inner,
    '"dev":{"metal":' .. jnum(mCurr, 1) .. ',"metalStorage":' .. jnum(mStor, 1)
      .. ',"energy":' .. jnum(eCurr, 1) .. ',"energyStorage":' .. jnum(eStor, 1)
      .. ',"metalIncome":' .. jnum(mInc, 2) .. ',"energyIncome":' .. jnum(eInc, 2)
      .. ',"centroid":{"x":' .. jnum(cx, 1) .. ',"z":' .. jnum(cz, 1) .. ',"units":' .. jnum(n) .. '}'
      .. ',"samplePeriodFrames":' .. jnum(devTel.period) .. '}',
    '"playerCommands":{' .. table.concat(cmdParts, ',') .. '}',
    '"playerCommandTotal":' .. jnum(devTel.cmdTotal),
    '"devSample":true',
    '"exportId":' .. jstr("va-dev-" .. tostring(frame)),
  }, ',') .. '}'
  Spring.Echo("VA_DEV_SAMPLE_JSON " .. devJson)
  Spring.Echo("VA_DEV_SAMPLE_OK frame=" .. tostring(frame) .. " cmds=" .. tostring(devTel.cmdTotal))
  resetDevCmdCounts()
  devTel.lastSample = frame
end

-- ============================================================
-- VERDANCE TRANSLATION MATRIX ENGINE
-- Consumes real zoneBuckets, runs Hermitian math, emits packet.
-- ============================================================

local MAX_WATER_HEIGHT = 250.0
local BASE_COUPLING = 0.3
local BASE_HYDRO_COUPLING = 0.6
local ENTANGLEMENT_THRESHOLD = 0.1
local DENSITY_HOTSPOT = 0.8
local HYDRO_HAZARD_THRESHOLD = 0.4

-- Determine zone hydro type from zone tags
local function getZoneHydroType(zone)
  -- Measured first: a zone is low-flood if the campaign's waterline can
  -- actually take it. Tags are the fallback for legacy rect zone maps.
  local hydro = zone and zone.hydrology
  local floodsAt = hydro and tonumber(hydro.floodsAt)
  if floodsAt then
    return (floodsAt <= 0.7) and "low-flood" or "high-dry"
  end
  if not zone or not zone.tags then return "high-dry" end
  for _, tag in ipairs(zone.tags) do
    if tag == "swamp" or tag == "flood" or tag == "low" then return "low-flood" end
  end
  return "high-dry"
end

-- ------------------------------------------------------------
-- Hydrology and zone geography for the density matrix.
--
-- These are gadget-env GLOBALS on purpose: the main chunk sits at 194/200 Lua
-- locals and one more would stop the whole gadget loading.
--
-- Spring has no synced water-level setter, so a rising waterline is realised by
-- sinking the world: lowering the entire heightmap by D drowns everything below
-- elevation D. The shift is uniform, so no slope and no relative height changes
-- -- only the shore moves -- and one AdjustHeightMap call does the whole map.
-- ------------------------------------------------------------

VA_WATER_TICK = 6           -- frames between waterline steps while ramping
vaWaterLevel = 0.0          -- normalized 0..1 along the map's measured ladder
vaWaterApplied = 0.0        -- elmos the world is currently sunk by
vaWaterTarget = nil         -- ramp destination, when a flood beat is running
vaWaterStep = 0.0
vaUnitZone = nil            -- unitID -> zoneId, for measuring border crossings
vaZoneFlow = nil            -- "A|B" -> crossings since the last packet
vaZoneAdjacencyCache = nil

-- Elevation of a normalized waterline, from the ladder the zone map carries.
function vaWaterElevation(level)
  local line = zoneMap and zoneMap.waterline
  local elevations = line and line.elevations
  if not elevations or #elevations == 0 then return nil end
  local levels = line.levels or {}
  local t = math.max(0, math.min(1, tonumber(level) or 0))
  for i = 1, #elevations do
    local at = tonumber(levels[i]) or ((i - 1) / math.max(1, #elevations - 1))
    if at >= t then
      if i == 1 then return elevations[1] end
      local prev = tonumber(levels[i - 1]) or 0
      local span = (at - prev)
      local f = (span > 0) and ((t - prev) / span) or 0
      return elevations[i - 1] + (elevations[i] - elevations[i - 1]) * f
    end
  end
  return elevations[#elevations]
end

-- Fraction of a zone under water at a normalized level, from its measured curve.
function vaZoneSubmerged(zone, level)
  local hydro = zone and zone.hydrology
  local curve = hydro and hydro.submergedAt
  if not curve or #curve == 0 then return 0.0 end
  local levels = (zoneMap and zoneMap.waterline and zoneMap.waterline.levels) or {}
  local t = math.max(0, math.min(1, tonumber(level) or 0))
  for i = 1, #curve do
    local at = tonumber(levels[i]) or ((i - 1) / math.max(1, #curve - 1))
    if at >= t then
      if i == 1 then return curve[1] or 0.0 end
      local prev = tonumber(levels[i - 1]) or 0
      local span = (at - prev)
      local f = (span > 0) and ((t - prev) / span) or 0
      return (curve[i - 1] or 0) + ((curve[i] or 0) - (curve[i - 1] or 0)) * f
    end
  end
  return curve[#curve] or 0.0
end

-- Which zones actually touch, and how much border they share. Derived once from
-- the cell mask; a coupling between zones that do not touch is not a coupling.
function vaZoneAdjacency()
  if vaZoneAdjacencyCache then return vaZoneAdjacencyCache end
  local index = vaZoneCellIndex and vaZoneCellIndex()
  if not index then return nil end
  local res, owner = index.res, index.owner
  local shared, perimeter = {}, {}
  for row = 0, res - 1 do
    for col = 0, res - 1 do
      -- vaZoneCellIndex stores the zone TABLE per cell, not its id; comparing
      -- those directly is a runtime error, and it takes the whole GameFrame
      -- callin down with it.
      local az = owner[row * res + col]
      local a = az and az.zoneId
      if a then
        perimeter[a] = (perimeter[a] or 0) + 1
        -- Checked one at a time: ipairs over {nil, x} stops at the first hole
        -- and would silently drop every south border on the map's east edge.
        local rz = (col < res - 1) and owner[row * res + col + 1] or nil
        local dz = (row < res - 1) and owner[(row + 1) * res + col] or nil
        local rb = rz and rz.zoneId
        if rb and rb ~= a then
          local key = (a < rb) and (a .. "|" .. rb) or (rb .. "|" .. a)
          shared[key] = (shared[key] or 0) + 1
        end
        local db = dz and dz.zoneId
        if db and db ~= a then
          local key = (a < db) and (a .. "|" .. db) or (db .. "|" .. a)
          shared[key] = (shared[key] or 0) + 1
        end
      end
    end
  end
  vaZoneAdjacencyCache = { shared = shared, perimeter = perimeter }
  return vaZoneAdjacencyCache
end

-- Units crossing a border are the live half of "entanglement".
function vaRecordZonePresence(unitID, zoneId)
  vaUnitZone = vaUnitZone or {}
  local was = vaUnitZone[unitID]
  vaUnitZone[unitID] = zoneId
  if was and zoneId and was ~= zoneId then
    vaZoneFlow = vaZoneFlow or {}
    local key = (was < zoneId) and (was .. "|" .. zoneId) or (zoneId .. "|" .. was)
    vaZoneFlow[key] = (vaZoneFlow[key] or 0) + 1
  end
end

-- Move the world relative to the sea. Idempotent: it only ever applies the
-- DIFFERENCE between where the waterline is and where it should be.
function vaApplyWaterline(level)
  local elevation = vaWaterElevation(level)
  if not elevation then return false end
  local resting = vaWaterElevation(0) or 0
  local wanted = elevation - resting
  -- The LOGICAL level always tracks, even when the physical shift is too small
  -- to bother the engine with. Deferring both would stall a slow ramp forever:
  -- the level would never advance, so the next step would ask for the same
  -- sub-threshold delta again.
  vaWaterLevel = level
  local delta = wanted - vaWaterApplied
  if math.abs(delta) < 0.05 then return false end
  if Spring.AdjustHeightMap then
    Spring.AdjustHeightMap(0, 0, Game.mapSizeX or 0, Game.mapSizeZ or 0, -delta)
  end
  vaWaterApplied = wanted
  Spring.SetGameRulesParam("va_water_level", level)
  Spring.SetGameRulesParam("va_water_sunk", vaWaterApplied)
  return true
end

-- Ramp the waterline over time so a flood reads as an event, not a teleport.
function vaStepWaterline()
  if not vaWaterTarget then return end
  local remaining = vaWaterTarget - vaWaterLevel
  if math.abs(remaining) <= math.abs(vaWaterStep) or vaWaterStep == 0 then
    vaApplyWaterline(vaWaterTarget)
    Spring.Echo(string.format("VA_HYDRO_DONE level=%.3f sunk=%.1f", vaWaterLevel, vaWaterApplied))
    if testHooks and testHooks.hydroDone and not testHooks.hydroProbe then
      testHooks.hydroProbe = Spring.GetGameFrame() + 90
    end
    if SendToUnsynced then
      SendToUnsynced("VERDANCE_HYDRO", "settled", vaWaterLevel)
    end
    vaWaterTarget = nil
    vaWaterStep = 0
    return
  end
  vaApplyWaterline(vaWaterLevel + vaWaterStep)
end

-- The waterline the campaign handed this mission. Applied once at start, so a
-- mission on a flooded map begins flooded rather than flooding on camera.
function vaInitWaterline()
  local hydro = mission and mission.hydrology
  local level = hydro and tonumber(hydro.level) or 0
  vaWaterLevel = 0.0
  vaWaterApplied = 0.0
  vaWaterTarget = nil
  vaZoneFlow = {}
  vaUnitZone = {}
  if level > 0 then
    vaApplyWaterline(level)
  end
  Spring.SetGameRulesParam("va_water_level", vaWaterLevel)
  Spring.Echo(string.format("VA_HYDRO_INIT level=%.3f sunk=%.1f amplitude=%s",
    vaWaterLevel, vaWaterApplied,
    tostring(hydro and hydro.amplitude or "n/a")))
end

-- What the terrain and the army look like right now, for the flood probe.
function vaEchoHydroProbe(tag, frame)
  local sx, sz = Game.mapSizeX or 0, Game.mapSizeZ or 0
  local samples = {}
  for _, at in ipairs({ 0.25, 0.5, 0.75 }) do
    local x, z = sx * at, sz * at
    samples[#samples + 1] = string.format("%.0f", Spring.GetGroundHeight(x, z) or 0)
  end
  local alive, underwater, structures = 0, 0, 0
  for _, teamID in ipairs(Spring.GetTeamList() or {}) do
    for _, unitID in ipairs(Spring.GetTeamUnits(teamID) or {}) do
      if Spring.ValidUnitID(unitID) and not Spring.GetUnitIsDead(unitID) then
        alive = alive + 1
        local ux, uy, uz = Spring.GetUnitPosition(unitID)
        if uy and uy < 0 then underwater = underwater + 1 end
        local ud = UnitDefs[Spring.GetUnitDefID(unitID) or -1]
        if ud and (ud.isImmobile or (ud.speed or 0) <= 0) then
          structures = structures + 1
        end
      end
    end
  end
  Spring.Echo(string.format(
    "VA_HYDRO_PROBE %s frame=%d level=%.3f sunk=%.1f ground=%s units=%d underwater=%d structures=%d",
    tag, frame, tonumber(vaWaterLevel) or 0, tonumber(vaWaterApplied) or 0,
    table.concat(samples, "/"), alive, underwater, structures))
end

function vaBeginWaterline(target, seconds)
  local to = math.max(0, math.min(1, tonumber(target) or 0))
  local span = math.max(1, math.floor((tonumber(seconds) or 20) * 30 / VA_WATER_TICK))
  vaWaterTarget = to
  vaWaterStep = (to - vaWaterLevel) / span
  Spring.Echo(string.format("VA_HYDRO_BEGIN from=%.3f to=%.3f seconds=%s",
    vaWaterLevel, to, tostring(seconds)))
  if SendToUnsynced then
    SendToUnsynced("VERDANCE_HYDRO", (to > vaWaterLevel) and "rising" or "falling", to)
  end
end

-- Sum metrics across all teams in a zone bucket (total military presence)
local function sumZoneMetrics(zoneEntry)
  local av, bp, dp = 0, 0, 0
  if not zoneEntry or not zoneEntry.teams then return av, bp, dp end
  for _, bucket in pairs(zoneEntry.teams) do
    av = av + (bucket.metrics.armyValue or 0)
    bp = bp + (bucket.metrics.buildPower or 0)
    dp = dp + (bucket.metrics.defensiveValue or 0)
  end
  return av, bp, dp
end

local function generateTranslationPacket(zoneBuckets)
  if not zoneMap or type(zoneMap.zones) ~= "table" or #zoneMap.zones == 0 then
    Spring.Echo("VA_TRANSLATION_SKIP no zone map loaded")
    return nil
  end

  local N = #zoneMap.zones
  -- Spring.GetMapWaterLevel does NOT exist on this engine; the old guarded call
  -- silently returned 0, which pinned the hydrology anchor at zero forever and
  -- made the whole last row and column of the matrix carry no information.
  -- The waterline is campaign state now, and it is measured per zone.
  local rho_H = math.max(0, math.min(1, tonumber(vaWaterLevel) or 0))
  local waterLevel = vaWaterElevation(rho_H) or 0

  -- Build flat zone list from real data
  local zones = {}
  for i, zone in ipairs(zoneMap.zones) do
    local entry = zoneBuckets[zone.zoneId] or { zone = zone, teams = {} }
    local av, bp, dp = sumZoneMetrics(entry)
    zones[i] = {
      id      = i,
      zoneId  = zone.zoneId,
      name    = zone.label or zone.zoneId,
      type    = getZoneHydroType(zone),
      av      = av,
      bp      = bp,
      dp      = dp,
    }
  end

  -- Instantiate (N+1) x (N+1) Hermitian matrix
  local matrix = {}
  for i = 1, N + 1 do
    matrix[i] = {}
    for j = 1, N + 1 do matrix[i][j] = 0 end
  end

  -- Step 1: Diagonals (zone density)
  for k = 1, N do
    local z = zones[k]
    matrix[k][k] = math.tanh((z.av + z.bp + z.dp) / 5735.0)
  end
  matrix[N+1][N+1] = rho_H  -- Environmental hydrology anchor

  -- Step 2: Off-diagonals -- entanglement between zones that actually TOUCH.
  --
  -- This used to couple every pair by how similar their army values were, which
  -- made two empty zones in opposite corners read as maximally entangled, and
  -- grew as N^2 with the zone count. A coupling is now a real front: shared
  -- border, forces on BOTH sides, plus the units measured crossing it.
  local geo = vaZoneAdjacency and vaZoneAdjacency()
  local shared = geo and geo.shared or {}
  local perimeter = geo and geo.perimeter or {}
  local flow = vaZoneFlow or {}
  local flowPeak = 1
  for _, count in pairs(flow) do
    if count > flowPeak then flowPeak = count end
  end
  for i = 1, N do
    for j = i + 1, N do
      local a, b = zones[i].zoneId, zones[j].zoneId
      local key = (a < b) and (a .. "|" .. b) or (b .. "|" .. a)
      local border = shared[key]
      if border and border > 0 then
        local edge = math.min(perimeter[a] or border, perimeter[b] or border)
        local borderShare = math.min(1.0, border / math.max(1, edge))
        -- A front needs two sides: the weaker presence sets the coupling.
        local weaker = math.min(zones[i].av, zones[j].av)
        local stronger = math.max(zones[i].av, zones[j].av, 1.0)
        local pressure = math.tanh(weaker / 2000.0) * (weaker / stronger)
        local crossing = (flow[key] or 0) / flowPeak
        local c = BASE_COUPLING * borderShare * (0.65 * pressure + 0.35 * crossing)
        matrix[i][j] = c
        matrix[j][i] = c
      end
    end
    -- Step 3: Hydrological coupling -- how much of this zone the current
    -- waterline actually takes, measured from its own flood curve.
    local wet = vaZoneSubmerged(zoneMap.zones[i], rho_H)
    local hc = BASE_HYDRO_COUPLING * wet
    matrix[i][N+1] = hc
    matrix[N+1][i] = hc
  end

  -- Build canonical packet
  local packet = {
    protocol = "VERDANCE_TRANSLATION_V1",
    frame    = Spring.GetGameFrame(),
    global   = { hydrology = { level = waterLevel, saturation = tonumber(string.format("%.3f", rho_H)) } },
    nodes    = {},
    entanglements = {},
    factoids = {},
  }

  for i = 1, N do
    local z = zones[i]
    table.insert(packet.nodes, {
      id           = z.id,
      zoneId       = z.zoneId,
      name         = z.name,
      type         = z.type,
      raw          = { av = z.av, bp = z.bp, dp = z.dp },
      density      = tonumber(string.format("%.3f", matrix[i][i])),
      hydroCoupling= tonumber(string.format("%.3f", matrix[i][N+1])),
    })
  end

  for i = 1, N do
    for j = i + 1, N do
      local coupling = matrix[i][j]
      if coupling > ENTANGLEMENT_THRESHOLD then
        table.insert(packet.entanglements, {
          zoneIds  = { zones[i].zoneId, zones[j].zoneId },
          names    = { zones[i].name, zones[j].name },
          coupling = tonumber(string.format("%.3f", coupling)),
        })
      end
    end
  end

  for _, node in ipairs(packet.nodes) do
    if node.type == "low-flood" and node.hydroCoupling > HYDRO_HAZARD_THRESHOLD then
      table.insert(packet.factoids, {
        type    = "HAZARD",
        zoneId  = node.zoneId,
        message = node.name .. " is critically exposed to current hydrology levels.",
      })
    end
    if node.density > DENSITY_HOTSPOT then
      table.insert(packet.factoids, {
        type    = "HOTSPOT",
        zoneId  = node.zoneId,
        message = node.name .. " has reached critical military density.",
      })
    end
  end

  return packet
end

-- Minimal table -> JSON serializer for the canonical packet
local function serializeTranslationPacket(p)
  if not p then return nil end

  local nodeParts = {}
  for _, n in ipairs(p.nodes) do
    table.insert(nodeParts, string.format(
      '{"id":%d,"zoneId":%s,"name":%s,"type":%s,"raw":{"av":%.0f,"bp":%.0f,"dp":%.0f},"density":%.3f,"hydroCoupling":%.3f}',
      n.id, jstr(n.zoneId), jstr(n.name), jstr(n.type), n.raw.av, n.raw.bp, n.raw.dp, n.density, n.hydroCoupling
    ))
  end

  local entParts = {}
  for _, e in ipairs(p.entanglements) do
    table.insert(entParts, string.format(
      '{"zoneIds":[%s,%s],"names":[%s,%s],"coupling":%.3f}',
      jstr(e.zoneIds[1]), jstr(e.zoneIds[2]), jstr(e.names[1]), jstr(e.names[2]), e.coupling
    ))
  end

  local factParts = {}
  for _, f in ipairs(p.factoids) do
    table.insert(factParts, string.format(
      '{"type":%s,"zoneId":%s,"message":%s}',
      jstr(f.type), jstr(f.zoneId), jstr(f.message)
    ))
  end

  return string.format(
    '{"protocol":%s,"frame":%d,"global":{"hydrology":{"level":%.1f,"saturation":%.3f}},"nodes":[%s],"entanglements":[%s],"factoids":[%s]}',
    jstr(p.protocol), p.frame,
    p.global.hydrology.level, p.global.hydrology.saturation,
    table.concat(nodeParts, ","),
    table.concat(entParts, ","),
    table.concat(factParts, ",")
  )
end

function logAndBroadcastTranslation()
  -- We need fresh zoneBuckets - rebuild them inline
  local zoneBucketsLive = {}
  if zoneMap and type(zoneMap.zones) == "table" then
    -- Build fresh per-zone buckets from current unit positions
    for _, teamID in ipairs(Spring.GetTeamList()) do
      local units = Spring.GetTeamUnits(teamID) or {}
      for _, unitID in ipairs(units) do
        if Spring.ValidUnitID(unitID) and not Spring.GetUnitIsDead(unitID) then
          local defID = Spring.GetUnitDefID(unitID)
          local x, _, z = Spring.GetUnitPosition(unitID)
          if x and z then
            local zone = zoneForPosition(x, z)
            if zone and zone.zoneId then
              zoneBucketsLive[zone.zoneId] = zoneBucketsLive[zone.zoneId] or { zone = zone, teams = {} }
              if not zoneBucketsLive[zone.zoneId].teams[teamID] then
                local zb = makeTeamBucket(teamID)
                zb.metrics = emptyMetrics()
                zb.unitCountsByDef = {}
                zoneBucketsLive[zone.zoneId].teams[teamID] = zb
              end
              addUnitToBucket(zoneBucketsLive[zone.zoneId].teams[teamID], defID)
            end
          end
        end
      end
    end
  end

  local packet = generateTranslationPacket(zoneBucketsLive)
  local json   = serializeTranslationPacket(packet)
  if not json then
    Spring.Echo("VA_TRANSLATION_ERROR failed to serialize packet")
    return
  end

  -- Log to infolog (chunked, readable in headless output)
  Spring.Echo("VA_TRANSLATION_PACKET_COMPACT " .. json)
  logJsonChunked("VA_TRANSLATION_PACKET", json)

  -- Broadcast to LuaUI Overmind Widget (no-op in headless, active in playable)
  if SendToUnsynced then
    SendToUnsynced("VERDANCE_TELEMETRY", json)
  end

  Spring.Echo(string.format(
    "VA_TRANSLATION_OK frame=%d zones=%d entanglements=%d factoids=%d water=%.3f",
    packet.frame, #packet.nodes, #packet.entanglements, #packet.factoids,
    tonumber(vaWaterLevel) or 0
  ))
  -- Crossings are counted BETWEEN packets, so the next matrix measures the next
  -- interval rather than the whole match.
  vaZoneFlow = {}
end

-- ============================================================
-- OBJECTIVE AUTOMATION
-- Real win/loss detection: target destruction, zone holds,
-- extraction, commander loss, player wipe.
-- ============================================================

local function objectiveKind()
  return mission and mission.objective and mission.objective.kind or ""
end

local function zoneRectFor(zoneId)
  if not zoneId or not zoneMap or type(zoneMap.zones) ~= "table" then return nil end
  local sx = Game.mapSizeX or 0
  local sz = Game.mapSizeZ or 0
  for _, z in ipairs(zoneMap.zones) do
    if z.zoneId == zoneId then
      local b = z.bounds or {}
      return {
        normalizedToElmos(b.xMin, sx),
        normalizedToElmos(b.zMin, sz),
        normalizedToElmos(b.xMax, sx),
        normalizedToElmos(b.zMax, sz),
      }, z.label
    end
  end
  return nil
end

local function scanZoneRect(rect)
  local playerPresent, enemyCombat = false, false
  if not rect then return playerPresent, enemyCombat end
  local units = Spring.GetUnitsInRectangle(rect[1], rect[2], rect[3], rect[4])
  for i = 1, #units do
    local uid = units[i]
    if Spring.ValidUnitID(uid) and not Spring.GetUnitIsDead(uid) then
      local team = Spring.GetUnitTeam(uid)
      if team == playerTeamID then
        playerPresent = true
      elseif team ~= gaiaTeamID and not Spring.AreTeamsAllied(playerTeamID, team) then
        -- Alliance-aware: allied Null Merc teams (allied via start-script Ally
        -- lines, distinct allyTeamID) are NOT enemy combat.
        if canFight(Spring.GetUnitDefID(uid)) then enemyCombat = true end
      end
    end
  end
  return playerPresent, enemyCombat
end

-- Pillar B wave machinery -----------------------------------------------------
local function teamUnitCentroid(teamID)
  local units = Spring.GetTeamUnits(teamID) or {}
  local n, sx, sz = 0, 0, 0
  for i = 1, #units do
    local x, _, z = Spring.GetUnitPosition(units[i])
    if x then sx = sx + x; sz = sz + z; n = n + 1 end
  end
  if n == 0 then return nil end
  return sx / n, sz / n
end

local function teamCombatDefNames(teamID)
  -- Sample the team's live mobile combat unit types; reinforcements are "more of
  -- what this force already fields", so no faction recipe is needed here.
  local seen, defs = {}, {}
  local units = Spring.GetTeamUnits(teamID) or {}
  for i = 1, #units do
    local dID = Spring.GetUnitDefID(units[i])
    local ud = dID and UnitDefs[dID]
    if ud and not (ud.isBuilding or ud.isFactory or ud.speed == 0) then
      local fights = ud.canAttack or (ud.weapons and #ud.weapons > 0)
      if fights and not seen[ud.name] then seen[ud.name] = true; defs[#defs + 1] = ud.name end
    end
  end
  if #defs == 0 then
    -- The camp's mobiles are all dead: reinforcements keep arriving from
    -- offscreen (seed-declared fallback), so the climax cannot quietly dry up.
    local fb = mission and mission.escalation and mission.escalation.fallbackWaveDefs
    if type(fb) == "table" then
      for _, name in ipairs(fb) do
        if UnitDefNames[name] and not seen[name] then seen[name] = true; defs[#defs + 1] = name end
      end
    end
  end
  return defs
end

local function spawnWave(fromTeamID, count, targetX, targetZ, label)
  if not fromTeamID or count < 1 then return 0 end
  local defs = teamCombatDefNames(fromTeamID)
  if #defs == 0 then return 0 end
  local cx, cz = teamUnitCentroid(fromTeamID)
  if not cx and targetZoneRect then
    -- Nothing left of the camp to anchor on: arrive at the objective zone edge.
    cx = (targetZoneRect[1] + targetZoneRect[3]) * 0.5
    cz = (targetZoneRect[2] + targetZoneRect[4]) * 0.5
  end
  if not cx then return 0 end
  local spawned = 0
  for i = 1, count do
    local defName = defs[((i - 1) % #defs) + 1]
    local ang = (i / count) * 6.28318
    local x = cx + math.cos(ang) * 120
    local z = cz + math.sin(ang) * 120
    local uID = Spring.CreateUnit(defName, x, Spring.GetGroundHeight(x, z), z, 0, fromTeamID)
    if uID then
      spawned = spawned + 1
      if targetX and CMD and CMD.FIGHT then
        Spring.GiveOrderToUnit(uID, CMD.FIGHT, { targetX, Spring.GetGroundHeight(targetX, targetZ), targetZ }, {})
      end
    end
  end
  if spawned > 0 then
    Spring.Echo("VA_WAVE_SPAWNED team=" .. tostring(fromTeamID) .. " count=" .. tostring(spawned) .. " kind=" .. tostring(label or "reinforce"))
    -- Telegraph the wave: the widget pings the muster point and plays a warning
    -- so escalation reads as an event, not units silently appearing.
    if SendToUnsynced then
      SendToUnsynced("VERDANCE_BEAT", "wave_warning", cx, Spring.GetGroundHeight(cx, cz) or 0, cz, tostring(label or "reinforcements"))
    end
  end
  return spawned
end

-- ============================================================
-- Named hero lifecycle (Fire Emblem doctrine).
-- alive -> down_pending_wreck -> down (wreck tracked) -> recovered | lost.
-- BAR's own gadgets guarantee the primitives: corpses link to their source
-- unit (unit_corpse_link.lua) and resurrection fires UnitCreated with the
-- rez bot as builder while the corpse still exists (unit_resurrected.lua).
-- ============================================================

local setTerminal  -- forward declaration: a lost critical hero ends the mission

local function broadcastHeroEvent(event, rec, x, z)
  Spring.Echo("VA_HERO_" .. string.upper(event) .. " id=" .. rec.id .. " critical=" .. tostring(rec.missionCritical))
  publishHeroRules()
  if SendToUnsynced then
    SendToUnsynced("VERDANCE_HERO_EVENT", event, rec.id, rec.name, rec.missionCritical and 1 or 0, x or 0, z or 0)
  end
end

local function heroLost(rec, how)
  -- WO-008: killing / losing a named unit (or its wreck) does NOT abort the
  -- sortie. Outcome is wreck bookkeeping — dead / wounded / recovered — and
  -- the match continues until objective, extract, wipe, or force spent.
  if rec.state == "lost" then return end
  rec.state = "lost"
  rec.diedHow = tostring(how or "")
  broadcastHeroEvent("lost", rec, rec.deathX, rec.deathZ)
  Spring.Echo("VA_NAMED_DEAD " .. rec.id .. " cause=" .. tostring(how or "unknown")
    .. " critical=" .. tostring(rec.missionCritical == true))
  -- Intentionally no setTerminal("defeat", "hero_lost_*") — DCO-01 wreck rule.
end

local function heroRecovered(rec, newUnitID)
  rec.state = "alive"
  rec.unitID = newUnitID
  rec.rezGraceUntil = nil
  heroByUnitID[newUnitID] = rec.id
  Spring.SetUnitRulesParam(newUnitID, "va_hero", 1, { public = true })
  Spring.SetUnitRulesParam(newUnitID, "va_hero_id", rec.id, { public = true })
  Spring.SetUnitRulesParam(newUnitID, "va_hero_name", rec.name, { public = true })
  Spring.SetUnitRulesParam(newUnitID, "va_hero_critical", rec.missionCritical and 1 or 0, { public = true })
  Spring.SetUnitRulesParam(newUnitID, "va_hero_level", rec.level or 1, { public = true })
  Spring.SetUnitRulesParam(newUnitID, "va_hero_rank", rec.rank or "Runner", { public = true })
  -- BAR's unit_resurrected gadget restores experience and heals the fresh
  -- instance; only the hero toughness multiplier needs re-applying.
  if Spring.GetUnitHealth and Spring.SetUnitMaxHealth then
    local _, maxH = Spring.GetUnitHealth(newUnitID)
    if maxH then pcall(Spring.SetUnitMaxHealth, newUnitID, maxH * rec.hpMult) end
  end
  -- XP NEVER drops on death/rez: restore peak (max of lastXp/peakXp).
  local keep = math.max(tonumber(rec.peakXp) or 0, tonumber(rec.lastXp) or 0)
  rec.peakXp = keep
  rec.lastXp = keep
  Spring.SetUnitRulesParam(newUnitID, "va_hero_xp", keep, { public = true })
  if Spring.SetUnitExperience and keep > 0 then
    local cur = 0
    if Spring.GetUnitExperience then cur = Spring.GetUnitExperience(newUnitID) or 0 end
    if cur < keep then pcall(Spring.SetUnitExperience, newUnitID, keep) end
  end
  local x, _, z = Spring.GetUnitPosition(newUnitID)
  broadcastHeroEvent("recovered", rec, x, z)
  Spring.Echo("VA_NAMED_RECOVERED " .. rec.id .. " unit=" .. tostring(newUnitID) .. " xp=" .. tostring(keep))
end

local function heroOnUnitDestroyed(unitID)
  local id = heroByUnitID[unitID]
  if not id then return end
  local rec = heroes[id]
  heroByUnitID[unitID] = nil
  rec.unitID = nil
  if Spring.GetUnitExperience then
    local cur = Spring.GetUnitExperience(unitID) or 0
    rec.lastXp = cur
    rec.peakXp = math.max(tonumber(rec.peakXp) or 0, cur)
  end
  -- Capture unitDef at death so rez matching still works if the seed omitted it.
  if (not rec.unitDefName or rec.unitDefName == "") and Spring.GetUnitDefID then
    local dID = Spring.GetUnitDefID(unitID)
    local ud = dID and UnitDefs[dID]
    if ud and ud.name then rec.unitDefName = ud.name end
  end
  if terminal then return end
  rec.everDown = true
  rec.state = "down_pending_wreck"
  local x, _, z = Spring.GetUnitPosition(unitID)
  rec.deathX, rec.deathZ = x, z
  rec.wreckDeadline = (Spring.GetGameFrame() or 0) + HERO_WRECK_TIMEOUT
  heroPendingWreck[unitID] = id
end

local function heroOnFeatureCreated(featureID, allyTeamID, sourceID)
  if not next(heroPendingWreck) then return end
  if not sourceID and GG and GG.GetCorpsePriorUnitID then
    -- Older engine path: BAR's corpse-link registry backfills the source unit.
    sourceID = GG.GetCorpsePriorUnitID(featureID)
  end
  local id = sourceID and heroPendingWreck[sourceID]
  if not id then return end
  heroPendingWreck[sourceID] = nil
  local rec = heroes[id]
  if rec.state ~= "down_pending_wreck" then return end
  rec.state = "down"
  rec.wreckFeatureID = featureID
  heroByFeatureID[featureID] = id
  if Spring.SetFeatureRulesParam then
    Spring.SetFeatureRulesParam(featureID, "va_hero_wreck", id, { public = true })
    Spring.SetFeatureRulesParam(featureID, "va_hero_wreck_name", rec.name, { public = true })
    Spring.SetFeatureRulesParam(featureID, "va_hero_wreck_def", rec.unitDefName or "", { public = true })
  end
  local x, _, z = Spring.GetFeaturePosition(featureID)
  if x then rec.deathX, rec.deathZ = x, z end
  broadcastHeroEvent("down", rec, x or rec.deathX, z or rec.deathZ)
end

local function resolveWorkerFeatureID(builderID)
  if not builderID or not Spring.GetUnitWorkerTask then return nil end
  local cmdID, targetID = Spring.GetUnitWorkerTask(builderID)
  if cmdID ~= CMD.RESURRECT or not targetID then return nil end
  local featureID = targetID
  -- Engine quirk copied from BAR's unit_resurrected.lua: worker-task feature
  -- IDs are offset by Game.maxUnits on engines without noOffsetForFeatureID.
  if not (Engine and Engine.FeatureSupport and Engine.FeatureSupport.noOffsetForFeatureID) then
    featureID = featureID - Game.maxUnits
  end
  return featureID
end

local function builderCanResurrect(builderID)
  if not builderID then return false end
  local dID = Spring.GetUnitDefID(builderID)
  local ud = dID and UnitDefs[dID]
  return ud and ud.canResurrect == true
end

-- Drop 2 act tech gate (gadget-env global: main-chunk local budget).
-- Act 1 ground control: no new structures (fight with the warband you brought).
-- Act 2 constrained RTS: build T1 only; T2/T3 arrive as earned special units.
-- Act 3 finale: gate off — full unconstrained BAR.
-- Resurrection is exempt so hero wrecks stay rescuable in tech-locked acts.
function vaTechGateAllows(unitDefID, builderID, builderTeam)
  if not doctrine.techGateEnabled then return true end
  if builderTeam ~= playerTeamID or not builderID then return true end
  if builderCanResurrect(builderID) and Spring.GetUnitWorkerTask then
    local cmdID = Spring.GetUnitWorkerTask(builderID)
    if cmdID == CMD.RESURRECT then return true end
  end
  local ud = UnitDefs[unitDefID]
  if not ud then return true end
  local tech = tonumber(ud.customParams and ud.customParams.techlevel) or 1
  local denyTech = tech > doctrine.techMaxLevel
  local denyStruct = (not doctrine.techBuildStructures) and ud.isBuilding == true
  if not denyTech and not denyStruct then return true end
  doctrine.techDenials = doctrine.techDenials + 1
  local frame = Spring.GetGameFrame() or 0
  if frame - doctrine.techLastDenyFrame > 300 then
    doctrine.techLastDenyFrame = frame
    SendToUnsynced("VERDANCE_BEAT", "tech_locked",
      tostring(ud.name or "unit"),
      denyStruct and "structures" or ("t" .. tostring(tech)),
      doctrine.actNumber, tostring(doctrine.actMode))
    Spring.Echo("VA_TECH_GATE_DENY def=" .. tostring(ud.name)
      .. " tech=" .. tostring(tech) .. " cap=" .. tostring(doctrine.techMaxLevel)
      .. " structures=" .. tostring(doctrine.techBuildStructures)
      .. " denials=" .. tostring(doctrine.techDenials))
  end
  return false
end

-- Match a freshly created unit back to a downed hero (feature id, def+position).
local function findHeroForResurrection(unitID, unitDefID, builderID)
  local featureID = resolveWorkerFeatureID(builderID)
  if featureID and heroByFeatureID[featureID] then
    return heroByFeatureID[featureID], featureID
  end

  local ud = unitDefID and UnitDefs[unitDefID]
  local defName = ud and ud.name or ""
  local x, _, z = Spring.GetUnitPosition(unitID)
  if not x then return nil, nil end

  local bestId, bestDist = nil, nil
  for id, rec in pairs(heroes) do
    if rec.state == "down" or rec.state == "rez_grace" or rec.state == "down_pending_wreck" then
      local expected = rec.unitDefName or ""
      if expected == "" or expected == defName then
        local dx = x - (rec.deathX or x)
        local dz = z - (rec.deathZ or z)
        local dist = dx * dx + dz * dz
        local limit = HERO_REZ_MATCH_DIST * HERO_REZ_MATCH_DIST
        if dist <= limit and (not bestDist or dist < bestDist) then
          bestId, bestDist = id, dist
        end
      end
    end
  end
  return bestId, featureID
end

local function heroOnUnitCreated(unitID, unitDefID, unitTeam, builderID)
  -- Need either a live wreck map or a hero in rez grace / pending.
  local anyDown = next(heroByFeatureID) ~= nil
  if not anyDown then
    for _, rec in pairs(heroes) do
      if rec.state == "down" or rec.state == "rez_grace" or rec.state == "down_pending_wreck" then
        anyDown = true
        break
      end
    end
  end
  if not anyDown then return end

  -- Only treat as rez when the builder is rezzing or is a rez-capable unit.
  -- (Worker task can already be cleared by the time we run; def check is backup.)
  local featureFromWorker = resolveWorkerFeatureID(builderID)
  if not featureFromWorker and not builderCanResurrect(builderID) then
    return
  end

  local id, featureID = findHeroForResurrection(unitID, unitDefID, builderID)
  if not id then return end
  local rec = heroes[id]
  if featureID then
    wreckConsumedByRez[featureID] = true
    heroByFeatureID[featureID] = nil
  elseif rec.wreckFeatureID then
    wreckConsumedByRez[rec.wreckFeatureID] = true
    heroByFeatureID[rec.wreckFeatureID] = nil
  end
  rec.wreckFeatureID = nil
  if unitTeam == playerTeamID or (Spring.AreTeamsAllied and Spring.AreTeamsAllied(unitTeam, playerTeamID)) then
    heroRecovered(rec, unitID)
  else
    heroLost(rec, "captured")
  end
end

local function heroOnFeatureDestroyed(featureID)
  if wreckConsumedByRez[featureID] then
    wreckConsumedByRez[featureID] = nil
    return
  end
  local id = heroByFeatureID[featureID]
  if not id then return end
  heroByFeatureID[featureID] = nil
  local rec = heroes[id]
  rec.wreckFeatureID = nil
  -- Rez path often destroys the corpse a tick before UnitCreated. Do not
  -- permanently kill the hero until the grace window expires with no reclaim.
  if rec.state == "down" or rec.state == "down_pending_wreck" or rec.state == "rez_grace" then
    rec.state = "rez_grace"
    rec.rezGraceUntil = (Spring.GetGameFrame() or 0) + HERO_REZ_GRACE
    Spring.Echo("VA_HERO_REZ_GRACE id=" .. id .. " feature=" .. tostring(featureID))
    return
  end
  heroLost(rec, "wreck_destroyed")
end

local function checkHeroWreckTimeouts(frame)
  if next(heroPendingWreck) then
    for deadUnitID, id in pairs(heroPendingWreck) do
      local rec = heroes[id]
      if rec and rec.state == "down_pending_wreck" and frame > (rec.wreckDeadline or 0) then
        heroPendingWreck[deadUnitID] = nil
        heroLost(rec, "no_wreck")
      end
    end
  end
  for id, rec in pairs(heroes) do
    if rec.state == "rez_grace" and frame > (rec.rezGraceUntil or 0) then
      heroLost(rec, "wreck_destroyed")
    end
  end
end

-- Terminal outcome for every hero: intact wrecks are dragged home only when the
-- line holds them dear (mission-critical); anyone else left in a wreck is gone.
local function finalizeHeroStates()
  for _, rec in pairs(heroes) do
    if rec.state == "lost" then
      rec.result = "dead"
    elseif rec.state == "down" or rec.state == "down_pending_wreck" or rec.state == "rez_grace" then
      -- Still a wreck (or rez race unresolved): critical = wounded carry, else dead.
      rec.result = rec.missionCritical and "wounded" or "dead"
    else
      -- alive: recovered mid-match still counts as wounded scar unless fully clean.
      rec.result = rec.everDown and "wounded" or "survived"
      if rec.unitID and Spring.ValidUnitID(rec.unitID) and Spring.GetUnitExperience then
        local cur = Spring.GetUnitExperience(rec.unitID) or 0
        rec.lastXp = cur
        rec.peakXp = math.max(tonumber(rec.peakXp) or 0, cur)
      end
    end
    -- Sticky peak for dead/wounded too (farmed XP survives the wreck).
    rec.peakXp = math.max(tonumber(rec.peakXp) or 0, tonumber(rec.lastXp) or 0)
    rec.lastXp = rec.peakXp
  end
end

-- ============================================================
-- In-mission beats: seed-authored WC3-style triggers -> actions.
-- All beats fire once; evaluation rides the CHECK_PERIOD cadence.
-- ============================================================

local function heroInState(heroId, state1, state2)
  if heroId then
    local rec = heroes[heroId]
    return rec ~= nil and (rec.state == state1 or rec.state == state2)
  end
  for _, rec in pairs(heroes) do
    if rec.state == state1 or rec.state == state2 then return true end
  end
  return false
end

local function heroWasRecovered(heroId)
  if heroId then
    local rec = heroes[heroId]
    return rec ~= nil and rec.state == "alive" and rec.everDown
  end
  for _, rec in pairs(heroes) do
    if rec.state == "alive" and rec.everDown then return true end
  end
  return false
end

local function compileBeats()
  local list = mission and mission.beats
  if type(list) ~= "table" then return end
  for _, b in ipairs(list) do
    local t = b.trigger or {}
    local kind = tostring(t.type or "")
    local ok = true
    local compiled = {
      id = tostring(b.id or ("beat_" .. tostring(#beats + 1))),
      trigger = kind,
      afterBeat = b.afterBeat and tostring(b.afterBeat) or nil,
      actions = b.actions or {},
    }
    if kind == "time" then
      compiled.frame = tonumber(t.frame) or math.floor((tonumber(t.seconds) or 0) * 30)
    elseif kind == "zone_entered" then
      compiled.rect = zoneRectFor(t.zoneId)
      ok = compiled.rect ~= nil
    elseif kind == "objective_progress" then
      compiled.atLeast = tonumber(t.atLeast) or 0.5
    elseif kind == "wave_spawned" then
      compiled.index = tonumber(t.index) or 1
    elseif kind == "hero_down" or kind == "hero_recovered" or kind == "hero_lost" then
      compiled.heroId = t.heroId and tostring(t.heroId) or nil
    elseif kind == "objective_complete" or kind == "extraction_started" then
      -- no params
    else
      ok = false
    end
    if ok then
      beats[#beats + 1] = compiled
    else
      Spring.Echo("VA_BEAT_INVALID id=" .. tostring(b.id) .. " type=" .. kind)
    end
  end
  Spring.Echo("VA_BEATS_COMPILED count=" .. tostring(#beats))
end

local function beatTriggerMet(b, frame)
  if b.afterBeat and not beatFiredSet[b.afterBeat] then return false end
  local k = b.trigger
  if k == "time" then
    return frame >= (b.frame or 0)
  elseif k == "zone_entered" then
    local playerPresent = scanZoneRect(b.rect)
    return playerPresent == true
  elseif k == "objective_progress" then
    if objectiveTargetCount <= 0 then return false end
    return (objectiveTargetsDestroyed / objectiveTargetCount) >= (b.atLeast or 0.5)
  elseif k == "wave_spawned" then
    return waves.spawned >= (b.index or 1)
  elseif k == "objective_complete" then
    return objectiveComplete
  elseif k == "extraction_started" then
    return extractionHoldFrames > 0
  elseif k == "hero_down" then
    return heroInState(b.heroId, "down", "down_pending_wreck")
  elseif k == "hero_recovered" then
    return heroWasRecovered(b.heroId)
  elseif k == "hero_lost" then
    return heroInState(b.heroId, "lost")
  end
  return false
end

local function beatActionXYZ(action)
  local x, z
  if action.zoneId then
    local rect = zoneRectFor(action.zoneId)
    if rect then
      x = (rect[1] + rect[3]) * 0.5
      z = (rect[2] + rect[4]) * 0.5
    end
  end
  if not x then
    x = normalizedToElmos(tonumber(action.x) or 0.5, Game.mapSizeX or 0)
    z = normalizedToElmos(tonumber(action.z) or 0.5, Game.mapSizeZ or 0)
  end
  return x, Spring.GetGroundHeight(x, z) or 0, z
end

local function runBeatSpawn(b, action)
  local teamID
  local t = action.team
  if t == "enemy" then teamID = objectiveTeamID
  elseif t == "merc" then teamID = mercTeamID
  else teamID = tonumber(t) end
  if not teamID then return end
  local x, _, z = beatActionXYZ(action)
  local spawned = 0
  local i = 0
  for _, u in ipairs(action.units or {}) do
    local defName = u.unitDefName or u.def
    local count = tonumber(u.count) or 1
    if defName and UnitDefNames[defName] then
      for _ = 1, count do
        i = i + 1
        local ux = x + ((i % 5) - 2) * 60
        local uz = z + math.floor(i / 5) * 60
        local uID = Spring.CreateUnit(defName, ux, Spring.GetGroundHeight(ux, uz), uz, 0, teamID)
        if uID then
          spawned = spawned + 1
          local tx, tz
          if action.fightTo == "player" then
            tx, tz = teamUnitCentroid(playerTeamID)
          elseif type(action.fightTo) == "table" then
            tx = normalizedToElmos(tonumber(action.fightTo.x) or 0.5, Game.mapSizeX or 0)
            tz = normalizedToElmos(tonumber(action.fightTo.z) or 0.5, Game.mapSizeZ or 0)
          end
          if tx and CMD and CMD.FIGHT then
            Spring.GiveOrderToUnit(uID, CMD.FIGHT, { tx, Spring.GetGroundHeight(tx, tz), tz }, {})
          end
        end
      end
    end
  end
  Spring.Echo("VA_BEAT_SPAWN id=" .. b.id .. " team=" .. tostring(teamID) .. " units=" .. tostring(spawned))
end

local function runBeatActions(b)
  for _, action in ipairs(b.actions or {}) do
    local kind = tostring(action.type or "")
    if kind == "bark" and SendToUnsynced then
      SendToUnsynced("VERDANCE_BEAT", "bark", tostring(action.speaker or "Ketha"), tostring(action.text or ""), tonumber(action.seconds) or 7)
    elseif kind == "marker" and SendToUnsynced then
      local x, y, z = beatActionXYZ(action)
      SendToUnsynced("VERDANCE_BEAT", "marker", x, y, z, tostring(action.text or ""))
    elseif kind == "sound" and SendToUnsynced then
      SendToUnsynced("VERDANCE_BEAT", "sound", tostring(action.file or "beep4"), tonumber(action.volume) or 1.0)
    elseif kind == "wave" then
      if objectiveTeamID then
        local px, pz = teamUnitCentroid(playerTeamID)
        spawnWave(objectiveTeamID, tonumber(action.count) or waves.baseSize, px, pz, "beat_" .. b.id)
      end
    elseif kind == "spawn" then
      runBeatSpawn(b, action)
    elseif kind == "hydrology" then
      -- Flood or drain. The waterline is a campaign scalar; this moves it
      -- inside a mission, over `seconds`, so it reads as an event.
      vaBeginWaterline(tonumber(action.to) or 0, tonumber(action.seconds) or 20)
    elseif kind == "objective_secondary" then
      local sid = tostring(action.id or b.id)
      secondaryObjectives[#secondaryObjectives + 1] = sid
      Spring.SetGameRulesParam("va_secondary_" .. sid, tostring(action.description or ""), { public = true })
      Spring.SetGameRulesParam("va_secondary_ids", table.concat(secondaryObjectives, ","), { public = true })
    end
  end
  Spring.Echo("VA_BEAT_FIRED id=" .. b.id)
end

local function checkBeats(frame)
  if #beats == 0 then return end
  for i = #beats, 1, -1 do
    local b = beats[i]
    if beatTriggerMet(b, frame) then
      runBeatActions(b)
      beatFiredSet[b.id] = true
      table.remove(beats, i)
    end
  end
end

-- Drop 4 (gadget-env globals — main chunk local budget): the full-victory
-- gate. Primary objective + every REQUIRED secondary + purge (when armed).
function vaAllObjectivesDone()
  if not objectiveComplete then return false end
  if extraObj.requiredLeft > 0 then return false end
  if extraObj.purge and not extraObj.purgeDone then return false end
  return true
end

function vaMaybeAnnounceAllDone()
  if extraObj.announced or not vaAllObjectivesDone() then return end
  extraObj.announced = true
  Spring.SetGameRulesParam("va_all_objectives_done", 1, { public = true })
  Spring.Echo("VA_ALL_OBJECTIVES_DONE")
  if SendToUnsynced then SendToUnsynced("VERDANCE_MISSION_EVENT", "all_objectives_complete", "") end
end

function vaCheckPurge(frame)
  if not extraObj.purge or extraObj.purgeDone then return end
  for teamID in pairs(extraObj.purgeTeams) do
    local n = Spring.GetTeamUnitCount(teamID)
    if n and n > 0 then return end
  end
  extraObj.purgeDone = true
  Spring.SetGameRulesParam("va_purge_done", 1, { public = true })
  Spring.Echo("VA_PURGE_COMPLETE frame=" .. tostring(frame))
  if SendToUnsynced then SendToUnsynced("VERDANCE_MISSION_EVENT", "purge_complete", "") end
  vaMaybeAnnounceAllDone()
end

local function onObjectiveComplete(how)
  if objectiveComplete then return end
  objectiveComplete = true
  objectiveCompleteHow = how or "complete"
  Spring.SetGameRulesParam("va_objective_complete", 1, { public = true })
  Spring.Echo("VA_OBJECTIVE_COMPLETE mission=" .. tostring(mission.missionId) .. " how=" .. objectiveCompleteHow)
  if SendToUnsynced then SendToUnsynced("VERDANCE_MISSION_EVENT", "objective_complete", objectiveCompleteHow) end
  vaMaybeAnnounceAllDone()
  -- Hot extraction: one counter-pack on objective complete (Arc A still gets
  -- this even when timed escalation is off). Full escalation also uses it.
  if (waves.enabled or doctrine.hotExtractOnly) and objectiveTeamID then
    local px, pz = teamUnitCentroid(playerTeamID)
    spawnWave(objectiveTeamID, waves.baseSize + 2, px, pz, "hot_extraction")
  end
end

-- ============================================================
-- MODE A: same-map seamless continue (WO-050..053)
-- Soft terminal skips Spring.GameOver; debrief pick reseeds in-place.
-- (sortieChapter / softContinueArmed declared with other file-scope locals)
-- ============================================================

local function currentMapId()
  return tostring((mission and mission.deploymentMapId) or (zoneMap and zoneMap.mapId) or "")
end

local function candidateIsSameMap(cand)
  if type(cand) ~= "table" then return false end
  local mapId = currentMapId()
  if mapId == "" then return false end
  return tostring(cand.mapId or "") == mapId
end

local function sameMapContinueAvailable()
  local rules = mission and mission.continueRules
  if rules and rules.sameMapContinue == false then return false end
  local cands = mission and mission.nextMissionCandidates
  if type(cands) ~= "table" then return false end
  for i = 1, #cands do
    if candidateIsSameMap(cands[i]) then return true end
  end
  return false
end

local function findEnemyCampTeam()
  if objectiveTeamID then return objectiveTeamID end
  for _, tid in ipairs(Spring.GetTeamList() or {}) do
    if tid ~= playerTeamID and tid ~= gaiaTeamID and not Spring.AreTeamsAllied(playerTeamID, tid) then
      return tid
    end
  end
  return nil
end

local function destroyEnemyInRect(rect, padding)
  if not rect then return 0 end
  padding = padding or 200
  local x1, z1 = rect[1] - padding, rect[2] - padding
  local x2, z2 = rect[3] + padding, rect[4] + padding
  local killed = 0
  local units = Spring.GetUnitsInRectangle(x1, z1, x2, z2) or {}
  for i = 1, #units do
    local uid = units[i]
    if Spring.ValidUnitID(uid) and not Spring.GetUnitIsDead(uid) then
      local team = Spring.GetUnitTeam(uid)
      if team and team ~= playerTeamID and team ~= gaiaTeamID
          and not Spring.AreTeamsAllied(playerTeamID, team) then
        -- Do not wipe named player heroes (they are always player team).
        Spring.DestroyUnit(uid, false, true)
        killed = killed + 1
        if objectiveTargets[uid] then
          objectiveTargets[uid] = nil
        end
      end
    end
  end
  return killed
end

-- Real same-map continue camps (not 1 fus + 2 LLT mockups). Eco sprawl, beefy
-- static teeth, mobile infantry. Wheelies stay a player toy -- no armfav/scout cars.
function continueCampBlueprint(kind)
  local works = {}   -- objective-tagged structures
  local guard = {}   -- non-objective teeth + infantry
  if kind == "eco_raid" or kind == "economy_disrupt" then
    works = {
      { def = "armfus", dx = 0, dz = 0, count = 1 },
      { def = "armsolar", dx = -180, dz = 40, count = 4, spacing = 70 },
      { def = "armsolar", dx = 160, dz = -60, count = 4, spacing = 70 },
      { def = "armsolar", dx = 40, dz = 180, count = 3, spacing = 70 },
      { def = "armwin", dx = -80, dz = -160, count = 4, spacing = 80 },
      { def = "armwin", dx = 200, dz = 120, count = 3, spacing = 80 },
      { def = "armmakr", dx = -120, dz = 120, count = 4, spacing = 75 },
      { def = "armmakr", dx = 130, dz = 40, count = 3, spacing = 75 },
      { def = "armadvsol", dx = 0, dz = -100, count = 2, spacing = 90 },
      { def = "armestor", dx = 90, dz = -40, count = 2, spacing = 80 },
    }
    guard = {
      { def = "armllt", dx = -200, dz = -140, count = 3, spacing = 120 },
      { def = "armllt", dx = 200, dz = -140, count = 3, spacing = 120 },
      { def = "armllt", dx = 0, dz = 220, count = 2, spacing = 120 },
      { def = "armbeamer", dx = -160, dz = 40, count = 1 },
      { def = "armbeamer", dx = 160, dz = 40, count = 1 },
      { def = "armdrag", dx = -240, dz = -180, count = 8, spacing = 36 },
      { def = "armdrag", dx = 240, dz = -180, count = 8, spacing = 36 },
      { def = "armrad", dx = 0, dz = -60, count = 1 },
      { def = "armrl", dx = -80, dz = 80, count = 1 },
      { def = "armpw", dx = -60, dz = 100, count = 5, spacing = 70 },
      { def = "armham", dx = 70, dz = 90, count = 3, spacing = 80 },
      { def = "armwar", dx = 0, dz = 140, count = 2, spacing = 90 },
    }
  elseif kind == "strike_relay" or kind == "destroy_key_structure" then
    works = {
      { def = "armtarg", dx = 0, dz = 0, count = 1 },
      { def = "armfus", dx = 120, dz = 40, count = 1 },
      { def = "armarad", dx = -40, dz = -80, count = 1 },
    }
    guard = {
      { def = "armllt", dx = -150, dz = -100, count = 3, spacing = 110 },
      { def = "armllt", dx = 150, dz = -100, count = 3, spacing = 110 },
      { def = "armbeamer", dx = 0, dz = 120, count = 2, spacing = 140 },
      { def = "armdrag", dx = -200, dz = -160, count = 10, spacing = 36 },
      { def = "armpw", dx = -40, dz = 60, count = 4, spacing = 70 },
      { def = "armwar", dx = 50, dz = 80, count = 2, spacing = 90 },
      { def = "armham", dx = 0, dz = -120, count = 2, spacing = 80 },
    }
  else
    -- seize_lane / gate_control: holdable camp with real teeth, not empty grass.
    works = {}
    guard = {
      { def = "armllt", dx = -140, dz = -100, count = 3, spacing = 110 },
      { def = "armllt", dx = 140, dz = -100, count = 3, spacing = 110 },
      { def = "armllt", dx = 0, dz = 160, count = 2, spacing = 110 },
      { def = "armbeamer", dx = -80, dz = 40, count = 1 },
      { def = "armbeamer", dx = 80, dz = 40, count = 1 },
      { def = "armdrag", dx = -200, dz = -150, count = 8, spacing = 36 },
      { def = "armdrag", dx = 200, dz = -150, count = 8, spacing = 36 },
      { def = "armrad", dx = 0, dz = -40, count = 1 },
      { def = "armpw", dx = -50, dz = 70, count = 6, spacing = 70 },
      { def = "armham", dx = 60, dz = 70, count = 3, spacing = 80 },
      { def = "armwar", dx = 0, dz = 120, count = 3, spacing = 90 },
      { def = "armwin", dx = 100, dz = 20, count = 2, spacing = 70 },
      { def = "armsolar", dx = -100, dz = 20, count = 2, spacing = 70 },
    }
  end
  return works, guard
end

local function isEcoStructureDef(ud)
  if not ud then return false end
  local n = string.lower(tostring(ud.name or ""))
  -- Armada/Cortex energy + converters + storage (raid credit).
  if n:find("solar", 1, true) or n:find("wind", 1, true) or n:find("makr", 1, true)
      or n:find("fus", 1, true) or n:find("estor", 1, true) or n:find("mstor", 1, true)
      or n:find("geo", 1, true) or n:find("tide", 1, true) then
    return true
  end
  return false
end

-- Living-shell gadget spawns static eco after playable setup. Claim any
-- shell eco marked objective_target (or inside primary zone) into the
-- campaign objective book so RAID_CREDIT / capture clear / promote paths work.
-- Capture kinds also tag static teeth so "clear pocket" is not empty grass.
local shellObjectivesClaimed = false
local function isShellTeethDef(ud, defID)
  if not ud then return false end
  local n = string.lower(tostring(ud.name or ""))
  -- Static defenses that form pocket teeth (LLT / beamer / HLT / RL / PB / guard).
  if n:find("llt", 1, true) or n:find("beamer", 1, true) or n:find("hlt", 1, true)
      or n:find("rl", 1, true) or n:find("pb", 1, true) or n:find("guard", 1, true)
      or n:find("ferrt", 1, true) or n:find("claw", 1, true) then
    return true
  end
  -- Generic: static with weapons, not eco.
  if defID and isStructure(defID) and canFight(defID) and not isEcoStructureDef(ud) then
    return true
  end
  return false
end

local function claimLivingShellObjectives()
  if shellObjectivesClaimed then return 0 end
  local shell = mission and mission.livingShell
  if not shell or shell.enabled == false then
    shellObjectivesClaimed = true
    return 0
  end
  local kind = objectiveKind()
  local captureMode = CAPTURE_KINDS[kind]
    or (mission.objective and mission.objective.captureMode == "clear_hold_shell")
    or (mission.objective and mission.objective.captureMode == true)
  -- Drop 4 raze strength: the whole pocket (teeth included) joins the book
  -- even on destruction kinds — "leave nothing standing" needs a full ledger.
  local razeMode = (mission.objective and tostring(mission.objective.strength or "") == "raze")
  local primaryZone = shell.primaryZoneId and tostring(shell.primaryZoneId)
    or (mission.objective and mission.objective.targetZoneId and tostring(mission.objective.targetZoneId))
    or nil
  local primaryPocket = shell.primaryPocketId and tostring(shell.primaryPocketId) or nil
  local primaryRect = primaryZone and zoneRectFor(primaryZone) or nil
  local forceId = "living_shell_primary"
  local tagged = 0
  local teamID = objectiveTeamID or findEnemyCampTeam()
  local units = Spring.GetAllUnits() or {}
  for i = 1, #units do
    local uid = units[i]
    if Spring.ValidUnitID(uid) and not Spring.GetUnitIsDead(uid) and not objectiveTargets[uid] then
      local isShell = Spring.GetUnitRulesParam(uid, "va_living_shell") == 1
        or Spring.GetUnitRulesParam(uid, "va_living_shell") == true
      if isShell then
        local team = Spring.GetUnitTeam(uid)
        local dID = Spring.GetUnitDefID(uid)
        local ud = dID and UnitDefs[dID]
        local eco = isEcoStructureDef(ud)
        local teeth = (captureMode or razeMode) and isShellTeethDef(ud, dID)
        local role = Spring.GetUnitRulesParam(uid, "va_force_role")
        local pocket = Spring.GetUnitRulesParam(uid, "va_shell_pocket")
        local zone = Spring.GetUnitRulesParam(uid, "va_shell_zone")
        local x, _, z = Spring.GetUnitPosition(uid)
        local inPrimary = false
        if primaryPocket and pocket and tostring(pocket) == primaryPocket then inPrimary = true end
        if primaryZone and zone and tostring(zone) == primaryZone then inPrimary = true end
        if primaryRect and x and z and x >= primaryRect[1] and z >= primaryRect[2]
            and x <= primaryRect[3] and z <= primaryRect[4] then
          inPrimary = true
        end
        if role == "objective_target" then inPrimary = true end
        local claimable = eco or teeth
        if claimable and inPrimary and team and team ~= playerTeamID and team ~= gaiaTeamID then
          objectiveTargets[uid] = forceId
          objectiveTargetCount = objectiveTargetCount + 1
          targetForceStructures[forceId] = (targetForceStructures[forceId] or 0) + 1
          tagged = tagged + 1
          if not teamID then teamID = team end
        end
      end
    end
  end
  if teamID then objectiveTeamID = teamID end
  -- Arm capture mode once shell pocket is booked.
  if captureMode and (tagged > 0 or shell.enabled) then
    capture.mode = true
    capture.phase = "clear"
    Spring.SetGameRulesParam("va_capture_mode", 1, { public = true })
    Spring.SetGameRulesParam("va_capture_phase", "clear", { public = true })
    Spring.Echo("VA_CAPTURE_ARMED mode=clear_hold_shell pocket="
      .. tostring(primaryPocket or primaryZone or "?")
      .. " targets=" .. tostring(tagged))
  end
  if tagged > 0 then
    Spring.SetGameRulesParam("va_objective_total", objectiveTargetCount, { public = true })
    Spring.SetGameRulesParam("va_objective_destroyed", objectiveTargetsDestroyed, { public = true })
    Spring.Echo("VA_SHELL_OBJECTIVES_CLAIMED count=" .. tostring(tagged)
      .. " total=" .. tostring(objectiveTargetCount)
      .. " team=" .. tostring(teamID)
      .. " capture=" .. tostring(capture.mode))
  end
  shellObjectivesClaimed = true
  return tagged
end

-- Promote pre-placed occupation eco in a zone into the active raid objective.
-- Returns how many structures were re-tagged (0 = zone empty / needs spawn).
local function promoteOccupationInZone(zoneId, kindHint)
  kindHint = kindHint or "eco_raid"
  local rect = zoneRectFor(zoneId)
  if not rect then return 0 end
  objectiveTargets = {}
  objectiveTargetCount = 0
  objectiveTargetsDestroyed = 0
  targetForceStructures = {}
  local forceId = "promote_" .. tostring(zoneId)
  local teamID = findEnemyCampTeam()
  local units = Spring.GetUnitsInRectangle(rect[1], rect[2], rect[3], rect[4]) or {}
  local tagged = 0
  for i = 1, #units do
    local uid = units[i]
    if Spring.ValidUnitID(uid) and not Spring.GetUnitIsDead(uid) then
      local team = Spring.GetUnitTeam(uid)
      if team and team ~= playerTeamID and team ~= gaiaTeamID
          and not Spring.AreTeamsAllied(playerTeamID, team) then
        local dID = Spring.GetUnitDefID(uid)
        local ud = dID and UnitDefs[dID]
        local eco = isEcoStructureDef(ud)
        local building = ud and (ud.isBuilding or (ud.speed or 1) == 0)
        -- Eco raids only credit energy economy. Other kinds can tag buildings.
        if eco or (building and kindHint ~= "eco_raid") then
          objectiveTargets[uid] = forceId
          objectiveTargetCount = objectiveTargetCount + 1
          targetForceStructures[forceId] = (targetForceStructures[forceId] or 0) + 1
          tagged = tagged + 1
          if teamID == nil then teamID = team end
        end
      end
    end
  end
  if teamID then objectiveTeamID = teamID end
  Spring.SetGameRulesParam("va_objective_total", objectiveTargetCount, { public = true })
  Spring.SetGameRulesParam("va_objective_destroyed", 0, { public = true })
  Spring.Echo("VA_PROMOTE_OCCUPATION zone=" .. tostring(zoneId)
    .. " tagged=" .. tostring(tagged) .. " team=" .. tostring(teamID)
    .. " kind=" .. tostring(kindHint))
  return tagged
end

local function spawnContinueCamp(zoneId, kind)
  local teamID = findEnemyCampTeam()
  if not teamID then
    Spring.Echo("VA_CONTINUE_NO_ENEMY_TEAM")
    return 0
  end
  objectiveTeamID = teamID
  local rect = zoneRectFor(zoneId)
  if not rect then
    Spring.Echo("VA_CONTINUE_NO_ZONE " .. tostring(zoneId))
    return 0
  end
  local cx = (rect[1] + rect[3]) * 0.5
  local cz = (rect[2] + rect[4]) * 0.5
  local works, guard = continueCampBlueprint(kind)
  local forceId = "continue_" .. tostring(kind) .. "_" .. tostring(zoneId)
  local garrisonForce = { id = forceId .. "_guard", role = "garrison", faction = "armada" }
  local objectiveForce = { id = forceId .. "_works", role = "objective_target", faction = "armada" }

  -- Reset objective target bookkeeping for the new camp only.
  objectiveTargets = {}
  objectiveTargetCount = 0
  objectiveTargetsDestroyed = 0
  targetForceStructures = {}
  local spawned = 0
  local claimed = {}

  local function placeList(list, force)
    for _, spec in ipairs(list) do
      local unitSpec = {
        unitDefName = spec.def,
        count = spec.count or 1,
        dx = spec.dx or 0,
        dz = spec.dz or 0,
        spacing = spec.spacing or 70,
      }
      spawned = spawned + spawnUnitSpec(unitSpec, teamID, cx, cz, 0, 0, claimed, force)
    end
  end

  if #works > 0 then
    placeList(works, objectiveForce)
  end
  placeList(guard, garrisonForce)

  if spawned <= 0 then
    Spring.Echo("VA_CONTINUE_CAMP_EMPTY zone=" .. tostring(zoneId) .. " kind=" .. tostring(kind))
  end
  Spring.SetGameRulesParam("va_objective_total", objectiveTargetCount, { public = true })
  Spring.SetGameRulesParam("va_objective_destroyed", 0, { public = true })
  Spring.Echo("VA_CONTINUE_CAMP zone=" .. tostring(zoneId) .. " kind=" .. tostring(kind)
    .. " units=" .. tostring(spawned) .. " targets=" .. tostring(objectiveTargetCount)
    .. " team=" .. tostring(teamID))
  return spawned
end

local function rebuildContinueCandidates(fromZoneId)
  local cands = {}
  if not zoneMap or type(zoneMap.zones) ~= "table" then
    mission.nextMissionCandidates = cands
    return
  end
  local sx = Game.mapSizeX or 1
  local sz = Game.mapSizeZ or 1
  local fromRect = zoneRectFor(fromZoneId)
  local fx, fz = 0.5 * sx, 0.5 * sz
  if fromRect then
    fx = (fromRect[1] + fromRect[3]) * 0.5
    fz = (fromRect[2] + fromRect[4]) * 0.5
  end
  local scored = {}
  for _, z in ipairs(zoneMap.zones) do
    local zid = z.zoneId
    if zid and zid ~= fromZoneId then
      local r = zoneRectFor(zid)
      if r then
        local cx = (r[1] + r[3]) * 0.5
        local cz = (r[2] + r[4]) * 0.5
        local dx, dz = cx - fx, cz - fz
        local dist = math.sqrt(dx * dx + dz * dz)
        scored[#scored + 1] = { id = zid, label = z.label or zid, dist = dist }
      end
    end
  end
  table.sort(scored, function(a, b) return a.dist < b.dist end)
  local kinds = { "seize_lane", "eco_raid", "strike_relay" }
  local mapId = currentMapId()
  for i = 1, math.min(3, #scored) do
    local s = scored[i]
    local kind = kinds[((i - 1) % #kinds) + 1]
    cands[#cands + 1] = {
      id = "cand_" .. i .. "_" .. s.id,
      title = kind .. " - " .. tostring(s.label),
      plain = "Next: " .. kind .. " on " .. tostring(s.label) .. " (adjacent). Deploy from current ground.",
      mapId = mapId,
      targetZoneId = s.id,
      fromZoneIds = { fromZoneId },
      objectiveArchetype = kind,
      patron = "nullmercs",
      against = "armada",
    }
  end
  -- Mode B: append strategic_link travel hops (session host Reload path).
  do
    local okL, links = pcall(VFS.Include, "luarules/gadgets/include/va_strategic_links.lua")
    if okL and type(links) == "table" then
      local have = {}
      for _, c in ipairs(cands) do
        if c.targetZoneId then have[tostring(c.targetZoneId)] = true end
      end
      for _, link in ipairs(links) do
        local a, b = tostring(link.fromZoneId or ""), tostring(link.toZoneId or "")
        local fromZ, toZ, toMap, fromMap, label
        if a == tostring(fromZoneId) then
          fromZ, toZ, toMap, fromMap = a, b, link.toMapId, link.fromMapId
          label = link.toLabel or b
        elseif b == tostring(fromZoneId) then
          fromZ, toZ, toMap, fromMap = b, a, link.fromMapId, link.toMapId
          label = a
        end
        if fromZ and toZ and tostring(toMap or "") ~= tostring(mapId) and not have[toZ] then
          have[toZ] = true
          cands[#cands + 1] = {
            id = "mode_b_" .. fromZ .. "_" .. toZ,
            title = "Travel — " .. tostring(label),
            plain = "Mode B map travel via strategic_link → " .. tostring(toMap)
              .. ". Session host Reload path.",
            mapId = tostring(toMap or ""),
            targetZoneId = toZ,
            fromZoneIds = { fromZ },
            objectiveArchetype = "seize_lane",
            patron = "nullmercs",
            against = "armada",
            sessionMode = "reload_travel",
            travelMode = "mode_b",
            edgeKind = "strategic_link",
            cost = link.cost or 2,
            notes = link.notes or "",
            fromMapId = tostring(fromMap or mapId),
          }
        end
      end
    end
  end
  mission.nextMissionCandidates = cands
end

local function publishContinueBriefing(cand, kind, targetZone, extractZone)
  local objLine = "Hit the refreshed Armada camp at " .. tostring(targetZone) .. ", then extract."
  if kind == "eco_raid" or kind == "economy_disrupt" then
    objLine = "Wreck the new energy works at " .. tostring(targetZone) .. " (~60%), then extract."
  elseif kind == "seize_lane" or kind == "gate_control" or kind == "hold_plateau" then
    objLine = "Clear the living-shell pocket at " .. tostring(targetZone)
      .. " (~60%), then hold under regrow pressure to claim the node. No free Tnb."
  elseif kind == "strike_relay" then
    objLine = "Destroy the relay at " .. tostring(targetZone) .. ", then extract."
  end
  local card = {
    situation = "Same map continue. Warband carries. New Armada camp materialised on " .. tostring(targetZone) .. ".",
    objective = objLine,
    howToWin = "No commanders. Phobos + rez + heroes. Blow or hold the new mark -- do not expand.",
    howItEnds = "Fresh soft clock armed for this chapter. When it hits zero the sortie ends.",
    threats = "Real pre-built camp: static guns, converters/solars when raiding, infantry screen.",
    allies = "Surviving Wheelies, Phobos, and rez bots stay in the field.",
    plainObjective = tostring(kind) .. ": " .. tostring(targetZone),
  }
  mission.missionCard = card
  Spring.SetGameRulesParam("va_continue_chapter", sortieChapter, { public = true })
  Spring.SetGameRulesParam("va_soft_continue", sameMapContinueAvailable() and 1 or 0, { public = true })
  Spring.Echo("VA_CONTINUE_CARD objective=" .. tostring(card.objective))
end

local function applyContinueCandidate(cand)
  if type(cand) ~= "table" then
    Spring.Echo("VA_CONTINUE_FAIL bad_candidate")
    return false
  end
  if not candidateIsSameMap(cand) then
    -- Mode B: strategic_link / cross-map hop. Session host Reload path builds + relaunches.
    -- Do not call Spring.Reload here — capability GO for presence, write/startscript still external.
    Spring.Echo("VA_CONTINUE_FAIL map_change_use_mode_b map=" .. tostring(cand.mapId)
      .. " target=" .. tostring(cand.targetZoneId or "")
      .. " sessionMode=reload_travel")
    Spring.Echo("VA_MODE_B_TRAVEL map=" .. tostring(cand.mapId)
      .. " target=" .. tostring(cand.targetZoneId or "")
      .. " edge=strategic_link")
    Spring.SetGameRulesParam("va_continue_mode", "map_change", { public = true })
    Spring.SetGameRulesParam("va_session_mode", "reload_travel", { public = true })
    Spring.SetGameRulesParam("va_mode_b", 1, { public = true })
    if SendToUnsynced then SendToUnsynced("VERDANCE_MISSION_EVENT", "map_change_required", tostring(cand.mapId or "")) end
    return false
  end
  if not terminal then
    Spring.Echo("VA_CONTINUE_FAIL not_terminal")
    return false
  end

  local kind = tostring(cand.objectiveArchetype or cand.kind or "seize_lane")
  local targetZone = tostring(cand.targetZoneId or "")
  if targetZone == "" then
    Spring.Echo("VA_CONTINUE_FAIL no_target")
    return false
  end

  -- Explicit extract / leave the field: end session soft-continue chain.
  if kind == "extract_leave" or cand.extractOnly == true then
    Spring.Echo("VA_CONTINUE_EXTRACT_LEAVE zone=" .. targetZone)
    softContinueArmed = false
    Spring.SetGameRulesParam("va_soft_continue", 0, { public = true })
    Spring.SetGameRulesParam("va_continue_mode", "extract_leave", { public = true })
    if SendToUnsynced then
      SendToUnsynced("VERDANCE_MISSION_EVENT", "extract_leave", targetZone)
    end
    -- Keep terminal debrief; player closes BAR / session host advances travel.
    return true
  end

  local prevTarget = mission.objective and mission.objective.targetZoneId
  local extractZone = prevTarget or mission.extractionZoneId or targetZone
  if type(cand.fromZoneIds) == "table" and cand.fromZoneIds[1] then
    extractZone = prevTarget or tostring(cand.fromZoneIds[1])
  end

  local preplaced = (cand.preplaced == true) or (cand.preplaced == 1)
  local rules = mission.continueRules or {}
  local promotePrefer = (rules.promoteOccupationOnContinue == true) or preplaced
  local clearNext = (rules.clearEnemyOnContinue == true) and (not promotePrefer)

  -- Clear residual at OLD objective only. Never wipe the next scar if it is
  -- already occupied world eco (that was the whole point of map occupation).
  local cleared = 0
  cleared = cleared + destroyEnemyInRect(targetZoneRect, 200)
  if clearNext then
    cleared = cleared + destroyEnemyInRect(zoneRectFor(targetZone), 200)
  end
  Spring.Echo("VA_CONTINUE_CLEAR killed=" .. tostring(cleared)
    .. " promotePrefer=" .. tostring(promotePrefer)
    .. " clearNext=" .. tostring(clearNext))

  -- Soft-reset objective automation state (heroes / player units stay).
  terminal = false
  softContinueArmed = false
  terminalReason = ""
  status = "active"
  objectiveComplete = false
  objectiveCompleteHow = ""
  objectiveBypassed = false
  -- Drop 4: re-arm the all-objectives latch for the next pocket. The
  -- secondary ledger itself persists — marks already wrecked stay credited,
  -- marks still standing stay killable on the same field.
  extraObj.announced = false
  Spring.SetGameRulesParam("va_all_objectives_done", 0, { public = true })
  zoneHoldFrames = 0
  extractionHoldFrames = 0
  extractionClean = true
  playerLeftExtraction = false
  stalemate.frames = 0
  stalemate.warned = false
  waves.spawned = 0
  holdFrames = 0
  mercWaveUsed = false
  waves.nextFrame = Spring.GetGameFrame() + 1800
  -- Reset capture claim machine for the next pocket on the same shell.
  capture.mode = false
  capture.phase = "idle"
  capture.pocketCleared = false
  capture.nodeClaimed = false
  capture.regrowWaves = 0
  capture.regrowNextFrame = 0
  shellObjectivesClaimed = false
  Spring.SetGameRulesParam("va_capture_mode", 0, { public = true })
  Spring.SetGameRulesParam("va_capture_phase", "idle", { public = true })
  Spring.SetGameRulesParam("va_pocket_cleared", 0, { public = true })
  Spring.SetGameRulesParam("va_node_claimed", 0, { public = true })
  Spring.SetGameRulesParam("va_regrow_waves", 0, { public = true })
  Spring.SetGameRulesParam("va_zone_hold", 0, { public = true })

  sortieChapter = sortieChapter + 1
  local mn = (tonumber(mission.missionNumber) or 0) + 1
  mission.missionNumber = mn
  mission.missionId = string.format("va_%03d", mn)
  mission.deploymentZoneId = extractZone
  mission.extractionZoneId = extractZone
  mission.objective = mission.objective or {}
  mission.objective.id = targetZone
  mission.objective.kind = kind
  mission.objective.targetZoneId = targetZone
  mission.objective.extractionZoneId = extractZone
  mission.objective.description = kind .. ": " .. targetZone
  -- Soft clock is absolute game frame. Must re-arm from NOW.
  local now = Spring.GetGameFrame() or 0
  local budget = 12000
  if kind == "eco_raid" or kind == "economy_disrupt" then budget = 13500 end
  if kind == "seize_lane" or kind == "gate_control" or kind == "hold_plateau" then budget = 11000 end
  mission.objective.requiredFrames = now + budget
  if CAPTURE_KINDS[kind] then
    mission.objective.captureMode = "clear_hold_shell"
    mission.objective.description = "Clear pocket + hold under regrow to claim " .. targetZone
  end
  mission.title = "Contract - " .. kind .. " - " .. targetZone
  mission.targetZoneId = targetZone

  targetZoneRect = zoneRectFor(targetZone)
  extractionZoneRect = zoneRectFor(extractZone)
  if extractionZoneRect then
    local ecx = (extractionZoneRect[1] + extractionZoneRect[3]) * 0.5
    local ecz = (extractionZoneRect[2] + extractionZoneRect[4]) * 0.5
    local hw = math.max(300, (extractionZoneRect[3] - extractionZoneRect[1]) * 0.275)
    local hh = math.max(300, (extractionZoneRect[4] - extractionZoneRect[2]) * 0.275)
    extractionZoneRect = { ecx - hw, ecz - hh, ecx + hw, ecz + hh }
    Spring.SetGameRulesParam("va_extract_x", math.floor(ecx), { public = true })
    Spring.SetGameRulesParam("va_extract_z", math.floor(ecz), { public = true })
  end

  -- Prefer promoting live occupation; only spawn mock camps if the zone is empty.
  local campUnits = 0
  if promotePrefer then
    campUnits = promoteOccupationInZone(targetZone, kind)
  end
  if campUnits <= 0 then
    Spring.Echo("VA_CONTINUE_SPAWN_FALLBACK zone empty -- building camp")
    campUnits = spawnContinueCamp(targetZone, kind)
  end
  rebuildContinueCandidates(targetZone)
  publishContinueBriefing(cand, kind, targetZone, extractZone)
  Spring.Echo("VA_CONTINUE_CLOCK now=" .. tostring(now)
    .. " requiredFrames=" .. tostring(mission.objective.requiredFrames)
    .. " budget=" .. tostring(budget)
    .. " campUnits=" .. tostring(campUnits)
    .. " preplaced=" .. tostring(preplaced))
  -- Publish objective marker (inline; avoid upvalue on later local).
  do
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
    end
    if n > 0 or targetZoneRect then
      Spring.SetGameRulesParam("va_objective_x", math.floor(ox), { public = true })
      Spring.SetGameRulesParam("va_objective_z", math.floor(oz), { public = true })
    end
  end

  Spring.SetGameRulesParam("va_terminal", 0, { public = true })
  Spring.SetGameRulesParam("va_result_code", 0, { public = true })
  Spring.SetGameRulesParam("va_status", "active", { public = true })
  Spring.SetGameRulesParam("va_terminal_reason", "", { public = true })
  Spring.SetGameRulesParam("va_objective_complete", 0, { public = true })
  Spring.SetGameRulesParam("va_zone_hold", 0, { public = true })
  Spring.SetGameRulesParam("va_extraction_hold", 0, { public = true })
  Spring.SetGameRulesParam("va_mission_number", mn, { public = true })
  Spring.SetGameRulesParam("va_hold_frames", 0, { public = true })
  Spring.SetGameRulesParam("va_required_frames", mission.objective.requiredFrames or 19800, { public = true })
  Spring.SetGameRulesParam("va_waves_spawned", 0, { public = true })
  Spring.SetGameRulesParam("va_continue_mode", "same_map", { public = true })
  Spring.SetGameRulesParam("va_soft_continue", sameMapContinueAvailable() and 1 or 0, { public = true })

  Spring.Echo("VA_CONTINUE chapter=" .. tostring(sortieChapter)
    .. " mission=" .. tostring(mission.missionId)
    .. " kind=" .. kind
    .. " target=" .. targetZone
    .. " extract=" .. tostring(extractZone))
  if SendToUnsynced then
    SendToUnsynced("VERDANCE_MISSION_EVENT", "continue_start", kind .. "|" .. targetZone)
  end
  return true
end

local function tryContinueByIndex(idx)
  idx = tonumber(idx)
  local cands = mission and mission.nextMissionCandidates
  if not idx or type(cands) ~= "table" or not cands[idx] then
    Spring.Echo("VA_CONTINUE_FAIL bad_index=" .. tostring(idx))
    return false
  end
  return applyContinueCandidate(cands[idx])
end

function setTerminal(newStatus, reason)
  if terminal then return end
  terminal = true
  terminalReason = tostring(reason or "")
  status = newStatus
  debugAutoProgress = 0
  finalizeHeroStates()
  publishHeroRules()
  Spring.SetGameRulesParam("va_terminal", 1, { public = true })
  Spring.SetGameRulesParam("va_result_code", (newStatus == "victory" and 1) or (newStatus == "defeat" and 2) or 3, { public = true })
  Spring.SetGameRulesParam("va_status", newStatus, { public = true })
  Spring.SetGameRulesParam("va_terminal_reason", terminalReason, { public = true })
  Spring.SetGameRulesParam("va_extraction_clean", extractionClean and 1 or 0, { public = true })
  Spring.Echo("VA_TERMINAL status=" .. status .. " reason=" .. terminalReason)
  logResult()
  -- Level 2: emit the Hermitian battlefield observable at terminal so the
  -- campaign engine can eigen-decompose it and collapse it onto the graph.
  logAndBroadcastTranslation()
  if SendToUnsynced then SendToUnsynced("VERDANCE_MISSION_EVENT", status, terminalReason) end
  local profilingRun = headless.autoStart or balance.exportFrame or (#fib.milestones > 0)
  if profilingRun then
    if headless.quit then
      headless.quitFrame = Spring.GetGameFrame() + 60
    end
    return
  end

  -- WO-050: soft terminal for victory/partial when same-map continue is legal.
  -- Skip Spring.GameOver so the match stays alive for Mode A reseed.
  local softOk = (newStatus == "victory" or newStatus == "partial") and sameMapContinueAvailable()
  softContinueArmed = softOk
  Spring.SetGameRulesParam("va_soft_continue", softOk and 1 or 0, { public = true })
  if softOk then
    Spring.Echo("VA_SOFT_TERMINAL same_map_continue=1 chapter=" .. tostring(sortieChapter))
    return
  end

  local winners = {}
  if newStatus == "defeat" then
    for _, at in ipairs(Spring.GetAllyTeamList()) do
      if at ~= playerAllyTeamID and at ~= gaiaAllyTeamID then winners[#winners + 1] = at end
    end
  else
    winners = { playerAllyTeamID }
  end
  Spring.GameOver(winners)
end

local function pocketClearProgress()
  if objectiveTargetCount <= 0 then return 1.0, 0, 0 end
  local need = math.max(1, math.ceil(objectiveTargetCount * CLEAR_FRACTION))
  return objectiveTargetsDestroyed / objectiveTargetCount, objectiveTargetsDestroyed, need
end

local function fireRegrowPressure(frame)
  -- During hold phase, occupation tries to regrow / retake the cleared node.
  if not capture.mode or capture.phase ~= "hold" then return end
  if capture.regrowWaves >= capture.regrowMax then return end
  if frame < (capture.regrowNextFrame or 0) then return end
  if not objectiveTeamID then return end
  local tx, tz
  if targetZoneRect then
    tx = (targetZoneRect[1] + targetZoneRect[3]) * 0.5
    tz = (targetZoneRect[2] + targetZoneRect[4]) * 0.5
  else
    tx, tz = teamUnitCentroid(playerTeamID)
  end
  if not tx then return end
  local size = capture.regrowBaseSize + math.min(2, capture.regrowWaves)
  local n = spawnWave(objectiveTeamID, size, tx, tz, "regrow_pressure")
  capture.regrowWaves = capture.regrowWaves + 1
  capture.regrowNextFrame = frame + capture.regrowInterval
  Spring.SetGameRulesParam("va_regrow_waves", capture.regrowWaves, { public = true })
  Spring.Echo("VA_REGROW_PRESSURE wave=" .. tostring(capture.regrowWaves)
    .. " spawned=" .. tostring(n) .. " phase=hold")
  if SendToUnsynced and capture.regrowWaves == 1 then
    SendToUnsynced("VERDANCE_BEAT", "bark", "Ketha",
      "They're trying to regrow the node — hold the claim.", 6)
  end
end

local function checkPresenceObjective(frame)
  if objectiveComplete then return end
  local kind = objectiveKind()
  -- Presence kinds hold the target zone; destruction kinds with zero spawned
  -- targets fall back to the same zone-hold rule so missions stay winnable.
  local presenceMode = PRESENCE_KINDS[kind] or CAPTURE_KINDS[kind]
    or (objectiveTargetCount == 0 and targetZoneRect ~= nil)
  if not presenceMode or not targetZoneRect then return end

  -- CAPTURE PATH: clear living-shell pocket first, then hold under regrow pressure.
  -- Not empty-grass claim. Claim does not free-mint Tnb (reclaim only).
  if capture.mode then
    local frac, destroyed, need = pocketClearProgress()
    Spring.SetGameRulesParam("va_pocket_clear_frac", math.floor(frac * 1000 + 0.5) / 1000, { public = true })
    Spring.SetGameRulesParam("va_capture_phase", capture.phase, { public = true })

    if capture.phase == "clear" or capture.phase == "idle" then
      capture.phase = "clear"
      -- Pocket is clear once enough objective shell units are wrecked,
      -- or (fallback) no enemy combat remains and we have zero book targets.
      local cleared = false
      if objectiveTargetCount > 0 then
        cleared = destroyed >= need
      else
        local playerPresent, enemyCombat = scanZoneRect(targetZoneRect)
        cleared = playerPresent and not enemyCombat
      end
      if cleared then
        capture.pocketCleared = true
        capture.phase = "hold"
        zoneHoldFrames = 0
        capture.regrowNextFrame = frame + math.floor(capture.regrowInterval * 0.5)
        Spring.SetGameRulesParam("va_pocket_cleared", 1, { public = true })
        Spring.SetGameRulesParam("va_capture_phase", "hold", { public = true })
        Spring.Echo("VA_POCKET_CLEARED destroyed=" .. tostring(destroyed)
          .. "/" .. tostring(objectiveTargetCount)
          .. " need=" .. tostring(need)
          .. " → hold under regrow pressure")
        if SendToUnsynced then
          SendToUnsynced("VERDANCE_BEAT", "bark", "Ketha",
            "Pocket clear. Hold the node — they will try to regrow it.", 7)
        end
      end
      return
    end

    if capture.phase == "hold" then
      fireRegrowPressure(frame)
      local playerPresent, enemyCombat = scanZoneRect(targetZoneRect)
      if playerPresent and not enemyCombat then
        zoneHoldFrames = zoneHoldFrames + CHECK_PERIOD
      else
        zoneHoldFrames = 0
      end
      Spring.SetGameRulesParam("va_zone_hold", zoneHoldFrames, { public = true })
      local required = tonumber(mission.objective and mission.objective.requiredHoldFrames) or PRESENCE_HOLD_DEFAULT
      if zoneHoldFrames >= required then
        capture.nodeClaimed = true
        capture.phase = "claimed"
        Spring.SetGameRulesParam("va_node_claimed", 1, { public = true })
        Spring.SetGameRulesParam("va_capture_phase", "claimed", { public = true })
        Spring.Echo("VA_NODE_CLAIMED zone=" .. tostring(mission.objective and mission.objective.targetZoneId or "")
          .. " freeTnbMint=false")
        onObjectiveComplete("node_claimed")
      end
      return
    end
    return
  end

  -- Legacy presence (no living shell): stand on zone with no enemy combat.
  local playerPresent, enemyCombat = scanZoneRect(targetZoneRect)
  if playerPresent and not enemyCombat then
    zoneHoldFrames = zoneHoldFrames + CHECK_PERIOD
  else
    zoneHoldFrames = 0
  end
  Spring.SetGameRulesParam("va_zone_hold", zoneHoldFrames, { public = true })
  local required = tonumber(mission.objective and mission.objective.requiredHoldFrames) or PRESENCE_HOLD_DEFAULT
  if zoneHoldFrames >= required then
    onObjectiveComplete("zone_held")
  end
end

local function checkExtraction(frame)
  local kind = objectiveKind()
  local allowBypass = (kind == "hive_clear_or_bypass") and playerLeftExtraction
  -- Drop 4: victory needs the PRIMARY plus every required secondary (and the
  -- purge, when armed) — extraction stays cold until the whole board signs off.
  local allDone = vaAllObjectivesDone()
  if not (allDone or allowBypass) then
    -- Track leaving the deployment/extraction zone; that arms the bypass path.
    if extractionZoneRect and not playerLeftExtraction then
      local playerPresent = scanZoneRect(extractionZoneRect)
      if not playerPresent then playerLeftExtraction = true end
    end
    return
  end
  if not extractionZoneRect then
    if allDone then setTerminal("victory", "objective_complete_no_extraction_zone") end
    return
  end
  local playerPresent, enemyCombat = scanZoneRect(extractionZoneRect)
  if playerPresent then
    extractionHoldFrames = extractionHoldFrames + CHECK_PERIOD
    if enemyCombat then extractionClean = false end
  else
    playerLeftExtraction = true
    extractionHoldFrames = 0
  end
  Spring.SetGameRulesParam("va_extraction_hold", extractionHoldFrames, { public = true })
  if extractionHoldFrames >= EXTRACTION_HOLD_FRAMES then
    if allDone then
      setTerminal("victory", "extracted")
    else
      objectiveBypassed = true
      setTerminal("partial", "extracted_bypass")
    end
  end
end

local function checkPlayerWipe(frame)
  if frame < WIPE_GRACE_FRAMES then return end
  local count = Spring.GetTeamUnitCount(playerTeamID) or 0
  if count <= 0 then
    setTerminal("defeat", "player_wiped")
  end
end

-- No-fail stalemate guard: a player left with neither mobile combat power nor
-- any way to build it (no builders, no factories) can neither win nor lose -
-- warn once, then end the mission as force-spent instead of hanging forever.
local function checkStalemate(frame)
  if frame < WIPE_GRACE_FRAMES then return end
  local units = Spring.GetTeamUnits(playerTeamID) or {}
  local capable = false
  for i = 1, #units do
    local dID = Spring.GetUnitDefID(units[i])
    local ud = dID and UnitDefs[dID]
    if ud then
      if ud.isFactory or isBuilder(dID) then capable = true; break end
      if canFight(dID) and not isStructure(dID) then capable = true; break end
    end
  end
  if capable then
    stalemate.frames = 0
    return
  end
  stalemate.frames = stalemate.frames + CHECK_PERIOD
  if not stalemate.warned and stalemate.frames >= CHECK_PERIOD then
    stalemate.warned = true
    Spring.Echo("VA_STALEMATE_WARNING no mobile combat units and no production")
    if SendToUnsynced then SendToUnsynced("VERDANCE_MISSION_EVENT", "stalemate_warning", "force_spent") end
  end
  if stalemate.frames >= stalemate.limit then
    setTerminal("defeat", "force_spent")
  end
end

-- Soft clock: requiredFrames is a real mission end, not just a HUD countdown.
-- Without this, time hits 0 and the player sits in PHASE FIGHT forever.
local function checkSoftClock(frame)
  if terminal or status ~= "active" then return end
  local req = mission and mission.objective and tonumber(mission.objective.requiredFrames)
  if not req or req <= 0 then return end
  local left = req - frame
  -- Publish phase for HUD (APPROACH / FIGHT / EXTRACT / TIMEOUT).
  local phase = "FIGHT"
  if objectiveComplete then
    phase = "EXTRACT"
  elseif frame < 90 * 30 then
    phase = "APPROACH"
  end
  if left <= 0 then phase = "TIMEOUT" end
  Spring.SetGameRulesParam("va_phase", phase, { public = true })
  Spring.SetGameRulesParam("va_clock_left", math.max(0, left), { public = true })
  if left > 0 then return end
  if objectiveComplete then
    setTerminal("partial", "soft_clock_no_extract")
    return
  end
  local dmg = 0
  if objectiveTargetCount > 0 then
    dmg = objectiveTargetsDestroyed / objectiveTargetCount
  end
  if dmg >= (RAID_CREDIT_FRACTION * 0.5) or zoneHoldFrames >= (PRESENCE_HOLD_DEFAULT * 0.5) then
    setTerminal("partial", "soft_clock_timeout")
  else
    setTerminal("defeat", "soft_clock_timeout")
  end
end

local function isCommanderUnitDef(ud)
  if not ud then return false end
  local cp = ud.customParams or {}
  -- Decoy commanders (armdecom/cordecom/legdecom) look like coms but are occupation
  -- swarm farmers — never treat as real commander (sweep / loss / soup).
  if cp.isdecoycommander or cp.decoyfor then return false end
  if cp.iscommander or cp.isCommander or cp.commander then return true end
  local n = string.lower(tostring(ud.name or ud.humanName or ""))
  -- BAR chassis names: armcom*, corcom*, legcom* (avoid "combat"/"comms" false positives).
  if n:find("combat", 1, true) then return false end
  if n:find("decom", 1, true) or n:find("decoy", 1, true) or n == "dummycom" then
    return false
  end
  if n:match("com$") or n:match("^armcom") or n:match("^corcom") or n:match("^legcom") then
    return true
  end
  return false
end

-- WO-043c handlers: physical split (include/va_tenebrium_handlers.lua).
-- Methods attach onto tenebLoot; api getters keep playerTeamID/mission live.
do
  local okAttach, attachOrErr = pcall(VFS.Include, "luarules/gadgets/include/va_tenebrium_handlers.lua")
  if not okAttach then
    Spring.Echo("VA_TENEBRIUM_HANDLERS_INCLUDE_FAIL " .. tostring(attachOrErr))
  else
    local attach = attachOrErr
    local api = {
      jnum = jnum,
      jstr = jstr,
      teamFaction = teamFaction,
      SendToUnsynced = SendToUnsynced,
      playerTeamID = function() return playerTeamID end,
      playerAllyTeamID = function() return playerAllyTeamID end,
      mission = function() return mission end,
    }
    local okRun, errRun = pcall(attach, tenebLoot, api)
    if not okRun then
      Spring.Echo("VA_TENEBRIUM_HANDLERS_ATTACH_FAIL " .. tostring(errRun))
    else
      Spring.Echo("VA_TENEBRIUM_HANDLERS_ATTACHED")
    end
  end
end


-- Verification harness: scripted objective kills, hero kills, rez orders,
-- wreck destruction, and LZ teleports, all armed via va_test_* modoptions.
-- Lives outside GameFrame so its state costs GameFrame a single upvalue.
local function runTestHarness(frame)
  -- Hydrology probe: sample ground and units, move the waterline, sample again.
  -- Terraforming under a live battle is the one mechanic here whose engine-side
  -- consequences are not documented anywhere, so the probe measures them.
  if testHooks.hydroFrame and not testHooks.hydroDone and frame >= testHooks.hydroFrame then
    testHooks.hydroDone = true
    vaEchoHydroProbe("before", frame)
    vaBeginWaterline(testHooks.hydroTo or 0.8, 12)
  end
  if testHooks.hydroProbe and frame >= testHooks.hydroProbe then
    testHooks.hydroProbe = nil
    vaEchoHydroProbe("after", frame)
  end

  if testHooks.killObjectiveFrame and not testHooks.killObjectiveDone and frame >= testHooks.killObjectiveFrame then
    testHooks.killObjectiveDone = true
    local ids = {}
    for unitID in pairs(objectiveTargets) do ids[#ids + 1] = unitID end
    for _, unitID in ipairs(ids) do Spring.DestroyUnit(unitID, false, false) end
    Spring.Echo("VA_TEST_KILLOBJECTIVE destroyed=" .. tostring(#ids) .. " frame=" .. tostring(frame))
  end
  -- Drop 4: wreck every secondary mark so probes can watch the required-left
  -- gate open (VA_SECONDARY_COMPLETE ... VA_ALL_OBJECTIVES_DONE).
  if testHooks.killSecondaryFrame and not testHooks.killSecondaryDone and frame >= testHooks.killSecondaryFrame then
    testHooks.killSecondaryDone = true
    local ids = {}
    for unitID in pairs(extraObj.targets) do ids[#ids + 1] = unitID end
    for _, unitID in ipairs(ids) do Spring.DestroyUnit(unitID, false, false) end
    Spring.Echo("VA_TEST_KILLSECONDARY destroyed=" .. tostring(#ids) .. " frame=" .. tostring(frame))
  end
  if testHooks.killHeroIdx <= #testHooks.killHeroFrames and frame >= testHooks.killHeroFrames[testHooks.killHeroIdx] then
    testHooks.killHeroIdx = testHooks.killHeroIdx + 1
    local ids = {}
    for id, rec in pairs(heroes) do
      if rec.state == "alive" and rec.unitID and Spring.ValidUnitID(rec.unitID) then ids[#ids + 1] = id end
    end
    table.sort(ids)
    if ids[1] then
      Spring.Echo("VA_TEST_KILLHERO id=" .. ids[1] .. " frame=" .. tostring(frame))
      Spring.DestroyUnit(heroes[ids[1]].unitID, false, false)
    end
  end
  if testHooks.rezWreckFrame and not testHooks.rezWreckDone and frame >= testHooks.rezWreckFrame then
    testHooks.rezWreckDone = true
    local featureID
    for fid in pairs(heroByFeatureID) do featureID = fid end
    if featureID and CMD and CMD.RESURRECT then
      local units = Spring.GetTeamUnits(playerTeamID) or {}
      for i = 1, #units do
        local dID = Spring.GetUnitDefID(units[i])
        local ud = dID and UnitDefs[dID]
        if ud and ud.canResurrect then
          Spring.GiveOrderToUnit(units[i], CMD.RESURRECT, { featureID + Game.maxUnits }, {})
          Spring.Echo("VA_TEST_REZWRECK feature=" .. tostring(featureID) .. " rezbot=" .. tostring(units[i]))
          break
        end
      end
    end
  end
  if testHooks.destroyWreckFrame and not testHooks.destroyWreckDone and frame >= testHooks.destroyWreckFrame then
    testHooks.destroyWreckDone = true
    for fid in pairs(heroByFeatureID) do
      Spring.Echo("VA_TEST_DESTROYWRECK feature=" .. tostring(fid))
      Spring.DestroyFeature(fid)
    end
  end
  if testHooks.techGateFrame and not testHooks.techGateDone and frame >= testHooks.techGateFrame then
    testHooks.techGateDone = true
    -- Tech-gate probe (Drop 3 Wave 1): spawn a con bot at the deploy beacon,
    -- echo the gate's verdict for a def matrix (policy check), then issue a
    -- real build order so the engine's AllowUnitCreation path produces a
    -- genuine VA_TECH_GATE_DENY when the gate is armed.
    local dx = tonumber(Spring.GetGameRulesParam("va_deploy_x")) or 512
    local dz = tonumber(Spring.GetGameRulesParam("va_deploy_z")) or 512
    local dy = Spring.GetGroundHeight(dx, dz) or 0
    local builder = Spring.CreateUnit("legck", dx, dy, dz, 0, playerTeamID)
    for _, defName in ipairs({ "legalab", "leglab", "legsolar", "legcen", "legshot" }) do
      local ud = UnitDefNames[defName]
      if ud then
        local ok = vaTechGateAllows(ud.id, builder, playerTeamID)
        Spring.Echo("VA_TEST_TECHGATE def=" .. defName .. " allowed=" .. tostring(ok and true or false))
      end
    end
    if builder then
      local advLab = UnitDefNames["legalab"]
      if advLab then Spring.GiveOrderToUnit(builder, -advLab.id, { dx + 140, dy, dz + 140 }, {}) end
      local solar = UnitDefNames["legsolar"]
      if solar then Spring.GiveOrderToUnit(builder, -solar.id, { dx - 140, dy, dz - 140 }, { "shift" }) end
    end
    Spring.Echo("VA_TEST_TECHGATE_DONE builder=" .. tostring(builder) .. " frame=" .. tostring(frame))
  end
  if testHooks.teleportExtractFrame and not testHooks.teleportExtractDone and frame >= testHooks.teleportExtractFrame then
    testHooks.teleportExtractDone = true
    if extractionZoneRect and Spring.SetUnitPosition then
      local ex = (extractionZoneRect[1] + extractionZoneRect[3]) * 0.5
      local ez = (extractionZoneRect[2] + extractionZoneRect[4]) * 0.5
      local moved = 0
      local units = Spring.GetTeamUnits(playerTeamID) or {}
      for i = 1, #units do
        local dID = Spring.GetUnitDefID(units[i])
        if dID and not isStructure(dID) then
          local ox = ex + ((moved % 5) - 2) * 40
          local oz = ez + math.floor(moved / 5) * 40
          pcall(Spring.SetUnitPosition, units[i], ox, oz)
          moved = moved + 1
        end
      end
      Spring.Echo("VA_TEST_TELEPORT_EXTRACT moved=" .. tostring(moved) .. " frame=" .. tostring(frame))
    end
  end
end

function gadget:Initialize()
  mission = readMission()
  zoneMap = readZoneMap()
  local modOptions = Spring.GetModOptions() or {}
  -- Dev telemetry arm: mission seed, modoption, or generated flag file.
  do
    local flag = nil
    local okF, dataF = pcall(VFS.Include, "singleplayer/verdance_ashes/generated/dev_telemetry_flag.lua")
    if okF and type(dataF) == "table" then flag = dataF end
    local fromMission = mission and (mission.devTelemetry == true or (mission.dev and mission.dev.telemetry == true))
    local fromOpt = truthy(modOptions.va_dev_telemetry)
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
  headless.fastWin = not (modOptions.va_headless_fastwin == false or modOptions.va_headless_fastwin == 0 or modOptions.va_headless_fastwin == "0")
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
  doctrine.hotExtractOnly = (mission.escalation and mission.escalation.hotExtractOnly == true)
      or (tostring(arc.escalation or "") == "off")
  -- Drop 2 act structure: seed techPolicy caps what the player may build.
  do
    local tp = mission.techPolicy
    local actInfo = mission.act
    doctrine.actNumber = tonumber((type(actInfo) == "table" and actInfo.act)
      or (type(tp) == "table" and tp.act)) or 0
    doctrine.actMode = tostring((type(tp) == "table" and tp.mode)
      or (type(actInfo) == "table" and actInfo.name) or "")
    if type(tp) == "table" then
      doctrine.techMaxLevel = tonumber(tp.buildTech) or 3
      doctrine.techBuildStructures = (tp.buildStructures ~= false)
      doctrine.techGateEnabled = (doctrine.techMaxLevel < 3)
        or (not doctrine.techBuildStructures)
    end
    local actLabel = (type(actInfo) == "table" and actInfo.label) and tostring(actInfo.label) or ""
    Spring.SetGameRulesParam("va_act", doctrine.actNumber, { public = true })
    Spring.SetGameRulesParam("va_act_label", actLabel, { public = true })
    Spring.SetGameRulesParam("va_tech_cap", doctrine.techGateEnabled and doctrine.techMaxLevel or 3, { public = true })
    Spring.SetGameRulesParam("va_tech_structures", doctrine.techBuildStructures and 1 or 0, { public = true })
    if doctrine.techGateEnabled then
      Spring.Echo("VA_TECH_GATE act=" .. tostring(doctrine.actNumber)
        .. " mode=" .. doctrine.actMode
        .. " maxTech=" .. tostring(doctrine.techMaxLevel)
        .. " structures=" .. tostring(doctrine.techBuildStructures))
    end
  end
  playerTeamID = tonumber(mission.balance and mission.balance.playerTeamID) or 0
  gaiaTeamID = Spring.GetGaiaTeamID()
  for _, tid in ipairs(Spring.GetTeamList()) do
    local _, _, _, _, _, at = Spring.GetTeamInfo(tid, false)
    teamAllyTeam[tid] = tonumber(at or -1) or -1
  end
  playerAllyTeamID = teamAllyTeam[playerTeamID] or 0
  gaiaAllyTeamID = teamAllyTeam[gaiaTeamID] or -1
  debugAutoProgressAllowed = headless.fastWin or truthy(modOptions.va_debug_autoprogress)
  testHooks.killObjectiveFrame = tonumber(modOptions.va_test_killobjective_frame or "")
  testHooks.killSecondaryFrame = tonumber(modOptions.va_test_secondary_frame or "")
  -- Accepts comma OR colon separators (colon survives ExtraModOptions strings).
  for s in tostring(modOptions.va_test_killhero_frames or ""):gmatch("[^,:]+") do
    local n = tonumber(s:match("^%s*(.-)%s*$"))
    if n and n > 0 then testHooks.killHeroFrames[#testHooks.killHeroFrames + 1] = math.floor(n) end
  end
  table.sort(testHooks.killHeroFrames)
  testHooks.rezWreckFrame = tonumber(modOptions.va_test_rezwreck_frame or "")
  testHooks.destroyWreckFrame = tonumber(modOptions.va_test_destroywreck_frame or "")
  testHooks.teleportExtractFrame = tonumber(modOptions.va_test_teleport_extract_frame or "")
  testHooks.techGateFrame = tonumber(modOptions.va_test_techgate_frame or "")
  testHooks.hydroFrame = tonumber(modOptions.va_test_hydro_frame or "")
  testHooks.hydroTo = tonumber(modOptions.va_test_hydro_to or "")
  -- Headless spins forever building the unit-icon texture atlas at frame 30.
  -- The shell-bake and cartography gadgets both learned this the hard way and
  -- carry the same guard; every va_* probe runs through THIS gadget, so it
  -- belongs here too. Only under an explicitly headless/profiling run -- a real
  -- session needs its icons.
  if (headless.autoStart or balance.exportFrame or #fib.milestones > 0
      or testHooks.hydroFrame) and Spring.SetConfigInt then
    Spring.SetConfigInt("UnitIconsAsUI", 0)
    Spring.SetConfigInt("UnitIconDist", 99999)
    Spring.SetConfigInt("LuaUI", 0)
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
  extractionZoneRect = zoneRectFor(mission.extractionZoneId or obj.extractionZoneId)
  -- Tighten the extraction footprint: "return to extraction" should mean
  -- reaching a marked LZ, not standing anywhere in a quarter-map rectangle.
  if extractionZoneRect then
    local ecx = (extractionZoneRect[1] + extractionZoneRect[3]) * 0.5
    local ecz = (extractionZoneRect[2] + extractionZoneRect[4]) * 0.5
    local hw = math.max(300, (extractionZoneRect[3] - extractionZoneRect[1]) * 0.275)
    local hh = math.max(300, (extractionZoneRect[4] - extractionZoneRect[2]) * 0.275)
    extractionZoneRect = { ecx - hw, ecz - hh, ecx + hw, ecz + hh }
    Spring.SetGameRulesParam("va_extract_x", math.floor(ecx), { public = true })
    Spring.SetGameRulesParam("va_extract_z", math.floor(ecz), { public = true })
  end
  -- Landing (enfil) beacon — always marked, distinct from extract.
  do
    local depRect = zoneRectFor(mission.deploymentZoneId)
    if depRect then
      local dcx = (depRect[1] + depRect[3]) * 0.5
      local dcz = (depRect[2] + depRect[4]) * 0.5
      Spring.SetGameRulesParam("va_deploy_x", math.floor(dcx), { public = true })
      Spring.SetGameRulesParam("va_deploy_z", math.floor(dcz), { public = true })
    end
  end

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
  Spring.SetGameRulesParam("va_terminal", 0, { public = true })
  Spring.SetGameRulesParam("va_arc_id", tostring(arc.id or ""), { public = true })
  Spring.SetGameRulesParam("va_player_commanders", doctrine.playerComsAllowed, { public = true })
  Spring.SetGameRulesParam("va_soft_continue", sameMapContinueAvailable() and 1 or 0, { public = true })
  Spring.SetGameRulesParam("va_continue_chapter", sortieChapter, { public = true })
  Spring.SetGameRulesParam("va_continue_mode", "none", { public = true })
  Spring.Echo("VA_BRIDGE_LOADED mission=" .. tostring(mission.missionId)
    .. " arc=" .. tostring(arc.id or "?")
    .. " playerComs=" .. tostring(doctrine.playerComsAllowed)
    .. " esc=" .. tostring(escMode ~= "" and escMode or (waves.enabled and "on" or "off"))
    .. " sameMapContinue=" .. tostring(sameMapContinueAvailable())
    .. " schema=" .. tostring(mission.schemaVersion or "unknown"))
  if headless.autoStart then Spring.Echo("VA_HEADLESS_AUTOSTART enabled") end
  if balance.exportFrame then Spring.Echo("VA_BALANCE_AUTORUN exportFrame=" .. tostring(balance.exportFrame) .. " quit=" .. tostring(balance.quitAfterExport)) end
  if #fib.milestones > 0 then
    Spring.Echo("VA_FIB_PROFILER milestones=" .. tostring(#fib.milestones) .. " first=" .. tostring(fib.milestones[1]) .. " last=" .. tostring(fib.milestones[#fib.milestones]) .. " quitAfterLast=" .. tostring(fib.quitAfterLast))
  end
  if zoneMap then Spring.Echo("VA_ZONES_LOADED mapId=" .. tostring(zoneMap.mapId or "unknown") .. " count=" .. tostring(zoneCount())) end
end

-- Pillar C: turn the commander's earned level/perks into tangible start-of-
-- mission bonuses. Perks the compiler cannot bake into the seed (resources,
-- commander experience/toughness) are applied live here once units exist.
local function applyCommanderPerks()
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
local function publishObjectiveMarker()
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

-- Strike / Ashwalker doctrine: BAR always drops a free faction commander.
-- Sweep it immediately so the player boots into heroes + kit, not a stock Legion com.
local function sweepPlayerCommanders(why)
  if not (doctrine.strikeTeam or doctrine.playerComsAllowed <= 0) then
    return 0
  end
  local removed = 0
  local units = Spring.GetTeamUnits(playerTeamID) or {}
  for i = 1, #units do
    local uID = units[i]
    local dID = Spring.GetUnitDefID(uID)
    local ud = dID and UnitDefs[dID]
    if isCommanderUnitDef(ud) then
      playerCommanders[uID] = nil
      Spring.DestroyUnit(uID, false, true)
      removed = removed + 1
    end
  end
  if removed > 0 then
    doctrine.sawPlayerCom = false
    Spring.Echo("VA_SWEEP_PLAYER_COMMANDERS count=" .. tostring(removed) .. " why=" .. tostring(why or "sweep"))
  end
  return removed
end

function gadget:GameStart()
  -- Bank + crisis flags before any unit stamps/charges.
  if tenebLoot.initFromMission then tenebLoot.initFromMission() end
  spawnPlayableSetup()
  -- Kill free engine commander before the player ever clicks (frame-0 feel).
  sweepPlayerCommanders("gamestart")
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
end

function gadget:GameFrame(frame)
  if vaWaterTarget and frame % VA_WATER_TICK == 0 then
    vaStepWaterline()
  end

  if headless.autoStart and not headless.started and frame >= 1 then
    headless.started = true
    startMission()
    if headless.fastWin then
      finishHeadlessResult("victory")
    end
  end

  if balance.exportFrame and not balance.exported and frame >= balance.exportFrame then
    balance.exported = true
    logTelemetry()
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

  -- Verification harness (objective kill, hero kill/rez/wreck, LZ teleport):
  -- one function call so GameFrame stays under Lua 5.1's 60-upvalue cap.
  runTestHarness(frame)

  -- WO-043c: shard spawn + wreck-gone loss timeout.
  if frame % 5 == 0 then
    tenebLoot.tickPending(frame)
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

  -- Arc A / Ashwalker strike: re-sweep free commanders a few times (engine can
  -- re-place late). Heroes + kit stay; stock Legion/Armada/Cortex coms go.
  if (doctrine.strikeTeam or doctrine.playerComsAllowed <= 0) and frame <= 90 then
    if frame == 1 or frame == 2 or frame == 8 or frame == 30 or frame == 90 then
      sweepPlayerCommanders("frame_" .. tostring(frame))
      if frame >= 90 then doctrine.commanderSwept = true end
    end
  elseif not doctrine.commanderSwept and frame >= 2 then
    doctrine.commanderSwept = true
  end
  if doctrine.sweepEnemy and not doctrine.enemySwept and frame >= 3 then
    doctrine.enemySwept = true
    local removed = 0
    for _, tid in ipairs(Spring.GetTeamList() or {}) do
      if tid ~= playerTeamID and tid ~= gaiaTeamID then
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
    if removed > 0 then Spring.Echo("VA_SWEEP_ENEMY_COMMANDERS count=" .. tostring(removed)) end
  end

  -- Living shell spawns ~frame 8; claim objective eco once shortly after.
  if not shellObjectivesClaimed and frame >= 20 and frame <= 90 and frame % 10 == 0 then
    claimLivingShellObjectives()
  end

  -- Objective automation checks (playable sessions)
  if status == "active" and not terminal and frame % CHECK_PERIOD == 0 then
    checkPresenceObjective(frame)
    vaCheckPurge(frame)
    checkExtraction(frame)
    checkPlayerWipe(frame)
    checkHeroWreckTimeouts(frame)
    checkStalemate(frame)
    checkSoftClock(frame)
    if beatsEnabled then checkBeats(frame) end
  end

  -- Pillar B / raid pressure: enemy reinforcements. For a raid the Armada QRF
  -- answers as the works are wrecked (damage thresholds) so the pressure reads
  -- as cause-and-effect; other missions use the steady timer.
  if waves.enabled and status == "active" and not terminal and not objectiveComplete and objectiveTeamID then
    if objectiveKind() == "eco_raid" then
      if waves.spawned < waves.max then
        local dmg = (objectiveTargetCount > 0) and (objectiveTargetsDestroyed / objectiveTargetCount) or 0
        local threshold = raidWaveThresholds[waves.spawned + 1] or 1.1
        if dmg >= threshold then
          local px, pz = teamUnitCentroid(playerTeamID)
          spawnWave(objectiveTeamID, waves.baseSize, px, pz, "armada_qrf")
          waves.spawned = waves.spawned + 1
          waves.nextFrame = frame + waves.interval
          Spring.SetGameRulesParam("va_waves_spawned", waves.spawned, { public = true })
        end
      end
    elseif frame >= waves.nextFrame and waves.spawned < waves.max then
      local px, pz = teamUnitCentroid(playerTeamID)
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
      setTerminal("victory", "debug_autoprogress")
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
  -- Spoke: newly minted player Wheelies inherit banked scout XP.
  if unitTeam == playerTeamID and wheelieMentor.heroId then
    local ud = UnitDefs[unitDefID]
    local defName = ud and ud.name
    if isWheelieDef(defName) and not heroByUnitID[unitID] then
      stampWheelieXp(unitID)
    end
  end
  -- WO-043c: charge / stamp Tenebrium for build-power units.
  tenebLoot.onUnitCreated(unitID, unitDefID, unitTeam, builderID)
end

function gadget:AllowUnitCreation(unitDefID, builderID, builderTeam, x, y, z, facing)
  if not vaTechGateAllows(unitDefID, builderID, builderTeam) then return false end
  return tenebLoot.allowCreate(unitDefID, builderTeam)
end

function gadget:FeatureCreated(featureID, allyTeamID, sourceID)
  heroOnFeatureCreated(featureID, allyTeamID, sourceID)
  tenebLoot.onFeatureCreated(featureID, allyTeamID, sourceID)
end

function gadget:FeatureDestroyed(featureID, allyTeamID)
  heroOnFeatureDestroyed(featureID)
  tenebLoot.onFeatureDestroyed(featureID)
end

-- Reclaim of builder/decoy wrecks pulls durable Tenebrium into the bank.
function gadget:AllowFeatureBuildStep(builderID, builderTeam, featureID, featureDefID, step)
  tenebLoot.tryLoot(builderID, builderTeam, featureID, step)
  return true
end

function gadget:UnitGiven(unitID, unitDefID, newTeam, oldTeam)
  if newTeam == playerTeamID then
    local ud = UnitDefs[unitDefID]
    if isCommanderUnitDef(ud) then
      playerCommanders[unitID] = true
      doctrine.sawPlayerCom = true
    end
  elseif playerCommanders[unitID] then
    playerCommanders[unitID] = nil
  end
end

function gadget:UnitDestroyed(unitID, unitDefID, unitTeam)
  -- Spoke harvests XP from dead wheelies *before* hero cleanup clears maps.
  if unitTeam == playerTeamID and wheelieMentor.heroId then
    local ud = UnitDefs[unitDefID]
    local defName = ud and ud.name
    if isWheelieDef(defName) then
      harvestWheelieXp(unitID)
    end
  end
  heroOnUnitDestroyed(unitID)
  tenebLoot.onDead(unitID, unitDefID, unitTeam)
  if recordShellScar then recordShellScar(unitID, unitDefID) end
  local forceId = objectiveTargets[unitID]
  if forceId then
    objectiveTargets[unitID] = nil
    objectiveTargetsDestroyed = objectiveTargetsDestroyed + 1
    targetForceStructures[forceId] = math.max(0, (targetForceStructures[forceId] or 1) - 1)
    Spring.SetGameRulesParam("va_objective_destroyed", objectiveTargetsDestroyed, { public = true })
    Spring.Echo("VA_OBJECTIVE_TARGET_DOWN force=" .. forceId .. " destroyed=" .. tostring(objectiveTargetsDestroyed) .. "/" .. tostring(objectiveTargetCount))
    if not objectiveComplete and status == "active" and not terminal then
      local kind = objectiveKind()
      if CHOICE_KINDS[kind] then
        if (targetForceStructures[forceId] or 0) <= 0 then
          chosenTargetForceId = forceId
          onObjectiveComplete("target_destroyed")
        end
      elseif kind == "eco_raid" then
        -- A raid credits once ENOUGH of the works are wrecked, not all of them.
        local need = math.max(1, math.ceil(objectiveTargetCount * RAID_CREDIT_FRACTION))
        if objectiveTargetsDestroyed >= need then
          onObjectiveComplete("works_crippled")
        end
      elseif CAPTURE_KINDS[kind] or capture.mode then
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
  -- Drop 4: secondary marks tick their own ledger (never the primary pool).
  local secId = extraObj.targets[unitID]
  if secId then
    extraObj.targets[unitID] = nil
    local g = extraObj.groups[secId]
    if g and not g.done then
      g.destroyed = g.destroyed + 1
      if g.destroyed >= g.total then
        g.done = true
        if g.required then extraObj.requiredLeft = math.max(0, extraObj.requiredLeft - 1) end
        local doneCount = 0
        for i, sid in ipairs(extraObj.order) do
          if extraObj.groups[sid].done then doneCount = doneCount + 1 end
          if sid == secId then
            Spring.SetGameRulesParam("va_sec" .. i .. "_done", 1, { public = true })
          end
        end
        Spring.SetGameRulesParam("va_secondary_done", doneCount, { public = true })
        Spring.SetGameRulesParam("va_secondary_required_left", extraObj.requiredLeft, { public = true })
        Spring.Echo("VA_SECONDARY_COMPLETE id=" .. secId
          .. " required=" .. tostring(g.required == true)
          .. " left=" .. tostring(extraObj.requiredLeft))
        if SendToUnsynced then SendToUnsynced("VERDANCE_MISSION_EVENT", "secondary_complete", secId) end
        vaMaybeAnnounceAllDone()
      end
    end
  end
  if playerCommanders[unitID] then
    playerCommanders[unitID] = nil
    if doctrine.sawPlayerCom and next(playerCommanders) == nil and status == "active" and not terminal then
      setTerminal("defeat", "commander_lost")
    end
  end
end

function gadget:GameOver(winningAllyTeams)
  if terminal then return end
  -- Safety net: the game ended without our own terminal path (resign, quit,
  -- external gameover). Derive a status and guarantee a result marker.
  local won = false
  for _, at in ipairs(winningAllyTeams or {}) do
    if at == playerAllyTeamID then won = true end
  end
  terminal = true
  terminalReason = "gameover_external"
  if won then
    status = objectiveComplete and "victory" or "partial"
  else
    status = "defeat"
  end
  debugAutoProgress = 0
  finalizeHeroStates()
  publishHeroRules()
  Spring.SetGameRulesParam("va_terminal", 1, { public = true })
  Spring.SetGameRulesParam("va_status", status, { public = true })
  Spring.Echo("VA_TERMINAL status=" .. status .. " reason=" .. terminalReason)
  logResult()
end

local function runVerdanceCommand(cmd)
  if type(cmd) ~= "string" then return false end
  -- WO-051: vacontinue:1 / vacontinue 1 — Mode A same-map reseed from debrief pick.
  local contIdx = cmd:match("^vacontinue[:%s]+(%d+)") or cmd:match("^vacontinue(%d+)")
  if contIdx then
    tryContinueByIndex(contIdx)
    return true
  end
  if cmd == "vastart" then startMission()
  elseif cmd == "vastatus" then echoStatus()
  elseif cmd == "vaprogress" then progress(300)
  elseif cmd == "vaprogressbig" then progress(99999)
  elseif cmd == "vawin" then setTerminal("victory", "debug_command")
  elseif cmd == "vafail" then setTerminal("defeat", "debug_command")
  elseif cmd == "vapartial" then setTerminal("partial", "debug_command")
  elseif cmd == "vatest_killobjective" then
    if Spring.IsCheatingEnabled() then
      local ids = {}
      for unitID in pairs(objectiveTargets) do ids[#ids + 1] = unitID end
      for _, unitID in ipairs(ids) do Spring.DestroyUnit(unitID, false, false) end
      Spring.Echo("VA_TEST_KILLOBJECTIVE destroyed=" .. tostring(#ids))
    else
      Spring.Echo("VA_TEST_DENIED cheats required for vatest_killobjective")
    end
  elseif cmd == "vaspawn" then spawnCompanions()
  elseif cmd == "vaspawnlayout" then spawnPlayableSetup()
  elseif cmd == "vazones" then echoZones()
  elseif cmd == "vatelemetry" or cmd == "vabalance" then logTelemetry()
  elseif cmd == "vatranslation" then logAndBroadcastTranslation()
  elseif cmd == "varesult" or cmd == "vaexport" then logResult()
  elseif cmd == "vaheadless" then startMission(); finishHeadlessResult("victory")
  elseif cmd == "vacallmercs" then
    -- Pillar B / C payoff: at high standing the Null Mercs answer one call.
    if mercsAllied and mercTeamID and not mercWaveUsed then
      local px, pz = teamUnitCentroid(playerTeamID)
      local ex, ez = teamUnitCentroid(objectiveTeamID)
      local n = spawnWave(mercTeamID, waves.baseSize + 2, ex or px, ez or pz, "merc_call")
      if n > 0 then
        mercWaveUsed = true
        Spring.SetGameRulesParam("va_mercs_available", 0, { public = true })
        Spring.SetGameRulesParam("va_mercs_called", 1, { public = true })
        Spring.Echo("VA_MERCS_CALLED count=" .. tostring(n))
      end
    else
      Spring.Echo("VA_MERCS_UNAVAILABLE allied=" .. tostring(mercsAllied) .. " used=" .. tostring(mercWaveUsed))
    end
  elseif cmd == "vareset" then status = "inactive"; holdFrames = 0; debugAutoProgress = 0; echoStatus()
  else return false end
  return true
end

function gadget:TextCommand(command)
  if type(command) ~= "string" then return false end
  -- Allow "vacontinue 2" with full rest of string.
  if command:match("^vacontinue") then
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
  if not runVerdanceCommand(cmd) then
    Spring.Echo("VA_UNKNOWN_CMD " .. tostring(cmd))
  end
end











