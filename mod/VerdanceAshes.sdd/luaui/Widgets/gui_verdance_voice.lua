if not VFS.Include("LuaRules/Configs/va_active.lua") then return false end -- plain BAR unless the hub launched this
local widget = widget

function widget:GetInfo()
  return {
    -- The real widgetHandler (BAR grants it to game-archive widgets that ask): the proxy's
    -- RegisterGlobal takes (name, value), so RegisterGlobal(widget, name, fn) registered nothing.
    handler = true,
    name = "Verdance Voice",
    desc = "One voice stack for everyone: Ketha, Yeva, rank-ups, inbound warnings. Framed lines under the Tnb bar, nothing centre-screen, no map pings.",
    author = "Verdance",
    date = "2026-10-20",
    license = "GPL v2 or later",
    layer = 11,
    enabled = true,
  }
end

-- Pass seven. Other widgets call WG.vaVoice.say(speaker, text, seconds, accentColour).
-- Synced beats arrive through VerdanceBeat / VerdanceVetRank. /valog prints the field log.

local Hud = VFS.Include("luaui/Include/va_hud.lua")
local Ash = Hud.Ash
local playUi = Hud.sound

local vsx, vsy = Spring.GetViewGeometry()
local BASE_Y = 150
local STEP = 46
local SLOTS = 3
local queue = {}      -- waiting { speaker, text, seconds, accent, ambient }
local live = {}       -- showing { ..., until_ }
local log = {}
local lastAmbient = -999

