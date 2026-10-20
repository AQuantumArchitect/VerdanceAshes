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

local COL = { ink = { 0.93, 0.96, 0.93 }, gold = { 0.83, 0.77, 0.60 }, good = { 0.49, 1.0, 0.54 }, warn = { 0.88, 0.63, 0.38 }, muted = { 0.49, 0.58, 0.52 }, bad = { 1.0, 0.49, 0.49 }, steam = { 0.494, 0.784, 1.0 }, ash = { 0.604, 0.545, 0.447 }, edge = { 0.239, 0.561, 0.333 }, panel = { 0.031, 0.063, 0.047, 0.90 }, bg = { 0.016, 0.035, 0.027 } }

-- Ash Console tokens (docs/UI_ASH_CONSOLE.md): one chrome for every Verdance screen.
local Ash
do
  local ok, mod = pcall(VFS.Include, "luaui/Include/va_ash_tokens.lua")
  if not ok or type(mod) ~= "table" then
    ok, mod = pcall(VFS.Include, "LuaUI/Include/va_ash_tokens.lua")
  end
  Ash = (ok and type(mod) == "table") and mod or nil
  if Ash and Ash.COL then
    for k in pairs(COL) do
      if Ash.COL[k] then COL[k] = Ash.COL[k] end
    end
  end
end

-- Input/draw fence: while the manifest owns the screen the objectives HUD steps back
-- (no EXTRACT re-click, no briefing dismiss on Esc). Read by gui_verdance_objectives.lua.
local function setModal(on)
  if WG then WG.vaExfilModal = on and true or false end
end

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
  setModal(true)
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
  setModal(false)
  setPaused(false)
  Spring.Echo("VA_EXFIL_UI back to the field")
end

function widget:VerdanceMissionEvent(eventStatus, reason)
  if eventStatus == "sortie_over" then
    phase = "over"
    setModal(true)
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
  -- the objectives widget owns VerdanceMissionEvent; the unsynced exfil gadget calls this
  -- second global for us, so both widgets hear sortie_over.
  widgetHandler:RegisterGlobal(widget, "VerdanceMissionEventExfil", function(e, r) widget:VerdanceMissionEvent(e, r) end)
  loadContext()
  setModal(false)
end

function widget:Shutdown()
  widgetHandler:DeregisterGlobal(widget, "VerdanceManifest")
  widgetHandler:DeregisterGlobal(widget, "VerdanceMissionEventExfil")
  setModal(false)
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
  gl.Color(col[1], col[2], col[3], col[4] or 1)
  gl.Text(tostring(s), x, y, size or 13, opts or "o")
end

local function scrim(x1, y1, x2, y2, a)
  if Ash and Ash.scrim then Ash.scrim(x1, y1, x2, y2, a); return end
  gl.Color(COL.bg[1], COL.bg[2], COL.bg[3], a or 0.72)
  gl.Rect(x1, y1, x2, y2)
end

local function panel(x1, y1, x2, y2, accent)
  if Ash and Ash.panel then Ash.panel(x1, y1, x2, y2, { accent = accent }); return end
  gl.Color(COL.panel[1], COL.panel[2], COL.panel[3], COL.panel[4] or 0.9)
  gl.Rect(x1, y1, x2, y2)
  if accent then
    gl.Color(accent[1], accent[2], accent[3], 0.85)
    gl.Rect(x1, y1, x1 + 3, y2)
  end
end

