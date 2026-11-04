if not VFS.Include("LuaRules/Configs/va_active.lua") then return false end -- plain BAR unless the hub launched this
local gadget = gadget

function gadget:GetInfo()
  return {
    name = "Verdance Camp Growth",
    desc = "The camp grew while the company was away: the builders left at base built eco and laser towers near the home pad",
    author = "Verdance",
    date = "2026-11-04",
    license = "GPL v2 or later",
    layer = 9,
    enabled = true,
  }
end

if not gadgetHandler:IsSyncedCode() then
  return
end

-- Whoever is not on the drop is at base, and the constructors left there build (owner call,
-- 2026-11-04). The campaign counts it (verdance.campaign.home.grow_camp_while_away) and the
-- mission carries mission.campGrowth = { count = N } on a Rock Jungle sortie. Here the company
-- finds that many structures already standing around the home pad: two eco for each laser
-- tower, each on ground a builder could build on (TestBuildOrder), outside the pad itself. From
-- then on they are the camp like anything built by hand (the result's footprint keeps them).

local SPAWN_FRAME = 45
local RECIPE = { "legsolar", "legwin", "leglht" }
local R_MIN, R_MAX, R_STEP = 640, 2400, 112   -- elmos from the pad centre; the pad itself stays clear

local want, teamID, px, pz = 0, 0, nil, nil

local function ringSpot(defID, startAngle)
  for r = R_MIN, R_MAX, R_STEP do
    local steps = math.max(8, math.floor(2 * math.pi * r / R_STEP))
    for i = 0, steps - 1 do
      local a = startAngle + i * 2 * math.pi / steps
      local x = px + math.cos(a) * r
      local z = pz + math.sin(a) * r
      if x > 64 and z > 64 and x < Game.mapSizeX - 64 and z < Game.mapSizeZ - 64 then
        local y = Spring.GetGroundHeight(x, z) or 0
        if (Spring.TestBuildOrder(defID, x, y, z, 0) or 0) > 0 then return x, y, z end
      end
    end
  end
  return nil
end

function gadget:Initialize()
  local ok, mission = pcall(VFS.Include, "singleplayer/verdance_ashes/generated/va_current.lua")
  local growth = ok and type(mission) == "table" and mission.campGrowth or nil
  want = math.floor(tonumber(growth and growth.count) or 0)
  if want <= 0 then
    gadgetHandler:RemoveGadget(self)
    return
  end
  teamID = tonumber(mission.balance and mission.balance.playerTeamID) or 0
  local okp, pad = pcall(VFS.Include, "singleplayer/verdance_ashes/generated/va_pad_current.lua")
  if okp and type(pad) == "table" and pad.x and pad.z then
    px, pz = tonumber(pad.x) * Game.mapSizeX, tonumber(pad.z) * Game.mapSizeZ
  end
  if not px then
    Spring.Echo("VA_CAMP_GROWTH no pad to grow around; " .. want .. " structures not placed")
    gadgetHandler:RemoveGadget(self)
  end
end

function gadget:GameFrame(frame)
  if frame < SPAWN_FRAME then return end
  local placed, byDef = 0, {}
  for i = 1, want do
    local name = RECIPE[((i - 1) % #RECIPE) + 1]
    local ud = UnitDefNames[name]
    if ud then
      local x, y, z = ringSpot(ud.id, i * 2.39996)   -- golden-angle starts spread them round the pad
      if x and Spring.CreateUnit(ud.id, x, y, z, 0, teamID) then
        placed = placed + 1
        byDef[name] = (byDef[name] or 0) + 1
      end
    end
  end
  local parts = {}
  for name, n in pairs(byDef) do parts[#parts + 1] = name .. "=" .. n end
  table.sort(parts)
  Spring.Echo("VA_CAMP_GROWTH placed=" .. placed .. "/" .. want .. " " .. table.concat(parts, " "))
  gadgetHandler:RemoveGadget(self)
end
