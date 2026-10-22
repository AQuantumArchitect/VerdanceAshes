if not VFS.Include("LuaRules/Configs/va_active.lua") then return false end -- plain BAR unless the hub launched this
local widget = widget

function widget:GetInfo()
  return {
    name = "Verdance Proxy Story",
    desc = "Quantum-graph campaign story hearth — three scars, bark strip, arc scoreboard",
    author = "Grok / Luke Spooner",
    date = "2026-07-26",
    license = "GPL v2 or later",
    layer = 6,
    enabled = true,
  }
end

local story = nil
-- Hidden by default during live play: the file is often a full proxy-sim archive
-- (every chapter checked). Show with /vastoryshow; hide with /vastoryhide.
local visible = false
local page = 1 -- 1 overview, 2+ chapters
local barkIndex = 1
local barkUntil = 0
local vsx, vsy = Spring.GetViewGeometry()
local liveMissionNumber = 1

-- Ash Console (docs/UI_ASH_CONSOLE.md)
local COL = {
  panel = { 0.031, 0.063, 0.047, 0.90 },
  edge = { 0.239, 0.561, 0.333, 0.75 },
  title = { 0.831, 0.769, 0.604 },
  text = { 0.933, 0.965, 0.933 },
  dim = { 0.490, 0.584, 0.518 },
  steam = { 0.494, 0.784, 1.0 },
  good = { 0.490, 1.0, 0.541 },
  bad = { 1.0, 0.490, 0.490 },
  gold = { 0.831, 0.769, 0.604 },
  warn = { 0.878, 0.627, 0.376 },
}
do
  local ok, Ash = pcall(VFS.Include, "luaui/Include/va_ash_tokens.lua")
  if not ok or type(Ash) ~= "table" then
    ok, Ash = pcall(VFS.Include, "LuaUI/Include/va_ash_tokens.lua")
  end
  if ok and type(Ash) == "table" and Ash.COL then
    COL.panel = Ash.COL.panel
    COL.edge = { Ash.COL.edge[1], Ash.COL.edge[2], Ash.COL.edge[3], 0.75 }
    COL.title = Ash.COL.gold
    COL.text = Ash.COL.ink
    COL.dim = Ash.COL.muted
    COL.steam = Ash.COL.steam
    COL.good = Ash.COL.good
    COL.bad = Ash.COL.bad
    COL.gold = Ash.COL.gold
    COL.warn = Ash.COL.warn
  end
end

local function say(s)
  Spring.Echo("[VA_PROXY_STORY] " .. tostring(s))
end

local function readStory()
  local ok, data = pcall(VFS.Include, "singleplayer/verdance_ashes/generated/proxy_story_current.lua")
  if ok and type(data) == "table" then
    return data
  end
  return nil
end

local function chapterCount()
  if not story or type(story.chapters) ~= "table" then return 0 end
  return #story.chapters
end

local function maxPage()
  return 1 + chapterCount()
end

local function readLiveMissionNumber()
  local ok, data = pcall(VFS.Include, "singleplayer/verdance_ashes/generated/va_current.lua")
  if ok and type(data) == "table" and data.missionNumber then
    return tonumber(data.missionNumber) or 1
  end
  return 1
end

function widget:Initialize()
  story = readStory()
  liveMissionNumber = readLiveMissionNumber()
  if story then
    say("loaded story agent=" .. tostring(story.agent) .. " cleared=" .. tostring(story.cleared)
      .. " missions=" .. tostring(story.missions)
      .. " (panel hidden by default — /vastoryshow). liveMission=" .. tostring(liveMissionNumber))
  else
    say("no proxy_story_current.lua yet — run RUN_CAMPAIGN from design forge")
  end
  vsx, vsy = Spring.GetViewGeometry()
end

function widget:ViewResize(x, y)
  vsx, vsy = x, y
end

function widget:TextCommand(command)
  if not command then return false end
  local cmd = command:match("^(%S+)")
  if not cmd then return false end
  if cmd == "vastory" then
    story = readStory()
    visible = true
    page = 1
    say(story and ("story reloaded: " .. tostring(story.title)) or "no story file")
    return true
  end
  if cmd == "vastoryhide" then
    visible = false
    return true
  end
  if cmd == "vastoryshow" then
    visible = true
    return true
  end
  if cmd == "vastorynext" then
    page = math.min(maxPage(), page + 1)
    return true
  end
  if cmd == "vastoryprev" then
    page = math.max(1, page - 1)
    return true
  end
  if cmd == "vastorygoto" then
    local n = tonumber(command:match("vastorygoto%s+(%d+)"))
    if n then page = math.max(1, math.min(maxPage(), n)) end
    return true
  end
  return false
end

local function drawBox(x, y, w, h, edgeA)
  gl.Color(COL.panel[1], COL.panel[2], COL.panel[3], COL.panel[4])
  gl.Rect(x, y, x + w, y + h)
  -- left accent strip (Ash Console chrome)
  gl.Color(COL.edge[1], COL.edge[2], COL.edge[3], edgeA or COL.edge[4] or 0.75)
  gl.Rect(x, y, x + 3, y + h)
  gl.LineWidth(1.25)
  gl.BeginEnd(GL.LINE_LOOP, function()
    gl.Vertex(x, y)
    gl.Vertex(x + w, y)
    gl.Vertex(x + w, y + h)
    gl.Vertex(x, y + h)
  end)
  gl.LineWidth(1)
end

local function text(x, y, s, col, size)
  col = col or COL.text
  gl.Color(col[1], col[2], col[3], col[4] or 1)
  gl.Text(tostring(s or ""), x, y, size or 14, "o")
end

