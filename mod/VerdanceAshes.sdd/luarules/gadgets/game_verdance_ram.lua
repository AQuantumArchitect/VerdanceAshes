if not VFS.Include("LuaRules/Configs/va_active.lua") then return false end -- plain BAR unless the hub launched this
local gadget = gadget

function gadget:GetInfo()
  return {
    name = "Verdance Ram",
    desc = "Bro's Tzar crushes small enemy units it drives into and rams bigger ones",
    author = "Verdance",
    date = "2026-10-23",
    license = "GPL v2 or later",
    layer = 9,
    enabled = true,
  }
end

if not gadgetHandler:IsSyncedCode() then
  return
end

-- Bro's Tzar (the hero unit tagged va_hero_id = "bro", a Cortex Tzar) is a very heavy tank. When it
-- touches an enemy unit:
--   light units (mass up to CRUSH_MASS, not structures, not commanders) are crushed outright;
--   anything heavier takes ram damage that grows with the Tzar's speed, at most once a second
--   per victim.
-- Only the hero Tzar rams; other Tzars on the field drive as BAR made them.

local CRUSH_MASS = 400            -- Pawns, Grunts, Ticks, scouts, light raiders: under the treads
local RAM_DAMAGE = 900            -- at full speed; scales with how fast the Tzar is moving
local RAM_COOLDOWN = 30           -- frames between rams on the same victim
local RAMMERS = { corgol = true, corgolt4 = true }

local lastRam = {}                -- victimID -> frame
local pending = {}                -- collisions seen this frame, settled in GameFrame (never kill mid-collision)

local function heroTzar(unitID)
  return Spring.GetUnitRulesParam(unitID, "va_hero_id") == "bro"
end

local function crushable(ud)
  if not ud or ud.isBuilding or ud.isImmobile or (ud.speed or 0) <= 0 then return false end
  local cp = ud.customParams or {}
  if cp.iscommander or cp.isdecoycommander then return false end
  return (ud.mass or 0) <= CRUSH_MASS
end

function gadget:Initialize()
  for id, ud in pairs(UnitDefs) do
    if RAMMERS[ud.name] and Script.SetWatchUnit then Script.SetWatchUnit(id, true) end
  end
end

-- Crush or ram: the Tzar may be either side of the collision.
local function hit(tzarID, victimID)
  if not (Spring.ValidUnitID(victimID) and not Spring.GetUnitIsDead(victimID)) then return end
  local tTeam, vTeam = Spring.GetUnitTeam(tzarID), Spring.GetUnitTeam(victimID)
  if not tTeam or not vTeam or Spring.AreTeamsAllied(tTeam, vTeam) then return end
  local ud = UnitDefs[Spring.GetUnitDefID(victimID)]
  if crushable(ud) then
    Spring.DestroyUnit(victimID, false, false, tzarID)
    Spring.Echo("VA_RAM_CRUSH victim=" .. tostring(ud.name))
    return
  end
  local frame = Spring.GetGameFrame()
  if lastRam[victimID] and frame - lastRam[victimID] < RAM_COOLDOWN then return end
  local _, _, _, speed = Spring.GetUnitVelocity(tzarID)
  local tud = UnitDefs[Spring.GetUnitDefID(tzarID)]
  local top = math.max(1, ((tud and tud.speed) or 39) / 30)   -- elmos per frame
  local share = math.min(1, (speed or 0) / top)
  if share < 0.2 then return end                              -- a nudge is not a ram
  lastRam[victimID] = frame
  Spring.AddUnitDamage(victimID, RAM_DAMAGE * share, 0, tzarID, -1)
  Spring.Echo("VA_RAM_HIT victim=" .. tostring(ud and ud.name) .. " damage=" .. tostring(math.floor(RAM_DAMAGE * share)))
end

function gadget:UnitUnitCollision(colliderID, collideeID)
  if heroTzar(colliderID) then pending[#pending + 1] = { colliderID, collideeID }
  elseif heroTzar(collideeID) then pending[#pending + 1] = { collideeID, colliderID } end
  return false
end

function gadget:GameFrame()
  if #pending == 0 then return end
  local now = pending
  pending = {}
  for _, p in ipairs(now) do
    if Spring.ValidUnitID(p[1]) then hit(p[1], p[2]) end
  end
end

function gadget:UnitDestroyed(unitID)
  lastRam[unitID] = nil
end
