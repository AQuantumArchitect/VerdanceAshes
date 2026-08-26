local widget = widget

function widget:GetInfo()
  return {
    name = "Verdance Objectives HUD",
    desc = "Mission briefing, objective flow, beats, heroes, and campaign debrief for Verdance's Ashes",
    author = "Claude / Luke Spooner",
    date = "2026-07-12",
    license = "GPL v2 or later",
    layer = 5,
    enabled = true,
  }
end

local mission
local briefingLines = {}
local missionCard = nil   -- WO-031 plain-English card
local nextMissionCandidates = {}  -- WO-042 debrief picks
local nextPickIndex = nil
local continueArmed = false       -- WO-050 soft terminal: same-map continue available
local continueChapter = 1
local continueMessage = nil       -- brief status after pick / map-change
local debriefCandidates = {}
local missionTitle = "Verdance's Ashes"
local storyReason = nil
local difficultyLabel = nil
local lastPoll = 0
local briefingDismissed = false
local briefingReopenUntil = 0
local vsx, vsy = Spring.GetViewGeometry()
-- Forward decl: Mode B inject is assigned below; Initialize needs the upvalue.
local injectModeBTravelCandidates

local BRIEFING_SECONDS = 45
local EXTRACTION_HOLD_FRAMES = 450
local PRESENCE_HOLD_DEFAULT = 900

local state = {
  status = "inactive",
  objectiveTotal = 0,
  objectiveDestroyed = 0,
  objectiveComplete = false,
  terminal = false,
  resultCode = 0,
  zoneHold = 0,
  extractionHold = 0,
  extractionClean = true,
  terminalReason = "",
  requiredFrames = 19800,
  holdFrames = 0,
  wavesSpawned = 0,
  captureMode = false,
  capturePhase = "idle",
  pocketCleared = false,
  nodeClaimed = false,
  pocketClearFrac = 0,
  regrowWaves = 0,
  mercsAvailable = false,
}

-- Mid-mission subtitles (beat barks): drawn one at a time, frame-timed.
local barkQueue = {}          -- { speaker, text, untilFrame (set when shown), seconds }

-- Named heroes: seeded from the mission manifest, updated by hero events.
local heroRoster = {}         -- heroId -> { name, missionCritical, state, everDown }
local heroBanner = nil        -- { text, critical } while a hero wreck is rescuable
local heroWreckBeacon = nil   -- { x, z, name } for the DrawWorld ground ring

-- World beacons + one-shot minimap markers for objective/extraction/landing.
local objectiveMarkerPlaced = false
local extractionMarkerPlaced = false
local deployMarkerPlaced = false
local secondaryMarkersPlaced = false  -- Drop 4: secondary-objective map marks
local beaconObjective = nil   -- { x, z }
local beaconExtraction = nil  -- { x, z }
local beaconDeploy = nil      -- { x, z } enfil / landing

-- Ash Console tokens (docs/UI_ASH_CONSOLE.md) — shared feel with hub HTML.
local Ash
do
  local ok, mod = pcall(VFS.Include, "luaui/Widgets/include/va_ash_tokens.lua")
  if not ok or type(mod) ~= "table" then
    ok, mod = pcall(VFS.Include, "LuaUI/Widgets/include/va_ash_tokens.lua")
  end
  Ash = (ok and type(mod) == "table") and mod or nil
end

-- Compatibility aliases (same names older draw code used).
local COL = Ash and {
  panel = Ash.COL.panel,
  edge = { Ash.COL.edge[1], Ash.COL.edge[2], Ash.COL.edge[3], 0.55 },
  title = Ash.COL.gold,
  text = Ash.COL.ink,
  ketha = Ash.COL.ketha,
  dim = Ash.COL.muted,
  good = Ash.COL.good,
  bad = Ash.COL.bad,
  warn = Ash.COL.warn,
  blue = Ash.COL.steam,
  steam = Ash.COL.steam,
  gold = Ash.COL.gold,
  tnb = Ash.COL.tnb,
  ash = Ash.COL.ash,
} or {
  panel = { 0.031, 0.063, 0.047, 0.90 },
  edge = { 0.239, 0.561, 0.333, 0.55 },
  title = { 0.831, 0.769, 0.604 },
  text = { 0.933, 0.965, 0.933 },
  ketha = { 0.651, 0.820, 0.651 },
  dim = { 0.490, 0.584, 0.518 },
  good = { 0.490, 1.0, 0.541 },
  bad = { 1.0, 0.490, 0.490 },
  warn = { 0.878, 0.627, 0.376 },
  blue = { 0.494, 0.784, 1.0 },
  steam = { 0.494, 0.784, 1.0 },
  gold = { 0.831, 0.769, 0.604 },
  tnb = { 0.788, 0.627, 1.0 },
  ash = { 0.604, 0.545, 0.447 },
}

local function readMission()
  local ok, data = pcall(VFS.Include, "singleplayer/verdance_ashes/generated/va_current.lua")
  if ok and type(data) == "table" then return data end
  ok, data = pcall(VFS.Include, "singleplayer/verdance_ashes/generated/va_001.lua")
  if ok and type(data) == "table" then return data end
  return nil
end

-- BAR ships these ui sounds; try the bare name first (how BAR widgets call
-- them), then the explicit VFS path as a fallback.
local function playUi(file, vol)
  if not Spring.PlaySoundFile then return end
  local ok = Spring.PlaySoundFile(tostring(file), vol or 1.0, 'ui')
  if not ok then
    Spring.PlaySoundFile("sounds/ui/" .. tostring(file) .. ".wav", vol or 1.0, 'ui')
  end
end

local function queueBark(speaker, textStr, seconds)
  barkQueue[#barkQueue + 1] = {
    speaker = tostring(speaker or ""),
    text = tostring(textStr or ""),
    seconds = tonumber(seconds) or 7,
  }
end

