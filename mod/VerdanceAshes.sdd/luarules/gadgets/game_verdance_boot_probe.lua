if not VFS.Include("LuaRules/Configs/va_active.lua") then return false end -- plain BAR unless the hub launched this
function gadget:GetInfo()
  return {
    name = "Verdance Boot Probe",
    desc = "va_boot_probe=1 counts the company, issues one move, then quits. Inert otherwise.",
    author = "Verdance",
    date = "2026-10-02",
    license = "GPL v2 or later",
    layer = 0,
    enabled = true,
  }
end

local function probeArmed()
  local mo = (Spring.GetModOptions and Spring.GetModOptions()) or {}
  local v = mo.va_boot_probe
  return v == true or v == 1 or v == "1" or v == "true"
end

local function queueLen(unitID)
  if not (unitID and Spring.GetUnitCommands) then return 0 end
  local n = Spring.GetUnitCommands(unitID, 0)
  if type(n) == "number" then return n end
  local q = Spring.GetUnitCommands(unitID, 1)
  return (q and #q) or 0
end

local function companySnapshot()
  local playerN, otherN, mobile = 0, 0, nil
  local list = Spring.GetTeamList and Spring.GetTeamList() or { 0, 1 }
  for t = 1, #list do
    local team = list[t]
    local units = Spring.GetTeamUnits(team) or {}
    for i = 1, #units do
      local id = units[i]
      local alive = Spring.ValidUnitID(id) and not Spring.GetUnitIsDead(id)
      if alive then
        if team == 0 then
          playerN = playerN + 1
          if not mobile then
            local defID = Spring.GetUnitDefID(id)
            local ud = defID and UnitDefs[defID]
            if ud and (ud.speed or 0) > 0 then mobile = id end
          end
        else
          otherN = otherN + 1
        end
      end
    end
  end
  return playerN, otherN, mobile
end

if gadgetHandler:IsSyncedCode() then
  local armed = false
  local orderedUnit = nil

  function gadget:Initialize()
    armed = probeArmed()
    if armed then
      Spring.Echo("VA_BOOT_PROBE synced armed")
    end
  end

  function gadget:GameFrame(frame)
    if not armed then return end
    if frame ~= 60 and frame ~= 120 then return end
    local playerN, otherN, mobile = companySnapshot()
    if frame == 60 and mobile and CMD and CMD.MOVE and not orderedUnit then
      local x, _, z = Spring.GetUnitPosition(mobile)
      if x then
        local tx, tz = x + 220, z + 60
        local y = Spring.GetGroundHeight(tx, tz) or 0
        pcall(Spring.GiveOrderToUnit, mobile, CMD.STOP, {}, {})
        pcall(Spring.GiveOrderToUnit, mobile, CMD.MOVE, { tx, y, tz }, {})
        orderedUnit = mobile
      end
    end
    local orderN = queueLen(orderedUnit)
    Spring.Echo("VA_BOOT_PROBE frame=" .. tostring(frame)
      .. " units=" .. tostring(playerN)
      .. " others=" .. tostring(otherN)
      .. " order=" .. tostring(orderN))
    if frame == 120 then
      pcall(Spring.SendCommands, "quitforce")
    end
  end

  return
end

local armed = false
local sawPausedAt = nil
local releasedPause = false
local sampled = false
local orderedUnit = nil
local quitAt = nil

function gadget:Initialize()
  armed = probeArmed()
  if armed then
    Spring.Echo("VA_BOOT_PROBE unsynced armed")
  end
end

function gadget:Update()
  if not armed then return end
  local frame = (Spring.GetGameFrame and Spring.GetGameFrame()) or 0
  if frame < 1 then return end

  local paused = false
  if Spring.GetGameSpeed then
    local _, _, isPaused = Spring.GetGameSpeed()
    paused = isPaused == true
  end
  if paused and not sawPausedAt then
    sawPausedAt = os.clock()
  end
  -- The objectives widget pauses the sortie and then stops. Wait until that
  -- hold has landed, then release it so synced frames can reach the probe.
  if sawPausedAt and not releasedPause and (os.clock() - sawPausedAt) > 1.0 then
    releasedPause = true
    pcall(Spring.SendCommands, "pause 0")
    Spring.Echo("VA_BOOT_PROBE unpause frame=" .. tostring(frame))
  end

  -- Sample while paused too. Spawn happens in GameStart, before the
  -- objectives widget freezes the sim around frame 30.
  local waited = sawPausedAt and (os.clock() - sawPausedAt) > 0.4
  if not sampled and frame >= 1 and (waited or not paused) then
    local playerN, otherN, mobile = companySnapshot()
    if playerN > 0 or (quitAt and os.clock() >= (quitAt - 8)) then
    sampled = true
    if mobile and CMD and CMD.MOVE then
      local x, _, z = Spring.GetUnitPosition(mobile)
      if x and Spring.GiveOrder then
        local tx, tz = x + 220, z + 60
        local y = (Spring.GetGroundHeight and Spring.GetGroundHeight(tx, tz)) or 0
        pcall(Spring.SelectUnitArray, { mobile })
        pcall(Spring.GiveOrder, CMD.MOVE, { tx, y, tz }, 0)
        orderedUnit = mobile
      end
    end
    Spring.Echo("VA_BOOT_PROBE unsynced units=" .. tostring(playerN)
      .. " others=" .. tostring(otherN)
      .. " order=" .. tostring(queueLen(orderedUnit))
      .. " frame=" .. tostring(frame))
    end
  elseif orderedUnit and sampled then
    local n = queueLen(orderedUnit)
    if n > 0 then
      Spring.Echo("VA_BOOT_PROBE unsynced order=" .. tostring(n) .. " frame=" .. tostring(frame))
      orderedUnit = nil
    end
  end

  if not quitAt then
    quitAt = os.clock() + 45
  end
  if os.clock() >= quitAt then
    armed = false
    Spring.Echo("VA_BOOT_PROBE wallclock quit frame=" .. tostring(Spring.GetGameFrame() or 0))
    pcall(Spring.SendCommands, "quitforce")
  end
end
