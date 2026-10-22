if not VFS.Include("LuaRules/Configs/va_active.lua") then return false end -- plain BAR unless the hub launched this
local gadget = gadget

function gadget:GetInfo()
  return {
    name = "Verdance Autoplay Playtest Rig",
    desc = "Deterministic BAR command rig for unattended campaign sortie tests",
    author = "Verdance tools",
    date = "2026-08-29",
    license = "GPL v2 or later",
    layer = 1,
    enabled = true,
  }
end

if not gadgetHandler:IsSyncedCode() then
  -- The objectives widget pauses the sim. Headless zip runs with LuaUI off,
  -- but if a widget still pauses, release it so the real extract hold can tick.
  local zipUnpause = false
  local unpauseEchoed = false

  local function zipRequested()
    local options = Spring.GetModOptions() or {}
    local v = options.va_autoplay_zip
    if v == true or v == 1 or v == "1" or v == "true" or v == "yes" then return true end
    return options.va_autoplay == "zip"
  end

  function gadget:Initialize()
    zipUnpause = zipRequested()
    if zipUnpause then
      Spring.Echo("VA_ZIP unsynced armed")
    end
  end

  function gadget:Update()
    if not zipUnpause then return end
    local frame = (Spring.GetGameFrame and Spring.GetGameFrame()) or 0
    if frame < 1 then return end
    local paused = false
    if Spring.GetGameSpeed then
      local _, _, isPaused = Spring.GetGameSpeed()
      paused = isPaused == true
    end
    if paused then
      pcall(Spring.SendCommands, "pause 0")
      if not unpauseEchoed then
        unpauseEchoed = true
        Spring.Echo("VA_ZIP unpause frame=" .. tostring(frame))
      end
    end
  end

  return
end

local enabled = false
local zip = false
local playerTeam = 0
local phase = "waiting"
local lastOrderFrame = -999999
local lastZipEcho = -999999
local ORDER_PERIOD = 120

local function truthy(v)
  if v == true or v == 1 then return true end
  if type(v) == "string" then
    v = v:lower()
    return v == "1" or v == "true" or v == "yes" or v == "enabled"
  end
  return false
end

local function isStructure(ud)
  return ud and (ud.isBuilding or ud.isFactory or ud.isImmobile or (ud.speed or 0) <= 0)
end

local function isRezBot(ud)
  return ud and (ud.canResurrect == true or (ud.customParams and
    (ud.customParams.canresurrect == "1" or ud.customParams.reclaim_speed)))
end

local function positionForRule(xKey, zKey)
  local x = tonumber((Spring.GetGameRulesParam(xKey)))
  local z = tonumber((Spring.GetGameRulesParam(zKey)))
  if x and z and x > 0 and z > 0 then return x, z end
  return nil, nil
end

local function orderAt(unitID, cmd, x, z)
  if not unitID or not x or not z or not cmd then return false end
  local y = Spring.GetGroundHeight(x, z) or 0
  local ok = pcall(Spring.GiveOrderToUnit, unitID, cmd, { x, y, z }, {})
  return ok
end