function widget:Initialize()
  mission = readMission()
  if mission then
    missionTitle = mission.title or missionTitle
    local intent = mission.storyIntent or {}
    -- WO-031: prefer seed missionCard; fall back to intent.missionCard.
    if type(mission.missionCard) == "table" then
      missionCard = mission.missionCard
    elseif type(intent.missionCard) == "table" then
      missionCard = intent.missionCard
    end
    if type(mission.nextMissionCandidates) == "table" then
      nextMissionCandidates = injectModeBTravelCandidates(mission.nextMissionCandidates)
      mission.nextMissionCandidates = nextMissionCandidates
    else
      nextMissionCandidates = injectModeBTravelCandidates({})
      mission.nextMissionCandidates = nextMissionCandidates
    end
    -- Ketha flavor lines stay for optional reopen; not the main intro.
    if type(intent.briefing) == "table" and type(intent.briefing.lines) == "table" then
      briefingLines = intent.briefing.lines
    end
    if type(intent.debriefCandidates) == "table" then
      debriefCandidates = intent.debriefCandidates
    end
    storyReason = intent.storyReason
    if mission.objective and mission.objective.requiredFrames then
      state.requiredFrames = tonumber(mission.objective.requiredFrames) or state.requiredFrames
    end
    local diff = mission.difficulty
    if type(diff) == "table" then
      -- Prefer compiler's plain-English label (includes dial + farm flags).
      if type(diff.label) == "string" and diff.label ~= "" then
        difficultyLabel = diff.label
      elseif diff.enemyScale then
        local scale = tonumber(diff.enemyScale) or 1.0
        if scale >= 1.6 then difficultyLabel = "Expected opposition: heavy"
        elseif scale >= 1.2 then difficultyLabel = "Expected opposition: reinforced"
        elseif scale <= 0.85 then difficultyLabel = "Expected opposition: light"
        else difficultyLabel = "Expected opposition: standard" end
      end
      if diff.fortified then difficultyLabel = (difficultyLabel or "") .. ", fortified" end
      if (tonumber(diff.hazardLevel) or 0) > 0.3 then difficultyLabel = (difficultyLabel or "") .. ", wild pressure rising" end
      if diff.farmSortie then difficultyLabel = (difficultyLabel or "") .. "  |  FARM XP" end
    end
    local arc = mission.arcProfile
    if type(arc) == "table" and arc.id then
      difficultyLabel = (difficultyLabel or "") .. "  |  Arc: " .. tostring(arc.id)
    end
    -- Hero manifest: names the HUD and debrief track through hero events.
    if type(mission.heroes) == "table" then
      for _, h in ipairs(mission.heroes) do
        if h.id then
          heroRoster[tostring(h.id)] = {
            name = tostring(h.name or h.id),
            missionCritical = h.missionCritical == true,
            state = "alive",
            everDown = false,
            level = tonumber(h.level) or 1,
            rank = tostring(h.rank or "Runner"),
          }
        end
      end
    end
  end
  pcall(function()
    widgetHandler:RegisterGlobal(widget, "VerdanceMissionEvent", function(eventStatus, reason)
      widget:VerdanceMissionEvent(eventStatus, reason)
    end)
    widgetHandler:RegisterGlobal(widget, "VerdanceHeroEvent", function(event, heroId, name, critical, x, z)
      widget:VerdanceHeroEvent(event, heroId, name, critical, x, z)
    end)
    widgetHandler:RegisterGlobal(widget, "VerdanceBeat", function(kind, a, b, c, d)
      widget:VerdanceBeat(kind, a, b, c, d)
    end)
  end)
end

function widget:Shutdown()
  pcall(function()
    widgetHandler:DeregisterGlobal(widget, "VerdanceMissionEvent")
    widgetHandler:DeregisterGlobal(widget, "VerdanceHeroEvent")
    widgetHandler:DeregisterGlobal(widget, "VerdanceBeat")
  end)
end

function widget:ViewResize(x, y)
  vsx, vsy = x, y
end

-- Spring.GetGameRulesParam returns ZERO values (not nil) for an unset param,
-- so tonumber(sp(name)) would call tonumber() with no argument and throw.
-- Capture into a local first, then coerce with a default.
local function numParam(name, default)
  local v = Spring.GetGameRulesParam(name)
  return tonumber(v) or default
end

local function groundY(x, z)
  return Spring.GetGroundHeight(x, z) or 0
end

local function placeMarkers()
  if not deployMarkerPlaced then
    local dx = numParam("va_deploy_x", -1)
    local dz = numParam("va_deploy_z", -1)
    if dx >= 0 and dz >= 0 then
      deployMarkerPlaced = true
      beaconDeploy = { x = dx, z = dz }
      pcall(Spring.MarkerAddPoint, dx, groundY(dx, dz), dz, ">>> LANDING (enfil) <<<", true)
    end
  end
  if not objectiveMarkerPlaced then
    local ox = numParam("va_objective_x", -1)
    local oz = numParam("va_objective_z", -1)
    if ox >= 0 and oz >= 0 then
      objectiveMarkerPlaced = true
      beaconObjective = { x = ox, z = oz }
      local label = (mission and mission.objective and mission.objective.description) or "Objective"
      pcall(Spring.MarkerAddPoint, ox, groundY(ox, oz), oz, "!!! OBJECTIVE: " .. tostring(label), true)
    end
  end
  -- Drop 4: secondary marks get their own map markers (required vs bonus).
  if not secondaryMarkersPlaced and (state.secondaryTotal or 0) > 0 then
    local placedAll = true
    for i = 1, state.secondaryTotal do
      local sec = state.secondaries and state.secondaries[i]
      if sec and sec.x >= 0 and sec.z >= 0 then
        pcall(Spring.MarkerAddPoint, sec.x, groundY(sec.x, sec.z), sec.z,
          (sec.req and "++ 2ND OBJECTIVE: " or "++ BONUS MARK: ") .. tostring(sec.label), true)
      else
        placedAll = false
      end
    end
    secondaryMarkersPlaced = placedAll
  end
  -- Show extract LZ early (dim) and strengthen after objective complete.
  local ex = numParam("va_extract_x", -1)
  local ez = numParam("va_extract_z", -1)
  if ex >= 0 and ez >= 0 then
    beaconExtraction = { x = ex, z = ez }
    if state.allObjectivesDone and not extractionMarkerPlaced then
      extractionMarkerPlaced = true
      pcall(Spring.MarkerAddPoint, ex, groundY(ex, ez), ez, "^^^ EXTRACT HERE — hold ^^^", true)
    end
  end
end

-- Draw a flat ground chevron / arrow pointing +Z (north) at (x,z).
local function drawGroundArrow(x, z, size, r, g, b, a)
  local y = groundY(x, z) + 4
  local s = size or 140
  gl.Color(r, g, b, a)
  gl.LineWidth(3.5)
  -- shaft
  gl.BeginEnd(GL.LINES, function()
    gl.Vertex(x, y, z - s * 0.55)
    gl.Vertex(x, y, z + s * 0.25)
  end)
  -- head
  gl.BeginEnd(GL.LINE_LOOP, function()
    gl.Vertex(x, y, z + s * 0.55)
    gl.Vertex(x - s * 0.35, y, z + s * 0.1)
    gl.Vertex(x + s * 0.35, y, z + s * 0.1)
  end)
  gl.LineWidth(1)
end

