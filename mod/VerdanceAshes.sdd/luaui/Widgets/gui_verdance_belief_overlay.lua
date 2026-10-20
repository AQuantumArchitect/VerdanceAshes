local widget = widget

function widget:GetInfo()
  return {
    name = "Verdance Belief Overlay",
    desc = "What the company believed about this map before landing, drawn on the minimap until line of sight replaces it; says so when the ground disagrees",
    author = "Verdance",
    date = "2026-10-19",
    license = "GPL v2 or later",
    layer = 9,
    enabled = true,
  }
end

-- Belief, not truth. generated/va_intel_current.lua is the company's own mind about the
-- planned map (tools/intel_lua_v1.py from intent.intel). Each zone is tinted by what we
-- believed (ours / held by someone / empty / nobody looked) with alpha by confidence, and
-- the tint fades as the synced observe gadget reports line of sight (va_obs_<zone>). When
-- what we see contradicts what we believed, Yeva says so once, and the result carries the
-- same contradiction home as surprise.

local intel          -- table from va_intel_current.lua
local mission
local zoneMap
local cellsByZone = {}  -- zoneId -> { cells = {{x1,z1,x2,z2},...}, cx, cz, label }
local zoneOrder = {}
local enabled = true
local showPanel = false
local lastTick = -1
local surprised = {}    -- zoneId -> true once checked to a conclusion
local contradicted = {} -- zoneId -> kind ("ours_found_enemy" | "dark_found_enemy" | "theirs_found_empty"); never fades
local toasts = {}       -- { text, until_ } — Yeva lines; drawn in the shared voice stack
local mapMatches = false

-- Every colour from Ash.COL (empty → muted). Belief fill, exposure hatch, glyphs.
local COL = {
  ours   = { 0.490, 1.000, 0.541 },
  theirs = { 0.878, 0.627, 0.376 },
  empty  = { 0.490, 0.584, 0.518 },
  dark   = { 0.490, 0.584, 0.518 },
  ink    = { 0.933, 0.965, 0.933 },
  warn   = { 0.878, 0.627, 0.376 },
  muted  = { 0.490, 0.584, 0.518 },
  bad    = { 1.000, 0.490, 0.490 },
}
local Ash
do
  local ok, mod = pcall(VFS.Include, "luaui/Include/va_ash_tokens.lua")
  if not ok or type(mod) ~= "table" then
    ok, mod = pcall(VFS.Include, "LuaUI/Include/va_ash_tokens.lua")
  end
  Ash = (ok and type(mod) == "table") and mod or nil
  if Ash and Ash.COL then
    local A = Ash.COL
    COL.ours = A.good; COL.theirs = A.warn; COL.empty = A.muted; COL.dark = A.muted
    COL.ink = A.ink; COL.warn = A.warn; COL.muted = A.muted; COL.bad = A.bad
  end
end

-- Voice stack (one chrome for everyone). gui_verdance_objectives.lua owns the stack when it is
-- loaded: it draws its Ketha bark at vsy-150 and our Yeva toasts above it (WG.vaYevaToasts),
-- 46px apart, so the two never overlap. If no owner has claimed the stack we draw it here.
local VOICE_BASE_Y = 150
local VOICE_STEP = 46

