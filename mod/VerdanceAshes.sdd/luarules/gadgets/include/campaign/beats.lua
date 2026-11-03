-- campaign/beats.lua: in-mission beats (authored triggers)
-- Part of game_verdance_campaign.lua, loaded into that gadget's environment
-- (VFS.Include with the gadget table), so its globals are the gadget's globals.
-- Provides: beatsEnabled, beatsNoteFact, beatsOnFeatureBuildStep, beatsOnGameStart,
-- beatsOnUnitCommand, beatsOnUnitCreated, beatsOnUnitDamaged, beatsOnUnitDestroyed, checkBeats,
-- configureBeats
-- Uses: crew, heroes, mission_data, objective_pad, objectives, reinforcements, start, state,
-- waterline

-- In-mission beats: data-driven WC3-style triggers. The hub writes them into the seed
-- (verdance.campaign.voice, and verdance.campaign.opening for mission 1); this part only runs them.
--
-- A beat: { id, trigger, afterBeat, notBefore, cancelIf, actions }
--   afterBeat  an id or a list of ids: the beat waits until every one has fired ("armed"), and an
--              "elapsed" trigger counts from the moment the last of them fired
--   notBefore  seconds of game time before which the beat does not fire
--   cancelIf   a list of triggers: if any is met while the beat waits, it is dropped unfired. This is
--              how a prompt goes away when the player has already done the thing.
-- Triggers: time · elapsed · sortie_start · company_landed · zone_entered · near_point ·
--   objective_progress · objective_complete · extraction_started · wave_spawned ·
--   hero_down · hero_recovered · hero_lost · player_selected · player_moved · player_attacked ·
--   player_built · enemy_killed · beat_fired · any_of · all_of
--   The player_* facts and enemy_killed take atLeast (default 1); fresh = true counts only what
--   happened after the beat's afterBeat fired.
-- Actions: bark · clear_bark · marker · field_mark · clear_mark · sound · wave · spawn · hydrology ·
--   objective_secondary · objective_stage
-- A point (marker, field_mark, spawn, objective_stage, near_point) is at = pad | objective | goal |
-- last_kill | company | overlook, or a zoneId, or normalised x/z.
local beats = {}              -- compiled pending beats (each fires, or is cancelled, once)
beatsEnabled = false
local beatFiredAt = {}        -- beatId -> frame it fired (afterBeat prerequisites)
local beatFactsAt = {}        -- beatId -> the facts as they stood when it fired ("fresh" counts)
local SEC = 30

-- What the player has done this sortie. Counted from the call-ins at the bottom of this part.
local facts = { selected = 0, moved = 0, attacked = 0, built = 0, kills = 0 }
local FACT_OF = { player_selected = "selected", player_moved = "moved", player_attacked = "attacked",
                  player_built = "built", enemy_killed = "kills" }
local lastKill = nil          -- { x, z } of the last enemy unit the player destroyed
local goal = nil              -- the staged first goal { x, z, r } (objective_stage 1)
local damageWatch = { on = false, release = false }
local PUBLIC = { public = true }

local function snapshotFacts()
  return { selected = facts.selected, moved = facts.moved, attacked = facts.attacked, built = facts.built, kills = facts.kills }
end

local function noteFact(k)
  facts[k] = facts[k] + 1
  if facts[k] == 1 then
    Spring.Echo("VA_BEAT_FACT " .. k .. " frame=" .. tostring(Spring.GetGameFrame and Spring.GetGameFrame() or 0))
  end
end

-- A hero the company brought: not a field recruit lying in the field as a wreck to be raised
-- (those are "down" from frame 2, and a "hero down" bark about a stranger is wrong).
local function isCompanyHero(rec)
  return rec ~= nil and not rec.wasFieldRecruit and not rec.recruitable
end

local function companyHeroIn(state1, state2)
  for _, rec in pairs(heroes) do
    if isCompanyHero(rec) and (rec.state == state1 or rec.state == state2) then return true end
  end
  return false
