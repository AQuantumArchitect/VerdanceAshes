-- The belief board: one model + one painter for every Verdance map surface in BAR
-- (minimap, infil screen, exfil manifest). Encoding is the hub's, token for token:
--   fill colour  = who the COMPANY believes holds the zone (faction palette; edge = ours)
--   fill alpha   = confidence; fades as our own line of sight replaces belief (va_obs_<zone>)
--   border       = solid current · dashed stale · faint muted for "empty" · none for "nobody looked"
--   hatch (bad)  = how much of us THEY currently see (va_seen_<zone>) — never shares the fill
--   glyphs       = △ pad · ◆ objective · ◆/◇ marks (✓ done ✗ failed) · ◉ loudest exposure
--                  ✗/○ where the brief was contradicted · ● ○ ✚ ⚑ people
-- Belief, not truth: nothing here reads an enemy mind. Facts come from rules params.

local Board = {}
Board.__index = Board

local Ash
do
  local ok, mod = pcall(VFS.Include, "luaui/Include/va_ash_tokens.lua")
  if not ok or type(mod) ~= "table" then ok, mod = pcall(VFS.Include, "LuaUI/Include/va_ash_tokens.lua") end
  Ash = (ok and type(mod) == "table") and mod or nil
end

local function readLua(path)
  local ok, data = pcall(VFS.Include, path)
  if ok and type(data) == "table" then return data end
  return nil
end

local function num(name, default)
  local v = Spring.GetGameRulesParam(name)
  return tonumber(v) or default
end

local function str(name)
  local v = Spring.GetGameRulesParam(name)
  if type(v) == "string" and v ~= "" then return v end
  return nil
end

local function normToMap(v, size)
  v = tonumber(v) or 0
  if v <= 1 then return v * (size or 0) end
  return v
end

