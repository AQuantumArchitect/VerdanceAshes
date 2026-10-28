-- campaign/objective_targets.lua: what the objective's targets are: the living shell's eco and teeth, high-value marks, and a target going down
-- Part of game_verdance_campaign.lua, loaded into that gadget's environment
-- (VFS.Include with the gadget table), so its globals are the gadget's globals.
-- Provides: marksOnUnitDestroyed, objectiveTargetDestroyed, tickShellClaims
-- Uses: objective_checks, objectives, reinforcements, state, terminal, units

-- ============================================================
-- MODE A: same-map seamless continue (WO-050..053)
-- Soft terminal skips Spring.GameOver; debrief pick reseeds in-place.
-- ============================================================

local function currentMapId()
  return tostring((mission and mission.deploymentMapId) or (zoneMap and zoneMap.mapId) or "")
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
shellObjectivesClaimed = false  -- gadget-env (local budget)
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

local function isLivingShellUnit(uid)
  local v = Spring.GetUnitRulesParam(uid, "va_living_shell")
  return v == 1 or v == true
end

local function isEnemyTeam(team)
  return team and team ~= playerTeamID and team ~= gaiaTeamID
end

-- Book one unit as a target of the objective (force living_shell_primary).
local function bookTarget(uid)
  objectiveTargets[uid] = "living_shell_primary"
  objectiveTargetCount = objectiveTargetCount + 1
end

-- The primary pocket: the shell's primary pocket or zone (or the objective's target zone), plus
-- anything the builder stamped objective_target.
local function primaryPocketOf(shell)
  local p = {}
  p.zone = shell.primaryZoneId and tostring(shell.primaryZoneId)
    or (mission.objective and mission.objective.targetZoneId and tostring(mission.objective.targetZoneId))
    or nil
  p.pocket = shell.primaryPocketId and tostring(shell.primaryPocketId) or nil
  p.rect = p.zone and zoneRectFor(p.zone) or nil
  return p
end

local function inPrimaryPocket(uid, p)
  local pocket = Spring.GetUnitRulesParam(uid, "va_shell_pocket")
  local zone = Spring.GetUnitRulesParam(uid, "va_shell_zone")
  if p.pocket and pocket and tostring(pocket) == p.pocket then return true end
  if p.zone and zone and tostring(zone) == p.zone then return true end
  local x, _, z = Spring.GetUnitPosition(uid)
  if p.rect and x and z and x >= p.rect[1] and z >= p.rect[2] and x <= p.rect[3] and z <= p.rect[4] then
    return true
  end
  return Spring.GetUnitRulesParam(uid, "va_force_role") == "objective_target"
end

-- Pass one: the shell's eco in the primary pocket, and its teeth too when the job is a capture
-- (clearing the pocket means the guns as well) or a raze (leave nothing standing).
local function bookPrimaryPocket(units, p, withTeeth, teamID)
  local tagged = 0
  for i = 1, #units do
    local uid = units[i]
    if Spring.ValidUnitID(uid) and not Spring.GetUnitIsDead(uid) and not objectiveTargets[uid]
        and isLivingShellUnit(uid) then
      local team = Spring.GetUnitTeam(uid)
      local dID = Spring.GetUnitDefID(uid)
      local ud = dID and UnitDefs[dID]
      local claimable = isEcoStructureDef(ud) or (withTeeth and isShellTeethDef(ud, dID))
      if claimable and inPrimaryPocket(uid, p) and isEnemyTeam(team) then
        bookTarget(uid)
        tagged = tagged + 1
        if not teamID then teamID = team end
      end
    end
  end
  return tagged, teamID
end

-- The pocket to fall back on when the primary pad holds nothing: the occupation's primary combat
-- pocket, else its first combat pocket (never an optional target, never a high-value vault).
local function fallbackPocketId()
  local occ = mission and mission.mapOccupation
  if type(occ) ~= "table" then return nil end
  for _, wantPrimary in ipairs({ true, false }) do
    for _, row in ipairs(occ) do
      if type(row) == "table" and row.livingShell and row.pocketId and (row.primary or not wantPrimary)
          and not row.optionalTarget and not row.highValue then
        return tostring(row.pocketId)
      end
    end
  end
  return nil
