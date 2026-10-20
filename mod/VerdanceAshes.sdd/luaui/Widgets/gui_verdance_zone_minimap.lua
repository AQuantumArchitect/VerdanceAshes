local widget = widget

function widget:GetInfo()
  return {
    name = "Verdance Zone Minimap",
    desc = "Trace authored campaign zone cells on the minimap (not AABB boxes) + stage route",
    author = "Head Hancho / Luke Spooner",
    date = "2026-07-29",
    license = "GPL v2 or later",
    layer = 8,
    enabled = true,
  }
end

local mission
local zoneMap
-- Role zones only: { zoneId, label, kind, cells={{wx1,wz1,wx2,wz2},...}, cx, cz }
local zones = {}
local enabled = true
local showLabels = true
local showAllFaint = false  -- /vazonesall — faint cell traces for every zone

-- Ash Console map markers (docs/UI_ASH_CONSOLE.md) — match hub deploy board.
-- Kinds: objective (warn) · secondary (gold) · pad (steam — the company lands AND lifts here).
local COL = {
  default = { 0.490, 0.584, 0.518, 0.14 },
  objective = { 0.878, 0.627, 0.376, 0.55 },
  secondary = { 0.831, 0.769, 0.604, 0.40 },
  pad = { 0.494, 0.784, 1.000, 0.55 },
  edge = { 0.933, 0.965, 0.933, 0.85 },
}
do
  local ok, Ash = pcall(VFS.Include, "luaui/Include/va_ash_tokens.lua")
  if not ok or type(Ash) ~= "table" then
    ok, Ash = pcall(VFS.Include, "LuaUI/Include/va_ash_tokens.lua")
  end
  if ok and type(Ash) == "table" and Ash.COL then
    COL.objective = { Ash.COL.warn[1], Ash.COL.warn[2], Ash.COL.warn[3], 0.55 }
    COL.secondary = { Ash.COL.gold[1], Ash.COL.gold[2], Ash.COL.gold[3], 0.40 }
    COL.pad = { Ash.COL.steam[1], Ash.COL.steam[2], Ash.COL.steam[3], 0.55 }
    COL.edge = { Ash.COL.ink[1], Ash.COL.ink[2], Ash.COL.ink[3], 0.85 }
    COL.default = { Ash.COL.muted[1], Ash.COL.muted[2], Ash.COL.muted[3], 0.14 }
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

