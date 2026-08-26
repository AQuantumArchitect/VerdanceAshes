local widget = widget

function widget:GetInfo()
  return {
    name = "Verdance Zone Minimap",
    desc = "Draw authored campaign zones on the minimap with clear enfil/exfil arrows",
    author = "Head Hancho / Luke Spooner",
    date = "2026-07-29",
    license = "GPL v2 or later",
    layer = 8,
    enabled = true,
  }
end

local mission
local zoneMap
local zones = {}  -- { zoneId, label, x1,z1,x2,z2, kind }
local enabled = true
local showLabels = true

-- Ash Console map markers (docs/UI_ASH_CONSOLE.md) — match hub deploy board.
local COL = {
  default = { 0.490, 0.584, 0.518, 0.22 },   -- muted
  objective = { 0.878, 0.627, 0.376, 0.65 }, -- warn
  secondary = { 0.831, 0.769, 0.604, 0.45 }, -- gold
  extract = { 0.494, 0.784, 1.000, 0.65 },   -- steam
  deploy = { 0.490, 1.000, 0.541, 0.65 },    -- good
  edge = { 0.933, 0.965, 0.933, 0.85 },      -- ink
}
do
  local ok, Ash = pcall(VFS.Include, "luaui/Widgets/include/va_ash_tokens.lua")
  if not ok or type(Ash) ~= "table" then
    ok, Ash = pcall(VFS.Include, "LuaUI/Widgets/include/va_ash_tokens.lua")
  end
  if ok and type(Ash) == "table" and Ash.COL then
    COL.objective = { Ash.COL.warn[1], Ash.COL.warn[2], Ash.COL.warn[3], 0.65 }
    COL.secondary = { Ash.COL.gold[1], Ash.COL.gold[2], Ash.COL.gold[3], 0.45 }
    COL.extract = { Ash.COL.steam[1], Ash.COL.steam[2], Ash.COL.steam[3], 0.65 }
    COL.deploy = { Ash.COL.good[1], Ash.COL.good[2], Ash.COL.good[3], 0.65 }
    COL.edge = { Ash.COL.ink[1], Ash.COL.ink[2], Ash.COL.ink[3], 0.85 }
    COL.default = { Ash.COL.muted[1], Ash.COL.muted[2], Ash.COL.muted[3], 0.22 }
  end
end

local function readMission()
  local ok, data = pcall(VFS.Include, "singleplayer/verdance_ashes/generated/va_current.lua")
  if ok and type(data) == "table" then return data end
  return nil
end

local function readZoneMap()
  local ok, data = pcall(VFS.Include, "singleplayer/verdance_ashes/generated/zone_map_current.lua")
  if ok and type(data) == "table" then return data end
  return nil
end

local function normToMap(v, size)
  v = tonumber(v) or 0
  if v <= 1 then return v * (size or 0) end
  return v
end