end

-- Pass two (the primary pad was empty: a hub mark with no shell pocket): book that one pocket's
-- eco, stamped objective_target so the HUD and the builder agree. Never vaults, never the map.
local function bookFallbackPocket(units, teamID)
  local fallbackPocket = fallbackPocketId()
  local tagged = 0
  for i = 1, #units do
    local uid = units[i]
    if Spring.ValidUnitID(uid) and not Spring.GetUnitIsDead(uid) and not objectiveTargets[uid]
        and isLivingShellUnit(uid) then
      local team = Spring.GetUnitTeam(uid)
      local dID = Spring.GetUnitDefID(uid)
      local ud = dID and UnitDefs[dID]
      local role = tostring(Spring.GetUnitRulesParam(uid, "va_force_role") or "")
      local pocket = tostring(Spring.GetUnitRulesParam(uid, "va_shell_pocket") or "")
      local highValue = Spring.GetUnitRulesParam(uid, "va_high_value") == 1 or role == "objective_secondary"
      local pocketOk = (not fallbackPocket) or (pocket == fallbackPocket)
      if pocketOk and not highValue and isEcoStructureDef(ud) and isEnemyTeam(team) then
        bookTarget(uid)
        tagged = tagged + 1
        if not teamID then teamID = team end
        Spring.SetUnitRulesParam(uid, "va_force_role", "objective_target", { public = true })
      end
    end
  end
  if tagged > 0 then
    Spring.Echo("VA_SHELL_OBJECTIVES_EXPANDED count=" .. tostring(tagged)
      .. " pocket=" .. tostring(fallbackPocket or "any_combat")
      .. " reason=empty_primary_pad")
  end
  return tagged, teamID
end

local function armCapture(p, tagged)
  capture.mode = true
  capture.phase = "clear"
  Spring.SetGameRulesParam("va_capture_mode", 1, { public = true })
  Spring.SetGameRulesParam("va_capture_phase", "clear", { public = true })
  Spring.Echo("VA_CAPTURE_ARMED mode=clear_hold_shell pocket="
    .. tostring(p.pocket or p.zone or "?")
    .. " targets=" .. tostring(tagged))
end

-- Book the objective's targets from the living shell, once it has spawned (tickShellClaims).
-- Fortify and survive jobs book nothing: they are measured by standing in the zone. A capture
-- arms the capture state machine (clear, then hold) once its pocket is booked. Returns how many.
local function claimLivingShellObjectives()
  local kind = objectiveKind()
  if VA_KINDS.fortify[kind] then shellObjectivesClaimed = true; return 0 end
  if shellObjectivesClaimed then return 0 end
  local shell = mission and mission.livingShell
  if not shell or shell.enabled == false or VA_KINDS.survive[kind] then
    shellObjectivesClaimed = true
    return 0
  end
  local obj = mission.objective
  local captureMode = VA_KINDS.capture[kind]
    or (obj and obj.captureMode == "clear_hold_shell")
    or (obj and obj.captureMode == true)
  -- Drop 4 raze strength: the whole pocket (teeth included) joins the book
  -- even on destruction kinds — "leave nothing standing" needs a full ledger.
  local razeMode = (obj and tostring(obj.strength or "") == "raze")
  local p = primaryPocketOf(shell)
  local units = Spring.GetAllUnits() or {}
  local tagged, teamID = bookPrimaryPocket(units, p, captureMode or razeMode, objectiveTeamID or findEnemyCampTeam())
  if teamID then objectiveTeamID = teamID end
  if captureMode and (tagged > 0 or shell.enabled) then armCapture(p, tagged) end
  if tagged <= 0 then
    tagged, teamID = bookFallbackPocket(units, teamID)
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
local function claimOptionalHighValueSecondaries()
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

-- Called by gadget:GameFrame.
function tickShellClaims(frame)
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
end

-- An objective target is down: count it, and complete or advance the objective. Called by gadget:UnitDestroyed.
function objectiveTargetDestroyed(unitID)
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
end

-- Called by gadget:UnitDestroyed.
function marksOnUnitDestroyed(unitID)
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
end
