if not VFS.Include("LuaRules/Configs/va_active.lua") then return false end -- plain BAR unless the hub launched this
local widget = widget

function widget:GetInfo()
  return {
    name = "Verdance Exfil",
    desc = "EXTRACT: pause, read the manifest on the belief board (who goes, what stays, where to, what we learned), confirm or go back",
    author = "Verdance",
    date = "2026-10-20",
    license = "GPL v2 or later",
    layer = 12,
    enabled = true,
  }
end

-- Get what you want to keep onto the pad. Press EXTRACT. The game pauses and shows the
-- manifest the synced exfil gadget built, drawn on the same board the minimap and the infil
-- card use: ● going at the pad, ○ staying where they stand, ■ structures becoming holdings.
-- Enter confirms, Esc goes back. Company belief only; the other minds stay hidden.

local Ash, J, Board
do
  local ok, mod = pcall(VFS.Include, "luaui/Include/va_ash_tokens.lua")
  if not ok or type(mod) ~= "table" then ok, mod = pcall(VFS.Include, "LuaUI/Include/va_ash_tokens.lua") end
  Ash = (ok and type(mod) == "table") and mod or nil
  ok, mod = pcall(VFS.Include, "luaui/Include/va_json.lua")
  if not ok or type(mod) ~= "table" then ok, mod = pcall(VFS.Include, "LuaUI/Include/va_json.lua") end
  J = (ok and type(mod) == "table") and mod or nil
  ok, mod = pcall(VFS.Include, "luaui/Include/va_board.lua")
  if not ok or type(mod) ~= "table" then ok, mod = pcall(VFS.Include, "LuaUI/Include/va_board.lua") end
  Board = (ok and type(mod) == "table") and mod or nil
end

local manifest = nil
local destIdx = 1
local phase = "field"       -- field | manifest | extracting | over
local overKind = nil
local buttons = {}
local ownBoard = nil
local learned = nil         -- composed once per manifest

local function theBoard()
  if WG and WG.vaBoard then return WG.vaBoard end
  if not ownBoard and Board then ownBoard = Board.new() end
  return ownBoard
end

local function setModal(on) if WG then WG.vaExfilModal = on and true or false end end
local function setPaused(on) pcall(Spring.SendCommands, on and "pause 1" or "pause 0") end
local function num(name, default) return tonumber((Spring.GetGameRulesParam(name))) or default end

