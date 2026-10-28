-- campaign/objective_checks.lua: the periodic checks and completion: onObjectiveComplete, all marks done, purge, wipe, the soft clock
-- Part of game_verdance_campaign.lua, loaded into that gadget's environment
-- (VFS.Include with the gadget table), so its globals are the gadget's globals.
-- Provides: onObjectiveComplete, tickObjectiveChecks, vaAllObjectivesDone, vaMaybeAnnounceAllDone
-- Uses: beats, crew, hero_joins, hero_wrecks, heroes, mentors, objective_presence, objectives,
-- reinforcements, result_objective, start, state, terminal

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

local function vaCheckPurge(frame)
  if not extraObj.purge or extraObj.purgeDone then return end
  local left = 0
  for teamID in pairs(extraObj.purgeTeams) do left = left + (Spring.GetTeamUnitCount(teamID) or 0) end
  Spring.SetGameRulesParam("va_purge_left", left, { public = true })   -- the HUD's "purge · n left"
  if left > 0 then return end
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

local function checkPlayerWipe(frame)
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
local function checkSoftClock(frame)
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

-- Called by gadget:GameFrame.
function tickObjectiveChecks(frame)
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
end
