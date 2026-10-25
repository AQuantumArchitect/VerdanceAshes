if not VFS.Include("LuaRules/Configs/va_active.lua") then return false end -- plain BAR unless the hub launched this
local widget = widget

function widget:GetInfo()
  return {
    name = "Verdance Sidebar",
    desc = "The command rail, top to bottom as a sentence: phase + clock · mission + marks · the company (one card per hero, click selects, double-click focuses) · the pad + EXTRACT. Paints the route stage on the battlefield.",
    author = "Verdance",
    date = "2026-10-20",
    license = "GPL v2 or later",
    layer = -20000,
    enabled = true,
  }
end

-- Pass seven. Replaces gui_verdance_objectives.lua. Facts come from rules params the gadgets
-- publish (va_hud_heroes_json, va_pad_*, va_sec*, latches); nothing here rescans units.
-- Shape first, word second: chips, meters, dots, glyphs — colour never alone.

local Ash, J
do
  local ok, mod = pcall(VFS.Include, "luaui/Include/va_ash_tokens.lua")
  if not ok or type(mod) ~= "table" then ok, mod = pcall(VFS.Include, "LuaUI/Include/va_ash_tokens.lua") end
  Ash = (ok and type(mod) == "table") and mod or nil
  ok, mod = pcall(VFS.Include, "luaui/Include/va_json.lua")
  if not ok or type(mod) ~= "table" then ok, mod = pcall(VFS.Include, "LuaUI/Include/va_json.lua") end
  J = (ok and type(mod) == "table") and mod or nil
end

local vsx, vsy = Spring.GetViewGeometry()
local W = 272
local TOP_GAP = 98          -- under BAR's resource bar + the Tnb bar
local lastPoll = -999

local M = {}                -- mission seed: title, objective, kind, requiredFrames, roster
local S = { status = "active" }  -- polled facts
local H = { list = {}, byId = {} } -- heroes (live json merged with the seed roster)
local UI = { rects = {} }   -- click targets: { x1,y1,x2,y2, kind, data }
local route = { stage = nil, from = nil, to = nil, painted = nil }
local lastClick = { t = 0, id = nil }

local function num(name, default)
  local v = Spring.GetGameRulesParam(name)
  return tonumber(v) or default
end
local function str(name)
  local v = Spring.GetGameRulesParam(name)
  if type(v) == "string" and v ~= "" then return v end
  return nil
end
local function board() return WG and WG.vaBoard or nil end
local function say(speaker, text, seconds, accent) if WG and WG.vaVoice then WG.vaVoice.say(speaker, text, seconds, accent) end end
local function playUi(file, vol)
  if not Spring.PlaySoundFile then return end
  local ok = Spring.PlaySoundFile(tostring(file), vol or 1.0, "ui")
  if not ok then Spring.PlaySoundFile("sounds/ui/" .. tostring(file) .. ".wav", vol or 1.0, "ui") end
end
local function terminal() return S.sortieOver or num("va_terminal", 0) == 1 end
local function begun() return (WG and WG.vaSortieBegan) == true end

-- ---------------------------------------------------------------- seed
local function readMission()
  local ok, data = pcall(VFS.Include, "singleplayer/verdance_ashes/generated/va_current.lua")
  if ok and type(data) == "table" then return data end
  return nil
end

