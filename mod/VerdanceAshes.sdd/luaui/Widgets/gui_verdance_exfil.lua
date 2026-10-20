local widget = widget

function widget:GetInfo()
  return {
    name = "Verdance Exfil",
    desc = "EXTRACT: pause, read the manifest (who goes, what stays, where to, what we learned), confirm or go back",
    author = "Verdance",
    date = "2026-10-20",
    license = "GPL v2 or later",
    layer = 12,
    enabled = true,
  }
end

-- Get what you want to keep onto the pad. Press EXTRACT. The game pauses and shows the
-- manifest the synced exfil gadget built; Enter confirms, Esc goes back. The manifest shows
-- the COMPANY's belief only (what we were briefed, what we looked at); the other minds stay
-- hidden. Confirm sends VA_CMD:extract:<destination>; the sortie ends; the exfil gadget
-- closes the game a few seconds later.

local manifest = nil        -- decoded table while the screen is open
local destIdx = 1
local phase = "field"       -- field | manifest | extracting | over
local overKind = nil
local overAt = 0
local intel = nil           -- company belief about this map (va_intel_current.lua)
local zoneLabel = {}
local buttons = {}          -- {x1,y1,x2,y2,action}

local COL = { ink = { 0.93, 0.96, 0.93 }, gold = { 0.83, 0.77, 0.60 }, good = { 0.49, 1.0, 0.54 }, warn = { 0.88, 0.63, 0.38 }, muted = { 0.49, 0.58, 0.52 }, bad = { 1.0, 0.42, 0.36 } }

