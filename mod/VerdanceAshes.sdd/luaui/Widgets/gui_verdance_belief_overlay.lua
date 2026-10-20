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
local surprised = {}    -- zoneId -> true once spoken
local toasts = {}       -- { text, until }
local mapMatches = false

local COL = {
  ours   = { 0.49, 1.00, 0.54 },
  theirs = { 1.00, 0.42, 0.36 },
  empty  = { 0.72, 0.72, 0.66 },
  dark   = { 0.35, 0.38, 0.36 },
  ink    = { 0.93, 0.96, 0.93 },
}
do
  local ok, Ash = pcall(VFS.Include, "luaui/Include/va_ash_tokens.lua")
  if not ok or type(Ash) ~= "table" then
    ok, Ash = pcall(VFS.Include, "LuaUI/Include/va_ash_tokens.lua")
  end
  if ok and type(Ash) == "table" and Ash.COL then
    if Ash.COL.good then COL.ours = { Ash.COL.good[1], Ash.COL.good[2], Ash.COL.good[3] } end
    if Ash.COL.warn then COL.theirs = { Ash.COL.warn[1], Ash.COL.warn[2], Ash.COL.warn[3] } end
    if Ash.COL.muted then COL.dark = { Ash.COL.muted[1], Ash.COL.muted[2], Ash.COL.muted[3] } end
    if Ash.COL.ink then COL.ink = { Ash.COL.ink[1], Ash.COL.ink[2], Ash.COL.ink[3] } end
  end
end

-- Yeva (the company's quartermaster of bad news). Plain speech; the numbers stay in the log.
local LINES = {
  ours_found_enemy = {
    "Yeva: %s was supposed to be ours. It is not.",
    "Yeva: We briefed %s as held. Somebody else is holding it.",
  },
  dark_found_enemy = {
    "Yeva: Nobody had looked at %s. There is a column in it.",
    "Yeva: %s was a blank on the map. It is not blank.",
  },
  theirs_found_empty = {
    "Yeva: %s was briefed as theirs. There is nobody there.",
    "Yeva: We came expecting a fight at %s. The ground is empty.",
  },
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

local function say(kind, label, id)
  local pool = LINES[kind]
  if not pool then return end
  local n = 0
  for c in tostring(id):gmatch(".") do n = n + c:byte() end
  local text = string.format(pool[(n % #pool) + 1], label)
  toasts[#toasts + 1] = { text = text, until_ = Spring.GetGameSeconds() + 14 }
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

function widget:DrawInMiniMap(sx, sy)
  if not enabled or not mapMatches or #zoneOrder == 0 then return end
  local mapX, mapZ = Game.mapSizeX or 1, Game.mapSizeZ or 1
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
      gl.Color(col[1], col[2], col[3], alpha)
      for i = 1, #rec.cells do
        local c = rec.cells[i]
        local x1 = (c[1] / mapX) * sx
        local y1 = sy - (c[2] / mapZ) * sy
        local x2 = (c[3] / mapX) * sx
        local y2 = sy - (c[4] / mapZ) * sy
        gl.Rect(math.min(x1, x2), math.min(y1, y2), math.max(x1, x2), math.max(y1, y2))
      end
      if state == "dark" and fade > 0.5 then
        -- a question mark where nobody has looked
        gl.Color(COL.ink[1], COL.ink[2], COL.ink[3], 0.35 * fade)
        gl.Text("?", (rec.cx / mapX) * sx, sy - (rec.cz / mapZ) * sy - 4, 9, "co")
      end
    end
  end
  gl.Color(1, 1, 1, 1)
end

function widget:DrawScreen()
  if not mapMatches then return end
  local vsx, vsy = Spring.GetViewGeometry()
  local now = Spring.GetGameSeconds()
  -- toasts: Yeva, top centre, below whatever the objectives widget owns
  local y = vsy - 150
  local keep = {}
  for i = 1, #toasts do
    local t = toasts[i]
    if t.until_ > now then
      keep[#keep + 1] = t
      local a = math.min(1, (t.until_ - now) / 2)
      gl.Color(0, 0, 0, 0.55 * a)
      local w = gl.GetTextWidth(t.text) * 15 + 24
      gl.Rect(vsx * 0.5 - w * 0.5, y - 8, vsx * 0.5 + w * 0.5, y + 20)
      gl.Color(COL.ink[1], COL.ink[2], COL.ink[3], a)
      gl.Text(t.text, vsx * 0.5, y, 15, "co")
      y = y - 30
    end
  end
  toasts = keep
  if not showPanel or #zoneOrder == 0 then
    gl.Color(1, 1, 1, 1)
    return
  end
  -- panel: belief vs what we have seen, per zone (/vabeliefpanel)
  local px, py = 20, vsy * 0.5 + 10 * #zoneOrder
  gl.Color(0, 0, 0, 0.5)
  gl.Rect(px - 8, py - 16 * (#zoneOrder + 1) - 6, px + 330, py + 18)
  gl.Color(COL.ink[1], COL.ink[2], COL.ink[3], 1)
  gl.Text("BELIEF  (before landing  ->  seen)", px, py, 12, "o")
  for _, id in ipairs(zoneOrder) do
    py = py - 16
    local state, conf = believed(id)
    local eta = observedEta(id)
    local col = COL[state] or COL.dark
    gl.Color(col[1], col[2], col[3], 1)
    local seen = (eta >= 0.6) and "seen" or ((eta > 0.05) and string.format("glimpsed %d%%", math.floor(eta * 100 + 0.5)) or "unseen")
    gl.Text(string.format("%-22s %-7s %3d%%  %s%s", cellsByZone[id].label:sub(1, 22), state, math.floor(conf * 100 + 0.5), seen,
      (enemySeen(id) > 0) and ("  enemy " .. enemySeen(id)) or ""), px, py, 11, "o")
  end
  gl.Color(1, 1, 1, 1)
end