-- Cells as world rects plus the zone's outline: only the edges with no neighbour in the
-- same zone, so a zone reads as one shape, never as a grid.
local function expandCells(z, mapX, mapZ)
  local out, edges = {}, {}
  local grid = z.cellGrid or {}
  local cols = tonumber(grid.cols) or 96
  local rows = tonumber(grid.rows) or 96
  local cw, ch = mapX / cols, mapZ / rows
  local runs = z.cells
  if type(runs) == "table" and #runs > 0 and z.shape == "cells" then
    local set = {}
    for _, run in ipairs(runs) do
      local start = tonumber(run[1]) or tonumber(run.start) or 0
      local len = tonumber(run[2]) or tonumber(run.length) or 0
      for i = 0, len - 1 do
        local idx = start + i
        local row = math.floor(idx / cols)
        if row >= 0 and row < rows then set[idx] = true end
      end
    end
    for idx in pairs(set) do
      local col = idx % cols
      local row = math.floor(idx / cols)
      local x1, z1 = col * cw, row * ch
      local x2, z2 = x1 + cw, z1 + ch
      out[#out + 1] = { x1, z1, x2, z2 }
      if not (row > 0 and set[idx - cols]) then edges[#edges + 1] = { x1, z1, x2, z1 } end
      if not (row < rows - 1 and set[idx + cols]) then edges[#edges + 1] = { x1, z2, x2, z2 } end
      if not (col > 0 and set[idx - 1]) then edges[#edges + 1] = { x1, z1, x1, z2 } end
      if not (col < cols - 1 and set[idx + 1]) then edges[#edges + 1] = { x2, z1, x2, z2 } end
    end
    return out, edges
  end
  local b = z.bounds or {}
  local x1, z1, x2, z2 = normToMap(b.xMin, mapX), normToMap(b.zMin, mapZ), normToMap(b.xMax, mapX), normToMap(b.zMax, mapZ)
  out[1] = { x1, z1, x2, z2 }
  edges = { { x1, z1, x2, z1 }, { x1, z2, x2, z2 }, { x1, z1, x1, z2 }, { x2, z1, x2, z2 } }
  return out, edges
end

function Board.new()
  local self = setmetatable({}, Board)
  self.zones, self.byId = {}, {}
  self.mapX, self.mapZ = Game.mapSizeX or 1, Game.mapSizeZ or 1
  self:reload()
  return self
end

function Board:reload()
  self.zones, self.byId = {}, {}
  self.mission = readLua("singleplayer/verdance_ashes/generated/va_current.lua")
  self.zoneMap = readLua("singleplayer/verdance_ashes/generated/zone_map_current.lua") or (self.mission and self.mission.zoneMap)
  self.intel = readLua("singleplayer/verdance_ashes/generated/va_intel_current.lua")
  self.padFile = readLua("singleplayer/verdance_ashes/generated/va_pad_current.lua")
  local missionMap = tostring((self.mission and self.mission.deploymentMapId) or (self.zoneMap and self.zoneMap.mapId) or "")
  if self.intel and self.intel.mapId and tostring(self.intel.mapId) ~= missionMap then
    Spring.Echo("VA_BOARD intel is for " .. tostring(self.intel.mapId) .. ", mission is " .. missionMap .. "; belief off")
    self.intel = nil
  end
  if not self.zoneMap or type(self.zoneMap.zones) ~= "table" then
    Spring.Echo("VA_BOARD no zone map")
    return
  end
  for _, z in ipairs(self.zoneMap.zones) do
    local id = tostring(z.zoneId or "")
    if id ~= "" then
      local cells, edges = expandCells(z, self.mapX, self.mapZ)
      local cx, cz, k = 0, 0, 0
      local x1, z1, x2, z2 = math.huge, math.huge, -math.huge, -math.huge
      for i = 1, #cells do
        local c = cells[i]
        cx = cx + (c[1] + c[3]) * 0.5; cz = cz + (c[2] + c[4]) * 0.5; k = k + 1
        if c[1] < x1 then x1 = c[1] end
        if c[2] < z1 then z1 = c[2] end
        if c[3] > x2 then x2 = c[3] end
        if c[4] > z2 then z2 = c[4] end
      end
      local a = z.anchor or {}
      local rec = {
        id = id, label = tostring(z.label or id), cells = cells, edges = edges,
        cx = (k > 0) and cx / k or 0, cz = (k > 0) and cz / k or 0,
        ax = a.x and normToMap(a.x, self.mapX) or nil, az = a.z and normToMap(a.z, self.mapZ) or nil,
        x1 = x1, z1 = z1, x2 = x2, z2 = z2, area = k,
      }
      self.zones[#self.zones + 1] = rec
      self.byId[id] = rec
    end
  end
  -- Small zones draw last so nested zones stay visible on top of the big ones.
  table.sort(self.zones, function(p, q) return p.area > q.area end)
  self:refreshRoles()
  Spring.Echo("VA_BOARD zones=" .. #self.zones .. " intel=" .. tostring(self.intel ~= nil) .. " asOfMinute=" .. tostring(self.intel and self.intel.asOfMinute))
end

-- Roles: the objective is the seed's target zone; the pad is wherever the exfil gadget says it is
-- now (va_pad_zone: it moves onto taken ground), else the seed's. Called whenever the key changes.
function Board:refreshRoles()
  local m = self.mission or {}
  local obj = m.objective or {}
  self.objectiveId = obj.targetZoneId and tostring(obj.targetZoneId) or nil
  self.padId = str("va_pad_zone") or (m.pad and m.pad.zoneId and tostring(m.pad.zoneId)) or (self.padFile and self.padFile.zoneId and tostring(self.padFile.zoneId)) or (m.deploymentZoneId and tostring(m.deploymentZoneId)) or nil
  self.markIds = {}
  local lists = { obj.secondaryCaptureZoneIds, m.secondaryCaptureZoneIds, obj.captureZoneIds, m.captureZoneIds }
  for _, list in ipairs(lists) do
    if type(list) == "table" then
      for _, sid in ipairs(list) do
        if tostring(sid) ~= tostring(self.objectiveId or "") then self.markIds[tostring(sid)] = true end
      end
    end
  end
  for _, z in ipairs(self.zones) do
    z.role = (z.id == self.objectiveId and "objective") or (z.id == self.padId and "pad") or (self.markIds[z.id] and "mark") or nil
  end
  self.roleKey = tostring(self.objectiveId) .. ":" .. tostring(self.padId)
end

function Board:roleKeyNow()
  return tostring(self.objectiveId) .. ":" .. tostring(str("va_pad_zone") or self.padId)
end

-- The pad point: va_pad_x/z/r, then the pad file, then the pad zone's anchor.
function Board:pad()
  local px, pz, pr = num("va_pad_x", -1), num("va_pad_z", -1), num("va_pad_r", 0)
  if px < 0 and self.padFile and self.padFile.x then
    px = normToMap(self.padFile.x, self.mapX); pz = normToMap(self.padFile.z, self.mapZ); pr = tonumber(self.padFile.radius) or 560
  end
  if px < 0 and self.padId and self.byId[self.padId] then
    local z = self.byId[self.padId]
    px, pz = z.ax or z.cx, z.az or z.cz
  end
  if pr <= 0 then pr = 560 end
  if px < 0 then return nil end
  return px, pz, pr
end

function Board:objectivePoint()
  local ox, oz = num("va_objective_x", -1), num("va_objective_z", -1)
  if ox >= 0 then return ox, oz end
  local z = self.objectiveId and self.byId[self.objectiveId]
  if z then return z.ax or z.cx, z.az or z.cz end
  return nil
end

function Board:label(id)
  local z = self.byId[tostring(id or "")]
  if z then return z.label end
  local b = self.intel and self.intel.zones and self.intel.zones[tostring(id or "")]
  if b and b.label then return tostring(b.label) end
  return tostring(id or "?")
end

-- Belief for a zone: state ours|held|empty|dark|unsure, confidence 0..1, faction, stale flag, threat 0..1
function Board:believed(id)
  local b = self.intel and self.intel.zones and self.intel.zones[id]
  if not b then return "dark", 0, nil, false, nil end
  local o, h = b.ours or {}, b.held or {}
  local oc, hc = tonumber(o.c) or 0, tonumber(h.c) or 0
  local threat = b.threat and tonumber(b.threat.v) or nil
  local stale = (o.state == "stale" or h.state == "stale")
  if (o.state == "dark" or o.v == nil) and (h.state == "dark" or h.v == nil) then return "dark", 0, nil, stale, threat end
  local ov, hv = tonumber(o.v) or 0.5, tonumber(h.v) or 0.5
  if ov > 0.5 and oc > 0.15 then return "ours", oc, "ashwalkers", stale, threat end
  if hv > 0.5 and hc > 0.15 then return "held", hc, h.faction, stale, threat end
  if hv <= 0.5 and hc > 0.15 then return "empty", hc, nil, stale, threat end
  return "unsure", math.max(oc, hc), nil, stale, threat
end

function Board:eta(id) return num("va_obs_" .. id, 0) end
function Board:enemySeen(id) return num("va_obs_enemy_" .. id, 0) end
function Board:exposure(id) return num("va_seen_" .. id, 0) end

-- Marks ledger from va_secN_* (shared shape with the sidebar).
function Board:marks()
  local out = {}
  local total = num("va_secondary_total", 0)
  for i = 1, total do
    local lbl = str("va_sec" .. i .. "_label")
    out[#out + 1] = {
      i = i, id = str("va_sec" .. i .. "_id"), kind = str("va_sec" .. i .. "_kind") or "", subtype = str("va_sec" .. i .. "_subtype") or "",
      label = lbl or ("Mark " .. i), req = num("va_sec" .. i .. "_req", 0) == 1, done = num("va_sec" .. i .. "_done", 0) == 1,
      failed = num("va_sec" .. i .. "_failed", 0) == 1, x = num("va_sec" .. i .. "_x", -1), z = num("va_sec" .. i .. "_z", -1),
    }
  end
  return out
end

-- Fill colour for a belief state.
function Board:fillFor(state, faction)
  if state == "ours" then return Ash.COL.edge end
  if state == "held" then return faction and Ash.faction(faction) or Ash.COL.warn end
  if state == "empty" then return Ash.COL.muted end
  return Ash.COL.ash
end

-- ---------------------------------------------------------------- the painter
-- proj(wx, wz) -> sx, sy in whatever space the caller draws in. opts:
--   fade (bool)      line of sight fades belief fill (true on the live minimap, false on snapshots)
--   seenNow (table)  zoneId -> eta to use instead of live rules params (exfil snapshot)
--   marks (table)    Board:marks() result (default: read live)
--   contradicted     zoneId -> "held"|"empty" glyph kind
--   people           list of { x, z, glyph, col, label } drawn last
--   glyphSize        px (default 11); labels (bool) draw pad/objective zone names
--   roleOnly (bool)  paint only role zones' borders (keeps the minimap quiet)
function Board:paint(proj, opts)
  opts = opts or {}
  if not Ash then return end
  local gs = opts.glyphSize or 11
  local seenNow = opts.seenNow
  local function cellRect(c)
    local ax, ay = proj(c[1], c[2])
    local bx, by = proj(c[3], c[4])
    return math.min(ax, bx), math.min(ay, by), math.max(ax, bx), math.max(ay, by)
  end
  local function fillCells(z, col, a)
    Ash.setColor(Ash.with(col, a))
    for i = 1, #z.cells do
      local x1, y1, x2, y2 = cellRect(z.cells[i])
      gl.Rect(x1, y1, x2, y2)
    end
  end
  local function borderCells(z, col, a, dashed, width)
    Ash.setColor(Ash.with(col, a))
    gl.LineWidth(width or 1)
    gl.BeginEnd(GL.LINES, function()
      for i = 1, #z.edges do
        if not dashed or (i % 2 == 1) then
          local e = z.edges[i]
          local ax, ay = proj(e[1], e[2])
          local bx, by = proj(e[3], e[4])
          gl.Vertex(ax, ay); gl.Vertex(bx, by)
        end
      end
    end)
    gl.LineWidth(1)
  end
  local function etaOf(id)
    if seenNow then return tonumber(seenNow[id]) or 0 end
    return self:eta(id)
  end

  -- 1. belief fill (+ a faint border so the zone's shape reads even when the fill is gone)
  for _, z in ipairs(self.zones) do
    local state, conf, faction, stale = self:believed(z.id)
    local fade = 1
    if opts.fade then fade = 1 - math.min(1, etaOf(z.id) / 0.6) end
    local col = self:fillFor(state, faction)
    if state == "ours" or state == "held" then
      local a = (0.10 + 0.34 * conf) * fade
      if a > 0.01 then fillCells(z, col, a) end
      borderCells(z, col, 0.25 + 0.45 * conf * fade, stale)
    elseif state == "empty" then
      borderCells(z, col, 0.18 + 0.3 * conf, stale)
    elseif state == "unsure" then
      borderCells(z, Ash.COL.ash, 0.22, true)
    elseif not opts.roleOnly or z.role then
      -- nobody looked: no fill, a hairline so the shape exists
      borderCells(z, Ash.COL.ash, 0.16, false)
    end
  end

  -- 2. exposure hatch (bad lines, alpha = how much of us they see)
  local loudId, loud = nil, 0
  for _, z in ipairs(self.zones) do
    local seen = self:exposure(z.id)
    if seen > loud then loud, loudId = seen, z.id end
    if seen > 0.02 then
      local hcol = Ash.with(Ash.COL.bad, math.min(0.85, 0.15 + 0.6 * seen))
      for i = 1, #z.cells do
        local x1, y1, x2, y2 = cellRect(z.cells[i])
        Ash.hatchRect(x1, y1, x2, y2, hcol, 4)
      end
    end
  end

  -- 3. role borders on top (pad steam, objective warn, marks gold)
  for _, z in ipairs(self.zones) do
    if z.role == "pad" then borderCells(z, Ash.COL.steam, 0.7, false, 1.5)
    elseif z.role == "objective" then borderCells(z, Ash.COL.warn, 0.75, false, 1.5)
    elseif z.role == "mark" then borderCells(z, Ash.COL.gold, 0.55, false, 1.5) end
  end

  -- 4. glyphs
  local G = Ash.GLYPH
  local function glyph(wx, wz, g, col, size, dy)
    local sx, sy = proj(wx, wz)
    Ash.text(g, sx, sy - (size or gs) * 0.4 + (dy or 0), size or gs, col, "c")
  end
  -- "?" where nobody looked (only zones big enough to carry it)
  for _, z in ipairs(self.zones) do
    local state = self:believed(z.id)
    if state == "dark" and z.area >= 6 and (not opts.fade or etaOf(z.id) < 0.3) then
      glyph(z.cx, z.cz, G.unknown, Ash.with(Ash.COL.ash, opts.unknownAlpha or 0.55), gs - 1)
    end
  end
  -- the pad: ring + △
  do
    local px, pz, pr = self:pad()
    if px then
      local sx, sy = proj(px, pz)
      local ex = proj(px + pr, pz)
      local r = math.abs(ex - sx)
      if r > 3 then Ash.ring(sx, sy, r, Ash.with(Ash.COL.steam, 0.85), 1.5, 36) end
      glyph(px, pz, G.pad, Ash.COL.steam, gs + 2)
      if opts.labels then Ash.text("PAD", sx, sy + (gs + 2) * 0.9, gs - 2, Ash.COL.steam, "c") end
    end
  end
  -- doors: the way to another map. ■ held (the road is open), □ not held.
  for _, d in ipairs((self.mission and self.mission.doors) or {}) do
    local z = self.byId[tostring(d.zoneId or "")]
    if z then
      local wx, wz = z.ax or z.cx, z.az or z.cz
      local col = d.held and Ash.COL.warn or Ash.with(Ash.COL.warn, 0.7)
      glyph(wx, wz, d.held and G.doorHeld or G.doorShut, col, gs)
      if opts.labels then
        local sx, sy = proj(wx, wz)
        Ash.text("TO " .. string.upper(tostring(d.farMapName or "")), sx, sy + gs * 0.9, gs - 2, col, "c")
      end
    end
  end
  -- the objective ◆ (good once complete)
  do
    local ox, oz = self:objectivePoint()
    if ox then
      local done = num("va_objective_complete", 0) == 1
      glyph(ox, oz, G.objective, done and Ash.COL.good or Ash.COL.warn, gs + 2)
      if opts.labels then
        local sx, sy = proj(ox, oz)
        Ash.text(done and "DONE" or "OBJECTIVE", sx, sy + (gs + 2) * 0.9, gs - 2, done and Ash.COL.good or Ash.COL.warn, "c")
      end
    end
  end
  -- marks ◆ required / ◇ optional / ✓ / ✗
  for _, mk in ipairs(opts.marks or self:marks()) do
    if mk.x and mk.x >= 0 then
      local g, col
      if mk.failed then g, col = G.failed, Ash.COL.bad
      elseif mk.done then g, col = G.done, Ash.COL.good
      elseif mk.req then g, col = G.markReq, Ash.COL.gold
      else g, col = G.markOpt, Ash.COL.gold end
      glyph(mk.x, mk.z, g, col, gs)
    end
  end
  -- ◉ where they see us loudest
  if loudId and loud >= 0.05 then
    local z = self.byId[loudId]
    if z then glyph(z.cx, z.cz, G.exposed, Ash.with(Ash.COL.bad, 0.95), gs + 1, -gs * 0.5) end
  end
  -- contradictions: the brief was wrong here (never fades)
  for id, kind in pairs(opts.contradicted or {}) do
    local z = self.byId[id]
    if z then
      if kind == "empty" then glyph(z.cx, z.cz, G.contradictedEmpty, Ash.COL.muted, gs + 1, gs * 0.5)
      else glyph(z.cx, z.cz, G.contradictedHeld, Ash.COL.warn, gs + 1, gs * 0.5) end
    end
  end
  -- people
  for _, p in ipairs(opts.people or {}) do
    if p.x and p.z then
      glyph(p.x, p.z, p.glyph or G.offPad, p.col or Ash.COL.ink, p.size or gs)
      if opts.labels and p.label then
        local sx, sy = proj(p.x, p.z)
        Ash.text(p.label, sx, sy - gs * 1.4, gs - 2, p.col or Ash.COL.ink, "c")
      end
    end
  end
  gl.Color(1, 1, 1, 1)
  gl.LineWidth(1)
end

-- Project the whole map into a screen rect, preserving aspect. Returns proj, and the rect used.
function Board:fitProj(x1, y1, x2, y2)
  local w, h = x2 - x1, y2 - y1
  local aspect = self.mapX / self.mapZ
  local bw, bh = w, w / aspect
  if bh > h then bh = h; bw = h * aspect end
  local ox = x1 + (w - bw) * 0.5
  local oy = y1 + (h - bh) * 0.5
  local mapX, mapZ = self.mapX, self.mapZ
  local function proj(wx, wz)
    return ox + (wx / mapX) * bw, oy + bh - (wz / mapZ) * bh
  end
  return proj, { ox, oy, ox + bw, oy + bh }
end

-- Minimap projection (DrawInMiniMap space: sx,sy = minimap size, V flipped).
function Board:minimapProj(sx, sy)
  local mapX, mapZ = self.mapX, self.mapZ
  return function(wx, wz)
    return (wx / mapX) * sx, sy - (wz / mapZ) * sy
  end
end

-- Plain-speech belief sentence for a zone (infil / exfil copy; numbers stay quiet).
function Board:sentence(id)
  local state, conf, faction, stale = self:believed(id)
  local name = self:label(id)
  local pct = math.floor(conf * 100 + 0.5)
  local tail = stale and " — old word" or ""
  if state == "ours" then return string.format("%s is ours, we think (%d%%)%s", name, pct, tail) end
  if state == "held" then
    local who = faction and (tostring(faction):sub(1, 1):upper() .. tostring(faction):sub(2)) or "Somebody"
    return string.format("%s holds %s, we think (%d%%)%s", who, name, pct, tail)
  end
  if state == "empty" then return string.format("%s should be empty (%d%%)%s", name, pct, tail) end
  if state == "unsure" then return string.format("%s — nobody is sure", name) end
  return string.format("%s — nobody has looked", name)
end

return Board