local function loadSeed()
  local m = readMission()
  M.seed = m
  if not m then
    Spring.Echo("VA_SIDEBAR no mission seed; rail stays blank")
    return
  end
  local intent = m.storyIntent or {}
  M.title = intent.title or m.title or "Verdance's Ashes"
  local obj = m.objective or {}
  M.objective = (m.missionCard and (m.missionCard.plainObjective or m.missionCard.objective)) or obj.description or "Complete the marked objective."
  M.kind = tostring(obj.kind or "")
  M.requiredFrames = tonumber(obj.requiredFrames) or 19800
  M.roster = {}
  for _, h in ipairs(m.heroes or {}) do
    if h.id then
      M.roster[#M.roster + 1] = { id = tostring(h.id), name = tostring(h.name or h.id), crit = h.missionCritical == true, level = tonumber(h.level) or 1, rank = tostring(h.rank or "") }
    end
  end
  Spring.Echo("VA_SIDEBAR armed mission=" .. tostring(m.missionId or M.title) .. " heroes=" .. #M.roster)
end

-- ---------------------------------------------------------------- poll
local function pollHeroes()
  local live = J and J.decode(Spring.GetGameRulesParam("va_hud_heroes_json") or "") or nil
  local states = J and J.decode(Spring.GetGameRulesParam("va_heroes_json") or "") or nil
  local list, byId = {}, {}
  for _, r in ipairs(M.roster or {}) do
    local rec = { id = r.id, name = r.name, crit = r.crit, level = r.level, rank = r.rank, state = "unknown" }
    list[#list + 1] = rec; byId[r.id] = rec
  end
  if type(live) == "table" then
    for _, h in ipairs(live) do
      local id = tostring(h.id or "")
      local rec = byId[id]
      if not rec then
        rec = { id = id, name = tostring(h.name or id), crit = h.crit == true, level = tonumber(h.level) or 1, rank = tostring(h.rank or "") }
        list[#list + 1] = rec; byId[id] = rec
      end
      -- a live unit wins over a wreck with the same id (recovered)
      if h.state == "alive" or rec.state ~= "alive" then
        rec.state = h.state or "alive"; rec.unit = h.unit; rec.hp = tonumber(h.hp); rec.x, rec.z = tonumber(h.x), tonumber(h.z)
        rec.onPad = h.onPad == true; rec.zone = h.zone; rec.dist = tonumber(h.dist); rec.vet = h.vet; rec.feature = h.feature
        if h.crit ~= nil then rec.crit = h.crit == true end
        if tonumber(h.level) then rec.level = tonumber(h.level) end
        if h.rank and h.rank ~= "" then rec.rank = h.rank end
        if h.name and h.name ~= "" then rec.name = h.name end
      end
    end
  end
  if type(states) == "table" then
    for id, st in pairs(states) do
      if type(st) == "table" then
        local rec = byId[tostring(id)]
        if not rec and (st.state == "lost" or st.state == "dead") then
          rec = { id = tostring(id), name = tostring(st.name or id), crit = st.missionCritical == true, level = 1, rank = "", state = "lost" }
          list[#list + 1] = rec; byId[tostring(id)] = rec
        elseif rec and rec.state ~= "alive" and rec.state ~= "down" then
          if st.state == "lost" or st.state == "dead" then rec.state = "lost" end
        end
      end
    end
  end
  -- The company is who dropped: a pack compiled into the field but left on the hub (the hot drop
  -- builds every candidate in) never shows up live, so it is not on the rail.
  local dropped = {}
  for _, rec in ipairs(list) do
    if rec.state ~= "unknown" then dropped[#dropped + 1] = rec else byId[rec.id] = nil end
  end
  list = dropped
  -- critical first, then alive on pad last so the ones you must fetch sit on top
  table.sort(list, function(a, b)
    local function rank(r) return (r.state == "down" and 0) or (r.state == "alive" and not r.onPad and 1) or (r.state == "alive" and 2) or 3 end
    local ra, rb = rank(a), rank(b)
    if ra ~= rb then return ra < rb end
    if a.crit ~= b.crit then return a.crit end
    return a.name < b.name
  end)
  H.list, H.byId = list, byId
  if WG then WG.vaHeroes = list end
end

local function marksList()
  local out = {}
  for i = 1, num("va_secondary_total", 0) do
    out[#out + 1] = {
      i = i, id = str("va_sec" .. i .. "_id"), kind = str("va_sec" .. i .. "_kind") or "", subtype = str("va_sec" .. i .. "_subtype") or "",
      label = str("va_sec" .. i .. "_label") or ("Mark " .. i), req = num("va_sec" .. i .. "_req", 0) == 1,
      done = num("va_sec" .. i .. "_done", 0) == 1, failed = num("va_sec" .. i .. "_failed", 0) == 1,
      x = num("va_sec" .. i .. "_x", -1), z = num("va_sec" .. i .. "_z", -1),
    }
  end
  return out
end

local function poll()
  S.objectiveTotal = num("va_objective_total", 0)
  S.objectiveDestroyed = num("va_objective_destroyed", 0)
  S.objectiveComplete = num("va_objective_complete", 0) == 1
  S.objectiveFailed = num("va_objective_failed", 0) == 1
  S.allDone = num("va_all_objectives_done", 0) == 1
  S.zoneHold = num("va_zone_hold", 0)
  S.zoneHoldNeed = num("va_zone_hold_need", 0)
  S.zoneHoldContested = num("va_zone_hold_contested", 0) == 1
  S.captureMode = num("va_capture_mode", 0) == 1
  S.capturePhase = str("va_capture_phase") or "idle"
  S.pocketClearFrac = num("va_pocket_clear_frac", 0)
  S.fortifyDef = num("va_fortify_def", 0)
  S.fortifyNeedDef = num("va_fortify_need_def", 0)
  S.claimValue = num("va_claim_value", 0)   -- our presence on the wound (vaClaimStrength)
  S.claimNeed = num("va_claim_need", 0)
  S.requiredFrames = num("va_required_frames", M.requiredFrames or 19800)
  S.marks = marksList()
  S.requiredLeft = num("va_secondary_required_left", 0)
  S.padPeople = num("va_pad_people", 0)
  S.padUnits = num("va_pad_units", 0)
  S.padOffUnits = num("va_pad_off_units", 0)
  S.padOffStructures = num("va_pad_off_structures", 0)
  S.padEnemy = num("va_pad_enemy_live", 0)
  S.inbound = num("va_inbound_total", 0)
  S.status = str("va_status") or S.status
  pollHeroes()
end

-- ---------------------------------------------------------------- route (painted on the field)
-- One stage at a time: push pad→objective · marks objective→next required · extract last→pad.
-- Painted once per stage with MarkerAddLine (the player's clear-marks button erases it);
-- no marker text, no ground arrows, no pings.
local function nextRequiredMark()
  for _, mk in ipairs(S.marks or {}) do
    if mk.req and not mk.done and not mk.failed and mk.x >= 0 then return mk end
  end
  for _, mk in ipairs(S.marks or {}) do
    if not mk.done and not mk.failed and mk.x >= 0 then return mk end
  end
  return nil
end

local function lastDoneMark()
  for i = #(S.marks or {}), 1, -1 do
    local mk = S.marks[i]
    if mk.done and mk.x >= 0 then return mk end
  end
  return nil
end

local function refreshRoute()
  route.stage, route.from, route.to = nil, nil, nil
  local b = board()
  if terminal() or not b then return end
  local px, pz = b:pad()
  local ox, oz = b:objectivePoint()
  local resolved = S.allDone or S.objectiveFailed
  if resolved and px then
    local from = ox and { x = ox, z = oz, label = "OBJECTIVE" } or nil
    local ld = lastDoneMark()
    if ld then from = { x = ld.x, z = ld.z, label = ld.label } end
    route.stage, route.from, route.to = "extract", from, { x = px, z = pz, label = "PAD" }
  elseif not S.objectiveComplete and ox then
    route.stage, route.from, route.to = "push", px and { x = px, z = pz, label = "PAD" } or nil, { x = ox, z = oz, label = "OBJECTIVE" }
  elseif S.objectiveComplete and S.requiredLeft > 0 and nextRequiredMark() then
    local mk = nextRequiredMark()
    route.stage, route.from, route.to = "marks", ox and { x = ox, z = oz, label = "OBJECTIVE" } or nil, { x = mk.x, z = mk.z, label = mk.label }
  elseif px then
    local from = ox and { x = ox, z = oz, label = "OBJECTIVE" } or nil
    local ld = lastDoneMark()
    if ld then from = { x = ld.x, z = ld.z, label = ld.label } end
    route.stage, route.from, route.to = "extract", from, { x = px, z = pz, label = "PAD" }
  end
  if route.stage and route.stage ~= route.painted and route.from and route.to and begun() then
    local y1 = Spring.GetGroundHeight(route.from.x, route.from.z) or 0
    local y2 = Spring.GetGroundHeight(route.to.x, route.to.z) or 0
    pcall(Spring.MarkerAddLine, route.from.x, y1, route.from.z, route.to.x, y2, route.to.z)
    route.painted = route.stage
    Spring.Echo("VA_UI_ROUTE_STAGE " .. route.stage .. " " .. tostring(route.from.label) .. "->" .. tostring(route.to.label))
  end
  if WG then WG.vaRoute = { stage = route.stage, from = route.from, to = route.to } end
end

-- ---------------------------------------------------------------- events
local function onMissionEvent(ev, reason)
  poll()
  if ev == "objective_complete" then
    playUi("beep6", 1.0)
    if S.requiredLeft > 0 then say("Ketha", "Primary's yours — finish the required marks, then bring them home.", 7)
    else say("Ketha", "Mark claimed. Your call when we leave. Load the pad, then press EXTRACT.", 7) end
  elseif ev == "objective_failed" then
    playUi("warning1", 1.0)
    say("Ketha", "Wreck's gone — rescue is scrubbed. Get the company onto the pad.", 7)
  elseif ev == "all_objectives_complete" then
    say("Ketha", "Required objectives complete. Load the pad with what you're keeping, then press EXTRACT.", 7)
  elseif ev == "secondary_complete" then
    playUi("beep4", 0.7)
  elseif ev == "secondary_changed" then
    playUi("warning2", 0.6)
  elseif ev == "debug_pause" then
    pcall(Spring.SendCommands, "pause 1")
  elseif ev == "sortie_over" then
    S.sortieOver = true
    route.stage, route.from, route.to = nil, nil, nil
    if WG then WG.vaRoute = nil end
  end
  refreshRoute()
end

local function onHeroEvent(ev, heroId, name, critical, x, z)
  heroId = tostring(heroId or "")
  local rec = H.byId[heroId]
  local who = (rec and rec.name) or tostring(name or heroId)
  if ev == "down" then
    playUi("warning2", 0.95)
    say("", who .. " is down — get a rez bot on the wreck.", 6, Ash and Ash.COL.bad)
  elseif ev == "recovered" then
    playUi("beep4", 1.0); say("", who .. " is back on their feet.", 5, Ash and Ash.COL.good)
  elseif ev == "recruited" then
    playUi("beep4", 1.0); say("", who .. " signed onto the company.", 6, Ash and Ash.COL.gold)
  elseif ev == "wreck_gone" then
    playUi("warning2", 0.85); say("", who .. "'s wreck is gone.", 6, Ash and Ash.COL.bad)
  elseif ev == "lost" then
    playUi("warning1", 1.0)
    if num("va_objective_failed", 0) ~= 1 then
      if rec and rec.crit then say("Ketha", who .. " is down for this drop — the sortie still stands. Get the rest home.", 7)
      else say("", who .. " is gone. The line will remember.", 6, Ash and Ash.COL.muted) end
    end
  end
  poll()
end

-- ---------------------------------------------------------------- lifecycle
function widget:Initialize()
  loadSeed()
  poll()
  pcall(function()
    widgetHandler:RegisterGlobal(widget, "VerdanceMissionEvent", function(ev, reason) onMissionEvent(ev, reason) end)
    widgetHandler:RegisterGlobal(widget, "VerdanceHeroEvent", function(ev, id, name, crit, x, z) onHeroEvent(ev, id, name, crit, x, z) end)
  end)
end

function widget:Shutdown()
  pcall(function()
    widgetHandler:DeregisterGlobal(widget, "VerdanceMissionEvent")
    widgetHandler:DeregisterGlobal(widget, "VerdanceHeroEvent")
  end)
  if WG then WG.vaRoute = nil; WG.vaHeroes = nil end
end

function widget:ViewResize(x, y) vsx, vsy = x, y end

function widget:GameFrame(frame)
  if frame - lastPoll >= 30 then
    lastPoll = frame
    poll()
    refreshRoute()
  end
end

function widget:TextCommand(cmd)
  if cmd == "vaextract" then
    if WG and WG.vaExfilModal then return true end
    if begun() and not terminal() then Spring.SendLuaRulesMsg("VA_CMD:manifest") end
    return true
  end
  return false
end

-- ---------------------------------------------------------------- input
local function focusHero(rec)
  if rec.x and rec.z then
    local y = Spring.GetGroundHeight(rec.x, rec.z) or 0
    pcall(Spring.SetCameraTarget, rec.x, y, rec.z, 0.5)
  end
end

function widget:MousePress(x, y, button)
  if terminal() or (WG and WG.vaExfilModal) then return false end
  if button ~= 1 then return false end
  for _, r in ipairs(UI.rects) do
    if Ash.inRect(x, y, r) then
      if r.kind == "extract" then
        if begun() then
          Spring.SendLuaRulesMsg("VA_CMD:manifest")
          Spring.Echo("VA_UI_EXTRACT_PRESSED frame=" .. tostring(Spring.GetGameFrame() or 0))
        end
        return true
      elseif r.kind == "hero" then
        local rec = r.data
        local now = os.clock()
        local dbl = (lastClick.id == rec.id) and (now - lastClick.t < 0.35)
        lastClick.t, lastClick.id = now, rec.id
        if rec.state == "alive" and rec.unit and Spring.ValidUnitID(rec.unit) then
          Spring.SelectUnitArray({ rec.unit })
        end
        if dbl then focusHero(rec) end
        return true
      end
    end
  end
  return false
end

-- ---------------------------------------------------------------- draw helpers
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
  local dropped = false
  if cur ~= "" then
    if #lines < maxLines then lines[#lines + 1] = cur else dropped = true end
  end
  if dropped or (#lines == maxLines and Ash.textW(lines[maxLines], size) > maxW) then
    lines[maxLines] = Ash.fit(lines[maxLines] .. " …", size, maxW)
  end
  return lines
end

local function fmtClock(sec)
  sec = math.max(0, math.floor(sec + 0.5))
  return string.format("%d:%02d", math.floor(sec / 60), sec % 60)
end

local function fmtDist(d)
  d = tonumber(d) or 0
  if d >= 1000 then return string.format("%.1f km", d / 1000) end
  return string.format("%d m", math.floor(d + 0.5))
end

local function phaseClock()
  local frame = Spring.GetGameFrame() or 0
  local req = S.requiredFrames or 19800
  local left = math.max(0, (req - frame) / 30)
  local over = math.max(0, (frame - req) / 30)
  local phase = str("va_phase")
  local known = { APPROACH = true, FIGHT = true, MARKS = true, EXTRACT = true, OVERTIME = true }
  phase = phase and string.upper(phase) or ""
  if not known[phase] then
    if S.allDone or S.objectiveFailed then phase = "EXTRACT"
    elseif S.objectiveComplete then phase = "MARKS"
    elseif frame < 90 * 30 then phase = "APPROACH"
    else phase = "FIGHT" end
  end
  if left <= 0 then phase = "OVERTIME" end
  return phase, left, over, math.min(1, frame / math.max(1, req))
end

-- ---------------------------------------------------------------- blocks (each returns next y)
local function drawPhase(x, y, right)
  local phase, left, over, frac = phaseClock()
  local spec = Ash.PHASE[phase] or Ash.PHASE.FIGHT
  local col = Ash.COL[spec.color] or Ash.COL.edge
  Ash.chipLabel(tostring(spec.glyph) .. " " .. phase, x, y, 10, col, "l")
  if left > 0 then text(fmtClock(left), right, y, 13, Ash.COL.ink, "r")
  else text("+" .. fmtClock(over), right, y, 13, Ash.COL.ash, "r") end
  if S.inbound > 0 then
    Ash.chipLabel("⇣ " .. math.floor(S.inbound) .. " inbound", right - Ash.textW(fmtClock(left), 13) - 14, y, 9, Ash.COL.steam, "r")
  end
  y = y - 10
  Ash.meter(x, y, right, y + 3, frac, (left > 0) and Ash.COL.edge or Ash.COL.ash)
  y = y - 6
  if spec.sub then text(spec.sub, x, y - 8, 9, Ash.COL.ash, "l"); y = y - 12 end
  return y - 8
end

local function drawMission(x, y, right)
  text("MISSION", x, y, 9, Ash.COL.ash, "l")
  Ash.rule(x, y - 4, right, Ash.COL.gold, 0.35)
  y = y - 18
  text(Ash.fit(M.title or "", 12, right - x), x, y, 12, Ash.COL.gold, "l"); y = y - 16
  local objCol = S.objectiveComplete and Ash.COL.good or (S.objectiveFailed and Ash.COL.bad or Ash.COL.ink)
  local prefix = S.objectiveComplete and (Ash.GLYPH.done .. " ") or (S.objectiveFailed and (Ash.GLYPH.failed .. " ") or (Ash.GLYPH.objective .. " "))
  for i, line in ipairs(wrap(M.objective or "", 11, right - x - 14, 2)) do
    text((i == 1 and prefix or "   ") .. line, x, y, 11, objCol, "l"); y = y - 14
  end
  -- progress meter: whichever gate the objective kind is behind
  local frac, label, col = nil, nil, Ash.COL.warn
  if not S.objectiveComplete and not S.objectiveFailed then
    if S.captureMode and S.capturePhase == "hold" then
      local need = (S.zoneHoldNeed > 0) and S.zoneHoldNeed or 900
      frac = S.zoneHold / need
      label = string.format("hold %ds / %ds", math.floor(S.zoneHold / 30), math.floor(need / 30))
      col = S.zoneHoldContested and Ash.COL.warn or Ash.COL.steam
    elseif S.captureMode then
      frac = S.pocketClearFrac
      label = string.format("clear %d%%", math.floor(frac * 100 + 0.5))
    elseif S.zoneHold > 0 then
      local need = (S.zoneHoldNeed > 0) and S.zoneHoldNeed or 900
      frac = S.zoneHold / need
      label = string.format("holding %ds / %ds", math.floor(S.zoneHold / 30), math.floor(need / 30))
      col = Ash.COL.steam
    elseif S.fortifyNeedDef > 0 or M.kind == "fortify_zone" or M.kind == "home_founding" then
      local need = (S.fortifyNeedDef > 0) and S.fortifyNeedDef or 800
      frac = S.fortifyDef / need
      label = string.format("defence %d / %d", math.floor(S.fortifyDef), math.floor(need))
      col = (S.fortifyDef >= need) and Ash.COL.good or Ash.COL.steam
    elseif S.objectiveTotal > 0 then
      frac = S.objectiveDestroyed / math.max(1, S.objectiveTotal)
      label = string.format("%s %d / %d", (M.kind == "eco_raid") and "wrecked" or "targets", S.objectiveDestroyed, S.objectiveTotal)
    end
  end
  if frac then
    y = y - 2
    Ash.meter(x + 14, y, right - 70, y + 5, frac, col)
    text(label, right, y - 1, 9, col, "r")
    y = y - 14
  end
  -- taking the wound needs presence there: armed units and defences, in metal
  if S.claimNeed > 0 and not S.objectiveComplete and not S.objectiveFailed then
    local strong = S.claimValue >= S.claimNeed
    local c = strong and Ash.COL.good or Ash.COL.warn
    y = y - 2
    Ash.meter(x + 14, y, right - 70, y + 5, S.claimValue / S.claimNeed, c)
    text(string.format("presence %d / %d", math.floor(S.claimValue), math.floor(S.claimNeed)), right, y - 1, 9, c, "r")
    y = y - 14
  end
  -- marks: a square per mark, the current one named
  if #(S.marks or {}) > 0 then
    y = y - 4
    local mx = x + 14
    local current = nextRequiredMark()
    for _, mk in ipairs(S.marks) do
      local col2, filled
      if mk.failed then col2, filled = Ash.COL.bad, true
      elseif mk.done then col2, filled = Ash.COL.good, true
      elseif mk.kind == "hero_recover" then col2, filled = Ash.COL.bad, false
      elseif mk.req then col2, filled = Ash.COL.gold, true
      else col2, filled = Ash.COL.gold, false end
      Ash.swatch(mx, y - 1, 9, Ash.with(col2, filled and 0.9 or 0.8), filled)
      if mk.failed then text(Ash.GLYPH.failed, mx + 4.5, y - 1, 8, Ash.COL.ink, "c")
      elseif mk.done then text(Ash.GLYPH.done, mx + 4.5, y - 1, 8, Ash.COL.bg, "c") end
      if current and current.i == mk.i then Ash.outline(mx - 2, y - 3, mx + 11, y + 10, Ash.with(Ash.COL.ink, 0.8), 1) end
      mx = mx + 14
    end
    if current then
      local lbl = (current.kind == "hero_recover") and ("recover " .. current.label:gsub("^[^:]+:%s*", "")) or current.label
      text(Ash.fit((current.req and "required · " or "optional · ") .. lbl, 10, right - mx - 6), mx + 6, y, 10, current.kind == "hero_recover" and Ash.COL.bad or Ash.COL.gold, "l")
    elseif S.requiredLeft == 0 and S.objectiveComplete then
      text("marks done", mx + 6, y, 10, Ash.COL.good, "l")
    end
    y = y - 16
  end
  return y - 6
end

local function heroStateLabel(rec)
  local G = Ash.GLYPH
  if rec.state == "down" then return G.down .. " down", Ash.COL.bad end
  if rec.state == "lost" then return G.failed .. " lost", Ash.COL.muted end
  if rec.onPad then return G.onPad .. " on pad", Ash.COL.steam end
  local where = rec.dist and fmtDist(rec.dist) or ""
  return G.offPad .. " " .. where, (rec.dist and rec.dist > 1200) and Ash.COL.warn or Ash.COL.ink
end

local function drawCompany(x, y, right)
  local n = #H.list
  text("COMPANY", x, y, 9, Ash.COL.ash, "l")
  text(tostring(n) .. (n == 1 and " person" or " people"), right, y, 9, Ash.COL.muted, "r")
  Ash.rule(x, y - 4, right, Ash.COL.edge, 0.35)
  y = y - 12
  if n == 0 then text("nobody on the manifest", x, y - 10, 10, Ash.COL.muted, "l"); return y - 24 end
  local rowH = 30
  for _, rec in ipairs(H.list) do
    local y1, y2 = y - rowH, y
    local strip = rec.crit and Ash.COL.gold or Ash.COL.edge
    if rec.state == "down" then strip = Ash.COL.bad elseif rec.state == "lost" then strip = Ash.COL.muted end
    Ash.rect(x, y1 + 2, right, y2 - 2, Ash.with(Ash.COL.bg, 0.55))
    Ash.rect(x, y1 + 2, x + 3, y2 - 2, Ash.with(strip, 0.95))
    local nameCol = (rec.state == "alive") and Ash.COL.ink or Ash.COL.muted
    text(Ash.fit(rec.name, 11, 120), x + 10, y2 - 13, 11, nameCol, "l")
    local chip = (rec.rank ~= "" and rec.rank or "Runner") .. " L" .. tostring(rec.level or 1)
    if rec.vet and rec.vet ~= "" and rec.vet ~= "green" then chip = chip .. " · " .. rec.vet end
    text(Ash.fit(chip, 8, 120), x + 10, y2 - 25, 8, Ash.COL.ash, "l")
    if rec.state == "alive" then
      local hp = math.max(0, math.min(1, rec.hp or 1))
      local hpCol = (hp > 0.6 and Ash.COL.good) or (hp > 0.3 and Ash.COL.warn) or Ash.COL.bad
      Ash.meter(x + 118, y2 - 11, x + 172, y2 - 7, hp, hpCol)
    end
    local lbl, col = heroStateLabel(rec)
    text(lbl, right - 6, y2 - 13, 10, col, "r")
    if rec.state == "alive" and not rec.onPad and rec.zone and rec.zone ~= "" and board() then
      text(Ash.fit(board():label(rec.zone), 8, 90), right - 6, y2 - 25, 8, Ash.COL.muted, "r")
    end
    UI.rects[#UI.rects + 1] = { x, y1, right, y2, kind = "hero", data = rec }
    y = y - rowH
  end
  return y - 12
end

local function drawPad(x, y, right)
  local b = board()
  local padLabel = (b and b.padId and b:label(b.padId)) or "the pad"
  text("PAD", x, y, 9, Ash.COL.ash, "l")
  text(Ash.fit(padLabel, 9, 150), right, y, 9, Ash.COL.steam, "r")
  Ash.rule(x, y - 4, right, Ash.COL.steam, 0.35)
  y = y - 18
  -- ground taken this sortie is extraction ground too (the exfil gadget's va_taken_zones)
  local taken = tostring(Spring.GetGameRulesParam("va_taken_zones") or "")
  if taken ~= "" then
    local names = {}
    for zid in taken:gmatch("[^,]+") do names[#names + 1] = (b and b:label(zid)) or zid end
    text(Ash.fit("also lifts from: " .. table.concat(names, ", "), 9, right - x), x, y, 9, Ash.COL.steam, "l")
    y = y - 14
  end
  -- people dots: one per living person, filled when on the pad
  local alive, onPad, off = 0, 0, {}
  for _, rec in ipairs(H.list) do
    if rec.state == "alive" then
      alive = alive + 1
      if rec.onPad then onPad = onPad + 1 else off[#off + 1] = rec end
    end
  end
  table.sort(off, function(a, c) return (a.dist or 0) > (c.dist or 0) end)
  local dx = x
  if alive > 0 then dx = x + Ash.dots(x, y - 2, alive, onPad, Ash.COL.steam, 8, 4) + 6 end
  text(string.format("%d / %d people · %d units aboard", onPad, alive, S.padUnits), dx, y, 10, Ash.COL.ink, "l")
  y = y - 14
  -- exposure: how much of us they see, where
  local best, bestLabel = 0, nil
  if b then
    for _, z in ipairs(b.zones) do
      local v = b:exposure(z.id)
      if v > best then best, bestLabel = v, z.label end
    end
  end
  local level, lcol
  if best < 0.05 then level, lcol = "quiet", Ash.COL.muted
  elseif best < 0.25 then level, lcol = "noticed", Ash.COL.ink
  elseif best < 0.6 then level, lcol = "loud", Ash.COL.warn
  else level, lcol = "pinned", Ash.COL.bad end
  Ash.rect(x, y - 2, x + 10, y + 8, { 0.12, 0.14, 0.13, 0.85 })
  Ash.hatchRect(x, y - 2, x + 10, y + 8, Ash.with(Ash.COL.bad, 0.3 + 0.7 * math.min(1, best)), 3)
  Ash.outline(x, y - 2, x + 10, y + 8, Ash.with(Ash.COL.bad, 0.6), 1)
  local seen = "seen · " .. level
  if bestLabel and best >= 0.05 then seen = seen .. " · " .. bestLabel end
  text(Ash.fit(seen, 10, right - x - 16), x + 16, y, 10, lcol, "l")
  y = y - 14
  if S.padEnemy > 0 then
    text(string.format("%s %d enemy on the pad", Ash.GLYPH.exposed, S.padEnemy), x, y, 10, Ash.COL.bad, "l")
    y = y - 14
  end
  -- EXTRACT: three redundant-coded states, never "good"
  if begun() then
    y = y - 4
    local empty = (S.padPeople + S.padUnits) == 0
    local fill, labelCol, label, sub
    if empty then
      fill, labelCol, label, sub = Ash.COL.bad, Ash.COL.bad, Ash.GLYPH.failed .. "  EXTRACT", "nobody on the pad"
    elseif #off > 0 then
      fill, labelCol = Ash.COL.warn, Ash.COL.warn
      label = "!  EXTRACT · " .. S.padPeople .. " ppl / " .. S.padUnits .. " u"
      sub = off[1].name .. (#off > 1 and (" +" .. (#off - 1)) or "") .. " off the pad — " .. fmtDist(off[1].dist)
    else
      fill, labelCol = Ash.COL.steam, Ash.COL.gold
      label = Ash.GLYPH.pad .. "  EXTRACT · " .. S.padPeople .. " ppl / " .. S.padUnits .. " u"
    end
    local h = sub and 42 or 30
    Ash.actionRow(x, y - h, right, y, { fill = fill, focused = not empty })
    text(label, x + 12, y - 19, 12, empty and labelCol or Ash.COL.ink, "l")
    if sub then text(Ash.fit(sub, 9, right - x - 16), x + 12, y - 33, 9, labelCol, "l") end
    UI.rects[#UI.rects + 1] = { x, y - h, right, y, kind = "extract" }
    y = y - h - 8
    -- the ledger: only when something would stay
    local rows = {}
    for i = 1, math.min(2, #off) do rows[#rows + 1] = { Ash.GLYPH.offPad .. " " .. off[i].name .. " — " .. fmtDist(off[i].dist), Ash.COL.bad } end
    if #off > 2 then rows[#rows + 1] = { Ash.GLYPH.offPad .. " +" .. (#off - 2) .. " more people off the pad", Ash.COL.bad } end
    if S.padOffUnits > 0 then rows[#rows + 1] = { "! " .. S.padOffUnits .. " unit" .. (S.padOffUnits == 1 and "" or "s") .. " off the pad", Ash.COL.warn } end
    if S.padOffStructures > 0 then rows[#rows + 1] = { Ash.GLYPH.holding .. " " .. S.padOffStructures .. " structure" .. (S.padOffStructures == 1 and "" or "s") .. " → holdings", Ash.COL.gold } end
    if #rows > 0 then
      text("LEFT IF YOU LIFT", x, y, 8, Ash.COL.ash, "l"); y = y - 12
      for i = 1, math.min(4, #rows) do text(Ash.fit(rows[i][1], 10, right - x), x, y, 10, rows[i][2], "l"); y = y - 12 end
    end
  else
    text("paused — Enter begins", x, y, 10, Ash.COL.steam, "l"); y = y - 14
  end
  return y - 4
end

-- ---------------------------------------------------------------- frame
local drawFail = {}
local function guard(name, fn, ...)
  local ok, res = pcall(fn, ...)
  if not ok then
    if not drawFail[name] then drawFail[name] = true; Spring.Echo("VA_UI_DRAW_FAIL " .. name .. " " .. tostring(res)) end
    return nil
  end
  return res
end

function widget:DrawScreen()
  if Spring.IsGUIHidden() or not Ash or not M.seed then return end
  pcall(function()
    local vx, vy = Spring.GetViewGeometry()
    if vx and vx > 32 then vsx, vsy = vx, vy end
    if gl.Scissor then gl.Scissor(false) end
    if gl.DepthTest then gl.DepthTest(false) end
    if gl.Blending then gl.Blending(true) end
    gl.Color(1, 1, 1, 1)
  end)
  UI.rects = {}
  if S.sortieOver or (WG and WG.vaExfilModal) then return end
  local right = vsx - 10
  local left = right - W
  local top = vsy - TOP_GAP
  local x = left + 12
  local inner = right - 12
  -- Two passes: measure with a no-op... keep it simple: draw the panel tall, then the blocks.
  -- Panel height is remembered from the previous frame (content changes slowly).
  local function blocks()
    local y = top - 8
    y = guard("phase", drawPhase, x, y, inner) or (y - 30)
    y = guard("mission", drawMission, x, y, inner) or (y - 60)
    y = guard("company", drawCompany, x, y, inner) or (y - 40)
    y = guard("pad", drawPad, x, y, inner) or (y - 60)
    return math.max(24, y)
  end
  local bottom = UI.lastBottom or (top - 320)
  Ash.panel(left, bottom - 10, right, top + 10, { accent = Ash.COL.edge })
  local y = blocks()
  if math.abs(y - bottom) > 2 then
    -- content height changed: redraw the panel at the right size, then the content once more
    UI.rects = {}
    Ash.panel(left, y - 10, right, top + 10, { accent = Ash.COL.edge })
    y = blocks()
  end
  UI.lastBottom = y
  gl.Color(1, 1, 1, 1)
end
