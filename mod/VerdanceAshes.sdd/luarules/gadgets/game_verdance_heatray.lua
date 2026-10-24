if not VFS.Include("LuaRules/Configs/va_active.lua") then return false end -- plain BAR unless the hub launched this
local gadget = gadget

function gadget:GetInfo()
  return {
    name = "Verdance Halberd Heat Ray",
    desc = "Runs Halbard's heat ray on the company's energy bank: damage, reach and burn time rise "
        .. "with how full the bank is, and every pulse draws from it.",
    author = "Verdance",
    date = "2026-10-24",
    license = "GPL v2 or later",
    layer = 4, -- after veterancy (2), whose range it composes with
    enabled = true,
  }
end

if not gadgetHandler:IsSyncedCode() then
  return
end

local okRay, Ray = pcall(VFS.Include, "luarules/gadgets/include/va_heat_ray.lua")
if not okRay or type(Ray) ~= "table" then return end

local spGetTeamResources = Spring.GetTeamResources
local spUseTeamResource = Spring.UseTeamResource
local spGetUnitWeaponState = Spring.GetUnitWeaponState
local spSetUnitWeaponState = Spring.SetUnitWeaponState
local spSetUnitWeaponDamages = Spring.SetUnitWeaponDamages
local spSetUnitMaxRange = Spring.SetUnitMaxRange
local spGetUnitWeaponTarget = Spring.GetUnitWeaponTarget
local spGetUnitRulesParam = Spring.GetUnitRulesParam
local spSetUnitRulesParam = Spring.SetUnitRulesParam

local WEAPON = 1                -- the Halberd has one weapon: the ray
local LEVEL_PERIOD = 10         -- frames between re-reading the bank
local PULSE_PERIOD = 5          -- frames between looking for a fired pulse
local TICK_SECONDS = LEVEL_PERIOD / 30

local rays = {}   -- unitID -> { team, baseDamage, baseRange, lastShot, level }
local burns = {}  -- targetID -> { attacker, untilFrame, perTick }

local rayDefID = nil
do
  local def = UnitDefNames and UnitDefNames[Ray.UNIT]
  rayDefID = def and def.id or nil
end
if not rayDefID then return end

local function weaponBase(unitID)
  local ud = UnitDefs[rayDefID]
  local wd = ud and ud.weapons and ud.weapons[WEAPON] and WeaponDefs[ud.weapons[WEAPON].weaponDef]
  if not wd then return 190, 330 end
  local cp = wd.customParams or {}
  return tonumber(cp.va_ray_damage) or 190, tonumber(wd.range) or 330
end

local function bank(team)
  local energy, storage = spGetTeamResources(team, "energy")
  return tonumber(energy) or 0, tonumber(storage) or 0
end

local function track(unitID)
  if rays[unitID] then return end
  local dmg, range = weaponBase(unitID)
  rays[unitID] = {
    team = Spring.GetUnitTeam(unitID),
    baseDamage = dmg,
    baseRange = range,
    lastShot = spGetUnitWeaponState(unitID, WEAPON, "reloadState"),
    level = Ray.at(0),
  }
end

-- Put the ray's damage and reach where the bank says they should be.
local function retune(unitID, rec)
  local energy, storage = bank(rec.team)
  local lv = Ray.at(Ray.charge(energy, storage))
  rec.level = lv
  if spSetUnitWeaponDamages then
    pcall(spSetUnitWeaponDamages, unitID, WEAPON, "default", rec.baseDamage * lv.damage)
  end
  -- veterancy owns the XP part of the reach; the bank's part rides on top of it
  local vet = tonumber(spGetUnitRulesParam(unitID, "va_vet_range_mult")) or 1
  local r = rec.baseRange * vet * lv.range
  pcall(spSetUnitWeaponState, unitID, WEAPON, "range", r)
  if spSetUnitMaxRange then pcall(spSetUnitMaxRange, unitID, r) end
  spSetUnitRulesParam(unitID, "va_ray_charge", lv.charge, { public = true })
  spSetUnitRulesParam(unitID, "va_ray_damage_mult", lv.damage, { public = true })
  spSetUnitRulesParam(unitID, "va_ray_range_mult", lv.range, { public = true })
  spSetUnitRulesParam(unitID, "va_ray_burn_seconds", lv.burnSeconds, { public = true })
end

-- One pulse has gone: it costs the bank, and it leaves the target burning.
local function pulse(unitID, rec, frame)
  local energy, storage = bank(rec.team)
  local take = math.min(Ray.draw(storage), energy)
  if take > 0 and spUseTeamResource then pcall(spUseTeamResource, rec.team, "energy", take) end
  local lv = rec.level
  local kind, _, target = spGetUnitWeaponTarget(unitID, WEAPON)
  if kind == 1 and target and lv.burnSeconds > 0 then
    local perTick = rec.baseDamage * lv.burnRate * TICK_SECONDS
    local old = burns[target]
    local untilFrame = frame + math.floor(lv.burnSeconds * 30)
    if not old or old.untilFrame < untilFrame or old.perTick < perTick then
      burns[target] = { attacker = unitID, untilFrame = untilFrame, perTick = perTick }
    end
  end
end

local function burn(frame)
  for target, b in pairs(burns) do
    if frame >= b.untilFrame or not Spring.ValidUnitID(target) or Spring.GetUnitIsDead(target) then
      burns[target] = nil
    else
      Spring.AddUnitDamage(target, b.perTick, 0, Spring.ValidUnitID(b.attacker) and b.attacker or -1)
      local x, y, z = Spring.GetUnitPosition(target)
      if x then pcall(Spring.SpawnCEG, "laserhit-small-red", x, y + 12, z) end
    end
  end
end

function gadget:Initialize()
  for _, unitID in ipairs(Spring.GetAllUnits()) do
    if Spring.GetUnitDefID(unitID) == rayDefID then track(unitID) end
  end
end

function gadget:UnitFinished(unitID, unitDefID)
  if unitDefID == rayDefID then track(unitID) end
end

function gadget:UnitCreated(unitID, unitDefID)
  if unitDefID == rayDefID then track(unitID) end
end

function gadget:UnitDestroyed(unitID)
  rays[unitID] = nil
  burns[unitID] = nil
end

function gadget:GameFrame(frame)
  if next(rays) == nil and next(burns) == nil then return end
  if frame % LEVEL_PERIOD == 0 then
    for unitID, rec in pairs(rays) do
      if Spring.ValidUnitID(unitID) then retune(unitID, rec) else rays[unitID] = nil end
    end
    burn(frame)
  end
  if frame % PULSE_PERIOD == 0 then
    for unitID, rec in pairs(rays) do
      local shot = spGetUnitWeaponState(unitID, WEAPON, "reloadState")
      if shot and rec.lastShot and shot > rec.lastShot then pulse(unitID, rec, frame) end
      rec.lastShot = shot
    end
  end
end
