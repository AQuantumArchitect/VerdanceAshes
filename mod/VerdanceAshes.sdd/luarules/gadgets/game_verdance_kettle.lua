if not VFS.Include("LuaRules/Configs/va_active.lua") then return false end -- plain BAR unless the hub launched this
local gadget = gadget

function gadget:GetInfo()
  return {
    name = "Verdance Saint Kettle Missiles",
    desc = "Saint Kettle's long-range anti-air missile is radar-guided and has eyes: the launcher locks "
        .. "onto air blips her company's radars paint, and the missile in flight shows the company what "
        .. "it passes and what it hunts.",
    author = "Verdance",
    date = "2026-10-25",
    license = "GPL v2 or later",
    layer = 5, -- after veterancy (2): her reach rides on whatever it made of the missile's range
    enabled = true,
  }
end

if not gadgetHandler:IsSyncedCode() then
  return
end

local UNIT = "va_kettle"
local WEAPON = 1                -- the long-range missile; weapon 2 is the rapid medium-range spray
local LOCK_PERIOD = 6           -- frames between looking for a blip to lock
local DEFAULT_SIGHT = 320       -- elmos around the missile that the company sees (customparams.va_sight_radius)

local spGetUnitPosition = Spring.GetUnitPosition
local spGetUnitAllyTeam = Spring.GetUnitAllyTeam
local spGetUnitTeam = Spring.GetUnitTeam
local spGetUnitDefID = Spring.GetUnitDefID
local spGetUnitWeaponTarget = Spring.GetUnitWeaponTarget
local spGetUnitsInSphere = Spring.GetUnitsInSphere
local spGetUnitLosState = Spring.GetUnitLosState
local spSetUnitLosState = Spring.SetUnitLosState
local spSetUnitTarget = Spring.SetUnitTarget
local spGetProjectilePosition = Spring.GetProjectilePosition
local spGetUnitMaxRange = Spring.GetUnitMaxRange

local kettleDefID, missileDefID, sight = nil, nil, DEFAULT_SIGHT
do
  local def = UnitDefNames and UnitDefNames[UNIT]
  kettleDefID = def and def.id or nil
  local wd = def and def.weapons and def.weapons[WEAPON] and WeaponDefs[def.weapons[WEAPON].weaponDef]
  if wd then
    missileDefID = wd.id
    local cp = wd.customParams or {}
    sight = tonumber(cp.va_sight_radius) or DEFAULT_SIGHT
  end
end
if not kettleDefID or not missileDefID then return end

local kettles = {}    -- unitID -> allyTeam
local missiles = {}   -- projectileID -> allyTeam of the Kettle that fired it

local function los(unitID, allyTeam)
  local st = spGetUnitLosState(unitID, allyTeam, false)
  if type(st) == "table" then return st.los == true, st.radar == true end
  if type(st) == "number" then return st % 2 == 1, math.floor(st / 2) % 2 == 1 end
  return false, false
end

-- Show the company a unit: in sight, in radar, and typed (so it is read as what it is).
local function reveal(unitID, allyTeam)
  spSetUnitLosState(unitID, allyTeam, { los = true, radar = true, typed = true })
end

local function isAir(defID)
  local ud = defID and UnitDefs[defID]
  return ud ~= nil and (ud.canFly == true or ud.isAirUnit == true)
end

-- The nearest hostile air unit the company has only on radar, inside this Kettle's missile reach.
local function radarBlip(unitID, allyTeam)
  local x, y, z = spGetUnitPosition(unitID)
  if not x then return nil end
  local reach = (spGetUnitMaxRange and spGetUnitMaxRange(unitID)) or 0
  if reach <= 0 then return nil end
  local best, bestD = nil, nil
  for _, other in ipairs(spGetUnitsInSphere(x, y, z, reach) or {}) do
    local oAlly = spGetUnitAllyTeam(other)
    if oAlly ~= nil and oAlly ~= allyTeam and isAir(spGetUnitDefID(other)) then
      local inLos, inRadar = los(other, allyTeam)
      if inRadar and not inLos then
        local ox, oy, oz = spGetUnitPosition(other)
        if ox then
          local d = (ox - x) ^ 2 + (oy - y) ^ 2 + (oz - z) ^ 2
          if not bestD or d < bestD then best, bestD = other, d end
        end
      end
    end
  end
  return best
end

local function lockBlips()
  for unitID, allyTeam in pairs(kettles) do
    local ttype = spGetUnitWeaponTarget(unitID, WEAPON)
    if not ttype or ttype == 0 then          -- the launcher has nothing: it takes the nearest blip
      local blip = radarBlip(unitID, allyTeam)
      if blip then
        -- a locked blip is seen for as long as the missile is on it: the missile's own eyes (below)
        -- keep it, and the lock itself needs it to be something the launcher can aim at
        reveal(blip, allyTeam)
        spSetUnitTarget(unitID, blip, false, false, WEAPON)
      end
    end
  end
end

-- The missile in flight sees: every hostile unit near it is in the company's sight this frame.
local function missileEyes()
  for proID, allyTeam in pairs(missiles) do
    local x, y, z = spGetProjectilePosition(proID)
    if x then
      for _, other in ipairs(spGetUnitsInSphere(x, y, z, sight) or {}) do
        local oAlly = spGetUnitAllyTeam(other)
        if oAlly ~= nil and oAlly ~= allyTeam then reveal(other, allyTeam) end
      end
    end
  end
end

function gadget:Initialize()
  Script.SetWatchWeapon(missileDefID, true)
  for _, unitID in ipairs(Spring.GetAllUnits() or {}) do
    if spGetUnitDefID(unitID) == kettleDefID then kettles[unitID] = spGetUnitAllyTeam(unitID) end
  end
end

function gadget:UnitCreated(unitID, unitDefID)
  if unitDefID == kettleDefID then kettles[unitID] = spGetUnitAllyTeam(unitID) end
end

function gadget:UnitGiven(unitID, unitDefID)
  if unitDefID == kettleDefID then kettles[unitID] = spGetUnitAllyTeam(unitID) end
end

function gadget:UnitDestroyed(unitID)
  kettles[unitID] = nil
end

function gadget:ProjectileCreated(proID, proOwnerID, weaponDefID)
  if weaponDefID == missileDefID and proOwnerID then
    missiles[proID] = spGetUnitAllyTeam(proOwnerID)
  end
end

function gadget:ProjectileDestroyed(proID)
  missiles[proID] = nil
end

function gadget:GameFrame(frame)
  missileEyes()
  if frame % LOCK_PERIOD == 0 then lockBlips() end
end