local function collectForce()
  local mobile, rez, wounded = {}, {}, {}
  local units = Spring.GetTeamUnits(playerTeam) or {}
  for i = 1, #units do
    local unitID = units[i]
    if Spring.ValidUnitID(unitID) and not Spring.GetUnitIsDead(unitID) then
      local ud = UnitDefs[Spring.GetUnitDefID(unitID) or -1]
      if ud then
        if isRezBot(ud) then
          rez[#rez + 1] = unitID
        elseif not isStructure(ud) and (ud.speed or 0) > 0 then
          mobile[#mobile + 1] = unitID
          local hp, maxHp = Spring.GetUnitHealth(unitID)
          hp, maxHp = tonumber(hp) or 0, tonumber(maxHp) or 0
          if maxHp > 0 and hp / maxHp < 0.92 then
            wounded[#wounded + 1] = { id = unitID, frac = hp / maxHp }
          end
        end
      end
    end
  end
  table.sort(wounded, function(a, b) return a.frac < b.frac end)
  return mobile, rez, wounded
end

local function issueRepairAndGuard(rez, mobile, wounded)
  for i = 1, #rez do
    local bot = rez[i]
    local target = wounded[((i - 1) % math.max(1, #wounded)) + 1]
    if target and CMD.REPAIR then
      pcall(Spring.GiveOrderToUnit, bot, CMD.REPAIR, { target.id }, {})
    elseif mobile[1] and CMD.GUARD then
      pcall(Spring.GiveOrderToUnit, bot, CMD.GUARD, { mobile[1] }, {})
    end
  end
end

local function issueObjectiveOrders(frame)
  local tx, tz = positionForRule("va_objective_x", "va_objective_z")
  local ex, ez = positionForRule("va_pad_x", "va_pad_z")
  local objectiveDone = tonumber((Spring.GetGameRulesParam("va_objective_complete"))) == 1
  local terminal = tonumber((Spring.GetGameRulesParam("va_terminal"))) == 1
  if terminal then return end

  local mobile, rez, wounded = collectForce()
  issueRepairAndGuard(rez, mobile, wounded)

  if objectiveDone then
    if phase ~= "extract" then
      phase = "extract"
      Spring.Echo("VA_AUTOPLAY phase=extract mobile=" .. tostring(#mobile)
        .. " rez=" .. tostring(#rez))
    end
    if ex and CMD.MOVE then
      for i = 1, #mobile do orderAt(mobile[i], CMD.MOVE, ex, ez) end
      for i = 1, #rez do orderAt(rez[i], CMD.MOVE, ex, ez) end
    end
  elseif tx and CMD.FIGHT then
    if phase ~= "objective" then
      phase = "objective"
      Spring.Echo("VA_AUTOPLAY phase=objective target=" .. tostring(math.floor(tx))
        .. "," .. tostring(math.floor(tz)) .. " mobile=" .. tostring(#mobile)
        .. " rez=" .. tostring(#rez))
    end
    for i = 1, #mobile do orderAt(mobile[i], CMD.FIGHT, tx, tz) end
  elseif frame > 300 and phase == "waiting" then
    Spring.Echo("VA_AUTOPLAY waiting_for_markers")
  end
end

local function firstLiving()
  local units = Spring.GetTeamUnits(playerTeam) or {}
  for i = 1, #units do
    local id = units[i]
    if Spring.ValidUnitID(id) and not Spring.GetUnitIsDead(id) then
      return id
    end
  end
  return nil
end

-- Delete hostiles the way a weapon kill does: not reclaimed, so the wreck
-- and the death event still happen. Gaia stays, except raptor bodies.
local function explodeHostiles(attacker, limit)
  local killed = 0
  local gaia = -1
  if Spring.GetGaiaTeamID then gaia = Spring.GetGaiaTeamID() end
  local teams = Spring.GetTeamList() or {}
  for t = 1, #teams do
    local team = teams[t]
    local take = false
    if team ~= playerTeam and team ~= gaia then
      local allied = false
      if Spring.AreTeamsAllied then
        allied = Spring.AreTeamsAllied(team, playerTeam) and true or false
      end
      if not allied then take = true end
    end
    if take then
      local units = Spring.GetTeamUnits(team) or {}
      for i = 1, #units do
        if killed >= limit then return killed end
        local id = units[i]
        if Spring.ValidUnitID(id) and not Spring.GetUnitIsDead(id) then
          local ok = false
          if attacker then
            ok = pcall(Spring.DestroyUnit, id, false, false, attacker)
          else
            ok = pcall(Spring.DestroyUnit, id, false, false)
          end
          if ok then killed = killed + 1 end
        end
      end
    end
  end
  if gaia >= 0 and killed < limit then
    local units = Spring.GetTeamUnits(gaia) or {}
    for i = 1, #units do
      if killed >= limit then return killed end
      local id = units[i]
      if Spring.ValidUnitID(id) and not Spring.GetUnitIsDead(id) then
        local defID = Spring.GetUnitDefID(id)
        local ud = defID and UnitDefs[defID]
        local name = (ud and ud.name) or ""
        if string.find(name, "raptor", 1, true) or string.find(name, "hive", 1, true) then
          local ok = pcall(Spring.DestroyUnit, id, false, false, attacker)
          if ok then killed = killed + 1 end
        end
      end
    end
  end
  return killed
end

-- Map-hack move: plant mobiles on the pad and give them a move order so the
-- real presence check (extract cylinder, objective hold) sees them there.
local function placeForce(x, z)
  local units = Spring.GetTeamUnits(playerTeam) or {}
  local moved = 0
  for i = 1, #units do
    local id = units[i]
    if Spring.ValidUnitID(id) and not Spring.GetUnitIsDead(id) then
      local defID = Spring.GetUnitDefID(id)
      local ud = defID and UnitDefs[defID]
      if ud and not ud.isBuilding and not ud.isFactory and (ud.speed or 0) > 0 then
        local ox = x + ((moved % 7) - 3) * 48
        local oz = z + math.floor(moved / 7) * 48
        pcall(Spring.SetUnitPosition, id, ox, oz, true)
        if CMD and CMD.MOVE then
          local y = Spring.GetGroundHeight(ox, oz) or 0
          pcall(Spring.GiveOrderToUnit, id, CMD.MOVE, { ox, y, oz }, {})
        end
        moved = moved + 1
      end
    end
  end
  return moved
end

local function braceForce()
  local units = Spring.GetTeamUnits(playerTeam) or {}
  for i = 1, #units do
    local id = units[i]
    if Spring.ValidUnitID(id) and not Spring.GetUnitIsDead(id) then
      local hp, maxhp = Spring.GetUnitHealth(id)
      hp = tonumber(hp)
      maxhp = tonumber(maxhp)
      if hp and maxhp and maxhp > 0 and hp < maxhp then
        pcall(Spring.SetUnitHealth, id, maxhp)
      end
    end
  end
end

local function zipTick(frame)
  if tonumber((Spring.GetGameRulesParam("va_terminal"))) == 1 then
    if phase ~= "terminal" then
      phase = "terminal"
      Spring.Echo("VA_ZIP phase=terminal frame=" .. tostring(frame))
    end
    return
  end
  -- Living-shell objectives are claimed from frame 20. Exploding before that
  -- deletes the buildings the claim is looking for, and the raid never starts.
  braceForce()
  local attacker = firstLiving()
  local killed = 0
  if frame >= 60 then
    killed = explodeHostiles(attacker, 80)
  end
  local objectiveDone = tonumber((Spring.GetGameRulesParam("va_objective_complete"))) == 1
  local tx, tz
  local nextPhase
  if objectiveDone then
    nextPhase = "extract"
    tx, tz = positionForRule("va_pad_x", "va_pad_z")
    if not tx then tx, tz = positionForRule("va_objective_x", "va_objective_z") end
  else
    nextPhase = "objective"
    tx, tz = positionForRule("va_objective_x", "va_objective_z")
  end
  local moved = 0
  if tx then moved = placeForce(tx, tz) end
  if nextPhase ~= phase or frame - lastZipEcho >= 90 then
    phase = nextPhase
    lastZipEcho = frame
    local hold = tonumber((Spring.GetGameRulesParam("va_hold_frames"))) or 0
    local got = tonumber((Spring.GetGameRulesParam("va_objective_destroyed"))) or 0
    local total = tonumber((Spring.GetGameRulesParam("va_objective_total"))) or 0
    Spring.Echo("VA_ZIP phase=" .. phase
      .. " frame=" .. tostring(frame)
      .. " killed=" .. tostring(killed)
      .. " moved=" .. tostring(moved)
      .. " hold=" .. tostring(hold)
      .. " obj=" .. tostring(got) .. "/" .. tostring(total)
      .. " at=" .. tostring(tx and math.floor(tx) or 0)
      .. "," .. tostring(tz and math.floor(tz) or 0))
  end
end

function gadget:Initialize()
  local options = Spring.GetModOptions() or {}
  zip = truthy(options.va_autoplay_zip) or options.va_autoplay == "zip"
  enabled = zip or truthy(options.va_autoplay)
  playerTeam = tonumber(options.va_autoplay_team or 0) or 0
  if zip then
    Spring.Echo("VA_ZIP_ARMED team=" .. tostring(playerTeam))
  elseif enabled then
    Spring.Echo("VA_AUTOPLAY_ARMED team=" .. tostring(playerTeam)
      .. " orderPeriod=" .. tostring(ORDER_PERIOD))
  end
end

function gadget:GameFrame(frame)
  if not enabled then return end
  if zip then
    if frame < 8 or frame % 5 ~= 0 then return end
    zipTick(frame)
    return
  end
  if frame < 30 or frame - lastOrderFrame < ORDER_PERIOD then return end
  lastOrderFrame = frame
  issueObjectiveOrders(frame)
end