local function rebuild()
  zones = {}
  zoneMap = readZoneMap()
  mission = readMission()
  if not zoneMap or type(zoneMap.zones) ~= "table" then return end
  local sx = Game.mapSizeX or 1
  local sz = Game.mapSizeZ or 1
  local obj = mission and mission.objective or {}
  local objId = obj.targetZoneId
  local extId = mission and (mission.extractionZoneId or obj.extractionZoneId)
  local depId = mission and mission.deploymentZoneId
  local secondarySet = {}
  local secList = obj.secondaryCaptureZoneIds or mission.secondaryCaptureZoneIds or {}
  if type(secList) == "table" then
    for _, sid in ipairs(secList) do
      secondarySet[tostring(sid)] = true
    end
  end
  local capList = obj.captureZoneIds or mission.captureZoneIds or {}
  if type(capList) == "table" then
    for _, cid in ipairs(capList) do
      local s = tostring(cid)
      if s ~= tostring(objId or "") then
        secondarySet[s] = true
      end
    end
  end
  for _, z in ipairs(zoneMap.zones) do
    local b = z.bounds or {}
    local rec = {
      zoneId = tostring(z.zoneId or "?"),
      label = tostring(z.label or z.zoneId or "?"),
      x1 = normToMap(b.xMin, sx),
      z1 = normToMap(b.zMin, sz),
      x2 = normToMap(b.xMax, sx),
      z2 = normToMap(b.zMax, sz),
      kind = "default",
    }
    if rec.zoneId == tostring(objId or "") then rec.kind = "objective"
    elseif secondarySet[rec.zoneId] then rec.kind = "secondary"
    elseif rec.zoneId == tostring(depId or "") then rec.kind = "deploy"
    elseif rec.zoneId == tostring(extId or "") then rec.kind = "extract"
    end
    -- If deploy and extract share a zone, prefer deploy tint until obj done
    if rec.zoneId == tostring(depId or "") and rec.zoneId == tostring(extId or "") then
      rec.kind = "deploy"
      rec.alsoExtract = true
    end
    zones[#zones + 1] = rec
  end
end

local function drawArrow(cx, cy, size, pointingUp, r, g, b, a)
  -- Minimap Y increases up; "up" = toward map north if we inverted z already.
  local s = size or 10
  gl.Color(r, g, b, a or 0.95)
  gl.LineWidth(2.2)
  if pointingUp then
    -- tip up
    gl.Shape(GL.LINE_LOOP, {
      { v = { cx, cy + s } },
      { v = { cx - s * 0.65, cy - s * 0.35 } },
      { v = { cx + s * 0.65, cy - s * 0.35 } },
    })
    gl.Shape(GL.LINES, {
      { v = { cx, cy - s * 0.85 } },
      { v = { cx, cy + s * 0.15 } },
    })
  else
    -- tip down (into map / land)
    gl.Shape(GL.LINE_LOOP, {
      { v = { cx, cy - s } },
      { v = { cx - s * 0.65, cy + s * 0.35 } },
      { v = { cx + s * 0.65, cy + s * 0.35 } },
    })
    gl.Shape(GL.LINES, {
      { v = { cx, cy + s * 0.85 } },
      { v = { cx, cy - s * 0.15 } },
    })
  end
  gl.LineWidth(1)
end

function widget:Initialize()
  rebuild()
end

function widget:TextCommand(cmd)
  if cmd == "vazones" then
    enabled = not enabled
    Spring.Echo("VA_ZONES_MINIMAP " .. (enabled and "on" or "off"))
    return true
  end
  if cmd == "vazoneslabels" then
    showLabels = not showLabels
    Spring.Echo("VA_ZONES_LABELS " .. (showLabels and "on" or "off"))
    return true
  end
  return false
end

function widget:DrawInMiniMap(sx, sy)
  if not enabled or #zones == 0 then return end
  local mapX = Game.mapSizeX or 1
  local mapZ = Game.mapSizeZ or 1
  for _, z in ipairs(zones) do
    local col = COL[z.kind] or COL.default
    local x1 = (z.x1 / mapX) * sx
    local y1 = sy - (z.z1 / mapZ) * sy
    local x2 = (z.x2 / mapX) * sx
    local y2 = sy - (z.z2 / mapZ) * sy
    local left, right = math.min(x1, x2), math.max(x1, x2)
    local bottom, top = math.min(y1, y2), math.max(y1, y2)
    local cx, cy = (left + right) * 0.5, (bottom + top) * 0.5
    gl.Color(col[1], col[2], col[3], col[4])
    gl.Rect(left, bottom, right, top)
    gl.Color(COL.edge[1], COL.edge[2], COL.edge[3], COL.edge[4])
    gl.LineWidth(z.kind == "default" and 1.0 or 2.0)
    gl.Shape(GL.LINE_LOOP, {
      { v = { left, bottom } },
      { v = { right, bottom } },
      { v = { right, top } },
      { v = { left, top } },
    })
    if z.kind == "deploy" then
      drawArrow(cx, cy, 11, false, 0.35, 1.0, 0.5, 1.0) -- tip down = land
      if showLabels then
        gl.Color(0.6, 1.0, 0.7, 1)
        gl.Text("LAND", cx, cy + 12, 9, "co")
      end
    elseif z.kind == "extract" then
      drawArrow(cx, cy, 11, true, 0.4, 0.85, 1.0, 1.0) -- tip up = extract out
      if showLabels then
        gl.Color(0.5, 0.9, 1.0, 1)
        gl.Text("EXTRACT", cx, cy + 12, 9, "co")
      end
    elseif z.kind == "objective" then
      -- target cross
      gl.Color(1.0, 0.7, 0.25, 1)
      gl.LineWidth(2)
      gl.Shape(GL.LINES, {
        { v = { cx - 10, cy } }, { v = { cx + 10, cy } },
        { v = { cx, cy - 10 } }, { v = { cx, cy + 10 } },
      })
      if showLabels then
        gl.Text("OBJ", cx, cy + 12, 9, "co")
      end
    elseif showLabels and z.kind ~= "default" then
      gl.Color(1, 1, 1, 0.9)
      gl.Text(z.label, cx, cy, 8, "co")
    end
  end
  gl.Color(1, 1, 1, 1)
  gl.LineWidth(1)
end
