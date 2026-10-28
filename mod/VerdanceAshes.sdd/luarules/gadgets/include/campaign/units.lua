-- campaign/units.lua: unit-def helpers and metal spots
-- Part of game_verdance_campaign.lua, loaded into that gadget's environment
-- (VFS.Include with the gadget table), so its globals are the gadget's globals.
-- Provides: canFight, isBuilder, isStructure, metalSpotKey, nearestOpenMetalSpot,
-- stampPadToothIfNeeded, unitDefMetal, unitDefName, unitIsPadTooth
-- Uses: hero_spawn

function unitDefName(defID)
  local ud = UnitDefs[defID]
  return ud and ud.name or tostring(defID or "unknown")
end

function unitDefMetal(defID)
  local ud = UnitDefs[defID]
  return tonumber(ud and ud.metalCost or 0) or 0
end

function isBuilder(defID)
  local ud = UnitDefs[defID]
  return ud and (tonumber(ud.buildSpeed or 0) or 0) > 0
end

function isStructure(defID)
  local ud = UnitDefs[defID]
  return ud and (ud.isBuilding or ud.isFactory or ud.speed == 0)
end

function canFight(defID)
  local ud = UnitDefs[defID]
  if not ud then return false end
  if ud.canAttack then return true end
  return ud.weapons and #ud.weapons > 0
end

-- Territory ownership is DV-only. Pad-tooth heroes (area_control / Warder ring)
-- count fighting metal as defensiveValue even when the chassis is mobile.
local function heroIsAreaControl(heroId)
  heroId = tostring(heroId or "")
  if heroId == "" then return false end
  local tags = HeroTags and HeroTags.HERO_DEFAULTS and HeroTags.HERO_DEFAULTS[heroId]
  if type(tags) == "table" then
    for i = 1, #tags do
      if tags[i] == "area_control" then return true end
    end
  end
  return false
end

function unitIsPadTooth(unitID)
  if not unitID then return false end
  local v = Spring.GetUnitRulesParam(unitID, "va_pad_tooth")
  if v == 1 or v == true or v == "1" then return true end
  local hid = Spring.GetUnitRulesParam(unitID, "va_hero_id")
    or Spring.GetUnitRulesParam(unitID, "va_pack_id")
  if hid and heroIsAreaControl(hid) then return true end
  return false
end

function stampPadToothIfNeeded(unitID, heroIdOrPkg)
  if not unitID or not Spring.ValidUnitID(unitID) then return end
  local hid = tostring(heroIdOrPkg or "")
  if hid == "" then return end
  local id = hid:match("^crew_pack_(.+)$")
    or hid:match("^crew_escort_([^_]+)")
    or hid:match("^crew_mint_(.+)$")
    or hid:match("^crew_([^_]+)$")
    or hid
  if heroIsAreaControl(id) then
    Spring.SetUnitRulesParam(unitID, "va_pad_tooth", 1, { public = true })
  end
end

function metalSpotKey(spot)
  return tostring(math.floor((spot.x or 0) + 0.5)) .. "|" .. tostring(math.floor((spot.z or 0) + 0.5))
end

local function metalSpotHasUnit(spot)
  if not spot or not Spring.GetUnitsInCylinder then return false end
  local units = Spring.GetUnitsInCylinder(spot.x, spot.z, 96)
  return units and #units > 0
end

function nearestOpenMetalSpot(anchorX, anchorZ, claimedMetalSpots)
  local spots = GG and GG["resource_spot_finder"] and GG["resource_spot_finder"].metalSpotsList or nil
  if not spots then return nil end
  local best, bestDist
  for i = 1, #spots do
    local spot = spots[i]
    local key = metalSpotKey(spot)
    if not claimedMetalSpots[key] and not metalSpotHasUnit(spot) then
      local dx, dz = anchorX - spot.x, anchorZ - spot.z
      local dist = dx * dx + dz * dz
      if not bestDist or dist < bestDist then
        best = spot
        bestDist = dist
      end
    end
  end
  return best
end
