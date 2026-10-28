-- campaign/mission_data.lua: reading the mission seed and the zone map
-- Part of game_verdance_campaign.lua, loaded into that gadget's environment
-- (VFS.Include with the gadget table), so its globals are the gadget's globals.
-- Provides: echoZones, normalizedToElmos, publishHeroRules, readMission, readZoneMap, zoneCount,
-- zoneMapJson
-- Uses: result_heroes, state, telemetry, waterline

function publishHeroRules()
  Spring.SetGameRulesParam("va_heroes_json", heroStatesJson(), { public = true })
end

function readMission()
  local ok, data = pcall(VFS.Include, "singleplayer/verdance_ashes/generated/va_current.lua")
  if ok and type(data) == "table" then return data end
  Spring.Echo("VA_SEED_MISSING generated/va_current.lua did not load; the kernel did not build this sortie")
  return {
    schemaVersion = "0.6",
    campaignId = "verdance_ashes",
    missionId = "va_missing_seed",
    missionNumber = 0,
    pathSignal = "B",
    zone = "Unknown",
    objective = { requiredFrames = 600, description = "Missing mission seed fallback" },
    economy = { metalIncome = 0, energyIncome = 0, buildPower = 0 },
    graph = {},
    reputation = {},
    companions = {}
  }
end

function readZoneMap()
  vaZoneCellIndexCache = nil    -- rebuild the cell index for the new map
  vaZoneAdjacencyCache = nil    -- and the border graph derived from it
  local ok, data = pcall(VFS.Include, "singleplayer/verdance_ashes/generated/zone_map_current.lua")
  if ok and type(data) == "table" then return data end
  return nil
end

function zoneCount()
  if not zoneMap or type(zoneMap.zones) ~= "table" then return 0 end
  return #zoneMap.zones
end

function normalizedToElmos(v, size)
  v = tonumber(v) or 0
  if v <= 1 then return math.floor(v * (size or 0) + 0.5) end
  return math.floor(v + 0.5)
end

function zoneMapJson()
  return table.concat({
    '"mapId":' .. jstr(zoneMap and zoneMap.mapId or ""),
    '"mapName":' .. jstr(zoneMap and zoneMap.mapName or ""),
    '"coordinateSystem":' .. jstr(zoneMap and zoneMap.coordinateSystem or ""),
    '"zoneCount":' .. jnum(zoneCount())
  }, ',')
end

function echoZones()
  if not zoneMap or type(zoneMap.zones) ~= "table" then
    Spring.Echo("VA_ZONES none loaded")
    return
  end
  local sx = Game.mapSizeX or 0
  local sz = Game.mapSizeZ or 0
  local cellIndex = vaZoneCellIndex()
  Spring.Echo("VA_ZONES mapId=" .. tostring(zoneMap.mapId or "unknown") .. " map=" .. tostring(Game.mapName or "unknown") .. " count=" .. tostring(#zoneMap.zones) .. " size=" .. tostring(sx) .. "x" .. tostring(sz)
    .. " cells=" .. tostring(cellIndex and cellIndex.claimed or 0) .. " res=" .. tostring(cellIndex and cellIndex.res or 0))
  for _, z in ipairs(zoneMap.zones) do
    local b = z.bounds or {}
    local x1 = normalizedToElmos(b.xMin, sx)
    local x2 = normalizedToElmos(b.xMax, sx)
    local z1 = normalizedToElmos(b.zMin, sz)
    local z2 = normalizedToElmos(b.zMax, sz)
    Spring.Echo("VA_ZONE " .. tostring(z.zoneId or "?") .. " label=" .. tostring(z.label or "") .. " bounds=" .. x1 .. "," .. z1 .. ".." .. x2 .. "," .. z2)
  end
end