end

local function heroOnField(heroId)
  local rec = heroes[tostring(heroId or "")]
  return rec ~= nil and rec.state == "alive" and (rec.recruited == true or not rec.wasFieldRecruit)
end

-- ---------------------------------------------------------------- points
local function objectivePoint()
  local ox = tonumber((Spring.GetGameRulesParam("va_objective_x"))) or -1
  local oz = tonumber((Spring.GetGameRulesParam("va_objective_z"))) or -1
  if ox >= 0 and oz >= 0 then return ox, oz end
  if targetZoneRect then return (targetZoneRect[1] + targetZoneRect[3]) * 0.5, (targetZoneRect[2] + targetZoneRect[4]) * 0.5 end
  return nil
end

-- On the line from the pad toward the farm (towardX/Z, normalised: the hub's pick), or the objective,
-- stopShort elmos before it and never nearer the pad than minFromPad.
local function overlookPoint(a)
  local px, pz = VA_padPoint()
  local ox, oz
  if a.towardX ~= nil and a.towardZ ~= nil then
    ox, oz = normalizedToElmos(tonumber(a.towardX), Game.mapSizeX or 0), normalizedToElmos(tonumber(a.towardZ), Game.mapSizeZ or 0)
  else
    ox, oz = objectivePoint()
  end
  if not (px and ox) then return ox or px, oz or pz end
  local dx, dz = ox - px, oz - pz
  local d = math.sqrt(dx * dx + dz * dz)
  if d < 1 then return px, pz end
  local want = math.max(d - (tonumber(a.stopShort) or 0), math.min(d, tonumber(a.minFromPad) or 0))
  return px + dx / d * want, pz + dz / d * want
end

local function beatPoint(a)
  local at = a.at
  if at == "pad" then return VA_padPoint()
  elseif at == "objective" then return objectivePoint()
  elseif at == "goal" then if goal then return goal.x, goal.z end return nil
  elseif at == "last_kill" then if lastKill then return lastKill.x, lastKill.z end return nil
  elseif at == "company" then return teamUnitCentroid(playerTeamID)
  elseif at == "overlook" then return overlookPoint(a)
  end
  if a.zoneId then
    local rect = zoneRectFor(a.zoneId)
    if rect then return (rect[1] + rect[3]) * 0.5, (rect[2] + rect[4]) * 0.5 end
  end
  if a.x ~= nil or a.z ~= nil then
    return normalizedToElmos(tonumber(a.x) or 0.5, Game.mapSizeX or 0), normalizedToElmos(tonumber(a.z) or 0.5, Game.mapSizeZ or 0)
  end
  return nil
end

function beatActionXYZ(action)
  local x, z = beatPoint(action)
  if not x then
    x = normalizedToElmos(tonumber(action.x) or 0.5, Game.mapSizeX or 0)
    z = normalizedToElmos(tonumber(action.z) or 0.5, Game.mapSizeZ or 0)
  end
  return x, Spring.GetGroundHeight(x, z) or 0, z
end

local function playerNear(x, z, r)
  local units = Spring.GetUnitsInCylinder(x, z, r, playerTeamID)
  return units ~= nil and #units > 0
end

local function companyLanded()
  if VA_HOT and VA_HOT.pending then return false end
  return (Spring.GetTeamUnitCount(playerTeamID) or 0) > 0
end

-- ---------------------------------------------------------------- triggers
local NO_PARAMS = { objective_complete = true, extraction_started = true, sortie_start = true, company_landed = true }

local function compileCond(t)
  if type(t) ~= "table" then return nil end
  local kind = tostring(t.type or "")
  local c = { kind = kind }
  if kind == "time" then
    c.frame = tonumber(t.frame) or math.floor((tonumber(t.seconds) or 0) * SEC)
  elseif kind == "elapsed" then
    c.frames = math.floor((tonumber(t.seconds) or 0) * SEC)
  elseif kind == "zone_entered" then
    c.rect = zoneRectFor(t.zoneId)
    if not c.rect then return nil end
  elseif kind == "near_point" then
    c.at, c.zoneId, c.x, c.z = t.at, t.zoneId, t.x, t.z
    c.radius = tonumber(t.radius) or 300
  elseif kind == "objective_progress" then
    c.atLeast = tonumber(t.atLeast) or 0.5
  elseif kind == "wave_spawned" then
    c.index = tonumber(t.index) or 1
  elseif kind == "hero_down" or kind == "hero_recovered" or kind == "hero_lost" then
    c.heroId = t.heroId and tostring(t.heroId) or nil
  elseif kind == "beat_fired" then
    c.beat = t.beat and tostring(t.beat) or nil
    if not c.beat then return nil end
  elseif FACT_OF[kind] then
    c.fact = FACT_OF[kind]
    c.atLeast = tonumber(t.atLeast) or 1
    c.fresh = t.fresh == true
  elseif kind == "any_of" or kind == "all_of" then
    c.of = {}
    for _, sub in ipairs(t.of or {}) do
      local s = compileCond(sub)
      if not s then return nil end
      c.of[#c.of + 1] = s
    end
    if #c.of == 0 then return nil end
  elseif not NO_PARAMS[kind] then
    return nil
  end
  return c
end

local function condMet(c, b, frame)
  local k = c.kind
  if c.fact then
    local base = (c.fresh and b.armedFacts and b.armedFacts[c.fact]) or 0
    return facts[c.fact] - base >= c.atLeast
  elseif k == "elapsed" then
    return frame - (b.armedAt or frame) >= c.frames
  elseif k == "time" then
    return frame >= (c.frame or 0)
  elseif k == "any_of" then
    for _, s in ipairs(c.of) do if condMet(s, b, frame) then return true end end
    return false
  elseif k == "all_of" then
    for _, s in ipairs(c.of) do if not condMet(s, b, frame) then return false end end
    return true
  elseif k == "beat_fired" then
    return beatFiredAt[c.beat] ~= nil
  elseif k == "sortie_start" then
    return true   -- beatsOnGameStart fires these before the first frame; this is the fallback
  elseif k == "company_landed" then
    return companyLanded()
  elseif k == "near_point" then
    local x, z = beatPoint(c)
    return x ~= nil and playerNear(x, z, c.radius)
  elseif k == "zone_entered" then
    return scanZoneRect(c.rect) == true
  elseif k == "objective_progress" then
    if objectiveTargetCount <= 0 then return false end
    return (objectiveTargetsDestroyed / objectiveTargetCount) >= (c.atLeast or 0.5)
  elseif k == "wave_spawned" then
    return waves.spawned >= (c.index or 1)
  elseif k == "objective_complete" then
    return objectiveComplete
  elseif k == "extraction_started" then
    -- There is no extract loop any more: "extraction started" = the EXTRACT phase
    -- opened (every objective done); the player ends the sortie via the manifest.
    return extraObj.announced == true
  elseif k == "hero_down" then
    if c.heroId then return heroInState(c.heroId, "down", "down_pending_wreck") end
    return companyHeroIn("down", "down_pending_wreck")
  elseif k == "hero_recovered" then
    if c.heroId then return heroWasRecovered(c.heroId) end
    for _, rec in pairs(heroes) do
      if isCompanyHero(rec) and rec.state == "alive" and rec.everDown then return true end
    end
    return false
  elseif k == "hero_lost" then
    if c.heroId then return heroInState(c.heroId, "lost") end
    return companyHeroIn("lost")
  end
  return false
end

function compileBeats()
  local list = mission and mission.beats
  if type(list) ~= "table" then return end
  for _, b in ipairs(list) do
    local t = b.trigger or {}
    local compiled = {
      id = tostring(b.id or ("beat_" .. tostring(#beats + 1))),
      cond = compileCond(t),
      after = {},
      notBefore = math.floor((tonumber(b.notBefore) or 0) * SEC),
      actions = b.actions or {},
    }
    if type(b.afterBeat) == "table" then
      for _, id in ipairs(b.afterBeat) do compiled.after[#compiled.after + 1] = tostring(id) end
    elseif b.afterBeat then
      compiled.after[1] = tostring(b.afterBeat)
    end
    local ok = compiled.cond ~= nil
    if ok and type(b.cancelIf) == "table" then
      compiled.cancel = {}
      for _, ct in ipairs(b.cancelIf) do
        local c = compileCond(ct)
        if c then compiled.cancel[#compiled.cancel + 1] = c else ok = false end
      end
    end
    if ok then
      beats[#beats + 1] = compiled
      for _, c in ipairs(compiled.cancel or {}) do if c.fact == "attacked" then damageWatch.on = true end end
      if compiled.cond.fact == "attacked" then damageWatch.on = true end
    else
      Spring.Echo("VA_BEAT_INVALID id=" .. tostring(b.id) .. " type=" .. tostring(t.type))
    end
  end
  Spring.Echo("VA_BEATS_COMPILED count=" .. tostring(#beats))
end

-- ---------------------------------------------------------------- actions
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

-- The staged job (mission 1): stage 1 is a small first goal with a ring on the ground, stage 2 the
-- real job. The HUD reads va_op_stage; the words come from the hub.
local function runObjectiveStage(action)
  local stage = tonumber(action.stage) or 1
  if stage <= 1 then
    local x, z = beatPoint(action)
    if x then
      goal = { x = x, z = z, r = tonumber(action.radius) or 300 }
      Spring.SetGameRulesParam("va_op_goal_x", math.floor(x), PUBLIC)
      Spring.SetGameRulesParam("va_op_goal_z", math.floor(z), PUBLIC)
      Spring.SetGameRulesParam("va_op_goal_r", math.floor(goal.r), PUBLIC)
    end
    Spring.SetGameRulesParam("va_op_goal_label", tostring(action.label or ""), PUBLIC)
  else
    Spring.SetGameRulesParam("va_op_job_label", tostring(action.label or ""), PUBLIC)
    -- The objective's mark was placed at GameStart, before the living shell's targets were claimed
    -- (it fell back to the zone's box centre). Now they are: put the mark on the farm itself.
    if publishObjectiveMarker then pcall(publishObjectiveMarker) end
  end
  Spring.SetGameRulesParam("va_op_stage", stage, PUBLIC)
  Spring.Echo("VA_OBJECTIVE_STAGE " .. tostring(stage) .. " " .. tostring(action.label or ""))
  if SendToUnsynced then SendToUnsynced("VERDANCE_MISSION_EVENT", "objective_stage", tostring(stage)) end
end

-- bark: priority (ambient | line | prompt), accent (an Ash colour name) and tag (clear_bark's key)
-- ride in one string, so the bark still fits the four values VERDANCE_BEAT carries.
local function barkStyle(action)
  return tostring(action.priority or "ambient") .. "|" .. tostring(action.accent or "") .. "|" .. tostring(action.tag or "")
end

function runBeatActions(b)
  for _, action in ipairs(b.actions or {}) do
    local kind = tostring(action.type or "")
    if kind == "bark" and SendToUnsynced then
      if action.onlyIfHero and not heroOnField(action.onlyIfHero) then
        Spring.Echo("VA_BEAT_BARK_SKIPPED id=" .. b.id .. " hero=" .. tostring(action.onlyIfHero))
      else
        SendToUnsynced("VERDANCE_BEAT", "bark", tostring(action.speaker or "Ketha"), tostring(action.text or ""), tonumber(action.seconds) or 7, barkStyle(action))
      end
    elseif kind == "clear_bark" and SendToUnsynced then
      SendToUnsynced("VERDANCE_BEAT", "clear_bark", tostring(action.tag or ""), 0, 0, "")
    elseif kind == "marker" and SendToUnsynced then
      local x, y, z = beatActionXYZ(action)
      SendToUnsynced("VERDANCE_BEAT", "marker", x, y, z, tostring(action.text or ""))
    elseif kind == "field_mark" and SendToUnsynced then
      local x, _, z = beatActionXYZ(action)
      local spec = tostring(action.shape or "goal") .. "|" .. tostring(tonumber(action.radius) or 120) .. "|" .. tostring(tonumber(action.seconds) or 30)
      SendToUnsynced("VERDANCE_BEAT", "field_mark", tostring(action.id or b.id), x, z, spec)
    elseif kind == "clear_mark" and SendToUnsynced then
      SendToUnsynced("VERDANCE_BEAT", "clear_mark", tostring(action.id or ""), 0, 0, "")
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
    elseif kind == "objective_stage" then
      runObjectiveStage(action)
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

-- ---------------------------------------------------------------- the tick
local function armedAt(b)
  local at, last = 0, nil
  for _, id in ipairs(b.after) do
    local f = beatFiredAt[id]
    if not f then return nil end
    if f >= at then at, last = f, id end
  end
  return at, last
end

local function fireBeat(b, i, frame)
  table.remove(beats, i)
  beatFiredAt[b.id] = frame
  beatFactsAt[b.id] = snapshotFacts()
  runBeatActions(b)
end

local function stepBeat(b, i, frame)
  if not b.armedAt then
    local at, last = armedAt(b)
    if not at then return end
    b.armedAt = (#b.after > 0) and at or frame
    b.armedFacts = last and beatFactsAt[last] or snapshotFacts()
  end
  if b.cancel then
    for _, c in ipairs(b.cancel) do
      if condMet(c, b, frame) then
        table.remove(beats, i)
        Spring.Echo("VA_BEAT_CANCELLED id=" .. b.id .. " by=" .. c.kind)
        return
      end
    end
  end
  if frame >= b.notBefore and condMet(b.cond, b, frame) then fireBeat(b, i, frame) end
end

function checkBeats(frame)
  if damageWatch.release then
    damageWatch.release = false
    pcall(function() gadgetHandler:RemoveCallIn("UnitDamaged") end)
  end
  if #beats == 0 then return end
  for i = #beats, 1, -1 do
    local b = beats[i]
    if b then stepBeat(b, i, frame) end
  end
end

-- The sortie's units are placed: run the beats that set the stage before anyone moves (the staged
-- job's first goal, so the infil card and the board show it). Called by gadget:GameStart.
function beatsOnGameStart()
  if not beatsEnabled then return end
  local frame = Spring.GetGameFrame and Spring.GetGameFrame() or 0
  for i = #beats, 1, -1 do
    local b = beats[i]
    if b.cond.kind == "sortie_start" and #b.after == 0 then
      b.armedAt, b.armedFacts = frame, snapshotFacts()
      fireBeat(b, i, frame)
    end
  end
end

-- ---------------------------------------------------------------- facts (call-ins)
local ORDER = { move = {}, attack = {}, work = {} }
local function orderTables()
  if not CMD or next(ORDER.move) then return end
  for _, n in ipairs({ "MOVE", "FIGHT", "PATROL" }) do if CMD[n] then ORDER.move[CMD[n]] = true end end
  for _, n in ipairs({ "ATTACK", "FIGHT", "AREA_ATTACK", "MANUALFIRE", "DGUN" }) do if CMD[n] then ORDER.attack[CMD[n]] = true end end
  for _, n in ipairs({ "RECLAIM", "RESURRECT", "REPAIR", "CAPTURE", "RESTORE" }) do if CMD[n] then ORDER.work[CMD[n]] = true end end
end

-- An order the player gave (not one a gadget gave for them: the pack drag, a spawn's first move).
-- State toggles (fire state, move state, on/off) do not count: widgets set those on their own.
-- Called by gadget:UnitCommand.
function beatsOnUnitCommand(unitTeam, cmdID, fromSynced)
  if not beatsEnabled or unitTeam ~= playerTeamID or fromSynced == true then return end
  orderTables()
  cmdID = tonumber(cmdID) or 0
  local move, attack, work = ORDER.move[cmdID], ORDER.attack[cmdID], ORDER.work[cmdID] or cmdID < 0
  if not (move or attack or work) then return end
  noteFact("selected")   -- nobody orders a unit they have not selected
  if move then noteFact("moved") end
  if attack then noteFact("attacked") end
  if work then noteFact("built") end
end

local function isEnemyTeam(teamID)
  if teamID == nil or teamID == playerTeamID or teamID == gaiaTeamID then return false end
  return not Spring.AreTeamsAllied(teamID, playerTeamID)
end

-- Our first hit on them. The call-in is released once a beat no longer needs it.
-- Called by gadget:UnitDamaged.
function beatsOnUnitDamaged(unitTeam, attackerTeam)
  if attackerTeam ~= playerTeamID or not damageWatch.on then return end
  if not isEnemyTeam(unitTeam) then return end
  noteFact("attacked")
  damageWatch.on = false
  damageWatch.release = true   -- removed on the next tick, not inside BAR's call-in loop
end

-- Called by gadget:UnitDestroyed.
function beatsOnUnitDestroyed(unitID, unitTeam, attackerTeam)
  if not beatsEnabled or attackerTeam ~= playerTeamID or not isEnemyTeam(unitTeam) then return end
  local x, _, z = Spring.GetUnitPosition(unitID)
  if x then lastKill = { x = x, z = z } end
  noteFact("kills")
  if facts.attacked == 0 then noteFact("attacked") end
end

-- A unit our builder started (a build, or a wreck raised). Not a factory's: a hero bay lands already
-- printing on repeat, and the player queueing a factory is counted as the order (UnitCommand).
-- Called by gadget:UnitCreated.
function beatsOnUnitCreated(unitTeam, builderID)
  if not beatsEnabled or not builderID or unitTeam ~= playerTeamID then return end
  if Spring.GetUnitTeam(builderID) ~= playerTeamID then return end
  local defID = Spring.GetUnitDefID and Spring.GetUnitDefID(builderID)
  local ud = defID and UnitDefs and UnitDefs[defID]
  if ud and ud.isFactory then return end
  noteFact("built")
end

-- Our builder working a wreck (reclaim or raise). Called by gadget:AllowFeatureBuildStep.
function beatsOnFeatureBuildStep(builderTeam)
  if beatsEnabled and builderTeam == playerTeamID then noteFact("built") end
end

-- Facts only the UI can see (selection is unsynced): "vabeatfact selected" from the field marks
-- widget. Called by gadget:RecvLuaMsg.
function beatsNoteFact(what, playerID)
  if not beatsEnabled or what ~= "selected" then return end
  if playerID ~= nil and Spring.GetPlayerInfo then
    local _, _, spectator, teamID = Spring.GetPlayerInfo(playerID, false)
    if spectator or teamID ~= playerTeamID then return end
  end
  noteFact("selected")
end

-- Called by gadget:Initialize.
function configureBeats(modOptions, profiling)
  -- In-mission beats ride the same profiling gate as escalation waves;
  -- va_beats forces them either way.
  local beatOpt = modOptions.va_beats
  if beatOpt ~= nil and tostring(beatOpt) ~= "" then
    beatsEnabled = truthy(beatOpt)
  else
    beatsEnabled = not profiling
  end
  if beatsEnabled then compileBeats() end
  -- Nothing waits on a hit: BAR need not call us for every point of damage in the match.
  if not damageWatch.on then pcall(function() gadgetHandler:RemoveCallIn("UnitDamaged") end) end
end
