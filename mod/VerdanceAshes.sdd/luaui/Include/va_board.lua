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

-- A zone's cells, as drawn. Three shapes from the same cell set:
--   cells  row runs: one world rect per horizontal run of cells (a muster is ~1000 cells, ~40 runs)
--   lines  the outline merged into long segments (solid borders)
--   edges  the outline cell edge by cell edge (dashed borders skip every other one; the pad's
--          ground ring samples the terrain at each)
-- plus the centroid, bounds and cell count, which are the same as cell by cell.
local function expandCells(z, mapX, mapZ)
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
    local out, edges = {}, {}
    local hseg, vseg = {}, {}  -- boundary line -> list of unit segment starts (merged below)
    local function seg(t, line, at) local l = t[line]; if not l then l = {}; t[line] = l end; l[#l + 1] = at end
    local sx, sz, n = 0, 0, 0
    local bx1, bz1, bx2, bz2 = math.huge, math.huge, -math.huge, -math.huge
    for row = 0, rows - 1 do
      local runStart = nil
      for col = 0, cols do
        local idx = row * cols + col
        local inside = col < cols and set[idx]
        if inside then
          if not runStart then runStart = col end
          local x1, z1 = col * cw, row * ch
          local x2, z2 = x1 + cw, z1 + ch
          sx, sz, n = sx + x1 + cw * 0.5, sz + z1 + ch * 0.5, n + 1
          if x1 < bx1 then bx1 = x1 end
          if z1 < bz1 then bz1 = z1 end
          if x2 > bx2 then bx2 = x2 end
          if z2 > bz2 then bz2 = z2 end
          if not (row > 0 and set[idx - cols]) then edges[#edges + 1] = { x1, z1, x2, z1 }; seg(hseg, row, col) end
          if not (row < rows - 1 and set[idx + cols]) then edges[#edges + 1] = { x1, z2, x2, z2 }; seg(hseg, row + 1, col) end
          if not (col > 0 and set[idx - 1]) then edges[#edges + 1] = { x1, z1, x1, z2 }; seg(vseg, col, row) end
          if not (col < cols - 1 and set[idx + 1]) then edges[#edges + 1] = { x2, z1, x2, z2 }; seg(vseg, col + 1, row) end
        elseif runStart then
          out[#out + 1] = { runStart * cw, row * ch, col * cw, (row + 1) * ch }
          runStart = nil
        end
      end
    end
    -- merge unit segments on each boundary line into long ones
    local lines = {}
    local function merge(t, horizontal)
      for line, list in pairs(t) do
        table.sort(list)
        local a, b = list[1], list[1] + 1
        for i = 2, #list + 1 do
          local v = list[i]
          if v == b then b = b + 1
          else
            if horizontal then lines[#lines + 1] = { a * cw, line * ch, b * cw, line * ch }
            else lines[#lines + 1] = { line * cw, a * ch, line * cw, b * ch } end
            if v then a, b = v, v + 1 end
          end
        end
      end
    end
    merge(hseg, true); merge(vseg, false)
    return out, edges, lines, n, (n > 0) and sx / n or 0, (n > 0) and sz / n or 0, bx1, bz1, bx2, bz2
  end
  local b = z.bounds or {}
  local x1, z1, x2, z2 = normToMap(b.xMin, mapX), normToMap(b.zMin, mapZ), normToMap(b.xMax, mapX), normToMap(b.zMax, mapZ)
  local edges = { { x1, z1, x2, z1 }, { x1, z2, x2, z2 }, { x1, z1, x1, z2 }, { x2, z1, x2, z2 } }
  return { { x1, z1, x2, z2 } }, edges, edges, 1, (x1 + x2) * 0.5, (z1 + z2) * 0.5, x1, z1, x2, z2
end

function Board.new()
  local self = setmetatable({}, Board)
  self.zones, self.byId = {}, {}
  self.mapX, self.mapZ = Game.mapSizeX or 1, Game.mapSizeZ or 1
  self:reload()
  return self
end

function Board:reload()
  self:dropCaches()
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
      local cells, edges, lines, k, cx, cz, x1, z1, x2, z2 = expandCells(z, self.mapX, self.mapZ)
      local a = z.anchor or {}
      local rec = {
        id = id, label = tostring(z.label or id), cells = cells, edges = edges, lines = lines,
        cx = cx, cz = cz,
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
  -- every zone we own is an extraction point too (game_verdance_exfil.lua va_lift_zones)
  self.liftIds = {}
  for zid in tostring(str("va_lift_zones") or ""):gmatch("[^,]+") do self.liftIds[zid] = true end
  for _, z in ipairs(self.zones) do
    z.role = (z.id == self.objectiveId and "objective") or (z.id == self.padId and "pad") or (self.markIds[z.id] and "mark")
      or (self.liftIds[z.id] and "exit") or nil
  end
  self.roleKey = self:roleKeyNow()
end

function Board:roleKeyNow()
  return tostring(self.objectiveId) .. ":" .. tostring(str("va_pad_zone") or self.padId) .. ":" .. tostring(str("va_lift_zones") or "")
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
--   people           list of { x, z, glyph, col, label } drawn last (or a function returning one)
--   glyphSize        px (default 11); labels (bool) draw pad/objective zone names
--   roleOnly (bool)  paint only role zones' borders (keeps the minimap quiet)
--
-- Cost: the board is drawn every frame on the minimap and on the infil / exfil cards, and a zone is
-- ~1000 cells. Geometry goes out one gl.BeginEnd per zone per layer (row runs, merged outline), and
-- Board:paintCached keeps it in a display list, so a frame is one CallList plus the glyphs.
-- (Painting cell by cell, a hatch and a closure per cell, made ~850 KB of Lua garbage a frame in a
-- fight: BAR's 1.2 GB emergency collection every minute or two.)

local GL_LINES, GL_QUADS = GL and GL.LINES, GL and GL.QUADS

-- Geometry batches: the vertex loops read these upvalues, so a batch allocates no closure.
local B = { proj = nil, list = nil, n = 0, every = 1, step = 4 }

local function vertsRects()       -- B.list = runs: filled quads
  local proj, list = B.proj, B.list
  for i = 1, #list do
    local c = list[i]
    local ax, ay = proj(c[1], c[2])
    local bx, by = proj(c[3], c[4])
    gl.Vertex(ax, ay); gl.Vertex(bx, ay); gl.Vertex(bx, by); gl.Vertex(ax, by)
  end
end

local function vertsSegs()        -- B.list = segments; B.every = 2 skips every other one (dashed)
  local proj, list, every = B.proj, B.list, B.every
  for i = 1, #list, every do
    local e = list[i]
    local ax, ay = proj(e[1], e[2])
    local bx, by = proj(e[3], e[4])
    gl.Vertex(ax, ay); gl.Vertex(bx, by)
  end
end

-- Diagonal hatch over a zone's runs. Lines are x + y = k * step in screen space, so the hatch runs
-- on unbroken from one row of the zone to the next.
local function vertsHatch()
  local proj, list, step = B.proj, B.list, B.step
  for i = 1, #list do
    local c = list[i]
    local ax, ay = proj(c[1], c[2])
    local bx, by = proj(c[3], c[4])
    local x1, y1, x2, y2 = math.min(ax, bx), math.min(ay, by), math.max(ax, bx), math.max(ay, by)
    local w, h = x2 - x1, y2 - y1
    if w > 0 and h > 0 then
      local d = step - ((x1 + y1) % step)
      while d < w + h do
        local px, py = x1 + d, y1
        if px > x2 then px = x2; py = y1 + (d - w) end
        local qx, qy = x1, y1 + d
        if qy > y2 then qy = y2; qx = x1 + (d - h) end
        gl.Vertex(px, py); gl.Vertex(qx, qy)
        d = d + step
      end
    end
  end
end

local function batch(mode, fn, proj, list)
  B.proj, B.list = proj, list
  gl.BeginEnd(mode, fn)
  B.proj, B.list = nil, nil
end

function Board:paint(proj, opts)
  opts = opts or {}
  if not Ash then return end
  local gs = opts.glyphSize or 11
  local seenNow = opts.seenNow
  local sink = self._glyphSink   -- set by paintCached: words are recorded, not drawn
  local function words(str, x, y, size, col, align)
    if sink then
      local i = sink.n + 1
      local e = sink.glyphs[i]
      if not e then e = {}; sink.glyphs[i] = e end
      col = col or Ash.COL.ink
      e[1], e[2], e[3], e[4] = tostring(str or ""), x, y, size or 12
      e[5], e[6], e[7], e[8], e[9] = col[1], col[2], col[3], col[4] or 1, Ash.ALIGN[align or "c"] or "co"
      sink.n = i
    else
      Ash.text(str, x, y, size, col, align)
    end
  end
  local function fillCells(z, col, a)
    Ash.setColorA(col, a)
    batch(GL_QUADS, vertsRects, proj, z.cells)
  end
  local function borderCells(z, col, a, dashed, width)
    Ash.setColorA(col, a)
    gl.LineWidth(width or 1)
    B.every = dashed and 2 or 1
    batch(GL_LINES, vertsSegs, proj, dashed and z.edges or (z.lines or z.edges))
    B.every = 1
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
      Ash.setColorA(Ash.COL.bad, math.min(0.85, 0.15 + 0.6 * seen))
      gl.LineWidth(1)
      B.step = 4
      batch(GL_LINES, vertsHatch, proj, z.cells)
    end
  end

  -- 3. role borders on top (pad steam, objective warn, marks gold)
  for _, z in ipairs(self.zones) do
    if z.role == "pad" then borderCells(z, Ash.COL.steam, 0.7, false, 1.5)
    elseif z.role == "exit" then borderCells(z, Ash.COL.steam, 0.4, false, 1)
    elseif z.role == "objective" then borderCells(z, Ash.COL.warn, 0.75, false, 1.5)
    elseif z.role == "mark" then borderCells(z, Ash.COL.gold, 0.55, false, 1.5) end
  end

  -- 4. glyphs
  local G = Ash.GLYPH
  local function glyph(wx, wz, g, col, size, dy)
    local sx, sy = proj(wx, wz)
    words(g, sx, sy - (size or gs) * 0.4 + (dy or 0), size or gs, col, "c")
  end
  -- "?" where nobody looked (only zones big enough to carry it)
  local unknownCol = Ash.with(Ash.COL.ash, opts.unknownAlpha or 0.55)
  for _, z in ipairs(self.zones) do
    local state = self:believed(z.id)
    if state == "dark" and z.area >= 6 and (not opts.fade or etaOf(z.id) < 0.3) then
      glyph(z.cx, z.cz, G.unknown, unknownCol, gs - 1)
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
      if opts.labels then words("PAD", sx, sy + (gs + 2) * 0.9, gs - 2, Ash.COL.steam, "c") end
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
        words("TO " .. string.upper(tostring(d.farMapName or "")), sx, sy + gs * 0.9, gs - 2, col, "c")
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
        words(done and "DONE" or "OBJECTIVE", sx, sy + (gs + 2) * 0.9, gs - 2, done and Ash.COL.good or Ash.COL.warn, "c")
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
  local people = opts.people
  if type(people) == "function" then people = people() end
  for _, p in ipairs(people or {}) do
    if p.x and p.z then
      glyph(p.x, p.z, p.glyph or G.offPad, p.col or Ash.COL.ink, p.size or gs)
      if opts.labels and p.label then
        local sx, sy = proj(p.x, p.z)
        words(p.label, sx, sy - gs * 1.4, gs - 2, p.col or Ash.COL.ink, "c")
      end
    end
  end
  gl.Color(1, 1, 1, 1)
  gl.LineWidth(1)
end

-- The board through a display list. slot names the surface ("minimap", "infil", ...); k1..k4 are
-- the numbers its projection is made of (minimap size, or the box). The list and the recorded words
-- are rebuilt when the projection changes, the observation tick or the roles move, or every
-- REBUILD_SECONDS (people, marks, the objective); in between a frame replays them and allocates
-- nothing.
local REBUILD_SECONDS = 0.5

function Board:dropCaches()
  for _, c in pairs(self._cache or {}) do
    if c.list and gl and gl.DeleteList then gl.DeleteList(c.list) end
  end
  self._cache = {}
end

function Board:paintCached(slot, k1, k2, k3, k4, proj, opts)
  if not (gl and gl.CreateList and gl.CallList) then return self:paint(proj, opts) end
  local cache = self._cache
  if not cache then cache = {}; self._cache = cache end
  local c = cache[slot]
  if not c then c = { glyphs = {}, n = 0, t = -math.huge }; cache[slot] = c end
  local now = os.clock()
  local tick = num("va_obs_tick", -1)
  if not c.list or c.k1 ~= k1 or c.k2 ~= k2 or c.k3 ~= k3 or c.k4 ~= k4 or c.tick ~= tick
      or c.roleKey ~= self.roleKey or now - c.t >= REBUILD_SECONDS then
    if c.list then gl.DeleteList(c.list) end
    c.n = 0
    self._glyphSink = c
    local ok, err = pcall(function() c.list = gl.CreateList(function() self:paint(proj, opts) end) end)
    self._glyphSink = nil
    if not ok then
      c.list = nil
      if not c.failed then c.failed = true; Spring.Echo("VA_BOARD paint failed: " .. tostring(err)) end
      return
    end
    c.k1, c.k2, c.k3, c.k4, c.tick, c.roleKey, c.t = k1, k2, k3, k4, tick, self.roleKey, now
  end
  if c.list then gl.CallList(c.list) end
  local g = c.glyphs
  for i = 1, c.n do
    local e = g[i]
    gl.Color(e[5], e[6], e[7], e[8])
    gl.Text(e[1], e[2], e[3], e[4], e[9])
  end
  gl.Color(1, 1, 1, 1)
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
