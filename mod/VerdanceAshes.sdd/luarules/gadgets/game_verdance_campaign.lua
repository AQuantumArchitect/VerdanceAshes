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
    pcall(Spring.SendCommands, "pause 1")
    Spring.Echo("VA_PAUSE " .. tostring(why or "request"))
  end

  local function gameIsPaused()
    if Spring.IsGamePaused then
      return Spring.IsGamePaused() == true
    end
    local _, _, paused = Spring.GetGameSpeed()
    return paused == true
  end

  -- Hold pause until it sticks. One-shot GameStart pause races the engine and
  -- often loses (sim runs; nests shoot). After pause is observed, stop asserting
  -- so the player can unpause with the normal pause key.
  local holdStartPause = true
  local sawStartPaused = false
  local pauseAssertEchoed = false

  function gadget:Initialize()
    -- Tracked-playtest channel. The synced half already writes every one of these
    -- packets to the infolog; this hands the same strings to LuaUI so a widget can
    -- write the session record itself. That is what lets a played campaign record
    -- itself from inside the client, with no external harvester in the loop.
    -- kind is one of: telemetry | zoneflow | devsample | result.
    gadgetHandler:AddSyncAction("VERDANCE_TRACK", function(_, kind, jsonStr)
      if Script.LuaUI and Script.LuaUI.VerdanceTrack then
        Script.LuaUI.VerdanceTrack(kind, jsonStr)
      end
    end)
    gadgetHandler:AddSyncAction("VERDANCE_MISSION_EVENT", function(_, eventStatus, reason)
      -- The end of the sortie is owned by game_verdance_exfil.lua (manifest, pause, quit).
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
    holdStartPause = true
    sawStartPaused = false
    requestPause("sortie_start")
  end

  function gadget:Update()
    if isHeadless() or not holdStartPause then return end
    if gameIsPaused() then
      if not sawStartPaused then
        sawStartPaused = true
        Spring.Echo("VA_PAUSE_HELD sortie_start_ok")
      end
      -- Pause stuck: release the hold so the player can begin with pause key.
      holdStartPause = false
      return
    end
    -- Re-assert every update until pause sticks (engine often ignores one-shot).
    pcall(Spring.SendCommands, "pause 1")
    if not pauseAssertEchoed then
      pauseAssertEchoed = true
      Spring.Echo("VA_PAUSE sortie_start_hold")
    end
  end

  function gadget:Shutdown()
    gadgetHandler:RemoveSyncAction("VERDANCE_TRACK")
    gadgetHandler:RemoveSyncAction("VERDANCE_MISSION_EVENT")
    gadgetHandler:RemoveSyncAction("VERDANCE_HERO_EVENT")
    gadgetHandler:RemoveSyncAction("VERDANCE_BEAT")
  end
  return
end

-- ---------------------------------------------------------------------------
-- Why so many things in this file are globals instead of `local`.
--
-- Lua 5.1 (the engine's Lua) allows at most 200 `local` names in one function,
-- and a chunk's top level IS one function. This file is near that cap. When it
-- is exceeded the gadget fails to load and BAR's Initial Spawn drops a stock
-- commander instead of the company. So: hot-path state and small helpers that
-- need upvalue speed stay `local`; everything else is a gadget-environment
-- global, either a bare `function name()` or a field on one of the packed
-- tables (VA_KINDS, VA_CREW_SELECT, VA_FIELD_RECRUIT, VAQ, VA_LOGISTICS,
-- VA_TRANSLATION). A gadget's globals live in that gadget's own environment,
-- so they do not leak into other gadgets; GG.* is the only cross-gadget
-- surface. The second cap that matters is 60 upvalues per function, which is
-- why gadget:GameFrame calls out to helpers instead of touching state directly.
-- ---------------------------------------------------------------------------

local mission
local zoneMap
local status = "inactive"
local holdFrames = 0
local debugAutoProgress = 0
local headless = { autoStart = false, fastWin = false, quit = false, started = false, quitFrame = nil }
local playableSetupSpawned = false
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
-- Field recruits: wild heroes seeded on this map; wreck+rez joins the company.
VA_FIELD_RECRUIT = {
  spawned = {},   -- heroId -> true
  recruited = {}, -- ordered list of heroIds rezzed this sortie
  pendingDeath = {}, -- unitIDs to quiet-kill next frame (engine leaves rez corpse)
  fabByUnit = {}, -- unitID -> heroId (factory seed awaiting wreck / capture)
  fabByFeature = {}, -- featureID -> heroId (Legion bay wreck awaiting rez)
}
local balance = { exportFrame = nil, exported = false, quitAfterExport = false }
local fib = { milestones = {}, idx = 1, quitAfterLast = false }
-- Quantum kernel lives in an include module to keep this Lua 5.1 main chunk
-- below its 200-local limit. Global table by design; all public names are VAQ.*.
VAQ = { module = nil, kernel = nil, lastTransitionFrame = 0, arrivals = {} }

-- Objective automation (gadget-env globals — Lua 5.1 main-chunk local budget).
CHECK_PERIOD = 30                 -- frames between objective checks
PRESENCE_HOLD_DEFAULT = 900       -- 30s hold for seize/gate objectives
WIPE_GRACE_FRAMES = 900           -- no wipe-defeat before 30s
-- Dev telemetry: one table so GameFrame stays under Lua 5.1's 60-upvalue cap.
-- Armed by singleplayer/.../generated/dev_telemetry_flag.lua or mission.devTelemetry.
local devTel = {
  enabled = false,
  period = 150,          -- ~5s @ 30fps
  lastSample = -999999,
  cmds = { move = 0, fight = 0, attack = 0, patrol = 0, build = 0, reclaim = 0, guard = 0, other = 0 },
  cmdTotal = 0,
}

-- Objective kinds → how the gadget resolves them (one table, gadget-env).
-- Every kind Python emits (verdance_story_engine_v1 / quest_generator_v1
-- ROLE_ARCHETYPE) must land in exactly one mode; vaObjectiveMode() below echoes
-- the choice at setup as VA_OBJECTIVE_KIND so the infolog shows it.
--   capture  clear the living-shell pocket (CLEAR_FRACTION of eco+teeth), then
--            hold the node under regrow pressure → node claimed. Without a
--            living shell the same kinds fall back to a plain presence hold.
--            siege = take the citadel; multipressure = hold the swamp under
--            pressure from all sides (the regrow waves are the pressure).
--   survive  stand in the target zone for requiredHoldFrames. No targets are
--            booked for it even when a shell is loaded (survive ≠ raze).
--   fortify  raise defensive value in the target zone (fortifyDefensiveValue).
--   choice   several target forces; wrecking any one of them completes.
--   targets  destruction kinds (strike_relay, destroy_key_structure,
--            economy_disrupt, hive_clear_or_bypass, sortie, anything unlisted):
--            every booked target must die. eco_raid credits at
--            RAID_CREDIT_FRACTION instead (see UnitDestroyed).
VA_KINDS = {
  capture = { seize_lane = true, gate_control = true, hold_plateau = true, siege = true, multipressure = true },
  survive = { survive_wilds = true },
  fortify = { fortify_zone = true, home_founding = true },
  choice = { choose_target_then_extract = true },
}

local playerTeamID = 0
local playerAllyTeamID = 0
local gaiaTeamID = -1
local teamAllyTeam = {}                 -- teamID -> allyTeamID
local teamFaction = {}                  -- teamID -> world faction (nullmercs/armada/cortex/...)
local objectiveTargets = {}             -- unitID -> forceId (objective_target structures)
local objectiveTargetCount = 0
local objectiveTargetsDestroyed = 0
local targetForceStructures = {}        -- forceId -> live structure count
local objectiveComplete = false
local objectiveBypassed = false
-- Sortie-linked field recruit wreck destroyed → fail contract, open partial extract.
-- Idempotent latch (WO-008: no hard defeat; RTB instead).
local rescueContractFailed = false
local rescueContractFailReason = ""
local rescueContractFailHero = ""
local chosenTargetForceId = nil
local zoneHoldFrames = 0
-- Frames at which the objective facts latched (0 = never). Exported in the result.
local objectiveCompleteFrame = 0
local nodeClaimedFrame = 0
-- The pad geometry only (pass five: there is no extract loop, timer or hold —
-- the sortie ends when the player confirms the manifest in game_verdance_exfil.lua).
local extractLoop = { padRadius = 560 }
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
  actNumber = 0, -- story label only; Tnb and build power are the only fabrication gate
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
-- Named hero roster (Fire Emblem doctrine): heroes leave wrecks; a rez bot can
-- bring them back mid-mission. A destroyed wreck is permadeath - and a mission
-- defeat when the hero is mission-critical (the player character, Ketha).
local heroes = {}             -- heroId -> record (state machine below)
local heroByUnitID = {}       -- live unitID -> heroId
local heroPendingWreck = {}   -- dead unitID -> heroId (awaiting corpse FeatureCreated)
local heroByFeatureID = {}    -- wreck featureID -> heroId
local wreckConsumedByRez = {} -- featureID -> true when a resurrection consumed it
local HERO_WRECK_TIMEOUT = 90 -- frames a corpse may lag the death (BAR corpse-link window)

-- Procedural hero tags (Runner = speed perk, not a career rank).
local HeroTags = nil
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
-- Resurrection often destroys the wreck feature before UnitCreated runs; hold
-- permadeath for a short grace so the rezzed unit can reclaim the hero identity.
local HERO_REZ_GRACE = 60     -- 2s at 30fps
local HERO_REZ_MATCH_DIST = 450 -- elmos; rez spawns on the wreck
-- In-mission beats: data-driven WC3-style triggers authored into the seed.
local beats = {}              -- compiled pending beats (all fire once)
local beatsEnabled = false
local beatFiredSet = {}       -- beatId -> true (afterBeat prerequisites)
-- Drop 4: marks registry = single SoT for vault / structure / hero_recover.
-- Purge + announce latch stay beside it (victory policy, not mark records).
local MarksLib = nil
do
  local ok, mod = pcall(VFS.Include, "luarules/gadgets/include/va_marks_registry.lua")
  if not ok or type(mod) ~= "table" then
    ok, mod = pcall(VFS.Include, "LuaRules/gadgets/include/va_marks_registry.lua")
  end
  if ok and type(mod) == "table" then
    MarksLib = mod
    Spring.Echo("VA_MARKS_REGISTRY_LOADED")
  else
    Spring.Echo("VA_MARKS_REGISTRY_MISSING")
    MarksLib = {
      KIND = { vault = "vault", structure = "structure", hero_recover = "hero_recover" },
      new = function()
        return { groups = {}, order = {}, targets = {}, requiredLeft = 0 }
      end,
      upsert = function() end,
      complete = function() end,
      bindTarget = function() end,
      hasTarget = function() return false end,
      onTargetDestroyed = function() return nil, nil, false end,
      eachTarget = function(_, fn) end,
      enrichFromMission = function() end,
      upsertHeroRecover = function() return nil end,
      completeHeroRecover = function() end,
      publish = function() end,
      doneCount = function() return 0 end,
      requiredLeft = function() return 0 end,
      count = function() return 0 end,
      resultsJson = function() return "[]" end,
      markRequired = function() end,
      targetOf = function() return nil end,
    }
  end
end
local marks = MarksLib.new()

local function marksCommit(event, sid)
  MarksLib.publish(marks)
  if event and SendToUnsynced then
    SendToUnsynced("VERDANCE_MISSION_EVENT", event, sid or "")
  end
end

local extraObj = {
  purge = false,
  purgeDone = false,
  purgeTeams = {},     -- teamID -> true
  announced = false,   -- all-objectives-done broadcast latch
}
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
local lastResultJson = nil     -- the one result this sortie wrote (dev telemetry re-sends it)
-- Chapter index carried in the result key (always 1: there is no same-map continue).
local sortieChapter = 1
local targetZoneRect = nil              -- {x1, z1, x2, z2} in elmos
local extractionZoneRect = nil
local debugAutoProgressAllowed = false

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
      '"rank":' .. jstr(HeroTags.normalizeRank(rec.rank or "Green")),
      '"recruited":' .. tostring(rec.recruited == true),
      '"fieldRecruit":' .. tostring(rec.wasFieldRecruit == true or rec.recruited == true),
    }, ',') .. '}'
  end
  return '{' .. table.concat(parts, ',') .. '}'
end

