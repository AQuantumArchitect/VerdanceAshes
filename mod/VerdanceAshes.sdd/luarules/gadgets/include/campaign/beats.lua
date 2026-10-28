-- campaign/beats.lua: in-mission beats (authored triggers)
-- Part of game_verdance_campaign.lua, loaded into that gadget's environment
-- (VFS.Include with the gadget table), so its globals are the gadget's globals.
-- Provides: beatsEnabled, checkBeats, compileBeats
-- Uses: heroes, mission_data, objectives, reinforcements, state, waterline

-- In-mission beats: data-driven WC3-style triggers authored into the seed.
local beats = {}              -- compiled pending beats (all fire once)
beatsEnabled = false
local beatFiredSet = {}       -- beatId -> true (afterBeat prerequisites)

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
  if teamID ~= playerTeamID and not Spring.AreTeamsAllied(teamID, playerTeamID) then
    local defs = {}
    for _, u in ipairs(action.units or {}) do
      for _ = 1, tonumber(u.count) or 1 do defs[#defs + 1] = u.unitDefName or u.def end
    end
    local ex, ez = enemyEntry(teamID, defs, x, z)
    if not ex then
      Spring.Echo("VA_BEAT_SPAWN_SKIPPED id=" .. tostring(b.id) .. " reason=" .. tostring(ez))
      return
    end
    x, z = ex, ez
  end
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
