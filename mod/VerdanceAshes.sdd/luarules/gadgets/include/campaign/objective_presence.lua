-- campaign/objective_presence.lua: holding ground: the capture pocket and regrow pressure, presence and fortify checks, claim strength
-- Part of game_verdance_campaign.lua, loaded into that gadget's environment
-- (VFS.Include with the gadget table), so its globals are the gadget's globals.
-- Provides: checkPresenceObjective
-- Uses: objective_checks, objectives, reinforcements, state, telemetry

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

-- Live metrics for player units standing inside a zone rect.
local function playerMetricsInRect(rect)
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

local function checkFortifyObjective(frame)
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
local function vaClaimStrength()
  local obj = mission and mission.objective or {}
  local need = tonumber(obj.claimValue) or 0
  local row = obj.targetZoneId and zoneDvTable()[tostring(obj.targetZoneId)] or nil
  local ours = math.floor((row and row.ashwalkers) or 0)
  Spring.SetGameRulesParam("va_claim_value", ours, { public = true })
  Spring.SetGameRulesParam("va_claim_need", need, { public = true })
  return ours >= need
end

-- One tick of the hold clock on the target zone. Present and uncontested, the clock runs; enemy
-- contact pauses it (regrow waves used to reset it and softlock 22/30 forever); leaving the zone
-- resets it. Publishes the hold for the HUD. True once the clock reaches the hold the objective needs.
local function tickZoneHold()
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
  local cx = (targetZoneRect[1] + targetZoneRect[3]) * 0.5
  local cz = (targetZoneRect[2] + targetZoneRect[4]) * 0.5
  local hw = math.abs(targetZoneRect[3] - targetZoneRect[1]) * 0.5
  local hh = math.abs(targetZoneRect[4] - targetZoneRect[2]) * 0.5
  Spring.SetGameRulesParam("va_hold_cx", math.floor(cx), { public = true })
  Spring.SetGameRulesParam("va_hold_cz", math.floor(cz), { public = true })
  Spring.SetGameRulesParam("va_hold_hw", math.floor(hw), { public = true })
  Spring.SetGameRulesParam("va_hold_hh", math.floor(hh), { public = true })
  return zoneHoldFrames >= required
end

-- Capture, phase one: clear the pocket. It is clear once enough of the booked shell is wrecked
-- (CLEAR_FRACTION), or, with nothing booked, once we stand there in strength and no enemy fights.
-- Then the hold begins, with the first regrow pulse half an interval away.
local function captureClearStep(frame, destroyed, need)
  capture.phase = "clear"
  local cleared
  if objectiveTargetCount > 0 then
    cleared = destroyed >= need
  else
    local playerPresent, enemyCombat = scanZoneRect(targetZoneRect)
    playerPresent = playerPresent and vaClaimStrength()
    cleared = playerPresent and not enemyCombat
  end
  if not cleared then return end
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

-- Capture, phase two: hold the node while the regrow waves try to take it back. A full hold
-- claims the node, and that completes the objective.
local function captureHoldStep(frame)
  fireRegrowPressure(frame)
  if not tickZoneHold() then return end
  capture.nodeClaimed = true
  nodeClaimedFrame = frame
  capture.phase = "claimed"
  Spring.SetGameRulesParam("va_node_claimed", 1, { public = true })
  Spring.SetGameRulesParam("va_capture_phase", "claimed", { public = true })
  Spring.Echo("VA_NODE_CLAIMED zone=" .. tostring(mission.objective and mission.objective.targetZoneId or ""))
  onObjectiveComplete("node_claimed")
end

-- Every CHECK_PERIOD: the objectives measured by standing somewhere.
--   fortify            defensive value in the zone (checkFortifyObjective)
--   capture (a shell)  clear the pocket, then hold the node under regrow pressure
--   capture / survive  without a shell, and a target kind with nothing booked: hold the zone
-- The kings' showdown and the gadget-decided kinds (VA_GADGET_KINDS) are not decided here.
function checkPresenceObjective(frame)
  if objectiveComplete then return end
  local kind = objectiveKind()
  if kind == "kings_showdown" or VA_GADGET_KINDS[kind] then return end
  if VA_KINDS.fortify[kind] then
    checkFortifyObjective(frame)
    return
  end
  local presenceMode = VA_KINDS.capture[kind] or VA_KINDS.survive[kind]
    or (objectiveTargetCount == 0 and targetZoneRect ~= nil)
  if not presenceMode or not targetZoneRect then return end

  if not capture.mode then
    if tickZoneHold() then onObjectiveComplete("zone_held") end
    return
  end
  local frac, destroyed, need = pocketClearProgress()
  Spring.SetGameRulesParam("va_pocket_clear_frac", math.floor(frac * 1000 + 0.5) / 1000, { public = true })
  Spring.SetGameRulesParam("va_capture_phase", capture.phase, { public = true })
  if capture.phase == "clear" or capture.phase == "idle" then
    captureClearStep(frame, destroyed, need)
  elseif capture.phase == "hold" then
    captureHoldStep(frame)
  end
end