function recruitedHeroIdsJson()
  local parts = {}
  for _, id in ipairs(VA_FIELD_RECRUIT.recruited or {}) do
    parts[#parts + 1] = jstr(id)
  end
  -- Also pick up any hero flagged recruited without list push (safety).
  for id, rec in pairs(heroes) do
    if rec.recruited then
      local seen = false
      for _, x in ipairs(VA_FIELD_RECRUIT.recruited or {}) do
        if x == id then seen = true; break end
      end
      if not seen then parts[#parts + 1] = jstr(id) end
    end
  end
  return '[' .. table.concat(parts, ',') .. ']'
end

-- DCO-01 / WO-006: named character outcomes for the story engine characters{} registry.
-- Maps gadget hero FSM results onto namedOutcomes: dead | recovered | wounded.
function namedOutcomesJson()
  local parts = {}
  for id, rec in pairs(heroes) do
    -- Wild field recruits who never joined are not company casualties.
    if rec.wasFieldRecruit and not rec.recruited then
      -- skip
    else
    local raw = rec.result or (rec.everDown and "wounded" or "survived")
    if raw == "survived" and rec.everDown then raw = "recovered" end
    local outcome = nil
    local cause = rec.diedHow or ""
    if raw == "dead" then
      outcome = "dead"
      if cause == "" then cause = "wreck_destroyed" end
    elseif raw == "recovered" then
      outcome = "recovered"
      cause = "reclaimed_friendly"
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
    end -- wasFieldRecruit skip else
  end
  return '[' .. table.concat(parts, ',') .. ']'
end

local function publishHeroRules()
  Spring.SetGameRulesParam("va_heroes_json", heroStatesJson(), { public = true })
end

local function readMission()
  local ok, data = pcall(VFS.Include, "singleplayer/verdance_ashes/generated/va_current.lua")
  if ok and type(data) == "table" then return data end
  Spring.Echo("VA_SEED_MISSING generated/va_current.lua did not load; the kernel did not build this sortie")
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

-- The primary objective id, listed once it completed by any path (destroyed,
-- zone held, node claimed). Python reads this as "the objective was done".
function destroyedObjectiveIdsJson()
  local oid = mission.objective and mission.objective.id
  if oid and objectiveComplete then
    return '[' .. jstr(oid) .. ']'
  end
  return '[]'
end

-- One row for the primary objective: how far it got and how it completed.
-- status is the mechanic that finished it, not a judgement of the sortie.
function objectiveResultsJson()
  local obj = mission.objective or {}
  if not obj.id then return '[]' end
  local objStatus = "incomplete"
  if objectiveComplete then
    if objectiveCompleteHow == "node_claimed" then
      objStatus = "claimed"
    elseif objectiveCompleteHow == "zone_held" or objectiveCompleteHow == "zone_fortified" then
      objStatus = "complete"
    else
      objStatus = "destroyed"
    end
  end
  local damage = 0
  if objectiveTargetCount > 0 then
    damage = objectiveTargetsDestroyed / objectiveTargetCount
  elseif objectiveComplete then
    damage = 1
  end
  return '[{' .. table.concat({
    '"objectiveId":' .. jstr(obj.id),
    '"kind":' .. jstr(obj.kind or ""),
    '"mode":' .. jstr(vaObjectiveMode(obj.kind)),
    '"status":' .. jstr(objStatus),
    '"how":' .. jstr(objectiveCompleteHow or ""),
    '"targetsTotal":' .. jnum(objectiveTargetCount),
    '"targetsDestroyed":' .. jnum(objectiveTargetsDestroyed),
    '"damage":' .. jnum(damage, 3),
  }, ',') .. '}]'
end

-- Drop 4: secondary-objective ledger for the campaign engine (bonus marks pay
-- merc standing; required marks are implied by any victory that got home).
function secondaryResultsJson()
  return MarksLib.resultsJson(marks, jstr, jnum)
end

-- Fusion vaults + their beamer teeth that are still standing at terminal.
-- Campaign state keeps these so the prize is here when you come back, and
-- offscreen aggression can schedule a defend sortie instead of silent wipe.
function survivingInstallsJson()
  local byPocket = {}
  local units = Spring.GetAllUnits() or {}
  for i = 1, #units do
    local uid = units[i]
    if Spring.ValidUnitID(uid) and not Spring.GetUnitIsDead(uid) then
      local hv = Spring.GetUnitRulesParam(uid, "va_high_value")
      local held = Spring.GetUnitRulesParam(uid, "va_held_install")
      local role = tostring(Spring.GetUnitRulesParam(uid, "va_force_role") or "")
      local pocket = tostring(Spring.GetUnitRulesParam(uid, "va_shell_pocket") or "")
      local zone = tostring(Spring.GetUnitRulesParam(uid, "va_shell_zone") or "")
      local isShell = Spring.GetUnitRulesParam(uid, "va_living_shell") == 1
        or Spring.GetUnitRulesParam(uid, "va_living_shell") == true
      local interesting = (hv == 1) or (held == 1) or role == "held_install"
        or role == "objective_secondary"
      if isShell and interesting and pocket ~= "" then
        local bag = byPocket[pocket]
        if not bag then
          bag = {
            pocketId = pocket,
            zoneId = zone,
            highValue = (hv == 1 or role == "objective_secondary"),
            held = (held == 1 or role == "held_install"),
            ownerTeam = Spring.GetUnitTeam(uid),
            units = {},
          }
          byPocket[pocket] = bag
        end
        local dID = Spring.GetUnitDefID(uid)
        local ud = dID and UnitDefs[dID]
        local x, _, z = Spring.GetUnitPosition(uid)
        local hp, maxHp = Spring.GetUnitHealth(uid)
        bag.units[#bag.units + 1] = {
          def = ud and ud.name or "",
          x = x or 0,
          z = z or 0,
          hpFrac = (maxHp and maxHp > 0 and hp) and (hp / maxHp) or 1,
          highValue = (hv == 1),
        }
        if hv == 1 then bag.highValue = true end
        if zone ~= "" then bag.zoneId = zone end
      end
    end
  end
  -- Also count beamer/LLT teeth in the same HV pocket even if not marked secondary.
  for i = 1, #units do
    local uid = units[i]
    if Spring.ValidUnitID(uid) and not Spring.GetUnitIsDead(uid) then
      local pocket = tostring(Spring.GetUnitRulesParam(uid, "va_shell_pocket") or "")
      local bag = pocket ~= "" and byPocket[pocket]
      if bag and bag.highValue then
        local role = tostring(Spring.GetUnitRulesParam(uid, "va_force_role") or "")
        local hv = Spring.GetUnitRulesParam(uid, "va_high_value")
        if role == "occupation" or role == "held_install" or role == "" then
          local dID = Spring.GetUnitDefID(uid)
          local ud = dID and UnitDefs[dID]
          local n = ud and tostring(ud.name or ""):lower() or ""
          if n:find("beamer", 1, true) or n:find("llt", 1, true) or n:find("hlt", 1, true)
              or n:find("fus", 1, true) then
            local already = false
            for _, u in ipairs(bag.units) do
              if u.def == (ud and ud.name) then
                -- coarse dedupe by def+near position later; allow multiples
              end
            end
            local x, _, z = Spring.GetUnitPosition(uid)
            local hp, maxHp = Spring.GetUnitHealth(uid)
            -- Skip if this uid was already recorded as HV/secondary above.
            local skip = (hv == 1) or role == "objective_secondary"
            if not skip then
              bag.units[#bag.units + 1] = {
                def = ud and ud.name or "",
                x = x or 0,
                z = z or 0,
                hpFrac = (maxHp and maxHp > 0 and hp) and (hp / maxHp) or 1,
                highValue = false,
              }
            end
          end
        end
      end
    end
  end
  local parts = {}
  local mapId = tostring((mission and mission.deploymentMapId) or "")
  for _, bag in pairs(byPocket) do
    if bag.highValue and #(bag.units) > 0 then
      local owner = "enemy"
      if bag.held or (bag.ownerTeam == playerTeamID) then owner = "player" end
      local uparts = {}
      for _, u in ipairs(bag.units) do
        uparts[#uparts + 1] = '{'
          .. '"unitDefName":' .. jstr(u.def)
          .. ',"x":' .. jnum(u.x, 1)
          .. ',"z":' .. jnum(u.z, 1)
          .. ',"hpFrac":' .. jnum(u.hpFrac, 3)
          .. ',"highValue":' .. tostring(u.highValue == true)
          .. '}'
      end
      parts[#parts + 1] = '{'
        .. '"mapId":' .. jstr(mapId)
        .. ',"zoneId":' .. jstr(bag.zoneId or "")
        .. ',"pocketId":' .. jstr(bag.pocketId or "")
        .. ',"installationId":' .. jstr(mapId .. "::" .. tostring(bag.pocketId or ""))
        .. ',"owner":' .. jstr(owner)
        .. ',"status":"standing"'
        .. ',"highValue":true'
        .. ',"units":[' .. table.concat(uparts, ",") .. ']'
        .. '}'
    end
  end
  return '[' .. table.concat(parts, ',') .. ']'
end

-- One walk over the player's units at terminal, five facts out of it:
--   footprint    company-built structures (pads / mex / storage) so a claimed zone is
--                not empty dirt on re-entry. Heroes and their pack structures travel
--                with the sheet and are skipped (saving them respawns a second Solarium).
--   survivors    mobile combat units by def (legacy cadre carry).
--   survivorXp   per def: count / peak+avg engine XP / peak+avg craft XP (fighters AND
--                constructors; rez bots and builders carry craft XP). Named heroes use
--                their sticky peak when it beats live engine XP.
--   loanUnitHp   per def HP quality of units tagged va_loan_package (broker settle).
--   armyValue    metal of living mobile combat units (banked as army budget by Python).
-- Self-contained on purpose: the shared unit helpers are defined further down.
function playerUnitFacts()
  local out = { footprint = {}, footprintCount = 0, survivors = {}, xp = {}, loan = {}, armyValue = 0 }
  local maxFootprint = 64
  local deployZ = tostring((mission and mission.deploymentZoneId) or "")
  local sx = Game.mapSizeX or 1
  local sz = Game.mapSizeZ or 1
  local units = Spring.GetTeamUnits(playerTeamID) or {}
  for i = 1, #units do
    local uID = units[i]
    if Spring.ValidUnitID(uID) and not Spring.GetUnitIsDead(uID) then
      local dID = Spring.GetUnitDefID(uID)
      local ud = dID and UnitDefs[dID]
      if ud then
        local structure = ud.isBuilding or ud.isFactory or ((ud.speed or 1) == 0)
        local commander = ud.customParams and ud.customParams.iscommander
        local fights = ud.canAttack or (ud.weapons and #ud.weapons > 0)
        local builder = (tonumber(ud.buildSpeed) or 0) > 0 or ud.canResurrect or ud.canRepair
        local x, _, z = Spring.GetUnitPosition(uID)
        local hp, maxHp = Spring.GetUnitHealth(uID)
        local hpFrac = (maxHp and maxHp > 0 and hp) and (hp / maxHp) or 1
        -- footprint: structures only, never commanders / living shell / hero pack kit
        if structure and not commander and out.footprintCount < maxFootprint then
          local shell = Spring.GetUnitRulesParam(uID, "va_living_shell")
          local isShell = (shell == 1 or shell == true or shell == "1")
          local heroMark = Spring.GetUnitRulesParam(uID, "va_hero_id")
          local packMark = Spring.GetUnitRulesParam(uID, "va_pack_id")
          local travels = (heroMark ~= nil and heroMark ~= "" and heroMark ~= 0)
            or (packMark ~= nil and packMark ~= "" and packMark ~= 0)
          if (not isShell) and (not travels) then
            local facing = 0
            if Spring.GetUnitBuildFacing then
              facing = tonumber(Spring.GetUnitBuildFacing(uID)) or 0
            end
            local zoneId = deployZ
            if zoneMap and type(zoneMap.zones) == "table" and x and z then
              for _, zrec in ipairs(zoneMap.zones) do
                local b = zrec.bounds or {}
                if x >= normalizedToElmos(b.xMin, sx) and x <= normalizedToElmos(b.xMax, sx)
                    and z >= normalizedToElmos(b.zMin, sz) and z <= normalizedToElmos(b.zMax, sz) then
                  zoneId = tostring(zrec.zoneId or zoneId)
                  break
                end
              end
            end
            out.footprintCount = out.footprintCount + 1
            out.footprint[#out.footprint + 1] = '{'
              .. '"unitDefName":' .. jstr(ud.name or "")
              .. ',"x":' .. jnum(x or 0, 1)
              .. ',"z":' .. jnum(z or 0, 1)
              .. ',"facing":' .. jnum(facing)
              .. ',"hpFrac":' .. jnum(hpFrac, 3)
              .. ',"zoneId":' .. jstr(zoneId)
              .. ',"owner":"player"'
              .. ',"role":"player_footprint"'
              .. '}'
          end
        end
        -- survivors / armyValue: mobile combat units
        if (not structure) and (not commander) and fights then
          out.survivors[ud.name] = (out.survivors[ud.name] or 0) + 1
          out.armyValue = out.armyValue + (tonumber(ud.metalCost or ud.metal or 0) or 0)
        end
        -- survivorXp: mobile fighters + constructors
        if (not structure) and (not commander) and (fights or builder) then
          local xp = 0
          if Spring.GetUnitExperience then
            xp = tonumber((Spring.GetUnitExperience(uID))) or 0
          end
          local hid = heroByUnitID and heroByUnitID[uID]
          if hid and heroes and heroes[hid] then
            local peak = math.max(tonumber(heroes[hid].peakXp) or 0, tonumber(heroes[hid].lastXp) or 0)
            if peak > xp then xp = peak end
          end
          local craft = tonumber((Spring.GetUnitRulesParam(uID, "va_craft_xp"))) or 0
          local b = out.xp[ud.name]
          if not b then
            b = { count = 0, sumXp = 0, peakXp = 0, sumCraft = 0, peakCraft = 0 }
            out.xp[ud.name] = b
          end
          b.count = b.count + 1
          b.sumXp = b.sumXp + xp
          if xp > b.peakXp then b.peakXp = xp end
          b.sumCraft = b.sumCraft + craft
          if craft > b.peakCraft then b.peakCraft = craft end
        end
        -- loanUnitHp: anything tagged as a broker loan
        local loan = Spring.GetUnitRulesParam(uID, "va_loan_package")
        if (loan == 1 or loan == true or loan == "1") and ud.name then
          local frac = (tonumber(maxHp) or 0) > 0 and ((tonumber(hp) or 0) / tonumber(maxHp)) or 0
          local b = out.loan[ud.name]
          if not b then
            b = { count = 0, sum = 0, min = 1 }
            out.loan[ud.name] = b
          end
          b.count = b.count + 1
          b.sum = b.sum + frac
          if frac < b.min then b.min = frac end
        end
      end
    end
  end
  Spring.Echo("VA_PLAYER_FOOTPRINT count=" .. tostring(out.footprintCount)
    .. " map=" .. tostring((mission and mission.deploymentMapId) or ""))
  return out
end

function playerFootprintJson(facts)
  return '[' .. table.concat(facts.footprint, ',') .. ']'
end

function playerSurvivorsJson(facts)
  local parts = {}
  for name, c in pairs(facts.survivors) do parts[#parts + 1] = jstr(name) .. ':' .. jnum(c) end
  return '{' .. table.concat(parts, ',') .. '}'
end

function playerSurvivorXpJson(facts)
  local parts = {}
  for name, b in pairs(facts.xp) do
    local avg = (b.count > 0) and (b.sumXp / b.count) or 0
    local avgCraft = (b.count > 0) and (b.sumCraft / b.count) or 0
    parts[#parts + 1] = jstr(name) .. ':{'
      .. '"count":' .. jnum(b.count)
      .. ',"peakXp":' .. jnum(b.peakXp, 4)
      .. ',"avgXp":' .. jnum(avg, 4)
      .. ',"peakCraftXp":' .. jnum(b.peakCraft, 4)
      .. ',"avgCraftXp":' .. jnum(avgCraft, 4)
      .. '}'
  end
  return '{' .. table.concat(parts, ',') .. '}'
end

function loanUnitHpJson(facts)
  local parts = {}
  for name, b in pairs(facts.loan) do
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
  local defName = ud and ud.name or ""
  local hvParam = Spring.GetUnitRulesParam and Spring.GetUnitRulesParam(unitID, "va_high_value")
  local highValue = (hvParam == 1 or hvParam == true or hvParam == "1")
  if not highValue and type(defName) == "string" then
    local dn = string.lower(defName)
    if string.find(dn, "fus", 1, true) or string.find(dn, "beamer", 1, true)
        or string.find(dn, "annihilator", 1, true) then
      highValue = true
    end
  end
  local targetZone = (mission and mission.objective and mission.objective.targetZoneId)
    or (mission and mission.targetZoneId) or ""
  shellScarEvents[#shellScarEvents + 1] = {
    zoneId = zone and tostring(zone) or tostring(targetZone),
    pocketId = pocket and tostring(pocket) or "",
    unitDefName = defName,
    destroyed = true,
    damageFrac = 1.0,
    highValue = highValue and true or false,
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
      .. ',"highValue":' .. tostring(e.highValue == true)
      .. '}'
  end
  return '[' .. table.concat(parts, ',') .. ']'
end

-- The result is facts only (law: Lua reports facts, Python interprets).
-- status is the terminal KIND (extracted | wiped | closed), never a verdict;
-- tools/manifest_v1.py and tools/match_credit_v1.py turn these facts into
-- victory / partial / defeat / abandon, zone flips and credits. Nothing here
-- may compute a judgement — if Python needs something, export the fact.
local function resultJson()
  local alive, total = companionCounts()
  local req = mission.objective and mission.objective.requiredFrames or 600
  local frame = Spring.GetGameFrame() or 0
  local obj = mission.objective or {}
  local targetZone = mission.targetZoneId or obj.targetZoneId or ""
  local patron = mission.patron or (mission.worldConflict and mission.worldConflict.patron) or ""
  -- Capture state machine facts: the pocket was cleared / the hold finished.
  local nodeClaimed = capture.nodeClaimed or (objectiveCompleteHow == "node_claimed")
  local chapter = sortieChapter or 1
  local reasonSafe = tostring(terminalReason or "none"):gsub("|", "_")
  local cid = mission.campaignId or "verdance_ashes"
  local mid = mission.missionId or "va_unknown"
  local mn = tostring(mission.missionNumber or 0)
  -- resultKey: unique per sortie attempt (chapter + terminal kind + reason + frame).
  local rkey = cid .. "|" .. mid .. "|" .. mn
    .. "|ch" .. tostring(chapter)
    .. "|" .. tostring(status)
    .. "|" .. reasonSafe
    .. "|f" .. tostring(frame)
  Spring.SetGameRulesParam("va_result_key", rkey, { public = true })
  local sortieId = mission.hubChoiceId or mission.choiceId or mission.sortieId or ""
  -- Exfil refund: living Tnb stakes on player builds return to liquid bank.
  -- Campaign settle uses tenebriumBank as bag SoT; without this, spent stakes
  -- on left-behind structures vanish from the company wallet.
  local livingStakes, livingStakeUnits = 0, 0
  if tenebLoot.refundLivingStakesOnExfil then
    livingStakes, livingStakeUnits = tenebLoot.refundLivingStakesOnExfil(playerTeamID)
  elseif tenebLoot.livingStakes then
    livingStakes, livingStakeUnits = tenebLoot.livingStakes(playerTeamID)
  end
  livingStakes = math.floor(tonumber(livingStakes) or 0)
  livingStakeUnits = math.floor(tonumber(livingStakeUnits) or 0)
  -- End-of-sortie metal stock → campaign 1km$ export (floor(metal/1000)).
  -- Campaign bag stays home; settle ADDS this export (does not replace bag).
  local metalStored, metalStorage = 0, 0
  if Spring.GetTeamResources then
    local okM, mc, ms = pcall(Spring.GetTeamResources, playerTeamID, "metal")
    if okM then
      metalStored = tonumber(mc) or 0
      metalStorage = tonumber(ms) or 0
    end
  end
  local metalKExtracted = math.floor(metalStored / 1000)
  local com = (mission and mission.commerce) or {}
  -- Bag no longer enters the field (metalKBrought=0). fieldStart is operating
  -- allotment only; settle nets it out so unused seed does not inflate the bag.
  local metalKBrought = math.floor(tonumber(com.metalKBrought or 0) or 0)
  local metalKFieldStart = math.floor(tonumber(com.fieldStartMetalK or com.metalKFieldStart or 0) or 0)
  -- One walk over the player's units: footprint, survivors, XP, loan HP, army metal.
  local facts = playerUnitFacts()
  return '{' .. table.concat({
    '"schemaVersion":' .. jstr("verdance-match-result/2.0"),
    '"campaignId":' .. jstr(cid),
    '"missionId":' .. jstr(mid),
    '"missionNumber":' .. jnum(mission.missionNumber or 0),
    '"playerTeamId":' .. jnum(playerTeamID),
    '"armyValue":' .. jnum(facts.armyValue, 2),
    '"metrics":{"armyValue":' .. jnum(facts.armyValue, 2) .. '}',
    '"chapterIndex":' .. jnum(chapter),
    '"pathSignal":' .. jstr(mission.pathSignal or "B"),
    -- terminal kind only: extracted | wiped | closed (Python reads the verdict off the manifest)
    '"status":' .. jstr(status),
    '"manifest":' .. ((GG and GG.VA_ManifestJson) and GG.VA_ManifestJson() or 'null'),
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
    -- capture state machine (facts)
    '"nodeClaimed":' .. tostring(nodeClaimed == true),
    '"nodeClaimedFrame":' .. jnum(nodeClaimedFrame),
    '"pocketCleared":' .. tostring(capture.pocketCleared == true),
    '"capturePhase":' .. jstr(capture.phase or "idle"),
    '"captureMode":' .. tostring(capture.mode == true),
    '"regrowWaves":' .. jnum(capture.regrowWaves or 0),
    '"zoneHoldFrames":' .. jnum(zoneHoldFrames),
    '"terminalReason":' .. jstr(terminalReason),
    -- primary objective (facts)
    '"objectiveKind":' .. jstr(obj.kind or ""),
    '"objectiveMode":' .. jstr(vaObjectiveMode(obj.kind)),
    '"objectiveComplete":' .. tostring(objectiveComplete == true),
    '"objectiveCompleteHow":' .. jstr(objectiveCompleteHow or ""),
    '"objectiveCompleteFrame":' .. jnum(objectiveCompleteFrame),
    '"objectiveBypassed":' .. tostring(objectiveBypassed == true),
    '"objectiveTargetsTotal":' .. jnum(objectiveTargetCount),
    '"objectiveTargetsDestroyed":' .. jnum(objectiveTargetsDestroyed),
    -- required secondary marks still open + the full-victory gate the HUD showed (EXTRACT phase)
    '"requiredMarksLeft":' .. jnum(MarksLib.requiredLeft(marks)),
    '"allObjectivesDone":' .. tostring(vaAllObjectivesDone() == true),
    -- objectiveFailed is the SoT latch (rescue contract destroyed). Alias kept
    -- for older hub/kernel readers. Fail hero lets company.fieldPool mark lost.
    '"objectiveFailed":' .. tostring(rescueContractFailed == true),
    '"objectiveFailReason":' .. jstr(rescueContractFailReason or ""),
    '"objectiveFailHero":' .. jstr(rescueContractFailHero or ""),
    '"rescueContractFailed":' .. tostring(rescueContractFailed == true),
    '"extractionZoneId":' .. jstr(mission.extractionZoneId or obj.extractionZoneId or ""),
    '"chosenTargetForceId":' .. jstr(chosenTargetForceId or ""),
    '"playerSurvivors":' .. playerSurvivorsJson(facts),
    '"playerSurvivorXp":' .. playerSurvivorXpJson(facts),
    '"loanUnitHp":' .. loanUnitHpJson(facts),
    '"shellScars":' .. shellScarsJson(),
    '"heroResults":' .. heroResultsJson(),
    '"recruitedHeroIds":' .. recruitedHeroIdsJson(),
    '"namedOutcomes":' .. namedOutcomesJson(),
    '"destroyedObjectiveIds":' .. destroyedObjectiveIdsJson(),
    '"objectiveResults":' .. objectiveResultsJson(),
    '"secondaryResults":' .. secondaryResultsJson(),
    '"survivingInstalls":' .. survivingInstallsJson(),
    '"playerFootprint":' .. playerFootprintJson(facts),
    -- pass three belief contract, produced by game_verdance_belief_observe.lua (GG, no new locals here)
    '"observedZones":' .. ((GG and GG.VA_ObservedZonesJson) and GG.VA_ObservedZonesJson() or 'null'),
    '"beliefExport":' .. ((GG and GG.VA_BeliefExportJson) and GG.VA_BeliefExportJson() or 'null'),
    '"purge":{"armed":' .. tostring(extraObj.purge == true)
      .. ',"done":' .. tostring(extraObj.purgeDone == true) .. '}',
    '"companionsAlive":' .. jnum(alive),
    '"companionsTotal":' .. jnum(total),
    '"debugAutoProgress":' .. jnum(debugAutoProgress),
    '"farmSortie":' .. tostring((mission.difficulty and mission.difficulty.farmSortie) or (mission.progression and mission.progression.farmSortie) or false),
    '"sessionMode":' .. jstr(mission.sessionMode or "same_map"),
    '"occupationModel":' .. jstr(mission.occupationModel or "living_shell"),
    '"map":{"name":' .. jstr(Game.mapName or "") .. ',"sizeX":' .. jnum(Game.mapSizeX or 0) .. ',"sizeZ":' .. jnum(Game.mapSizeZ or 0) .. '}',
    '"zoneMap":{' .. zoneMapJson() .. '}',
    '"economy":{' .. economyJson() .. '}',
    '"metalStored":' .. jnum(metalStored, 1),
    '"metalStorage":' .. jnum(metalStorage, 1),
    '"metalKExtracted":' .. jnum(metalKExtracted),
    '"metalKBrought":' .. jnum(metalKBrought),
    '"metalKFieldStart":' .. jnum(metalKFieldStart),
    '"metalExportMode":' .. jstr("add"),
    '"graph":{' .. graphJson() .. '}',
    '"reputation":{' .. reputationJson() .. '}',
    '"primaryCompanion":{' .. primaryCompanionJson() .. '}',
    '"tenebriumLooted":' .. jnum(tenebLoot.looted or tenebLoot.total or 0),
    '"tenebriumBank":' .. jnum(tenebLoot.bank or 0),
    '"tenebriumInvested":' .. jnum(livingStakes),
    '"tenebriumLivingStakes":' .. jnum(livingStakes),
    '"tenebriumLivingStakeUnits":' .. jnum(livingStakeUnits),
    '"tenebriumSpent":' .. jnum(tenebLoot.spent or 0),
    '"tenebriumLost":' .. jnum(tenebLoot.lost or 0),
    '"tenebriumLootEvents":' .. (tenebLoot.eventsJson and tenebLoot.eventsJson() or '[]'),
    '"tenebriumWrecksCreated":' .. jnum(tenebLoot.wrecksCreated or 0),
    '"tenebriumWrecksClaimed":' .. jnum(tenebLoot.wrecksClaimed or 0),
    '"tenebriumWrecksLost":' .. jnum(tenebLoot.wrecksLost or 0),
    '"tenebriumUnclaimedOnExtraction":' .. jnum(tenebLoot.unclaimedWrecks and tenebLoot.unclaimedWrecks() or 0),
    '"tenebriumClaimEvents":' .. (tenebLoot.claimEventsJson and tenebLoot.claimEventsJson() or '[]'),
    '"tenebriumTeamBanks":' .. (tenebLoot.teamBanksJson and tenebLoot.teamBanksJson() or '{}'),
    '"tenebriumFactionBanks":' .. (tenebLoot.factionBanksJson and tenebLoot.factionBanksJson() or '{}'),
    '"armadaTenebriumCrisis":' .. tostring(tenebLoot.armadaCrisis == true),
    '"quantumTransitionJournal":' .. (VAQ.kernel and VAQ.kernel:journalJson() or '[]'),
    '"finalQuantumState":' .. (VAQ.kernel and VAQ.kernel:json() or 'null')
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
  -- resultJson can throw on bad Spring returns; never skip the harvest marker.
  local ok, json = pcall(resultJson)
  if not ok then
    Spring.Echo("VA_RESULT_JSON_ERROR " .. tostring(json))
    json = "{"
      .. '"schemaVersion":"verdance-match-result/2.0-fallback",'
      .. '"status":' .. jstr(tostring(status or "unknown")) .. ","
      .. '"terminalReason":' .. jstr(tostring(terminalReason or "result_json_error")) .. ","
      .. '"objectiveComplete":' .. tostring(objectiveComplete == true) .. ","
      .. '"objectiveFailed":' .. tostring(rescueContractFailed == true) .. ","
      .. '"objectiveFailHero":' .. jstr(tostring(rescueContractFailHero or "")) .. ","
      .. '"tenebriumBank":' .. jnum((tenebLoot and tenebLoot.bank) or 0) .. ","
      .. '"tenebriumLooted":' .. jnum((tenebLoot and (tenebLoot.looted or tenebLoot.total)) or 0)
      .. "}"
  end
  lastResultJson = json
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
  VAQ.transition(terminalReason)
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
  if tenebLoot.initFromMission then tenebLoot.initFromMission() end
  Spring.SetGameRulesParam("va_status", status, { public = true })
  Spring.Echo("VA_START " .. tostring(mission.missionId) .. " zone=" .. tostring(mission.zone or "unknown"))
  echoStatus()
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

-- Territory ownership is DV-only. Pad-tooth heroes (area_control / Warder ring)
-- count fighting metal as defensiveValue even when the chassis is mobile.
local function heroIsAreaControl(heroId)
  heroId = tostring(heroId or "")
  if heroId == "" then return false end
  local tags = HeroTags and HeroTags.HERO_DEFAULTS and HeroTags.HERO_DEFAULTS[heroId]
  if type(tags) == "table" then
    for i = 1, #tags do
      if tags[i] == "area_control" then return true end
    end
  end
  return false
end

local function unitIsPadTooth(unitID)
  if not unitID then return false end
  local v = Spring.GetUnitRulesParam(unitID, "va_pad_tooth")
  if v == 1 or v == true or v == "1" then return true end
  local hid = Spring.GetUnitRulesParam(unitID, "va_hero_id")
    or Spring.GetUnitRulesParam(unitID, "va_pack_id")
  if hid and heroIsAreaControl(hid) then return true end
  return false
end

local function stampPadToothIfNeeded(unitID, heroIdOrPkg)
  if not unitID or not Spring.ValidUnitID(unitID) then return end
  local hid = tostring(heroIdOrPkg or "")
  if hid == "" then return end
  local id = hid:match("^crew_pack_(.+)$")
    or hid:match("^crew_escort_([^_]+)")
    or hid:match("^crew_mint_(.+)$")
    or hid:match("^crew_callin_(.+)$")
    or hid:match("^crew_([^_]+)$")
    or hid
  if heroIsAreaControl(id) then
    Spring.SetUnitRulesParam(unitID, "va_pad_tooth", 1, { public = true })
  end
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
-- Pack mentors (scout / factory heroes): bank XP from ALL subordinates, then
-- re-grant the hero's ONE field-effect stat (speed / vision / build / …).
-- Spoke wheelies remain the classic case; Tick / Kettle / Consul / Twitch join.
packMentors = packMentors or {}  -- heroId -> { bankXp, harvested, minted, productDefs }

-- Compat alias: older call sites still touch wheelieMentor for Spoke.
wheelieMentor = wheelieMentor or { heroId = nil, bankXp = 0, minted = 0, harvested = 0 }

local function isWheelieDef(defName)
  if not defName then return false end
  local n = string.lower(tostring(defName))
  return n == "legscout" or n:find("wheel", 1, true) ~= nil
end

local function mentorProductDefs()
  local roster = VA_CREW_loadRoster and VA_CREW_loadRoster() or nil
  if roster and roster.MENTOR_PRODUCTS then return roster.MENTOR_PRODUCTS end
  return {}
end

local function heroIsPackMentor(heroId, spec, tagList)
  local id = tostring(heroId or (spec and spec.heroId) or "")
  local roster = VA_CREW_loadRoster and VA_CREW_loadRoster() or nil
  if roster and roster.isMentor and roster.isMentor(id) then return true end
  if HeroTags and HeroTags.isMentorHero then
    return HeroTags.isMentorHero(id, tagList)
  end
  local trait = tostring(spec and (spec.heroTrait or spec.trait) or "")
  return trait == "wheelie_mentor" or trait == "scout_tech" or trait == "factory_mentor"
end

local function refreshMentorFieldEffect(heroId)
  local rec = heroes[heroId]
  if not rec or not rec.unitID or not Spring.ValidUnitID(rec.unitID) then return end
  if not HeroTags or not HeroTags.applyToHero then return end
  local roster = VA_CREW_loadRoster and VA_CREW_loadRoster() or nil
  local h = roster and ((roster.get and roster.get(heroId)) or (roster.HEROES and roster.HEROES[heroId])) or nil
  local tagList = HeroTags.collectFromHero(h, { heroId = heroId, heroTrait = rec.trait }, heroId)
  local xp = math.max(tonumber(rec.peakXp) or 0, tonumber((packMentors[heroId] or {}).bankXp) or 0)
  local field = HeroTags.applyToHero(rec.unitID, rec, tagList, xp)
  -- Push the same field effect onto living pack mates.
  if field and field.primaryStat and Spring.GetTeamUnits then
    local units = Spring.GetTeamUnits(playerTeamID) or {}
    for i = 1, #units do
      local u = units[i]
      if u ~= rec.unitID and Spring.ValidUnitID(u) and not Spring.GetUnitIsDead(u) then
        local lead = Spring.GetUnitRulesParam(u, "va_pack_leader")
          or Spring.GetUnitRulesParam(u, "va_pack_id")
        if tostring(lead or "") == tostring(heroId) then
          HeroTags.applyFieldToUnit(u, field, rec)
        end
      end
    end
  end
end

local function stampMentorSubordinate(unitID, heroId)
  local bag = packMentors[heroId]
  if not bag then return end
  local floor = tonumber(bag.bankXp) or 0
  Spring.SetUnitRulesParam(unitID, "va_pack_leader", heroId, { public = true })
  Spring.SetUnitRulesParam(unitID, "va_pack_id", heroId, { public = true })
  Spring.SetUnitRulesParam(unitID, "va_pack_role", "mate", { public = true })
  if floor > 0 and Spring.SetUnitExperience then
    pcall(Spring.SetUnitExperience, unitID, floor)
    Spring.SetUnitRulesParam(unitID, "va_mentor_xp_floor", floor, { public = true })
  end
  bag.minted = (bag.minted or 0) + 1
  -- Apply current field effect to the new mate.
  local rec = heroes[heroId]
  if rec and rec.field and HeroTags and HeroTags.applyFieldToUnit then
    HeroTags.applyFieldToUnit(unitID, rec.field, rec)
  elseif rec then
    refreshMentorFieldEffect(heroId)
  end
  if GG and GG.VA_PackOverlayStamp then
    pcall(GG.VA_PackOverlayStamp, unitID, heroId, "mate")
  end
  -- Spoke compat markers
  if heroId == "spoke" then
    Spring.SetUnitRulesParam(unitID, "va_wheelie_mint", 1, { public = true })
    Spring.SetUnitRulesParam(unitID, "va_wheelie_xp_floor", floor, { public = true })
  end
end

local function harvestMentorXp(unitID, heroId)
  heroId = tostring(heroId or "")
  if heroId == "" or not packMentors[heroId] then return end
  if heroByUnitID[unitID] then return end -- named hero death handled elsewhere
  local xp = 0
  if Spring.GetUnitExperience then xp = Spring.GetUnitExperience(unitID) or 0 end
  if xp <= 0 then return end
  local bag = packMentors[heroId]
  local prev = tonumber(bag.bankXp) or 0
  if xp <= prev then return end
  bag.bankXp = xp
  bag.harvested = (bag.harvested or 0) + 1
  local rec = heroes[heroId]
  if rec then
    rec.peakXp = math.max(tonumber(rec.peakXp) or 0, xp)
    rec.lastXp = rec.peakXp
    if rec.unitID and Spring.ValidUnitID(rec.unitID) and Spring.SetUnitExperience then
      pcall(Spring.SetUnitExperience, rec.unitID, rec.peakXp)
      Spring.SetUnitRulesParam(rec.unitID, "va_hero_xp", rec.peakXp, { public = true })
    end
    refreshMentorFieldEffect(heroId)
  end
  if heroId == "spoke" then
    wheelieMentor.bankXp = bag.bankXp
    wheelieMentor.harvested = bag.harvested
  end
  Spring.Echo("VA_MENTOR_HARVEST mentor=" .. heroId
    .. " xp=" .. tostring(xp) .. " bank=" .. tostring(bag.bankXp)
    .. " field=" .. tostring(rec and rec.fieldStat or "?"))
end

local function registerPackMentor(heroId, rec, seedXp)
  heroId = tostring(heroId or "")
  if heroId == "" then return end
  local bag = packMentors[heroId] or { bankXp = 0, harvested = 0, minted = 0 }
  bag.bankXp = math.max(tonumber(bag.bankXp) or 0, tonumber(seedXp) or 0, tonumber(rec and rec.peakXp) or 0)
  bag.productDefs = mentorProductDefs()[heroId]
  packMentors[heroId] = bag
  if heroId == "spoke" then
    wheelieMentor.heroId = heroId
    wheelieMentor.bankXp = bag.bankXp
  end
  Spring.Echo("VA_PACK_MENTOR online id=" .. heroId
    .. " bank=" .. tostring(bag.bankXp)
    .. " field=" .. tostring(rec and rec.fieldStat or "?"))
end

local function pollMentorSubordinateXp(frame)
  if not next(packMentors) then return end
  if frame % 90 ~= 0 then return end -- ~3s
  local units = Spring.GetTeamUnits(playerTeamID) or {}
  local peaks = {}
  for i = 1, #units do
    local u = units[i]
    if Spring.ValidUnitID(u) and not Spring.GetUnitIsDead(u) and not heroByUnitID[u] then
      local lead = Spring.GetUnitRulesParam(u, "va_pack_leader")
        or Spring.GetUnitRulesParam(u, "va_pack_id")
      lead = tostring(lead or "")
      if lead ~= "" and packMentors[lead] then
        local xp = 0
        if Spring.GetUnitExperience then xp = Spring.GetUnitExperience(u) or 0 end
        if xp > (peaks[lead] or 0) then peaks[lead] = xp end
      end
    end
  end
  for heroId, xp in pairs(peaks) do
    local bag = packMentors[heroId]
    if bag and xp > (tonumber(bag.bankXp) or 0) then
      bag.bankXp = xp
      local rec = heroes[heroId]
      if rec then
        rec.peakXp = math.max(tonumber(rec.peakXp) or 0, xp)
        rec.lastXp = rec.peakXp
        if rec.unitID and Spring.ValidUnitID(rec.unitID) and Spring.SetUnitExperience then
          pcall(Spring.SetUnitExperience, rec.unitID, rec.peakXp)
          Spring.SetUnitRulesParam(rec.unitID, "va_hero_xp", rec.peakXp, { public = true })
        end
        refreshMentorFieldEffect(heroId)
        Spring.Echo("VA_MENTOR_POLL mentor=" .. heroId .. " bank=" .. tostring(xp)
          .. " field=" .. tostring(rec.fieldStat or "?"))
      end
    end
  end
end

-- Named heroes are flat-tough: 3× stock HP before field-effect folds.
VA_HERO_HP_MULT = 3.0

-- Spring GetUnitRulesParam can return *no value*; tonumber() with zero args
-- aborts LuaRules (LUA_ERRRUN). Never pass a bare Get* into tonumber().
local function rulesNum(unitID, key)
  local v = Spring.GetUnitRulesParam(unitID, key)
  if v == nil then return nil end
  return tonumber(v)
end

local function applyHeroModifiers(unitID, rec)
  local hpMult = tonumber(rec.hpMult) or VA_HERO_HP_MULT or 3.0
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

local function registerHeroSpawn(unitID, spec)
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
      hpMult = tonumber(spec.heroHpMult) or VA_HERO_HP_MULT or 3.0,
      baseHpMult = tonumber(spec.heroHpMult) or VA_HERO_HP_MULT or 3.0,
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
    -- Flat 3× toughness is the named-hero floor; mission may raise, not shrink.
    local wantHp = tonumber(spec.heroHpMult) or VA_HERO_HP_MULT or 3.0
    if wantHp < (VA_HERO_HP_MULT or 3.0) then wantHp = VA_HERO_HP_MULT or 3.0 end
    rec.baseHpMult = wantHp
    rec.hpMult = wantHp
    if tonumber(spec.heroBuildPowerMult) then rec.buildPowerMult = tonumber(spec.heroBuildPowerMult) end
    if spec.heroTrait then rec.trait = tostring(spec.heroTrait) end
  end
  if rec.baseHpMult == nil then
    rec.baseHpMult = tonumber(rec.hpMult) or VA_HERO_HP_MULT or 3.0
  end
  if (tonumber(rec.baseHpMult) or 0) < (VA_HERO_HP_MULT or 3.0) then
    rec.baseHpMult = VA_HERO_HP_MULT or 3.0
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
      local h = roster and ((roster.get and roster.get(id)) or (roster.HEROES and roster.HEROES[id])) or nil
      local tagList = HeroTags.collectFromHero(h, spec, id)
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

local DECOY_FOR_REAL_COM = {
  armcom = "armdecom",
  corcom = "cordecom",
  legcom = "legdecom",
}

-- Sea level is 0. A front-band slide can plant the company in the lake;
-- land units there drown. Global on purpose (main chunk is at the local cap).
vaDryClaims = nil
function vaDryLanding(x, z)
  local mapX = Game.mapSizeX or 0
  local mapZ = Game.mapSizeZ or 0
  local function ground(px, pz)
    if px < 64 or pz < 64 or (mapX > 0 and px > mapX - 64) or (mapZ > 0 and pz > mapZ - 64) then
      return -9999
    end
    return (Spring.GetGroundHeight and Spring.GetGroundHeight(px, pz)) or -9999
  end
  local sinkPending = 0
  if (tonumber(vaWaterApplied) or 0) < 0.05 and vaWaterElevation then
    local hydro = mission and mission.hydrology
    local level = hydro and tonumber(hydro.level) or 0
    if level > 0 then
      sinkPending = math.max(0, (vaWaterElevation(level) or 0) - (vaWaterElevation(0) or 0))
    end
  end
  local need = 10 + sinkPending
  local function cell(px, pz)
    return tostring(math.floor(px / 80)) .. ":" .. tostring(math.floor(pz / 80))
  end
  vaDryClaims = vaDryClaims or {}
  if ground(x, z) >= need and not vaDryClaims[cell(x, z)] then
    vaDryClaims[cell(x, z)] = true
    return x, z
  end
  for radius = 90, 3600, 90 do
    for i = 0, 19 do
      local ang = (i / 20) * math.pi * 2
      local px = x + math.cos(ang) * radius
      local pz = z + math.sin(ang) * radius
      local y = ground(px, pz)
      if y >= need and not vaDryClaims[cell(px, pz)] then
        vaDryClaims[cell(px, pz)] = true
        return px, pz
      end
    end
  end
  vaDryClaims[cell(x, z)] = true
  return x, z
end

local function spawnOneUnit(defName, x, z, facing, teamID, spec, force)
  -- Occupation shells plant decoy farmers, not real commanders. Remap any
  -- enemy real-com spawn (all maps) so a stale recipe / AI start unit cannot
  -- introduce a 700-AoE commanderExplosion + 1250-metal wreck into a raid.
  if teamID ~= playerTeamID then
    local decoy = DECOY_FOR_REAL_COM[tostring(defName)]
    if decoy and UnitDefNames and UnitDefNames[decoy] then
      defName = decoy
    end
  end
  do
    local ud = UnitDefNames and UnitDefNames[defName]
    local skipDry = ud and (ud.canFly or ud.floatOnWater)
    if not skipDry then
      local nx, nz = vaDryLanding(x, z)
      if math.abs((nx or x) - x) > 40 or math.abs((nz or z) - z) > 40 then
        vaDryMoves = (vaDryMoves or 0) + 1
        if vaDryMoves <= 8 then
          Spring.Echo(string.format(
            "VA_DRY_LANDING def=%s from=%.0f,%.0f to=%.0f,%.0f y=%.0f",
            tostring(defName), x, z, nx or x, nz or z,
            (Spring.GetGroundHeight and Spring.GetGroundHeight(nx or x, nz or z)) or 0))
        end
      end
      x, z = nx or x, nz or z
    end
  end
  local y = Spring.GetGroundHeight(x, z)
  local unitID = Spring.CreateUnit(defName, x, y, z, facing, teamID)
  if unitID then
    Spring.SetUnitRulesParam(unitID, "va_playable_proxy", 1, { public = true })
    -- Pack mates: stamp leader; mentors also mint XP floor + field aura.
    if teamID == playerTeamID and not (spec and (spec.heroId or spec.hero)) then
      local pkg = spec and tostring(spec.packageTag or "") or ""
      local lead = nil
      if pkg ~= "" then
        lead = pkg:match("^crew_pack_(.+)$")
          or pkg:match("^crew_escort_([^_]+)")
          or pkg:match("^crew_mint_(.+)$")
          or pkg:match("^crew_([^_]+)$")
      end
      if lead and packMentors[lead] then
        stampMentorSubordinate(unitID, lead)
      elseif lead and heroes[lead] then
        Spring.SetUnitRulesParam(unitID, "va_pack_leader", lead, { public = true })
        Spring.SetUnitRulesParam(unitID, "va_pack_id", lead, { public = true })
        Spring.SetUnitRulesParam(unitID, "va_pack_role", "mate", { public = true })
        local rec = heroes[lead]
        if rec and rec.field and HeroTags and HeroTags.applyFieldToUnit then
          local okMate, errMate = pcall(HeroTags.applyFieldToUnit, unitID, rec.field, rec)
          if not okMate then
            Spring.Echo("VA_PACK_FIELD_FAIL lead=" .. tostring(lead)
              .. " unit=" .. tostring(unitID) .. " err=" .. tostring(errMate))
          end
        end
        if GG and GG.VA_PackOverlayStamp then
          pcall(GG.VA_PackOverlayStamp, unitID, lead, "mate")
        end
      elseif isWheelieDef(defName) and packMentors["spoke"] then
        stampMentorSubordinate(unitID, "spoke")
      end
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
          MarksLib.bindTarget(marks, unitID, sid, {
            required = (force.required == true),
            kind = MarksLib.KIND.structure,
            label = sid,
          })
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
    elseif teamID == playerTeamID and spec then
      -- Non-hero player units: restore banked combat / craft XP between rounds.
      -- Majority retain: campaign bakes keepFrac into spec.xp already; still
      -- floor against mission.cadreXp so green packs do not wipe veterans.
      local seedXp = tonumber(spec.xp or spec.heroXp or 0) or 0
      if seedXp <= 0 and mission and type(mission.cadreXp) == "table" then
        local bag = mission.cadreXp[defName]
        if type(bag) == "table" then
          seedXp = tonumber(bag.xp or bag.avgXp or bag.peakXp) or 0
        elseif type(bag) == "number" then
          seedXp = bag
        end
      end
      if seedXp > 0 and Spring.SetUnitExperience then
        pcall(Spring.SetUnitExperience, unitID, seedXp)
        Spring.SetUnitRulesParam(unitID, "va_carry_xp", seedXp, { public = true })
        if GG and GG.VA_VetRefresh then pcall(GG.VA_VetRefresh, unitID) end
      end
      local craftSeed = tonumber(spec.craftXp or 0) or 0
      if craftSeed <= 0 and mission and type(mission.cadreXp) == "table" then
        local bag = mission.cadreXp[defName]
        if type(bag) == "table" then
          craftSeed = tonumber(bag.craftXp or bag.avgCraftXp or bag.peakCraftXp) or 0
        end
      end
      if craftSeed > 0 then
        Spring.SetUnitRulesParam(unitID, "va_craft_xp", craftSeed, { public = true })
        if GG and GG.VA_CraftRefresh then
          pcall(GG.VA_CraftRefresh, unitID)
        end
      end
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
        stampPadToothIfNeeded(unitID, spec.packageTag)
        if GG and GG.VA_PackOverlayStamp then
          local pid = tostring(spec.packageTag):match("crew_pack_(.+)")
            or tostring(spec.packageTag):match("crew_escort_([^_]+)")
            or tostring(spec.packageTag):match("crew_([^_]+)")
          if pid then GG.VA_PackOverlayStamp(unitID, pid, "mate") end
        end
      end
      Spring.Echo("VA_DAMAGED_SPAWN unit=" .. tostring(unitID) .. " frac=" .. tostring(hfrac)
        .. " package=" .. tostring(spec.packageTag or ""))
    elseif spec and spec.packageTag then
      Spring.SetUnitRulesParam(unitID, "va_package_tag", tostring(spec.packageTag), { public = true })
      stampPadToothIfNeeded(unitID, spec.packageTag)
      if GG and GG.VA_PackOverlayStamp then
        local pid = tostring(spec.packageTag):match("crew_pack_(.+)")
          or tostring(spec.packageTag):match("crew_escort_([^_]+)")
          or tostring(spec.packageTag):match("crew_([^_]+)")
        if pid then GG.VA_PackOverlayStamp(unitID, pid, "mate") end
      end
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

  local formation = tostring(spec.formation or "")
  if formation == "triangle" and count >= 3 then
    -- Equilateral-ish triangle: point toward +Z, base behind.
    local tri = {
      { 0, 0 },
      { -spacing, spacing },
      { spacing, spacing },
    }
    for i = 1, count do
      local off = tri[((i - 1) % 3) + 1]
      local ring = math.floor((i - 1) / 3)
      local x = anchorX + off[1] * (1 + ring * 0.85)
      local z = anchorZ + off[2] * (1 + ring * 0.85)
      spawned = spawned + spawnOneUnit(defName, x, z, facing, teamID, spec, force)
    end
    return spawned
  end
  if formation == "ring" and count > 1 then
    local radius = spacing
    for i = 1, count do
      local ang = ((i - 1) / count) * math.pi * 2
      local x = anchorX + math.cos(ang) * radius
      local z = anchorZ + math.sin(ang) * radius
      spawned = spawned + spawnOneUnit(defName, x, z, facing, teamID, spec, force)
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

function VA_CREW_spawnHeroPack(heroId, baseX, baseZ, dx0)
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
    heroName = tostring(h.name or heroId),
    -- you (the first company pick, mission.you) are mission-critical, like Ketha
    missionCritical = h.missionCritical == true or (mission ~= nil and tostring(mission.you or "") == tostring(heroId)),
    heroTrait = h.heroTrait,
    heroTags = h.tags or h.traits,
    packageTag = "crew_" .. tostring(heroId),
  }
  -- Pull XP/level from mission.heroes if present; else roster startXp (explicit 0 is green).
  -- Named heroes are flat 3× HP; mission hpMult may raise above that, never below.
  heroSpec.heroHpMult = VA_HERO_HP_MULT or 3.0
  if mission and type(mission.heroes) == "table" then
    for _, mh in ipairs(mission.heroes) do
      if mh and tostring(mh.id or mh.heroId) == tostring(heroId) then
        heroSpec.heroXp = mh.xp
        heroSpec.heroLevel = mh.level
        heroSpec.heroRank = mh.rank
        local mhHp = tonumber(mh.hpMult)
        if mhHp and mhHp > (VA_HERO_HP_MULT or 3.0) then
          heroSpec.heroHpMult = mhHp
        end
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
  local offsets = {
    {0, 0}, {96, 0}, {-96, 0}, {0, 96}, {0, -96},
    {128, 64}, {-128, 64}, {64, -128}, {-64, -128}, {160, 0},
  }
  local unitID, sx, sz = nil, x, z
  for oi = 1, #offsets do
    local ox, oz = x + offsets[oi][1], z + offsets[oi][2]
    local oy = (Spring.GetGroundHeight and Spring.GetGroundHeight(ox, oz)) or 0
    unitID = Spring.CreateUnit(seedDef, ox, oy, oz, 0, gaia)
    if unitID then
      sx, sz = ox, oz
      break
    end
  end
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
      hpMult = tonumber(fr.heroHpMult) or VA_HERO_HP_MULT or 3.0,
      baseHpMult = tonumber(fr.heroHpMult) or VA_HERO_HP_MULT or 3.0,
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

local function tickFieldRecruitPendingDeath(frame)
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
local function enableFieldFactoryPrinter(unitID, heroId)
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

local function claimFieldFactoriesForHero(heroId, aroundX, aroundZ)
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
          heroHpMult = tonumber(fr.heroHpMult) or VA_HERO_HP_MULT or 3.0,
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
  -- Core always
  for ci, id in ipairs(roster.CORE or { "vane", "ketha" }) do
    total = total + VA_CREW_spawnHeroPack(id, baseX, baseZ, (ci - 1) * 200)
  end
  for i, id in ipairs(picks) do
    total = total + VA_CREW_spawnHeroPack(id, baseX, baseZ, 400 + (i - 1) * 220)
  end
  -- No free pad M/E storage — Solarium (and bought eco) own that seat.
  -- Mission-only call-ins (Bro's Tzar, etc.) — not permanent company seats.
  local callIns = mission and mission.missionCallIns
  if type(callIns) == "table" then
    for ci, call in ipairs(callIns) do
      if type(call) == "table" then
        local cdef = tostring(call.unitDef or call.unitDefName or "")
        local cid = tostring(call.heroId or call.id or ("callin_" .. tostring(ci)))
        local cname = tostring(call.name or cid)
        if cdef ~= "" and UnitDefNames and UnitDefNames[cdef] then
          local callSpec = {
            unitDefName = cdef,
            count = 1,
            dx = 400 + (#picks + ci) * 220,
            dz = 40,
            spacing = 120,
            heroId = cid,
            heroName = cname,
            missionCritical = false,
            packageTag = "crew_callin_" .. cid,
          }
          total = total + spawnUnitSpec(callSpec, playerTeamID, baseX, baseZ, 0, 0, {}, { role = "player_crew" })
          Spring.Echo("VA_CREW_CALLIN hero=" .. cid .. " def=" .. cdef .. " source=" .. tostring(call.source or ""))
          if SendToUnsynced then
            SendToUnsynced("VERDANCE_BEAT", "bark", "Bro", "Pass me the Tzar — he's rolling.", 5)
          end
        else
          Spring.Echo("VA_CREW_CALLIN_SKIP def=" .. cdef)
        end
      end
    end
  end
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


local function spawnPlayableSetup()
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
        elseif useCrewKit and isPlayer and not spec.reserve and not VA_CREW_isAnchorKeep(spec) then
          -- Heroes come from the sealed hub packet (spawn below). The reserve the player
          -- chose (spec.reserve, Add-ReserveToKit) lands with the company.
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
  if useCrewKit then
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
  do
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
    return owner -- Unassigned cells stay unassigned; do not invent AABB ownership.
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

local function addUnitToBucket(bucket, defID, unitID)
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
    -- Structures always DV; area_control pad rings (Beamers/LLTs/Thistles) too.
    if isStructure(defID) or unitIsPadTooth(unitID) then
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

function VAQ.zoneSamples()
  local buckets = {}
  for _, unitID in ipairs(Spring.GetAllUnits() or {}) do
    local teamID = Spring.GetUnitTeam(unitID)
    if teamID and teamID ~= gaiaTeamID then
      local x, _, z = Spring.GetUnitPosition(unitID)
      local zone = x and zoneForPosition(x, z)
      local defID = Spring.GetUnitDefID(unitID)
      if zone and zone.zoneId and defID then
        local zoneId = tostring(zone.zoneId)
        local bucket = buckets[zoneId]
        if not bucket then
          -- byFactionDv is ownership; av/bp remain pressure/economy axes.
          bucket = { zoneId = zoneId, av = 0, bp = 0, dp = 0, byFactionDv = {} }
          buckets[zoneId] = bucket
        end
        local faction = tostring(teamFaction[teamID] or "neutral"):lower()
        local metal = unitDefMetal(defID)
        local ud = UnitDefs[defID]
        if isBuilder(defID) then bucket.bp = bucket.bp + (tonumber(ud and ud.buildSpeed) or 0) end
        if canFight(defID) then
          if isStructure(defID) or unitIsPadTooth(unitID) then
            bucket.dp = bucket.dp + metal
            bucket.byFactionDv[faction] = (bucket.byFactionDv[faction] or 0) + metal
          else
            bucket.av = bucket.av + metal
          end
        end
      end
    end
  end
  local samples = {}
  for _, bucket in pairs(buckets) do
    -- Territory control = defensive value only (no army/build metal ownership).
    local control, peak = "neutral", 0
    for faction, value in pairs(bucket.byFactionDv or {}) do
      if value > peak then control, peak = faction, value end
    end
    bucket.control, bucket.byFactionDv = control, nil
    samples[#samples + 1] = bucket
  end
  table.sort(samples, function(a, b) return a.zoneId < b.zoneId end)
  return samples
end

function VAQ.transition(reason)
  if not VAQ.kernel then return false, "kernel_unavailable" end
  local frame = Spring.GetGameFrame() or 0
  local target = mission.targetZoneId or (mission.objective and mission.objective.targetZoneId) or ""
  local damage = objectiveTargetCount > 0 and (objectiveTargetsDestroyed / objectiveTargetCount)
    or (objectiveComplete and 1 or 0)
  local requestId = tostring(mission.missionId or "mission") .. "|ch" .. tostring(sortieChapter or 1)
    .. "|f" .. tostring(frame)
  local ok, statusText, journal = VAQ.kernel:transition({
    requestId = requestId,
    contractId = tostring(mission.missionId or "") .. ":" .. tostring(sortieChapter or 1),
    mapId = mission.deploymentMapId,
    targetZoneId = target,
    elapsedMinutes = math.max(0.05, (frame - (VAQ.lastTransitionFrame or 0)) / 1800),
    objectiveDamage = damage,
    zoneFlipped = status == "victory" and objectiveComplete,
    patron = mission.patron or (mission.worldConflict and mission.worldConflict.patron) or "nullmercs",
    against = (mission.worldConflict and mission.worldConflict.primaryEnemy) or "armada",
    pathSignal = mission.pathSignal or "B",
    zoneSamples = VAQ.zoneSamples(),
    reason = reason,
  })
  if ok then
    VAQ.lastTransitionFrame = frame
    local snapshot = VAQ.kernel:snapshot()
    Spring.SetGameRulesParam("va_quantum_transition", snapshot.transitionIndex or 0, { public = true })
    Spring.SetGameRulesParam("va_quantum_clock", snapshot.clockMinutes or 0, { public = true })
    Spring.SetGameRulesParam("va_quantum_hash", snapshot.stateHash or "", { public = true })
    Spring.Echo("VA_QUANTUM_TRANSITION index=" .. tostring(snapshot.transitionIndex)
      .. " clock=" .. tostring(snapshot.clockMinutes) .. " hash=" .. tostring(snapshot.stateHash)
      .. " dispatch=" .. tostring(journal and journal.dispatchId or "none"))
    if SendToUnsynced then
      SendToUnsynced("VERDANCE_MISSION_EVENT", "quantum_transition",
        tostring(snapshot.transitionIndex) .. "|" .. tostring(snapshot.stateHash or ""))
    end
  else
    Spring.Echo("VA_QUANTUM_TRANSITION_SKIP reason=" .. tostring(statusText))
  end
  return ok, statusText
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
  -- Same source of truth as the objective/win system. playerTeamID already IS
  -- the seed's balance.playerTeamID, clamped at load to a team this match has;
  -- re-reading the raw seed here would reintroduce a nonexistent team.
  local playerTeam = playerTeamID

  for _, teamID in ipairs(Spring.GetTeamList()) do
    teamBuckets[teamID] = makeTeamBucket(teamID)
  end

  for teamID, bucket in pairs(teamBuckets) do
    local units = Spring.GetTeamUnits(teamID) or {}
    for _, unitID in ipairs(units) do
      if Spring.ValidUnitID(unitID) and not Spring.GetUnitIsDead(unitID) then
        local defID = Spring.GetUnitDefID(unitID)
        addUnitToBucket(bucket, defID, unitID)
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
            addUnitToBucket(zoneBuckets[zone.zoneId].teams[teamID], defID, unitID)
            vaRecordZonePresence(unitID, zone.zoneId, teamID)
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
  if SendToUnsynced then SendToUnsynced("VERDANCE_TRACK", "telemetry", json) end
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
  -- Emit the occupancy packet in its own right, not only spliced into the dev
  -- sample below. Without this a played mission produces exactly one snapshot (the
  -- one at terminal) and its "timeline" is a single point, while every AI run has
  -- five. Free: telemetryJson() has already been called.
  Spring.Echo("VA_TELEMETRY_JSON_COMPACT " .. base)
  if SendToUnsynced then SendToUnsynced("VERDANCE_TRACK", "telemetry", base) end
  -- strip outer braces to splice fields
  local inner = base
  if inner:sub(1, 1) == "{" then inner = inner:sub(2) end
  if inner:sub(-1) == "}" then inner = inner:sub(1, -2) end
  local playerTeam = playerTeamID
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
    -- Recoil builds differ here: some expose no value for a missing team rule
    -- and the C binding then returns zero Lua values. Calling tonumber(...) on
    -- that result raises "value expected" and aborts the whole GameFrame.
    local okM, rawM = pcall(Spring.GetTeamRulesParam, playerTeam, "metalIncome")
    local okE, rawE = pcall(Spring.GetTeamRulesParam, playerTeam, "energyIncome")
    if okM then mInc = tonumber(rawM) or 0 end
    if okE then eInc = tonumber(rawE) or 0 end
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
  if SendToUnsynced then SendToUnsynced("VERDANCE_TRACK", "devsample", devJson) end
  -- Cumulative crossings ride the dev cadence so a session that never reaches a
  -- terminal -- alt-F4, resign, crash, or simply stopping to make dinner -- still
  -- leaves a usable flow record. setTerminal emits the clean final copy; this is the
  -- one that survives not getting there. Global lookup: vaZoneFlowJson is defined
  -- below this function and only resolves at call time.
  if vaZoneFlowJson then
    local flowJson = vaZoneFlowJson()
    Spring.Echo("VA_ZONE_FLOW_JSON " .. flowJson)
    if SendToUnsynced then SendToUnsynced("VERDANCE_TRACK", "zoneflow", flowJson) end
  end
  resetDevCmdCounts()
  devTel.lastSample = frame
end

-- ============================================================
-- VERDANCE TRANSLATION MATRIX ENGINE
-- Consumes real zoneBuckets, runs Hermitian math, emits packet.
-- ============================================================

-- Tuning constants packed into one gadget-env table (main-chunk local budget).
VA_TRANSLATION = {
  BASE_COUPLING = 0.3,
  BASE_HYDRO_COUPLING = 0.6,
  ENTANGLEMENT_THRESHOLD = 0.1,
  DENSITY_HOTSPOT = 0.8,
  HYDRO_HAZARD_THRESHOLD = 0.4,
}

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
vaZoneFlowTotals = nil      -- "A|B" -> crossings for the whole match (never reset)
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
function vaRecordZonePresence(unitID, zoneId, teamID)
  -- Gaia's wildlife wanders the whole map. On greenest_fields eight critter_gulls
  -- flying laps produced border "crossings" between zones no ground unit can move
  -- between (NE plateau straight to SW bastion). Wildlife is not a front. The
  -- guard lives here rather than in the sampler because telemetryJson walks every
  -- team's units, gaia included, and calls straight into this function.
  if teamID and teamID == gaiaTeamID then return end
  vaUnitZone = vaUnitZone or {}
  local was = vaUnitZone[unitID]
  vaUnitZone[unitID] = zoneId
  if was and zoneId and was ~= zoneId then
    vaZoneFlow = vaZoneFlow or {}
    local key = (was < zoneId) and (was .. "|" .. zoneId) or (zoneId .. "|" .. was)
    vaZoneFlow[key] = (vaZoneFlow[key] or 0) + 1
    vaZoneFlowTotals = vaZoneFlowTotals or {}
    local row = vaZoneFlowTotals[key]
    if not row then
      row = { total = 0, byTeam = {} }
      vaZoneFlowTotals[key] = row
    end
    row.total = row.total + 1
    if teamID then row.byTeam[teamID] = (row.byTeam[teamID] or 0) + 1 end
  end
end

-- vaRecordZonePresence only ever ran from inside telemetryJson, which fires at
-- export milestones. Sampling a unit's zone five times in eight minutes cannot
-- observe a border crossing, so vaZoneFlow -- the live half of "entanglement" --
-- was always ~0 and every front read as uncoupled no matter how hard the armies
-- were actually moving. Sample on its own clock instead. Globals, not locals:
-- this file is already against Lua 5.1's 200-local ceiling.
vaZoneFlowSample = 0
function vaSampleZoneFlow()
  local units = Spring.GetAllUnits()
  if not units then return end
  for i = 1, #units do
    local unitID = units[i]
    local teamID = Spring.GetUnitTeam(unitID)
    -- Gaia's wildlife wanders the whole map. On greenest_fields the first pass of
    -- this sampler measured eight critter_gulls flying laps and reported it as
    -- army traffic between zones. Wildlife is not a front.
    if teamID and teamID ~= gaiaTeamID then
      local x, _, z = Spring.GetUnitPosition(unitID)
      if x then
        local zone = zoneForPosition(x, z)
        if zone and zone.zoneId then
          vaRecordZonePresence(unitID, zone.zoneId, teamID)
        end
      end
    end
  end
end

-- Cumulative border traffic for the whole match, so an offline analysis can see
-- which zones actually feed each other. vaZoneFlow itself is reset after every
-- translation packet (it means "crossings since the last packet"); this is not.
function vaZoneFlowJson()
  local parts = {}
  for key, row in pairs(vaZoneFlowTotals or {}) do
    local a, b = key:match("^(.-)|(.*)$")
    if a and b then
      local teamParts = {}
      for teamID, count in pairs(row.byTeam or {}) do
        teamParts[#teamParts + 1] = '{"team":' .. jnum(teamID) .. ',"crossings":' .. jnum(count) .. '}'
      end
      parts[#parts + 1] = '{"from":' .. jstr(a) .. ',"to":' .. jstr(b)
        .. ',"crossings":' .. jnum(row.total or 0)
        .. ',"byTeam":[' .. table.concat(teamParts, ",") .. ']}'
    end
  end
  return '{"frame":' .. jnum(Spring.GetGameFrame() or 0)
    .. ',"sampleEvery":' .. jnum(vaZoneFlowSample or 0)
    .. ',"edges":[' .. table.concat(parts, ",") .. ']}'
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

function vaBeginWaterline(target, seconds)
  local to = math.max(0, math.min(1, tonumber(target) or 0))
  local span = math.max(1, math.floor((tonumber(seconds) or 20) * 30 / VA_WATER_TICK))
  vaWaterTarget = to
  vaWaterStep = (to - vaWaterLevel) / span
  Spring.Echo(string.format("VA_HYDRO_BEGIN from=%.3f to=%.3f seconds=%s",
    vaWaterLevel, to, tostring(seconds)))
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
        local c = VA_TRANSLATION.BASE_COUPLING * borderShare * (0.65 * pressure + 0.35 * crossing)
        matrix[i][j] = c
        matrix[j][i] = c
      end
    end
    -- Step 3: Hydrological coupling -- how much of this zone the current
    -- waterline actually takes, measured from its own flood curve.
    local wet = vaZoneSubmerged(zoneMap.zones[i], rho_H)
    local hc = VA_TRANSLATION.BASE_HYDRO_COUPLING * wet
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
      if coupling > VA_TRANSLATION.ENTANGLEMENT_THRESHOLD then
        table.insert(packet.entanglements, {
          zoneIds  = { zones[i].zoneId, zones[j].zoneId },
          names    = { zones[i].name, zones[j].name },
          coupling = tonumber(string.format("%.3f", coupling)),
        })
      end
    end
  end

  for _, node in ipairs(packet.nodes) do
    if node.type == "low-flood" and node.hydroCoupling > VA_TRANSLATION.HYDRO_HAZARD_THRESHOLD then
      table.insert(packet.factoids, {
        type    = "HAZARD",
        zoneId  = node.zoneId,
        message = node.name .. " is critically exposed to current hydrology levels.",
      })
    end
    if node.density > VA_TRANSLATION.DENSITY_HOTSPOT then
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
              addUnitToBucket(zoneBucketsLive[zone.zoneId].teams[teamID], defID, unitID)
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

-- How a kind resolves (see VA_KINDS). Gadget-env global: resultJson / setup echo call it.
function vaObjectiveMode(kind)
  kind = tostring(kind or "")
  if VA_KINDS.capture[kind] then return "capture" end
  if VA_KINDS.survive[kind] then return "presence" end
  if VA_KINDS.fortify[kind] then return "fortify" end
  if VA_KINDS.choice[kind] then return "targets_choice" end
  if kind == "eco_raid" then return "targets_raid" end
  return "targets_all"
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

-- Exfil is a pad on the zone anchor, the same point the marker uses.
-- A shrunk bounding-box center can sit in the river while the marker the
-- player flies to is the dry anchor, so the pad scan never sees them.
-- (padRadius lives on the extractLoop table declared at the top of the file.)
extractLoop.applyPad = function(zoneId)
  extractionZoneRect = nil
  if not zoneId then return end
  local sx = Game.mapSizeX or 0
  local sz = Game.mapSizeZ or 0
  local cx, cz
  if zoneMap and type(zoneMap.zones) == "table" then
    for _, z in ipairs(zoneMap.zones) do
      if z.zoneId == zoneId then
        local a = z.anchor
        if type(a) == "table" and tonumber(a.x) and tonumber(a.z) then
          cx = normalizedToElmos(tonumber(a.x), sx)
          cz = normalizedToElmos(tonumber(a.z), sz)
        end
        break
      end
    end
  end
  if not cx then
    local rect = zoneRectFor(zoneId)
    if not rect then return end
    cx = (rect[1] + rect[3]) * 0.5
    cz = (rect[2] + rect[4]) * 0.5
  end
  local r = extractLoop.padRadius
  extractionZoneRect = { cx - r, cz - r, cx + r, cz + r }
  -- va_pad_x/z/r are published by game_verdance_exfil.lua (the pad authority); this is the
  -- same anchor, so readers use padPoint() below.
end

-- The pad point as the HUD sees it; falls back to our own rect while the exfil gadget boots.
function VA_padPoint()
  local px = tonumber((Spring.GetGameRulesParam("va_pad_x"))) or -1
  local pz = tonumber((Spring.GetGameRulesParam("va_pad_z"))) or -1
  if px >= 0 and pz >= 0 then return px, pz end
  if extractionZoneRect then
    return (extractionZoneRect[1] + extractionZoneRect[3]) * 0.5, (extractionZoneRect[2] + extractionZoneRect[4]) * 0.5
  end
  return nil, nil
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

-- Same constraint as player infil: reinforcements enter from the map rim, never
-- pop in midfield next to the fight. Anchor toward the destination, then pick
-- the nearest walkable border point (shared geometry with VAQ.entryFor).
function VAQ.responseDefs(teamID)
  if tostring(teamFaction[teamID] or ""):lower() == "armada" then
    return { "armdecom", "armflea", "armflea", "armflea", "armflea",
      "armpw", "armpw", "armpw", "armpw", "corthud", "corthud" }
  end
  local defs = {}
  for _, name in ipairs(teamCombatDefNames(teamID)) do
    local ud = UnitDefNames[name]
    local cp = ud and ud.customParams or {}
    if ud and not ud.isBuilder and not cp.iscommander and not cp.isdecoycommander
        and not cp.decoyfor and not name:find("decom", 1, true) then
      defs[#defs + 1] = name
    end
  end
  return defs
end

-- Where the enemy sends its answer: the zone it BELIEVES we are in (what it has seen of us,
-- recency faded — game_verdance_belief_observe.lua), not our true centroid. If it has seen
-- nothing, it goes to where we were last known: the pad.
function enemyResponseTarget()
  if GG and GG.VA_EnemyBelievedZone then
    local zid, ax, az = GG.VA_EnemyBelievedZone()
    if zid and ax and az then return ax, az, zid end
  end
  local px = tonumber((Spring.GetGameRulesParam("va_pad_x"))) or -1
  local pz = tonumber((Spring.GetGameRulesParam("va_pad_z"))) or -1
  if px >= 0 and pz >= 0 then return px, pz, "pad" end
  local cx, cz = teamUnitCentroid(playerTeamID)
  return cx, cz, "centroid"
end

local function spawnWave(fromTeamID, count, targetX, targetZ, label)
  if not fromTeamID or count < 1 then return 0 end
  -- Vivarium: reinforcements come from somewhere that exists. A team with nothing left on
  -- this map (its base gone, or never placed because the ground is vacant) sends no one;
  -- the Mercs answer a call the player makes, so they are exempt.
  if fromTeamID ~= mercTeamID and (Spring.GetTeamUnitCount(fromTeamID) or 0) == 0 then
    Spring.Echo("VA_WAVE_SKIPPED team=" .. tostring(fromTeamID) .. " kind=" .. tostring(label) .. " reason=nobody_on_the_map")
    return 0
  end
  -- Every pressure producer shares one response budget per credited chapter.
  -- Neither regrowth nor objective completion may add another commander pack.
  if VAQ.responseChapter == sortieChapter then return 0 end
  local defs = VAQ.responseDefs(fromTeamID)
  if #defs == 0 then return 0 end
  local cx, cz = VAQ.entryFor({ destinationZoneId = mission.objective.targetZoneId }, defs)
  if not cx then return 0 end
  local spawned = 0
  for i, defName in ipairs(defs) do
    local x = cx + ((i - 1) % 3 - 1) * 48
    local z = cz + math.floor((i - 1) / 3) * 48
    if VAQ.hiddenFromPlayer(x, z) and VAQ.playerDistanceOk(x, z) then
      local uID = Spring.CreateUnit(defName, x, Spring.GetGroundHeight(x, z), z, 0, fromTeamID)
      if uID then
        spawned = spawned + 1
        if targetX and targetZ and CMD and CMD.FIGHT then
          Spring.GiveOrderToUnit(uID, CMD.FIGHT, { targetX, Spring.GetGroundHeight(targetX, targetZ), targetZ }, {})
        end
      end
    end
  end
  if spawned > 0 then
    VAQ.responseChapter = sortieChapter
    Spring.Echo("VA_WAVE_SPAWNED team=" .. tostring(fromTeamID) .. " count=" .. spawned
      .. " kind=" .. tostring(label or "reinforce") .. " rim=1")
    if SendToUnsynced then
      SendToUnsynced("VERDANCE_BEAT", "wave_warning", cx, Spring.GetGroundHeight(cx, cz), cz,
        "Enemy response approaching from the map edge")
    end
  end
  return spawned
end

function VAQ.teamForFaction(faction)
  faction = tostring(faction or ""):lower()
  for teamID, value in pairs(teamFaction) do
    if tostring(value or ""):lower() == faction then return teamID end
  end
  if objectiveTeamID and faction ~= "nullmercs" and faction ~= "ashwalkers" then return objectiveTeamID end
  return nil
end

function VAQ.playerDistanceOk(x, z)
  for _, team in ipairs(Spring.GetTeamList() or {}) do
    if team == playerTeamID or Spring.AreTeamsAllied(playerTeamID, team) then
      for _, unitID in ipairs(Spring.GetTeamUnits(team) or {}) do
        local ux, _, uz = Spring.GetUnitPosition(unitID)
        if ux then
          local dx, dz = ux - x, uz - z
          if dx * dx + dz * dz < 2200 * 2200 then return false end
        end
      end
    end
  end
  return true
end

function VAQ.hiddenFromPlayer(x, z)
  local y = Spring.GetGroundHeight(x, z)
  local ok, any, los, radar = pcall(Spring.GetPositionLosState, x, y, z, playerAllyTeamID)
  if not ok then return false end
  return not (any or los or radar)
end

function VAQ.entryFor(arrival, defs)
  local margin, candidates = 192, {}
  local sx, sz = Game.mapSizeX or 1, Game.mapSizeZ or 1
  for i = 1, 8 do
    local t = i / 9
    candidates[#candidates + 1] = { x = margin, z = t * sz }
    candidates[#candidates + 1] = { x = sx - margin, z = t * sz }
    candidates[#candidates + 1] = { x = t * sx, z = margin }
    candidates[#candidates + 1] = { x = t * sx, z = sz - margin }
  end
  local snapshot = VAQ.kernel and VAQ.kernel:snapshot() or nil
  local zone = snapshot and snapshot.zones and snapshot.zones[arrival.destinationZoneId]
  local anchor = zone and zone.anchor or { x = 0.5, z = 0.5 }
  local ax, az = (tonumber(anchor.x) or 0.5) * sx, (tonumber(anchor.z) or 0.5) * sz
  table.sort(candidates, function(a, b)
    local adx, adz, bdx, bdz = a.x - ax, a.z - az, b.x - ax, b.z - az
    local da, db = adx * adx + adz * adz, bdx * bdx + bdz * bdz
    if da == db then return (a.x + a.z) < (b.x + b.z) end
    return da < db
  end)
  for _, pos in ipairs(candidates) do
    local y = Spring.GetGroundHeight(pos.x, pos.z)
    local valid = VAQ.hiddenFromPlayer(pos.x, pos.z) and VAQ.playerDistanceOk(pos.x, pos.z)
    if valid then
      for i, defName in ipairs(defs) do
        local def = UnitDefNames[defName]
        local ux, uz = pos.x + ((i - 1) % 3 - 1) * 48, pos.z + math.floor((i - 1) / 3) * 48
        if not def or not VAQ.hiddenFromPlayer(ux, uz) or not VAQ.playerDistanceOk(ux, uz)
            or not Spring.TestMoveOrder(def.id, ux, Spring.GetGroundHeight(ux, uz), uz, 0, 0, 0, true, true, true) then
          valid = false
          break
        end
      end
    end
    if valid then return pos.x, pos.z end
  end
  return nil
end

function VAQ.spawnArrival(arrival, frame)
  local teamID = VAQ.teamForFaction(arrival.faction)
  if not teamID then return false, "no_faction_team" end
  if VAQ.responseChapter == sortieChapter then return false, "chapter_response_already_arrived" end
  local defs = VAQ.responseDefs(teamID)
  if #defs == 0 then return false, "no_mobile_recipe" end
  local x, z = VAQ.entryFor(arrival, defs)
  if not x then return false, "no_hidden_ingress" end
  local count = #defs
  local targetRect = zoneRectFor(arrival.destinationZoneId)
  local tx, tz = x, z
  if targetRect then
    tx = (targetRect[1] + targetRect[3]) * 0.5
    tz = (targetRect[2] + targetRect[4]) * 0.5
  end
  local spawned = 0
  for i = 1, count do
    local defName = defs[((i - 1) % #defs) + 1]
    local offset = (i - 1) * 48
    local ux = math.max(32, math.min((Game.mapSizeX or 64) - 32, x + (((i - 1) % 3) - 1) * 48))
    local uz = math.max(32, math.min((Game.mapSizeZ or 64) - 32, z + math.floor((i - 1) / 3) * 48))
    if VAQ.hiddenFromPlayer(ux, uz) and VAQ.playerDistanceOk(ux, uz) then
      local unitID = Spring.CreateUnit(defName, ux, Spring.GetGroundHeight(ux, uz), uz, 0, teamID)
      if unitID then
        spawned = spawned + 1
        Spring.SetUnitRulesParam(unitID, "va_quantum_transit", tostring(arrival.id), { public = true })
        Spring.SetUnitRulesParam(unitID, "va_source_zone", tostring(arrival.sourceZoneId), { public = true })
        if CMD and CMD.FIGHT then
          Spring.GiveOrderToUnit(unitID, CMD.FIGHT,
            { tx, Spring.GetGroundHeight(tx, tz), tz }, {})
        end
      end
    end
  end
  if spawned <= 0 then return false, "formation_became_visible" end
  VAQ.responseChapter = sortieChapter
  VAQ.kernel:ackArrival(arrival.id, arrival.mass, VAQ.kernel:snapshot().clockMinutes
    + (frame - VAQ.lastTransitionFrame) / 1800)
  Spring.SetGameRulesParam("va_reinforcement_entry_x", math.floor(x), { public = true })
  Spring.SetGameRulesParam("va_reinforcement_entry_z", math.floor(z), { public = true })
  Spring.SetGameRulesParam("va_reinforcement_source", tostring(arrival.sourceZoneId), { public = true })
  Spring.Echo("VA_QUANTUM_ARRIVAL id=" .. tostring(arrival.id)
    .. " source=" .. tostring(arrival.sourceZoneId)
    .. " destination=" .. tostring(arrival.destinationZoneId)
    .. " spawned=" .. tostring(spawned) .. " x=" .. math.floor(x) .. " z=" .. math.floor(z))
  if SendToUnsynced then
    SendToUnsynced("VERDANCE_BEAT", "wave_warning", x, Spring.GetGroundHeight(x, z), z,
      "reinforcements from " .. tostring(arrival.sourceZoneId))
  end
  return true, "arrived"
end

function VAQ.processArrivals(frame)
  if not VAQ.kernel or terminal or status ~= "active" then return end
  local snapshot = VAQ.kernel:snapshot()
  local now = (tonumber(snapshot.clockMinutes) or 0) + (frame - (VAQ.lastTransitionFrame or 0)) / 1800
  for _, arrival in ipairs(VAQ.kernel:dueArrivals(now, currentMapId and currentMapId() or mission.deploymentMapId)) do
    local ok, reason = VAQ.spawnArrival(arrival, frame)
    if not ok then
      VAQ.kernel:deferArrival(arrival.id, now + (300 / 1800), reason)
      Spring.SetGameRulesParam("va_reinforcement_deferred", 1, { public = true })
      Spring.Echo("VA_QUANTUM_ARRIVAL_DEFER id=" .. tostring(arrival.id) .. " reason=" .. tostring(reason))
    end
  end
end

-- ============================================================
-- Named hero lifecycle (Fire Emblem doctrine).
-- alive -> down_pending_wreck -> down (wreck tracked) -> recovered | lost.
-- BAR's own gadgets guarantee the primitives: corpses link to their source
-- unit (unit_corpse_link.lua) and resurrection fires UnitCreated with the
-- rez bot as builder while the corpse still exists (unit_resurrected.lua).
--
-- Downed heroes share the marks registry (kind=hero_recover) with vault marks.
-- ============================================================

setTerminal = nil  -- forward: a lost critical hero ends the mission (gadget-env; local budget)

function registerHeroDownObjective(rec)
  local sid = MarksLib.upsertHeroRecover(marks, rec)
  if not sid then return end
  marksCommit("secondary_changed", sid)
end

function resolveHeroDownObjective(rec, outcome)
  local g, newly = MarksLib.completeHeroRecover(marks, rec, outcome)
  local sid = rec and (rec.secondaryId or ("hero_down_" .. tostring(rec.id))) or ""
  if newly and outcome == "lost" then
    marksCommit("secondary_failed", sid)
  elseif newly then
    marksCommit("secondary_complete", sid)
  else
    marksCommit("secondary_changed", sid)
  end
  return g, newly
end

function broadcastHeroEvent(event, rec, x, z)
  Spring.Echo("VA_HERO_" .. string.upper(event) .. " id=" .. rec.id .. " critical=" .. tostring(rec.missionCritical))
  publishHeroRules()
  if SendToUnsynced then
    SendToUnsynced("VERDANCE_HERO_EVENT", event, rec.id, rec.name, rec.missionCritical and 1 or 0, x or 0, z or 0)
  end
end

-- One fail path: latch → publish. The player decides when to lift (manifest);
-- there is no extract loop to open.
function failRescueContract(rec, how)
  if rescueContractFailed then return false end
  if not rec or not rec.wasFieldRecruit or rec.recruited then return false end
  if rec.sortieLinked ~= true then return false end
  rescueContractFailed = true
  rescueContractFailReason = tostring(how or "wreck_destroyed")
  rescueContractFailHero = tostring(rec.id or "")
  -- SoT for HUD / playfeel / result JSON. Do NOT set objectiveBypassed —
  -- bypass is hive_clear_or_bypass only; fail is its own latch.
  Spring.SetGameRulesParam("va_objective_failed", 1, { public = true })
  Spring.SetGameRulesParam("va_objective_fail_reason", rescueContractFailReason, { public = true })
  Spring.SetGameRulesParam("va_objective_fail_hero", rescueContractFailHero, { public = true })
  Spring.Echo("VA_OBJECTIVE_FAILED reason=" .. rescueContractFailReason
    .. " hero=" .. rescueContractFailHero
    .. " name=" .. tostring(rec.name or ""))
  if SendToUnsynced then
    SendToUnsynced("VERDANCE_MISSION_EVENT", "objective_failed", rescueContractFailReason)
  end
  return true
end

function heroLost(rec, how)
  -- WO-008: named loss never hard-defeats. Contracted field recruit →
  -- failRescueContract (partial EXTRACT). Company heroes: bookkeeping only.
  if rec.state == "lost" then return end
  rec.state = "lost"
  rec.diedHow = tostring(how or "")
  resolveHeroDownObjective(rec, "lost")
  -- Latch before lost broadcast so HUD sees va_objective_failed and skips
  -- a second rescue bark (objective_failed event owns that copy).
  failRescueContract(rec, how)
  broadcastHeroEvent("lost", rec, rec.deathX, rec.deathZ)
  Spring.Echo("VA_NAMED_DEAD " .. rec.id .. " cause=" .. tostring(how or "unknown")
    .. " critical=" .. tostring(rec.missionCritical == true)
    .. " linked=" .. tostring(rec.sortieLinked == true))
  -- Intentionally no setTerminal("defeat", "hero_lost_*") — DCO-01 wreck rule.
end

function heroRecovered(rec, newUnitID)
  rec.state = "alive"
  rec.unitID = newUnitID
  rec.rezGraceUntil = nil
  heroByUnitID[newUnitID] = rec.id
  Spring.SetUnitRulesParam(newUnitID, "va_hero", 1, { public = true })
  Spring.SetUnitRulesParam(newUnitID, "va_hero_id", rec.id, { public = true })
  Spring.SetUnitRulesParam(newUnitID, "va_hero_name", rec.name, { public = true })
  Spring.SetUnitRulesParam(newUnitID, "va_hero_critical", rec.missionCritical and 1 or 0, { public = true })
  Spring.SetUnitRulesParam(newUnitID, "va_hero_level", rec.level or 1, { public = true })
  Spring.SetUnitRulesParam(newUnitID, "va_hero_rank", HeroTags.normalizeRank(rec.rank or "Green"), { public = true })
  stampPadToothIfNeeded(newUnitID, rec.id)
  -- BAR's unit_resurrected gadget restores experience and heals the fresh
  -- instance; only the hero toughness multiplier needs re-applying.
  applyHeroModifiers(newUnitID, rec)
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
  -- Peak XP is stamped after toughness — refresh vet curve so HP/RoF match kept XP.
  if GG and GG.VA_VetRefresh then
    pcall(GG.VA_VetRefresh, newUnitID)
  end
  local x, _, z = Spring.GetUnitPosition(newUnitID)
  resolveHeroDownObjective(rec, "recovered")
  broadcastHeroEvent("recovered", rec, x, z)
  Spring.Echo("VA_NAMED_RECOVERED " .. rec.id .. " unit=" .. tostring(newUnitID) .. " xp=" .. tostring(keep))
end

function heroOnUnitDestroyed(unitID)
  local id = heroByUnitID[unitID]
  if not id then return end
  local rec = heroes[id]
  heroByUnitID[unitID] = nil
  rec.unitID = nil
  -- Chassis promote destroys the proxy constructor without a rescue contract.
  if rec.promotingChassis then
    return
  end
  if Spring.GetUnitExperience then
    local cur = Spring.GetUnitExperience(unitID) or 0
    rec.lastXp = cur
    rec.peakXp = math.max(tonumber(rec.peakXp) or 0, cur)
  end
  -- Capture unitDef at death so rez matching still works if the seed omitted it.
  -- Never overwrite a real hero chassis with a wreck-seed proxy def.
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

function heroOnFeatureCreated(featureID, allyTeamID, sourceID)
  if not next(heroPendingWreck) then return end
  if not sourceID and GG and GG.GetCorpsePriorUnitID then
    -- Older engine path: BAR's corpse-link registry backfills the source unit.
    sourceID = GG.GetCorpsePriorUnitID(featureID)
  end
  local id = sourceID and heroPendingWreck[sourceID]
  if not id then
    -- No source link (seen with a Halberd hovertank): take the corpse of the hero's chassis
    -- that appears where they fell.
    local fx, _, fz = Spring.GetFeaturePosition(featureID)
    local fdef = Spring.GetFeatureDefID and FeatureDefs[Spring.GetFeatureDefID(featureID) or -1]
    local fname = fdef and fdef.name or ""
    if fx then
      for deadUnitID, hid in pairs(heroPendingWreck) do
        local r = heroes[hid]
        local chassis = r and tostring(r.unitDefName or "") or ""
        local dx, dz = fx - (r and r.deathX or fx), fz - (r and r.deathZ or fz)
        if chassis ~= "" and fname:sub(1, #chassis) == chassis and dx * dx + dz * dz <= 300 * 300 then
          id, sourceID = hid, deadUnitID
          Spring.Echo("VA_HERO_WRECK_BY_POSITION id=" .. hid .. " feature=" .. tostring(featureID) .. " def=" .. fname)
          break
        end
      end
    end
  end
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
  -- Same objective ledger for seeded field wrecks and mid-fight company downs.
  registerHeroDownObjective(rec)
  broadcastHeroEvent("down", rec, x or rec.deathX, z or rec.deathZ)
end

-- IIFE: nested locals do not count toward main-chunk 200-local limit.
WorkerFeature = (function()
  local ok, mod = pcall(VFS.Include, "luarules/gadgets/include/va_worker_feature.lua")
  if ok and type(mod) == "table" then return mod end
  return nil
end)()

function resolveWorkerFeatureID(builderID)
  if WorkerFeature and WorkerFeature.featureIDFromResurrect then
    return WorkerFeature.featureIDFromResurrect(builderID)
  end
  if not builderID or not Spring.GetUnitWorkerTask then return nil end
  local cmdID, targetID = Spring.GetUnitWorkerTask(builderID)
  if cmdID ~= CMD.RESURRECT or not targetID then return nil end
  local featureID = targetID
  if not (Engine and Engine.FeatureSupport and Engine.FeatureSupport.noOffsetForFeatureID) then
    featureID = featureID - Game.maxUnits
  end
  return featureID
end

function builderCanResurrect(builderID)
  if not builderID then return false end
  local dID = Spring.GetUnitDefID(builderID)
  local ud = dID and UnitDefs[dID]
  return ud and ud.canResurrect == true
end

-- Match a freshly created unit back to a downed hero (feature id, def+position).
-- A hero can come back by rez while down, in rez grace, waiting for the wreck, or "lost" only
-- because the wreck never linked (no_wreck): the corpse may still be lying there.
function heroRezzable(rec)
  local st = rec and rec.state
  return st == "down" or st == "rez_grace" or st == "down_pending_wreck" or (st == "lost" and rec.diedHow == "no_wreck")
end

function findHeroForResurrection(unitID, unitDefID, builderID)
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
    if heroRezzable(rec) then
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

function heroOnUnitCreated(unitID, unitDefID, unitTeam, builderID)
  -- Need either a live wreck map or a hero in rez grace / pending.
  local anyDown = next(heroByFeatureID) ~= nil
  if not anyDown then
    for _, rec in pairs(heroes) do
      if heroRezzable(rec) then
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
    -- Field recruit: wreck+rez (or stash retrieve) by the player signs them on.
    tryRecruitFieldHero(rec, unitID, "wreck_rez")
  else
    heroLost(rec, "captured")
  end
end

-- If the wreck corpse was a mobile proxy (geo/fusion/nano/airpad seeds), swap
-- the rezzed constructor into the real hero chassis once they join.
local function promoteFieldRecruitChassis(rec, unitID)
  if not rec or not unitID or not Spring.ValidUnitID(unitID) then return unitID end
  if not rec.needsChassisPromote then return unitID end
  local want = tostring(rec.unitDefName or "")
  if want == "" or not UnitDefNames or not UnitDefNames[want] then
    rec.needsChassisPromote = false
    return unitID
  end
  local curDefID = Spring.GetUnitDefID and Spring.GetUnitDefID(unitID)
  local cur = curDefID and UnitDefs[curDefID]
  local curName = cur and cur.name or ""
  if curName == want then
    rec.needsChassisPromote = false
    return unitID
  end
  local x, y, z = Spring.GetUnitPosition(unitID)
  local team = Spring.GetUnitTeam(unitID) or playerTeamID
  local facing = (Spring.GetUnitBuildFacing and Spring.GetUnitBuildFacing(unitID)) or 0
  local xp = 0
  if Spring.GetUnitExperience then xp = Spring.GetUnitExperience(unitID) or 0 end
  rec.promotingChassis = true
  heroByUnitID[unitID] = nil
  Spring.DestroyUnit(unitID, false, true) -- reclaimed → no wreck
  rec.promotingChassis = false
  local fresh = Spring.CreateUnit(want, x, y or 0, z, facing, team)
  if not fresh then
    Spring.Echo("VA_FIELD_RECRUIT_PROMOTE_FAIL id=" .. tostring(rec.id)
      .. " want=" .. want .. " from=" .. tostring(curName))
    rec.needsChassisPromote = false
    return nil
  end
  rec.needsChassisPromote = false
  rec.wreckSeedDef = nil
  heroRecovered(rec, fresh)
  if Spring.SetUnitExperience and xp > 0 then
    pcall(Spring.SetUnitExperience, fresh, math.max(xp, tonumber(rec.peakXp) or 0))
  end
  Spring.Echo("VA_FIELD_RECRUIT_PROMOTE id=" .. tostring(rec.id)
    .. " from=" .. tostring(curName) .. " to=" .. want .. " unit=" .. tostring(fresh))
  return fresh
end

-- Sign a wild / mission-join hero onto the company. Used by wreck+rez,
-- decoy capture (UnitGiven), and assist_fortify on zone secure.
function publishRecruitedHeroIds()
  local parts = {}
  for _, id in ipairs(VA_FIELD_RECRUIT.recruited or {}) do
    if id and tostring(id) ~= "" then parts[#parts + 1] = tostring(id) end
  end
  -- Sticky across soft-continue + gadget auto-reload (Lua tables reset on reload).
  Spring.SetGameRulesParam("va_recruited_heroes", table.concat(parts, ","), { public = true })
  Spring.SetGameRulesParam("va_recruited_count", #parts, { public = true })
end

function restoreRecruitedHeroIdsFromRules()
  local raw = tostring((Spring.GetGameRulesParam("va_recruited_heroes")) or "")
  if raw == "" or raw == "0" then return 0 end
  local n = 0
  VA_FIELD_RECRUIT.recruited = VA_FIELD_RECRUIT.recruited or {}
  for id in string.gmatch(raw, "[^,]+") do
    id = tostring(id or ""):match("^%s*(.-)%s*$") or ""
    if id ~= "" then
      local seen = false
      for _, x in ipairs(VA_FIELD_RECRUIT.recruited) do
        if x == id then seen = true; break end
      end
      if not seen then
        VA_FIELD_RECRUIT.recruited[#VA_FIELD_RECRUIT.recruited + 1] = id
        n = n + 1
      end
      local rec = heroes[id]
      if rec then
        rec.recruited = true
        rec.recruitable = false
        rec.wasFieldRecruit = true
      end
    end
  end
  if n > 0 then
    Spring.Echo("VA_FIELD_RECRUIT_RESTORE count=" .. tostring(#VA_FIELD_RECRUIT.recruited)
      .. " from_rules=" .. raw)
  end
  return n
end

function tryRecruitFieldHero(rec, unitID, reason)
  if not rec or not rec.recruitable or rec.recruited then return false end
  unitID = promoteFieldRecruitChassis(rec, unitID) or unitID
  rec.recruited = true
  rec.recruitable = false
  rec.recruitReason = tostring(reason or rec.recruitMode or "wreck_rez")
  VA_FIELD_RECRUIT.recruited[#VA_FIELD_RECRUIT.recruited + 1] = rec.id
  publishRecruitedHeroIds()
  if unitID and Spring.ValidUnitID(unitID) then
    Spring.SetUnitRulesParam(unitID, "va_recruitable", 0, { public = true })
    Spring.SetUnitRulesParam(unitID, "va_recruited", 1, { public = true })
    Spring.SetUnitRulesParam(unitID, "va_force_role", "field_join", { public = true })
    Spring.SetUnitRulesParam(unitID, "va_recruit_reason", rec.recruitReason, { public = true })
  end
  local rx, rz = 0, 0
  if unitID and Spring.ValidUnitID(unitID) then
    rx, _, rz = Spring.GetUnitPosition(unitID)
  end
  -- Pull the bound bay/lab onto the company (capture already may have done this).
  claimFieldFactoriesForHero(rec.id, rx, rz)
  resolveHeroDownObjective(rec, "recruited")
  broadcastHeroEvent("recruited", rec, rx, rz)
  Spring.Echo("VA_FIELD_RECRUITED id=" .. tostring(rec.id)
    .. " unit=" .. tostring(unitID)
    .. " reason=" .. tostring(rec.recruitReason))
  if SendToUnsynced then
    SendToUnsynced("VERDANCE_BEAT", "field_recruit", tostring(rec.id), tostring(rec.name or rec.id), 0, 0)
  end
  return true
end

-- Factory structure captured or rezzed onto the player team.
function maybeFieldFactoryJoin(unitID, unitDefID, unitTeam, builderID)
  if unitTeam ~= playerTeamID or not unitID then return end
  local forHero = Spring.GetUnitRulesParam(unitID, "va_field_factory_for")
  -- Rez: builder was working a stamped Legion bay wreck.
  if (not forHero or tostring(forHero) == "") and builderID then
    local featureID = resolveWorkerFeatureID(builderID)
    if featureID and VA_FIELD_RECRUIT.fabByFeature[featureID] then
      forHero = VA_FIELD_RECRUIT.fabByFeature[featureID]
      VA_FIELD_RECRUIT.fabByFeature[featureID] = nil
    end
  end
  if forHero and tostring(forHero) ~= "" then
    Spring.SetUnitRulesParam(unitID, "va_field_factory_for", tostring(forHero), { public = true })
    enableFieldFactoryPrinter(unitID, tostring(forHero))
    Spring.Echo("VA_FIELD_FACTORY_OWNED hero=" .. tostring(forHero) .. " unit=" .. tostring(unitID))
    return
  end
  -- Fallback: structure def → bound field hero (rez lost the feature link).
  local ud = unitDefID and UnitDefs[unitDefID]
  local defName = ud and ud.name
  if not defName then return end
  local roster = VA_CREW_loadRoster()
  if not roster.FACTORIES then return end
  for _, fab in pairs(roster.FACTORIES) do
    if fab and tostring(fab.structureDef or "") == defName and fab.boundHero then
      local hid = tostring(fab.boundHero)
      local rec = heroes[hid]
      if rec and (rec.wasFieldRecruit or rec.recruitable or rec.recruited) then
        Spring.SetUnitRulesParam(unitID, "va_field_factory_for", hid, { public = true })
        enableFieldFactoryPrinter(unitID, hid)
        Spring.Echo("VA_FIELD_FACTORY_REZ hero=" .. hid .. " unit=" .. tostring(unitID))
        return
      end
    end
  end
end

-- Decoy commanders (and any cancapture builder) convert via Capture.
-- When a recruitable hero unit is Given to the player, that is a join.
function heroOnUnitGiven(unitID, unitDefID, newTeam, oldTeam)
  if newTeam ~= playerTeamID then return end
  maybeFieldFactoryJoin(unitID, unitDefID, newTeam, nil)
  local id = heroByUnitID[unitID]
  if not id then return end
  local rec = heroes[id]
  if not rec then return end
  -- Capture is the standard conversion path (armdecom cancapture=true).
  if tryRecruitFieldHero(rec, unitID, "capture") then
    -- Ensure they sit on the player force role after the transfer.
    if Spring.ValidUnitID(unitID) then
      Spring.SetUnitRulesParam(unitID, "va_force_role", "field_join", { public = true })
    end
  end
end

-- After fortify / secure: assist_fortify recruits who are still alive join.
function recruitAssistFortifyOnSecure()
  for _, rec in pairs(heroes) do
    if rec and rec.recruitable and not rec.recruited then
      local mode = tostring(rec.recruitMode or "")
      if mode == "assist_fortify" or mode == "mission_assist" then
        local uid = rec.unitID
        if uid and Spring.ValidUnitID(uid) and not Spring.GetUnitIsDead(uid) then
          -- Pull them onto the player team if they were still wild/NPC.
          local team = Spring.GetUnitTeam(uid)
          if team and team ~= playerTeamID and Spring.TransferUnit then
            pcall(Spring.TransferUnit, uid, playerTeamID, false)
          end
          tryRecruitFieldHero(rec, uid, "assist_fortify")
        end
      end
    end
  end
end

function rezBuilderWorkingFeature(featureID)
  if not featureID or not playerTeamID or not Spring.GetTeamUnits then return false end
  local units = Spring.GetTeamUnits(playerTeamID) or {}
  for i = 1, #units do
    local uid = units[i]
    if uid and builderCanResurrect(uid) then
      local fid = resolveWorkerFeatureID(uid)
      if fid == featureID then return true end
    end
  end
  return false
end

function heroOnFeatureDestroyed(featureID)
  if wreckConsumedByRez[featureID] then
    wreckConsumedByRez[featureID] = nil
    return
  end
  local id = heroByFeatureID[featureID]
  if not id then return end
  heroByFeatureID[featureID] = nil
  local rec = heroes[id]
  rec.wreckFeatureID = nil
  -- Rez path often destroys the corpse a tick before UnitCreated. Always enter
  -- grace for the race — but blast/reclaim (no rez bot on the feature) uses a
  -- short window so rescue-fail → EXTRACT does not wait a full 2s.
  if rec.state == "down" or rec.state == "down_pending_wreck" or rec.state == "rez_grace" then
    local likelyRez = rezBuilderWorkingFeature(featureID)
    local grace = likelyRez and HERO_REZ_GRACE or math.min(HERO_REZ_GRACE, 15)
    rec.state = "rez_grace"
    rec.rezGraceUntil = (Spring.GetGameFrame() or 0) + grace
    rec.wreckLikelyBlasted = not likelyRez
    Spring.Echo("VA_HERO_REZ_GRACE id=" .. id
      .. " feature=" .. tostring(featureID)
      .. " frames=" .. tostring(grace)
      .. " blast=" .. tostring(not likelyRez))
    if not likelyRez and SendToUnsynced then
      -- Early HUD cue: stop "still recoverable" while grace races the rez check.
      SendToUnsynced("VERDANCE_HERO_EVENT", "wreck_gone", rec.id, rec.name,
        rec.missionCritical and 1 or 0, rec.deathX or 0, rec.deathZ or 0)
    end
    return
  end
  heroLost(rec, "wreck_destroyed")
end

function checkHeroWreckTimeouts(frame)
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
function finalizeHeroStates()
  for _, rec in pairs(heroes) do
    if rec.state == "lost" then
      rec.result = "dead"
    elseif rec.state == "down" or rec.state == "down_pending_wreck" or rec.state == "rez_grace" then
      -- Still a wreck (or rez race unresolved): critical = wounded carry, else dead.
      rec.result = rec.missionCritical and "wounded" or "dead"
    else
      -- alive at the end = home in good health, even if they went down and were rezzed
      -- (the rescue is still reported, as a "recovered" named outcome, for the story).
      rec.result = "survived"
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

function heroInState(heroId, state1, state2)
  if heroId then
    local rec = heroes[heroId]
    return rec ~= nil and (rec.state == state1 or rec.state == state2)
  end
  for _, rec in pairs(heroes) do
    if rec.state == state1 or rec.state == state2 then return true end
  end
  return false
end

function heroWasRecovered(heroId)
  if heroId then
    local rec = heroes[heroId]
    return rec ~= nil and rec.state == "alive" and rec.everDown
  end
  for _, rec in pairs(heroes) do
    if rec.state == "alive" and rec.everDown then return true end
  end
  return false
end

function compileBeats()
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

function beatTriggerMet(b, frame)
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
    -- There is no extract loop any more: "extraction started" = the EXTRACT phase
    -- opened (every objective done); the player ends the sortie via the manifest.
    return extraObj.announced == true
  elseif k == "hero_down" then
    return heroInState(b.heroId, "down", "down_pending_wreck")
  elseif k == "hero_recovered" then
    return heroWasRecovered(b.heroId)
  elseif k == "hero_lost" then
    return heroInState(b.heroId, "lost")
  end
  return false
end

function beatActionXYZ(action)
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

function runBeatSpawn(b, action)
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

function runBeatActions(b)
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
        local px, pz = enemyResponseTarget()
        spawnWave(objectiveTeamID, tonumber(action.count) or waves.baseSize, px, pz, "beat_" .. b.id)
      end
    elseif kind == "spawn" then
      runBeatSpawn(b, action)
    elseif kind == "hydrology" then
      -- Flood or drain. The waterline is a campaign scalar; this moves it
      -- inside a mission, over `seconds`, so it reads as an event.
      vaBeginWaterline(tonumber(action.to) or 0, tonumber(action.seconds) or 20)
    elseif kind == "objective_secondary" then
      -- Wire into marks registry (orphan va_secondary_ids path removed).
      local sid = tostring(action.id or b.id)
      local ax, _, az = beatActionXYZ(action)
      MarksLib.upsert(marks, sid, {
        kind = tostring(action.kind or MarksLib.KIND.structure),
        label = tostring(action.description or action.label or sid),
        required = action.required == true,
        total = tonumber(action.total) or 1,
        x = ax,
        z = az,
      })
      marksCommit("secondary_changed", sid)
    end
  end
  Spring.Echo("VA_BEAT_FIRED id=" .. b.id)
end

function checkBeats(frame)
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
  if MarksLib.requiredLeft(marks) > 0 then return false end
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

function onObjectiveComplete(how)
  if objectiveComplete then return end
  objectiveComplete = true
  objectiveCompleteHow = how or "complete"
  objectiveCompleteFrame = Spring.GetGameFrame() or 0
  Spring.SetGameRulesParam("va_objective_complete", 1, { public = true })
  Spring.Echo("VA_OBJECTIVE_COMPLETE mission=" .. tostring(mission.missionId) .. " how=" .. objectiveCompleteHow)
  if SendToUnsynced then SendToUnsynced("VERDANCE_MISSION_EVENT", "objective_complete", objectiveCompleteHow) end
  -- Builder / fortify mission joins: Consul (etc.) sign on when the zone is secured.
  if how == "zone_fortified" or VA_KINDS.fortify[objectiveKind()] then
    recruitAssistFortifyOnSecure()
  end
  -- Retrieve-stash: if the stash pilot was wrecked+rezzed already they joined via
  -- wreck_rez; if still alive on player team after retrieve, treat as stash join.
  for _, rec in pairs(heroes) do
    if rec and rec.recruitable and not rec.recruited and tostring(rec.recruitMode or "") == "retrieve_stash" then
      local uid = rec.unitID
      if uid and Spring.ValidUnitID(uid) and not Spring.GetUnitIsDead(uid) then
        local team = Spring.GetUnitTeam(uid)
        if team == playerTeamID or (Spring.AreTeamsAllied and Spring.AreTeamsAllied(team, playerTeamID)) then
          tryRecruitFieldHero(rec, uid, "retrieve_stash")
        end
      end
    end
  end
  vaMaybeAnnounceAllDone()
  -- Hot extraction: one counter-pack on objective complete (Arc A still gets
  -- this even when timed escalation is off). Full escalation also uses it.
  if (waves.enabled or doctrine.hotExtractOnly) and objectiveTeamID then
    local px, pz = enemyResponseTarget()
    spawnWave(objectiveTeamID, waves.baseSize + 2, px, pz, "hot_extraction")
  end
end

-- ============================================================
-- MODE A: same-map seamless continue (WO-050..053)
-- Soft terminal skips Spring.GameOver; debrief pick reseeds in-place.
-- ============================================================

function currentMapId()
  return tostring((mission and mission.deploymentMapId) or (zoneMap and zoneMap.mapId) or "")
end

function candidateIsSameMap(cand)
  if type(cand) ~= "table" then return false end
  local mapId = currentMapId()
  if mapId == "" then return false end
  return tostring(cand.mapId or "") == mapId
end

function sameMapContinueAvailable()
  local rules = mission and mission.continueRules
  if rules and rules.sameMapContinue == false then return false end
  local cands = mission and mission.nextMissionCandidates
  if type(cands) ~= "table" then return false end
  for i = 1, #cands do
    if candidateIsSameMap(cands[i]) then return true end
  end
  return false
end

function findEnemyCampTeam()
  if objectiveTeamID then return objectiveTeamID end
  for _, tid in ipairs(Spring.GetTeamList() or {}) do
    if tid ~= playerTeamID and tid ~= gaiaTeamID and not Spring.AreTeamsAllied(playerTeamID, tid) then
      return tid
    end
  end
  return nil
end

function isEcoStructureDef(ud)
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
shellObjectivesClaimed = false  -- gadget-env (local budget)
function isShellTeethDef(ud, defID)
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

function claimLivingShellObjectives()
  if shellObjectivesClaimed then return 0 end
  local shell = mission and mission.livingShell
  if not shell or shell.enabled == false then
    shellObjectivesClaimed = true
    return 0
  end
  local kind = objectiveKind()
  -- Survive kinds stand in the zone; they never book the shell as targets
  -- (survive is a presence hold, not a raze). Nothing to claim.
  if VA_KINDS.survive[kind] then
    shellObjectivesClaimed = true
    return 0
  end
  local captureMode = VA_KINDS.capture[kind]
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
  -- Empty primary pad (hub mark with no shell pocket): promote one combat
  -- pocket's eco — never fusion vaults, never the whole map.
  if tagged <= 0 then
    local fallbackPocket = nil
    local occ = mission and mission.mapOccupation
    if type(occ) == "table" then
      for _, row in ipairs(occ) do
        if type(row) == "table" and row.livingShell and row.primary and row.pocketId
            and not row.optionalTarget and not row.highValue then
          fallbackPocket = tostring(row.pocketId)
          break
        end
      end
      if not fallbackPocket then
        for _, row in ipairs(occ) do
          if type(row) == "table" and row.livingShell and row.pocketId
              and not row.optionalTarget and not row.highValue then
            fallbackPocket = tostring(row.pocketId)
            break
          end
        end
      end
    end
    for i = 1, #units do
      local uid = units[i]
      if Spring.ValidUnitID(uid) and not Spring.GetUnitIsDead(uid) and not objectiveTargets[uid] then
        local isShell = Spring.GetUnitRulesParam(uid, "va_living_shell") == 1
          or Spring.GetUnitRulesParam(uid, "va_living_shell") == true
        if isShell then
          local team = Spring.GetUnitTeam(uid)
          local dID = Spring.GetUnitDefID(uid)
          local ud = dID and UnitDefs[dID]
          local role = tostring(Spring.GetUnitRulesParam(uid, "va_force_role") or "")
          local pocket = tostring(Spring.GetUnitRulesParam(uid, "va_shell_pocket") or "")
          local highValue = Spring.GetUnitRulesParam(uid, "va_high_value") == 1
            or role == "objective_secondary"
          local pocketOk = (not fallbackPocket) or (pocket == fallbackPocket)
          if pocketOk and not highValue and isEcoStructureDef(ud)
              and team and team ~= playerTeamID and team ~= gaiaTeamID then
            objectiveTargets[uid] = forceId
            objectiveTargetCount = objectiveTargetCount + 1
            targetForceStructures[forceId] = (targetForceStructures[forceId] or 0) + 1
            tagged = tagged + 1
            if not teamID then teamID = team end
            Spring.SetUnitRulesParam(uid, "va_force_role", "objective_target", { public = true })
          end
        end
      end
    end
    if tagged > 0 then
      Spring.Echo("VA_SHELL_OBJECTIVES_EXPANDED count=" .. tostring(tagged)
        .. " pocket=" .. tostring(fallbackPocket or "any_combat")
        .. " reason=empty_primary_pad")
    end
  end
  if teamID then objectiveTeamID = teamID end
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

-- Optional high-value shell marks (fusion vaults, etc.): book into the marks
-- registry as required=false so they pay bonus standing but never gate victory.
function claimOptionalHighValueSecondaries()
  local units = Spring.GetAllUnits() or {}
  local tagged = 0
  for i = 1, #units do
    local uid = units[i]
    if Spring.ValidUnitID(uid) and not Spring.GetUnitIsDead(uid) and not MarksLib.hasTarget(marks, uid) then
      local isShell = Spring.GetUnitRulesParam(uid, "va_living_shell") == 1
        or Spring.GetUnitRulesParam(uid, "va_living_shell") == true
      local highValue = Spring.GetUnitRulesParam(uid, "va_high_value") == 1
        or Spring.GetUnitRulesParam(uid, "va_keep_class") == "high_value"
      local role = tostring(Spring.GetUnitRulesParam(uid, "va_force_role") or "")
      if isShell and (highValue or role == "objective_secondary") then
        local team = Spring.GetUnitTeam(uid)
        local dID = Spring.GetUnitDefID(uid)
        if team and team ~= playerTeamID and team ~= gaiaTeamID and isStructure(dID) then
          local sid = tostring(Spring.GetUnitRulesParam(uid, "va_secondary_id") or "")
          if sid == "" then
            local pocket = tostring(Spring.GetUnitRulesParam(uid, "va_shell_pocket") or "mark")
            sid = "bonus_fus_" .. pocket:lower()
          end
          MarksLib.bindTarget(marks, uid, sid, {
            required = false,
            kind = MarksLib.KIND.vault,
            label = sid,
          })
          tagged = tagged + 1
        end
      end
    end
  end
  if tagged > 0 then
    MarksLib.enrichFromMission(marks, mission and mission.secondaries, Game.mapSizeX, Game.mapSizeZ)
    MarksLib.publish(marks)
    Spring.Echo("VA_OPTIONAL_HIGH_VALUE_CLAIMED count=" .. tostring(tagged)
      .. " groups=" .. tostring(MarksLib.count(marks)))
  end
  return tagged
end

-- Heavy terminal work (quantum transition, result JSON, telemetry, GameOver).
-- Extracted from setTerminal so the exfil path can paint a loading screen first.
-- Pass five: the sortie ends once, with facts. No verdict here (Python reads the manifest),
-- no deferred crunch, no soft-continue, no engine GameOver. The exfil gadget owns the manifest
-- and the quit; this is the one place the result is written.
function runTerminalCrunch(opts)
  opts = opts or {}
  local kind = opts.reason or terminalReason
  Spring.Echo("VA_TERMINAL_CRUNCH kind=" .. tostring(kind) .. " frame=" .. tostring(Spring.GetGameFrame() or 0))
  VAQ.transition(kind)
  logResult()
  if devTel.enabled and SendToUnsynced then
    SendToUnsynced("VERDANCE_TRACK", "result", lastResultJson or "")
  end
  if SendToUnsynced then SendToUnsynced("VERDANCE_SORTIE_OVER", kind) end
  local profilingRun = headless.autoStart or balance.exportFrame or (#fib.milestones > 0)
  if profilingRun and headless.quit then
    headless.quitFrame = Spring.GetGameFrame() + 60
  end
end



-- kind: "extracted" (manifest confirmed) | "wiped" (nobody left) | "closed" (engine ended it).
function setTerminal(kind, reason)
  if terminal then return end
  terminal = true
  terminalReason = tostring(reason or kind or "")
  status = tostring(kind or "closed")
  debugAutoProgress = 0
  finalizeHeroStates()
  publishHeroRules()
  Spring.SetGameRulesParam("va_terminal", 1, { public = true })
  Spring.SetGameRulesParam("va_status", status, { public = true })
  Spring.SetGameRulesParam("va_terminal_reason", terminalReason, { public = true })
  Spring.Echo("VA_TERMINAL kind=" .. status .. " reason=" .. terminalReason)
  runTerminalCrunch({ reason = status })
end

-- The exfil gadget calls this when the player confirms the manifest.
function GG.VA_EndSortie(kind)
  -- Clean vs contested extraction is Python's reading of manifest.enemyOnPad.
  setTerminal(kind, kind)
end

function GG.VA_TenebriumBank()
  return tonumber(tenebLoot and tenebLoot.bank) or 0
end

-- Tnb top bar feed (gui_verdance_tnb_bar.lua). GLOBAL on purpose: the main chunk is
-- at Lua 5.1's 200-local ceiling. Every field is guarded; tenebLoot may be bare early
-- (handlers pack attaches after the chunk) so each read is pcall-safe.
function publishTenebriumRules()
  local function readField(name)
    local ok, v = pcall(function() return tenebLoot and tenebLoot[name] end)
    if not ok then return nil end
    return v
  end
  local function asCount(v)
    if type(v) == "function" then
      local ok, r = pcall(v)
      v = ok and r or 0
    end
    if type(v) == "table" then
      local n = 0
      for _ in pairs(v) do n = n + 1 end
      return n
    end
    return tonumber(v) or 0
  end
  local bank = tonumber(readField("bank")) or 0
  local looted = tonumber(readField("looted")) or tonumber(readField("total")) or 0
  local spent = tonumber(readField("spent")) or 0
  local field = asCount(readField("unclaimedWrecks"))
  pcall(Spring.SetGameRulesParam, "va_tenebrium_bank", bank, { public = true })
  pcall(Spring.SetGameRulesParam, "va_tenebrium_looted", looted, { public = true })
  pcall(Spring.SetGameRulesParam, "va_tenebrium_spent", spent, { public = true })
  pcall(Spring.SetGameRulesParam, "va_tenebrium_wrecks_unclaimed", field, { public = true })
end

function pocketClearProgress()
  if objectiveTargetCount <= 0 then return 1.0, 0, 0 end
  local need = math.max(1, math.ceil(objectiveTargetCount * CLEAR_FRACTION))
  return objectiveTargetsDestroyed / objectiveTargetCount, objectiveTargetsDestroyed, need
end

function fireRegrowPressure(frame)
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

-- Live metrics for player units standing inside a zone rect.
function playerMetricsInRect(rect)
  local bucket = { metrics = emptyMetrics(), unitCountsByDef = {} }
  if not rect or not Spring.GetTeamUnits then return bucket.metrics end
  local units = Spring.GetTeamUnits(playerTeamID) or {}
  for i = 1, #units do
    local u = units[i]
    if Spring.ValidUnitID(u) and not Spring.GetUnitIsDead(u) then
      local x, _, z = Spring.GetUnitPosition(u)
      if x and z and x >= rect[1] and x <= rect[3] and z >= rect[2] and z <= rect[4] then
        local defID = Spring.GetUnitDefID(u)
        if defID then addUnitToBucket(bucket, defID, u) end
      end
    end
  end
  return bucket.metrics
end

function checkFortifyObjective(frame)
  if objectiveComplete or not targetZoneRect then return end
  local kind = objectiveKind()
  if not VA_KINDS.fortify[kind] then return end
  local obj = mission and mission.objective or {}
  -- Territory secure = defensive value only (circle of dirt / Warder teeth).
  local needDef = tonumber(obj.fortifyDefensiveValue) or 800
  local metrics = playerMetricsInRect(targetZoneRect)
  local defNow = math.floor(metrics.defensiveValue or 0)
  local defOk = defNow >= needDef
  Spring.SetGameRulesParam("va_fortify_def", defNow, { public = true })
  Spring.SetGameRulesParam("va_fortify_need_def", needDef, { public = true })
  Spring.SetGameRulesParam("va_fortify_score", defOk and 1 or 0, { public = true })
  if defOk then
    onObjectiveComplete("zone_fortified")
  end
end

function checkPresenceObjective(frame)
  if objectiveComplete then return end
  local kind = objectiveKind()
  if VA_KINDS.fortify[kind] then
    checkFortifyObjective(frame)
    return
  end
  -- Capture and survive kinds hold the target zone; destruction kinds with zero
  -- booked targets fall back to the same zone-hold rule so missions stay winnable.
  local presenceMode = VA_KINDS.capture[kind] or VA_KINDS.survive[kind]
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
      -- Player must stay on the node. Enemy contact PAUSES the clock (regrow
      -- waves used to hard-reset to 0 and softlock 22/30 forever). Leave zone
      -- → lose progress. Contested but present → hold what you earned.
      if not playerPresent then
        zoneHoldFrames = 0
      elseif not enemyCombat then
        zoneHoldFrames = zoneHoldFrames + CHECK_PERIOD
      end
      Spring.SetGameRulesParam("va_zone_hold", zoneHoldFrames, { public = true })
      Spring.SetGameRulesParam("va_zone_hold_contested", (playerPresent and enemyCombat) and 1 or 0, { public = true })
      local required = tonumber(mission.objective and mission.objective.requiredHoldFrames) or PRESENCE_HOLD_DEFAULT
      Spring.SetGameRulesParam("va_zone_hold_need", required, { public = true })
      if targetZoneRect then
        local cx = (targetZoneRect[1] + targetZoneRect[3]) * 0.5
        local cz = (targetZoneRect[2] + targetZoneRect[4]) * 0.5
        local hw = math.abs(targetZoneRect[3] - targetZoneRect[1]) * 0.5
        local hh = math.abs(targetZoneRect[4] - targetZoneRect[2]) * 0.5
        Spring.SetGameRulesParam("va_hold_cx", math.floor(cx), { public = true })
        Spring.SetGameRulesParam("va_hold_cz", math.floor(cz), { public = true })
        Spring.SetGameRulesParam("va_hold_hw", math.floor(hw), { public = true })
        Spring.SetGameRulesParam("va_hold_hh", math.floor(hh), { public = true })
      end
      if zoneHoldFrames >= required then
        capture.nodeClaimed = true
        nodeClaimedFrame = frame
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

  -- Legacy presence (no living shell): stand on zone; pause on contact, reset on leave.
  local playerPresent, enemyCombat = scanZoneRect(targetZoneRect)
  if not playerPresent then
    zoneHoldFrames = 0
  elseif not enemyCombat then
    zoneHoldFrames = zoneHoldFrames + CHECK_PERIOD
  end
  Spring.SetGameRulesParam("va_zone_hold", zoneHoldFrames, { public = true })
  Spring.SetGameRulesParam("va_zone_hold_contested", (playerPresent and enemyCombat) and 1 or 0, { public = true })
  local required = tonumber(mission.objective and mission.objective.requiredHoldFrames) or PRESENCE_HOLD_DEFAULT
  Spring.SetGameRulesParam("va_zone_hold_need", required, { public = true })
  if targetZoneRect then
    local cx = (targetZoneRect[1] + targetZoneRect[3]) * 0.5
    local cz = (targetZoneRect[2] + targetZoneRect[4]) * 0.5
    local hw = math.abs(targetZoneRect[3] - targetZoneRect[1]) * 0.5
    local hh = math.abs(targetZoneRect[4] - targetZoneRect[2]) * 0.5
    Spring.SetGameRulesParam("va_hold_cx", math.floor(cx), { public = true })
    Spring.SetGameRulesParam("va_hold_cz", math.floor(cz), { public = true })
    Spring.SetGameRulesParam("va_hold_hw", math.floor(hw), { public = true })
    Spring.SetGameRulesParam("va_hold_hh", math.floor(hh), { public = true })
  end
  if zoneHoldFrames >= required then
    onObjectiveComplete("zone_held")
  end
end

function checkPlayerWipe(frame)
  if frame < WIPE_GRACE_FRAMES then return end
  local count = Spring.GetTeamUnitCount(playerTeamID) or 0
  if count <= 0 then
    -- nobody left to confirm a manifest: the exfil gadget stamps an empty one and we end
    if not (GG and GG.VA_WipedManifest and GG.VA_WipedManifest()) then setTerminal("wiped", "player_wiped") end
  end
end


-- Soft clock: requiredFrames is a real mission end, not just a HUD countdown.
-- Without this, time hits 0 and the player sits in PHASE FIGHT forever.
-- The clock is a fact on the HUD, not an ending. The sortie ends when the player extracts,
-- when nobody is left, or when the player closes the game.
function checkSoftClock(frame)
  if terminal or status ~= "active" then return end
  local req = mission and mission.objective and tonumber(mission.objective.requiredFrames)
  if not req or req <= 0 then return end
  local left = req - frame
  Spring.SetGameRulesParam("va_clock_left", math.max(0, left), { public = true })
  local phase = "FIGHT"
  if vaAllObjectivesDone() then
    phase = "EXTRACT"
  elseif objectiveComplete then
    phase = "MARKS"
  elseif frame < 90 * 30 then
    phase = "APPROACH"
  end
  if left <= 0 then phase = "OVERTIME" end
  Spring.SetGameRulesParam("va_phase", phase, { public = true })
end

function isCommanderUnitDef(ud)
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


function gadget:Initialize()
  Spring.Echo("VA_CAMPAIGN_BRIDGE_LOADED")
  mission = readMission()
  zoneMap = readZoneMap()
  do
    local okQ, module = pcall(VFS.Include, "luarules/gadgets/include/va_quantum_campaign.lua")
    if okQ and type(module) == "table" and type(mission.campaignQuantumState) == "table" then
      VAQ.module = module
      VAQ.kernel = module.new(mission.campaignQuantumState, {})
      local snapshot = VAQ.kernel:snapshot()
      Spring.Echo("VA_QUANTUM_READY schema=" .. tostring(snapshot.schemaVersion)
        .. " index=" .. tostring(snapshot.transitionIndex)
        .. " hash=" .. tostring(snapshot.stateHash))
    else
      Spring.Echo("VA_QUANTUM_LEGACY reason=" .. tostring(okQ and "seed_missing" or module))
    end
  end
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
  -- Quantum transit is the sole runtime source of reinforcements. Legacy seeds
  -- keep the old escalation path; quantum seeds never run both systems.
  if VAQ.kernel then waves.enabled = false end
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
  local metal = fieldK * 1000
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

function gadget:GameStart()
  -- Bank + crisis flags before any unit stamps/charges.
  if tenebLoot.initFromMission then tenebLoot.initFromMission() end
  -- Sink the waterline before anyone is placed, so the dry search sees the
  -- shore the company will actually stand on.
  vaInitWaterline()
  spawnPlayableSetup()
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
  if VAQ.kernel and frame > 0 and frame % 30 == 0 then
    VAQ.processArrivals(frame)
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
  -- (hub marks like GF_NE_PLATEAU with no pocket used to leave eco_raid at 0).
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

  -- Pillar B / raid pressure: enemy reinforcements. For a raid the Armada QRF
  -- answers as the works are wrecked (damage thresholds) so the pressure reads
  -- as cause-and-effect; other missions use the steady timer.
  if waves.enabled and status == "active" and not terminal and not objectiveComplete and objectiveTeamID then
    if objectiveKind() == "eco_raid" then
      if waves.spawned < waves.max then
        local dmg = (objectiveTargetCount > 0) and (objectiveTargetsDestroyed / objectiveTargetCount) or 0
        local threshold = raidWaveThresholds[waves.spawned + 1] or 1.1
        if dmg >= threshold then
          local px, pz = enemyResponseTarget()
          spawnWave(objectiveTeamID, waves.baseSize, px, pz, "armada_qrf")
          waves.spawned = waves.spawned + 1
          waves.nextFrame = frame + waves.interval
          Spring.SetGameRulesParam("va_waves_spawned", waves.spawned, { public = true })
        end
      end
    elseif frame >= waves.nextFrame and waves.spawned < waves.max then
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
    targetForceStructures[forceId] = math.max(0, (targetForceStructures[forceId] or 1) - 1)
    Spring.SetGameRulesParam("va_objective_destroyed", objectiveTargetsDestroyed, { public = true })
    Spring.Echo("VA_OBJECTIVE_TARGET_DOWN force=" .. forceId .. " destroyed=" .. tostring(objectiveTargetsDestroyed) .. "/" .. tostring(objectiveTargetCount))
    if not objectiveComplete and status == "active" and not terminal then
      local kind = objectiveKind()
      if VA_KINDS.choice[kind] then
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
      elseif VA_KINDS.capture[kind] or capture.mode then
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

-- Living logistics: deferred combat packs arrive mid-sortie from map-web / launcher.
-- Packed into one gadget-env table so this file stays under Lua 5.1's 200-local limit
-- (Exceeded → gadget fails to load → BAR Initial Spawn drops a naked Legion com only).
VA_LOGISTICS = { pending = {} }

function VA_LOGISTICS.infilAnchor()
  local dx, dz = VA_padPoint()
  if dx and dz then return dx, dz end
  local px, pz = teamUnitCentroid(playerTeamID)
  if px then return px, pz end
  return (Game.mapSizeX or 0) * 0.5, (Game.mapSizeZ or 0) * 0.5
end

function VA_LOGISTICS.publishInboundHud()
  local n = 0
  for _, d in ipairs(VA_LOGISTICS.pending) do
    if d and not d.arrived then
      n = n + 1
      local left = math.max(0, (d.dueFrame or 0) - (Spring.GetGameFrame() or 0))
      Spring.SetGameRulesParam("va_inbound_" .. n .. "_label", tostring(d.label or d.listingId or "shipment"), { public = true })
      Spring.SetGameRulesParam("va_inbound_" .. n .. "_source", tostring(d.sourceLabel or d.mode or ""), { public = true })
      Spring.SetGameRulesParam("va_inbound_" .. n .. "_eta", math.floor(left / 30), { public = true })
      Spring.SetGameRulesParam("va_inbound_" .. n .. "_count", tonumber(d.count) or 0, { public = true })
      Spring.SetGameRulesParam("va_inbound_" .. n .. "_mode", tostring(d.mode or ""), { public = true })
    end
  end
  Spring.SetGameRulesParam("va_inbound_total", n, { public = true })
end

function VA_LOGISTICS.spawnPackageDelivery(spec)
  if not playerTeamID or type(spec) ~= "table" then return 0 end
  local defName = tostring(spec.unitDef or "")
  local count = math.max(1, math.min(24, math.floor(tonumber(spec.count) or 1)))
  if defName == "" or not UnitDefNames or not UnitDefNames[defName] then
    Spring.Echo("VA_DELIVERY_FAIL missing_def=" .. defName)
    return 0
  end
  local mode = tostring(spec.mode or "map_web")
  local tx, tz = VA_LOGISTICS.infilAnchor()
  local x, z
  if mode == "pawn_launcher" then
    -- Land near infil with tight scatter.
    x = tx + ((math.random() * 2) - 1) * 160
    z = tz + ((math.random() * 2) - 1) * 160
  else
    local arrival = { destinationZoneId = mission and mission.targetZoneId or "", mass = 0.05 }
    x, z = VAQ.entryFor(arrival, { defName })
    if not x then
      local sx, sz = Game.mapSizeX or 1, Game.mapSizeZ or 1
      local edges = {
        { x = 220, z = tz }, { x = sx - 220, z = tz },
        { x = tx, z = 220 }, { x = tx, z = sz - 220 },
      }
      local best, bestD = edges[1], -1
      for _, e in ipairs(edges) do
        local dx, dz = e.x - tx, e.z - tz
        local d = dx * dx + dz * dz
        if d > bestD then best, bestD = e, d end
      end
      x, z = best.x, best.z
    end
  end
  local spawned = 0
  local hmin = tonumber(spec.healthFracMin) or 1
  local hmax = tonumber(spec.healthFracMax) or 1
  local hfrac = (hmin + hmax) * 0.5
  for i = 1, count do
    local ux, uz
    if mode == "pawn_launcher" then
      ux = x + ((i % 3) - 1) * 55
      uz = z + math.floor((i - 1) / 3) * 55
    else
      ux = x + ((i % 3) - 1) * 70
      uz = z + math.floor((i - 1) / 3) * 70
    end
    ux = math.max(48, math.min((Game.mapSizeX or 96) - 48, ux))
    uz = math.max(48, math.min((Game.mapSizeZ or 96) - 48, uz))
    local uid = Spring.CreateUnit(defName, ux, Spring.GetGroundHeight(ux, uz), uz, 0, playerTeamID)
    if uid then
      spawned = spawned + 1
      Spring.SetUnitRulesParam(uid, "va_package_tag", tostring(spec.packageTag or spec.listingId or defName), { public = true })
      Spring.SetUnitRulesParam(uid, "va_playable_proxy", 1, { public = true })
      Spring.SetUnitRulesParam(uid, "va_delivery_mode", mode, { public = true })
      if hfrac < 0.99 and Spring.SetUnitHealth and Spring.GetUnitHealth then
        local _, maxH = Spring.GetUnitHealth(uid)
        if maxH and maxH > 0 then pcall(Spring.SetUnitHealth, uid, maxH * hfrac) end
      end
      -- Delivered units wait where they land: only named heroes act on their own.
    end
  end
  Spring.Echo("VA_DELIVERY_ARRIVE listing=" .. tostring(spec.listingId or "")
    .. " mode=" .. mode
    .. " source=" .. tostring(spec.sourceLabel or spec.sourceMapId or "")
    .. " count=" .. tostring(spawned)
    .. " from=" .. tostring(math.floor(x)) .. "," .. tostring(math.floor(z)))
  if spawned > 0 and SendToUnsynced then
    local bark = tostring(spec.label or spec.listingId or "shipment")
    if mode == "pawn_launcher" then
      bark = "Pawn launcher impact — " .. tostring(spawned) .. " near infil"
    elseif tostring(spec.sourceMapId or "") == "all_that_simmers" then
      bark = "Geo-vent stream clearing the gaps — " .. bark
    else
      bark = "Column clearing the rim from " .. tostring(spec.sourceLabel or "the web") .. " — " .. bark
    end
    SendToUnsynced("VERDANCE_BEAT", "wave_warning", x, Spring.GetGroundHeight(x, z) or 0, z, bark)
  end
  return spawned
end

function VA_LOGISTICS.armPendingDeliveries()
  VA_LOGISTICS.pending = {}
  local bag = mission and mission.commerce or {}
  local list = bag.pendingDeliveries or mission.pendingDeliveries or {}
  local frame = Spring.GetGameFrame() or 0
  for _, raw in ipairs(list) do
    if type(raw) == "table" and tostring(raw.status or "in_transit") == "in_transit" then
      local eta = math.max(15, math.floor(tonumber(raw.etaSeconds) or 90))
      local rec = {
        id = tostring(raw.id or (#VA_LOGISTICS.pending + 1)),
        listingId = raw.listingId,
        label = raw.label or raw.listingId,
        unitDef = raw.unitDef,
        count = tonumber(raw.count) or 1,
        mode = raw.mode or "map_web",
        sourceMapId = raw.sourceMapId,
        sourceLabel = raw.sourceLabel,
        packageTag = raw.packageTag or raw.listingId,
        healthFracMin = raw.healthFracMin,
        healthFracMax = raw.healthFracMax,
        dueFrame = frame + eta * 30,
        arrived = false,
        warned = false,
      }
      VA_LOGISTICS.pending[#VA_LOGISTICS.pending + 1] = rec
      Spring.Echo("VA_DELIVERY_ARMED listing=" .. tostring(rec.listingId)
        .. " mode=" .. tostring(rec.mode)
        .. " etaSec=" .. tostring(eta)
        .. " source=" .. tostring(rec.sourceLabel or ""))
    end
  end
  VA_LOGISTICS.publishInboundHud()
end

-- t=0 commerce bag (pawn-launcher packs, constructors, fabs, nanos) — mission.commerce.deploy.
-- Deferred map-web packs stay on pendingDeliveries; this only loads what already paid at the hub.
-- RULE (one owner): this is the ONLY spawner of the commerce deploy bag. The layout force
-- in playableSetup carries preview copies of the same items (stamped commerceDeploy=true by
-- scripts/build_next_mission_v1.ps1 Add-CommerceDeployToKit) and spawnPlayableSetup skips
-- them via VA_CREW_isCommerceKitSpec. Spawning here AND there is the double-spawn bug.
function VA_LOGISTICS.spawnCommerceDeployKit()
  if VA_LOGISTICS.deployKitSpawned then
    Spring.Echo("VA_COMMERCE_DEPLOY already_spawned")
    return 0
  end
  VA_LOGISTICS.deployKitSpawned = true
  local bag = mission and mission.commerce or {}
  local list = bag.deploy or {}
  if type(list) ~= "table" or #list == 0 then
    Spring.Echo("VA_COMMERCE_DEPLOY empty")
    return 0
  end
  if not playerTeamID then
    Spring.Echo("VA_COMMERCE_DEPLOY skip no_player_team")
    return 0
  end
  local baseX, baseZ = VA_LOGISTICS.infilAnchor()
  local total = 0
  for i, raw in ipairs(list) do
    if type(raw) == "table" then
      local kind = tostring(raw.kind or "package")
      local lid = tostring(raw.listingId or raw.packageTag or ("kit_" .. tostring(i)))
      if kind == "package" or kind == "loan_package" or kind == "purchase_package" then
        local n = VA_LOGISTICS.spawnPackageDelivery({
          listingId = lid,
          label = raw.label or lid,
          unitDef = raw.unitDef,
          count = tonumber(raw.count) or 1,
          mode = "pawn_launcher",
          packageTag = raw.packageTag or lid,
          healthFracMin = raw.healthFracMin or raw.healthFrac,
          healthFracMax = raw.healthFracMax or raw.healthFrac,
        })
        total = total + n
      elseif kind == "constructor" then
        local defName = tostring(raw.unitDef or "")
        local count = math.max(1, math.floor(tonumber(raw.count) or 1))
        if defName ~= "" and UnitDefNames and UnitDefNames[defName] then
          local n = spawnUnitSpec({
            unitDefName = defName,
            count = count,
            dx = 90 + (i % 3) * 70,
            dz = -160 - math.floor((i - 1) / 3) * 70,
            spacing = 85,
            packageTag = lid,
          }, playerTeamID, baseX, baseZ, 0, 0, {}, { role = "player_crew" })
          total = total + n
          Spring.Echo("VA_COMMERCE_DEPLOY constructor=" .. defName .. " n=" .. tostring(n) .. " listing=" .. lid)
        else
          Spring.Echo("VA_COMMERCE_DEPLOY_FAIL constructor_def=" .. defName)
        end
      elseif kind == "unit_printer" then
        local factoryDef = tostring(raw.factoryDef or raw.unitDef or "")
        local product = tostring(raw.product or "corak")
        local seed = math.max(0, math.floor(tonumber(raw.seedCount) or 0))
        if factoryDef ~= "" and UnitDefNames and UnitDefNames[factoryDef] then
          local n = spawnUnitSpec({
            unitDefName = factoryDef,
            count = 1,
            dx = 140 + (i % 2) * 110,
            dz = -220 - math.floor((i - 1) / 2) * 100,
            spacing = 120,
            packageTag = lid,
            unitPrinter = true,
            printerProduct = product,
            printerMetalIncome = tonumber(raw.metalIncome) or 8,
            printerEnergyIncome = tonumber(raw.energyIncome) or 40,
          }, playerTeamID, baseX, baseZ, 0, 0, {}, { role = "player_crew" })
          total = total + n
          if seed > 0 and product ~= "" and UnitDefNames[product] then
            total = total + spawnUnitSpec({
              unitDefName = product,
              count = seed,
              dx = 200 + (i % 2) * 90,
              dz = -280,
              spacing = 70,
              packageTag = lid .. "_seed",
            }, playerTeamID, baseX, baseZ, 0, 0, {}, { role = "player_crew" })
          end
          Spring.Echo("VA_COMMERCE_DEPLOY fab=" .. factoryDef .. " product=" .. product
            .. " seed=" .. tostring(seed) .. " listing=" .. lid)
        else
          Spring.Echo("VA_COMMERCE_DEPLOY_FAIL fab_def=" .. factoryDef)
        end
      elseif kind == "nano" then
        local defName = tostring(raw.unitDef or "cornanotc")
        local count = math.max(1, math.floor(tonumber(raw.count) or 1))
        if UnitDefNames and UnitDefNames[defName] then
          local n = spawnUnitSpec({
            unitDefName = defName,
            count = count,
            dx = 60 + i * 55,
            dz = -240,
            spacing = 70,
            packageTag = lid,
          }, playerTeamID, baseX, baseZ, 0, 0, {}, { role = "player_crew" })
          total = total + n
        end
      else
        Spring.Echo("VA_COMMERCE_DEPLOY_SKIP kind=" .. kind .. " listing=" .. lid)
      end
    end
  end
  Spring.Echo("VA_COMMERCE_DEPLOY spawned=" .. tostring(total) .. " listings=" .. tostring(#list))
  return total
end

function VA_LOGISTICS.tickPendingDeliveries(frame)
  if #VA_LOGISTICS.pending == 0 then return end
  local dirty = false
  for _, d in ipairs(VA_LOGISTICS.pending) do
    if d and not d.arrived then
      local left = (d.dueFrame or 0) - frame
      if not d.warned and left <= 30 * 30 and left > 0 then
        d.warned = true
        if SendToUnsynced then
          SendToUnsynced("VERDANCE_BEAT", "wave_warning", 0, 0, 0,
            "Inbound " .. tostring(d.label or "shipment") .. " · " .. tostring(math.floor(left / 30)) .. "s")
        end
      end
      if frame >= (d.dueFrame or 0) then
        d.arrived = true
        VA_LOGISTICS.spawnPackageDelivery(d)
        dirty = true
      end
    end
  end
  if dirty or (frame % 30 == 0) then
    VA_LOGISTICS.publishInboundHud()
  end
end

function VA_LOGISTICS.spawnBruteCrashFromEdge(count)
  return VA_LOGISTICS.spawnPackageDelivery({
    listingId = "crash_of_brutes",
    label = "Crash of Brutes",
    unitDef = "corraid",
    count = count or 4,
    mode = "map_web",
    sourceMapId = "eye_of_horus",
    sourceLabel = "Eye of Horus",
    packageTag = "crash_of_brutes",
    healthFracMin = 0.9,
    healthFracMax = 1.0,
  })
end

-- Compat aliases for existing call sites (gadget-env globals, not main-chunk locals).
armPendingDeliveries = function(...) return VA_LOGISTICS.armPendingDeliveries(...) end
tickPendingDeliveries = function(...) return VA_LOGISTICS.tickPendingDeliveries(...) end
spawnBruteCrashFromEdge = function(...) return VA_LOGISTICS.spawnBruteCrashFromEdge(...) end
spawnCommerceDeployKit = function(...) return VA_LOGISTICS.spawnCommerceDeployKit(...) end

-- Playtest commands change the sortie (grant, spawn, end, reset): cheats only, so a player's
-- typo can never freeze or end a real drop.
local VA_CHEAT_COMMANDS = { vatnb = true, vabrutecrash = true, vaheadless = true, vareset = true,
  vaspawnlayout = true, vastart = true, varesult = true, vaexport = true, vatest_killobjective = true }

function runVerdanceCommand(cmd)
  if type(cmd) ~= "string" then return false end
  local head = cmd:match("^(%a[%w_]*)") or cmd
  if VA_CHEAT_COMMANDS[head] and not Spring.IsCheatingEnabled() then
    Spring.Echo("VA_CMD_DENIED " .. head .. " needs /cheat")
    return true
  end
  -- Exfil (manifest / extract:<dest>) is owned by game_verdance_exfil.lua.
  -- Operator / playtest: grant liquid Tenebrium so BP constructors unlock.
  local tnbAmt = cmd:match("^vatnb[%s:]+(%-?%d+)")
  if cmd == "vatnb" or tnbAmt or cmd:match("^vatnb[%s:]") then
    local n = tonumber(tnbAmt) or 8
    if tenebLoot and tenebLoot.addBank then
      tenebLoot.addBank(n, "operator_grant")
      Spring.Echo("VA_TENEBRIUM_GRANT amount=" .. tostring(n)
        .. " bank=" .. tostring(tenebLoot.bank or 0))
    else
      Spring.Echo("VA_TENEBRIUM_GRANT_FAIL handlers_missing")
    end
    return true
  end
  local bruteN = cmd:match("^vabrutecrash[%s:]+(%d+)")
  if cmd == "vabrutecrash" or bruteN or cmd:match("^vabrutecrash") then
    spawnBruteCrashFromEdge(tonumber(bruteN) or 4)
    return true
  end
  if cmd == "vastart" then startMission()
  elseif cmd == "vastatus" then echoStatus()
  elseif cmd == "vatest_killobjective" then
    if Spring.IsCheatingEnabled() then
      local ids = {}
      for unitID in pairs(objectiveTargets) do ids[#ids + 1] = unitID end
      for _, unitID in ipairs(ids) do Spring.DestroyUnit(unitID, false, false) end
      Spring.Echo("VA_TEST_KILLOBJECTIVE destroyed=" .. tostring(#ids))
    else
      Spring.Echo("VA_TEST_DENIED cheats required for vatest_killobjective")
    end
  elseif cmd == "vaspawnlayout" then spawnPlayableSetup()
  elseif cmd == "vazones" then echoZones()
  elseif cmd == "vatelemetry" or cmd == "vabalance" then logTelemetry()
  elseif cmd == "vatranslation" then logAndBroadcastTranslation()
  elseif cmd == "varesult" or cmd == "vaexport" then
    if Spring.IsCheatingEnabled() then logResult() else Spring.Echo("VA_TEST_DENIED cheats required for varesult") end
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
  elseif cmd == "vareset" then
    -- Local debug mission latch only — not a campaign wipe (use hub RESET.bat).
    status = "inactive"
    holdFrames = 0
    debugAutoProgress = 0
    Spring.Echo("VA_RESET local_debug_only (hub RESET.bat wipes campaign)")
    echoStatus()
  elseif cmd:match("^vapack") then
    -- Mid-Drop A/B for pack glue / line-spread (handled by pack_overlay GG).
    if GG and GG.VA_PackSet then
      local rest = string.lower((cmd:match("^vapack%s+(.+)$") or ""):match("^%s*(.-)%s*$") or "")
      if rest == "" or rest == "status" or rest == "?" then
        if GG.VA_PackStatus then GG.VA_PackStatus() end
      elseif rest == "help" then
        Spring.Echo("VA_PACK help: /vapack status|on|off|drag on|drag off")
      elseif rest:match("^drag%s+") then
        local tok = rest:match("^drag%s+(%S+)")
        local on = (tok == "on" or tok == "1" or tok == "true")
        local off = (tok == "off" or tok == "0" or tok == "false")
        if on or off then
          GG.VA_PackSet({ drag = on })
        else
          Spring.Echo("VA_PACK_BAD use /vapack drag on|off")
        end
      elseif rest == "on" or rest == "1" or rest == "true" then
        GG.VA_PackSet({ enabled = true, drag = true })
      elseif rest == "off" or rest == "0" or rest == "false" then
        GG.VA_PackSet({ enabled = false, drag = false })
      else
        Spring.Echo("VA_PACK_BAD use /vapack status|on|off|drag on|drag off")
      end
    else
      Spring.Echo("VA_PACK_UNAVAILABLE overlay_gadget_missing")
    end
  else return false end
  return true
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
