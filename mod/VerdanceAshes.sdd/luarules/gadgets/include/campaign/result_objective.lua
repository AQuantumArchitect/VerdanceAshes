-- campaign/result_objective.lua: the result's objective parts: how it completed, targets destroyed, secondaries, surviving installs, shell scars
-- Part of game_verdance_campaign.lua, loaded into that gadget's environment
-- (VFS.Include with the gadget table), so its globals are the gadget's globals.
-- Provides: objectiveCompleteHow, recordShellScar, resultCaptureFields, resultObjectiveFields
-- Uses: heroes, objective_checks, objectives, state

objectiveCompleteHow = ""

-- The primary objective id, listed once it completed by any path (destroyed,
-- zone held, node claimed). Python reads this as "the objective was done".
local function destroyedObjectiveIdsJson()
  local oid = mission.objective and mission.objective.id
  if oid and objectiveComplete then
    return '[' .. jstr(oid) .. ']'
  end
  return '[]'
end

-- One row for the primary objective: how far it got and how it completed.
-- status is the mechanic that finished it, not a judgement of the sortie.
local function objectiveResultsJson()
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
local function secondaryResultsJson()
  return MarksLib.resultsJson(marks, jstr, jnum)
end

-- Fusion vaults + their beamer teeth that are still standing at terminal.
-- Campaign state keeps these so the prize is here when you come back, and
-- offscreen aggression can schedule a defend sortie instead of silent wipe.
local function survivingInstallsJson()
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

-- Living-shell scar events this sortie (occupation model lock — wrath not listed).
local shellScarEvents = {}
function recordShellScar(unitID, unitDefID)
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

local function shellScarsJson()
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

-- The objective: what kind, whether and how it completed, its targets and marks, the rescue latch,
-- and what the company did to the living shell.
function resultObjectiveFields(c)
  return {
    '"objectiveKind":' .. jstr(c.obj.kind or ""),
    '"objectiveMode":' .. jstr(vaObjectiveMode(c.obj.kind)),
    '"objectiveComplete":' .. tostring(objectiveComplete == true),
    '"objectiveCompleteHow":' .. jstr(objectiveCompleteHow or ""),
    '"objectiveCompleteFrame":' .. jnum(objectiveCompleteFrame),
    '"objectiveTargetsTotal":' .. jnum(objectiveTargetCount),
    '"objectiveTargetsDestroyed":' .. jnum(objectiveTargetsDestroyed),
    '"destroyedObjectiveIds":' .. destroyedObjectiveIdsJson(),
    '"objectiveResults":' .. objectiveResultsJson(),
    -- required secondary marks still open + the full-victory gate the HUD showed (EXTRACT phase)
    '"requiredMarksLeft":' .. jnum(MarksLib.requiredLeft(marks)),
    '"allObjectivesDone":' .. tostring(vaAllObjectivesDone() == true),
    '"secondaryResults":' .. secondaryResultsJson(),
    '"purge":{"armed":' .. tostring(extraObj.purge == true)
      .. ',"done":' .. tostring(extraObj.purgeDone == true) .. '}',
    -- objectiveFailed is the SoT latch (rescue contract destroyed). Alias kept
    -- for older hub/kernel readers. Fail hero lets company.fieldPool mark lost.
    '"objectiveFailed":' .. tostring(rescueContractFailed == true),
    '"objectiveFailReason":' .. jstr(rescueContractFailReason or ""),
    '"objectiveFailHero":' .. jstr(rescueContractFailHero or ""),
    '"rescueContractFailed":' .. tostring(rescueContractFailed == true),
    '"shellScars":' .. shellScarsJson(),
    '"survivingInstalls":' .. survivingInstallsJson(),
  }
end

-- The capture state machine (facts): the pocket cleared, the hold, the node claimed.
function resultCaptureFields(c)
  local nodeClaimed = capture.nodeClaimed or (objectiveCompleteHow == "node_claimed")
  return {
    '"nodeClaimed":' .. tostring(nodeClaimed == true),
    '"nodeClaimedFrame":' .. jnum(nodeClaimedFrame),
    '"pocketCleared":' .. tostring(capture.pocketCleared == true),
    '"capturePhase":' .. jstr(capture.phase or "idle"),
    '"captureMode":' .. tostring(capture.mode == true),
    '"regrowWaves":' .. jnum(capture.regrowWaves or 0),
    '"zoneHoldFrames":' .. jnum(zoneHoldFrames),
  }
end

