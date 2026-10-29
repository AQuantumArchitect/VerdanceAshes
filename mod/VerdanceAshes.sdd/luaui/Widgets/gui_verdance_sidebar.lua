if not VFS.Include("LuaRules/Configs/va_active.lua") then return false end -- plain BAR unless the hub launched this
local widget = widget

function widget:GetInfo()
  return {
    name = "Verdance Sidebar",
    desc = "The command rail, top to bottom as a sentence: phase + clock · mission + its gauge + marks · the company (one card per hero, click selects, double-click focuses) · the pad + EXTRACT. Paints the route stage on the battlefield.",
    author = "Verdance",
    date = "2026-10-20",
    license = "GPL v2 or later",
    layer = -20000,
    enabled = true,
  }
end

-- Three layers, each feeding the next:
--   facts (S, H)  polled from the rules params the gadgets publish; nothing here rescans units
--   the rail (R)  what the rail says: phase, the job's gauge, marks, the pad and EXTRACT, in words
--                 and fractions; built at poll time and published as WG.vaRail
--   paint         DrawScreen lays R out; shape first, word second, colour never alone
-- EXTRACT is the "extract" verb (WG.vaVerbs): the button, /vaextract and the rig all press it.

local Hud = VFS.Include("luaui/Include/va_hud.lua")
local Ash = Hud.Ash
local num, str, on = Hud.num, Hud.str, Hud.on

local vsx, vsy = Spring.GetViewGeometry()
local W = 272
local TOP_GAP = 98          -- under BAR's resource bar + the Tnb bar
local lastPoll = -999

local M = {}                -- the mission seed: title, objective, kind, requiredFrames, roster, kings
local S = { status = "active" }  -- polled facts
local H = { list = {}, byId = {} } -- heroes (live json merged with the seed roster)
local R = {}                -- the rail
local UI = { rects = {}, n = 0 }   -- click targets: { x1,y1,x2,y2, kind, data }; the first n are live

-- Click targets are laid out every frame; the tables are reused, not made.
local function addRect(x1, y1, x2, y2, kind, data)
  local i = UI.n + 1
  local r = UI.rects[i]
  if not r then r = {}; UI.rects[i] = r end
  r[1], r[2], r[3], r[4], r.kind, r.data = x1, y1, x2, y2, kind, data
  UI.n = i
end
local route = { stage = nil, from = nil, to = nil, painted = nil }
local lastClick = { t = 0, id = nil }

local function say(speaker, text, seconds, accent) if WG and WG.vaVoice then WG.vaVoice.say(speaker, text, seconds, accent) end end
local playUi = Hud.sound
local function over() return S.sortieOver or Hud.over() end

