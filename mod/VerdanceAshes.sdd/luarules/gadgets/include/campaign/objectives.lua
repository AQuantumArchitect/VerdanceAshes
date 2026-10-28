-- campaign/objectives.lua: the objective: kind and mode, the pad, living-shell claims, presence / fortify / wipe / soft clock
-- Part of game_verdance_campaign.lua, loaded into that gadget's environment
-- (VFS.Include with the gadget table), so its globals are the gadget's globals.
-- Provides: CHECK_PERIOD, CLEAR_FRACTION, VA_KINDS, VA_padPoint, capture, checkPlayerWipe,
-- checkPresenceObjective, checkSoftClock, claimLivingShellObjectives,
-- claimOptionalHighValueSecondaries, extraObj, extractLoop, nodeClaimedFrame, objectiveComplete,
-- objectiveCompleteFrame, objectiveKind, objectiveTargetCount, objectiveTargets,
-- objectiveTargetsDestroyed, onObjectiveComplete, shellObjectivesClaimed, targetZoneRect,
-- vaAllObjectivesDone, vaCheckPurge, vaMaybeAnnounceAllDone, vaObjectiveMode, zoneHoldFrames,
-- zoneRectFor
-- Uses: crew, heroes, mission_data, reinforcements, result, start, state, telemetry, terminal,
-- units

-- Objective automation (gadget-env globals — Lua 5.1 main-chunk local budget).
CHECK_PERIOD = 30                 -- frames between objective checks
PRESENCE_HOLD_DEFAULT = 900       -- 30s hold for seize/gate objectives
WIPE_GRACE_FRAMES = 900           -- no wipe-defeat before 30s

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
--   targets  anything else (hive_clear_or_bypass, kings_showdown, jump_gate): every booked
--            target must die, unless a dedicated gadget decides the kind (VA_GADGET_KINDS).
-- Every job is territory (2026-10-27): Python turns raids, strikes and the Eye's contracts into
-- seize_lane and keeps the old kind as contractKind, the reason the zone is worth taking.
VA_KINDS = {
  capture = { seize_lane = true, gate_control = true, hold_plateau = true, siege = true, multipressure = true },
  survive = { survive_wilds = true },
  fortify = { fortify_zone = true, home_founding = true },
}
-- kind -> the one completion word its own gadget sends (onObjectiveComplete ignores any other)
VA_GADGET_KINDS = { jump_gate = "jumped" }

objectiveTargets = {}             -- unitID -> forceId (objective_target structures)
objectiveTargetCount = 0
objectiveTargetsDestroyed = 0
objectiveComplete = false

zoneHoldFrames = 0
-- Frames at which the objective facts latched (0 = never). Exported in the result.
objectiveCompleteFrame = 0
nodeClaimedFrame = 0
-- The pad geometry only (pass five: there is no extract loop, timer or hold —
-- the sortie ends when the player confirms the manifest in game_verdance_exfil.lua).
extractLoop = { padRadius = 560 }

extraObj = {
  purge = false,
  purgeDone = false,
  purgeTeams = {},     -- teamID -> true
  announced = false,   -- all-objectives-done broadcast latch
}
CLEAR_FRACTION = 0.6              -- pocket clear threshold for capture claims
-- Capture claim state (one table — Lua 5.1 local budget).
-- Fantasy: clear living-shell pocket, then hold it while regrow pressure tries to retake.
capture = {
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

targetZoneRect = nil              -- {x1, z1, x2, z2} in elmos

local extractionZoneRect = nil

-- ============================================================
-- OBJECTIVE AUTOMATION
-- Real win/loss detection: target destruction, zone holds,
-- extraction, commander loss, player wipe.
-- ============================================================

function objectiveKind()
  return mission and mission.objective and mission.objective.kind or ""
end

-- How a kind resolves (see VA_KINDS). Gadget-env global: resultJson / setup echo call it.
function vaObjectiveMode(kind)
  kind = tostring(kind or "")
  if VA_KINDS.capture[kind] then return "capture" end
  if VA_KINDS.survive[kind] then return "presence" end
  if VA_KINDS.fortify[kind] then return "fortify" end
  return "targets_all"
end

function zoneRectFor(zoneId)
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
  -- Kinds a dedicated gadget decides take only that gadget's word: no zone hold, no burnt hive
  -- (jump_gate: game_verdance_jump_gate.lua).
  local own = VA_GADGET_KINDS[objectiveKind()]
  if own and how ~= own then return end
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
  -- A presence job (fortify) is measured in defensive value; no enemy building is its target.
  if VA_KINDS.fortify[objectiveKind()] then shellObjectivesClaimed = true; return 0 end
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
  -- One source of marks: the mission's secondaries (the builder declares every vault). A shell
  -- building with no secondary id is booked only under a vault the mission declared.
  local declared = {}
  for _, sec in ipairs((mission and mission.secondaries) or {}) do
    if type(sec) == "table" and sec.id then declared[tostring(sec.id)] = true end
  end
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
            if not declared[sid] then sid = nil end
          end
          -- Fusion vaults are vaults; an escalation side mark on the shell's works is a
          -- structure mark (enrichFromMission flags it required from mission.secondaries).
          if sid then MarksLib.bindTarget(marks, uid, sid, {
            required = false,
            kind = highValue and MarksLib.KIND.vault or MarksLib.KIND.structure,
            label = sid,
          })
          tagged = tagged + 1 end
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

-- Standing on the wound is not taking it: the company's presence there (armed units and
-- defences, the same measure Python claims with at home) must reach mission.objective.claimValue
-- (verdance.world.claim). Published for the rail. Global (the main chunk is at the local cap).
function vaClaimStrength()
  local obj = mission and mission.objective or {}
  local need = tonumber(obj.claimValue) or 0
  local row = obj.targetZoneId and zoneDvTable()[tostring(obj.targetZoneId)] or nil
  local ours = math.floor((row and row.ashwalkers) or 0)
  Spring.SetGameRulesParam("va_claim_value", ours, { public = true })
  Spring.SetGameRulesParam("va_claim_need", need, { public = true })
  return ours >= need
end

function checkPresenceObjective(frame)
  if objectiveComplete then return end
  local kind = objectiveKind()
  if kind == "kings_showdown" or VA_GADGET_KINDS[kind] then return end  -- their own gadget decides; no zone hold stands in
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
      playerPresent = playerPresent and vaClaimStrength()
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
      playerPresent = playerPresent and vaClaimStrength()
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
        Spring.Echo("VA_NODE_CLAIMED zone=" .. tostring(mission.objective and mission.objective.targetZoneId or ""))
        onObjectiveComplete("node_claimed")
      end
      return
    end
    return
  end

  -- Legacy presence (no living shell): stand on zone; pause on contact, reset on leave.
  local playerPresent, enemyCombat = scanZoneRect(targetZoneRect)
      playerPresent = playerPresent and vaClaimStrength()
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
  if frame < WIPE_GRACE_FRAMES or VA_HOT.pending then return end
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
