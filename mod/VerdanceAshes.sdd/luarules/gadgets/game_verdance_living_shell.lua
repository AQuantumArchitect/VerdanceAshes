if not VFS.Include("LuaRules/Configs/va_active.lua") then return false end -- plain BAR unless the hub launched this
local gadget = gadget

function gadget:GetInfo()
  return {
    name = "Verdance Living Shell",
    desc = "Spawn frozen living-shell templates + contact wrath (ephemeral, not saved)",
    author = "Verdance",
    date = "2026-07-27",
    license = "GPL v2 or later",
    layer = 1,
    enabled = true,
  }
end

if not gadgetHandler:IsSyncedCode() then
  return
end

-- Packed state (avoid 200-local pressure if this file grows).
local S = {
  mission = nil,
  shell = nil,
  wrath = nil,
  spawned = false,
  contactFrame = nil,
  wrathFired = false,
  playerTeam = 0,
  enemyTeam = nil,
  shellUnitSet = {},
  ephemeralSet = {},
  primaryZoneId = nil,
  mapSizeX = 1,
  mapSizeZ = 1,
}

local ECO_OBJECTIVE = {
  armsolar = true, armadvsol = true, armwin = true, armfus = true, armmakr = true,
  armestor = true, armmstor = true, armmex = true, armmoho = true,
  corsolar = true, coradvsol = true, corwin = true, corfus = true, cormakr = true,
  corestor = true, cormstor = true, cormex = true, cormoho = true,
  legsolar = true, legwin = true, legmex = true,
}

local function loadMission()
  local ok, data = pcall(VFS.Include, "singleplayer/verdance_ashes/generated/va_current.lua")
  if ok and type(data) == "table" then return data end
  return nil
end

local function nrm(v, size)
  v = tonumber(v) or 0.5
  size = size or 1
  if v > 1.5 then return v end -- already elmos
  return v * size
end

local function shellCoord(v, size, fallback, slot)
  local n = tonumber(v)
  size = size or 1
  -- Player pads are stored as Spring elmos. A value above 1 is a real
  -- map position, not a broken normalized coordinate. Snapping those to
  -- the map center is what moved a base onto the other side.
  if n and n > 1.5 then
    if size > 1 and n > size - 8 then n = size - 8 end
    if n < 8 then n = 8 end
    return n
  end
  local repaired = (not n) or n < 0 or n > 1
  if repaired then n = tonumber(fallback) end
  if not n or n < 0 or n > 1 then n = 0.5 end
  if repaired and slot then
    n = n + 0.014 * ((slot % 4) - 1.5)
  end
  n = math.max(0.04, math.min(0.96, n))
  return n * size
end

-- The old center-snap parked pads on four points: 0.5 ± 0.007 and ± 0.021.
local function centerSnapArtifact(x, z, sizeX, sizeZ)
  if not x or not z or not sizeX or not sizeZ then return false end
  if x < 1.5 or z < 1.5 or sizeX < 512 or sizeZ < 512 then return false end
  local function hit(v, size)
    local d = math.abs(v / size - 0.5)
    return math.abs(d - 0.007) < 0.002 or math.abs(d - 0.021) < 0.002
  end
  return hit(x, sizeX) and hit(z, sizeZ)
end

local function inRect(x, z, rect)
  if not rect then return false end
  return x >= rect[1] and z >= rect[2] and x <= rect[3] and z <= rect[4]
end

local function zoneRect(zoneId)
  if not zoneId or not S.mission or not S.mission.zoneMap then return nil end
  local zones = S.mission.zoneMap.zones
  if type(zones) ~= "table" then return nil end
  for _, z in ipairs(zones) do
    if z.zoneId == zoneId and z.bounds then
      local b = z.bounds
      local x1 = nrm(b.xMin, S.mapSizeX)
      local x2 = nrm(b.xMax, S.mapSizeX)
      local z1 = nrm(b.zMin, S.mapSizeZ)
      local z2 = nrm(b.zMax, S.mapSizeZ)
      return { x1, z1, x2, z2 }
    end
  end
  return nil
end