local function poll()
  local sp = Spring.GetGameRulesParam
  state.objectiveTotal = numParam("va_objective_total", 0)
  state.objectiveDestroyed = numParam("va_objective_destroyed", 0)
  state.objectiveComplete = numParam("va_objective_complete", 0) == 1
  state.terminal = numParam("va_terminal", 0) == 1
  state.resultCode = numParam("va_result_code", 0)
  state.zoneHold = numParam("va_zone_hold", 0)
  state.extractionHold = numParam("va_extraction_hold", 0)
  state.extractionClean = numParam("va_extraction_clean", 1) == 1
  state.wavesSpawned = numParam("va_waves_spawned", 0)
  state.captureMode = numParam("va_capture_mode", 0) == 1
  state.pocketCleared = numParam("va_pocket_cleared", 0) == 1
  state.nodeClaimed = numParam("va_node_claimed", 0) == 1
  state.pocketClearFrac = numParam("va_pocket_clear_frac", 0)
  state.regrowWaves = numParam("va_regrow_waves", 0)
  do
    local ph = Spring.GetGameRulesParam("va_capture_phase")
    if type(ph) == "string" and ph ~= "" then state.capturePhase = ph end
  end
  -- Drop 4: secondary ledger + strong-objective state.
  state.secondaryTotal = numParam("va_secondary_total", 0)
  state.secondaryDone = numParam("va_secondary_done", 0)
  state.secondaryRequiredLeft = numParam("va_secondary_required_left", 0)
  state.purgeArmed = numParam("va_purge_armed", 0) == 1
  state.purgeDone = numParam("va_purge_done", 0) == 1
  state.allObjectivesDone = numParam("va_all_objectives_done", 0) == 1
  state.secondaries = state.secondaries or {}
  for i = 1, state.secondaryTotal do
    local lbl = Spring.GetGameRulesParam("va_sec" .. i .. "_label")
    state.secondaries[i] = {
      label = (type(lbl) == "string" and lbl ~= "") and lbl or ("Mark " .. i),
      req = numParam("va_sec" .. i .. "_req", 0) == 1,
      done = numParam("va_sec" .. i .. "_done", 0) == 1,
      x = numParam("va_sec" .. i .. "_x", -1),
      z = numParam("va_sec" .. i .. "_z", -1),
    }
  end
  state.mercsAvailable = numParam("va_mercs_available", 0) == 1
  state.tenebriumLooted = numParam("va_tenebrium_looted", 0)
  state.tenebriumBank = numParam("va_tenebrium_bank", 0)
  state.tenebriumSpent = numParam("va_tenebrium_spent", 0)
  state.tenebriumLost = numParam("va_tenebrium_lost", 0)
  state.tenebriumBpMax = numParam("va_tenebrium_bp_max", 0)
  state.tenebriumBpUsed = numParam("va_tenebrium_bp_used", 0)
  state.tenebriumAccess = numParam("va_tenebrium_access", 0)
  state.armadaTenebriumCrisis = numParam("va_armada_tenebrium_crisis", 1) == 1
  state.requiredFrames = numParam("va_required_frames", state.requiredFrames or 19800)
  state.holdFrames = numParam("va_hold_frames", 0)
  continueArmed = numParam("va_soft_continue", 0) == 1
  continueChapter = numParam("va_continue_chapter", 1)
  local st = sp("va_status")
  if type(st) == "string" and st ~= "" then state.status = st end
  local reason = sp("va_terminal_reason")
  if type(reason) == "string" then state.terminalReason = reason end
  placeMarkers()
end

local function formatClock(totalSeconds)
  totalSeconds = math.max(0, math.floor(totalSeconds + 0.5))
  local m = math.floor(totalSeconds / 60)
  local s = totalSeconds % 60
  return string.format("%d:%02d", m, s)
end

function widget:GameFrame(frame)
  if frame - lastPoll >= 30 then
    lastPoll = frame
    poll()
  end
end

local function currentMissionMapId()
  if mission and mission.deploymentMapId then return tostring(mission.deploymentMapId) end
  return ""
end

local function candidateIsSameMap(cand)
  if type(cand) ~= "table" then return false end
  local mapId = currentMissionMapId()
  if mapId == "" then return true end -- optimistic if seed omits map id
  return tostring(cand.mapId or "") == mapId
end

-- Mode B: strategic_link table from world_zone_graph (session host Reload path).
local strategicLinks = nil
local function loadStrategicLinks()
  if strategicLinks ~= nil then return strategicLinks end
  strategicLinks = {}
  for _, p in ipairs({
    "luaui/Widgets/include/va_strategic_links.lua",
    "LuaUI/Widgets/include/va_strategic_links.lua",
    "luarules/gadgets/include/va_strategic_links.lua",
  }) do
    local ok, data = pcall(VFS.Include, p)
    if ok and type(data) == "table" then
      strategicLinks = data
      break
    end
  end
  return strategicLinks
end