local function wrapPush(lines, s, maxLen)
  s = tostring(s or "")
  while #s > maxLen do
    local cut = s:sub(1, maxLen)
    local sp = cut:match(".*()%s")
    if not sp or sp < maxLen * 0.5 then sp = maxLen end
    lines[#lines + 1] = s:sub(1, sp)
    s = s:sub(sp + 1)
  end
  if s ~= "" then lines[#lines + 1] = s end
end

function widget:DrawScreen()
  if not visible or not story then return end

  local w = math.min(560, vsx * 0.44)
  local h = math.min(400, vsy * 0.55)
  local x = vsx - w - 16
  local y = vsy - h - 72

  drawBox(x, y, w, h)

  local pad = 14
  local cy = y + h - pad - 16
  text(x + pad, cy, "VERDANCE · STORY ARCHIVE (not live progress)", COL.steam, 12)
  cy = cy - 18
  text(x + pad, cy, tostring(story.title or "Verdance"), COL.title, 15)
  cy = cy - 16
  if story.tagline and story.tagline ~= "" then
    text(x + pad, cy, tostring(story.tagline), COL.gold, 11)
    cy = cy - 16
  end

  local badge = string.format(
    "YOU are mission %s  ·  archive agent %s seed %s",
    tostring(liveMissionNumber),
    tostring(story.agent or "?"),
    tostring(story.seed or "?")
  )
  text(x + pad, cy, badge, COL.dim, 11)
  cy = cy - 16
  text(x + pad, cy, "Checks below = proxy sim lore, not your campaign clears.", COL.warn, 11)
  cy = cy - 18

  local body = {}
  if page == 1 then
    wrapPush(body, story.arcBlurb or "", 64)
    body[#body + 1] = ""
    if type(story.arcs) == "table" and #story.arcs > 0 then
      body[#body + 1] = "ARCS (proxy archive)"
      for _, a in ipairs(story.arcs) do
        -- Live progress: arc 1 = missions 1-5, arc 2 = 6-10, arc 3 = 11-15.
        local aid = tonumber(a.id) or 0
        local liveWins = 0
        if liveMissionNumber > (aid * 5) then
          liveWins = tonumber(a.total) or 5
        elseif liveMissionNumber > ((aid - 1) * 5) then
          liveWins = liveMissionNumber - ((aid - 1) * 5) - 1
        end
        local total = tonumber(a.total) or 5
        local mark = (liveWins >= total) and "✓" or "·"
        body[#body + 1] = string.format(
          "  %s Arc %s — %s  live %s/%s  (archive %s/%s)",
          mark,
          tostring(a.id or "?"),
          tostring(a.title or ""),
          tostring(math.max(0, liveWins)),
          tostring(total),
          tostring(a.wins or 0),
          tostring(total)
        )
        if a.blurb and a.blurb ~= "" then
          wrapPush(body, "      " .. tostring(a.blurb), 62)
        end
      end
      body[#body + 1] = ""
    end
    body[#body + 1] = "CHAPTERS (· = ahead of you, > = current, archive ✓ kept as lore)"
    if type(story.chapters) == "table" then
      for i, ch in ipairs(story.chapters) do
        local mark = "·"
        if i < liveMissionNumber then mark = ">"
        elseif i == liveMissionNumber then mark = ">"
        end
        if i < liveMissionNumber then mark = "✓" end
        if i == liveMissionNumber then mark = ">" end
        local arc = ch.arc and ("A" .. tostring(ch.arc)) or ""
        body[#body + 1] = string.format(
          "  %s %2d. [%s] %s",
          mark, i, arc, tostring(ch.title or ch.id)
        )
      end
    end
    body[#body + 1] = ""
    body[#body + 1] = "/vastorynext · /vastoryprev · /vastoryhide · /vastorygoto N"
  else
    local ch = story.chapters and story.chapters[page - 1]
    if ch then
      body[#body + 1] = tostring(ch.title or ch.id)
      body[#body + 1] = string.format(
        "%s · %s · arc %s · %s",
        tostring(ch.mapName or ""),
        tostring(ch.kind or ""),
        tostring(ch.arc or "?"),
        tostring(ch.verdict or "")
      )
      body[#body + 1] = ""
      if type(ch.beats) == "table" then
        for _, beat in ipairs(ch.beats) do
          wrapPush(body, "• " .. tostring(beat), 62)
        end
      end
      body[#body + 1] = ""
      wrapPush(body, tostring(ch.verdictLine or ""):gsub("%*", ""), 62)
    end
  end

  for _, line in ipairs(body) do
    if cy < y + 38 then break end
    local col = COL.text
    if line:match("^%s*✓") or line:match("CLEARED") then col = COL.good end
    if line:match("^ARCS") or line:match("^CHAPTERS") then col = COL.steam end
    text(x + pad, cy, line, col, 11)
    cy = cy - 14
  end

  text(x + pad, y + 12, string.format("page %d / %d", page, maxPage()), COL.dim, 11)

  -- rotating bark strip
  if type(story.barks) == "table" and #story.barks > 0 then
    local now = Spring.GetGameFrame and Spring.GetGameFrame() or 0
    if now > barkUntil then
      barkIndex = (barkIndex % #story.barks) + 1
      barkUntil = now + 150
    end
    local bark = story.barks[barkIndex]
    if bark then
      local bw = math.min(680, vsx * 0.58)
      local bx = (vsx - bw) / 2
      local by = 44
      drawBox(bx, by, bw, 48, 0.85)
      text(bx + 14, by + 28, string.upper(tostring(bark.speaker or "voice")), COL.steam, 11)
      text(bx + 14, by + 10, tostring(bark.text or ""), COL.text, 13)
    end
  end
end

function widget:Shutdown()
end