-- Action row (CONFIRM = steam focused; BACK = muted). Redundant coding: fill + rail + caption.
local function actionButton(x1, y1, x2, y2, caption, action, fillCol, focused)
  if Ash and Ash.actionRow then
    Ash.actionRow(x1, y1, x2, y2, { fill = fillCol, focused = focused })
  else
    gl.Color(fillCol[1], fillCol[2], fillCol[3], focused and 0.32 or 0.16)
    gl.Rect(x1, y1, x2, y2)
    gl.Color(fillCol[1], fillCol[2], fillCol[3], focused and 0.95 or 0.7)
    gl.Rect(x1, y1, x1 + 4, y2)
  end
  text(caption, (x1 + x2) * 0.5, y1 + (y2 - y1) * 0.5 - 6, 14, "co", focused and COL.ink or COL.muted)
  buttons[#buttons + 1] = { x1, y1, x2, y2, action }
end

-- Small square step button (destination < >).
local function stepButton(x1, y1, x2, y2, caption, action)
  panel(x1, y1, x2, y2, nil)
  text(caption, (x1 + x2) * 0.5, y1 + (y2 - y1) * 0.5 - 6, 13, "co", COL.steam)
  buttons[#buttons + 1] = { x1, y1, x2, y2, action }
end

local function sortedKeys(t)
  local ks = {}
  for k in pairs(t or {}) do ks[#ks + 1] = k end
  table.sort(ks)
  return ks
end

-- One manifest column: Ash.panel, ash kicker, rows { label, col, flag }.
-- flag "bad"  → "[!] " prefix + bad text + bad left border
-- flag "note" → warn left border (the ✗ / ! learned-notes)
local function column(x1, y1, x2, y2, kicker, accent, lines)
  panel(x1, y1, x2, y2, accent)
  local ix = x1 + 12
  local ly = y2 - 18
  text(kicker, ix, ly, 10, "o", COL.ash)
  if Ash and Ash.rule then Ash.rule(ix, ly - 5, x2 - 12, accent, 0.45) end
  ly = ly - 24
  local maxRows = math.max(1, math.floor((ly - y1 - 8) / 17))
  local shown = math.min(#lines, maxRows)
  for i = 1, shown do
    local row = lines[i]
    local label, col, flag = row[1], row[2] or COL.ink, row[3]
    if flag == "bad" then
      label = "[!] " .. label
      col = COL.bad
      gl.Color(COL.bad[1], COL.bad[2], COL.bad[3], 0.85)
      gl.Rect(x1 + 5, ly - 4, x1 + 7, ly + 12)
    elseif flag == "note" then
      gl.Color(COL.warn[1], COL.warn[2], COL.warn[3], 0.85)
      gl.Rect(x1 + 5, ly - 4, x1 + 7, ly + 12)
    end
    text(label, ix, ly, 12, "o", col)
    ly = ly - 17
  end
  if #lines > shown then text("… and " .. (#lines - shown) .. " more", ix, ly, 11, "o", COL.muted) end
end

local function drawManifest()
  buttons = {}
  local vsx, vsy = Spring.GetViewGeometry()
  local m = manifest
  scrim(0, 0, vsx, vsy, 0.78)
  local W = math.min(1180, vsx - 60)
  local x0 = (vsx - W) * 0.5
  local top = vsy - 70
  local padLabel = (m.pad and m.pad.label) or "the pad"
  text("EXTRACT", x0, top, 10, "o", COL.ash)
  text("The company lifts from " .. padLabel, x0, top - 26, 22, "o", COL.gold)

  -- destination
  local dests = m.destinations or { { id = "home", label = "Back to camp" } }
  if destIdx > #dests then destIdx = #dests end
  local d = dests[destIdx] or dests[1]
  local y = top - 58
  text("TO", x0, y, 10, "o", COL.ash)
  stepButton(x0 + 28, y - 7, x0 + 54, y + 17, "<", "prev")
  local destLabel = (d and d.label or "Back to camp") .. ((d and d.mapId) and ("  ·  " .. tostring(d.mapId):gsub("_", " ")) or "")
  text(destLabel, x0 + 66, y, 16, "o", COL.ink)
  local w = gl.GetTextWidth(destLabel) * 16 + 80
  stepButton(x0 + w + 2, y - 7, x0 + w + 28, y + 17, ">", "next")
  text(string.format("%d of %d", destIdx, #dests), x0 + w + 40, y, 11, "o", COL.muted)

  -- the three columns: going (steam) · staying (warn) · learned (gold)
  local gap = 16
  local colW = (W - 2 * gap) / 3
  local colTop = y - 26
  local colBot = vsy * 0.14 + 56
  if colBot > colTop - 120 then colBot = math.max(40, colTop - 120) end

  local g = m.going or {}
  local goingLines = {}
  for _, h in ipairs(g.heroes or {}) do goingLines[#goingLines + 1] = { h.name or h.heroId, COL.steam } end
  for _, k in ipairs(sortedKeys(g.units)) do goingLines[#goingLines + 1] = { string.format("%d × %s", g.units[k], k), COL.ink } end
  local padEmpty = (g.unitCount or 0) == 0 and #(g.heroes or {}) == 0
  if padEmpty then goingLines[1] = { "nobody is on the pad", COL.bad, "bad" } end
  if m.tenebrium then goingLines[#goingLines + 1] = { string.format("%s Tenebrium", tostring(m.tenebrium)), COL.gold } end
  if (m.enemyOnPad or 0) > 0 then
    goingLines[#goingLines + 1] = { string.format("%d enemy on the pad — contested lift", m.enemyOnPad), COL.bad, "bad" }
  end
  column(x0, colBot, x0 + colW, colTop,
    string.format("GOING  ·  %d people  ·  %d units", #(g.heroes or {}), g.unitCount or 0), COL.steam, goingLines)

  local s = m.staying or {}
  local stayLines = {}
  for _, h in ipairs(s.heroes or {}) do stayLines[#stayLines + 1] = { (h.name or h.heroId) .. "  — at " .. label(h.zoneId or "?"), COL.bad, "bad" } end
  for _, zid in ipairs(sortedKeys(s.units)) do stayLines[#stayLines + 1] = { string.format("%d units at %s", s.units[zid], label(zid)), COL.warn } end
  for _, zid in ipairs(sortedKeys(s.structures)) do
    local r = s.structures[zid]
    stayLines[#stayLines + 1] = { string.format("%d structures at %s  → holding", r.count or 0, label(zid)), COL.gold }
  end
  if #stayLines == 0 then stayLines[1] = { "nothing left behind", COL.muted } end
  column(x0 + colW + gap, colBot, x0 + 2 * colW + gap, colTop,
    string.format("LEFT IF YOU LIFT  ·  %d people  ·  %d units  ·  %d structures", #(s.heroes or {}), s.unitCount or 0, s.structureCount or 0), COL.warn, stayLines)

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
      seenLines[#seenLines + 1] = {
        string.format("%-16s briefed %s%s · looked %d%%%s", label(zid):sub(1, 16), bel,
          (conf > 0) and string.format(" %d%%", math.floor(conf * 100 + 0.5)) or "", math.floor(eta * 100 + 0.5), note),
        note ~= "" and COL.warn or COL.ink,
        note ~= "" and "note" or nil,
      }
    end
  end
  if #seenLines == 0 then seenLines[1] = { "we looked at nothing", COL.muted } end
  column(x0 + 2 * (colW + gap), colBot, x0 + W, colTop, "WHAT WE LEARNED", COL.gold, seenLines)

  -- buttons: out of BAR's build band (bottom-left), at vsy*0.14
  local by = vsy * 0.14
  actionButton(x0, by, x0 + 300, by + 42, "CONFIRM EXTRACTION   [Enter]", "confirm", COL.steam, true)
  actionButton(x0 + 316, by, x0 + 556, by + 42, "BACK TO THE FIELD   [Esc]", "cancel", COL.muted, false)
  text("Left/right picks where the company goes. Whatever is not on the pad stays on Verdance.", x0, by - 18, 11, "o", COL.muted)
end

local function drawOver()
  local vsx, vsy = Spring.GetViewGeometry()
  scrim(0, 0, vsx, vsy, 0.92)
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
    scrim(0, 0, vsx, vsy, 0.6)
    text("Extracting…", vsx * 0.5, vsy * 0.5, 24, "co", COL.gold)
    if Ash and Ash.progressSweep then
      Ash.progressSweep(vsx * 0.5 - 140, vsy * 0.5 - 22, vsx * 0.5 + 140, vsy * 0.5 - 16, COL.steam, os.clock() * 0.6)
    end
  elseif phase == "over" then
    drawOver()
  end
  gl.Color(1, 1, 1, 1)
end
