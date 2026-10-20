local widget = widget

function widget:GetInfo()
  return {
    name = "Verdance Objectives HUD",
    desc = "Mission briefing, objectives, narrative sidebar cam, beats, heroes, and the EXTRACT button for Verdance's Ashes",
    author = "Claude / Luke Spooner",
    date = "2026-07-12",
    license = "GPL v2 or later",
    layer = -20000,
    enabled = true,
  }
end

local mission
local briefingLines = {}
local missionCard = nil   -- WO-031 plain-English card
local missionTitle = "Verdance's Ashes"
local storyReason = nil
local difficultyLabel = nil
local lastPoll = 0
local briefingDismissed = false
local briefingReopenUntil = 0
local briefingOpenedAt = 0
local briefingAutoStarted = false
local playerBeganSortie = false
local sawStartPaused = false
local holdStartPause = true
local lastPauseAssertAt = 0
local followCamEnabled = false
local followUnitID = nil
local followCamRect = nil   -- {x1,y1,x2,y2} click target for watch toggle
local followViewRect = nil  -- sidebar PiP viewport (never drives main camera)
local followViewCenter = nil -- {x,z} world center of sidebar view
local followViewRadius = 1400 -- elmos half-width of sidebar minimap crop
local followViewRadiusIdle = 1800
-- Narrative cam = steered built-in map view ($minimap crop + BAR PIP if present).
-- Never calls Spring.SetCameraTarget on the main camera.
local narrativeQueue = {}     -- FIFO of narrative beats
local narrativeActive = nil   -- currently playing beat
local narrativeHighlightUntil = 0  -- gameframe; pulse OBJECTIVES text
local narrativeDiscovered = {} -- key -> true (one-shot discoveries)
local narrativeObjShown = false
local narrUserSteering = false -- player panned/zoomed; hold until next beat
local narrPanDrag = nil        -- { lastX, lastY } while dragging the crop
local narrPipSteeredAt = 0
local leftRailRectCache = nil
local extractButtonRect = nil  -- mid-mission EXTRACT click target (sends VA_CMD:manifest)
local vsx, vsy = Spring.GetViewGeometry()
-- Forward decl: Update runs before the body below is assigned (Lua local scope).
local poll

local BRIEFING_SECONDS = 45
local PRESENCE_HOLD_DEFAULT = 900
local NARRATIVE_LERP = 0.12
local NARRATIVE_DISCOVER_PERIOD = 20  -- frames between LOS discovery sweeps