-- Yeva (the company's quartermaster of bad news). Plain speech; the numbers stay in the log.
local LINES = {
  ours_found_enemy = {
    "%s was supposed to be ours. It is not.",
    "We briefed %s as held. Somebody else is holding it.",
  },
  dark_found_enemy = {
    "Nobody had looked at %s. There is a column in it.",
    "%s was a blank on the map. It is not blank.",
  },
  theirs_found_empty = {
    "%s was briefed as theirs. There is nobody there.",
    "We came expecting a fight at %s. The ground is empty.",
  },
}
-- Persistent minimap glyph per contradiction kind (never fades once drawn).
local GLYPH = {
  ours_found_enemy   = { "✗", "warn" },
  dark_found_enemy   = { "✗", "warn" },
  theirs_found_empty = { "○", "muted" },
}

local function readLua(path)
  local ok, data = pcall(VFS.Include, path)
  if ok and type(data) == "table" then return data end
  return nil
end

local function normToMap(v, size)
  v = tonumber(v) or 0
  if v <= 1 then return v * (size or 0) end
  return v
end

local function expandCells(z, mapX, mapZ)
  local out = {}
  local grid = z.cellGrid or {}
  local cols = tonumber(grid.cols) or 96
  local rows = tonumber(grid.rows) or 96
  local cw, ch = mapX / cols, mapZ / rows
  local runs = z.cells
  if type(runs) == "table" and #runs > 0 and z.shape == "cells" then
    for _, run in ipairs(runs) do
      local start = tonumber(run[1]) or tonumber(run.start) or 0
      local len = tonumber(run[2]) or tonumber(run.length) or 0
      for i = 0, len - 1 do
        local idx = start + i
        local col = idx % cols
        local row = math.floor(idx / cols)
        if row >= 0 and row < rows then
          local x1, z1 = col * cw, row * ch
          out[#out + 1] = { x1, z1, x1 + cw, z1 + ch }
        end
      end
    end
    return out
  end
  local b = z.bounds or {}
  out[1] = { normToMap(b.xMin, mapX), normToMap(b.zMin, mapZ), normToMap(b.xMax, mapX), normToMap(b.zMax, mapZ) }
  return out
end

local function rebuild()
  cellsByZone, zoneOrder = {}, {}
  intel = readLua("singleplayer/verdance_ashes/generated/va_intel_current.lua")
  mission = readLua("singleplayer/verdance_ashes/generated/va_current.lua")
  zoneMap = readLua("singleplayer/verdance_ashes/generated/zone_map_current.lua")
  mapMatches = false
  if not intel or type(intel.zones) ~= "table" or not zoneMap or type(zoneMap.zones) ~= "table" then
    Spring.Echo("VA_BELIEF overlay idle (no intel or zone map)")
    return
  end
  local missionMap = tostring((mission and mission.deploymentMapId) or (zoneMap.mapId) or "")
  mapMatches = (tostring(intel.mapId or "") == missionMap) or (intel.mapId == nil)
  if not mapMatches then
    Spring.Echo("VA_BELIEF intel is for " .. tostring(intel.mapId) .. ", mission is " .. missionMap .. "; overlay off")
    return
  end
  local sx, sz = Game.mapSizeX or 1, Game.mapSizeZ or 1
  local n = 0
  for _, z in ipairs(zoneMap.zones) do
    local id = tostring(z.zoneId or "")
    if id ~= "" and intel.zones[id] then
      local cells = expandCells(z, sx, sz)
      local cx, cz, k = 0, 0, 0
      for i = 1, #cells do
        local c = cells[i]
        cx = cx + (c[1] + c[3]) * 0.5; cz = cz + (c[2] + c[4]) * 0.5; k = k + 1
      end
      cellsByZone[id] = { cells = cells, cx = (k > 0) and cx / k or 0, cz = (k > 0) and cz / k or 0, label = tostring(z.label or id) }
      zoneOrder[#zoneOrder + 1] = id
      n = n + 1
    end
  end
  Spring.Echo("VA_BELIEF overlay zones=" .. n .. " asOfMinute=" .. tostring(intel.asOfMinute))
end

-- believed state of a zone: "ours" | "theirs" | "empty" | "dark", and a confidence 0..1
local function believed(id)
  local b = intel and intel.zones and intel.zones[id]
  if not b then return "dark", 0 end
  local o, h = b.ours or {}, b.held or {}
  local oc, hc = tonumber(o.c) or 0, tonumber(h.c) or 0
  if (o.state == "dark" or o.v == nil) and (h.state == "dark" or h.v == nil) then
    return "dark", 0
  end
  local ov, hv = tonumber(o.v) or 0.5, tonumber(h.v) or 0.5
  if ov > 0.5 and oc > 0.15 then return "ours", oc end
  if hv > 0.5 and hc > 0.15 then return "theirs", hc end
  if hv <= 0.5 and hc > 0.15 then return "empty", hc end
  return "dark", math.max(oc, hc)
end

local function observedEta(id)
  return tonumber(Spring.GetGameRulesParam("va_obs_" .. id)) or 0
end

local function enemySeen(id)
  return tonumber(Spring.GetGameRulesParam("va_obs_enemy_" .. id)) or 0
end

-- how much of us the enemy currently sees in this zone (observe gadget, 0..1)
local function exposure(id)
  return tonumber(Spring.GetGameRulesParam("va_seen_" .. id)) or 0
end

local function publishToasts()
  if WG then WG.vaYevaToasts = toasts end
end

local function say(kind, label, id)
  local pool = LINES[kind]
  if not pool then return end
  local n = 0
  for c in tostring(id):gmatch(".") do n = n + c:byte() end
  local text = string.format(pool[(n % #pool) + 1], label)
  toasts[#toasts + 1] = { speaker = "Yeva", text = text, until_ = Spring.GetGameSeconds() + 14 }
  publishToasts()
  contradicted[id] = kind
  Spring.Echo("VA_SURPRISE_LIVE zone=" .. id .. " kind=" .. kind)
end

-- The live contradiction check: only once a zone is well seen (eta >= 0.5), once per zone.
local function checkSurprises()
  for _, id in ipairs(zoneOrder) do
    if not surprised[id] then
      local eta = observedEta(id)
      if eta >= 0.5 then
        local state, conf = believed(id)
        local enemies = enemySeen(id)
        local label = cellsByZone[id].label
        if state == "ours" and conf >= 0.3 and enemies >= 3 then
          surprised[id] = true; say("ours_found_enemy", label, id)
        elseif state == "dark" and enemies >= 5 then
          surprised[id] = true; say("dark_found_enemy", label, id)
        elseif state == "theirs" and conf >= 0.4 and eta >= 0.75 and enemies == 0 then
          surprised[id] = true; say("theirs_found_empty", label, id)
        elseif eta >= 0.9 then
          surprised[id] = true   -- fully seen, nothing to say: belief and ground agree
        end
      end
    end
  end
end

function widget:Initialize()
  rebuild()
  publishToasts()
end

function widget:Shutdown()
  if WG then WG.vaYevaToasts = nil end
end

function widget:Update()
  if not mapMatches then return end
  local tick = tonumber(Spring.GetGameRulesParam("va_obs_tick")) or -1
  if tick ~= lastTick then
    lastTick = tick
    checkSurprises()
  end
end

function widget:TextCommand(cmd)
  if cmd == "vabelief" then
    enabled = not enabled
    Spring.Echo("VA_BELIEF overlay " .. (enabled and "on" or "off"))
    return true
  end
  if cmd == "vabeliefpanel" then
    showPanel = not showPanel
    return true
  end
  if cmd == "vabeliefrebuild" then
    rebuild()
    return true
  end
  return false
end

-- Minimap pass order: belief shape (fill / fill+border / border / "?") → exposure hatch
-- (bad diagonal lines, alpha = va_seen_) → "◉" at the loudest zone → contradiction glyphs.
-- Fill and hatch never share an encoding: fill = what we believed, hatch = what they see.
function widget:DrawInMiniMap(sx, sy)
  if not enabled or not mapMatches or #zoneOrder == 0 then return end
  local mapX, mapZ = Game.mapSizeX or 1, Game.mapSizeZ or 1
  local function cellRect(c)
    local x1 = (c[1] / mapX) * sx
    local y1 = sy - (c[2] / mapZ) * sy
    local x2 = (c[3] / mapX) * sx
    local y2 = sy - (c[4] / mapZ) * sy
    return math.min(x1, x2), math.min(y1, y2), math.max(x1, x2), math.max(y1, y2)
  end
  local function outlineCells(rec, col, a)
    gl.Color(col[1], col[2], col[3], a)
    gl.LineWidth(1)
    for i = 1, #rec.cells do
      local x1, y1, x2, y2 = cellRect(rec.cells[i])
      gl.BeginEnd(GL.LINE_LOOP, function()
        gl.Vertex(x1, y1); gl.Vertex(x2, y1); gl.Vertex(x2, y2); gl.Vertex(x1, y2)
      end)
    end
  end

  -- 1. belief tint, shape by state
  for _, id in ipairs(zoneOrder) do
    local rec = cellsByZone[id]
    local state, conf = believed(id)
    local eta = observedEta(id)
    -- line of sight replaces belief: by eta 0.6 the tint is gone and the real map shows through
    local fade = 1 - math.min(1, eta / 0.6)
    local alpha = (0.10 + 0.32 * conf) * fade
    if state == "dark" then alpha = 0.06 * fade end
    if alpha > 0.01 then
      local col = COL[state] or COL.dark
      if state == "ours" or state == "theirs" or state == "dark" then
        gl.Color(col[1], col[2], col[3], alpha)
        for i = 1, #rec.cells do
          local x1, y1, x2, y2 = cellRect(rec.cells[i])
          gl.Rect(x1, y1, x2, y2)
        end
      end
      if state == "theirs" then
        outlineCells(rec, COL.warn, math.min(0.9, alpha * 2.2))
      elseif state == "empty" then
        outlineCells(rec, COL.empty, math.min(0.8, alpha * 2.0))
      end
      if state == "dark" and fade > 0.5 then
        -- a question mark where nobody has looked
        gl.Color(COL.ink[1], COL.ink[2], COL.ink[3], 0.35 * fade)
        gl.Text("?", (rec.cx / mapX) * sx, sy - (rec.cz / mapZ) * sy - 4, 9, "co")
      end
    end
  end

  -- 2. exposure hatch: how much of us the enemy sees here (bad, lines only)
  local loudId, loud = nil, 0
  for _, id in ipairs(zoneOrder) do
    local rec = cellsByZone[id]
    local seen = exposure(id)
    if seen > loud then loud, loudId = seen, id end
    if seen > 0.02 then
      local hcol = { COL.bad[1], COL.bad[2], COL.bad[3], math.min(0.9, seen) }
      for i = 1, #rec.cells do
        local x1, y1, x2, y2 = cellRect(rec.cells[i])
        if Ash and Ash.hatchRect then
          Ash.hatchRect(x1, y1, x2, y2, hcol, 4)
        else
          gl.Color(hcol[1], hcol[2], hcol[3], hcol[4])
          gl.BeginEnd(GL.LINES, function()
            gl.Vertex(x1, y1); gl.Vertex(x2, y2)
          end)
        end
      end
    end
  end
  if loudId and loud >= 0.05 then
    local rec = cellsByZone[loudId]
    gl.Color(COL.bad[1], COL.bad[2], COL.bad[3], 0.95)
    gl.Text("◉", (rec.cx / mapX) * sx, sy - (rec.cz / mapZ) * sy - 5, 11, "co")
  end

  -- 3. contradiction glyphs: once the ground disagreed with the brief, the mark stays
  for id, kind in pairs(contradicted) do
    local rec = cellsByZone[id]
    local g = GLYPH[kind]
    if rec and g then
      local col = COL[g[2]] or COL.warn
      gl.Color(col[1], col[2], col[3], 0.95)
      gl.Text(g[1], (rec.cx / mapX) * sx, sy - (rec.cz / mapZ) * sy - 5, 11, "co")
    end
  end
  gl.Color(1, 1, 1, 1)
  gl.LineWidth(1)
end

-- Draw the voice stack ourselves only when no owner (objectives HUD) has claimed it.
local function drawToastsFallback(vsx, vsy, now)
  local y = vsy - VOICE_BASE_Y
  local shown = 0
  for i = 1, #toasts do
    local t = toasts[i]
    if shown >= 3 then break end
    local a = math.min(1, (t.until_ - now) / 2)
    if Ash and Ash.voiceBlock then
      Ash.voiceBlock(vsx * 0.5, y, math.min(560, vsx * 0.55), t.speaker or "Yeva", t.text, a)
    else
      gl.Color(0, 0, 0, 0.55 * a)
      local w = gl.GetTextWidth(t.text) * 15 + 24
      gl.Rect(vsx * 0.5 - w * 0.5, y - 8, vsx * 0.5 + w * 0.5, y + 20)
      gl.Color(COL.ink[1], COL.ink[2], COL.ink[3], a)
      gl.Text("Yeva: " .. t.text, vsx * 0.5, y, 15, "co")
    end
    y = y + VOICE_STEP
    shown = shown + 1
  end
end

function widget:DrawScreen()
  if not mapMatches then return end
  local vsx, vsy = Spring.GetViewGeometry()
  local now = Spring.GetGameSeconds()
  -- expire toasts; keep the shared table identity so the owner sees the same list
  local n = #toasts
  local w = 0
  for i = 1, n do
    local t = toasts[i]
    toasts[i] = nil
    if t.until_ > now then
      w = w + 1
      toasts[w] = t
    end
  end
  if w > 0 and not (WG and WG.vaVoiceOwner) then
    drawToastsFallback(vsx, vsy, now)
  end
  if not showPanel or #zoneOrder == 0 then
    gl.Color(1, 1, 1, 1)
    return
  end
  -- panel: belief vs what we have seen, per zone (/vabeliefpanel)
  local px, py = 20, vsy * 0.5 + 10 * #zoneOrder
  gl.Color(0, 0, 0, 0.5)
  gl.Rect(px - 8, py - 16 * (#zoneOrder + 1) - 6, px + 360, py + 18)
  gl.Color(COL.ink[1], COL.ink[2], COL.ink[3], 1)
  gl.Text("BELIEF  (before landing  ->  seen  ->  they see us)", px, py, 12, "o")
  for _, id in ipairs(zoneOrder) do
    py = py - 16
    local state, conf = believed(id)
    local eta = observedEta(id)
    local col = COL[state] or COL.dark
    gl.Color(col[1], col[2], col[3], 1)
    local seen = (eta >= 0.6) and "seen" or ((eta > 0.05) and string.format("glimpsed %d%%", math.floor(eta * 100 + 0.5)) or "unseen")
    gl.Text(string.format("%-22s %-7s %3d%%  %s%s  exp %d%%%s", cellsByZone[id].label:sub(1, 22), state, math.floor(conf * 100 + 0.5), seen,
      (enemySeen(id) > 0) and ("  enemy " .. enemySeen(id)) or "", math.floor(exposure(id) * 100 + 0.5),
      contradicted[id] and ("  " .. (GLYPH[contradicted[id]] or { "?" })[1]) or ""), px, py, 11, "o")
  end
  gl.Color(1, 1, 1, 1)
end
