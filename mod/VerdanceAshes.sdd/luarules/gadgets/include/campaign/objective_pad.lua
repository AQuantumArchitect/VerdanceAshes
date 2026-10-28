-- campaign/objective_pad.lua: the pad: the one zone the company lands and lifts from
-- Part of game_verdance_campaign.lua, loaded into that gadget's environment
-- (VFS.Include with the gadget table), so its globals are the gadget's globals.
-- Provides: VA_padPoint, placeTargetAndPad
-- Uses: mission_data, objectives, state

local extractionZoneRect = nil

-- Exfil is a pad on the zone anchor, the same point the marker uses.
-- A shrunk bounding-box center can sit in the river while the marker the
-- player flies to is the dry anchor, so the pad scan never sees them.
-- (padRadius lives on the extractLoop table declared at the top of the file.)
extractLoop.applyPad = function(zoneId)
  extractionZoneRect = nil
  if not zoneId then return end
  local sx = Game.mapSizeX or 0
  local sz = Game.mapSizeZ or 0
  local cx, cz
  if zoneMap and type(zoneMap.zones) == "table" then
    for _, z in ipairs(zoneMap.zones) do
      if z.zoneId == zoneId then
        local a = z.anchor
        if type(a) == "table" and tonumber(a.x) and tonumber(a.z) then
          cx = normalizedToElmos(tonumber(a.x), sx)
          cz = normalizedToElmos(tonumber(a.z), sz)
        end
        break
      end
    end
  end
  if not cx then
    local rect = zoneRectFor(zoneId)
    if not rect then return end
    cx = (rect[1] + rect[3]) * 0.5
    cz = (rect[2] + rect[4]) * 0.5
  end
  local r = extractLoop.padRadius
  extractionZoneRect = { cx - r, cz - r, cx + r, cz + r }
  -- va_pad_x/z/r are published by game_verdance_exfil.lua (the pad authority); this is the
  -- same anchor, so readers use padPoint() below.
end

-- The pad point as the HUD sees it; falls back to our own rect while the exfil gadget boots.
function VA_padPoint()
  local px = tonumber((Spring.GetGameRulesParam("va_pad_x"))) or -1
  local pz = tonumber((Spring.GetGameRulesParam("va_pad_z"))) or -1
  if px >= 0 and pz >= 0 then return px, pz end
  if extractionZoneRect then
    return (extractionZoneRect[1] + extractionZoneRect[3]) * 0.5, (extractionZoneRect[2] + extractionZoneRect[4]) * 0.5
  end
  return nil, nil
end

-- The target zone's rectangle, and the one pad the company lands and lifts from. Called by gadget:Initialize.
function placeTargetAndPad()
  local obj = mission.objective or {}
  targetZoneRect = zoneRectFor(obj.targetZoneId)
  -- One pad (pass five): the company lands and lifts from the same point — the deployment
  -- zone's anchor. Deploy beacon, bought kit (infilAnchor) and extraction all read it.
  extractLoop.applyPad(mission.deploymentZoneId or mission.extractionZoneId or obj.extractionZoneId)
end
