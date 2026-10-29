if not VFS.Include("LuaRules/Configs/va_active.lua") then return false end -- plain BAR unless the hub launched this
local widget = widget

function widget:GetInfo()
  return {
    name = "Verdance Infil",
    desc = "The landing card: who you brought, the belief board with the pad and the job marked, what the company thinks it is walking into. The game waits, paused; Enter closes the card and the field stays paused until the player presses Pause.",
    author = "Verdance",
    date = "2026-10-20",
    license = "GPL v2 or later",
    layer = 13,
    enabled = true,
  }
end

-- The card the sortie opens on. Same chrome as the exfil manifest; same board as the minimap.
-- "begin" (WG.vaVerbs) closes it: Enter, the button, BAR's own pause key, or the rig's player.

local Hud = VFS.Include("luaui/Include/va_hud.lua")
local Ash = Hud.Ash
local paused, theBoard = Hud.paused, Hud.board

local phase = "infil"        -- infil | field
local mission = nil
local sawPaused = false
local lastPauseAt = -10
local yevaHadBoard = false   -- Yeva's read is redone once the shared board exists
local buttons = {}
local C = {}                 -- composed copy: title, objective, threat, heroes, units, lines, yeva

local function compose()
  mission = Hud.seed()
  C = { heroes = {}, units = {}, lines = {}, yeva = {}, marks = {} }
  if not mission then return end
  local intent = mission.storyIntent or {}
  local obj = mission.objective or {}
  C.title = intent.title or mission.title or "Verdance's Ashes"
  C.missionNumber = tonumber(mission.missionNumber) or 1
  C.objective = obj.description or "Complete the marked objective."
  C.reason = intent.storyReason
  local diff = mission.difficulty
  if type(diff) == "table" and type(diff.label) == "string" and diff.label ~= "" then C.threat = diff.label end
  C.requiredFrames = tonumber(obj.requiredFrames) or 19800
  for _, h in ipairs(mission.heroes or {}) do
    if h.id then C.heroes[#C.heroes + 1] = { name = tostring(h.name or h.id), crit = h.missionCritical == true, level = tonumber(h.level) or 1, rank = tostring(h.rank or "Runner") } end
  end
  -- what else you brought: what actually comes down with the heroes: the reserve you chose to bring
  -- (roster.cadre) and what the shop sent (commerce.deploy). The layout force in playableSetup is a
  -- preview the gadget discards, so it is read only by an older mission that has neither.
  local counts, order = {}, {}
  local function add(def, n)
    local ud = UnitDefNames and UnitDefNames[def]
    local name = (ud and (ud.humanName or ud.name)) or def
    if name ~= "" and (tonumber(n) or 0) > 0 then
      if not counts[name] then counts[name] = 0; order[#order + 1] = name end
      counts[name] = counts[name] + tonumber(n)
    end
  end
  local cadre = mission.roster and mission.roster.cadre
  local deploy = mission.commerce and mission.commerce.deploy
  if type(cadre) == "table" or type(deploy) == "table" then
    for def, n in pairs(cadre or {}) do add(tostring(def), n) end
    for _, item in ipairs(deploy or {}) do
      if type(item) == "table" and item.unitDef then add(tostring(item.unitDef), tonumber(item.count) or 1) end
    end
  end
  local setup = (next(counts) == nil and not cadre and not deploy) and mission.playableSetup or nil
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
-- A hot-drop field is built with every pack the company could send; once the drop lands, the card
-- names who actually came (va_dropped_heroes, crew.lua vaNoteDropped), a hero rented while the
-- field loaded included (named from the crew roster, not on the seed's list).
local droppedSeen = ""
local crewRoster = nil
local function composeDropped()
  local ids = tostring(Spring.GetGameRulesParam("va_dropped_heroes") or "")
  if ids == droppedSeen or ids == "" or not mission then return end
  droppedSeen = ids
  local known = {}
  for _, h in ipairs(mission.heroes or {}) do if h.id then known[tostring(h.id)] = h end end
  if crewRoster == nil then
    local ok, mod = pcall(VFS.Include, "luarules/gadgets/include/va_crew_roster.lua")
    crewRoster = (ok and type(mod) == "table") and mod or false
  end
  C.heroes = {}
  for id in ids:gmatch("[^,]+") do
    local h = known[id]
    local r = (not h) and crewRoster and crewRoster.get and crewRoster.get(id)
    C.heroes[#C.heroes + 1] = h and { name = tostring(h.name or id), crit = h.missionCritical == true,
        level = tonumber(h.level) or 1, rank = tostring(h.rank or "Runner") }
      or { name = tostring((r and r.name) or id), crit = false, level = 1, rank = "Runner" }
  end
end

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

-- Closing the card does not start the clock: the field stays paused so the player can queue
-- orders (builders first), then presses BAR's Pause key to begin. A sortie that ends while the
-- card is up, or a player who unpauses with the card open, also closes it.
local function begin()
  if phase ~= "infil" then return false end
  phase = "field"
  if WG then WG.vaSortieBegan = true end
  Hud.setModal(false)
  Spring.Echo("VA_UI_SORTIE_BEGAN frame=" .. tostring(Spring.GetGameFrame() or 0) .. " paused=" .. tostring(paused()))
end

local function reopen()
  phase = "infil"
  Hud.setModal(true)
  Hud.setPaused(true)
  composeYeva()
end

function widget:Initialize()
  compose()
  -- An offline bake (the Koom war) has no sortie and nobody to press the pause key.
  local bake = (Spring.GetModOptions() or {}).va_shell_bake
  if bake == true or bake == 1 or bake == "1" or bake == "true" then mission = nil end
  if not mission then
    phase = "field"
    if WG then WG.vaSortieBegan = true end
    return
  end
  composeYeva()
  yevaHadBoard = WG and WG.vaBoard ~= nil
  Hud.setModal(true)
  Hud.verb("begin", begin)
  if WG then WG.vaSortieBegan = false end
  Spring.Echo("VA_UI_INFIL armed mission=" .. tostring(mission.missionId or C.title))
end

function widget:Shutdown()
  if phase == "infil" then Hud.setModal(false) end
end

function widget:Update()
  if phase ~= "infil" then return end
  composeDropped()
  if Hud.over() then begin(); return end
  if not sawPaused then
    if paused() then
      sawPaused = true
      Spring.Echo("VA_UI_PAUSE_HELD frame=" .. tostring(Spring.GetGameFrame() or 0))
    else
      local now = os.clock()
      if now - lastPauseAt >= 0.15 then lastPauseAt = now; Hud.setPaused(true) end
    end
  elseif not paused() then
    -- the player used BAR's pause key instead of Enter: that is a begin too
    begin()
  end
  if #C.yeva == 0 or (not yevaHadBoard and WG and WG.vaBoard) then
    yevaHadBoard = WG and WG.vaBoard ~= nil
    composeYeva()
  end
end

function widget:KeyPress(key)
  if phase ~= "infil" then return false end
  if key == 13 or key == 271 or key == 32 then Hud.press("begin"); return true end
  return true
end

function widget:MousePress(x, y, button)
  if phase ~= "infil" then return false end
  for _, b in ipairs(buttons) do
    if Ash.inRect(x, y, b) and b.action == "begin" then Hud.press("begin"); return true end
  end
  return true
end

function widget:TextCommand(cmd)
  if cmd == "vabrief" then reopen(); return true end
  return false
end

-- ---------------------------------------------------------------- draw
local text, wrap, column = Ash.text, Hud.wrap, Hud.column

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
    Hud.boardBox(b, bx1 + 6, by1 + 6, bx2 - 6, by2 - 6, { fade = false, labels = true, glyphSize = 13, contradicted = WG and WG.vaContradicted or nil })
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
  text(Hud.clock((C.requiredFrames or 19800) / 30), x, y - 4, 20, Ash.COL.ink, "l")
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
  text("TO THE FIELD   [Enter]", x0 + 150, by + 15, 14, Ash.COL.ink, "c")
  buttons[#buttons + 1] = { x0, by, x0 + 300, by + 42, action = "begin" }
  text("The field stays paused: queue your orders, then press Pause to begin.  The pad is where you land and where you lift; what is not on it at EXTRACT stays on Verdance.  /vabrief reopens this card.", x0, by - 18, 11, Ash.COL.muted, "l")
  gl.Color(1, 1, 1, 1)
end
