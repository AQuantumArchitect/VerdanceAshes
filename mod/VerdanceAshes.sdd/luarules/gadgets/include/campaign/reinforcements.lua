-- campaign/reinforcements.lua: enemy response waves and where they enter
-- Part of game_verdance_campaign.lua, loaded into that gadget's environment
-- (VFS.Include with the gadget table), so its globals are the gadget's globals.
-- Provides: enemyEntry, enemyResponseTarget, mercTeamID, mercWaveUsed, mercsAllied,
-- objectiveTeamID, scanZoneRect, spawnWave, teamUnitCentroid, waves
-- Uses: state, telemetry, units

-- Enemy reinforcements share one budget per sortie chapter (global: main-chunk local limit).
VA_REINFORCE = { usedChapter = nil }

-- Pillar B: in-mission dynamism (escalation waves, hot extraction, callable
-- merc reinforcements). Enemy reinforcements are inferred from the enemy team's
-- own composition, so no seed/compiler change is needed. Disabled during
-- headless/balance profiling unless va_escalation forces it on.
objectiveTeamID = nil             -- team the objective camp belongs to
mercTeamID = nil                  -- allied Null Merc foothold team, if any
mercsAllied = false
mercWaveUsed = false
-- Waves + doctrine packed (Lua 5.1 main-chunk local budget).
waves = { enabled = false, interval = 2700, nextFrame = 1800, spawned = 0, max = 4, baseSize = 4 }

function scanZoneRect(rect)
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
function teamUnitCentroid(teamID)
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

-- What a team sends: its own combat units (no builders, no commanders, no decoys).
function responseDefs(teamID)
  if tostring(teamFaction[teamID] or ""):lower() == "armada" then
    return { "armflea", "armflea", "armflea", "armflea", "armpw", "armpw", "armpw", "armpw", "armwar", "armwar" }
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

-- The player's side can neither see the spot nor stand near it.
local SIGHT_MARGIN = 2200
function unseenByPlayer(x, z)
  local y = Spring.GetGroundHeight(x, z)
  local ok, any, los, radar = pcall(Spring.GetPositionLosState, x, y, z, playerAllyTeamID)
  if not ok or any or los or radar then return false end
  for _, team in ipairs(Spring.GetTeamList() or {}) do
    if team == playerTeamID or Spring.AreTeamsAllied(playerTeamID, team) then
      for _, unitID in ipairs(Spring.GetTeamUnits(team) or {}) do
        local ux, _, uz = Spring.GetUnitPosition(unitID)
        if ux and (ux - x) * (ux - x) + (uz - z) * (uz - z) < SIGHT_MARGIN * SIGHT_MARGIN then return false end
      end
    end
  end
  return true
end

-- THE entry rule, for every reinforcement: a team comes in only on the map edge, only inside a
-- zone its faction truly holds (mission.entryZones, from the kernel), and, if hostile, only where
-- the player cannot see and is not near. No such spot means no reinforcements: nobody walks in
-- from nowhere. (Allies such as the Mercs enter the same way but may be seen arriving.)
function enemyEntry(teamID, defs, towardX, towardZ)
  local faction = tostring(teamFaction[teamID] or ""):lower()
  local hostile = not Spring.AreTeamsAllied(teamID, playerTeamID)
  local owned = {}
  local entry = (mission and mission.entryZones) or {}
  local blocs = (faction == "nullmercs") and { "nullmercs", "ashwalkers" } or { faction }
  for _, bloc in ipairs(blocs) do
    for _, zid in ipairs(entry[bloc] or {}) do owned[tostring(zid)] = true end
  end
  -- ... and the zones it holds right now: the most defensive value standing there is its.
  for zid, row in pairs(zoneDvTable()) do
    local best, leader = 0, nil
    for f, v in pairs(row) do if v > best then best, leader = v, f end end
    for _, bloc in ipairs(blocs) do if leader == bloc then owned[zid] = true end end
  end
  if next(owned) == nil then return nil, "no_owned_zone" end
  local sx, sz, inset, step = Game.mapSizeX or 1, Game.mapSizeZ or 1, 160, 128
  local spots = {}
  local function consider(x, z)
    local zone = zoneForPosition(x, z)
    if zone and owned[tostring(zone.zoneId)] then spots[#spots + 1] = { x = x, z = z } end
  end
  for x = inset, sx - inset, step do consider(x, inset); consider(x, sz - inset) end
  for z = inset, sz - inset, step do consider(inset, z); consider(sx - inset, z) end
  if #spots == 0 then return nil, "no_owned_edge" end
  local ax, az = towardX or sx * 0.5, towardZ or sz * 0.5
  table.sort(spots, function(a, b)
    return (a.x - ax) ^ 2 + (a.z - az) ^ 2 < (b.x - ax) ^ 2 + (b.z - az) ^ 2
  end)
  for _, pos in ipairs(spots) do
    local ok = true
    for i, defName in ipairs(defs) do
      local def = UnitDefNames[defName]
      local ux, uz = pos.x + ((i - 1) % 3 - 1) * 48, pos.z + math.floor((i - 1) / 3) * 48
      if not def or (hostile and not unseenByPlayer(ux, uz))
          or not Spring.TestMoveOrder(def.id, ux, Spring.GetGroundHeight(ux, uz), uz, 0, 0, 0, true, true, true) then
        ok = false
        break
      end
    end
    if ok then return pos.x, pos.z end
  end
  return nil, "every_owned_edge_in_sight"
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

function spawnWave(fromTeamID, count, targetX, targetZ, label)
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
  if VA_REINFORCE.usedChapter == sortieChapter then return 0 end
  local defs = responseDefs(fromTeamID)
  if #defs == 0 then return 0 end
  local cx, cz = enemyEntry(fromTeamID, defs, targetX, targetZ)
  if not cx then
    Spring.Echo("VA_WAVE_SKIPPED team=" .. tostring(fromTeamID) .. " kind=" .. tostring(label) .. " reason=" .. tostring(cz))
    return 0
  end
  local spawned = 0
  for i, defName in ipairs(defs) do
    local x = cx + ((i - 1) % 3 - 1) * 48
    local z = cz + math.floor((i - 1) / 3) * 48
    if Spring.AreTeamsAllied(fromTeamID, playerTeamID) or unseenByPlayer(x, z) then
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
    VA_REINFORCE.usedChapter = sortieChapter
    Spring.Echo("VA_WAVE_SPAWNED team=" .. tostring(fromTeamID) .. " count=" .. spawned
      .. " kind=" .. tostring(label or "reinforce") .. " rim=1")
    if SendToUnsynced then
      SendToUnsynced("VERDANCE_BEAT", "wave_warning", cx, Spring.GetGroundHeight(cx, cz), cz,
        "Enemy response approaching from the map edge")
    end
  end
  return spawned
end