-- tag: a key a later clear(tag) takes the line down by (a prompt the player has just acted on).
-- boxed: the line is a prompt and gets a border, so a prompt differs in shape as well as colour.
local function say(speaker, text, seconds, accent, ambient, tag, boxed)
  text = tostring(text or "")
  if text == "" then return end
  speaker = tostring(speaker or "")
  log[#log + 1] = { speaker = speaker, text = text }
  Spring.Echo("VA_UI_SAY " .. (speaker ~= "" and (speaker .. ": ") or "") .. text)
  if #log > 80 then table.remove(log, 1) end
  local now = Spring.GetGameSeconds() or 0
  if ambient and (now - lastAmbient < 15 or #queue > 0 or #live >= SLOTS) then return end
  if ambient then lastAmbient = now end
  local entry = { speaker = speaker, text = text, seconds = tonumber(seconds) or 7, accent = accent, ambient = ambient, tag = tag, boxed = boxed }
  if ambient then queue[#queue + 1] = entry else table.insert(queue, 1, entry) end
end

-- Take a tagged line down: dropped if it is still waiting, faded out if it is showing.
local function clear(tag)
  if not tag or tag == "" then return end
  for i = #queue, 1, -1 do if queue[i].tag == tag then table.remove(queue, i) end end
  local now = Spring.GetGameSeconds() or 0
  for _, e in ipairs(live) do
    if e.tag == tag and e.until_ > now + 0.75 then e.until_ = now + 0.75 end
  end
end

-- A beat's bark style: "priority|accent|tag" (beats.lua barkStyle). An ambient bark may be dropped
-- when the stack is busy; a line or a prompt never is. A prompt (the company asking the player for
-- a control) wears the pad's blue, so it never reads as story.
local function barkStyle(d)
  local priority, accent, tag = tostring(d or ""):match("^([^|]*)|([^|]*)|(.*)$")
  priority = priority or "ambient"
  local col = Ash and accent and accent ~= "" and Ash.COL[accent] or nil
  if not col and priority == "prompt" and Ash then col = Ash.COL.steam end
  return priority ~= "line" and priority ~= "prompt", col, (tag ~= "" and tag) or nil, priority == "prompt"
end

local function promote()
  local now = Spring.GetGameSeconds() or 0
  -- expire
  local keep = {}
  for i = 1, #live do
    if live[i].until_ > now then keep[#keep + 1] = live[i] end
  end
  live = keep
  while #live < SLOTS and #queue > 0 do
    local e = table.remove(queue, 1)
    e.until_ = now + e.seconds
    live[#live + 1] = e
    if e.speaker ~= "" then playUi("beep4", 0.4) end
  end
end

function widget:Initialize()
  if WG then
    WG.vaVoice = { say = say, clear = clear }
    WG.vaVoiceOwner = "voice"
  end
  pcall(function()
    widgetHandler:RegisterGlobal(widget, "VerdanceBeat", function(kind, a, b, c, d) widget:VerdanceBeat(kind, a, b, c, d) end)
    widgetHandler:RegisterGlobal(widget, "VerdanceVetRank", function(unitID, prev, rank, x, y, z, mults) widget:VerdanceVetRank(unitID, prev, rank) end)
  end)
end

function widget:Shutdown()
  pcall(function()
    widgetHandler:DeregisterGlobal(widget, "VerdanceBeat")
    widgetHandler:DeregisterGlobal(widget, "VerdanceVetRank")
  end)
  if WG then WG.vaVoice = nil; WG.vaVoiceOwner = nil end
end

function widget:ViewResize(x, y) vsx, vsy = x, y end

-- Beats from the synced side (beats.lua and the gadgets' barks), by kind:
--   bark (speaker, text, seconds, "priority|accent|tag") · clear_bark (tag) · sound (file, volume)
--   wave_warning (.., .., .., where) · narrative (x, z, "title|body|radius|seconds")
--   marker (x, y, z, text): said, never pinged · crew_ready / field_recruit (.., .., line)
--   field_mark (id, x, z, "shape|radius|seconds") / clear_mark (id): rings on the ground, drawn by
--   the field marks widget (WG.vaFieldMarks); this widget holds the one VerdanceBeat global
function widget:VerdanceBeat(kind, a, b, c, d)
  if kind == "bark" then
    local ambient, accent, tag, boxed = barkStyle(d)
    say(a, b, c, accent, ambient, tag, boxed)
  elseif kind == "clear_bark" then
    clear(tostring(a or ""))
  elseif kind == "field_mark" or kind == "clear_mark" then
    if WG and WG.vaFieldMarks then WG.vaFieldMarks(kind, a, b, c, d) end
  elseif kind == "sound" then
    playUi(a, tonumber(b) or 1.0)
  elseif kind == "wave_warning" then
    say("", "Inbound: " .. tostring(d or "enemy reinforcements"), 6, Ash and Ash.COL.warn)
    playUi("warning2", 0.7)
  elseif kind == "narrative" then
    local title, body, seconds = tostring(c or ""), tostring(d or ""), 6
    if type(c) == "string" and c:find("|", 1, true) then
      local parts = {}
      for part in string.gmatch(c, "[^|]+") do parts[#parts + 1] = part end
      title = parts[1] or title
      body = (parts[2] and parts[2] ~= "") and parts[2] or body
      seconds = tonumber(parts[4]) or seconds
    end
    if body ~= "" then say(title, body, seconds) end
  elseif kind == "marker" then
    if type(d) == "string" and d ~= "" then say("", d, 6, Ash and Ash.COL.gold) end
  elseif kind == "crew_ready" or kind == "field_recruit" then
    if type(d) == "string" and d ~= "" then say("", d, 6) elseif type(c) == "string" and c ~= "" then say("", c, 6) end
  end
end

local function unitLabel(unitID)
  local hero = Spring.GetUnitRulesParam(unitID, "va_hero_name")
  if type(hero) == "string" and hero ~= "" then return hero end
  local dID = Spring.GetUnitDefID(unitID)
  local ud = dID and UnitDefs[dID]
  return (ud and (ud.humanName or ud.name)) or ("Unit " .. tostring(unitID))
end

function widget:VerdanceVetRank(unitID, prev, rank)
  local accent = Ash and ((rank == "cracked" and Ash.COL.gold) or (rank == "hardened" and Ash.COL.steam) or Ash.COL.good)
  say("", unitLabel(unitID) .. " · " .. tostring(rank):upper(), 4, accent)
  playUi("beep6", 0.7)
end

function widget:TextCommand(cmd)
  if cmd == "valog" then
    Spring.Echo("Company field log:")
    for _, e in ipairs(log) do Spring.Echo((e.speaker ~= "" and (e.speaker .. ": ") or "") .. e.text) end
    return true
  end
  return false
end

function widget:DrawScreen()
  if Spring.IsGUIHidden() then return end
  promote()
  if #live == 0 or not Ash then return end
  -- the exfil / infil screens own the whole frame while modal
  if WG and WG.vaExfilModal then return end
  local now = Spring.GetGameSeconds() or 0
  local cx = vsx * 0.5
  local w = math.min(560, vsx * 0.55)
  local y = vsy - BASE_Y
  for i = 1, #live do
    local e = live[i]
    local a = math.min(1, (e.until_ - now) / 0.75)
    Ash.voiceBlock(cx, y, w, e.speaker, e.text, a, e.accent)
    if e.boxed then Ash.outline(cx - w / 2, y - 21, cx + w / 2, y + 21, Ash.with(e.accent or Ash.COL.steam, 0.7 * a), 1) end
    y = y + STEP
  end
  gl.Color(1, 1, 1, 1)
end