local function sortedKeys(t)
  local ks = {}
  for k in pairs(t or {}) do ks[#ks + 1] = k end
  table.sort(ks)
  return ks
end

-- What we learned: per zone we looked at, belief → what the ground showed.
local function composeLearned(m)
  local b = theBoard()
  local rows = {}
  if not b then return rows end
  local seen = m.seen or {}
  local ids = sortedKeys(seen)
  table.sort(ids, function(p, q) return (tonumber(seen[p]) or 0) > (tonumber(seen[q]) or 0) end)
  local contradicted = (WG and WG.vaContradicted) or {}
  for _, zid in ipairs(ids) do
    local eta = tonumber(seen[zid]) or 0
    if eta >= 0.05 then
      local state, conf, faction = b:believed(zid)
      local enemies = b:enemySeen(zid)
      local found = (enemies >= 3) and "held" or ((eta >= 0.6) and "empty" or "glimpsed")
      local note = contradicted[zid]
      rows[#rows + 1] = {
        id = zid, label = b:label(zid), state = state, conf = conf, faction = faction, eta = eta, found = found, note = note,
      }
    end
  end
  return rows
end

function widget:VerdanceManifest(json)
  local m = J and J.decode(json or "") or nil
  if type(m) ~= "table" then Spring.Echo("VA_EXFIL_UI bad manifest"); return end
  manifest = m
  destIdx = 1
  phase = "manifest"
  learned = composeLearned(m)
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
  setPaused(false)
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
    if not manifest then
      manifest = { going = { heroes = {}, unitCount = 0 }, staying = { heroes = {}, unitCount = 0, structureCount = 0, structures = {}, units = {} }, pad = {}, seen = {} }
      learned = composeLearned(manifest)
    end
  end
end

function widget:Initialize()
  -- the infil card may already own the modal flag; never clear it here
end

function widget:Shutdown()
  if phase ~= "field" then setModal(false) end
end

local lastManifestSeq = 0
function widget:Update()
  if phase == "over" then return end
  -- The exfil gadget posts the manifest as rules params; a new seq opens the screen.
  local seq = num("va_manifest_seq", 0)
  if seq > lastManifestSeq then
    lastManifestSeq = seq
    if phase == "field" then widget:VerdanceManifest(Spring.GetGameRulesParam("va_manifest_json")) end
  end
  if num("va_terminal", 0) == 1 then
    widget:VerdanceMissionEvent("sortie_over", tostring(Spring.GetGameRulesParam("va_status") or "extracted"))
  end
end

function widget:KeyPress(key)
  if phase == "manifest" then
    if key == 13 or key == 271 then confirm(); return true end
    if key == 27 then cancel(); return true end
    if key == 276 or key == 97 then destIdx = math.max(1, destIdx - 1); return true end
    if key == 275 or key == 100 then destIdx = math.min(#(manifest.destinations or {}), destIdx + 1); return true end
    return true
  elseif phase == "extracting" or phase == "over" then
    return true
  end
  return false
end

function widget:MousePress(mx, my, button)
  if phase ~= "manifest" then return phase ~= "field" end
  for _, b in ipairs(buttons) do
    if Ash.inRect(mx, my, b) then
      if b.action == "confirm" then confirm()
      elseif b.action == "cancel" then cancel()
      elseif b.action == "dest" then destIdx = b.idx end
      return true
    end
  end
  return true
end

-- ---------------------------------------------------------------- draw
local function text(s, x, y, size, col, align) Ash.text(s, x, y, size, col, align) end

local function column(x1, y1, x2, y2, kicker, accent)
  Ash.panel(x1, y1, x2, y2, { accent = accent })
  text(kicker, x1 + 12, y2 - 18, 10, Ash.COL.ash, "l")
  Ash.rule(x1 + 12, y2 - 23, x2 - 12, accent, 0.45)
  return x1 + 12, y2 - 42, x2 - 12
end

local function rows(x, y, right, bottom, list)
  local shown = 0
  for _, r in ipairs(list) do
    if y < bottom + 10 then break end
    local label, col, flag = r[1], r[2] or Ash.COL.ink, r[3]
    if flag then Ash.rect(x - 7, y - 4, x - 5, y + 12, Ash.with(flag, 0.85)) end
    text(Ash.fit(label, 12, right - x), x, y, 12, col, "l")
    y = y - 17
    shown = shown + 1
  end
  if shown < #list then text("… and " .. (#list - shown) .. " more", x, y, 11, Ash.COL.muted, "l") end
  return y
end

local function drawGoing(m, x1, y1, x2, y2)
  local g = m.going or {}
  local x, y, right = column(x1, y1, x2, y2, "GOING", Ash.COL.steam)
  local list = { { string.format("%d people · %d units", #(g.heroes or {}), g.unitCount or 0), Ash.COL.muted } }
  for _, h in ipairs(g.heroes or {}) do list[#list + 1] = { Ash.GLYPH.onPad .. " " .. tostring(h.name or h.heroId), Ash.COL.steam } end
  for _, k in ipairs(sortedKeys(g.units)) do
    local ud = UnitDefNames and UnitDefNames[k]
    list[#list + 1] = { string.format("%d × %s", g.units[k], (ud and (ud.humanName or ud.name)) or k), Ash.COL.ink }
  end
  if (g.unitCount or 0) == 0 and #(g.heroes or {}) == 0 then list[1] = { Ash.GLYPH.failed .. " nobody is on the pad", Ash.COL.bad, Ash.COL.bad } end
  if m.tenebrium then list[#list + 1] = { string.format("%s Tenebrium", tostring(m.tenebrium)), Ash.COL.tnb } end
  if (m.enemyOnPad or 0) > 0 then list[#list + 1] = { string.format("%s %d enemy on the pad", Ash.GLYPH.exposed, m.enemyOnPad), Ash.COL.bad, Ash.COL.bad } end
  rows(x, y, right, y1, list)
end

local function drawStaying(m, x1, y1, x2, y2)
  local s = m.staying or {}
  local b = theBoard()
  local function lbl(z) return b and b:label(z) or tostring(z) end
  local x, y, right = column(x1, y1, x2, y2, "LEFT IF YOU LIFT", Ash.COL.warn)
  local list = { { string.format("%d people · %d units · %d structures", #(s.heroes or {}), s.unitCount or 0, s.structureCount or 0), Ash.COL.muted } }
  for _, h in ipairs(s.heroes or {}) do list[#list + 1] = { Ash.GLYPH.offPad .. " " .. tostring(h.name or h.heroId) .. "  — at " .. lbl(h.zoneId or "?"), Ash.COL.bad, Ash.COL.bad } end
  for _, zid in ipairs(sortedKeys(s.units)) do list[#list + 1] = { string.format("! %d units at %s", s.units[zid], lbl(zid)), Ash.COL.warn } end
  for _, zid in ipairs(sortedKeys(s.structures)) do
    local r = s.structures[zid]
    list[#list + 1] = { string.format("%s %d structures at %s  → holding", Ash.GLYPH.holding, r.count or 0, lbl(zid)), Ash.COL.gold }
  end
  if #list == 0 then list[1] = { "nothing left behind", Ash.COL.muted } end
  rows(x, y, right, y1, list)
end

local function drawLearned(x1, y1, x2, y2)
  local x, y, right = column(x1, y1, x2, y2, "WHAT WE LEARNED  ·  briefed → seen", Ash.COL.gold)
  local b = theBoard()
  if not learned or #learned == 0 then text("we looked at nothing", x, y, 12, Ash.COL.muted, "l"); return end
  for _, r in ipairs(learned) do
    if y < y1 + 12 then break end
    -- briefed swatch
    local bcol = b and b:fillFor(r.state, r.faction) or Ash.COL.ash
    if r.state == "dark" then text(Ash.GLYPH.unknown, x + 4.5, y, 9, Ash.COL.ash, "c")
    else Ash.swatch(x, y - 1, 9, Ash.with(bcol, 0.3 + 0.7 * r.conf), r.state ~= "empty") end
    text("→", x + 15, y, 10, Ash.COL.muted, "l")
    -- seen swatch
    local scol, filled = Ash.COL.muted, false
    if r.found == "held" then scol, filled = Ash.COL.warn, true elseif r.found == "glimpsed" then scol = Ash.COL.ash end
    Ash.swatch(x + 28, y - 1, 9, Ash.with(scol, 0.9), filled)
    local note = ""
    local col = Ash.COL.ink
    if r.note == "held" then note = "  " .. Ash.GLYPH.contradictedHeld; col = Ash.COL.warn
    elseif r.note == "empty" then note = "  " .. Ash.GLYPH.contradictedEmpty; col = Ash.COL.warn end
    local tail = (r.found == "glimpsed") and string.format("  glimpsed %d%%", math.floor(r.eta * 100 + 0.5)) or ""
    text(Ash.fit(r.label .. tail .. note, 11, right - x - 44), x + 44, y, 11, col, "l")
    y = y - 16
  end
end

local function drawBoardColumn(m, x1, y1, x2, y2)
  local x, y, right = column(x1, y1, x2, y2, "THE BOARD  ·  " .. ((m.pad and m.pad.label) or "the pad"), Ash.COL.steam)
  local b = theBoard()
  local bx1, by1, bx2, by2 = x, y1 + 12, right, y + 10
  Ash.rect(bx1, by1, bx2, by2, Ash.with(Ash.COL.bg, 0.9))
  if not b or #b.zones == 0 then text("no board", (bx1 + bx2) * 0.5, (by1 + by2) * 0.5, 12, Ash.COL.muted, "c"); return end
  local proj, rect = b:fitProj(bx1 + 6, by1 + 6, bx2 - 6, by2 - 6)
  Ash.rect(rect[1], rect[2], rect[3], rect[4], { 0.05, 0.09, 0.07, 1 })
  local people = {}
  local px, pz = b:pad()
  local g, s = m.going or {}, m.staying or {}
  -- going: a ● per person fanned around the pad centre
  local n = #(g.heroes or {})
  for i, h in ipairs(g.heroes or {}) do
    if px then
      local a = (i / math.max(1, n)) * math.pi * 2
      people[#people + 1] = { x = px + math.cos(a) * 180, z = pz + math.sin(a) * 180, glyph = Ash.GLYPH.onPad, col = Ash.COL.steam, size = 11 }
    end
  end
  -- staying people at their zone, structures as ■ at theirs
  for _, h in ipairs(s.heroes or {}) do
    local z = b.byId[tostring(h.zoneId or "")]
    if z then people[#people + 1] = { x = z.cx, z = z.cz, glyph = Ash.GLYPH.offPad, col = Ash.COL.bad, size = 13, label = tostring(h.name or h.heroId) } end
  end
  for _, zid in ipairs(sortedKeys(s.structures)) do
    local z = b.byId[tostring(zid)]
    if z then people[#people + 1] = { x = z.cx, z = z.cz + 90, glyph = Ash.GLYPH.holding, col = Ash.COL.gold, size = 11 } end
  end
  b:paint(proj, { fade = true, seenNow = m.seen, labels = true, glyphSize = 12, contradicted = WG and WG.vaContradicted or nil, people = people })
  Ash.outline(rect[1], rect[2], rect[3], rect[4], Ash.with(Ash.COL.edge, 0.4), 1)
end

local function drawDestinations(m, x0, y, W)
  local dests = m.destinations or { { id = "home", label = "Back to camp" } }
  if destIdx > #dests then destIdx = #dests end
  text("TO", x0, y, 10, Ash.COL.ash, "l")
  local cx = x0 + 28
  for i, d in ipairs(dests) do
    local label = tostring(d.label or d.id)
    if d.mapId and d.kind ~= "camp" then label = label .. "  ·  " .. tostring(d.mapId):gsub("_", " ") end
    local focused = (i == destIdx)
    local w = Ash.textW(label, 12) + 24
    if focused then Ash.actionRow(cx, y - 8, cx + w, y + 18, { fill = Ash.COL.steam, focused = true })
    else Ash.panel(cx, y - 8, cx + w, y + 18, { edgeA = 0.35 }) end
    text(label, cx + 12, y, 12, focused and Ash.COL.ink or Ash.COL.muted, "l")
    buttons[#buttons + 1] = { cx, y - 8, cx + w, y + 18, action = "dest", idx = i }
    cx = cx + w + 8
  end
  text("← →", cx + 6, y, 10, Ash.COL.muted, "l")
end

local function drawManifest()
  buttons = {}
  local vsx, vsy = Spring.GetViewGeometry()
  local m = manifest
  Ash.scrim(0, 0, vsx, vsy, 0.8)
  local W = math.min(1180, vsx - 60)
  local x0 = (vsx - W) * 0.5
  local top = vsy - 56
  text("EXTRACT", x0, top, 10, Ash.COL.ash, "l")
  text("The company lifts from " .. tostring((m.pad and m.pad.label) or "the pad"), x0, top - 26, 22, Ash.COL.gold, "l")
  drawDestinations(m, x0, top - 58, W)
  local colTop = top - 84
  local colBot = vsy * 0.14 + 56
  if colBot > colTop - 140 then colBot = math.max(40, colTop - 140) end
  local gap = 14
  local sideW = W * 0.25
  local midW = W - 2 * sideW - 2 * gap
  -- left: going over staying
  local leftMid = colBot + (colTop - colBot) * 0.5
  pcall(drawGoing, m, x0, leftMid + gap * 0.5, x0 + sideW, colTop)
  pcall(drawStaying, m, x0, colBot, x0 + sideW, leftMid - gap * 0.5)
  pcall(drawBoardColumn, m, x0 + sideW + gap, colBot, x0 + sideW + gap + midW, colTop)
  pcall(drawLearned, x0 + W - sideW, colBot, x0 + W, colTop)
  local by = vsy * 0.14
  Ash.actionRow(x0, by, x0 + 300, by + 42, { fill = Ash.COL.steam, focused = true })
  text("CONFIRM EXTRACTION   [Enter]", x0 + 150, by + 15, 14, Ash.COL.ink, "c")
  buttons[#buttons + 1] = { x0, by, x0 + 300, by + 42, action = "confirm" }
  Ash.actionRow(x0 + 316, by, x0 + 556, by + 42, { fill = Ash.COL.muted, focused = false })
  text("BACK TO THE FIELD   [Esc]", x0 + 436, by + 15, 14, Ash.COL.muted, "c")
  buttons[#buttons + 1] = { x0 + 316, by, x0 + 556, by + 42, action = "cancel" }
  text("Whatever is not on the pad stays on Verdance. Structures become holdings.", x0, by - 18, 11, Ash.COL.muted, "l")
end

local function drawOver()
  local vsx, vsy = Spring.GetViewGeometry()
  Ash.scrim(0, 0, vsx, vsy, 0.92)
  local m = manifest or {}
  local g, s = m.going or {}, m.staying or {}
  local y = vsy * 0.74
  if overKind == "wiped" then
    text("Nobody came back.", vsx * 0.5, y, 28, Ash.COL.bad, "c")
    text("Everything on Verdance is Verdance's now.", vsx * 0.5, y - 34, 15, Ash.COL.muted, "c")
  else
    text("The company lifts from " .. tostring((m.pad and m.pad.label) or "the pad") .. ".", vsx * 0.5, y, 28, Ash.COL.gold, "c")
    local function n(k, one, many) return tostring(k) .. " " .. ((k == 1) and one or many) end
    text(string.format("%s and %s going.  %s, %s and %s stay.", n(#(g.heroes or {}), "person", "people"), n(g.unitCount or 0, "unit", "units"), n(#(s.heroes or {}), "person", "people"), n(s.unitCount or 0, "unit", "units"), n(s.structureCount or 0, "structure", "structures")), vsx * 0.5, y - 34, 15, Ash.COL.ink, "c")
  end
  -- the board, frozen, small, under the headline
  local b = theBoard()
  if b and #b.zones > 0 then
    local bw = math.min(420, vsx * 0.35)
    local bx1, by1 = vsx * 0.5 - bw * 0.5, y - 70 - bw * (b.mapZ / b.mapX)
    local proj, rect = b:fitProj(bx1, by1, bx1 + bw, y - 70)
    Ash.rect(rect[1], rect[2], rect[3], rect[4], { 0.05, 0.09, 0.07, 1 })
    b:paint(proj, { fade = true, seenNow = m.seen, glyphSize = 11, contradicted = WG and WG.vaContradicted or nil })
    Ash.outline(rect[1], rect[2], rect[3], rect[4], Ash.with(Ash.COL.edge, 0.4), 1)
    text("Returning to camp…", vsx * 0.5, rect[2] - 22, 13, Ash.COL.muted, "c")
  else
    text("Returning to camp…", vsx * 0.5, y - 70, 13, Ash.COL.muted, "c")
  end
end

function widget:DrawScreen()
  if not Ash then return end
  if phase == "manifest" then
    drawManifest()
  elseif phase == "extracting" then
    local vsx, vsy = Spring.GetViewGeometry()
    Ash.scrim(0, 0, vsx, vsy, 0.6)
    text("Extracting…", vsx * 0.5, vsy * 0.5, 24, Ash.COL.gold, "c")
    Ash.progressSweep(vsx * 0.5 - 140, vsy * 0.5 - 22, vsx * 0.5 + 140, vsy * 0.5 - 16, Ash.COL.steam, os.clock() * 0.6)
  elseif phase == "over" then
    drawOver()
  end
  gl.Color(1, 1, 1, 1)
end
