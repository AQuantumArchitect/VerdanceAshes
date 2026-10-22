local widget = widget

function widget:GetInfo()
  return {
    name = "Verdance Infil",
    desc = "The landing card: who you brought, the belief board with the pad and the job marked, what the company thinks it is walking into. The game waits, paused, until Enter.",
    author = "Verdance",
    date = "2026-10-20",
    license = "GPL v2 or later",
    layer = 13,
    enabled = true,
  }
end

-- Pass seven. Replaces the 45-second briefing card and the pause hammer in the old
-- objectives HUD. Same chrome as the exfil manifest; same board as the minimap.

local Ash, Board
do
  local ok, mod = pcall(VFS.Include, "luaui/Include/va_ash_tokens.lua")
  if not ok or type(mod) ~= "table" then ok, mod = pcall(VFS.Include, "LuaUI/Include/va_ash_tokens.lua") end
  Ash = (ok and type(mod) == "table") and mod or nil
  ok, mod = pcall(VFS.Include, "luaui/Include/va_board.lua")
  if not ok or type(mod) ~= "table" then ok, mod = pcall(VFS.Include, "LuaUI/Include/va_board.lua") end
  Board = (ok and type(mod) == "table") and mod or nil
end

local phase = "infil"        -- infil | field
local mission = nil
local board = nil            -- own instance until the minimap publishes WG.vaBoard
local sawPaused = false
local lastPauseAt = -10
local buttons = {}
local C = {}                 -- composed copy: title, objective, threat, heroes, units, lines, yeva

local function readLua(path)
  local ok, data = pcall(VFS.Include, path)
  if ok and type(data) == "table" then return data end
  return nil
end

local function num(name, default) return tonumber((Spring.GetGameRulesParam(name))) or default end

local function paused()
  if Spring.IsGamePaused then return Spring.IsGamePaused() == true end
  local _, _, p = Spring.GetGameSpeed()
  return p == true
end

local function theBoard()
  if WG and WG.vaBoard then return WG.vaBoard end
  if not board and Board then board = Board.new() end
  return board
end

