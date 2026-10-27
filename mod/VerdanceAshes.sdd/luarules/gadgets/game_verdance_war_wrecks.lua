-- The standing war's dead: lay the wrecks and heaps the baked war left (mission.warWrecks, written by
-- the mission builder from war_snapshot_v1.json). Metal to reclaim on the approaches, hulls to raise.
function gadget:GetInfo()
  return {
    name = "Verdance War Wrecks",
    desc = "Lays the baked war's wrecks and heaps on a standing-war field",
    author = "Verdance",
    layer = 0,
    enabled = true,
  }
end

if not gadgetHandler:IsSyncedCode() then return end

local LAY_FRAME = 12  -- after the field's units stand (footprint clearance runs on the first frames)
local wrecks

function gadget:Initialize()
  local ok, data = pcall(VFS.Include, "singleplayer/verdance_ashes/generated/va_current.lua")
  wrecks = ok and type(data) == "table" and data.warWrecks or nil
  if type(wrecks) ~= "table" or #wrecks == 0 then
    gadgetHandler:RemoveGadget(self)
  end
end

function gadget:GameFrame(frame)
  if frame < LAY_FRAME then return end
  local mx, mz = Game.mapSizeX, Game.mapSizeZ
  local laid, skipped = 0, 0
  for _, w in ipairs(wrecks) do
    local name, x, z, heading = w[1], tonumber(w[2]) or 0, tonumber(w[3]) or 0, tonumber(w[4]) or 0
    if x <= 1.5 then x = x * mx end
    if z <= 1.5 then z = z * mz end
    if name and FeatureDefNames[name] then
      local ok, fid = pcall(Spring.CreateFeature, name, x, Spring.GetGroundHeight(x, z), z, heading)
      if ok and fid then laid = laid + 1 else skipped = skipped + 1 end
    else
      skipped = skipped + 1
    end
  end
  Spring.Echo("VA_WAR_WRECKS laid=" .. laid .. " skipped=" .. skipped)
  gadgetHandler:RemoveGadget(self)
end