-- Expand RLE cell runs into world-space cell rects.
-- cells = { {startIndex, length}, ... } over row-major grid.
local function expandCells(z, mapX, mapZ)
  local out = {}
  local grid = z.cellGrid or {}
  local cols = tonumber(grid.cols) or 96
  local rows = tonumber(grid.rows) or 96
  local cw = mapX / cols
  local ch = mapZ / rows
  local runs = z.cells
  if type(runs) == "table" and #runs > 0 and z.shape == "cells" then
    for _, run in ipairs(runs) do
      local start = tonumber(run[1]) or tonumber(run.start) or 0
      local len = tonumber(run[2]) or tonumber(run.length) or 0
      if len > 0 then
        for i = 0, len - 1 do
          local idx = start + i
          local col = idx % cols
          local row = math.floor(idx / cols)
          if row >= 0 and row < rows then
            local x1 = col * cw
            local z1 = row * ch
            out[#out + 1] = { x1, z1, x1 + cw, z1 + ch }
          end
        end
      end
    end
    return out
  end
  -- Legacy rect fallback when no cell runs.
  local b = z.bounds or {}
  out[1] = {
    normToMap(b.xMin, mapX),
    normToMap(b.zMin, mapZ),
    normToMap(b.xMax, mapX),
    normToMap(b.zMax, mapZ),
  }
  return out
end

local function cellCentroid(cells)
  if not cells or #cells == 0 then return 0, 0 end
  local sx, sz, n = 0, 0, 0
  for i = 1, #cells do
    local c = cells[i]
    sx = sx + (c[1] + c[3]) * 0.5
    sz = sz + (c[2] + c[4]) * 0.5
    n = n + 1
  end
  return sx / n, sz / n
end

local function rebuild()
  zones = {}
  zoneMap = readZoneMap()
  mission = readMission()
  if not zoneMap or type(zoneMap.zones) ~= "table" then return end
  local sx = Game.mapSizeX or 1
  local sz = Game.mapSizeZ or 1
  local obj = mission and mission.objective or {}
  local objId = Spring.GetGameRulesParam("va_target_zone") or obj.targetZoneId
  -- The pad: one zone (va_pad_zone from the exfil gadget); deployment zone until it is published.
  local padId = Spring.GetGameRulesParam("va_pad_zone")
  if type(padId) ~= "string" or padId == "" then
    padId = mission and (mission.pad and mission.pad.zoneId or mission.deploymentZoneId)
  end
  local secondarySet = {}
  local secList = obj.secondaryCaptureZoneIds or mission.secondaryCaptureZoneIds or {}
  if type(secList) == "table" then
    for _, sid in ipairs(secList) do secondarySet[tostring(sid)] = true end
  end
  local capList = obj.captureZoneIds or mission.captureZoneIds or {}
  if type(capList) == "table" then
    for _, cid in ipairs(capList) do
      local s = tostring(cid)
      if s ~= tostring(objId or "") then secondarySet[s] = true end
    end
  end

  for _, z in ipairs(zoneMap.zones) do
    local zoneId = tostring(z.zoneId or "?")
    local kind = "default"
    if zoneId == tostring(objId or "") then kind = "objective"
    elseif secondarySet[zoneId] then kind = "secondary"
    elseif zoneId == tostring(padId or "") then kind = "pad"
    end
    -- Lean: only role zones by default (AABB spam was the green-box mess).
    if kind == "default" and not showAllFaint then
      -- skip
    else
      local cells = expandCells(z, sx, sz)
      local cx, cz = cellCentroid(cells)
      local rec = {
        zoneId = zoneId,
        label = tostring(z.label or zoneId),
        kind = kind,
        cells = cells,
        cx = cx,
        cz = cz,
      }
      zones[#zones + 1] = rec
    end
  end

  if WG then
    WG.vaZones = zones
  end
end

local function drawArrow(cx, cy, size, pointingUp, r, g, b, a)
  local s = size or 10
  gl.Color(r, g, b, a or 0.95)
  gl.LineWidth(2.2)
  if pointingUp then
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

local lastRouteKey = ""
function widget:Update()
  local key = tostring(Spring.GetGameRulesParam("va_target_zone")) .. ":" .. tostring(Spring.GetGameRulesParam("va_pad_zone"))
  if key ~= lastRouteKey then lastRouteKey = key; rebuild() end
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
  if cmd == "vazonesall" then
    showAllFaint = not showAllFaint
    rebuild()
    Spring.Echo("VA_ZONES_ALL " .. (showAllFaint and "on" or "off") .. " (cell traces)")
    return true
  end
  if cmd == "vazonesrebuild" then
    rebuild()
    Spring.Echo("VA_ZONES_REBUILT n=" .. tostring(#zones))
    return true
  end
  return false
end

local function drawRouteOnMinimap(sx, sy, mapX, mapZ)
  local route = WG and WG.vaRoute
  if not route or not route.from or not route.to then return end
  local ax = (route.from.x / mapX) * sx
  local ay = sy - (route.from.z / mapZ) * sy
  local bx = (route.to.x / mapX) * sx
  local by = sy - (route.to.z / mapZ) * sy
  local col = COL.objective
  if route.stage == "extract" then col = COL.pad
  elseif route.stage == "marks" then col = COL.secondary
  end
  gl.Color(col[1], col[2], col[3], 0.95)
  gl.LineWidth(2.4)
  gl.Shape(GL.LINES, { { v = { ax, ay } }, { v = { bx, by } } })
  local dx, dy = bx - ax, by - ay
  local len = math.sqrt(dx * dx + dy * dy)
  if len > 6 then
    local ux, uy = dx / len, dy / len
    local px, py = -uy, ux
    local hs = 8
    gl.Shape(GL.LINE_LOOP, {
      { v = { bx, by } },
      { v = { bx - ux * hs - px * hs * 0.55, by - uy * hs - py * hs * 0.55 } },
      { v = { bx - ux * hs + px * hs * 0.55, by - uy * hs + py * hs * 0.55 } },
    })
  end
  gl.LineWidth(1)
end

local function drawZoneCells(z, sx, sy, mapX, mapZ)
  local col = COL[z.kind] or COL.default
  local cells = z.cells or {}
  -- Trace real cells — not the legacy AABB square.
  gl.Color(col[1], col[2], col[3], col[4])
  for i = 1, #cells do
    local c = cells[i]
    local x1 = (c[1] / mapX) * sx
    local y1 = sy - (c[2] / mapZ) * sy
    local x2 = (c[3] / mapX) * sx
    local y2 = sy - (c[4] / mapZ) * sy
    local left, right = math.min(x1, x2), math.max(x1, x2)
    local bottom, top = math.min(y1, y2), math.max(y1, y2)
    gl.Rect(left, bottom, right, top)
  end

end

function widget:DrawInMiniMap(sx, sy)
  if not enabled or #zones == 0 then return end
  local mapX = Game.mapSizeX or 1
  local mapZ = Game.mapSizeZ or 1
  for _, z in ipairs(zones) do
    drawZoneCells(z, sx, sy, mapX, mapZ)
    local cx = (z.cx / mapX) * sx
    local cy = sy - (z.cz / mapZ) * sy
    if z.kind == "pad" then
      -- Down-arrow (land) and up-arrow (lift) share the point: one pad, steam.
      local p = COL.pad
      drawArrow(cx - 6, cy, 9, false, p[1], p[2], p[3], 1.0)
      drawArrow(cx + 6, cy, 9, true, p[1], p[2], p[3], 1.0)
      if showLabels then
        gl.Color(p[1], p[2], p[3], 1)
        gl.Text("PAD", cx, cy + 12, 9, "co")
      end
    elseif z.kind == "objective" then
      gl.Color(1.0, 0.7, 0.25, 1)
      gl.LineWidth(2)
      gl.Shape(GL.LINES, {
        { v = { cx - 10, cy } }, { v = { cx + 10, cy } },
        { v = { cx, cy - 10 } }, { v = { cx, cy + 10 } },
      })
      if showLabels then
        gl.Text("OBJ", cx, cy + 12, 9, "co")
      end
    elseif showLabels and z.kind == "secondary" then
      gl.Color(1, 1, 1, 0.9)
      gl.Text("2ND", cx, cy + 10, 8, "co")
    end
  end
  drawRouteOnMinimap(sx, sy, mapX, mapZ)
  gl.Color(1, 1, 1, 1)
  gl.LineWidth(1)
end