local function missionAnchorZones()
  local zones = {}
  local function push(z)
    z = tostring(z or "")
    if z == "" then return end
    for i = 1, #zones do if zones[i] == z then return end end
    zones[#zones + 1] = z
  end
  if mission then
    if mission.objective then push(mission.objective.targetZoneId) end
    push(mission.extractionZoneId)
    push(mission.deploymentZoneId)
  end
  return zones
end

injectModeBTravelCandidates = function(cands)
  cands = cands or {}
  local links = loadStrategicLinks()
  if type(links) ~= "table" or #links == 0 then return cands end
  local curMap = currentMissionMapId()
  local anchors = missionAnchorZones()
  if #anchors == 0 then return cands end
  local have = {}
  for _, c in ipairs(cands) do
    if c and c.targetZoneId then have[tostring(c.targetZoneId)] = true end
  end
  local function addHop(fromZ, toZ, toMap, fromMap, cost, notes, label)
    if curMap ~= "" and tostring(toMap) == curMap then return end
    if have[tostring(toZ)] then return end
    have[tostring(toZ)] = true
    cands[#cands + 1] = {
      id = "mode_b_" .. tostring(fromZ) .. "_" .. tostring(toZ),
      title = "Travel — " .. tostring(label or toZ),
      plain = "Mode B map travel via strategic_link. Exit BAR; session host Reload path builds "
        .. tostring(toMap) .. " (" .. tostring(toZ) .. ").",
      mapId = tostring(toMap or ""),
      targetZoneId = tostring(toZ or ""),
      fromZoneIds = { tostring(fromZ) },
      objectiveArchetype = "seize_lane",
      patron = "nullmercs",
      against = "armada",
      sessionMode = "reload_travel",
      travelMode = "mode_b",
      edgeKind = "strategic_link",
      cost = cost or 2,
      notes = notes or "",
      fromMapId = tostring(fromMap or curMap),
    }
    Spring.Echo("VA_MODE_B_CANDIDATE from=" .. tostring(fromZ)
      .. " to=" .. tostring(toZ) .. " map=" .. tostring(toMap))
  end
  for _, link in ipairs(links) do
    local a, b = tostring(link.fromZoneId or ""), tostring(link.toZoneId or "")
    for _, az in ipairs(anchors) do
      if az == a then
        addHop(a, b, link.toMapId, link.fromMapId, link.cost, link.notes, link.toLabel)
      elseif az == b then
        -- reverse direction
        addHop(b, a, link.fromMapId, link.toMapId, link.cost, link.notes, a)
      end
    end
  end
  return cands
end

local function writeNextSortieChoice(cand, pickIndex)
  if type(cand) ~= "table" then return end
  local isModeB = (cand.travelMode == "mode_b")
    or (cand.sessionMode == "reload_travel")
    or (cand.edgeKind == "strategic_link")
    or (not candidateIsSameMap(cand))
  local sessionMode = cand.sessionMode
  if not sessionMode then
    sessionMode = isModeB and "reload_travel" or "same_map"
  end
  local payload = {
    schemaVersion = "verdance-sortie-order/1.0",
    mapId = cand.mapId,
    targetZoneId = cand.targetZoneId,
    fromZoneIds = cand.fromZoneIds or {},
    objectiveArchetype = cand.objectiveArchetype or cand.kind or "seize_lane",
    patron = cand.patron or "nullmercs",
    against = cand.against or "armada",
    flavor = cand.flavor,
    source = "debrief_pick",
    candidateId = cand.id,
    title = cand.title,
    sessionMode = sessionMode,
    travelMode = isModeB and "mode_b" or nil,
    edgeKind = isModeB and (cand.edgeKind or "strategic_link") or nil,
  }
  -- Echo machine line for extract/advance scripts + Mode B session host.
  local bits = {
    '"mapId":"' .. tostring(payload.mapId or "") .. '"',
    '"targetZoneId":"' .. tostring(payload.targetZoneId or "") .. '"',
    '"objectiveArchetype":"' .. tostring(payload.objectiveArchetype or "") .. '"',
    '"patron":"' .. tostring(payload.patron or "") .. '"',
    '"against":"' .. tostring(payload.against or "") .. '"',
    '"sessionMode":"' .. tostring(sessionMode) .. '"',
  }
  if payload.travelMode then
    bits[#bits + 1] = '"travelMode":"' .. tostring(payload.travelMode) .. '"'
  end
  if payload.edgeKind then
    bits[#bits + 1] = '"edgeKind":"' .. tostring(payload.edgeKind) .. '"'
  end
  if payload.flavor then
    bits[#bits + 1] = '"flavor":"' .. tostring(payload.flavor) .. '"'
  end
  if type(payload.fromZoneIds) == "table" and payload.fromZoneIds[1] then
    bits[#bits + 1] = '"fromZoneIds":["' .. tostring(payload.fromZoneIds[1]) .. '"]'
  end
  Spring.Echo("VA_NEXT_SORTIE_CHOICE {" .. table.concat(bits, ",") .. "}")
  if isModeB then
    Spring.Echo("VA_MODE_B_TRAVEL map=" .. tostring(payload.mapId)
      .. " target=" .. tostring(payload.targetZoneId)
      .. " sessionMode=reload_travel edge=strategic_link")
  end
  -- Best-effort write into BAR write-dir outbox (WO-043 probe path).
  local ok = false
  if io and io.open then
    local paths = {
      "outbox/next_sortie_choice.json",
      "LuaUI/Config/verdance_next_sortie_choice.json",
    }
    for _, p in ipairs(paths) do
      local f = io.open(p, "w")
      if f then
        f:write("{\n")
        f:write('  "schemaVersion": "verdance-sortie-order/1.0",\n')
        f:write('  "mapId": "' .. tostring(payload.mapId or "") .. '",\n')
        f:write('  "targetZoneId": "' .. tostring(payload.targetZoneId or "") .. '",\n')
        f:write('  "objectiveArchetype": "' .. tostring(payload.objectiveArchetype or "") .. '",\n')
        f:write('  "patron": "' .. tostring(payload.patron or "") .. '",\n')
        f:write('  "against": "' .. tostring(payload.against or "") .. '",\n')
        f:write('  "sessionMode": "' .. tostring(sessionMode) .. '",\n')
        if payload.travelMode then
          f:write('  "travelMode": "' .. tostring(payload.travelMode) .. '",\n')
        end
        if payload.edgeKind then
          f:write('  "edgeKind": "' .. tostring(payload.edgeKind) .. '",\n')
        end
        if type(payload.fromZoneIds) == "table" and payload.fromZoneIds[1] then
          f:write('  "fromZoneIds": ["' .. tostring(payload.fromZoneIds[1]) .. '"],\n')
        end
        if payload.flavor then
          f:write('  "flavor": "' .. tostring(payload.flavor) .. '",\n')
        end
        f:write('  "source": "debrief_pick"\n')
        f:write("}\n")
        f:close()
        ok = true
        Spring.Echo("VA_NEXT_SORTIE_WROTE " .. p)
        break
      end
    end
  end
  if not ok then
    Spring.Echo("VA_NEXT_SORTIE_WRITE_FAILED use infolog VA_NEXT_SORTIE_CHOICE")
  end
  nextPickIndex = cand

  -- WO-051 Mode A: same-map pick continues in-engine without exiting BAR.
  local idx = tonumber(pickIndex)
  if idx and candidateIsSameMap(cand) and (continueArmed or state.terminal) then
    Spring.SendLuaRulesMsg("VA_CMD:vacontinue:" .. tostring(idx))
    continueMessage = "Continuing on this map..."
    Spring.Echo("VA_UI_REQUEST_CONTINUE index=" .. tostring(idx) .. " target=" .. tostring(cand.targetZoneId))
  elseif idx and not candidateIsSameMap(cand) then
    continueMessage = "Mode B travel locked. Exit BAR — session host Reload path launches the new map."
    Spring.Echo("VA_UI_MAP_CHANGE_PICK map=" .. tostring(cand.mapId) .. " mode=mode_b")
  end
end

function widget:KeyPress(key)
  -- WO-042/051: number keys 1-3 pick next mission on debrief (Mode A continues in-seat).
  if state.terminal and #nextMissionCandidates > 0 then
    local idx = nil
    if key == 49 or key == 257 then idx = 1 end -- 1 / numpad1
    if key == 50 or key == 258 then idx = 2 end
    if key == 51 or key == 259 then idx = 3 end
    if idx and nextMissionCandidates[idx] then
      writeNextSortieChoice(nextMissionCandidates[idx], idx)
      return true
    end
  end
  -- space or escape dismisses the briefing card early
  if not briefingDismissed and (key == 32 or key == 27) and not state.terminal then
    local frame = Spring.GetGameFrame() or 0
    if frame < BRIEFING_SECONDS * 30 or frame < briefingReopenUntil then
      briefingDismissed = true
      briefingReopenUntil = 0
      return false
    end
  end
  return false
end

function widget:TextCommand(command)
  if command == "vabrief" then
    -- Re-open the briefing card for another read.
    briefingDismissed = false
    briefingReopenUntil = (Spring.GetGameFrame() or 0) + BRIEFING_SECONDS * 30
    return true
  end
  if command:sub(1, 8) == "vanext " then
    local n = tonumber(command:sub(9))
    if n and nextMissionCandidates[n] then
      writeNextSortieChoice(nextMissionCandidates[n], n)
      return true
    end
  end
  if command:sub(1, 11) == "vacontinue " then
    local n = tonumber(command:sub(12))
    if n and nextMissionCandidates[n] then
      writeNextSortieChoice(nextMissionCandidates[n], n)
      return true
    end
  end
  return false
end

local function text(str, x, y, size, color, align)
  if Ash and Ash.text then
    Ash.text(str, x, y, size, color, align)
    return
  end
  gl.Color(color[1], color[2], color[3], color[4] or 1)
  gl.Text(str, x, y, size, (align or "c") .. "o")
end

local function panel(x1, y1, x2, y2, accent)
  if Ash and Ash.panel then
    Ash.panel(x1, y1, x2, y2, { accent = accent })
    return
  end
  gl.Color(COL.panel[1], COL.panel[2], COL.panel[3], COL.panel[4] or 0.9)
  gl.Rect(x1, y1, x2, y2)
  gl.Color(COL.edge[1], COL.edge[2], COL.edge[3], COL.edge[4] or 0.55)
  gl.Rect(x1, y2 - 2, x2, y2)
  gl.Rect(x1, y1, x2, y1 + 2)
  if accent then
    gl.Color(accent[1], accent[2], accent[3], accent[4] or 0.85)
    gl.Rect(x1, y1, x1 + 3, y2)
  end
end

local function pickDebriefLine()
  if state.resultCode == 1 then
    if state.extractionClean and debriefCandidates.victoryClean then return debriefCandidates.victoryClean end
    if debriefCandidates.objectiveDestroyed and state.objectiveTotal > 0 then return debriefCandidates.objectiveDestroyed end
    return debriefCandidates.victory
  elseif state.resultCode == 2 then
    if state.terminalReason == "commander_lost" and debriefCandidates.defeatCommander then return debriefCandidates.defeatCommander end
    if state.terminalReason:find("^hero_lost_") and debriefCandidates.defeatHero then return debriefCandidates.defeatHero end
    return debriefCandidates.defeat
  end
  return debriefCandidates.partial
end

local function currentDisplayVerdict()
  if Ash and Ash.displayVerdict then
    return Ash.displayVerdict(state.status, state.resultCode, state.terminalReason)
  end
  if state.resultCode == 1 or state.status == "victory" then return "victory" end
  if state.resultCode == 2 or state.status == "defeat" then return "defeat" end
  return "partial"
end

local function verdictPaint(verdict)
  if Ash and Ash.verdictInfo then
    local info = Ash.verdictInfo(verdict)
    local col = Ash.color(info.color)
    return info.banner, info.headline, col
  end
  if verdict == "victory" then return "SECURED", "Secured.", COL.good end
  if verdict == "defeat" then return "FIELD COSTS", "Field costs.", COL.bad end
  return "HINGE", "Hinge. Not a win.", COL.warn
end

-- Credit honesty line (UI only; real credits live in match_credit_v1).
local function creditHonestyLine(verdict)
  if verdict == "victory" then
    if state.nodeClaimed then
      return "Zone claim eligible · no free Tnb mint"
    end
    return "Full credit on bring-home"
  end
  if verdict == "partial" then
    if state.nodeClaimed then
      return "Node claimed · hinge only · no free Tnb"
    end
    return "Hinge credit · not a full victory"
  end
  if verdict == "defeat" then
    return "No zone flip · scars may land"
  end
  return "No campaign advance until bring-home"
end

local function drawBriefingCard()
  local w = math.min(700, vsx * 0.62)
  local cx = vsx * 0.5
  local cardLines = {}
  if missionCard then
    local order = {
      { "WHERE", missionCard.situation },
      { "OBJECTIVE", missionCard.objective or missionCard.plainObjective },
      { "HOW TO WIN", missionCard.howToWin },
      { "HOW IT ENDS", missionCard.howItEnds },
      { "THREATS", missionCard.threats },
      { "ALLIES", missionCard.allies },
    }
    for _, row in ipairs(order) do
      if row[2] and tostring(row[2]) ~= "" then
        cardLines[#cardLines + 1] = { head = row[1], body = tostring(row[2]) }
      end
    end
  end
  local h = 110 + (#cardLines * 36) + (difficultyLabel and 18 or 0) + 44
  if #cardLines == 0 then
    h = 146 + math.min(3, #briefingLines) * 22 + (difficultyLabel and 20 or 0)
  end
  local top = vsy * 0.82
  local bottom = top - h
  panel(cx - w / 2, bottom, cx + w / 2, top, COL.edge)

  local y = top - 22
  text("ORDERS", cx, y, 10, COL.ash or COL.dim); y = y - 18
  text(missionTitle, cx, y, 18, COL.title); y = y - 22
  do
    local actLabel = Spring.GetGameRulesParam("va_act_label")
    if actLabel and actLabel ~= "" then
      text(tostring(actLabel), cx, y, 11, COL.warn or COL.dim); y = y - 16
    end
  end
  if difficultyLabel then
    text(difficultyLabel, cx, y, 11, COL.dim); y = y - 18
  end
  -- Route line (Ash Console): infil → target → exfil (matches hub theater arrows)
  if mission then
    local dep = mission.deploymentZoneId or (mission.fromZoneIds and mission.fromZoneIds[1])
    local tgt = mission.targetZoneId or (mission.objective and mission.objective.zoneId)
    local ext = mission.extractionZoneId or dep
    if dep or tgt or ext then
      local route = "Route  " .. tostring(dep or "?") .. "  →  " .. tostring(tgt or "?") .. "  →  " .. tostring(ext or "?")
      text(route, cx, y, 11, COL.steam or COL.warn); y = y - 16
    end
  end
  y = y - 2
  if #cardLines > 0 then
    for _, row in ipairs(cardLines) do
      text(row.head, cx, y, 10, COL.ash or COL.warn); y = y - 14
      text(row.body, cx, y, 12, COL.text); y = y - 20
    end
  else
    if mission and mission.objective and mission.objective.description then
      text("OBJECTIVE", cx, y, 10, COL.ash or COL.warn); y = y - 14
      text(mission.objective.description, cx, y, 13, COL.text); y = y - 22
    end
    for i = 1, math.min(3, #briefingLines) do
      text(tostring(briefingLines[i].text), cx, y, 12, COL.ketha); y = y - 20
    end
  end
  text("Space dismiss  ·  /vabrief reopen", cx, bottom + 14, 10, COL.dim)
end

local function drawObjectiveBar()
  -- Command strip under BAR resource bar — quiet hierarchy, not a debug dump.
  local y = vsy - 72
  local cx = vsx * 0.5
  local obj = mission and mission.objective or {}
  local stripW = math.min(640, vsx * 0.58)
  local stripTop = y + 14
  local stripBot = y - 78
  if heroBanner and not state.terminal then
    stripBot = stripBot - 22
  end
  panel(cx - stripW / 2, stripBot, cx + stripW / 2, stripTop, COL.edge)

  y = stripTop - 16
  text(missionTitle, cx, y, 12, COL.title); y = y - 16

  if not state.terminal then
    local frame = Spring.GetGameFrame() or 0
    local req = state.requiredFrames or 19800
    local left = math.max(0, (req - frame) / 30)
    local phase = Spring.GetGameRulesParam("va_phase")
    if type(phase) ~= "string" or phase == "" then
      phase = "FIGHT"
      if state.objectiveComplete then
        phase = "EXTRACT"
      elseif frame < 90 * 30 then
        phase = "APPROACH"
      end
    end
    phase = string.upper(tostring(phase))
    local clockCol = COL.good
    if left < 120 then clockCol = COL.warn end
    if left < 45 then clockCol = COL.bad end
    local phaseCol = COL.edge
    if phase == "EXTRACT" then phaseCol = COL.steam or COL.blue end
    if phase == "TIMEOUT" then phaseCol = COL.bad end
    text(string.format("%s", phase), cx - 70, y, 13, phaseCol)
    text(formatClock(left), cx + 70, y, 14, clockCol)
    y = y - 16
  end

  if obj.description then
    local marker = state.objectiveComplete and "DONE  " or ""
    local col = state.objectiveComplete and COL.good or COL.text
    text(marker .. obj.description, cx, y, 12, col); y = y - 14
  end

  if state.objectiveTotal > 0 and not state.objectiveComplete then
    local pct = math.floor((state.objectiveDestroyed / math.max(1, state.objectiveTotal)) * 100 + 0.5)
    if state.captureMode and (state.capturePhase == "clear" or state.capturePhase == "idle") then
      text(string.format("Clear pocket  %d%%", pct), cx, y, 11, COL.warn)
    elseif obj.kind == "eco_raid" then
      text(string.format("Works wrecked  %d%%", pct), cx, y, 11, COL.warn)
    else
      text(string.format("Targets  %d / %d", state.objectiveDestroyed, state.objectiveTotal), cx, y, 11, COL.dim)
    end
    y = y - 13
  end

  if state.captureMode and state.capturePhase == "hold" and not state.objectiveComplete then
    local required = (obj.requiredHoldFrames) or PRESENCE_HOLD_DEFAULT
    text(string.format("Hold  %ds / %ds  ·  regrow %d",
      math.floor(state.zoneHold / 30), math.floor(required / 30), state.regrowWaves or 0),
      cx, y, 11, COL.steam or COL.blue)
    y = y - 13
  elseif not state.objectiveComplete and state.zoneHold > 0 and not state.captureMode then
    local required = (obj.requiredHoldFrames) or PRESENCE_HOLD_DEFAULT
    text(string.format("Holding  %ds / %ds", math.floor(state.zoneHold / 30), math.floor(required / 30)),
      cx, y, 11, COL.steam or COL.blue)
    y = y - 13
  end

  if state.captureMode and state.nodeClaimed then
    text("Node claimed · no free Tnb · extract when ready", cx, y, 11, COL.good)
    y = y - 12
  end

  -- Drop 4: secondary marks + strong-objective lines. The extract prompt only
  -- appears once EVERYTHING required has signed off (va_all_objectives_done).
  if (state.secondaryTotal or 0) > 0 then
    for i = 1, state.secondaryTotal do
      local sec = state.secondaries and state.secondaries[i]
      if sec then
        local col = sec.done and COL.good or (sec.req and COL.warn or COL.dim)
        local prefix = sec.done and "DONE  " or ""
        local kindTag = sec.req and "[REQUIRED] " or "[bonus] "
        text(prefix .. kindTag .. tostring(sec.label), cx, y, 11, col)
        y = y - 13
      end
    end
  end
  if state.purgeArmed and not state.terminal then
    if state.purgeDone then
      text("PURGE COMPLETE — the board is clear", cx, y, 11, COL.good)
    else
      text("PURGE ORDER: every enemy faction unit dies", cx, y, 11, COL.warn)
    end
    y = y - 13
  end
  if state.objectiveComplete and not state.allObjectivesDone and not state.terminal then
    text("Primary down — finish the required marks", cx, y, 11, COL.warn)
    y = y - 13
  end

  if state.allObjectivesDone and not state.terminal then
    local held = math.floor(state.extractionHold / 30)
    local need = math.floor(EXTRACTION_HOLD_FRAMES / 30)
    text(string.format("Extract  %ds / %ds", held, need), cx, y, 12, COL.warn)
    y = y - 14
  end

  -- Quiet secondary chips (dim) — not full-width scream.
  if not state.terminal then
    local chips = {}
    chips[#chips + 1] = string.format("Tnb %d", state.tenebriumBank or 0)
    if (state.tenebriumBpMax or 0) > 0 or (state.tenebriumAccess or 0) >= 0 then
      chips[#chips + 1] = string.format("BP %d/%d", math.floor(state.tenebriumBpUsed or 0), math.floor(state.tenebriumBpMax or 0))
    end
    if (state.wavesSpawned or 0) > 0 then
      chips[#chips + 1] = string.format("waves %d", state.wavesSpawned)
    end
    if state.mercsAvailable then
      chips[#chips + 1] = "mercs ready"
    end
    if state.armadaTenebriumCrisis then
      chips[#chips + 1] = "armada Tnb crisis"
    end
    if #chips > 0 then
      text(table.concat(chips, "  ·  "), cx, y, 10, COL.dim)
      y = y - 12
    end
  end

  if heroBanner and not state.terminal then
    local pulse = 0.55 + 0.45 * math.abs(math.sin(os.clock() * 3.5))
    text(heroBanner.text, cx, y - 2, 14, { COL.bad[1], COL.bad[2], COL.bad[3], pulse })
  end
end

-- One bark at a time — framed voice block (matches hub .voice).
local function drawBark()
  local bark = barkQueue[1]
  if not bark then return end
  local frame = Spring.GetGameFrame() or 0
  if not bark.untilFrame then
    bark.untilFrame = frame + bark.seconds * 30
    if bark.speaker ~= "" then playUi("beep4", 0.45) end
  end
  if frame >= bark.untilFrame then
    table.remove(barkQueue, 1)
    return
  end
  local remaining = (bark.untilFrame - frame) / 30
  local alpha = math.min(1, remaining / 0.75)
  local cx = vsx * 0.5
  local y = vsy - 188
  if Ash and Ash.voiceBlock then
    Ash.voiceBlock(cx, y, math.min(560, vsx * 0.55), bark.speaker, bark.text, alpha)
    return
  end
  local label
  local color
  if bark.speaker ~= "" then
    label = bark.speaker .. ': "' .. bark.text .. '"'
    color = { COL.ketha[1], COL.ketha[2], COL.ketha[3], alpha }
  else
    label = bark.text
    color = { COL.warn[1], COL.warn[2], COL.warn[3], alpha }
  end
  text(label, cx, y, 15, color)
end

local function heroStatusBits()
  local bits = {}
  for _, rec in pairs(heroRoster) do
    local s
    if rec.state == "lost" then
      s = rec.name .. ": lost"
    elseif rec.state == "down" then
      s = rec.name .. (rec.missionCritical and ": dragged home wounded" or ": left in the wreckage")
    elseif rec.everDown then
      s = rec.name .. ": recovered, wounded"
    else
      s = rec.name .. ": standing"
    end
    bits[#bits + 1] = s
  end
  table.sort(bits)
  return bits
end

local function warShiftLine(verdict)
  if verdict == "victory" then
    return "The front eases here — contested space recedes."
  elseif verdict == "defeat" then
    return "Contested space spreads — standing frays on this front."
  end
  return "The line holds, barely. The world stays contested."
end

local function drawDebriefScreen()
  local heroBits = heroStatusBits()
  local candCount = #nextMissionCandidates
  local w = math.min(720, vsx * 0.66)
  local cx = vsx * 0.5
  local top = vsy * 0.74
  local extra = candCount * 36 + (nextPickIndex and 22 or 0)
  local bottom = top - 220 - (#heroBits > 0 and (#heroBits * 16 + 10) or 0) - extra
  local verdict = currentDisplayVerdict()
  local banner, headline, bannerCol = verdictPaint(verdict)
  panel(cx - w / 2, bottom, cx + w / 2, top, bannerCol)

  local y = top - 24
  text("SORTIE HOME", cx, y, 10, COL.ash or COL.dim); y = y - 18
  text(banner, cx, y, 22, bannerCol); y = y - 20
  text(headline, cx, y, 13, COL.title); y = y - 18

  local debrief = pickDebriefLine()
  if debrief then
    if Ash and Ash.voiceBlock then
      Ash.voiceBlock(cx, y - 8, w - 40, "Ketha", tostring(debrief), 1)
      y = y - 48
    else
      text('Ketha: "' .. tostring(debrief) .. '"', cx, y, 13, COL.ketha)
      y = y - 22
    end
  end

  local bits = {}
  if state.objectiveTotal > 0 then
    bits[#bits + 1] = string.format("targets %d/%d", state.objectiveDestroyed, state.objectiveTotal)
  end
  if verdict == "victory" then
    bits[#bits + 1] = state.extractionClean and "clean extract" or "contested extract"
  end
  if state.terminalReason ~= "" then
    bits[#bits + 1] = state.terminalReason:gsub("_", " ")
  end
  if #bits > 0 then
    text(table.concat(bits, "  ·  "), cx, y, 11, COL.dim); y = y - 16
  end

  text(creditHonestyLine(verdict), cx, y, 11, COL.steam or COL.blue); y = y - 16

  if #heroBits > 0 then
    text("THE COMPANY", cx, y, 10, COL.ash or COL.dim); y = y - 14
    for _, line in ipairs(heroBits) do
      text(line, cx, y, 11, COL.text); y = y - 14
    end
    y = y - 4
  end

  text(warShiftLine(verdict), cx, y, 11, COL.dim); y = y - 18

  if candCount > 0 then
    if continueArmed then
      text("STILL HERE — press 1 / 2 / 3", cx, y, 12, COL.warn); y = y - 16
    else
      text("NEXT DROP — press 1 / 2 / 3", cx, y, 12, COL.warn); y = y - 16
    end
    for i, c in ipairs(nextMissionCandidates) do
      local same = candidateIsSameMap(c)
      local tag = same and "  · stay on map" or "  · travel (exit BAR)"
      local mark = (nextPickIndex and nextPickIndex.id == c.id) and ">> " or (i .. ") ")
      text(mark .. tostring(c.title or c.id) .. tag, cx, y, 12, COL.text); y = y - 13
      if c.plain then
        text(tostring(c.plain), cx, y, 10, COL.dim); y = y - 15
      end
    end
  end

  if continueMessage then
    text(continueMessage, cx, bottom + 16, 11, COL.good)
  elseif nextPickIndex and continueArmed and candidateIsSameMap(nextPickIndex) then
    text("Stay on this map — company carries forward.", cx, bottom + 16, 11, COL.good)
  elseif nextPickIndex then
    text("Travel locked. Exit BAR — session host reloads the new map.", cx, bottom + 16, 11, COL.steam or COL.blue)
  else
    text("Result logged. Stay continues in-seat; travel exits BAR.", cx, bottom + 16, 11, COL.dim)
  end
end

function widget:DrawScreen()
  if Spring.IsGUIHidden() then return end
  if not mission then return end

  if state.terminal then
    drawDebriefScreen()
    drawObjectiveBar()
    return
  end

  local frame = Spring.GetGameFrame() or 0
  local showCard = missionCard ~= nil or #briefingLines > 0
  if not briefingDismissed and (frame < BRIEFING_SECONDS * 30 or frame < briefingReopenUntil)
      and not state.objectiveComplete and showCard then
    drawBriefingCard()
  end
  drawObjectiveBar()
  drawBark()
end

-- Ground rings + arrows so enfil / objective / extract read as game markers,
-- not just colored text blobs.
function widget:DrawWorld()
  if Spring.IsGUIHidden() then return end
  if not mission then return end
  local pulse = 0.45 + 0.3 * math.abs(math.sin(os.clock() * 2.2))
  local cDeploy = COL.good
  local cObj = COL.warn
  local cExt = COL.steam or COL.blue
  if beaconDeploy and not state.terminal and not state.objectiveComplete then
    gl.Color(cDeploy[1], cDeploy[2], cDeploy[3], pulse * 0.85)
    gl.DrawGroundCircle(beaconDeploy.x, groundY(beaconDeploy.x, beaconDeploy.z), beaconDeploy.z, 200, 40)
    drawGroundArrow(beaconDeploy.x, beaconDeploy.z, 160, cDeploy[1], cDeploy[2], cDeploy[3], pulse)
  end
  if beaconObjective and not state.objectiveComplete and not state.terminal then
    gl.Color(cObj[1], cObj[2], cObj[3], pulse)
    gl.DrawGroundCircle(beaconObjective.x, groundY(beaconObjective.x, beaconObjective.z), beaconObjective.z, 200, 40)
    local ox, oz = beaconObjective.x, beaconObjective.z
    local y = groundY(ox, oz) + 6
    gl.Color(cObj[1], cObj[2], cObj[3], pulse)
    gl.LineWidth(3)
    gl.BeginEnd(GL.LINES, function()
      gl.Vertex(ox - 140, y, oz - 140); gl.Vertex(ox - 40, y, oz - 40)
      gl.Vertex(ox + 140, y, oz - 140); gl.Vertex(ox + 40, y, oz - 40)
      gl.Vertex(ox - 140, y, oz + 140); gl.Vertex(ox - 40, y, oz + 40)
      gl.Vertex(ox + 140, y, oz + 140); gl.Vertex(ox + 40, y, oz + 40)
    end)
    gl.LineWidth(1)
  end
  if beaconExtraction and not state.terminal then
    local a = state.objectiveComplete and pulse or (pulse * 0.45)
    gl.Color(cExt[1], cExt[2], cExt[3], a)
    gl.DrawGroundCircle(beaconExtraction.x, groundY(beaconExtraction.x, beaconExtraction.z), beaconExtraction.z, 230, 40)
    if state.objectiveComplete then
      drawGroundArrow(beaconExtraction.x, beaconExtraction.z, 180, cExt[1], cExt[2], cExt[3], pulse)
    end
  end
  if heroWreckBeacon and not state.terminal then
    gl.Color(COL.bad[1], COL.bad[2], COL.bad[3], 0.5 + 0.4 * math.abs(math.sin(os.clock() * 4)))
    gl.DrawGroundCircle(heroWreckBeacon.x, groundY(heroWreckBeacon.x, heroWreckBeacon.z), heroWreckBeacon.z, 120, 24)
  end
  gl.Color(1, 1, 1, 1)
end

function widget:VerdanceMissionEvent(eventStatus, reason)
  poll()
  if eventStatus == "objective_complete" then
    playUi("beep6", 1.0)
    queueBark("", "Objective complete - return to extraction.")
    Spring.Echo("Verdance: objective complete (" .. tostring(reason) .. ") - return to extraction.")
  elseif eventStatus == "stalemate_warning" then
    playUi("warning1", 0.9)
    queueBark("", "Force spent: no combat units and no way to build more. The sortie is failing.")
  elseif eventStatus == "victory" then
    playUi("commanderspawn", 0.8)
  elseif eventStatus == "defeat" then
    playUi("warning1", 1.0)
  elseif eventStatus == "continue_start" then
    -- Mode A reseed: leave debrief, show next mission card, reset markers.
    state.terminal = false
    state.objectiveComplete = false
    state.resultCode = 0
    state.terminalReason = ""
    nextPickIndex = nil
    continueMessage = nil
    objectiveMarkerPlaced = false
    extractionMarkerPlaced = false
    deployMarkerPlaced = false
    beaconObjective = nil
    beaconExtraction = nil
    beaconDeploy = nil
    briefingDismissed = false
    briefingReopenUntil = (Spring.GetGameFrame() or 0) + BRIEFING_SECONDS * 30
    local kind, zone = tostring(reason or ""):match("([^|]+)|?(.*)")
    zone = zone or ""
    missionCard = {
      situation = "Chapter " .. tostring(continueChapter) .. " - same map. Warband carries forward.",
      objective = "Next contract: " .. tostring(kind or "push") .. (zone ~= "" and (" at " .. zone) or ""),
      howToWin = "Use surviving heroes and units. Hold or demolish, then extract.",
      howItEnds = "Soft clock about 10 minutes. Watch the HUD countdown.",
      threats = "Fresh enemy garrison at the new target.",
      allies = "Your force is still in the field.",
      plainObjective = tostring(reason or "continue"),
    }
    if mission then
      mission.title = missionCard.objective
      mission.deploymentMapId = mission.deploymentMapId or currentMissionMapId()
      if mission.objective then
        mission.objective.description = missionCard.plainObjective
        mission.objective.kind = kind or mission.objective.kind
        mission.objective.targetZoneId = (zone ~= "" and zone) or mission.objective.targetZoneId
      end
      -- Rebuild debrief candidates for the next soft terminal (nearest zones).
      local okZm, zm = pcall(VFS.Include, "singleplayer/verdance_ashes/generated/zone_map_current.lua")
      local cands = {}
      if okZm and type(zm) == "table" and type(zm.zones) == "table" and zone ~= "" then
        local kinds = { "seize_lane", "eco_raid", "strike_relay" }
        local mapId = tostring(mission.deploymentMapId or zm.mapId or "")
        local n = 0
        for _, z in ipairs(zm.zones) do
          if z.zoneId and z.zoneId ~= zone then
            n = n + 1
            if n <= 3 then
              local k = kinds[((n - 1) % #kinds) + 1]
              cands[#cands + 1] = {
                id = "cand_" .. n .. "_" .. z.zoneId,
                title = k .. " - " .. tostring(z.label or z.zoneId),
                plain = "Next: " .. k .. " on " .. tostring(z.label or z.zoneId) .. " (adjacent).",
                mapId = mapId,
                targetZoneId = z.zoneId,
                fromZoneIds = { zone },
                objectiveArchetype = k,
                patron = "nullmercs",
                against = "armada",
              }
            end
          end
        end
      end
      cands = injectModeBTravelCandidates(cands)
      if #cands > 0 then
        nextMissionCandidates = cands
        mission.nextMissionCandidates = cands
      end
    end
    playUi("beep4", 1.0)
    queueBark("", "Next contract is live. Space dismisses briefing.")
    Spring.Echo("VA_UI_CONTINUE_START " .. tostring(reason))
  elseif eventStatus == "map_change_required" then
    continueMessage = "Mode B travel required (" .. tostring(reason)
      .. "). Exit BAR — session host Reload path loads the new map."
    playUi("warning1", 0.8)
  end
end

function widget:VerdanceHeroEvent(event, heroId, name, critical, x, z)
  heroId = tostring(heroId or "")
  local rec = heroRoster[heroId]
  if not rec then
    rec = { name = tostring(name or heroId), missionCritical = (critical == 1), state = "alive", everDown = false }
    heroRoster[heroId] = rec
  end
  if event == "down" then
    rec.state = "down"
    rec.everDown = true
    heroBanner = {
      text = string.upper(rec.name) .. " IS DOWN - recover the wreck!",
      critical = rec.missionCritical,
    }
    if x and z and x > 0 then
      heroWreckBeacon = { x = x, z = z, name = rec.name }
      pcall(Spring.MarkerAddPoint, x, groundY(x, z), z, rec.name .. " is down - recover the wreck", true)
    end
    playUi("warning2", 0.95)
  elseif event == "recovered" then
    rec.state = "alive"
    heroBanner = nil
    heroWreckBeacon = nil
    playUi("beep4", 1.0)
    queueBark("", rec.name .. " is back on their feet.")
  elseif event == "lost" then
    rec.state = "lost"
    heroBanner = nil
    heroWreckBeacon = nil
    if not rec.missionCritical then
      playUi("warning1", 1.0)
      queueBark("", rec.name .. " is gone. The line will remember.")
    end
  end
end

function widget:VerdanceBeat(kind, a, b, c, d)
  if kind == "bark" then
    queueBark(a, b, c)
  elseif kind == "marker" then
    pcall(Spring.MarkerAddPoint, a, b, c, tostring(d or ""), true)
  elseif kind == "sound" then
    playUi(a, tonumber(b) or 1.0)
  elseif kind == "wave_warning" then
    pcall(Spring.MarkerAddPoint, a, b, c, "Enemy reinforcements: " .. tostring(d or ""), true)
    playUi("warning2", 0.85)
  elseif kind == "tech_locked" then
    -- Act tech gate denial (a = unitDef name, b = "structures" | "tN").
    local line
    if tostring(b) == "structures" then
      line = "No base laying this act — ground control doctrine. Fight with what you brought."
    else
      line = "Fabrication cap: " .. tostring(a or "that unit") .. " is beyond this act's tech. Earned units only."
    end
    queueBark("Doctrine", line, 6)
    playUi("warning1", 0.7)
  end
end