-- ---------------------------------------------------------------- the seed
local function loadSeed()
  local m = Hud.seed()
  M.seed = m
  if not m then
    Spring.Echo("VA_SIDEBAR no mission seed; rail stays blank")
    return
  end
  local intent = m.storyIntent or {}
  M.title = intent.title or m.title or "Verdance's Ashes"
  local obj = m.objective or {}
  M.objective = obj.description or "Complete the marked objective."
  M.kind = tostring(obj.kind or "")
  M.requiredFrames = tonumber(obj.requiredFrames) or 19800
  M.roster = {}
  for _, h in ipairs(m.heroes or {}) do
    if h.id then
      M.roster[#M.roster + 1] = { id = tostring(h.id), name = tostring(h.name or h.id), crit = h.missionCritical == true, level = tonumber(h.level) or 1, rank = tostring(h.rank or "") }
    end
  end
  -- the kings' showdown: every king but ours must fall (game_verdance_kings.lua, va_king_<faction>)
  local player = tonumber(m.balance and m.balance.playerTeamID) or 0
  M.kings = {}
  for _, k in ipairs(m.kings or {}) do
    if tonumber(k.teamID) ~= player then M.kings[#M.kings + 1] = { faction = tostring(k.faction or k.teamID), label = tostring(k.label or k.faction or k.teamID) } end
  end
  Spring.Echo("VA_SIDEBAR armed mission=" .. tostring(m.missionId or M.title) .. " heroes=" .. #M.roster)
end

-- ---------------------------------------------------------------- facts
local function pollHeroes()
  local live = Hud.json("va_hud_heroes_json")
  local states = Hud.json("va_heroes_json")
  local list, byId = {}, {}
  for _, r in ipairs(M.roster or {}) do
    local rec = { id = r.id, name = r.name, crit = r.crit, level = r.level, rank = r.rank, state = "unknown" }
    list[#list + 1] = rec; byId[r.id] = rec
  end
  for _, h in ipairs(type(live) == "table" and live or {}) do
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
  for id, st in pairs(type(states) == "table" and states or {}) do
    if type(st) == "table" and (st.state == "lost" or st.state == "dead") then
      local rec = byId[tostring(id)]
      if not rec then
        rec = { id = tostring(id), name = tostring(st.name or id), crit = st.missionCritical == true, level = 1, rank = "", state = "lost" }
        list[#list + 1] = rec; byId[tostring(id)] = rec
      elseif rec.state ~= "alive" and rec.state ~= "down" then
        rec.state = "lost"
      end
    end
  end
  -- The company is who dropped: a pack compiled into the field but left on the hub (the hot drop
  -- builds every candidate in) never shows up live, so it is not on the rail.
  local dropped = {}
  for _, rec in ipairs(list) do
    if rec.state ~= "unknown" then dropped[#dropped + 1] = rec else byId[rec.id] = nil end
  end
  -- the ones you must fetch on top: down, then alive off the pad, then on the pad, then lost
  local function order(r) return (r.state == "down" and 0) or (r.state == "alive" and not r.onPad and 1) or (r.state == "alive" and 2) or 3 end
  table.sort(dropped, function(a, b)
    local oa, ob = order(a), order(b)
    if oa ~= ob then return oa < ob end
    if a.crit ~= b.crit then return a.crit end
    return a.name < b.name
  end)
  H.list, H.byId = dropped, byId
  if WG then WG.vaHeroes = dropped end
end

local function pollMarks()
  local out = {}
  for i = 1, num("va_secondary_total", 0) do
    local p = "va_sec" .. i .. "_"
    out[#out + 1] = {
      i = i, id = str(p .. "id"), kind = str(p .. "kind") or "", label = str(p .. "label") or ("Mark " .. i),
      req = on(p .. "req"), done = on(p .. "done"), failed = on(p .. "failed"), x = num(p .. "x", -1), z = num(p .. "z", -1),
    }
  end
  return out
end

local function poll()
  S.objectiveTotal = num("va_objective_total", 0)
  S.objectiveDestroyed = num("va_objective_destroyed", 0)
  S.objectiveComplete = on("va_objective_complete")
  S.objectiveFailed = on("va_objective_failed")
  S.allDone = on("va_all_objectives_done")
  S.zoneHold = num("va_zone_hold", 0)
  S.zoneHoldNeed = num("va_zone_hold_need", 0)
  S.zoneHoldContested = on("va_zone_hold_contested")
  S.captureMode = on("va_capture_mode")
  S.capturePhase = str("va_capture_phase") or "idle"
  S.clearNeed = num("va_pocket_clear_need", 0)
  S.fortifyDef = num("va_fortify_def", 0)
  S.fortifyNeedDef = num("va_fortify_need_def", 0)
  S.claimValue = num("va_claim_value", 0)   -- our presence on the wound (vaClaimStrength)
  S.claimNeed = num("va_claim_need", 0)
  S.purgeArmed = on("va_purge_armed")
  S.purgeDone = on("va_purge_done")
  S.purgeLeft = num("va_purge_left", -1)
  S.gateState = str("va_gate_state")
  S.requiredFrames = num("va_required_frames", M.requiredFrames or 19800)
  S.marks = pollMarks()
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

-- ---------------------------------------------------------------- the rail: phase
local PHASES = { APPROACH = true, FIGHT = true, MARKS = true, EXTRACT = true, OVERTIME = true }

-- The soft clock writes va_phase; a mission without a clock reads its phase from the latches.
local function railPhase()
  local frame = Spring.GetGameFrame() or 0
  local req = S.requiredFrames or 19800
  local left = math.max(0, (req - frame) / 30)
  local phase = string.upper(str("va_phase") or "")
  if not PHASES[phase] then
    if S.allDone or S.objectiveFailed then phase = "EXTRACT"
    elseif S.objectiveComplete then phase = "MARKS"
    elseif frame < 90 * 30 then phase = "APPROACH"
    else phase = "FIGHT" end
  end
  if left <= 0 then phase = "OVERTIME" end
  return { name = phase, left = left, over = math.max(0, (frame - req) / 30), frac = math.min(1, frame / math.max(1, req)) }
end

-- ---------------------------------------------------------------- the rail: the job's gauge
-- One gauge per kind of job; the first that applies is the job's. Each returns
-- { frac, label, col } (frac nil: words only) or nil when it does not apply.
local function holdGauge(word)
  local need = (S.zoneHoldNeed > 0) and S.zoneHoldNeed or 900
  -- contested: the enemy fights on it, so the clock waits (never colour alone: the word says so)
  return { frac = S.zoneHold / need, col = S.zoneHoldContested and Ash.COL.warn or Ash.COL.steam,
           label = string.format("%s %ds / %ds", word, math.floor(S.zoneHold / 30), math.floor(need / 30)) .. (S.zoneHoldContested and " · contested" or "") }
end

local GATE_WORDS = {   -- game_verdance_jump_gate.lua: frame → unpowered → charging → open; lost
  lost = function() return { frac = 0, label = "the gate is lost", col = Ash.COL.bad } end,
  frame = function() local b = num("va_gate_built", 0); return { frac = b, label = string.format("build the gate %d%%", math.floor(b * 100)), col = Ash.COL.warn } end,
  unpowered = function()
    local have, need = num("va_gate_afus", 0), math.max(1, num("va_gate_afus_need", 4))
    return { frac = have / need, label = string.format("power %d / %d fusions", have, need), col = Ash.COL.warn }
  end,
  charging = function() local c = num("va_gate_charge", 0); return { frac = c, label = string.format("charging %d%%", math.floor(c * 100)), col = Ash.COL.steam } end,
  open = function()
    local n = num("va_gate_ported", 0)
    return { frac = num("va_gate_channel", 0), label = "open · heroes onto the gate · " .. n .. " through", col = Ash.COL.gold }
  end,
}

local JOB_GAUGES = {
  function() -- the Spire Gate
    local w = S.gateState and GATE_WORDS[S.gateState]
    return w and w() or nil
  end,
  function() -- the kings' showdown
    if #M.kings == 0 then return nil end
    local standing = {}
    for _, k in ipairs(M.kings) do if num("va_king_" .. k.faction, 1) == 1 then standing[#standing + 1] = k.label end end
    local fallen = #M.kings - #standing
    return { frac = fallen / #M.kings, label = (#standing == 0) and "every king has fallen" or ("standing: " .. table.concat(standing, ", ")), col = Ash.COL.warn }
  end,
  function() -- capture, second half: hold the node under regrow pressure
    if S.captureMode and S.capturePhase == "hold" then return holdGauge("hold") end
  end,
  function() -- capture, first half: wreck enough of the pocket (the gadget says how many)
    if not S.captureMode then return nil end
    if S.objectiveTotal > 0 then
      local need = (S.clearNeed > 0) and S.clearNeed or S.objectiveTotal
      return { frac = S.objectiveDestroyed / need, label = string.format("clear %d / %d", S.objectiveDestroyed, need), col = Ash.COL.warn }
    end
    return { label = "clear: stand on it, nothing of theirs fighting", col = Ash.COL.warn }
  end,
  function() -- a zone to stand on
    if S.zoneHold > 0 then return holdGauge("holding") end
  end,
  function() -- fortify: defensive value in the zone
    if S.fortifyNeedDef > 0 or M.kind == "fortify_zone" or M.kind == "home_founding" then
      local need = (S.fortifyNeedDef > 0) and S.fortifyNeedDef or 800
      return { frac = S.fortifyDef / need, label = string.format("defence %d / %d", math.floor(S.fortifyDef), math.floor(need)),
               col = (S.fortifyDef >= need) and Ash.COL.good or Ash.COL.steam }
    end
  end,
  function() -- targets to wreck
    if S.objectiveTotal > 0 then
      return { frac = S.objectiveDestroyed / S.objectiveTotal, label = string.format("targets %d / %d", S.objectiveDestroyed, S.objectiveTotal), col = Ash.COL.warn }
    end
  end,
}

-- Beside the job: what else has to be true. Presence on the wound; a purge's last enemies.
local SIDE_GAUGES = {
  function()
    if S.claimNeed <= 0 or S.objectiveComplete or S.objectiveFailed then return nil end
    return { frac = S.claimValue / S.claimNeed, label = string.format("presence %d / %d", math.floor(S.claimValue), math.floor(S.claimNeed)),
             col = (S.claimValue >= S.claimNeed) and Ash.COL.good or Ash.COL.warn }
  end,
  function()
    if not S.purgeArmed or S.purgeDone or S.purgeLeft < 0 then return nil end
    return { label = "purge · " .. Hud.plural(S.purgeLeft, "enemy", "enemies") .. " left", col = Ash.COL.warn }
  end,
}

local function railGauges()
  local out = {}
  if not S.objectiveComplete and not S.objectiveFailed then
    for _, g in ipairs(JOB_GAUGES) do
      local v = g()
      if v then out[1] = v; break end
    end
  end
  for _, g in ipairs(SIDE_GAUGES) do
    local v = g()
    if v then out[#out + 1] = v end
  end
  return out
end

-- ---------------------------------------------------------------- the rail: marks
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

local function markLine(mk)
  local lbl = (mk.kind == "hero_recover") and ("recover " .. mk.label:gsub("^[^:]+:%s*", "")) or mk.label
  return (mk.req and "required · " or "optional · ") .. lbl
end

-- ---------------------------------------------------------------- the rail: the pad and EXTRACT
local EXPOSURE = { { 0.05, "quiet", "muted" }, { 0.25, "noticed", "ink" }, { 0.6, "loud", "warn" }, { math.huge, "pinned", "bad" } }

local function railExposure()
  local b = Hud.board()
  local best, where = 0, nil
  for _, z in ipairs(b and b.zones or {}) do
    local v = b:exposure(z.id)
    if v > best then best, where = v, z.label end
  end
  for _, e in ipairs(EXPOSURE) do
    if best < e[1] then
      return { level = e[2], col = Ash.COL[e[3]], best = best, where = (best >= 0.05) and where or nil }
    end
  end
end

-- Three states, redundant-coded and never "good": nobody aboard · someone left off · all aboard.
local function railExtract()
  local alive, off = 0, {}
  for _, rec in ipairs(H.list) do
    if rec.state == "alive" then
      alive = alive + 1
      if not rec.onPad then off[#off + 1] = rec end
    end
  end
  table.sort(off, function(a, c) return (a.dist or 0) > (c.dist or 0) end)
  local aboard = S.padPeople .. " ppl / " .. S.padUnits .. " u"
  local e = { alive = alive, onPad = alive - #off, off = off }
  if S.padPeople + S.padUnits == 0 then
    e.state, e.label, e.sub = "empty", Ash.GLYPH.failed .. "  EXTRACT", "nobody on our ground"
  elseif #off > 0 then
    e.state, e.label = "short", "!  EXTRACT · " .. aboard
    e.sub = off[1].name .. (#off > 1 and (" +" .. (#off - 1)) or "") .. " off the pad — " .. Hud.dist(off[1].dist)
  else
    e.state, e.label = "ready", Ash.GLYPH.pad .. "  EXTRACT · " .. aboard
  end
  -- left if you lift: only what would stay
  e.left = {}
  for i = 1, math.min(2, #off) do e.left[#e.left + 1] = { Ash.GLYPH.offPad .. " " .. off[i].name .. " — " .. Hud.dist(off[i].dist), Ash.COL.bad } end
  if #off > 2 then e.left[#e.left + 1] = { Ash.GLYPH.offPad .. " +" .. (#off - 2) .. " more people off the pad", Ash.COL.bad } end
  if S.padOffUnits > 0 then e.left[#e.left + 1] = { "! " .. Hud.plural(S.padOffUnits, "unit", "units") .. " off the pad", Ash.COL.warn } end
  if S.padOffStructures > 0 then e.left[#e.left + 1] = { Ash.GLYPH.holding .. " " .. Hud.plural(S.padOffStructures, "structure", "structures") .. " → holdings", Ash.COL.gold } end
  return e
end

-- The rail in one line, for the infolog and the rig: what a player would read off it.
local function railSentence()
  local p = R.phase
  local parts = { p.name .. " " .. ((p.left > 0) and Hud.clock(p.left) or ("+" .. Hud.clock(p.over))) }
  for _, g in ipairs(R.gauges) do parts[#parts + 1] = g.label end
  if R.current then parts[#parts + 1] = markLine(R.current) end
  parts[#parts + 1] = R.extract.label:gsub("^%S+%s+", "") .. (R.extract.sub and (" (" .. R.extract.sub .. ")") or "")
  return table.concat(parts, " | ")
end

local function buildRail()
  R.phase = railPhase()
  R.gauges = railGauges()
  R.current = nextRequiredMark()
  R.exposure = railExposure()
  R.extract = railExtract()
  R.sentence = railSentence()
  if WG then WG.vaRail = R end
end

-- ---------------------------------------------------------------- route (painted on the field)
-- One stage at a time: push pad→objective · marks objective→next required · extract last→pad.
-- Painted once per stage with MarkerAddLine (the player's clear-marks button erases it);
-- no marker text, no ground arrows, no pings.
local function point(x, z, label) return (x and { x = x, z = z, label = label }) or nil end

local function refreshRoute()
  route.stage, route.from, route.to = nil, nil, nil
  local b = Hud.board()
  if over() or not b then return end
  local px, pz = b:pad()
  local ox, oz = b:objectivePoint()
  local pad, objective = point(px, pz, "PAD"), point(ox, oz, "OBJECTIVE")
  local function lastStop() local ld = lastDoneMark(); return ld and point(ld.x, ld.z, ld.label) or objective end
  local mk = nextRequiredMark()
  if (S.allDone or S.objectiveFailed) and pad then
    route.stage, route.from, route.to = "extract", lastStop(), pad
  elseif not S.objectiveComplete and objective then
    route.stage, route.from, route.to = "push", pad, objective
  elseif S.objectiveComplete and S.requiredLeft > 0 and mk then
    route.stage, route.from, route.to = "marks", objective, point(mk.x, mk.z, mk.label)
  elseif pad then
    route.stage, route.from, route.to = "extract", lastStop(), pad
  end
  if route.stage and route.stage ~= route.painted and route.from and route.to and Hud.begun() then
    local y1 = Spring.GetGroundHeight(route.from.x, route.from.z) or 0
    local y2 = Spring.GetGroundHeight(route.to.x, route.to.z) or 0
    pcall(Spring.MarkerAddLine, route.from.x, y1, route.from.z, route.to.x, y2, route.to.z)
    route.painted = route.stage
    Spring.Echo("VA_UI_ROUTE_STAGE " .. route.stage .. " " .. tostring(route.from.label) .. "->" .. tostring(route.to.label))
  end
  if WG then WG.vaRoute = { stage = route.stage, from = route.from, to = route.to } end
end

local function refresh()
  poll()
  buildRail()
  refreshRoute()
end

-- ---------------------------------------------------------------- events: what the rail says aloud
local ON_MISSION = {
  objective_complete = function()
    playUi("beep6", 1.0)
    if S.requiredLeft > 0 then say("Ketha", "Primary's yours — finish the required marks, then bring them home.", 7)
    else say("Ketha", "Mark claimed. Your call when we leave. Load the pad, then press EXTRACT.", 7) end
  end,
  objective_failed = function()
    playUi("warning1", 1.0)
    say("Ketha", "Wreck's gone — rescue is scrubbed. Get the company onto the pad.", 7)
  end,
  all_objectives_complete = function()
    say("Ketha", "Required objectives complete. Load the pad with what you're keeping, then press EXTRACT.", 7)
  end,
  purge_complete = function()
    playUi("beep6", 0.9)
    say("Ketha", "Nothing of theirs is left standing. The purge is done.", 7)
  end,
  secondary_complete = function() playUi("beep4", 0.7) end,
  secondary_changed = function() playUi("warning2", 0.6) end,
  secondary_failed = function() playUi("warning1", 0.7) end,
  sortie_over = function()
    S.sortieOver = true
    if WG then WG.vaRoute = nil end
  end,
}

local function heroLost(rec, who)
  playUi("warning1", 1.0)
  if on("va_objective_failed") then return end  -- the objective_failed line already said it
  if rec and rec.crit then say("Ketha", who .. " is down for this drop — the sortie still stands. Get the rest home.", 7)
  else say("", who .. " is gone. The line will remember.", 6, Ash.COL.muted) end
end

local ON_HERO = {
  down = function(_, who) playUi("warning2", 0.95); say("", who .. " is down — get a rez bot on the wreck.", 6, Ash.COL.bad) end,
  recovered = function(_, who) playUi("beep4", 1.0); say("", who .. " is back on their feet.", 5, Ash.COL.good) end,
  recruited = function(_, who) playUi("beep4", 1.0); say("", who .. " signed onto the company.", 6, Ash.COL.gold) end,
  wreck_gone = function(_, who) playUi("warning2", 0.85); say("", who .. "'s wreck is gone.", 6, Ash.COL.bad) end,
  lost = heroLost,
}

local function onMissionEvent(ev, reason)
  poll()
  local fn = ON_MISSION[ev]
  if fn then fn(reason) end
  buildRail()
  refreshRoute()
end

local function onHeroEvent(ev, heroId, name, critical, x, z)
  heroId = tostring(heroId or "")
  local rec = H.byId[heroId]
  local fn = ON_HERO[ev]
  if fn then fn(rec, (rec and rec.name) or tostring(name or heroId)) end
  refresh()
end

-- ---------------------------------------------------------------- verbs
-- EXTRACT asks the exfil gadget for the manifest; the exfil widget opens it.
local function extract()
  if not Hud.begun() or over() or Hud.modal() then return false end
  Spring.SendLuaRulesMsg("VA_CMD:manifest")
  Spring.Echo("VA_UI_EXTRACT_PRESSED frame=" .. tostring(Spring.GetGameFrame() or 0) .. " rail=" .. tostring(R.sentence))
end

-- ---------------------------------------------------------------- lifecycle
function widget:Initialize()
  loadSeed()
  refresh()
  Hud.verb("extract", extract)
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
  if WG then WG.vaRoute = nil; WG.vaHeroes = nil; WG.vaRail = nil end
end

function widget:ViewResize(x, y) vsx, vsy = x, y end

local lastSaid = nil
function widget:GameFrame(frame)
  if frame - lastPoll < 30 then return end
  lastPoll = frame
  refresh()
  -- the rail's sentence, once a minute when it changed: a headless run reads what a player would
  if frame % 1800 < 30 and R.sentence ~= lastSaid and Hud.begun() then
    lastSaid = R.sentence
    Spring.Echo("VA_UI_RAIL " .. R.sentence)
  end
end

function widget:TextCommand(cmd)
  if cmd == "vaextract" then Hud.press("extract"); return true end
  return false
end

-- ---------------------------------------------------------------- input
local function focusHero(rec)
  if rec.x and rec.z then
    local y = Spring.GetGroundHeight(rec.x, rec.z) or 0
    pcall(Spring.SetCameraTarget, rec.x, y, rec.z, 0.5)
  end
end

local function clickHero(rec)
  local now = os.clock()
  local dbl = (lastClick.id == rec.id) and (now - lastClick.t < 0.35)
  lastClick.t, lastClick.id = now, rec.id
  if rec.state == "alive" and rec.unit and Spring.ValidUnitID(rec.unit) then Spring.SelectUnitArray({ rec.unit }) end
  if dbl then focusHero(rec) end
end

function widget:MousePress(x, y, button)
  if over() or Hud.modal() or button ~= 1 then return false end
  for i = 1, UI.n do
    local r = UI.rects[i]
    if Ash.inRect(x, y, r) then
      if r.kind == "extract" then Hud.press("extract") elseif r.kind == "hero" then clickHero(r.data) end
      return true
    end
  end
  return false
end

-- ---------------------------------------------------------------- paint (each block returns next y)
local text = Ash.text

local function drawPhase(x, y, right)
  local p = R.phase
  local spec = Ash.PHASE[p.name] or Ash.PHASE.FIGHT
  Ash.chipLabel(tostring(spec.glyph) .. " " .. p.name, x, y, 10, Ash.COL[spec.color] or Ash.COL.edge, "l")
  if p.left > 0 then text(Hud.clock(p.left), right, y, 13, Ash.COL.ink, "r")
  else text("+" .. Hud.clock(p.over), right, y, 13, Ash.COL.ash, "r") end
  if S.inbound > 0 then
    Ash.chipLabel("⇣ " .. math.floor(S.inbound) .. " inbound", right - Ash.textW(Hud.clock(p.left), 13) - 14, y, 9, Ash.COL.steam, "r")
  end
  y = y - 10
  Ash.meter(x, y, right, y + 3, p.frac, (p.left > 0) and Ash.COL.edge or Ash.COL.ash)
  y = y - 6
  if spec.sub then text(spec.sub, x, y - 8, 9, Ash.COL.ash, "l"); y = y - 12 end
  return y - 8
end

local function drawMarks(x, y, right)
  local mx = x + 14
  for _, mk in ipairs(S.marks) do
    local col, filled
    if mk.failed then col, filled = Ash.COL.bad, true
    elseif mk.done then col, filled = Ash.COL.good, true
    elseif mk.kind == "hero_recover" then col, filled = Ash.COL.bad, false
    else col, filled = Ash.COL.gold, mk.req end
    Ash.swatch(mx, y - 1, 9, Ash.with(col, filled and 0.9 or 0.8), filled)
    if mk.failed then text(Ash.GLYPH.failed, mx + 4.5, y - 1, 8, Ash.COL.ink, "c")
    elseif mk.done then text(Ash.GLYPH.done, mx + 4.5, y - 1, 8, Ash.COL.bg, "c") end
    if R.current and R.current.i == mk.i then Ash.outline(mx - 2, y - 3, mx + 11, y + 10, Ash.with(Ash.COL.ink, 0.8), 1) end
    mx = mx + 14
  end
  if R.current then
    text(Ash.fit(markLine(R.current), 10, right - mx - 6), mx + 6, y, 10, R.current.kind == "hero_recover" and Ash.COL.bad or Ash.COL.gold, "l")
  elseif S.requiredLeft == 0 and S.objectiveComplete then
    text("marks done", mx + 6, y, 10, Ash.COL.good, "l")
  end
  return y - 16
end

local function drawMission(x, y, right)
  text("MISSION", x, y, 9, Ash.COL.ash, "l")
  Ash.rule(x, y - 4, right, Ash.COL.gold, 0.35)
  y = y - 18
  text(Ash.fit(M.title or "", 12, right - x), x, y, 12, Ash.COL.gold, "l"); y = y - 16
  local col, glyph = Ash.COL.ink, Ash.GLYPH.objective
  if S.objectiveComplete then col, glyph = Ash.COL.good, Ash.GLYPH.done elseif S.objectiveFailed then col, glyph = Ash.COL.bad, Ash.GLYPH.failed end
  for i, line in ipairs(Hud.wrap(M.objective or "", 11, right - x - 14, 2)) do
    text((i == 1 and (glyph .. " ") or "   ") .. line, x, y, 11, col, "l"); y = y - 14
  end
  for _, g in ipairs(R.gauges) do
    y = y - 2
    if g.frac then
      -- the bar ends where its words begin (at least a third of the rail stays bar)
      local label = Ash.fit(g.label, 9, (right - x) * 0.6)
      Ash.meter(x + 14, y, math.max(x + 14 + (right - x) * 0.3, right - Ash.textW(label, 9) - 8), y + 5, math.max(0, math.min(1, g.frac)), g.col)
      text(label, right, y - 1, 9, g.col, "r")
    else
      text(Ash.fit(g.label, 9, right - x - 14), x + 14, y - 1, 9, g.col, "l")
    end
    y = y - 14
  end
  if #(S.marks or {}) > 0 then y = drawMarks(x, y - 4, right) end
  return y - 6
end

local function heroStateLabel(rec)
  local G = Ash.GLYPH
  if rec.state == "down" then return G.down .. " down", Ash.COL.bad end
  if rec.state == "lost" then return G.failed .. " lost", Ash.COL.muted end
  if rec.onPad then return G.onPad .. " on pad", Ash.COL.steam end
  return G.offPad .. " " .. (rec.dist and Hud.dist(rec.dist) or ""), (rec.dist and rec.dist > 1200) and Ash.COL.warn or Ash.COL.ink
end

local function drawCompany(x, y, right)
  local n = #H.list
  text("COMPANY", x, y, 9, Ash.COL.ash, "l")
  text(Hud.plural(n, "person", "people"), right, y, 9, Ash.COL.muted, "r")
  Ash.rule(x, y - 4, right, Ash.COL.edge, 0.35)
  y = y - 12
  if n == 0 then text("nobody on the manifest", x, y - 10, 10, Ash.COL.muted, "l"); return y - 24 end
  local rowH = 30
  local b = Hud.board()
  for _, rec in ipairs(H.list) do
    local y1, y2 = y - rowH, y
    local strip = (rec.state == "down" and Ash.COL.bad) or (rec.state == "lost" and Ash.COL.muted) or (rec.crit and Ash.COL.gold) or Ash.COL.edge
    Ash.rect(x, y1 + 2, right, y2 - 2, Ash.with(Ash.COL.bg, 0.55))
    Ash.rect(x, y1 + 2, x + 3, y2 - 2, Ash.with(strip, 0.95))
    text(Ash.fit(rec.name, 11, 120), x + 10, y2 - 13, 11, (rec.state == "alive") and Ash.COL.ink or Ash.COL.muted, "l")
    local chip = (rec.rank ~= "" and rec.rank or "Runner") .. " L" .. tostring(rec.level or 1)
    if rec.vet and rec.vet ~= "" and rec.vet ~= "green" then chip = chip .. " · " .. rec.vet end
    text(Ash.fit(chip, 8, 120), x + 10, y2 - 25, 8, Ash.COL.ash, "l")
    if rec.state == "alive" then
      local hp = math.max(0, math.min(1, rec.hp or 1))
      Ash.meter(x + 118, y2 - 11, x + 172, y2 - 7, hp, (hp > 0.6 and Ash.COL.good) or (hp > 0.3 and Ash.COL.warn) or Ash.COL.bad)
    end
    local lbl, col = heroStateLabel(rec)
    text(lbl, right - 6, y2 - 13, 10, col, "r")
    if rec.state == "alive" and not rec.onPad and rec.zone and rec.zone ~= "" and b then
      text(Ash.fit(b:label(rec.zone), 8, 90), right - 6, y2 - 25, 8, Ash.COL.muted, "r")
    end
    addRect(x, y1, right, y2, "hero", rec)
    y = y - rowH
  end
  return y - 12
end

local function drawPad(x, y, right)
  local b = Hud.board()
  text("PAD", x, y, 9, Ash.COL.ash, "l")
  text(Ash.fit((b and b.padId and b:label(b.padId)) or "the pad", 9, 150), right, y, 9, Ash.COL.steam, "r")
  Ash.rule(x, y - 4, right, Ash.COL.steam, 0.35)
  y = y - 18
  -- people dots: one per living person, filled when on the pad
  local e = R.extract
  local dx = x
  if e.alive > 0 then dx = x + Ash.dots(x, y - 2, e.alive, e.onPad, Ash.COL.steam, 8, 4) + 6 end
  text(string.format("%d / %d people · %d units aboard", e.onPad, e.alive, S.padUnits), dx, y, 10, Ash.COL.ink, "l")
  y = y - 14
  -- exposure: how much of us they see, where
  local ex = R.exposure
  Ash.rect(x, y - 2, x + 10, y + 8, { 0.12, 0.14, 0.13, 0.85 })
  Ash.hatchRect(x, y - 2, x + 10, y + 8, Ash.with(Ash.COL.bad, 0.3 + 0.7 * math.min(1, ex.best)), 3)
  Ash.outline(x, y - 2, x + 10, y + 8, Ash.with(Ash.COL.bad, 0.6), 1)
  text(Ash.fit("seen · " .. ex.level .. (ex.where and (" · " .. ex.where) or ""), 10, right - x - 16), x + 16, y, 10, ex.col, "l")
  y = y - 14
  if S.padEnemy > 0 then
    text(string.format("%s %d enemy on the pad", Ash.GLYPH.exposed, S.padEnemy), x, y, 10, Ash.COL.bad, "l")
    y = y - 14
  end
  if not Hud.begun() then
    text("paused — Enter begins", x, y, 10, Ash.COL.steam, "l")
    return y - 18
  end
  y = y - 4
  local fill = (e.state == "empty" and Ash.COL.bad) or (e.state == "short" and Ash.COL.warn) or Ash.COL.steam
  local subCol = (e.state == "empty" and Ash.COL.bad) or Ash.COL.warn
  local h = e.sub and 42 or 30
  Ash.actionRow(x, y - h, right, y, { fill = fill, focused = e.state ~= "empty" })
  text(e.label, x + 12, y - 19, 12, (e.state == "empty") and Ash.COL.bad or Ash.COL.ink, "l")
  if e.sub then text(Ash.fit(e.sub, 9, right - x - 16), x + 12, y - 33, 9, subCol, "l") end
  addRect(x, y - h, right, y, "extract", nil)
  y = y - h - 8
  if #e.left > 0 then
    text("LEFT IF YOU LIFT", x, y, 8, Ash.COL.ash, "l"); y = y - 12
    for i = 1, math.min(4, #e.left) do text(Ash.fit(e.left[i][1], 10, right - x), x, y, 10, e.left[i][2], "l"); y = y - 12 end
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

local BLOCKS = { { "phase", drawPhase, 30 }, { "mission", drawMission, 60 }, { "company", drawCompany, 40 }, { "pad", drawPad, 60 } }

local function glReset()
  local vx, vy = Spring.GetViewGeometry()
  if vx and vx > 32 then vsx, vsy = vx, vy end
  if gl.Scissor then gl.Scissor(false) end
  if gl.DepthTest then gl.DepthTest(false) end
  if gl.Blending then gl.Blending(true) end
  gl.Color(1, 1, 1, 1)
end

local function blocks(top, x, inner)
  local y = top - 8
  for i = 1, #BLOCKS do local blk = BLOCKS[i]; y = guard(blk[1], blk[2], x, y, inner) or (y - blk[3]) end
  return math.max(24, y)
end

local PANEL = { accent = Ash and Ash.COL.edge }

function widget:DrawScreen()
  if Spring.IsGUIHidden() or not Ash or not M.seed or not R.phase then return end
  pcall(glReset)   -- named functions throughout: the rail draws every frame and makes no closures
  UI.n = 0
  if S.sortieOver or Hud.modal() then return end
  local right = vsx - 10
  local left = right - W
  local top = vsy - TOP_GAP
  local x, inner = left + 12, right - 12
  -- the panel's height is last frame's content height (content changes slowly); when it changed,
  -- redraw the panel at the new size and the content once more
  local bottom = UI.lastBottom or (top - 320)
  Ash.panel(left, bottom - 10, right, top + 10, PANEL)
  local y = blocks(top, x, inner)
  if math.abs(y - bottom) > 2 then
    UI.n = 0
    Ash.panel(left, y - 10, right, top + 10, PANEL)
    y = blocks(top, x, inner)
  end
  UI.lastBottom = y
  gl.Color(1, 1, 1, 1)
end