-- ---------------------------------------------------------------- tiny json
local function decode(str)
  local pos = 1
  local function ws() pos = str:find("%S", pos) or (#str + 1) end
  local parseValue
  local function parseString()
    pos = pos + 1
    local out = {}
    while pos <= #str do
      local c = str:sub(pos, pos)
      if c == '"' then pos = pos + 1; return table.concat(out) end
      if c == "\\" then
        local n = str:sub(pos + 1, pos + 1)
        if n == "n" then out[#out + 1] = "\n" elseif n == "t" then out[#out + 1] = "\t" elseif n == "u" then
          local hex = str:sub(pos + 2, pos + 5); out[#out + 1] = "?"; pos = pos + 4
        else out[#out + 1] = n end
        pos = pos + 2
      else
        out[#out + 1] = c; pos = pos + 1
      end
    end
    return table.concat(out)
  end
  local function parseNumber()
    local s, e = str:find("^-?%d+%.?%d*[eE]?[-+]?%d*", pos)
    local n = tonumber(str:sub(s, e)); pos = e + 1; return n
  end
  parseValue = function()
    ws()
    local c = str:sub(pos, pos)
    if c == "{" then
      pos = pos + 1; local t = {}
      ws(); if str:sub(pos, pos) == "}" then pos = pos + 1; return t end
      while true do
        ws(); local k = parseString(); ws(); pos = pos + 1 -- ':'
        t[k] = parseValue(); ws()
        local d = str:sub(pos, pos); pos = pos + 1
        if d == "}" then return t end
      end
    elseif c == "[" then
      pos = pos + 1; local t = {}
      ws(); if str:sub(pos, pos) == "]" then pos = pos + 1; return t end
      while true do
        t[#t + 1] = parseValue(); ws()
        local d = str:sub(pos, pos); pos = pos + 1
        if d == "]" then return t end
      end
    elseif c == '"' then return parseString()
    elseif str:sub(pos, pos + 3) == "true" then pos = pos + 4; return true
    elseif str:sub(pos, pos + 4) == "false" then pos = pos + 5; return false
    elseif str:sub(pos, pos + 3) == "null" then pos = pos + 4; return nil
    else return parseNumber() end
  end
  local ok, v = pcall(parseValue)
  if ok then return v end
  return nil
end

-- ---------------------------------------------------------------- belief (company only)
local function readLua(path)
  local ok, data = pcall(VFS.Include, path)
  if ok and type(data) == "table" then return data end
  return nil
end

local function believed(id)
  local b = intel and intel.zones and intel.zones[id]
  if not b then return "nobody looked", 0 end
  local o, h = b.ours or {}, b.held or {}
  local oc, hc = tonumber(o.c) or 0, tonumber(h.c) or 0
  if (o.state == "dark" or o.v == nil) and (h.state == "dark" or h.v == nil) then return "nobody looked", 0 end
  local ov, hv = tonumber(o.v) or 0.5, tonumber(h.v) or 0.5
  if ov > 0.5 and oc > 0.15 then return "ours", oc end
  if hv > 0.5 and hc > 0.15 then return "held", hc end
  if hv <= 0.5 and hc > 0.15 then return "empty", hc end
  return "unsure", math.max(oc, hc)
end

local function loadContext()
  intel = readLua("singleplayer/verdance_ashes/generated/va_intel_current.lua")
  local zm = readLua("singleplayer/verdance_ashes/generated/zone_map_current.lua")
  local mission = readLua("singleplayer/verdance_ashes/generated/va_current.lua")
  zm = zm or (mission and mission.zoneMap)
  if zm and type(zm.zones) == "table" then
    for _, z in ipairs(zm.zones) do zoneLabel[tostring(z.zoneId or "")] = tostring(z.label or z.zoneId or "?") end
  end
end

local function label(zid)
  return zoneLabel[zid] or (intel and intel.zones and intel.zones[zid] and intel.zones[zid].label) or zid
end

-- ---------------------------------------------------------------- flow
local function setPaused(on)
  pcall(Spring.SendCommands, on and "pause 1" or "pause 0")
end

function widget:VerdanceManifest(json)
  local m = decode(json or "")
  if type(m) ~= "table" then
    Spring.Echo("VA_EXFIL_UI bad manifest")
    return
  end
  manifest = m
  destIdx = 1
  phase = "manifest"
  setPaused(true)
  Spring.Echo("VA_EXFIL_UI manifest open going=" .. tostring(#(m.going and m.going.heroes or {})) .. "h staying=" .. tostring(#(m.staying and m.staying.heroes or {})) .. "h")
end

local function confirm()
  if phase ~= "manifest" or not manifest then return end
  local d = (manifest.destinations or {})[destIdx] or { id = "home" }
  phase = "extracting"
  Spring.SendLuaRulesMsg("VA_CMD:extract:" .. tostring(d.id or "home"))
  Spring.Echo("VA_EXFIL_UI confirm dest=" .. tostring(d.id))
  setPaused(false)  -- let the synced side run the one frame it needs
end

local function cancel()
  if phase ~= "manifest" then return end
  phase = "field"
  manifest = nil
  setPaused(false)
  Spring.Echo("VA_EXFIL_UI back to the field")
end

function widget:VerdanceMissionEvent(eventStatus, reason)
  if eventStatus == "sortie_over" then
    phase = "over"
    overKind = tostring(reason or "extracted")
    overAt = Spring.GetGameSeconds()
    if not manifest then
      -- wiped: nothing was shown; show the fact
      manifest = { going = { heroes = {}, unitCount = 0 }, staying = { heroes = {}, unitCount = 0, structureCount = 0 }, pad = {} }
    end
  end
end

function widget:Initialize()
  widgetHandler:RegisterGlobal(widget, "VerdanceManifest", function(json) widget:VerdanceManifest(json) end)
  -- the objectives widget also registers VerdanceMissionEvent; the unsynced exfil gadget calls
  -- whichever is registered last, so we chain: keep a reference to a previous global if any.
  local prev = Script and Script.LuaUI and Script.LuaUI.VerdanceMissionEvent or nil
  widgetHandler:RegisterGlobal(widget, "VerdanceMissionEventExfil", function(e, r) widget:VerdanceMissionEvent(e, r) end)
  loadContext()
end

function widget:Shutdown()
  widgetHandler:DeregisterGlobal(widget, "VerdanceManifest")
  widgetHandler:DeregisterGlobal(widget, "VerdanceMissionEventExfil")
end

function widget:Update()
  if phase == "over" then return end
  -- the mission-event global may be owned by the objectives widget; poll the fact instead
  if (tonumber(Spring.GetGameRulesParam("va_terminal")) or 0) == 1 and phase ~= "over" then
    local kind = tostring(Spring.GetGameRulesParam("va_status") or "extracted")
    widget:VerdanceMissionEvent("sortie_over", kind)
  end
end

-- ---------------------------------------------------------------- input
function widget:KeyPress(key, mods, isRepeat)
  if phase == "manifest" then
    if key == 13 or key == 271 then confirm(); return true end       -- Enter / numpad Enter
    if key == 27 then cancel(); return true end                      -- Esc
    if key == 276 or key == 97 then destIdx = math.max(1, destIdx - 1); return true end  -- left / a
    if key == 275 or key == 100 then destIdx = math.min(#(manifest.destinations or {}), destIdx + 1); return true end -- right / d
    return true
  elseif phase == "extracting" or phase == "over" then
    return true
  end
  return false
end

function widget:MousePress(mx, my, button)
  if phase ~= "manifest" then return phase ~= "field" end
  for _, b in ipairs(buttons) do
    if mx >= b[1] and mx <= b[3] and my >= b[2] and my <= b[4] then
      if b[5] == "confirm" then confirm()
      elseif b[5] == "cancel" then cancel()
      elseif b[5] == "prev" then destIdx = math.max(1, destIdx - 1)
      elseif b[5] == "next" then destIdx = math.min(#(manifest.destinations or {}), destIdx + 1)
      end
      return true
    end
  end
  return true
end

-- ---------------------------------------------------------------- draw
local function text(s, x, y, size, opts, col)
  col = col or COL.ink
  gl.Color(col[1], col[2], col[3], 1)
  gl.Text(tostring(s), x, y, size or 13, opts or "o")
end

local function button(x1, y1, x2, y2, caption, action, primary)
  if primary then gl.Color(0.20, 0.45, 0.26, 0.9) else gl.Color(0.12, 0.16, 0.13, 0.9) end
  gl.Rect(x1, y1, x2, y2)
  gl.Color(COL.gold[1], COL.gold[2], COL.gold[3], 0.6)
  gl.LineWidth(1)
  gl.Shape(GL.LINE_LOOP, { { v = { x1, y1 } }, { v = { x2, y1 } }, { v = { x2, y2 } }, { v = { x1, y2 } } })
  text(caption, (x1 + x2) * 0.5, y1 + (y2 - y1) * 0.5 - 6, 14, "co", COL.ink)
  buttons[#buttons + 1] = { x1, y1, x2, y2, action }
end

local function sortedKeys(t)
  local ks = {}
  for k in pairs(t or {}) do ks[#ks + 1] = k end
  table.sort(ks)
  return ks
end

local function drawManifest()
  buttons = {}
  local vsx, vsy = Spring.GetViewGeometry()
  local m = manifest
  gl.Color(0.02, 0.05, 0.03, 0.88)
  gl.Rect(0, 0, vsx, vsy)
  local W = math.min(1180, vsx - 60)
  local x0 = (vsx - W) * 0.5
  local top = vsy - 70
  local padLabel = (m.pad and m.pad.label) or "the pad"
  text("EXTRACT  —  " .. padLabel, x0, top, 24, "o", COL.gold)
  -- destination
  local dests = m.destinations or { { id = "home", label = "Back to camp" } }
  if destIdx > #dests then destIdx = #dests end
  local d = dests[destIdx] or dests[1]
  local y = top - 40
  text("to:", x0, y, 15, "o", COL.muted)
  button(x0 + 40, y - 6, x0 + 70, y + 18, "<", "prev")
  text((d and d.label or "Back to camp") .. ((d and d.mapId) and ("  ·  " .. tostring(d.mapId):gsub("_", " ")) or ""), x0 + 82, y, 17, "o", COL.ink)
  local w = gl.GetTextWidth((d and d.label or "") .. "        ") * 17 + 110
  button(x0 + w + 2, y - 6, x0 + w + 32, y + 18, ">", "next")
  text(string.format("%d of %d", destIdx, #dests), x0 + w + 44, y, 12, "o", COL.muted)

  -- columns
  local colW = (W - 40) / 3
  local cy = y - 44
  local function column(cx, title, col, lines)
    text(title, cx, cy, 15, "o", col)
    local ly = cy - 22
    for i = 1, math.min(#lines, 18) do
      text(lines[i][1], cx, ly, 12, "o", lines[i][2] or COL.ink)
      ly = ly - 17
    end
    if #lines > 18 then text("… and " .. (#lines - 18) .. " more", cx, ly, 11, "o", COL.muted) end
  end
  -- going
  local g = m.going or {}
  local goingLines = {}
  for _, h in ipairs(g.heroes or {}) do goingLines[#goingLines + 1] = { h.name or h.heroId, COL.good } end
  for _, k in ipairs(sortedKeys(g.units)) do goingLines[#goingLines + 1] = { string.format("%d × %s", g.units[k], k), COL.ink } end
  if (g.unitCount or 0) == 0 and #(g.heroes or {}) == 0 then goingLines[1] = { "nobody is on the pad", COL.bad } end
  if m.tenebrium then goingLines[#goingLines + 1] = { string.format("%s Tenebrium", tostring(m.tenebrium)), COL.gold } end
  column(x0, string.format("GOING  (%d people, %d units)", #(g.heroes or {}), g.unitCount or 0), COL.good, goingLines)
  -- staying
  local s = m.staying or {}
  local stayLines = {}
  for _, h in ipairs(s.heroes or {}) do stayLines[#stayLines + 1] = { (h.name or h.heroId) .. "  — at " .. label(h.zoneId or "?"), COL.bad } end
  for _, zid in ipairs(sortedKeys(s.units)) do stayLines[#stayLines + 1] = { string.format("%d units at %s", s.units[zid], label(zid)), COL.warn } end
  for _, zid in ipairs(sortedKeys(s.structures)) do
    local r = s.structures[zid]
    stayLines[#stayLines + 1] = { string.format("%d structures at %s  → our holding there", r.count or 0, label(zid)), COL.gold }
  end
  if #stayLines == 0 then stayLines[1] = { "nothing left behind", COL.muted } end
  column(x0 + colW + 20, string.format("STAYING  (%d people, %d units, %d structures)", #(s.heroes or {}), s.unitCount or 0, s.structureCount or 0), COL.warn, stayLines)
  -- what we learned (company belief vs what we looked at)
  local seenLines = {}
  local seen = m.seen or {}
  local ids = sortedKeys(seen)
  table.sort(ids, function(a, b) return (seen[a] or 0) > (seen[b] or 0) end)
  for _, zid in ipairs(ids) do
    local eta = tonumber(seen[zid]) or 0
    if eta >= 0.05 then
      local bel, conf = believed(zid)
      local enemies = tonumber(Spring.GetGameRulesParam("va_obs_enemy_" .. zid)) or 0
      local note = ""
      if bel == "ours" and enemies >= 3 then note = "  ✗ not ours" elseif bel == "held" and eta >= 0.75 and enemies == 0 then note = "  ✗ nobody there" elseif bel == "nobody looked" and enemies >= 5 then note = "  ! a column" end
      seenLines[#seenLines + 1] = { string.format("%-18s briefed %s%s · looked %d%%%s", label(zid):sub(1, 18), bel, (conf > 0) and string.format(" %d%%", math.floor(conf * 100 + 0.5)) or "", math.floor(eta * 100 + 0.5), note), note ~= "" and COL.warn or COL.ink }
    end
  end
  if #seenLines == 0 then seenLines[1] = { "we looked at nothing", COL.muted } end
  column(x0 + 2 * (colW + 20), "WHAT WE LEARNED", COL.gold, seenLines)
  -- enemy on the pad
  if (m.enemyOnPad or 0) > 0 then
    text(string.format("%d enemy units are on the pad — this will be a contested extraction", m.enemyOnPad), x0, 118, 13, "o", COL.bad)
  end
  -- buttons
  button(x0, 50, x0 + 300, 92, "CONFIRM EXTRACTION   [Enter]", "confirm", true)
  button(x0 + 320, 50, x0 + 560, 92, "BACK TO THE FIELD   [Esc]", "cancel", false)
  text("Left/right picks where the company goes. Whatever is not on the pad stays on Verdance.", x0, 28, 11, "o", COL.muted)
end

local function drawOver()
  local vsx, vsy = Spring.GetViewGeometry()
  gl.Color(0.02, 0.05, 0.03, 0.92)
  gl.Rect(0, 0, vsx, vsy)
  local m = manifest or {}
  local g, s = m.going or {}, m.staying or {}
  local y = vsy * 0.55
  if overKind == "wiped" then
    text("Nobody came back.", vsx * 0.5, y, 28, "co", COL.bad)
    text("Everything on Verdance is Verdance's now.", vsx * 0.5, y - 34, 15, "co", COL.muted)
  else
    text("The company lifts from " .. tostring((m.pad and m.pad.label) or "the pad") .. ".", vsx * 0.5, y, 28, "co", COL.gold)
    text(string.format("%d people and %d units going.  %d people, %d units and %d structures stay.", #(g.heroes or {}), g.unitCount or 0, #(s.heroes or {}), s.unitCount or 0, s.structureCount or 0), vsx * 0.5, y - 34, 15, "co", COL.ink)
  end
  text("Returning to camp…", vsx * 0.5, y - 70, 13, "co", COL.muted)
end

function widget:DrawScreen()
  if phase == "manifest" then
    drawManifest()
  elseif phase == "extracting" then
    local vsx, vsy = Spring.GetViewGeometry()
    gl.Color(0.02, 0.05, 0.03, 0.6)
    gl.Rect(0, 0, vsx, vsy)
    text("Extracting…", vsx * 0.5, vsy * 0.5, 24, "co", COL.gold)
  elseif phase == "over" then
    drawOver()
  end
  gl.Color(1, 1, 1, 1)
end