local function teamCentroid(teamID)
  local units = Spring.GetTeamUnits(teamID) or {}
  local sx, sz, n = 0, 0, 0
  for _, u in ipairs(units) do
    if not S.ephemeralSet[u] then
      local x, _, z = Spring.GetUnitPosition(u)
      if x then sx = sx + x; sz = sz + z; n = n + 1 end
    end
  end
  if n < 1 then
    return S.mapSizeX * 0.5, S.mapSizeZ * 0.5
  end
  return sx / n, sz / n
end

local function spawnShell()
  local shell = S.shell
  if not shell or not shell.units then return 0 end
  local teamID = tonumber(shell.teamID) or S.enemyTeam
  if not teamID then
    Spring.Echo("VA_SHELL_SPAWN_SKIP no enemy team")
    return 0
  end
  S.enemyTeam = teamID
  S.primaryZoneId = shell.primaryZoneId and tostring(shell.primaryZoneId) or nil
  local primaryPocketId = shell.primaryPocketId and tostring(shell.primaryPocketId) or nil
  local primaryRect = zoneRect(S.primaryZoneId)
  local pocketCenters = {}
  for _, pocket in ipairs(shell.pockets or {}) do
    if pocket.pocketId and pocket.center then
      pocketCenters[tostring(pocket.pocketId)] = pocket.center
    end
  end
  local spawned = 0
  local objectiveTagged = 0
  local spawnLimit = tonumber(shell.spawnLimit or shell.openingSpawnLimit or "")
  local shellUnits = shell.units
  -- openingPocketOnly is the builder alias; localPocketOnly is the live flag.
  local pocketOnly = shell.localPocketOnly or shell.openingPocketOnly
  if pocketOnly and primaryPocketId then
    shellUnits = {}
    for _, u in ipairs(shell.units) do
      local forceRole = tostring(u.forceRole or "")
      local isFp = (forceRole == "player_footprint") or (u.role == "player_footprint")
      -- Company pads always spawn even when occupation is pocket-gated.
      if isFp or (u.pocketId and tostring(u.pocketId) == primaryPocketId) then
        shellUnits[#shellUnits + 1] = u
      end
    end
  end
  for _, u in ipairs(shellUnits) do
    if spawnLimit and spawned >= spawnLimit then break end
    local defName = u.unitDefName or u.def
    if defName and UnitDefNames and UnitDefNames[defName] then
      local rawX = tonumber(u.x)
      local rawZ = tonumber(u.z)
      local center = u.pocketId and pocketCenters[tostring(u.pocketId)]
      local fallbackX = center and center[1]
      local fallbackZ = center and center[2]
      local x = shellCoord(rawX, S.mapSizeX, fallbackX, spawned)
      local z = shellCoord(rawZ, S.mapSizeZ, fallbackZ, spawned)
      local forceRoleEarly = tostring(u.forceRole or "")
      local footprintEarly = (forceRoleEarly == "player_footprint") or (u.role == "player_footprint")
      if footprintEarly and centerSnapArtifact(rawX, rawZ, S.mapSizeX, S.mapSizeZ) then
        -- A previous drop saved the teleported pile. Leave it off the map.
        x = nil
      end
      if x then
      local y = Spring.GetGroundHeight(x, z)
      local facing = tonumber(u.facing) or 0
      -- Held prizes (player-bloc continuity): spawn on the company team so the
      -- fusion + beamer ring is still here when you come back to defend it.
      -- player_footprint: company-built pads from prior Drop (not occupation).
      local spawnTeam = teamID
      local forceRole = tostring(u.forceRole or "")
      local isFootprint = (forceRole == "player_footprint")
        or (u.role == "player_footprint")
      local held = (u.heldByPlayer == true or u.heldByPlayer == 1
        or forceRole == "held_install" or isFootprint)
      if held and S.playerTeam ~= nil then
        spawnTeam = S.playerTeam
      end
      local unitID = Spring.CreateUnit(defName, x, y, z, facing, spawnTeam)
      if unitID then
        spawned = spawned + 1
        if not isFootprint then
          S.shellUnitSet[unitID] = true
          Spring.SetUnitRulesParam(unitID, "va_living_shell", 1, { public = true })
        else
          Spring.SetUnitRulesParam(unitID, "va_player_footprint", 1, { public = true })
        end
        if u.pocketId then
          Spring.SetUnitRulesParam(unitID, "va_shell_pocket", tostring(u.pocketId), { public = true })
        end
        if u.zoneId then
          Spring.SetUnitRulesParam(unitID, "va_shell_zone", tostring(u.zoneId), { public = true })
        end
        if u.keepClass then
          Spring.SetUnitRulesParam(unitID, "va_keep_class", tostring(u.keepClass), { public = true })
        end
        -- Decoy commanders: Armada autonomous eco-farm swarm nodes (not real coms).
        local isDecoy = (u.keepClass == "decoy_node")
          or (u.role == "autonomous_decoy_farmer")
          or (defName == "armdecom" or defName == "cordecom" or defName == "legdecom")
        -- Optional high-value marks (e.g. Greenest center fusion vaults):
        -- fusion keepClass=high_value becomes a bonus secondary, not the primary raid.
        local isHighValue = (u.keepClass == "high_value")
        if isFootprint then
          Spring.SetUnitRulesParam(unitID, "va_force_role", "player_footprint", { public = true })
          if CMD then
            if CMD.FIRE_STATE then pcall(Spring.GiveOrderToUnit, unitID, CMD.FIRE_STATE, { 2 }, {}) end
            if CMD.MOVE_STATE then pcall(Spring.GiveOrderToUnit, unitID, CMD.MOVE_STATE, { 0 }, {}) end
          end
        elseif held then
          Spring.SetUnitRulesParam(unitID, "va_held_install", 1, { public = true })
          Spring.SetUnitRulesParam(unitID, "va_force_role", "held_install", { public = true })
          if isHighValue then
            Spring.SetUnitRulesParam(unitID, "va_high_value", 1, { public = true })
          end
          if CMD then
            if CMD.FIRE_STATE then pcall(Spring.GiveOrderToUnit, unitID, CMD.FIRE_STATE, { 2 }, {}) end
            if CMD.MOVE_STATE then pcall(Spring.GiveOrderToUnit, unitID, CMD.MOVE_STATE, { 0 }, {}) end
          end
        elseif isDecoy then
          Spring.SetUnitRulesParam(unitID, "va_decoy_node", 1, { public = true })
          Spring.SetUnitRulesParam(unitID, "va_force_role", "decoy_farmer", { public = true })
          -- Occupation farmers: they already built the pocket, but must look alive —
          -- fire at will, maneuver, light patrol. Not HOLD+STOP (reads as broken AI).
          if CMD then
            if CMD.MOVE_STATE then pcall(Spring.GiveOrderToUnit, unitID, CMD.MOVE_STATE, { 1 }, {}) end
            if CMD.FIRE_STATE then pcall(Spring.GiveOrderToUnit, unitID, CMD.FIRE_STATE, { 2 }, {}) end
            if CMD.PATROL then
              local r = 220
              local px = x + r
              local pz = z
              pcall(Spring.GiveOrderToUnit, unitID, CMD.PATROL, { px, y, pz }, {})
              pcall(Spring.GiveOrderToUnit, unitID, CMD.PATROL, { x, y, z + r }, { "shift" })
              pcall(Spring.GiveOrderToUnit, unitID, CMD.PATROL, { x - r, y, z }, { "shift" })
              pcall(Spring.GiveOrderToUnit, unitID, CMD.PATROL, { x, y, z - r }, { "shift" })
            elseif CMD.FIGHT then
              pcall(Spring.GiveOrderToUnit, unitID, CMD.FIGHT, { x + 80, y, z + 80 }, {})
            end
          end
        elseif isHighValue then
          local sid = "bonus_fus_" .. tostring(u.pocketId or u.zoneId or "mark"):lower()
          Spring.SetUnitRulesParam(unitID, "va_force_role", "objective_secondary", { public = true })
          Spring.SetUnitRulesParam(unitID, "va_secondary_id", sid, { public = true })
          Spring.SetUnitRulesParam(unitID, "va_secondary_required", 0, { public = true })
          Spring.SetUnitRulesParam(unitID, "va_high_value", 1, { public = true })
        else
          -- Tag primary-pocket eco as raid objective structures.
          local isPrimary = false
          if S.primaryZoneId and u.zoneId and tostring(u.zoneId) == S.primaryZoneId then
            isPrimary = true
          elseif primaryRect and inRect(x, z, primaryRect) then
            isPrimary = true
          end
          if shell.primaryPocketId and u.pocketId and tostring(u.pocketId) == tostring(shell.primaryPocketId) then
            isPrimary = true
          end
          if isPrimary and ECO_OBJECTIVE[defName] then
            Spring.SetUnitRulesParam(unitID, "va_force_role", "objective_target", { public = true })
            objectiveTagged = objectiveTagged + 1
          else
            Spring.SetUnitRulesParam(unitID, "va_force_role", "occupation", { public = true })
          end
        end
      end
      end
    end
  end
  Spring.Echo("VA_SHELL_SPAWNED count=" .. tostring(spawned)
    .. " objectiveEco=" .. tostring(objectiveTagged)
    .. " limit=" .. tostring(spawnLimit or 0)
    .. " pocket=" .. tostring(primaryPocketId or "all")
    .. " team=" .. tostring(teamID)
    .. " template=" .. tostring(shell.templateId or "?"))
  return spawned
end

local function fireWrath()
  local wrath = S.wrath
  if not wrath or not wrath.enabled then return end
  local teamID = S.enemyTeam
  if not teamID then return end
  local pack = wrath.pack or {}
  local units = pack.units or wrath.units or {}
  local px, pz = teamCentroid(S.playerTeam)
  local scatter = tonumber(pack.scatterElmos or wrath.scatterElmos) or 180
  local spawned = 0
  local i = 0
  for _, entry in ipairs(units) do
    local defName = entry.unitDefName or entry.def
    local count = tonumber(entry.count) or 1
    if defName and UnitDefNames and UnitDefNames[defName] then
      for _ = 1, count do
        i = i + 1
        local ang = (i * 2.399) -- golden-ish
        local r = scatter * (0.35 + (i % 5) * 0.12)
        local ux = px + math.cos(ang) * r
        local uz = pz + math.sin(ang) * r
        ux = math.max(32, math.min(S.mapSizeX - 32, ux))
        uz = math.max(32, math.min(S.mapSizeZ - 32, uz))
        local uy = Spring.GetGroundHeight(ux, uz)
        local unitID = Spring.CreateUnit(defName, ux, uy, uz, 0, teamID)
        if unitID then
          spawned = spawned + 1
          S.ephemeralSet[unitID] = true
          Spring.SetUnitRulesParam(unitID, "va_ephemeral", 1, { public = true })
          Spring.SetUnitRulesParam(unitID, "va_wrath", 1, { public = true })
          if CMD and CMD.FIGHT then
            Spring.GiveOrderToUnit(unitID, CMD.FIGHT, { px, Spring.GetGroundHeight(px, pz), pz }, {})
          end
        end
      end
    end
  end
  Spring.Echo("VA_WRATH_DROP count=" .. tostring(spawned) .. " nearPlayer=1")
  if wrath.telegraph ~= false then
    local bark = (pack.telegraphBark or wrath.telegraphBark
      or "Contact. Armada response inbound - get clear.")
    Spring.Echo("VA_WRATH_BARK " .. tostring(bark))
    if SendToUnsynced then
      SendToUnsynced("VERDANCE_BEAT", "bark", "Ketha", tostring(bark), 8)
    end
  end
end

local function noteContact(why)
  if S.contactFrame then return end
  if not S.wrath or not S.wrath.enabled then return end
  S.contactFrame = Spring.GetGameFrame()
  local sec = tonumber(S.wrath.responseSeconds) or 120
  Spring.Echo("VA_CONTACT why=" .. tostring(why or "hit")
    .. " responseSeconds=" .. tostring(sec)
    .. " frame=" .. tostring(S.contactFrame))
  Spring.SetGameRulesParam("va_contact_frame", S.contactFrame, { public = true })
  Spring.SetGameRulesParam("va_wrath_deadline", S.contactFrame + math.floor(sec * 30), { public = true })
  if S.wrath.telegraph ~= false then
    Spring.Echo("VA_WRATH_BARK Contact made. Response inbound in ~" .. tostring(sec) .. "s.")
    if SendToUnsynced then
      SendToUnsynced("VERDANCE_BEAT", "bark", "Ketha",
        "Contact. You've got about " .. tostring(sec) .. " seconds before the response.", 7)
    end
  end
end

local function modFlag(name)
  local mo = Spring.GetModOptions and Spring.GetModOptions() or {}
  local v = mo[name]
  if v == true or v == 1 then return true end
  if type(v) == "string" then
    v = v:lower()
    return v == "1" or v == "true" or v == "yes" or v == "enabled"
  end
  return false
end

function gadget:Initialize()
  -- Offline shell bakes must not inject campaign livingShell occupation.
  if modFlag("va_shell_bake") then
    Spring.Echo("VA_SHELL_SKIP bake mode - no occupation spawn")
    return
  end
  S.mission = loadMission()
  if not S.mission then return end
  S.shell = S.mission.livingShell
  S.wrath = S.mission.wrath
  if S.mission.balance and S.mission.balance.playerTeamID then
    S.playerTeam = tonumber(S.mission.balance.playerTeamID) or 0
  end
  if S.shell and S.shell.teamID then
    S.enemyTeam = tonumber(S.shell.teamID)
  end
  if S.shell and S.shell.enabled then
    Spring.Echo("VA_SHELL_ARMED template=" .. tostring(S.shell.templateId or "?"))
  end
  if S.wrath and S.wrath.enabled then
    Spring.Echo("VA_WRATH_ARMED responseSeconds=" .. tostring(S.wrath.responseSeconds or 120))
  end
end

function gadget:GameStart()
  S.mapSizeX = Game.mapSizeX or 1
  S.mapSizeZ = Game.mapSizeZ or 1
end

function gadget:GameFrame(frame)
  if not S.spawned and S.shell and S.shell.enabled and frame >= 1 then
    -- Wait one frame so campaign gadget can establish teams / playable setup.
    if frame >= 8 then
      S.spawned = true
      if not S.enemyTeam and S.shell.teamID then
        S.enemyTeam = tonumber(S.shell.teamID)
      end
      -- Fallback: first non-player team with units or from playable setup.
      if not S.enemyTeam and S.mission.playableSetup and S.mission.playableSetup.forces then
        for _, f in ipairs(S.mission.playableSetup.forces) do
          if f.teamID and tonumber(f.teamID) ~= S.playerTeam then
            S.enemyTeam = tonumber(f.teamID)
            break
          end
        end
      end
      spawnShell()
    end
  end

  if S.contactFrame and not S.wrathFired and S.wrath and S.wrath.enabled then
    local sec = tonumber(S.wrath.responseSeconds) or 120
    local deadline = S.contactFrame + math.floor(sec * 30)
    if frame >= deadline then
      S.wrathFired = true
      fireWrath()
    end
  end
end

function gadget:UnitDamaged(unitID, unitDefID, unitTeam, damage, paralyzer, weaponDefID, projectileID, attackerID, attackerDefID, attackerTeam)
  if S.contactFrame then return end
  if not S.wrath or not S.wrath.enabled then return end
  if not attackerTeam then return end
  -- Player hit enemy shell / garrison, or enemy hit player.
  if attackerTeam == S.playerTeam and unitTeam ~= S.playerTeam then
    noteContact("player_damaged_enemy")
  elseif unitTeam == S.playerTeam and attackerTeam ~= S.playerTeam then
    noteContact("enemy_damaged_player")
  end
end

function gadget:UnitDestroyed(unitID, unitDefID, unitTeam, attackerID, attackerDefID, attackerTeam)
  if S.ephemeralSet[unitID] then
    S.ephemeralSet[unitID] = nil
    return
  end
  if S.shellUnitSet[unitID] then
    S.shellUnitSet[unitID] = nil
    if attackerTeam == S.playerTeam then
      noteContact("shell_structure_killed")
    end
  end
end