local state = {
  status = "inactive",
  objectiveTotal = 0,
  objectiveDestroyed = 0,
  objectiveComplete = false,
  terminal = false,
  sortieOver = false,   -- set by VERDANCE_MISSION_EVENT "sortie_over"; exfil widget owns the closing card
  zoneHold = 0,
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
local refreshHeroDownBanner   -- forward: open recover/recruit secondaries → banner

-- World beacons + one-shot minimap markers for objective/extraction/landing.
local objectiveMarkerPlaced = false
local extractionMarkerPlaced = false
local deployMarkerPlaced = false
local secondaryMarkerDone = {}  -- index -> true (supports mid-mission hero-down marks)
local presentSecondary  -- defined after COL
local beaconObjective = nil   -- { x, z }
local beaconExtraction = nil  -- { x, z }
local beaconDeploy = nil      -- { x, z } enfil / landing
-- Stage-gated route (hub theater arrows, one stage at a time).
-- push: enfil→obj | marks: obj→next required | extract: last→exfil
local routeStage = nil          -- "push" | "marks" | "extract" | nil
local routeStageDrawn = nil     -- last stage we stamped as a persistent map line
local routeFrom = nil           -- { x, z, label }
local routeTo = nil             -- { x, z, label }
local stratOverlay = false      -- F9 strategic / objective overlay (minimap-like)
local stratZones = nil          -- cached zone rects for overlay
local ourMapMarkers = {}        -- {x,z} list we placed — player can /vaclear
-- Forward decls (KeyPress / TextCommand call these before the bodies below).
local toggleStratOverlay
local refreshRouteStage

-- Ash Console tokens (docs/UI_ASH_CONSOLE.md) — shared feel with hub HTML.
local Ash
do
  local ok, mod = pcall(VFS.Include, "luaui/Include/va_ash_tokens.lua")
  if not ok or type(mod) ~= "table" then
    ok, mod = pcall(VFS.Include, "LuaUI/Include/va_ash_tokens.lua")
  end
  Ash = (ok and type(mod) == "table") and mod or nil
end

-- Compatibility aliases (same names older draw code used).
local COL = Ash and {
  bg = Ash.COL.bg,
  panel = Ash.COL.panel,
  edge = { Ash.COL.edge[1], Ash.COL.edge[2], Ash.COL.edge[3], 0.55 },
  title = Ash.COL.gold,
  text = Ash.COL.ink,
  ink = Ash.COL.ink,
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
  bg = { 0.016, 0.035, 0.027, 1.0 },
  panel = { 0.031, 0.063, 0.047, 0.90 },
  edge = { 0.239, 0.561, 0.333, 0.55 },
  title = { 0.831, 0.769, 0.604 },
  text = { 0.933, 0.965, 0.933 },
  ink = { 0.933, 0.965, 0.933 },
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

-- Presentation from mark kind + subtype (synced registry). No label sniffing.
local SEC_PRESENT = {
  hero_recover = { marker = "++ RECOVER: ", rail = "RECOVER ", color = "bad" },
  vault        = { marker = "++ OPTIONAL VAULT: ", rail = "VAULT ", color = "gold" },
  structure    = { marker = "++ BONUS: ", rail = "+ ", color = "dim" },
}
presentSecondary = function(sec)
  sec = sec or {}
  local kind = tostring(sec.kind or "")
  if kind == "" then
    kind = (tostring(sec.id or "")):find("^hero_down_") and "hero_recover" or "structure"
  end
  local p = SEC_PRESENT[kind] or SEC_PRESENT.structure
  local marker, rail, colorKey = p.marker, p.rail, p.color
  if sec.req then
    marker, rail, colorKey = "++ REQUIRED: ", "[!] ", "warn"
  end
  if kind == "hero_recover" and tostring(sec.subtype or "") == "recruit" then
    marker, rail = "++ RECRUIT: ", "REZ "
  end
  local col = COL.dim
  if sec.failed then
    col = COL.bad or COL.warn
    rail = "FAIL "
  elseif sec.done then
    col = COL.good
    rail = "DONE "
  elseif colorKey == "bad" then
    col = COL.bad or COL.warn
  elseif colorKey == "warn" then
    col = COL.warn
  elseif colorKey == "gold" then
    col = COL.gold or COL.title
  end
  return {
    kind = kind,
    markerTag = marker,
    railPrefix = rail,
    color = col,
    isHeroRecover = kind == "hero_recover",
    failed = sec.failed == true,
  }
end

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

barkQueue.log = {}
barkQueue.lastAmbientFrame = -900
local function queueBark(speaker, textStr, seconds, ambient)
  local frame = Spring.GetGameFrame() or 0
  barkQueue.log[#barkQueue.log + 1] = {speaker = tostring(speaker or ""), text = tostring(textStr or "")}
  if #barkQueue.log > 60 then table.remove(barkQueue.log, 1) end
  -- Ambient lines are retained in /valog even when urgent orders own the screen.
  if ambient and (frame - barkQueue.lastAmbientFrame < 450 or #barkQueue > 0) then return end
  if ambient then barkQueue.lastAmbientFrame = frame end
  local entry = {
    speaker = tostring(speaker or ""),
    text = tostring(textStr or ""),
    seconds = tonumber(seconds) or 7,
  }
  if ambient then barkQueue[#barkQueue + 1] = entry
  else table.insert(barkQueue, 1, entry) end
end

-- Sidebar narrative camera beat. Zooms the PiP only — never the main view.
-- kind: "discover" | "objective" | "hero" | "threat" | "contact" | "story"
local function queueNarrative(opts)
  if type(opts) ~= "table" then return end
  local x = tonumber(opts.x)
  local z = tonumber(opts.z)
  if not x or not z then return end
  local key = opts.key
  if key then
    if narrativeDiscovered[key] then return end
    narrativeDiscovered[key] = true
  end
  narrativeQueue[#narrativeQueue + 1] = {
    kind = tostring(opts.kind or "story"),
    x = x,
    z = z,
    title = tostring(opts.title or "SCOUT REPORT"),
    body = tostring(opts.body or ""),
    radius = tonumber(opts.radius) or 620,
    seconds = tonumber(opts.seconds) or 6,
    highlightObjective = opts.highlightObjective == true,
    unitID = opts.unitID,
    featureID = opts.featureID,
    untilFrame = nil,
  }
end

local function narrativeBusy()
  return narrativeActive ~= nil or #narrativeQueue > 0
end

local function startNextNarrative()
  if narrativeActive then return end
  local beat = table.remove(narrativeQueue, 1)
  if not beat then return end
  local frame = Spring.GetGameFrame() or 0
  beat.untilFrame = frame + math.max(2, (beat.seconds or 6) * 30)
  narrativeActive = beat
  if beat.highlightObjective then
    narrativeHighlightUntil = beat.untilFrame
  end
  if beat.unitID and Spring.ValidUnitID and Spring.ValidUnitID(beat.unitID) then
    followUnitID = beat.unitID
  end
  -- Narrative always lights the sidebar lens so the player sees the zoom.
  followCamEnabled = true
  playUi("beep4", 0.4)
  Spring.Echo("VA_UI_NARRATIVE kind=" .. tostring(beat.kind)
    .. " title=" .. tostring(beat.title):sub(1, 40))
end

-- Steer BAR Picture-in-Picture if the player has it enabled (built-in cam).
-- Never touches the main camera.
local function steerBuiltInPip(x, z, radius)
  if not x or not z then return end
  local now = os.clock()
  if now - (narrPipSteeredAt or 0) < 0.2 then return end
  narrPipSteeredAt = now
  local zoom = math.max(0.08, math.min(0.85, 1100 / math.max(400, radius or followViewRadius)))
  if WG then
    for i = 1, 3 do
      local pip = WG["pip" .. i]
      if pip and type(pip.SetCamera) == "function" then
        pcall(pip.SetCamera, x, z, zoom, 0.4)
        return
      end
    end
  end
  if Script and Script.LuaUI then
    for i = 1, 3 do
      local fn = Script.LuaUI["PIPSetCamera" .. i]
      if type(fn) == "function" then
        pcall(fn, x, z, zoom, 0.4)
        return
      end
    end
  end
end

local function updateNarrativeCam()
  local frame = Spring.GetGameFrame() or 0
  if narrativeActive then
    if frame >= (narrativeActive.untilFrame or 0) then
      narrativeActive = nil
      startNextNarrative()
    end
  else
    startNextNarrative()
  end

  local targetX, targetZ, targetR
  if narrativeActive then
    narrUserSteering = false
    targetX, targetZ = narrativeActive.x, narrativeActive.z
    targetR = narrativeActive.radius or 900
    if narrativeActive.unitID and Spring.ValidUnitID and Spring.ValidUnitID(narrativeActive.unitID) then
      local ux, _, uz = Spring.GetUnitPosition(narrativeActive.unitID)
      if ux then targetX, targetZ = ux, uz end
    end
  elseif not narrUserSteering and followCamEnabled and routeTo then
    -- LIVE = look toward the current route stage (useful objective view).
    targetX, targetZ = routeTo.x, routeTo.z
    targetR = followViewRadiusIdle
  elseif not narrUserSteering and followCamEnabled and followUnitID
      and Spring.ValidUnitID and Spring.ValidUnitID(followUnitID) then
    local ux, _, uz = Spring.GetUnitPosition(followUnitID)
    if ux then
      targetX, targetZ = ux, uz
      targetR = followViewRadiusIdle
    end
  end

  if targetX and targetZ then
    if not followViewCenter then
      followViewCenter = { x = targetX, z = targetZ }
    else
      local t = NARRATIVE_LERP
      followViewCenter.x = followViewCenter.x + (targetX - followViewCenter.x) * t
      followViewCenter.z = followViewCenter.z + (targetZ - followViewCenter.z) * t
    end
    followViewRadius = followViewRadius + ((targetR or followViewRadiusIdle) - followViewRadius) * NARRATIVE_LERP
    if followCamEnabled or narrativeActive then
      steerBuiltInPip(followViewCenter.x, followViewCenter.z, followViewRadius)
    end
  elseif not followViewCenter then
    local dx = tonumber((Spring.GetGameRulesParam("va_deploy_x"))) or -1
    local dz = tonumber((Spring.GetGameRulesParam("va_deploy_z"))) or -1
    if dx >= 0 and dz >= 0 then
      followViewCenter = { x = dx, z = dz }
    elseif routeTo then
      followViewCenter = { x = routeTo.x, z = routeTo.z }
    end
  end
end

local function posInLos(x, z)
  if not x or not z then return false end
  local myAlly = Spring.GetLocalAllyTeamID and Spring.GetLocalAllyTeamID() or Spring.GetMyAllyTeamID()
  local y = (Spring.GetGroundHeight and Spring.GetGroundHeight(x, z)) or 0
  if Spring.GetPositionLosState then
    local ok, any, los, radar = pcall(Spring.GetPositionLosState, x, y, z, myAlly)
    if ok then return any or los or radar end
  end
  return true
end

-- Scout discovery: first LOS on Tnb shards, named heroes, merc contacts.
local function sweepNarrativeDiscoveries()
  if state.terminal then return end
  local frame = Spring.GetGameFrame() or 0
  if frame < 90 then return end
  if frame % NARRATIVE_DISCOVER_PERIOD ~= 0 then return end

  -- Valuable Tenebrium wrecks / shards entering sight.
  if Spring.GetAllFeatures then
    for _, fid in ipairs(Spring.GetAllFeatures() or {}) do
      local amt = Spring.GetFeatureRulesParam and Spring.GetFeatureRulesParam(fid, "va_tenebrium_amount")
      local shard = Spring.GetFeatureRulesParam and Spring.GetFeatureRulesParam(fid, "va_tenebrium_shard")
      amt = tonumber(amt) or 0
      if (amt > 0 or (tonumber(shard) or 0) > 0) then
        local key = "tnb_f_" .. tostring(fid)
        if not narrativeDiscovered[key] then
          local fx, _, fz = Spring.GetFeaturePosition(fid)
          if fx and posInLos(fx, fz) then
            local body = amt > 0
              and string.format("Valuable wreck — %d Tnb still in the field.", math.floor(amt))
              or "Tenebrium signature on a field wreck. Reclaim it."
            queueNarrative({
              key = key,
              kind = "discover",
              x = fx, z = fz,
              title = "SCOUT: TENEBRIIUM",
              body = body,
              radius = 520,
              seconds = 5.5,
            })
          end
        end
      end
      -- Hero wrecks: share key with VerdanceHeroEvent("down") so scout + event don't double.
      local heroName = Spring.GetFeatureRulesParam and Spring.GetFeatureRulesParam(fid, "va_hero_wreck_name")
      if heroName and tostring(heroName) ~= "" and tostring(heroName) ~= "0" then
        local heroId = Spring.GetFeatureRulesParam(fid, "va_hero_wreck")
        local key = (heroId and tostring(heroId) ~= "" and tostring(heroId) ~= "0")
          and ("hero_down_" .. tostring(heroId))
          or ("hero_wreck_f_" .. tostring(fid))
        if not narrativeDiscovered[key] then
          local fx, _, fz = Spring.GetFeaturePosition(fid)
          if fx and posInLos(fx, fz) then
            queueNarrative({
              key = key,
              kind = "hero",
              x = fx, z = fz,
              title = "SCOUT: DOWNED HERO",
              body = tostring(heroName) .. " — wreck still recoverable. Get a rez bot on it.",
              radius = 480,
              seconds = 6,
            })
          end
        end
      end
    end
  end

  -- Recruitable / contact units (merc foothold, tagged contacts) entering LOS.
  local myAlly = Spring.GetLocalAllyTeamID and Spring.GetLocalAllyTeamID() or Spring.GetMyAllyTeamID()
  for _, teamID in ipairs(Spring.GetTeamList() or {}) do
    local ally = Spring.GetTeamAllyTeamID and Spring.GetTeamAllyTeamID(teamID)
    for _, uid in ipairs(Spring.GetTeamUnits(teamID) or {}) do
      local contact = Spring.GetUnitRulesParam(uid, "va_contact")
        or Spring.GetUnitRulesParam(uid, "va_recruitable")
        or Spring.GetUnitRulesParam(uid, "va_merc_contact")
      local role = Spring.GetUnitRulesParam(uid, "va_force_role")
      local isContact = (tonumber(contact) or 0) > 0
        or tostring(role or "") == "merc_foothold"
        or tostring(role or "") == "recruitable"
      if isContact then
        local key = "contact_u_" .. tostring(uid)
        if not narrativeDiscovered[key] then
          local ux, _, uz = Spring.GetUnitPosition(uid)
          local inLos = true
          if Spring.IsUnitInLos then
            inLos = Spring.IsUnitInLos(uid, myAlly)
          elseif ux then
            inLos = posInLos(ux, uz)
          end
          if ux and inLos then
            local defID = Spring.GetUnitDefID(uid)
            local def = defID and UnitDefs[defID]
            local label = (def and (def.humanName or def.name)) or "contact"
            local heroName = Spring.GetUnitRulesParam(uid, "va_hero_name")
            local recruitable = (tonumber((Spring.GetUnitRulesParam(uid, "va_recruitable"))) or 0) > 0
            local title = recruitable and "SCOUT: RECRUITABLE" or "SCOUT: CONTACT"
            local body
            if recruitable and heroName and tostring(heroName) ~= "" then
              body = tostring(heroName) .. " — wreck them, rez with Ketha, bring them home."
            elseif recruitable then
              body = "Named recruit — wreck & rez to sign them onto the company."
            else
              body = "Recruitable presence — " .. tostring(label) .. ". Worth a look."
            end
            queueNarrative({
              key = key,
              kind = "contact",
              x = ux, z = uz,
              title = title,
              body = body,
              radius = 560,
              seconds = 7,
              unitID = uid,
            })
          end
        end
      end
    end
  end

  -- First look at the live objective once the sortie is underway.
  if not narrativeObjShown and playerBeganSortie and beaconObjective
      and not state.objectiveComplete then
    local ox, oz = beaconObjective.x, beaconObjective.z
    if ox and posInLos(ox, oz) then
      narrativeObjShown = true
      local desc = mission and mission.objective and mission.objective.description
      queueNarrative({
        key = "objective_first_look",
        kind = "objective",
        x = ox, z = oz,
        title = "OBJECTIVE MARK",
        body = tostring(desc or "Primary mark is live. Push the line."),
        radius = 780,
        seconds = 5,
        highlightObjective = true,
      })
    elseif ox and frame > 180 and frame < 240 then
      -- Soft nudge even before LOS — briefing emphasis after pause lifts.
      narrativeObjShown = true
      local desc = mission and mission.objective and mission.objective.description
      queueNarrative({
        key = "objective_open",
        kind = "objective",
        x = ox, z = oz,
        title = "OBJECTIVE",
        body = tostring(desc or "Primary mark is live."),
        radius = 900,
        seconds = 4.5,
        highlightObjective = true,
      })
    end
  end
end

function widget:Initialize()
  briefingOpenedAt = os.time()
  mission = readMission()
  if not mission then
    Spring.Echo("VA_UI_OBJECTIVES_NO_MISSION — HUD will stay blank until va_current.lua loads")
  end
  if mission then
    Spring.Echo("VA_UI_OBJECTIVES_ARMED v2026-10-02g mission=" .. tostring(mission.missionId or mission.title or "?"))
    missionTitle = mission.title or missionTitle
    local intent = mission.storyIntent or {}
    -- The compiler title includes map/variant metadata for files and logs;
    -- the player-facing brief should use the authored story title instead.
    missionTitle = intent.title or missionTitle
    -- WO-031: prefer seed missionCard; fall back to intent.missionCard.
    if type(mission.missionCard) == "table" then
      missionCard = mission.missionCard
    elseif type(intent.missionCard) == "table" then
      missionCard = intent.missionCard
    end
    -- Ketha flavor lines stay for optional reopen; not the main intro.
    if type(intent.briefing) == "table" and type(intent.briefing.lines) == "table" then
      briefingLines = intent.briefing.lines
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
    -- Hero manifest: names the HUD tracks through hero events.
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
  -- F9 strategic overlay — free in modern BAR grid (F5–F8/F10–F12 taken).
  pcall(function()
    widgetHandler:AddAction(widget, "va_strat_overlay", function()
      if toggleStratOverlay then toggleStratOverlay() end
      return true
    end, nil, "t")
    Spring.SendCommands("bind Any+f9 va_strat_overlay")
  end)
  Spring.Echo("VA_UI_STRAT_OVERLAY bound to F9 · /vaoverlay · /vaclear")
end

local function gameIsPaused()
  if Spring.IsGamePaused then
    return Spring.IsGamePaused() == true
  end
  local _, _, paused = Spring.GetGameSpeed()
  return paused == true
end

local function pickWatchUnit()
  local myTeam = Spring.GetLocalTeamID and Spring.GetLocalTeamID() or Spring.GetMyTeamID()
  if myTeam == nil then return nil end
  local units = Spring.GetTeamUnits(myTeam) or {}
  local best, bestScore = nil, -1
  for i = 1, #units do
    local uid = units[i]
    local hp, maxHp = Spring.GetUnitHealth(uid)
    if hp and maxHp and maxHp > 0 and hp > 0 then
      local defID = Spring.GetUnitDefID(uid)
      local def = defID and UnitDefs[defID] or nil
      local cost = def and (tonumber(def.metalCost) or 0) or 0
      local vuln = 1.0 - (hp / maxHp)
      local score = cost * (0.25 + vuln)
      local hero = Spring.GetUnitRulesParam(uid, "va_hero_id")
      if hero and tostring(hero) ~= "" and tostring(hero) ~= "0" then
        score = score * 3.2
      end
      if def and def.canResurrect then score = score * 2.6 end
      if def and def.isBuilder and not def.isFactory then score = score * 1.6 end
      if def and def.customParams and def.customParams.iscommander then score = score * 4 end
      if score > bestScore then
        bestScore = score
        best = uid
      end
    end
  end
  return best
end

local function updateFollowCam()
  -- Sidebar narrative / watch only. NEVER call Spring.SetCameraTarget.
  if state.terminal then
    followUnitID = nil
    followViewCenter = nil
    narrativeActive = nil
    narrativeQueue = {}
    return
  end
  if followUnitID and Spring.ValidUnitID and not Spring.ValidUnitID(followUnitID) then
    followUnitID = nil
  end
  -- While a narrative beat owns the lens, do not steal focus back to HVU.
  if not narrativeBusy() then
    if not followUnitID or (Spring.GetGameFrame() or 0) % 45 == 0 then
      followUnitID = pickWatchUnit()
    end
  end
  sweepNarrativeDiscoveries()
  updateNarrativeCam()
end

-- Fold the other teams once per match. Click the Enemies header to open them.
-- The stock list has no setter; the flag is a local, shared by its callins.
local function collapseEnemyTeams()
  if widget._vaEnemyListCollapsed then return end
  widget._vaEnemyListTries = (widget._vaEnemyListTries or 0) + 1
  if widget._vaEnemyListTries > 120 then
    widget._vaEnemyListCollapsed = true
    return
  end
  if not (widgetHandler and widgetHandler.FindWidget and debug and debug.getupvalue and debug.setupvalue) then
    return
  end
  local ok, changed = pcall(function()
    local listWidget = widgetHandler:FindWidget("AdvPlayersList")
    local probe = listWidget and (listWidget.MousePress or listWidget.GetConfigData)
    if not probe then return false end
    local wrote = false
    local index = 1
    while true do
      local name = debug.getupvalue(probe, index)
      if not name then break end
      if name == "enemyListShow" or name == "enemyListShowUserPref" then
        debug.setupvalue(probe, index, false)
        wrote = true
      end
      index = index + 1
    end
    if not wrote then return false end
    local env = getfenv(probe)
    if env then
      if env.SortList then env.SortList() end
      if env.SetModulesPositionX then env.SetModulesPositionX() end
      if env.CreateLists then env.CreateLists() end
    end
    return true
  end)
  if ok and changed then
    widget._vaEnemyListCollapsed = true
    Spring.Echo("VA_UI_TEAMLIST_MINIMIZED")
  end
end

-- Start paused and stay paused until the player hits BAR's pause key.
-- Space only closes the ephemeral briefing card — it must not begin the fight.
function widget:Update(dt)
  collapseEnemyTeams()
  -- End-of-sortie flow (manifest confirm, closing card, quit) is owned by
  -- gui_verdance_exfil.lua. This widget only sends VA_CMD:manifest on EXTRACT.

  -- Normal BAR feel: sortie must load PAUSED. Hammer pause until it sticks,
  -- then stop so the player can begin with the pause key. Do not treat the
  -- pre-pause race (frame 0 unpaused) as "sortie began".
  if holdStartPause and not state.terminal then
    if gameIsPaused() then
      sawStartPaused = true
      holdStartPause = false
      Spring.Echo("VA_UI_PAUSE_HELD frame=" .. tostring(Spring.GetGameFrame() or 0))
    else
      local now = os.clock()
      if (now - (lastPauseAssertAt or 0)) >= 0.15 then
        lastPauseAssertAt = now
        pcall(Spring.SendCommands, "pause 1")
      end
    end
  end

  if not playerBeganSortie and not state.terminal and sawStartPaused and not gameIsPaused() then
    playerBeganSortie = true
    Spring.Echo("VA_UI_SORTIE_BEGAN frame=" .. tostring(Spring.GetGameFrame() or 0))
  end

  -- Never let cam/poll glue remove the Objectives + Tnb HUD.
  pcall(updateFollowCam)
end

function widget:Shutdown()
  pcall(function()
    widgetHandler:DeregisterGlobal(widget, "VerdanceMissionEvent")
    widgetHandler:DeregisterGlobal(widget, "VerdanceHeroEvent")
    widgetHandler:DeregisterGlobal(widget, "VerdanceBeat")
  end)
  pcall(function()
    Spring.SendCommands("unbind Any+f9 va_strat_overlay")
    widgetHandler:RemoveAction(widget, "va_strat_overlay", "t")
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

local function rememberMarker(x, z)
  if x and z then ourMapMarkers[#ourMapMarkers + 1] = { x = x, z = z } end
end

local function clearOurMapMarkers()
  -- Spring has no reliable per-marker delete; wipe map marks/drawings.
  -- Player asked to clear — ~ eraser works too; this is the bulk path.
  if Spring.MarkerErasePosition then
    for _, m in ipairs(ourMapMarkers) do
      pcall(Spring.MarkerErasePosition, m.x, groundY(m.x, m.z), m.z, 80)
    end
  end
  if Spring.SendCommands then
    pcall(Spring.SendCommands, "clearmapmarks")
    pcall(Spring.SendCommands, "clearmapdrawings")
  end
  ourMapMarkers = {}
  routeStageDrawn = nil
  Spring.Echo("VA_UI_MARKS_CLEARED")
end

local function markCopy(key, fallback)
  return (Ash and Ash.MARK and Ash.MARK[key]) or fallback
end

local function placeMarkers()
  if not deployMarkerPlaced then
    local dx = numParam("va_deploy_x", -1)
    local dz = numParam("va_deploy_z", -1)
    if dx >= 0 and dz >= 0 then
      deployMarkerPlaced = true
      beaconDeploy = { x = dx, z = dz }
      pcall(Spring.MarkerAddPoint, dx, groundY(dx, dz), dz, markCopy("landing", ">>> LANDING (enfil) <<<"), true)
      rememberMarker(dx, dz)
    end
  end
  if not objectiveMarkerPlaced then
    local ox = numParam("va_objective_x", -1)
    local oz = numParam("va_objective_z", -1)
    if ox >= 0 and oz >= 0 then
      objectiveMarkerPlaced = true
      beaconObjective = { x = ox, z = oz }
      local label = (mission and mission.objective and mission.objective.description) or "Objective"
      pcall(Spring.MarkerAddPoint, ox, groundY(ox, oz), oz,
        markCopy("objective", "!!! OBJECTIVE: ") .. tostring(label), true)
      rememberMarker(ox, oz)
    end
  end
  -- Secondary marks — re-place when done so map text tracks registry.
  if (state.secondaryTotal or 0) > 0 then
    for i = 1, state.secondaryTotal do
      local sec = state.secondaries and state.secondaries[i]
      if sec and sec.x >= 0 and sec.z >= 0 then
        local doneKey = (sec.failed and "fail") or (sec.done and "done") or "open"
        if secondaryMarkerDone[i] ~= doneKey then
          local label = tostring(sec.label or ("mark " .. i))
          local pres = presentSecondary(sec)
          local tag = (sec.failed and "FAIL: ") or (sec.done and "DONE: ") or pres.markerTag
          pcall(Spring.MarkerAddPoint, sec.x, groundY(sec.x, sec.z), sec.z, tag .. label, true)
          rememberMarker(sec.x, sec.z)
          secondaryMarkerDone[i] = doneKey
        end
      end
    end
  end
  -- Extract LZ — single owner of Ash.MARK.extract.
  -- boardResolved = all marks done OR rescue contract failed (same as gadget).
  local ex = numParam("va_extract_x", -1)
  local ez = numParam("va_extract_z", -1)
  if ex >= 0 and ez >= 0 then
    beaconExtraction = { x = ex, z = ez }
    if not extractionMarkerPlaced then
      extractionMarkerPlaced = true
      local label = markCopy("extract", "EXTRACTION PAD - load it, then press EXTRACT")
      pcall(Spring.MarkerAddPoint, ex, groundY(ex, ez), ez, label, true)
      rememberMarker(ex, ez)
    end
  end
end

-- Next required secondary mark that still needs wrecking (objective→objective).
local function nextRequiredSecondary()
  if not state.secondaries then return nil end
  for i = 1, (state.secondaryTotal or 0) do
    local sec = state.secondaries[i]
    if sec and sec.req and not sec.done and sec.x and sec.x >= 0 and sec.z and sec.z >= 0 then
      return { x = sec.x, z = sec.z, label = sec.label or ("Mark " .. i) }
    end
  end
  -- Fall back to any unfinished secondary with coords.
  for i = 1, (state.secondaryTotal or 0) do
    local sec = state.secondaries[i]
    if sec and not sec.done and sec.x and sec.x >= 0 and sec.z and sec.z >= 0 then
      return { x = sec.x, z = sec.z, label = sec.label or ("Mark " .. i) }
    end
  end
  return nil
end

-- Lean theater route: only ONE stage of arrows live at a time.
refreshRouteStage = function()
  routeFrom, routeTo, routeStage = nil, nil, nil
  if state.terminal or not mission then return end

  local dep = beaconDeploy
  local obj = beaconObjective
  local ext = beaconExtraction
  local nextSec = nextRequiredSecondary()
  local requiredLeft = state.secondaryRequiredLeft or 0
  -- Same boardResolved as gadget: victory list done OR rescue contract failed.
  local boardResolved = state.allObjectivesDone or state.objectiveFailed

  -- Board resolved (all marks done or rescue failed): route to the pad.
  if ext and boardResolved then
    routeStage = "extract"
    local from = dep and { x = dep.x, z = dep.z, label = "COMPANY" } or nil
    if obj then from = { x = obj.x, z = obj.z, label = "OBJECTIVE" } end
    if state.secondaries then
      for i = (state.secondaryTotal or 0), 1, -1 do
        local sec = state.secondaries[i]
        if sec and sec.done and sec.x and sec.x >= 0 then
          from = { x = sec.x, z = sec.z, label = tostring(sec.label or "MARK"):upper() }
          break
        end
      end
    end
    routeFrom = from
    local label = "EXFIL"
    if state.objectiveFailed then
      label = "EXFIL (FAIL)"
    end
    routeTo = { x = ext.x, z = ext.z, label = label }
  elseif not state.objectiveComplete then
    -- PUSH: enfil → primary objective
    if dep and obj then
      routeStage = "push"
      routeFrom = { x = dep.x, z = dep.z, label = "ENFIL" }
      routeTo = { x = obj.x, z = obj.z, label = "OBJECTIVE" }
    elseif obj then
      routeStage = "push"
      routeFrom = nil
      routeTo = { x = obj.x, z = obj.z, label = "OBJECTIVE" }
    end
  elseif requiredLeft > 0 and nextSec then
    -- MARKS: primary (or last) → next required secondary
    routeStage = "marks"
    routeFrom = obj and { x = obj.x, z = obj.z, label = "OBJECTIVE" } or nil
    routeTo = { x = nextSec.x, z = nextSec.z, label = tostring(nextSec.label):upper() }
  elseif ext then
    -- EXTRACT: last mark → exfil
    routeStage = "extract"
    local from = nextSec -- shouldn't exist if requiredLeft==0
    if obj then from = { x = obj.x, z = obj.z, label = "OBJECTIVE" } end
    if state.secondaries then
      for i = (state.secondaryTotal or 0), 1, -1 do
        local sec = state.secondaries[i]
        if sec and sec.done and sec.x and sec.x >= 0 then
          from = { x = sec.x, z = sec.z, label = tostring(sec.label or "MARK"):upper() }
          break
        end
      end
    end
    routeFrom = from
    routeTo = { x = ext.x, z = ext.z, label = "EXFIL" }
  end

  -- Stamp a persistent map line once per stage so the drawing stays until
  -- the player clears it (~ eraser or /vaclear). Live GL arrows stay stage-fresh.
  if routeStage and routeStage ~= routeStageDrawn and routeFrom and routeTo then
    local y1 = groundY(routeFrom.x, routeFrom.z)
    local y2 = groundY(routeTo.x, routeTo.z)
    if Spring.MarkerAddLine then
      pcall(Spring.MarkerAddLine, routeFrom.x, y1, routeFrom.z, routeTo.x, y2, routeTo.z)
    end
    rememberMarker(routeFrom.x, routeFrom.z)
    rememberMarker(routeTo.x, routeTo.z)
    pcall(Spring.MarkerAddPoint, routeTo.x, y2, routeTo.z,
      string.format(">> %s → %s", routeFrom.label or "?", routeTo.label or "?"), true)
    rememberMarker(routeTo.x, routeTo.z)
    routeStageDrawn = routeStage
    Spring.Echo("VA_UI_ROUTE_STAGE " .. tostring(routeStage)
      .. " " .. tostring(routeFrom.label) .. "->" .. tostring(routeTo.label))
  end
  -- Share live route with zone minimap / other UI (unsynced WG table).
  if WG then
    WG.vaRoute = {
      stage = routeStage,
      from = routeFrom,
      to = routeTo,
    }
  end
end

-- Hub-style big route arrow on the ground: chevrons along the path + fat head.
-- Never uses SetCameraTarget. Replaces the old north-only chevron + circles.
local function drawBigRouteArrow(ax, az, bx, bz, r, g, b, a)
  if not ax or not bx then return end
  local dx, dz = bx - ax, bz - az
  local dist = math.sqrt(dx * dx + dz * dz)
  if dist < 60 then return end
  local ux, uz = dx / dist, dz / dist
  local px, pz = -uz, ux
  local pulse = 0.55 + 0.35 * math.abs(math.sin(os.clock() * 2.0))
  local alpha = (a or 0.9) * pulse
  local head = math.min(260, math.max(140, dist * 0.09))
  local chevrons = math.min(6, math.max(2, math.floor(dist / 750)))

  gl.LineWidth(4.5)
  for i = 1, chevrons do
    local t = (i + 0.15) / (chevrons + 0.6)
    local cx = ax + ux * dist * t
    local cz = az + uz * dist * t
    local y = groundY(cx, cz) + 10
    local hs = head * (0.55 + 0.45 * t)
    local fade = 0.35 + 0.65 * t
    gl.Color(r, g, b, alpha * fade)
    gl.BeginEnd(GL.LINES, function()
      gl.Vertex(cx - ux * hs * 0.4 + px * hs * 0.5, y, cz - uz * hs * 0.4 + pz * hs * 0.5)
      gl.Vertex(cx + ux * hs * 0.55, y, cz + uz * hs * 0.55)
      gl.Vertex(cx - ux * hs * 0.4 - px * hs * 0.5, y, cz - uz * hs * 0.4 - pz * hs * 0.5)
      gl.Vertex(cx + ux * hs * 0.55, y, cz + uz * hs * 0.55)
    end)
  end

  -- Fat arrow head at the destination (the "big arrow" from the theater board).
  local hy = groundY(bx, bz) + 12
  gl.Color(r, g, b, alpha)
  gl.LineWidth(5.5)
  gl.BeginEnd(GL.LINE_LOOP, function()
    gl.Vertex(bx, hy, bz)
    gl.Vertex(bx - ux * head - px * head * 0.55, hy, bz - uz * head - pz * head * 0.55)
    gl.Vertex(bx - ux * head * 0.4, hy, bz - uz * head * 0.4)
    gl.Vertex(bx - ux * head + px * head * 0.55, hy, bz - uz * head + pz * head * 0.55)
  end)
  -- Small destination pin (cross, not a circle).
  local pin = 55
  gl.LineWidth(3)
  gl.BeginEnd(GL.LINES, function()
    gl.Vertex(bx - pin, hy, bz); gl.Vertex(bx + pin, hy, bz)
    gl.Vertex(bx, hy, bz - pin); gl.Vertex(bx, hy, bz + pin)
  end)
  gl.LineWidth(1)
end

local function routeStageColor()
  if routeStage == "extract" then
    local c = COL.steam or COL.blue
    return c[1], c[2], c[3], 0.95
  elseif routeStage == "marks" then
    local c = COL.gold or COL.title
    return c[1], c[2], c[3], 0.95
  end
  local c = COL.warn
  return c[1], c[2], c[3], 0.95
end

poll = function()
  local sp = Spring.GetGameRulesParam
  state.objectiveTotal = numParam("va_objective_total", 0)
  state.objectiveDestroyed = numParam("va_objective_destroyed", 0)
  state.objectiveComplete = numParam("va_objective_complete", 0) == 1
  -- sortie_over latches terminal locally so route/cam gating holds even if
  -- the new synced flow never publishes va_terminal.
  state.terminal = state.sortieOver or numParam("va_terminal", 0) == 1
  state.zoneHold = numParam("va_zone_hold", 0)
  state.fortifyDef = numParam("va_fortify_def", 0)
  state.fortifyBp = numParam("va_fortify_bp", 0)
  state.fortifyArmy = numParam("va_fortify_army", 0)
  state.fortifyStorage = numParam("va_fortify_storage", 0)
  state.fortifyNeedDef = numParam("va_fortify_need_def", 0)
  state.fortifyNeedBp = numParam("va_fortify_need_bp", 0)
  state.fortifyNeedArmy = numParam("va_fortify_need_army", 0)
  state.fortifyNeedStorage = numParam("va_fortify_need_storage", 0)
  state.fortifyScore = numParam("va_fortify_score", 0)
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
  state.secondaryFailed = numParam("va_secondary_failed", 0)
  state.secondaryRequiredLeft = numParam("va_secondary_required_left", 0)
  state.purgeArmed = numParam("va_purge_armed", 0) == 1
  state.purgeDone = numParam("va_purge_done", 0) == 1
  state.allObjectivesDone = numParam("va_all_objectives_done", 0) == 1
  -- SoT: campaign latch va_objective_failed (rescue contract destroyed).
  state.objectiveFailed = numParam("va_objective_failed", 0) == 1
  do
    local fr = Spring.GetGameRulesParam("va_objective_fail_reason")
    if type(fr) == "string" then state.objectiveFailReason = fr end
    local fh = Spring.GetGameRulesParam("va_objective_fail_hero")
    if type(fh) == "string" then state.objectiveFailHero = fh end
  end
  state.secondaries = state.secondaries or {}
  for i = 1, state.secondaryTotal do
    local lbl = Spring.GetGameRulesParam("va_sec" .. i .. "_label")
    local sid = Spring.GetGameRulesParam("va_sec" .. i .. "_id")
    local kind = Spring.GetGameRulesParam("va_sec" .. i .. "_kind")
    local subtype = Spring.GetGameRulesParam("va_sec" .. i .. "_subtype")
    state.secondaries[i] = {
      id = (type(sid) == "string" and sid ~= "") and sid or nil,
      kind = (type(kind) == "string" and kind ~= "") and kind or "",
      subtype = (type(subtype) == "string" and subtype ~= "") and subtype or "",
      label = (type(lbl) == "string" and lbl ~= "") and lbl or ("Mark " .. i),
      req = numParam("va_sec" .. i .. "_req", 0) == 1,
      done = numParam("va_sec" .. i .. "_done", 0) == 1,
      failed = numParam("va_sec" .. i .. "_failed", 0) == 1,
      x = numParam("va_sec" .. i .. "_x", -1),
      z = numParam("va_sec" .. i .. "_z", -1),
    }
  end
  state.mercsAvailable = numParam("va_mercs_available", 0) == 1
  state.tenebriumLooted = numParam("va_tenebrium_looted", 0)
  state.tenebriumBank = numParam("va_tenebrium_bank", 0)
  state.tenebriumSpent = numParam("va_tenebrium_spent", 0)
  state.tenebriumLost = numParam("va_tenebrium_lost", 0)
  state.tenebriumWrecksCreated = numParam("va_tenebrium_wrecks_created", 0)
  state.tenebriumWrecksClaimed = numParam("va_tenebrium_wrecks_claimed", 0)
  state.tenebriumWrecksLost = numParam("va_tenebrium_wrecks_lost", 0)
  state.tenebriumWrecksUnclaimed = numParam("va_tenebrium_wrecks_unclaimed", 0)
  state.armadaTenebriumCrisis = numParam("va_armada_tenebrium_crisis", 1) == 1
  state.requiredFrames = numParam("va_required_frames", state.requiredFrames or 19800)
  state.holdFrames = numParam("va_hold_frames", 0)
  local st = sp("va_status")
  if type(st) == "string" and st ~= "" then state.status = st end
  placeMarkers()
  refreshRouteStage()
  if refreshHeroDownBanner then refreshHeroDownBanner() end
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

local function pointInRect(x, y, r)
  return r and x >= r.x1 and x <= r.x2 and y >= r.y1 and y <= r.y2
end

function widget:KeyPress(key)
  -- After sortie_over the exfil widget owns input; this HUD stays out of the way.
  if state.sortieOver then return false end
  -- Space / Esc dismiss the briefing card only. Do not touch pause.
  if not briefingDismissed and (key == 32 or key == 27) and not state.terminal then
    briefingDismissed = true
    briefingReopenUntil = 0
    briefingAutoStarted = true
    Spring.Echo("VA_UI_BRIEFING_DISMISS key=" .. tostring(key))
    return true
  end
  -- F9 fallback if action bind missed (primary path is AddAction Any+f9).
  if not state.terminal and toggleStratOverlay then
    local f9 = (Spring.GetKeyCode and Spring.GetKeyCode("f9")) or 290
    if key == f9 or key == 290 then
      return toggleStratOverlay()
    end
  end
  return false
end

function widget:MouseMove(x, y)
  if narrPanDrag and followViewCenter and followViewRect then
    local dx = x - narrPanDrag.lastX
    local dy = y - narrPanDrag.lastY
    narrPanDrag.lastX, narrPanDrag.lastY = x, y
    local vw = math.max(1, followViewRect.x2 - followViewRect.x1)
    local vh = math.max(1, followViewRect.y2 - followViewRect.y1)
    local aspect = vw / vh
    local halfZ = followViewRadius
    local halfX = halfZ * aspect
    -- Drag right → look left (grab the map).
    followViewCenter.x = followViewCenter.x - (dx / vw) * (halfX * 2)
    followViewCenter.z = followViewCenter.z - (dy / vh) * (halfZ * 2)
    local mapX = Game.mapSizeX or 1
    local mapZ = Game.mapSizeZ or 1
    followViewCenter.x = math.max(0, math.min(mapX, followViewCenter.x))
    followViewCenter.z = math.max(0, math.min(mapZ, followViewCenter.z))
    steerBuiltInPip(followViewCenter.x, followViewCenter.z, followViewRadius)
    return true
  end
  return false
end

function widget:MousePress(x, y, button)
  if state.sortieOver then return false end
  -- Drag inside the narrative minimap crop to steer (does not toggle LIVE).
  if button == 1 and followViewRect and pointInRect(x, y, followViewRect) then
    followCamEnabled = true
    narrPanDrag = { lastX = x, lastY = y }
    narrUserSteering = true
    return true
  end
  if button == 1 and followCamRect and pointInRect(x, y, followCamRect)
      and not (followViewRect and pointInRect(x, y, followViewRect)) then
    followCamEnabled = not followCamEnabled
    if followCamEnabled then
      narrUserSteering = false
      followUnitID = pickWatchUnit()
      Spring.Echo("VA_UI_NARRATIVE_CAM on (built-in map crop / PIP steer)")
    else
      Spring.Echo("VA_UI_NARRATIVE_CAM off")
    end
    return true
  end
  -- EXTRACT: ask synced for the manifest. gui_verdance_exfil.lua receives
  -- VerdanceManifest and owns pause / confirm / closing card from there.
  if button == 1 and extractButtonRect and pointInRect(x, y, extractButtonRect) and not state.terminal then
    Spring.SendLuaRulesMsg("VA_CMD:manifest")
    Spring.Echo("VA_UI_EXTRACT_PRESSED frame=" .. tostring(Spring.GetGameFrame() or 0))
    return true
  end
  return false
end

function widget:MouseRelease(x, y, button)
  if narrPanDrag then
    narrPanDrag = nil
    return true
  end
  return false
end

function widget:MouseWheel(up, value)
  local mx, my = Spring.GetMouseState()
  if not followViewRect or not pointInRect(mx, my, followViewRect) then
    return false
  end
  followCamEnabled = true
  narrUserSteering = true
  local factor = up and 0.85 or 1.18
  followViewRadius = math.max(400, math.min(6000, followViewRadius * factor))
  if followViewCenter then
    steerBuiltInPip(followViewCenter.x, followViewCenter.z, followViewRadius)
  end
  return true
end

function widget:TextCommand(command)
  if command == "valog" then
    Spring.Echo("Company field log (recent observations):")
    for _, entry in ipairs(barkQueue.log) do
      Spring.Echo(entry.speaker .. ": " .. entry.text)
    end
    return true
  end
  if command == "vabrief" then
    -- Re-open the briefing card for another read.
    briefingDismissed = false
    briefingReopenUntil = (Spring.GetGameFrame() or 0) + BRIEFING_SECONDS * 30
    return true
  end
  if command == "vawatch" or command == "vafollow" then
    followCamEnabled = not followCamEnabled
    if followCamEnabled then followUnitID = pickWatchUnit() end
    Spring.Echo("VA_UI_WATCHVIEW " .. (followCamEnabled and "on" or "off") .. " (sidebar only)")
    return true
  end
  if command == "vaoverlay" or command == "vastrat" or command == "vastrategic" then
    return toggleStratOverlay()
  end
  if command == "vaclear" or command == "vaclearmarks" then
    clearOurMapMarkers()
    return true
  end
  if command == "vanarrative" or command:match("^vanarrative%s") then
    -- Dev/test: fire a narrative cam beat at the objective (or deploy).
    local ox = beaconObjective and beaconObjective.x
    local oz = beaconObjective and beaconObjective.z
    if not ox then
      ox = tonumber((Spring.GetGameRulesParam("va_deploy_x"))) or 0
      oz = tonumber((Spring.GetGameRulesParam("va_deploy_z"))) or 0
    end
    local body = command:match("^vanarrative%s+(.+)$")
      or "Test beat — sidebar zoom only. Main camera stays put."
    -- Allow re-fire by clearing the test key.
    narrativeDiscovered["dev_test_beat"] = nil
    queueNarrative({
      key = "dev_test_beat",
      kind = "story",
      x = ox, z = oz,
      title = "NARRATIVE TEST",
      body = body,
      radius = 700,
      seconds = 6,
      highlightObjective = true,
    })
    Spring.Echo("VA_UI_NARRATIVE_TEST x=" .. tostring(ox) .. " z=" .. tostring(oz))
    return true
  end
  -- Forward operator grants / edge crash to synced gadget.
  if command:match("^vatnb") or command:match("^vabrutecrash") then
    if Spring.SendLuaRulesMsg then
      Spring.SendLuaRulesMsg("VA_CMD:" .. command)
      Spring.Echo("VA_UI_FORWARD " .. tostring(command))
      return true
    end
  end
  if command == "vaextract" then
    -- Same as the sidebar EXTRACT button.
    Spring.SendLuaRulesMsg("VA_CMD:manifest")
    return true
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

local function zoneLabel(zoneId)
  zoneId = tostring(zoneId or "")
  if zoneId == "" then return "unknown" end
  local sources = {}
  if mission and type(mission.mapOccupation) == "table" then
    sources[#sources + 1] = mission.mapOccupation
  end
  if mission and type(mission.offscreenPressureSummary) == "table" then
    sources[#sources + 1] = mission.offscreenPressureSummary.zones
  end
  if mission and type(mission.zoneMap) == "table" then
    sources[#sources + 1] = mission.zoneMap.zones
  end
  for _, list in ipairs(sources) do
    for _, entry in ipairs(list or {}) do
      if entry and tostring(entry.zoneId or "") == zoneId and entry.label then
        return tostring(entry.label)
      end
    end
  end
  local fallback = zoneId:gsub("^[A-Z]+_", ""):gsub("_", " "):lower()
  return fallback:gsub("^%l", string.upper)
end

local function playerForceSummary()
  local counts = { thugs = 0, karkinos = 0, rez = 0 }
  local setup = mission and mission.playableSetup
  for _, force in ipairs((setup and setup.forces) or {}) do
    if tonumber(force.teamID) == 0 then
      for _, group in ipairs(force.groups or {}) do
        for _, spec in ipairs(group.units or {}) do
          local def = tostring(spec.unitDefName or spec.def or "")
          local count = tonumber(spec.count) or 1
          if def == "corthud" and spec.packageTag == "punch_of_thugs" then
            counts.thugs = counts.thugs + count
          elseif def == "legkark" then
            counts.karkinos = counts.karkinos + count
          elseif def == "legrezbot" then
            counts.rez = counts.rez + count
          end
        end
      end
    end
  end
  local bits = {}
  if counts.thugs > 0 then bits[#bits + 1] = string.format("Pawn-launcher Punch ×%d", counts.thugs) end
  if counts.karkinos > 0 then bits[#bits + 1] = string.format("Legion Karkinos x%d", counts.karkinos) end
  if counts.rez > 0 then bits[#bits + 1] = string.format("rez bots x%d", counts.rez) end
  if #bits == 0 then return "Strike team loaded from the campaign roster." end
  return table.concat(bits, "  |  ")
end

local function wrapBriefing(s, maxLen, maxLines)
  local lines = {}
  s = tostring(s or "")
  while #s > maxLen and #lines < (maxLines - 1) do
    local cut = s:sub(1, maxLen)
    local sp = cut:match(".*()%s")
    if not sp or sp < maxLen * 0.5 then sp = maxLen end
    lines[#lines + 1] = s:sub(1, sp)
    s = s:sub(sp + 1)
  end
  if s ~= "" and #lines < maxLines then lines[#lines + 1] = s end
  if #lines == maxLines and #s > maxLen then
    lines[#lines] = lines[#lines]:sub(1, math.max(1, maxLen - 3)) .. "..."
  end
  return lines
end

local function currentPhaseClock()
  local frame = Spring.GetGameFrame() or 0
  local req = state.requiredFrames or 19800
  local left = math.max(0, (req - frame) / 30)
  local phase = Spring.GetGameRulesParam("va_phase")
  if type(phase) ~= "string" or phase == "" then
    if state.terminal then
      phase = "DONE"
    elseif state.allObjectivesDone or state.objectiveFailed then
      phase = "EXTRACT"
    elseif state.objectiveComplete then
      phase = "MARKS"
    elseif state.captureMode and state.capturePhase == "hold" then
      phase = (numParam("va_zone_hold_contested", 0) == 1) and "HOLD_CONTESTED" or "HOLD"
    elseif state.captureMode and (state.capturePhase == "clear" or state.capturePhase == "idle") then
      phase = "CLEAR"
    elseif frame < 90 * 30 then
      phase = "APPROACH"
    else
      phase = "FIGHT"
    end
  end
  phase = string.upper(tostring(phase))
  return phase, left
end

-- Slim boot card: title + one-line objective. Permanent detail lives on the left rail.
local function drawBriefingCard()
  local w = math.min(520, vsx * 0.52)
  local cx = vsx * 0.5
  local objective = (missionCard and (missionCard.plainObjective or missionCard.objective))
    or (mission and mission.objective and mission.objective.description)
    or "Complete the marked objective."
  local threat = difficultyLabel or (missionCard and missionCard.threats)
  local objLines = wrapBriefing(objective, 62, 2)
  local h = 118 + (#objLines * 18) + (threat and 18 or 0)
  local top = vsy * 0.78
  local bottom = top - h
  panel(cx - w / 2, bottom, cx + w / 2, top, COL.edge)

  local left = cx - w / 2 + 22
  local y = top - 20
  text("MISSION BRIEF", left, y, 10, COL.ash or COL.dim, "l"); y = y - 18
  text(missionTitle, left, y, 16, COL.title, "l"); y = y - 20
  text("OBJECTIVE", left, y, 10, COL.ash or COL.warn, "l"); y = y - 14
  for _, line in ipairs(objLines) do
    text(line, left, y, 12, COL.text, "l")
    y = y - 17
  end
  if threat then
    text(tostring(threat), left, y, 11, COL.warn or COL.dim, "l")
    y = y - 16
  end
  text("Space closes card  ·  Pause key begins  ·  objectives stay on the right", left, bottom + 14, 10, COL.dim, "l")
end

local function resolveRightRail()
  -- Mid-right column. Width matches the team list. Height matches it when that
  -- list is a real column; a folded stub must not crush the clock or exfil line.
  local rememberedW = leftRailRectCache and leftRailRectCache.teamW
  local rememberedH = leftRailRectCache and leftRailRectCache.teamH
  local width = rememberedW or 232
  local height = rememberedH or 340
  local margin = 8
  local screenW = vsx or 0
  local screenH = vsy or 0
  if WG and WG.advplayerlist_api and WG.advplayerlist_api.GetPosition then
    local pos = WG.advplayerlist_api.GetPosition()
    if type(pos) == "table" and pos[1] and pos[2] and pos[3] and pos[4] then
      local absTop, absLeft, absBottom, absRight = pos[1], pos[2], pos[3], pos[4]
      local tw = absRight - absLeft
      local th = absTop - absBottom
      local rightGap = screenW - absRight
      if absLeft > screenW * 0.4 and rightGap >= 0 and rightGap < 40 then
        margin = math.max(3, rightGap)
      end
      if tw > 140 and tw < screenW * 0.45 then
        width = tw
        rememberedW = tw
      end
      if th > 160 and th < screenH * 0.72 then
        height = th
        rememberedH = th
      end
    end
  end
  if width < 200 then width = 200 end
  if width > 320 then width = 320 end
  local maxH = math.max(220, screenH * 0.48)
  if height > maxH then height = maxH end
  if height < 260 then height = math.min(260, maxH) end

  -- Flush to the screen's right edge. Sitting left of the team list left a
  -- one-column gap (logged 1417-1668 on a 1920-wide view).
  local right = math.max(width + 8, screenW - margin)
  local left = right - width
  if left < 4 then
    left = 4
    right = left + width
  end
  if right > screenW - 4 and screenW > 32 then
    right = screenW - 4
    left = math.max(4, right - width)
  end
  local mid = screenH * 0.5
  local top = mid + height * 0.5
  local bottom = mid - height * 0.5
  -- Keep clear of the top resource bar.
  local topLimit = screenH - math.min(120, screenH * 0.14)
  if topLimit < 200 then topLimit = screenH - 8 end
  if top > topLimit then
    local shift = top - topLimit
    top = topLimit
    bottom = bottom - shift
  end
  if bottom < 28 then
    bottom = 28
    top = math.min(topLimit, bottom + height)
  end
  if top <= bottom then top = bottom + 180 end
  if top > screenH - 4 and screenH > 32 then
    top = screenH - 4
    bottom = math.max(28, top - height)
  end
  leftRailRectCache = {
    x1 = left, y1 = bottom, x2 = right, y2 = top,
    teamW = rememberedW, teamH = rememberedH,
  }
  return left, bottom, right, top
end

local function drawDonut(cx, cy, outerR, innerR, rgb, alpha)
  local r, g, b = rgb[1], rgb[2], rgb[3]
  local a = alpha or 0.95
  -- Outer plate (screen-space 2D vertices)
  gl.Color(r, g, b, a)
  gl.BeginEnd(GL.TRIANGLE_FAN, function()
    gl.Vertex(cx, cy)
    for i = 0, 24 do
      local ang = (i / 24) * math.pi * 2
      gl.Vertex(cx + math.cos(ang) * outerR, cy + math.sin(ang) * outerR)
    end
  end)
  -- Dark hole (infinite-power well)
  gl.Color(0.04, 0.02, 0.08, 0.92)
  gl.BeginEnd(GL.TRIANGLE_FAN, function()
    gl.Vertex(cx, cy)
    for i = 0, 20 do
      local ang = (i / 20) * math.pi * 2
      gl.Vertex(cx + math.cos(ang) * innerR, cy + math.sin(ang) * innerR)
    end
  end)
  -- Fusion-bright inner rim
  gl.Color(math.min(1, r + 0.25), math.min(1, g + 0.15), 1, a * 0.85)
  gl.LineWidth(1.5)
  gl.BeginEnd(GL.LINE_LOOP, function()
    for i = 0, 20 do
      local ang = (i / 20) * math.pi * 2
      gl.Vertex(cx + math.cos(ang) * (innerR + 1.2), cy + math.sin(ang) * (innerR + 1.2))
    end
  end)
  gl.LineWidth(1)
end

-- Purple Tnb donuts sit on the left objectives panel.
-- Stays visible for the whole sortie — blanking looked like a Tnb UI break.
local function drawTenebriumDonuts()
  local railLeft, _, railRight, railTop = resolveRightRail()
  local bank = math.floor(tonumber(state.tenebriumBank) or 0)
  -- Sit on the objectives panel, not in the metal bar. The resource bar
  -- draws over anything parked on the top edge.
  local cy = railTop - 36
  local plates = math.min(14, math.max(1, bank > 0 and math.ceil(bank / 3) or 1))
  if bank <= 0 then plates = 1 end
  local grow = (plates - 1) * 6.5
  local baseX = math.max((railLeft or 0) + 48, (railLeft or 0) + 168)
  local roomRight = (railRight or (baseX + 40)) - 18
  if baseX > roomRight then baseX = roomRight end
  local minX = (railLeft or 0) + 52
  if baseX - grow < minX then baseX = minX + grow end
  local tnb = COL.tnb or { 0.788, 0.627, 1.0 }
  local dark = { 0.35, 0.12, 0.55 }
  for i = plates, 1, -1 do
    -- Stack back into the panel. The left edge is the screen edge.
    local ox = -(i - 1) * 6.5
    local oy = (i - 1) * 4.5
    local ceiling = (railTop or cy) - 16
    if cy + oy > ceiling then oy = ceiling - cy end
    local glow = 0.55 + 0.45 * (i / plates)
    local rgb = (i == plates) and tnb or dark
    drawDonut(baseX + ox, cy + oy, 11 + (i == plates and 1 or 0), 4.5, rgb, glow)
  end
  local labelX = math.max((railLeft or 0) + 28, baseX - (plates * 6.5) - 18)
  text(tostring(bank), labelX, cy - 1, 13, tnb, "r")
  text("Tnb", labelX, cy + 12, 9, COL.ash or COL.dim, "r")
  if (state.tenebriumWrecksUnclaimed or 0) > 0 then
    text(string.format("+%d field", state.tenebriumWrecksUnclaimed), labelX, cy - 14, 9, COL.warn or COL.dim, "r")
  end
end

local function watchUnitLabel(uid)
  if not uid or not Spring.ValidUnitID or not Spring.ValidUnitID(uid) then
    return "no high-value unit", nil
  end
  local defID = Spring.GetUnitDefID(uid)
  local def = defID and UnitDefs[defID]
  local hero = Spring.GetUnitRulesParam(uid, "va_hero_id")
  local label
  if hero and tostring(hero) ~= "" and tostring(hero) ~= "0" then
    local rec = heroRoster[tostring(hero)]
    label = rec and rec.name or tostring(hero)
  else
    label = (def and (def.humanName or def.name)) or ("unit " .. tostring(uid))
  end
  local hp, maxHp = Spring.GetUnitHealth(uid)
  local hpFrac = (hp and maxHp and maxHp > 0) and (hp / maxHp) or nil
  return tostring(label), hpFrac
end

-- Built-in map view: crop of engine $minimap (same terrain/units as the minimap).
-- Drag to pan, wheel to zoom. Never moves the main camera.
local function drawWatchViewport(vx1, vy1, vx2, vy2)
  followViewRect = { x1 = vx1, y1 = vy1, x2 = vx2, y2 = vy2 }
  local vw, vh = vx2 - vx1, vy2 - vy1
  if vw < 40 or vh < 40 then return end

  gl.Color(0.02, 0.05, 0.04, 0.95)
  gl.Rect(vx1, vy1, vx2, vy2)

  local narrOn = narrativeActive ~= nil
  local accent = narrOn and (COL.gold or COL.title)
    or (followCamEnabled and (COL.tnb or COL.edge) or COL.dim)
  gl.Color(accent[1], accent[2], accent[3], narrOn and 0.95 or 0.75)
  gl.Rect(vx1, vy2 - 1, vx2, vy2)
  gl.Rect(vx1, vy1, vx2, vy1 + 1)
  gl.Rect(vx1, vy1, vx1 + 1, vy2)
  gl.Rect(vx2 - 1, vy1, vx2, vy2)

  local cx = followViewCenter and followViewCenter.x
  local cz = followViewCenter and followViewCenter.z
  if not cx then
    text("drag / scroll to steer", (vx1 + vx2) * 0.5, (vy1 + vy2) * 0.5, 10, COL.dim)
    return
  end

  local mapX = Game.mapSizeX or 1
  local mapZ = Game.mapSizeZ or 1
  -- Keep crop square in world so the minimap aspect doesn't stretch badly.
  local aspect = vw / math.max(1, vh)
  local halfZ = followViewRadius
  local halfX = halfZ * aspect
  local x0 = math.max(0, cx - halfX)
  local x1 = math.min(mapX, cx + halfX)
  local z0 = math.max(0, cz - halfZ)
  local z1 = math.min(mapZ, cz + halfZ)
  local u0, u1 = x0 / mapX, x1 / mapX
  -- Engine minimap V is flipped vs world Z.
  local v0, v1 = 1 - z0 / mapZ, 1 - z1 / mapZ

  local okTex = false
  if gl.Texture then
    okTex = pcall(function()
      gl.Color(1, 1, 1, 1)
      gl.Texture("$minimap")
      gl.BeginEnd(GL.QUADS, function()
        gl.TexCoord(u0, v0); gl.Vertex(vx1, vy1)
        gl.TexCoord(u1, v0); gl.Vertex(vx2, vy1)
        gl.TexCoord(u1, v1); gl.Vertex(vx2, vy2)
        gl.TexCoord(u0, v1); gl.Vertex(vx1, vy2)
      end)
      gl.Texture(false)
    end)
  end
  if not okTex then
    text("minimap texture unavailable", (vx1 + vx2) * 0.5, (vy1 + vy2) * 0.5, 9, COL.dim)
  end

  local function worldToView(wx, wz)
    local u = (wx - x0) / math.max(1, x1 - x0)
    local v = (wz - z0) / math.max(1, z1 - z0)
    return vx1 + u * vw, vy1 + v * vh
  end

  -- Trace role-zone cells that intersect the crop (real shapes, not AABB).
  local roleZones = WG and WG.vaZones
  if roleZones then
    for _, z in ipairs(roleZones) do
      if z.kind and z.kind ~= "default" and z.cells then
        local col = z.kind == "objective" and COL.warn
          or (z.kind == "extract" and (COL.steam or COL.blue)
          or (z.kind == "deploy" and COL.good or (COL.gold or COL.title)))
        gl.Color(col[1], col[2], col[3], 0.28)
        for _, c in ipairs(z.cells) do
          if c[3] >= x0 and c[1] <= x1 and c[4] >= z0 and c[2] <= z1 then
            local sx1, sy1 = worldToView(c[1], c[2])
            local sx2, sy2 = worldToView(c[3], c[4])
            gl.Rect(math.min(sx1, sx2), math.min(sy1, sy2), math.max(sx1, sx2), math.max(sy1, sy2))
          end
        end
      end
    end
  end

  -- Current route arrow tip inside the crop.
  if routeFrom and routeTo then
    local ax, ay = worldToView(routeFrom.x, routeFrom.z)
    local bx, by = worldToView(routeTo.x, routeTo.z)
    local r, g, b = routeStageColor()
    gl.Color(r, g, b, 0.95)
    gl.LineWidth(2.2)
    gl.BeginEnd(GL.LINES, function()
      gl.Vertex(ax, ay); gl.Vertex(bx, by)
    end)
    gl.LineWidth(1)
  end

  -- Center crosshair
  local mx, my = (vx1 + vx2) * 0.5, (vy1 + vy2) * 0.5
  gl.Color(accent[1], accent[2], accent[3], narrOn and 0.8 or 0.45)
  gl.BeginEnd(GL.LINES, function()
    gl.Vertex(mx - 7, my); gl.Vertex(mx + 7, my)
    gl.Vertex(mx, my - 7); gl.Vertex(mx, my + 7)
  end)

  gl.Color(1, 1, 1, 1)
end

local function drawFollowCamCard(left, bottom, right, y)
  followCamRect = nil
  followViewRect = nil
  local narrOn = narrativeActive ~= nil
  local captionLines = 0
  if narrOn and narrativeActive.body and narrativeActive.body ~= "" then
    captionLines = 2
  elseif narrOn then
    captionLines = 1
  end
  local headerH = narrOn and 40 or 36
  local captionH = captionLines > 0 and (12 + captionLines * 12) or 0
  local viewH = (followCamEnabled or narrOn) and 160 or 120
  local cardH = headerH + viewH + captionH + 8
  local cardBot = y - cardH
  if cardBot < bottom + 4 then
    viewH = math.max(70, (y - bottom - 4) - headerH - captionH - 8)
    cardH = headerH + viewH + captionH + 8
    cardBot = y - cardH
    if cardBot < bottom + 2 then return y end
  end
  local accent = narrOn and (COL.gold or COL.title)
    or (followCamEnabled and (COL.tnb or COL.edge) or COL.dim)
  panel(left + 6, cardBot, right - 6, y, accent)
  followCamRect = { x1 = left + 6, y1 = cardBot, x2 = right - 6, y2 = y }

  text("NARRATIVE CAM", left + 14, y - 12, 9, COL.ash or COL.dim, "l")
  local statusLabel = narrOn and "BEAT" or (followCamEnabled and "LIVE" or "click")
  local statusCol = narrOn and (COL.gold or COL.title)
    or (followCamEnabled and (COL.tnb or COL.good) or COL.dim)
  text(statusLabel, right - 14, y - 12, 9, statusCol, "r")

  if narrOn then
    text(tostring(narrativeActive.title or "REPORT"):sub(1, 24), left + 14, y - 26, 10, COL.title, "l")
  else
    local look = routeTo and tostring(routeTo.label or "objective") or "map"
    text(("look: " .. look):sub(1, 22), left + 14, y - 26, 10, COL.text, "l")
  end

  local vx1, vx2 = left + 10, right - 10
  local vy2 = y - headerH - 2
  local vy1 = cardBot + 6 + captionH
  drawWatchViewport(vx1, vy1, vx2, vy2)

  if narrOn and narrativeActive.body and narrativeActive.body ~= "" then
    local cy = cardBot + captionH - 4
    for _, line in ipairs(wrapBriefing(narrativeActive.body, 30, 2)) do
      text(line, left + 12, cy, 9, COL.text, "l")
      cy = cy - 11
    end
  else
    text("drag pan · wheel zoom · built-in map", left + 12, cardBot + 2, 8, COL.dim, "l")
  end
  return cardBot - 8
end

-- Permanent mission objectives, mid-right, in the team list's column size.
local function drawRightMissionRail()
  local left, bottom, right, top = resolveRightRail()
  if not widget._vaRailLogged then
    widget._vaRailLogged = true
    Spring.Echo(string.format(
      "VA_UI_RAIL left=%.0f bottom=%.0f right=%.0f top=%.0f vsx=%.0f vsy=%.0f",
      left or -1, bottom or -1, right or -1, top or -1, vsx or -1, vsy or -1))
  end
  local obj = mission and mission.objective or {}
  panel(left, bottom, right, top, COL.edge)

  local x = left + 12
  local y = top - 14
  local frame = Spring.GetGameFrame() or 0
  local objPulse = frame < narrativeHighlightUntil
  local objPulseA = objPulse and (0.55 + 0.45 * math.abs(math.sin(os.clock() * 4.5))) or 1
  local kickerCol = objPulse
    and { (COL.gold or COL.title)[1], (COL.gold or COL.title)[2], (COL.gold or COL.title)[3], objPulseA }
    or (COL.ash or COL.dim)
  text("OBJECTIVES", x, y, 10, kickerCol, "l"); y = y - 16
  if objPulse then
    -- Soft gold underline while the narrative cam is emphasizing this mark.
    local gold = COL.gold or COL.title
    gl.Color(gold[1], gold[2], gold[3], objPulseA * 0.7)
    gl.Rect(x, y + 12, right - 12, y + 14)
  end
  text(tostring(missionTitle):sub(1, 28), x, y, 12, COL.title, "l"); y = y - 16
  if routeStage and not state.terminal then
    local stageCol = routeStage == "extract" and (COL.steam or COL.blue)
      or (routeStage == "marks" and (COL.gold or COL.title) or COL.warn)
    local stageBit = routeStage == "push" and "ROUTE  enfil → obj"
      or (routeStage == "marks" and "ROUTE  obj → mark" or "ROUTE  → exfil")
    text(stageBit, x, y, 10, stageCol, "l")
    text("F9", right - 12, y, 9, COL.dim, "r")
    y = y - 14
  end

  if not state.terminal then
    local phase, clockLeft = currentPhaseClock()
    local clockCol = COL.good
    if clockLeft < 120 then clockCol = COL.warn end
    if clockLeft < 45 then clockCol = COL.bad end
    local phaseCol = COL.edge
    if phase == "EXTRACT" then phaseCol = COL.steam or COL.blue end
    if phase == "TIMEOUT" then phaseCol = COL.bad end
    text(phase, x, y, 12, phaseCol, "l")
    text(formatClock(clockLeft), right - 12, y, 12, clockCol, "r")
    y = y - 16
  end

  -- Pin Tnb near the top so content below cannot push it off the rail.
  do
    local bank = math.floor(tonumber(state.tenebriumBank) or 0)
    local field = math.floor(tonumber(state.tenebriumWrecksUnclaimed) or 0)
    local tnb = COL.tnb or { 0.788, 0.627, 1.0 }
    local line = string.format("Tnb carried %d", bank)
    if field > 0 then
      line = line .. string.format("  ·  +%d field", field)
    end
    text(line:sub(1, 34), x, y, 11, tnb, "l")
    y = y - 14
  end

  if obj.description then
    local marker = state.objectiveComplete and "DONE  " or ""
    local col
    if state.objectiveComplete then
      col = COL.good
    elseif objPulse then
      col = { (COL.gold or COL.title)[1], (COL.gold or COL.title)[2], (COL.gold or COL.title)[3], objPulseA }
    else
      col = COL.text
    end
    for _, line in ipairs(wrapBriefing(marker .. obj.description, 28, 3)) do
      text(line, x, y, 11, col, "l")
      y = y - 14
    end
    y = y - 2
  end

  if state.objectiveTotal > 0 and not state.objectiveComplete
      and not (state.captureMode and state.capturePhase == "hold") then
    local pct = math.floor((state.objectiveDestroyed / math.max(1, state.objectiveTotal)) * 100 + 0.5)
    if state.captureMode and (state.capturePhase == "clear" or state.capturePhase == "idle") then
      text(string.format("Clear pocket  %d%%", pct), x, y, 11, COL.warn, "l")
    elseif obj.kind == "eco_raid" then
      text(string.format("Works wrecked  %d%%", pct), x, y, 11, COL.warn, "l")
    else
      text(string.format("Targets  %d / %d", state.objectiveDestroyed, state.objectiveTotal), x, y, 11, COL.dim, "l")
    end
    y = y - 14
  end

  if state.captureMode and state.capturePhase == "hold" and not state.objectiveComplete then
    local required = numParam("va_zone_hold_need", 0)
    if required <= 0 then required = (obj.requiredHoldFrames) or PRESENCE_HOLD_DEFAULT end
    local contested = numParam("va_zone_hold_contested", 0) == 1
    local holdCol = contested and COL.warn or (COL.steam or COL.blue)
    local frac = math.max(0, math.min(1, (state.zoneHold or 0) / math.max(1, required)))
    text(string.format("Hold gate  %ds / %ds  (%d%%)",
        math.floor(state.zoneHold / 30), math.floor(required / 30), math.floor(frac * 100 + 0.5)),
      x, y, 11, holdCol, "l")
    y = y - 12
    -- Trust bar: fill shows progress; contested washes warm.
    do
      local bw = math.min(168, (right or (x + 180)) - x - 8)
      gl.Color(0.12, 0.14, 0.13, 0.85)
      gl.Rect(x, y, x + bw, y + 7)
      local fillCol = contested and (COL.warn or COL.gold) or (COL.steam or COL.blue)
      gl.Color(fillCol[1], fillCol[2], fillCol[3], 0.95)
      gl.Rect(x, y, x + bw * frac, y + 7)
      gl.Color(1, 1, 1, 1)
      y = y - 12
    end
    text(contested and "Contested — clock paused" or "Clear hostiles to keep ticking",
      x, y, 10, contested and COL.warn or COL.dim, "l")
    y = y - 13
  elseif not state.objectiveComplete and state.zoneHold > 0 and not state.captureMode then
    local required = numParam("va_zone_hold_need", 0)
    if required <= 0 then required = (obj.requiredHoldFrames) or PRESENCE_HOLD_DEFAULT end
    local frac = math.max(0, math.min(1, (state.zoneHold or 0) / math.max(1, required)))
    text(string.format("Holding  %ds / %ds  (%d%%)",
        math.floor(state.zoneHold / 30), math.floor(required / 30), math.floor(frac * 100 + 0.5)),
      x, y, 11, COL.steam or COL.blue, "l")
    y = y - 12
    do
      local bw = 168
      gl.Color(0.12, 0.14, 0.13, 0.85)
      gl.Rect(x, y, x + bw, y + 7)
      local fillCol = COL.steam or COL.blue
      gl.Color(fillCol[1], fillCol[2], fillCol[3], 0.95)
      gl.Rect(x, y, x + bw * frac, y + 7)
      gl.Color(1, 1, 1, 1)
      y = y - 12
    end
  end

  -- Fortify / secure: defensive value alone is the "secured" signal.
  do
    local kind = tostring(obj.kind or "")
    local fortifying = (kind == "fortify_zone" or kind == "secure_foothold" or kind == "home_founding")
      or ((state.fortifyNeedDef or 0) > 0)
    if fortifying and not state.objectiveComplete then
      local cur = state.fortifyDef or 0
      local need = state.fortifyNeedDef or 800
      local ok = need > 0 and cur >= need
      local col = ok and COL.good or COL.warn
      text("Secure the zone — dig in teeth", x, y, 11, COL.steam or COL.blue, "l")
      y = y - 14
      text(string.format("Defense  %d / %d", cur, need), x, y, 10, col, "l")
      y = y - 13
      text("Territory = defensive value", x, y, 9, COL.dim, "l")
      y = y - 12
    end
  end

  if state.captureMode and state.nodeClaimed then
    text("Node claimed", x, y, 10, COL.good, "l")
    y = y - 13
  end

  if (state.secondaryTotal or 0) > 0 then
    for i = 1, state.secondaryTotal do
      local sec = state.secondaries and state.secondaries[i]
      if sec then
        local label = tostring(sec.label or ("mark " .. i))
        local pres = presentSecondary(sec)
        for _, line in ipairs(wrapBriefing(pres.railPrefix .. label, 26, 2)) do
          text(line, x, y, 10, pres.color, "l")
          y = y - 13
        end
      end
    end
  end

  if state.purgeArmed and not state.terminal then
    text(state.purgeDone and "PURGE COMPLETE" or "PURGE ORDER active", x, y, 10,
      state.purgeDone and COL.good or COL.warn, "l")
    y = y - 13
  end

  if state.objectiveComplete and not state.allObjectivesDone
      and not state.objectiveFailed and not state.terminal then
    text("Primary claimed — finish REQUIRED marks", x, y, 10, COL.warn, "l")
    y = y - 13
    text("Extract early for partial credit, or finish required marks", x, y, 9, COL.dim, "l")
    y = y - 12
  end

  -- EXTRACT: always available once the sortie is underway. One click sends
  -- VA_CMD:manifest; gui_verdance_exfil.lua takes it from there.
  extractButtonRect = nil
  if not state.terminal and playerBeganSortie then
    y = math.max(y, 120) -- Keep the button on-screen at 720p.
    local boardResolved = state.allObjectivesDone or state.objectiveFailed
    extractButtonRect = { x1 = x, y1 = y - 30, x2 = right - 12, y2 = y }
    panel(x, y - 30, right - 12, y, boardResolved and COL.good or (COL.steam or COL.edge))
    text("EXTRACT", x + 10, y - 19, 12, COL.title, "l")
    y = y - 36
    text("Get what you want to keep onto the pad first.", x, y, 9, COL.dim, "l")
    y = y - 16
  end

  if not playerBeganSortie and not state.terminal then
    text("PAUSED — pause key to begin", x, y, 10, COL.steam or COL.blue, "l")
    y = y - 14
  end

  -- Living logistics inbound (map-web / pawn launcher).
  local inboundN = math.floor(numParam("va_inbound_total", 0))
  if inboundN > 0 and not state.terminal then
    text("INBOUND", x, y, 10, COL.ash or COL.dim, "l"); y = y - 13
    for i = 1, math.min(inboundN, 4) do
      local label = Spring.GetGameRulesParam("va_inbound_" .. i .. "_label")
      local source = Spring.GetGameRulesParam("va_inbound_" .. i .. "_source")
      local eta = numParam("va_inbound_" .. i .. "_eta", 0)
      local count = numParam("va_inbound_" .. i .. "_count", 0)
      local mode = Spring.GetGameRulesParam("va_inbound_" .. i .. "_mode")
      local line = tostring(label or ("ship " .. i))
      if count > 0 then line = line .. " ×" .. tostring(math.floor(count)) end
      text(line:sub(1, 26), x, y, 10, COL.steam or COL.blue, "l"); y = y - 12
      local sub = string.format("%s · %ds", tostring(source or mode or "web"), math.floor(eta))
      text(sub:sub(1, 28), x, y, 9, COL.dim, "l"); y = y - 12
    end
    y = y - 2
  end

  if heroBanner and not state.terminal then
    local pulse = 0.55 + 0.45 * math.abs(math.sin(os.clock() * 3.5))
    text(tostring(heroBanner.text):sub(1, 28), x, y, 11, { COL.bad[1], COL.bad[2], COL.bad[3], pulse }, "l")
    y = y - 14
  end

  y = drawFollowCamCard(left, bottom, right, y - 4)
end

local drawFaultLogged = {}

local function guardDraw(name, fn)
  local ok, err = pcall(fn)
  if not ok and not drawFaultLogged[name] then
    drawFaultLogged[name] = true
    Spring.Echo("VA_UI_DRAW_FAIL " .. tostring(name) .. " " .. tostring(err))
  end
  return ok
end

local function drawObjectiveBar()
  -- Permanent objectives live on the left panel; Tnb sits on that same panel.
  guardDraw("rail", drawRightMissionRail)
  guardDraw("tnb", drawTenebriumDonuts)
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

local function loadStratZones()
  if stratZones then return stratZones end
  stratZones = {}
  local ok, zoneMap = pcall(VFS.Include, "singleplayer/verdance_ashes/generated/zone_map_current.lua")
  if not ok or type(zoneMap) ~= "table" or type(zoneMap.zones) ~= "table" then
    return stratZones
  end
  local sx = Game.mapSizeX or 1
  local sz = Game.mapSizeZ or 1
  local function norm(v, size)
    v = tonumber(v) or 0
    if v <= 1 then return v * size end
    return v
  end
  for _, z in ipairs(zoneMap.zones) do
    local b = z.bounds or {}
    stratZones[#stratZones + 1] = {
      zoneId = tostring(z.zoneId or "?"),
      label = tostring(z.label or z.zoneId or "?"),
      x1 = norm(b.xMin, sx), z1 = norm(b.zMin, sz),
      x2 = norm(b.xMax, sx), z2 = norm(b.zMax, sz),
    }
  end
  return stratZones
end

toggleStratOverlay = function()
  stratOverlay = not stratOverlay
  if stratOverlay then loadStratZones() end
  Spring.Echo("VA_UI_STRAT_OVERLAY " .. (stratOverlay and "on" or "off") .. " (F9)")
  return true
end

-- Minimap-like strategic overlay: zones + the ONE live route stage.
-- Replaces the noisy ground circles as the "where am I going" readout.
local function drawStratOverlay()
  if not stratOverlay or state.terminal then return end
  local mapX = Game.mapSizeX or 1
  local mapZ = Game.mapSizeZ or 1
  local panelW = math.min(vsx * 0.42, 520)
  local panelH = math.min(vsy * 0.55, panelW * (mapZ / mapX) + 56)
  local x1 = vsx - panelW - 18
  local y2 = vsy * 0.72
  local y1 = y2 - panelH
  local x2 = x1 + panelW
  panel(x1, y1, x2, y2, COL.edge)

  local stageName = (routeStage == "push" and "PUSH  enfil → objective")
    or (routeStage == "marks" and "MARKS  objective → next")
    or (routeStage == "extract" and "EXTRACT  → exfil")
    or "ROUTE idle"
  text("STRATEGIC OVERLAY", x1 + 14, y2 - 14, 10, COL.ash or COL.dim, "l")
  text("F9 close · /vaclear marks", x2 - 14, y2 - 14, 9, COL.dim, "r")
  text(stageName, x1 + 14, y2 - 30, 11, COL.title, "l")

  local pad = 16
  local mx1, my1 = x1 + pad, y1 + pad
  local mx2, my2 = x2 - pad, y2 - 44
  local mw, mh = mx2 - mx1, my2 - my1
  gl.Color(0.02, 0.05, 0.04, 0.95)
  gl.Rect(mx1, my1, mx2, my2)
  -- Built-in full-map texture under the zone traces.
  pcall(function()
    gl.Color(1, 1, 1, 1)
    gl.Texture("$minimap")
    gl.BeginEnd(GL.QUADS, function()
      gl.TexCoord(0, 1); gl.Vertex(mx1, my1)
      gl.TexCoord(1, 1); gl.Vertex(mx2, my1)
      gl.TexCoord(1, 0); gl.Vertex(mx2, my2)
      gl.TexCoord(0, 0); gl.Vertex(mx1, my2)
    end)
    gl.Texture(false)
  end)

  local function worldToOverlay(wx, wz)
    local u = (wx or 0) / mapX
    local v = (wz or 0) / mapZ
    return mx1 + u * mw, my1 + (1 - v) * mh
  end

  -- Trace real zone cells from the minimap widget (WG.vaZones) — not AABB boxes.
  local zones = (WG and WG.vaZones) or {}
  if #zones == 0 then loadStratZones() end
  for _, z in ipairs(zones) do
    local col = COL.dim
    local a = 0.12
    if z.kind == "objective" then col, a = COL.warn, 0.40
    elseif z.kind == "deploy" then col, a = COL.good, 0.35
    elseif z.kind == "extract" then col, a = (COL.steam or COL.blue), 0.35
    elseif z.kind == "secondary" then col, a = (COL.gold or COL.title), 0.30
    else
      -- skip default clutter on the overlay
      col = nil
    end
    if col and z.cells then
      gl.Color(col[1], col[2], col[3], a)
      for _, c in ipairs(z.cells) do
        local sx1, sy1 = worldToOverlay(c[1], c[2])
        local sx2, sy2 = worldToOverlay(c[3], c[4])
        gl.Rect(math.min(sx1, sx2), math.min(sy1, sy2), math.max(sx1, sx2), math.max(sy1, sy2))
      end
    end
  end

  -- Current stage arrow on the overlay (same lean notation as the ground).
  if routeFrom and routeTo then
    local ax, ay = worldToOverlay(routeFrom.x, routeFrom.z)
    local bx, by = worldToOverlay(routeTo.x, routeTo.z)
    local r, g, b = routeStageColor()
    gl.Color(r, g, b, 0.95)
    gl.LineWidth(3)
    gl.Shape(GL.LINES, { { v = { ax, ay } }, { v = { bx, by } } })
    -- Arrow head
    local dx, dy = bx - ax, by - ay
    local len = math.sqrt(dx * dx + dy * dy)
    if len > 8 then
      local ux, uy = dx / len, dy / len
      local px, py = -uy, ux
      local hs = 12
      gl.Shape(GL.LINE_LOOP, {
        { v = { bx, by } },
        { v = { bx - ux * hs - px * hs * 0.55, by - uy * hs - py * hs * 0.55 } },
        { v = { bx - ux * hs + px * hs * 0.55, by - uy * hs + py * hs * 0.55 } },
      })
    end
    text(tostring(routeFrom.label or ""), ax, ay + 10, 9, COL.good, "c")
    text(tostring(routeTo.label or ""), bx, by + 10, 9, COL.warn, "c")
  end

  -- Player camera position pip
  local cx, _, cz = Spring.GetCameraPosition()
  if cx and cz then
    local px, py = worldToOverlay(cx, cz)
    gl.Color(COL.ink and COL.ink[1] or 1, COL.ink and COL.ink[2] or 1, COL.ink and COL.ink[3] or 1, 0.9)
    gl.Rect(px - 3, py - 3, px + 3, py + 3)
  end
  gl.Color(1, 1, 1, 1)
  gl.LineWidth(1)
end

function widget:DrawScreen()
  if Spring.IsGUIHidden() then return end
  if not mission then return end
  -- A previous widget can leave scissor or depth-test on, which clips this
  -- HUD to nothing while the rest of the frame still draws.
  pcall(function()
    local vx, vy = Spring.GetViewGeometry()
    if vx and vx > 32 and vy and vy > 32 then
      vsx, vsy = vx, vy
    end
    if gl.Scissor then gl.Scissor(false) end
    if gl.DepthTest then gl.DepthTest(false) end
    if gl.Blending then gl.Blending(true) end
    if gl.ColorMask then gl.ColorMask(true, true, true, true) end
    gl.Color(1, 1, 1, 1)
  end)

  -- Sortie over: gui_verdance_exfil.lua draws the closing card. Hide our panels.
  if state.sortieOver then return end

  local frame = Spring.GetGameFrame() or 0
  local showCard = missionCard ~= nil or #briefingLines > 0
  if not briefingDismissed and (frame < BRIEFING_SECONDS * 30 or frame < briefingReopenUntil)
      and not state.objectiveComplete and showCard then
    guardDraw("briefing", drawBriefingCard)
  end
  -- Objectives + Tnb are the load-bearing HUD — always attempt them.
  drawObjectiveBar()
  guardDraw("bark", drawBark)
  guardDraw("strat", drawStratOverlay)
end

-- Stage-gated theater arrows on the ground. Circles removed — they went stale
-- and fought the notation. One route stage at a time (hub lean).
function widget:DrawWorld()
  if Spring.IsGUIHidden() then return end
  if not mission then return end

  if routeFrom and routeTo and not state.terminal then
    local r, g, b, a = routeStageColor()
    drawBigRouteArrow(routeFrom.x, routeFrom.z, routeTo.x, routeTo.z, r, g, b, a)
  elseif routeTo and not state.terminal then
    -- Destination-only pin when we lack a from (rare).
    local r, g, b, a = routeStageColor()
    local hx, hz = routeTo.x, routeTo.z
    local hy = groundY(hx, hz) + 12
    gl.Color(r, g, b, a)
    gl.LineWidth(3.5)
    gl.BeginEnd(GL.LINES, function()
      gl.Vertex(hx - 70, hy, hz); gl.Vertex(hx + 70, hy, hz)
      gl.Vertex(hx, hy, hz - 70); gl.Vertex(hx, hy, hz + 70)
    end)
    gl.LineWidth(1)
  end

  -- Presence / hold zone outline while the clock matters.
  if not state.terminal and not state.objectiveComplete
      and ((state.captureMode and state.capturePhase == "hold") or (state.zoneHold or 0) > 0) then
    local cx = numParam("va_hold_cx", -1)
    local cz = numParam("va_hold_cz", -1)
    local hw = numParam("va_hold_hw", 0)
    local hh = numParam("va_hold_hh", 0)
    if cx > 0 and cz > 0 and hw > 0 and hh > 0 then
      local contested = numParam("va_zone_hold_contested", 0) == 1
      local col = contested and (COL.warn or COL.gold) or (COL.steam or COL.blue)
      local pulse = 0.35 + 0.35 * math.abs(math.sin(os.clock() * 2.2))
      local y0 = groundY(cx, cz) + 10
      local x1, z1, x2, z2 = cx - hw, cz - hh, cx + hw, cz + hh
      gl.Color(col[1], col[2], col[3], pulse)
      gl.LineWidth(3.0)
      gl.BeginEnd(GL.LINE_LOOP, function()
        gl.Vertex(x1, y0, z1)
        gl.Vertex(x2, y0, z1)
        gl.Vertex(x2, y0, z2)
        gl.Vertex(x1, y0, z2)
      end)
      -- Progress tick on the north edge.
      local need = numParam("va_zone_hold_need", PRESENCE_HOLD_DEFAULT)
      local frac = math.max(0, math.min(1, (state.zoneHold or 0) / math.max(1, need)))
      gl.Color(COL.good[1], COL.good[2], COL.good[3], 0.85)
      gl.BeginEnd(GL.LINES, function()
        gl.Vertex(x1, y0 + 2, z2)
        gl.Vertex(x1 + (x2 - x1) * frac, y0 + 2, z2)
      end)
      gl.LineWidth(1)
    end
  end

  -- Hero wreck: urgent X, not a circle.
  if heroWreckBeacon and not state.terminal then
    local hx, hz = heroWreckBeacon.x, heroWreckBeacon.z
    local hy = groundY(hx, hz) + 8
    local pulse = 0.5 + 0.4 * math.abs(math.sin(os.clock() * 4))
    gl.Color(COL.bad[1], COL.bad[2], COL.bad[3], pulse)
    gl.LineWidth(4)
    gl.BeginEnd(GL.LINES, function()
      gl.Vertex(hx - 90, hy, hz - 90); gl.Vertex(hx + 90, hy, hz + 90)
      gl.Vertex(hx + 90, hy, hz - 90); gl.Vertex(hx - 90, hy, hz + 90)
    end)
    gl.LineWidth(1)
  end
  gl.Color(1, 1, 1, 1)
end

-- Mission events split into per-status handlers so each stays under Lua's
-- 60-upvalue limit (a single giant VerdanceMissionEvent failed to load the widget).
local missionEventHandlers = {}

missionEventHandlers["objective_complete"] = function(reason)
  playUi("beep6", 1.0)
  local reqLeft = numParam("va_secondary_required_left", 0)
  if reqLeft > 0 then
    queueBark("Ketha", "Primary's yours — finish the required marks, then bring them home.")
  else
    queueBark("Ketha", "Mark claimed. Your call when we leave. Load the pad, then press EXTRACT.")
  end
  Spring.Echo("Verdance: objective complete (" .. tostring(reason) .. ") - return to extraction.")

end

missionEventHandlers["objective_failed"] = function(reason)
  playUi("warning1", 1.0)
  poll()
  placeMarkers()
  refreshRouteStage()
  refreshHeroDownBanner()
  queueBark("Ketha", "Wreck's gone — rescue is scrubbed. Get the company to extract.")
  local ex = beaconExtraction
  queueNarrative({
    key = "objective_failed_" .. tostring(reason or "wreck"),
    kind = "objective",
    x = ex and ex.x or nil,
    z = ex and ex.z or nil,
    title = "RESCUE FAILED",
    body = "The wreck is gone. Get the company onto the pad and press EXTRACT.",
    radius = 900,
    seconds = 7.5,
    highlightObjective = true,
  })
end

missionEventHandlers["all_objectives_complete"] = function(reason)
  queueBark("Ketha", "Required objectives complete. Load the pad with what you're keeping, then press EXTRACT.")
  poll()
  refreshRouteStage()
end

missionEventHandlers["extract_armed"] = function(reason)
  playUi("beep4", 0.9)
  queueBark("Ketha", reason == "on_pad"
    and "On the extract pad. Press EXTRACT when you're loaded."
    or "Pad is live — get the company onto it, then press EXTRACT.")
  routeStageDrawn = nil
  refreshRouteStage()
end

missionEventHandlers["secondary_complete"] = function(reason)
  -- Narrative cam zoom arrives via VERDANCE_BEAT "narrative" from synced.
  playUi("beep4", 0.7)
end

missionEventHandlers["secondary_changed"] = function(reason)
  -- Marks registry upsert; poll + place + banner (hero_down_objective alias retired).
  poll()
  if refreshHeroDownBanner then refreshHeroDownBanner() end
  playUi("warning2", 0.7)
end

missionEventHandlers["debug_pause"] = function(reason)
  -- Dev commands: synced asks the field to freeze.
  pcall(Spring.SendCommands, "pause 1")
  holdStartPause = false
  Spring.Echo("VA_UI_DEBUG_PAUSE " .. tostring(reason or ""))
end

missionEventHandlers["sortie_over"] = function(reason)
  -- reason: "extracted" | "wiped". gui_verdance_exfil.lua owns the closing
  -- card and the quit; this HUD just steps aside (DrawScreen returns early).
  state.sortieOver = true
  state.terminal = true
  extractButtonRect = nil
  followCamRect = nil
  followViewRect = nil
  heroBanner = nil
  heroWreckBeacon = nil
  narrativeActive = nil
  narrativeQueue = {}
  routeStage, routeFrom, routeTo = nil, nil, nil
  if WG then WG.vaRoute = nil end
  Spring.Echo("VA_UI_SORTIE_OVER reason=" .. tostring(reason or ""))
end

function widget:VerdanceMissionEvent(eventStatus, reason)
  poll()
  local handler = missionEventHandlers[eventStatus]
  if handler then
    handler(reason)
  end
end


refreshHeroDownBanner = function()
  -- Banner derives only from open hero_recover marks (registry SoT via poll).
  local open = {}
  for i = 1, (state.secondaryTotal or 0) do
    local sec = state.secondaries and state.secondaries[i]
    if sec and not sec.done and presentSecondary(sec).isHeroRecover then
      open[#open + 1] = sec
    end
  end
  if #open == 0 then
    heroBanner = nil
    heroWreckBeacon = nil
    return
  end
  local first = open[1]
  local name = tostring(first.label or "hero"):gsub("^[^:]+:%s*", "")
  if #open == 1 then
    heroBanner = {
      text = string.upper(name) .. " IS DOWN — recover!",
      critical = false,
    }
  else
    heroBanner = {
      text = string.format("%d HEROES DOWN — recover!", #open),
      critical = true,
    }
  end
  if first.x and first.z and first.x >= 0 then
    heroWreckBeacon = { x = first.x, z = first.z, name = name }
  end
end

function widget:VerdanceHeroEvent(event, heroId, name, critical, x, z)
  -- Juice only: roster + bark/cam/SFX. Mark rail comes from secondary_changed poll.
  heroId = tostring(heroId or "")
  local rec = heroRoster[heroId]
  if not rec then
    rec = { name = tostring(name or heroId), missionCritical = (critical == 1), state = "alive", everDown = false }
    heroRoster[heroId] = rec
  end
  if event == "down" then
    rec.state = "down"
    rec.everDown = true
    if name and tostring(name) ~= "" then rec.name = tostring(name) end
    if x and z and tonumber(x) and tonumber(x) > 0 then
      queueNarrative({
        key = "hero_down_" .. heroId,
        kind = "hero",
        x = x, z = z,
        title = "HERO DOWN",
        body = rec.name .. " is in the mud — get a rez bot on that wreck.",
        radius = 500,
        seconds = 6.5,
      })
    end
    playUi("warning2", 0.95)
    -- Banner refreshes from poll / secondary_changed (marks SoT).
  elseif event == "recovered" or event == "recruited" then
    rec.state = "alive"
    if event == "recruited" then
      playUi("beep4", 1.0)
      queueBark("", (rec.name or name) .. " signed onto the company.")
    else
      playUi("beep4", 1.0)
      queueBark("", rec.name .. " is back on their feet.")
    end
  elseif event == "wreck_gone" then
    -- Early cue while rez-grace races: stop promising recover on a blasted wreck.
    rec.state = "down"
    rec.everDown = true
    heroBanner = {
      text = string.upper(tostring(rec.name or name or "WRECK")) .. " WRECK GONE",
      critical = true,
    }
    playUi("warning2", 0.85)
  elseif event == "lost" then
    rec.state = "lost"
    playUi("warning1", 1.0)
    refreshHeroDownBanner()
    -- Rescue-fail bark is owned by objective_failed (latched before this event).
    if numParam("va_objective_failed", 0) == 1 then
      -- no second bark
    elseif rec.missionCritical then
      queueBark("Ketha", rec.name .. " is down for this drop — sortie still stands. Get the rest home.")
    else
      queueBark("", rec.name .. " is gone. The line will remember.")
    end
  end
end

function widget:VerdanceBeat(kind, a, b, c, d)
  if kind == "bark" then
    queueBark(a, b, c, true)
  elseif kind == "marker" then
    pcall(Spring.MarkerAddPoint, a, b, c, tostring(d or ""), true)
  elseif kind == "sound" then
    playUi(a, tonumber(b) or 1.0)
  elseif kind == "wave_warning" then
    pcall(Spring.MarkerAddPoint, a, b, c, "Enemy reinforcements: " .. tostring(d or ""), true)
    playUi("warning2", 0.85)
    local wx, wz = tonumber(a), tonumber(c)
    if wx and wz and (wx ~= 0 or wz ~= 0) then
      queueNarrative({
        key = "wave_" .. tostring(wx) .. "_" .. tostring(wz) .. "_" .. tostring(d or ""),
        kind = "threat",
        x = wx, z = wz,
        title = "INBOUND THREAT",
        body = "Enemy reinforcements: " .. tostring(d or "contact"),
        radius = 780,
        seconds = 5,
      })
    end
  elseif kind == "narrative" or kind == "cam" then
    -- Scripted story beat from synced: a=x, b=z, c=title, d=body
    -- Or packed: a=x, b=z, c="title|body|radius|seconds|highlight"
    local nx, nz = tonumber(a), tonumber(b)
    local title, body, radius, seconds, highlight = tostring(c or "REPORT"), tostring(d or ""), 620, 6, false
    if type(c) == "string" and c:find("|", 1, true) then
      local parts = {}
      for part in string.gmatch(c, "[^|]+") do parts[#parts + 1] = part end
      title = parts[1] or title
      body = parts[2] or body
      radius = tonumber(parts[3]) or radius
      seconds = tonumber(parts[4]) or seconds
      highlight = parts[5] == "1" or parts[5] == "true"
      if d and tostring(d) ~= "" and (not parts[2] or parts[2] == "") then
        body = tostring(d)
      end
    end
    if nx and nz then
      queueNarrative({
        kind = "story",
        x = nx, z = nz,
        title = title,
        body = body,
        radius = radius,
        seconds = seconds,
        highlightObjective = highlight,
      })
    end
  elseif kind == "tenebrium_loot" then
    -- a=take, b=bank, c=featureID — soft toast only; discovery zoom is LOS-driven.
  elseif kind == "tech_locked" then
    -- Legacy act-gate bark (gate is retired; keep quiet unless harness forces it).
    queueBark("Doctrine", "Fabrication locked (harness). Live play uses Tnb/BP only.", 5)
    playUi("warning1", 0.5)
  end
end