local function compose()
  mission = readLua("singleplayer/verdance_ashes/generated/va_current.lua")
  C = { heroes = {}, units = {}, lines = {}, yeva = {}, marks = {} }
  if not mission then return end
  local intent = mission.storyIntent or {}
  local obj = mission.objective or {}
  local card = mission.missionCard or intent.missionCard or {}
  C.title = intent.title or mission.title or "Verdance's Ashes"
  C.missionNumber = tonumber(mission.missionNumber) or 1
  C.objective = card.plainObjective or card.objective or obj.description or "Complete the marked objective."
  C.reason = intent.storyReason
  local diff = mission.difficulty
  if type(diff) == "table" and type(diff.label) == "string" and diff.label ~= "" then C.threat = diff.label
  elseif type(card.threats) == "string" then C.threat = card.threats end
  C.requiredFrames = tonumber(obj.requiredFrames) or 19800
  for _, h in ipairs(mission.heroes or {}) do
    if h.id then C.heroes[#C.heroes + 1] = { name = tostring(h.name or h.id), crit = h.missionCritical == true, level = tonumber(h.level) or 1, rank = tostring(h.rank or "Runner") } end
  end
  -- what else you brought: the player's force groups, by human name
  local counts, order = {}, {}
  local setup = mission.playableSetup
  for _, force in ipairs((setup and setup.forces) or {}) do
    if tonumber(force.teamID) == 0 then
      for _, group in ipairs(force.groups or {}) do
        for _, spec in ipairs(group.units or {}) do
          local def = tostring(spec.unitDefName or spec.def or "")
          local ud = UnitDefNames and UnitDefNames[def]
          local name = (ud and (ud.humanName or ud.name)) or def
          if name ~= "" then
            if not counts[name] then counts[name] = 0; order[#order + 1] = name end
            counts[name] = counts[name] + (tonumber(spec.count) or 1)
          end
        end
      end
    end
  end
  table.sort(order, function(a, b) return counts[a] > counts[b] end)
  for i = 1, math.min(6, #order) do C.units[#C.units + 1] = { name = order[i], count = counts[order[i]] } end
  if type(intent.briefing) == "table" and type(intent.briefing.lines) == "table" then
    for i = 1, math.min(2, #intent.briefing.lines) do C.lines[#C.lines + 1] = tostring(intent.briefing.lines[i]) end
  end
  -- marks the seed knows about (the live ledger arrives once the gadget publishes)
  for _, sid in ipairs(obj.secondaryCaptureZoneIds or mission.secondaryCaptureZoneIds or {}) do C.marks[#C.marks + 1] = tostring(sid) end
end

-- Yeva's read of the ground: the pad, the objective, the loudest other belief, who is posted.
local function composeYeva()
  local b = theBoard()
  C.yeva = {}
  if not b then return end
  local said = {}
  local function add(id)
    if id and not said[id] and b.byId[id] then said[id] = true; C.yeva[#C.yeva + 1] = b:sentence(id) end
  end
  add(b.padId)
  add(b.objectiveId)
  for _, sid in ipairs(C.marks or {}) do add(sid) end
  -- the most threatening zone we have an opinion about
  local bestId, bestT = nil, 0
  for _, z in ipairs(b.zones) do
    local state, conf, faction, stale, threat = b:believed(z.id)
    local t = (tonumber(threat) or 0) * (0.5 + 0.5 * conf)
    if (state == "held") and t > bestT and not said[z.id] then bestT, bestId = t, z.id end
  end
  add(bestId)
  if b.intel then
    for _, p in ipairs(b.intel.posted or {}) do
      if b.byId[tostring(p.zoneId or "")] then C.yeva[#C.yeva + 1] = tostring(p.name or p.heroId) .. " is posted at " .. b:label(p.zoneId) .. "." end
    end
    for _, f in ipairs(b.intel.frames or {}) do
      if b.byId[tostring(f.zoneId or "")] then C.yeva[#C.yeva + 1] = tostring(f.name or f.heroId) .. " was left at " .. b:label(f.zoneId) .. "." end
    end
  end
  if #C.yeva == 0 then C.yeva[1] = "Nobody has looked at this ground. We land blind." end
end

local function setModal(on)
  if WG then WG.vaExfilModal = on and true or false end
end

local function begin()
  phase = "field"
  if WG then WG.vaSortieBegan = true end
  setModal(false)
  pcall(Spring.SendCommands, "pause 0")
  Spring.Echo("VA_UI_SORTIE_BEGAN frame=" .. tostring(Spring.GetGameFrame() or 0))
end

local function reopen()
  phase = "infil"
  setModal(true)
  pcall(Spring.SendCommands, "pause 1")
  composeYeva()
end

function widget:Initialize()
  compose()
  if not mission then
    phase = "field"
    if WG then WG.vaSortieBegan = true end
    return
  end
  composeYeva()
  setModal(true)
  if WG then WG.vaSortieBegan = false end
  Spring.Echo("VA_UI_INFIL armed mission=" .. tostring(mission.missionId or C.title))
end

function widget:Shutdown()
  if phase == "infil" then setModal(false) end
end

function widget:Update()
  if phase ~= "infil" then return end
  if num("va_terminal", 0) == 1 then begin(); return end
  if not sawPaused then
    if paused() then
      sawPaused = true
      Spring.Echo("VA_UI_PAUSE_HELD frame=" .. tostring(Spring.GetGameFrame() or 0))
    else
      local now = os.clock()
      if now - lastPauseAt >= 0.15 then lastPauseAt = now; pcall(Spring.SendCommands, "pause 1") end
    end
  elseif not paused() then
    -- the player used BAR's pause key instead of Enter: that is a begin too
    begin()
  end
  if #C.yeva == 0 or (WG and WG.vaBoard and board) then
    board = nil
    composeYeva()
  end
end

function widget:KeyPress(key)
  if phase ~= "infil" then return false end
  if key == 13 or key == 271 or key == 32 then begin(); return true end
  return true
end

function widget:MousePress(x, y, button)
  if phase ~= "infil" then return false end
  for _, b in ipairs(buttons) do
    if Ash.inRect(x, y, b) and b.action == "begin" then begin(); return true end
  end
  return true
end

function widget:TextCommand(cmd)
  if cmd == "vabrief" then reopen(); return true end
  return false
end

-- ---------------------------------------------------------------- draw
local function text(s, x, y, size, col, align) Ash.text(s, x, y, size, col, align) end

local function wrap(s, size, maxW, maxLines)
  local lines, cur = {}, ""
  for word in tostring(s or ""):gmatch("%S+") do
    local try = (cur == "") and word or (cur .. " " .. word)
    if Ash.textW(try, size) <= maxW then cur = try
    else
      if cur ~= "" then lines[#lines + 1] = cur end
      cur = word
      if #lines >= maxLines then break end
    end
  end
  if cur ~= "" and #lines < maxLines then lines[#lines + 1] = cur end
  return lines
end

local function column(x1, y1, x2, y2, kicker, accent)
  Ash.panel(x1, y1, x2, y2, { accent = accent })
  text(kicker, x1 + 12, y2 - 18, 10, Ash.COL.ash, "l")
  Ash.rule(x1 + 12, y2 - 23, x2 - 12, accent, 0.45)
  return x1 + 12, y2 - 42, x2 - 12
end

local function drawCompany(x1, y1, x2, y2)
  local x, y, right = column(x1, y1, x2, y2, "THE COMPANY  ·  " .. #C.heroes .. (#C.heroes == 1 and " person" or " people"), Ash.COL.edge)
  for _, h in ipairs(C.heroes) do
    if y < y1 + 40 then break end
    Ash.rect(x, y - 20, right, y + 8, Ash.with(Ash.COL.bg, 0.55))
    Ash.rect(x, y - 20, x + 3, y + 8, Ash.with(h.crit and Ash.COL.gold or Ash.COL.edge, 0.95))
    text(Ash.fit(h.name, 13, right - x - 90), x + 10, y - 4, 13, Ash.COL.ink, "l")
    text(h.rank .. "  L" .. tostring(h.level), right - 6, y - 4, 10, Ash.COL.ash, "r")
    if h.crit then text("must come home", x + 10, y - 16, 8, Ash.COL.gold, "l") end
    y = y - 32
  end
  if #C.units > 0 then
    y = y - 6
    text("AND", x, y, 9, Ash.COL.ash, "l"); y = y - 16
    for _, u in ipairs(C.units) do
      if y < y1 + 14 then break end
      text(Ash.fit(string.format("%d × %s", u.count, u.name), 11, right - x), x, y, 11, Ash.COL.muted, "l"); y = y - 15
    end
  end
end

local function drawBoard(x1, y1, x2, y2)
  local b = theBoard()
  local x, y, right = column(x1, y1, x2, y2, "WHAT THE COMPANY BELIEVES  ·  belief, not truth", Ash.COL.gold)
  local legendH = 20
  local bx1, by1, bx2, by2 = x, y1 + 12 + legendH, right, y + 10
  Ash.rect(bx1, by1, bx2, by2, Ash.with(Ash.COL.bg, 0.9))
  if b and #b.zones > 0 then
    local proj, rect = b:fitProj(bx1 + 6, by1 + 6, bx2 - 6, by2 - 6)
    Ash.rect(rect[1], rect[2], rect[3], rect[4], { 0.05, 0.09, 0.07, 1 })
    b:paint(proj, { fade = false, labels = true, glyphSize = 13, contradicted = WG and WG.vaContradicted or nil })
    Ash.outline(rect[1], rect[2], rect[3], rect[4], Ash.with(Ash.COL.edge, 0.4), 1)
  else
    text("no belief board for this map", (bx1 + bx2) * 0.5, (by1 + by2) * 0.5, 12, Ash.COL.muted, "c")
  end
  -- legend: one swatch per encoding that appears
  local lx, ly = x, y1 + 14
  local function key(col, filled, label)
    Ash.swatch(lx, ly, 9, Ash.with(col, 0.9), filled)
    text(label, lx + 13, ly, 9, Ash.COL.muted, "l")
    lx = lx + 13 + Ash.textW(label, 9) + 14
  end
  key(Ash.COL.edge, true, "ours")
  local seen = {}
  if b then
    for _, z in ipairs(b.zones) do
      local state, _, faction = b:believed(z.id)
      if state == "held" and faction and not seen[faction] then seen[faction] = true; key(Ash.faction(faction), true, tostring(faction)) end
    end
  end
  key(Ash.COL.muted, false, "empty")
  text(Ash.GLYPH.unknown .. " nobody looked", lx, ly, 9, Ash.COL.ash, "l"); lx = lx + Ash.textW("? nobody looked", 9) + 14
  Ash.rect(lx, ly, lx + 9, ly + 9, { 0.12, 0.14, 0.13, 0.85 }); Ash.hatchRect(lx, ly, lx + 9, ly + 9, Ash.with(Ash.COL.bad, 0.8), 3)
  text("they see us", lx + 13, ly, 9, Ash.COL.muted, "l")
end

local function drawJob(x1, y1, x2, y2)
  local x, y, right = column(x1, y1, x2, y2, "THE JOB", Ash.COL.warn)
  for _, line in ipairs(wrap(C.objective, 12, right - x, 4)) do text(line, x, y, 12, Ash.COL.ink, "l"); y = y - 16 end
  if C.threat then y = y - 2; text(Ash.fit(C.threat, 10, right - x), x, y, 10, Ash.COL.warn, "l"); y = y - 16 end
  local b = theBoard()
  local marks = b and b:marks() or {}
  if #marks > 0 then
    y = y - 4
    text("MARKS", x, y, 9, Ash.COL.ash, "l"); y = y - 14
    for _, mk in ipairs(marks) do
      local g = mk.req and Ash.GLYPH.markReq or Ash.GLYPH.markOpt
      local col = (mk.kind == "hero_recover") and Ash.COL.bad or Ash.COL.gold
      text(g .. "  " .. Ash.fit(mk.label, 11, right - x - 70), x, y, 11, col, "l")
      text(mk.req and "required" or "optional", right, y, 9, Ash.COL.muted, "r")
      y = y - 15
    end
  elseif #C.marks > 0 and b then
    y = y - 4
    text("MARKS", x, y, 9, Ash.COL.ash, "l"); y = y - 14
    for _, sid in ipairs(C.marks) do text(Ash.GLYPH.markOpt .. "  " .. Ash.fit(b:label(sid), 11, right - x), x, y, 11, Ash.COL.gold, "l"); y = y - 15 end
  end
  y = y - 8
  text("THE CLOCK", x, y, 9, Ash.COL.ash, "l"); y = y - 16
  local sec = math.floor((C.requiredFrames or 19800) / 30)
  text(string.format("%d:%02d", math.floor(sec / 60), sec % 60), x, y - 4, 20, Ash.COL.ink, "l")
  y = y - 22
  text("then overtime — the map wakes, nothing ends", x, y, 9, Ash.COL.ash, "l")
  y = y - 20
  text("YEVA", x, y, 9, Ash.COL.ash, "l"); y = y - 14
  for i, s in ipairs(C.yeva) do
    if y < y1 + 16 or i > 6 then break end
    for _, line in ipairs(wrap(s, 10, right - x, 2)) do text(line, x, y, 10, Ash.COL.ketha, "l"); y = y - 13 end
    y = y - 3
  end
end

function widget:DrawScreen()
  if phase ~= "infil" or not Ash or not mission then return end
  buttons = {}
  local vsx, vsy = Spring.GetViewGeometry()
  Ash.scrim(0, 0, vsx, vsy, 0.82)
  local Wd = math.min(1180, vsx - 60)
  local x0 = (vsx - Wd) * 0.5
  local top = vsy - 56
  text("DROP  ·  MISSION " .. tostring(C.missionNumber), x0, top, 10, Ash.COL.ash, "l")
  text(C.title or "", x0, top - 28, 24, Ash.COL.gold, "l")
  if C.reason then text(Ash.fit(tostring(C.reason), 11, Wd * 0.5), x0 + Wd, top - 24, 11, Ash.COL.muted, "r") end
  local colTop = top - 52
  local gap = 16
  local leftW = Wd * 0.26
  local rightW = Wd * 0.27
  local midW = Wd - leftW - rightW - 2 * gap
  -- the columns are as tall as the board needs (square-ish maps), never taller
  local b = theBoard()
  local boardH = midW * ((b and b.mapZ or 1) / (b and b.mapX or 1))
  local colBot = math.max(vsy * 0.14 + 64, colTop - (boardH + 86))
  if colBot > colTop - 160 then colBot = math.max(40, colTop - 160) end
  pcall(drawCompany, x0, colBot, x0 + leftW, colTop)
  pcall(drawBoard, x0 + leftW + gap, colBot, x0 + leftW + gap + midW, colTop)
  pcall(drawJob, x0 + Wd - rightW, colBot, x0 + Wd, colTop)
  -- Ketha's line + BEGIN, right under the columns
  local by = math.max(vsy * 0.08, colBot - 64)
  if C.lines[1] then Ash.voiceBlock(x0 + 330 + (Wd - 330) * 0.5, by + 21, Wd - 330, "Ketha", C.lines[1], 1) end
  Ash.actionRow(x0, by, x0 + 300, by + 42, { fill = Ash.COL.steam, focused = true })
  text("BEGIN   [Enter]", x0 + 150, by + 15, 14, Ash.COL.ink, "c")
  buttons[#buttons + 1] = { x0, by, x0 + 300, by + 42, action = "begin" }
  text("The pad is where you land and where you lift. What is not on it when you press EXTRACT stays on Verdance.  /vabrief reopens this card.", x0, by - 18, 11, Ash.COL.muted, "l")
  gl.Color(1, 1, 1, 1)
end
