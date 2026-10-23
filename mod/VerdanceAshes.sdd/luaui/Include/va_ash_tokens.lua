-- Ash Console tokens + draw helpers for Verdance BAR widgets (pass seven).
-- Keep in sync with docs/UI_ASH_CONSOLE.md and app/showoff/index.html :root.
-- No verdict copy lives here: Lua reports facts, Python interprets.

local Ash = {}

-- RGB 0–1 tables (r, g, b [, a])
Ash.COL = {
  bg     = { 0.016, 0.035, 0.027, 1.0 },
  panel  = { 0.031, 0.063, 0.047, 0.90 },
  ink    = { 0.933, 0.965, 0.933, 1.0 },
  muted  = { 0.490, 0.584, 0.518, 1.0 },
  ash    = { 0.604, 0.545, 0.447, 1.0 },
  edge   = { 0.239, 0.561, 0.333, 1.0 },
  gold   = { 0.831, 0.769, 0.604, 1.0 },
  ketha  = { 0.651, 0.820, 0.651, 1.0 },
  steam  = { 0.494, 0.784, 1.000, 1.0 },
  good   = { 0.490, 1.000, 0.541, 1.0 },
  warn   = { 0.878, 0.627, 0.376, 1.0 },
  bad    = { 1.000, 0.490, 0.490, 1.0 },
  tnb    = { 0.788, 0.627, 1.000, 1.0 },
  pad = { 0.494, 0.784, 1.000, 0.75 },
  objective = { 0.878, 0.627, 0.376, 0.75 },
}

-- The ONE faction palette (hub :root --f-*). A faction colour on any board means
-- "the company believes they hold it", never "they do".
Ash.FACTION = {
  ashwalkers = { 0.239, 0.561, 0.333, 1.0 },  -- edge: ours
  armada     = { 0.353, 0.647, 1.000, 1.0 },
  cortex     = { 1.000, 0.384, 0.420, 1.0 },
  nullmercs  = { 0.314, 0.929, 0.549, 1.0 },
  legion     = { 0.314, 0.929, 0.549, 1.0 },
  wild       = { 0.961, 0.831, 0.278, 1.0 },
  raptors    = { 0.961, 0.831, 0.278, 1.0 },
  raptor     = { 0.961, 0.831, 0.278, 1.0 },
  scavengers = { 0.757, 0.525, 1.000, 1.0 },
}
function Ash.faction(name)
  return Ash.FACTION[tostring(name or ""):lower()] or Ash.COL.warn
end

-- Phase chips (sidebar + clock). Never bad: the clock never ends the game.
Ash.PHASE = {
  APPROACH = { glyph = "▸", color = "edge" },
  FIGHT    = { glyph = "✦", color = "warn" },
  MARKS    = { glyph = "◆", color = "gold" },
  EXTRACT  = { glyph = "⌂", color = "steam", sub = "board resolved — your call" },
  OVERTIME = { glyph = "∞", color = "ash", sub = "clock out — the map is awake" },
}

-- Glyph vocabulary (one meaning each, everywhere: minimap, sidebar, infil, exfil, hub)
Ash.GLYPH = {
  pad = "△", doorHeld = "■", doorShut = "□", objective = "◆", markReq = "◆", markOpt = "◇", done = "✓", failed = "✗",
  onPad = "●", offPad = "○", down = "✚", left = "⚑", holding = "■", unknown = "?",
  exposed = "◉", contradictedHeld = "✗", contradictedEmpty = "○",
}

function Ash.color(name, alpha)
  local c = Ash.COL[name] or Ash.COL.ink
  if alpha ~= nil then return { c[1], c[2], c[3], alpha } end
  return c
end

function Ash.with(col, alpha)
  col = col or Ash.COL.ink
  return { col[1], col[2], col[3], alpha }
end

function Ash.setColor(col)
  if not col then gl.Color(1, 1, 1, 1); return end
  gl.Color(col[1], col[2], col[3], col[4] or 1)
end

function Ash.text(str, x, y, size, col, align)
  Ash.setColor(col or Ash.COL.ink)
  gl.Text(tostring(str or ""), x, y, size or 12, (align or "c") .. "o")
end

function Ash.textW(str, size)
  return gl.GetTextWidth(tostring(str or "")) * (size or 12)
end

-- Clip a string to a pixel width (ellipsis).
function Ash.fit(str, size, maxW)
  str = tostring(str or "")
  if Ash.textW(str, size) <= maxW then return str end
  local function chop(s)
    local n = #s - 1
    while n > 0 and s:byte(n + 1) >= 0x80 and s:byte(n + 1) < 0xC0 do n = n - 1 end
    return s:sub(1, n)
  end
  while #str > 1 and Ash.textW(str .. "…", size) > maxW do str = chop(str) end
  return str .. "…"
end

function Ash.rect(x1, y1, x2, y2, col)
  Ash.setColor(col)
  gl.Rect(x1, y1, x2, y2)
end

function Ash.outline(x1, y1, x2, y2, col, width)
  Ash.setColor(col)
  gl.LineWidth(width or 1)
  gl.BeginEnd(GL.LINE_LOOP, function()
    gl.Vertex(x1, y1); gl.Vertex(x2, y1); gl.Vertex(x2, y2); gl.Vertex(x1, y2)
  end)
  gl.LineWidth(1)
end

--- Filled panel with edge border and left accent strip (Ash Console chrome).
function Ash.panel(x1, y1, x2, y2, opts)
  opts = opts or {}
  local fill = opts.fill or Ash.COL.panel
  local edge = opts.edge or Ash.COL.edge
  Ash.rect(x1, y1, x2, y2, fill)
  if opts.accent then
    Ash.rect(x1, y1, x1 + 3, y2, Ash.with(opts.accent, opts.accent[4] or 0.85))
  end
  Ash.outline(x1, y1, x2, y2, Ash.with(edge, opts.edgeA or 0.55), 1.25)
end

--- Framed voice block (matches hub .voice). speaker may be "" for system lines.
function Ash.voiceBlock(cx, y, maxW, speaker, line, alpha, accent)
  alpha = alpha or 1
  local w = maxW or 520
  local x1, x2 = cx - w / 2, cx + w / 2
  local h = 42
  local y1, y2 = y - h / 2, y + h / 2
  Ash.rect(x1, y1, x2, y2, Ash.with(Ash.COL.panel, 0.88 * alpha))
  local acc = accent or Ash.COL.edge
  Ash.rect(x1, y1, x1 + 3, y2, Ash.with(acc, 0.9 * alpha))
  local textY = y + 4
  if speaker and speaker ~= "" then
    Ash.text(string.upper(tostring(speaker)), cx, y + 12, 10, Ash.with(acc, alpha), "c")
    textY = y - 6
  end
  local body = tostring(line or "")
  if speaker and speaker ~= "" then body = '"' .. body .. '"' end
  Ash.text(body, cx, textY, 13, Ash.with(Ash.COL.gold, alpha), "c")
  return h
end

--- Small label chip: dark fill, coloured text, 1px border. Returns width.
function Ash.chipLabel(str, x, y, size, col, align)
  size = size or 11
  col = col or Ash.COL.muted
  str = tostring(str or "")
  local w = Ash.textW(str, size) + 12
  local h = size + 6
  local x1
  if align == "l" then x1 = x elseif align == "r" then x1 = x - w else x1 = x - w / 2 end
  local y1 = y - 3
  Ash.rect(x1, y1, x1 + w, y1 + h, Ash.with(Ash.COL.bg, 0.78))
  Ash.outline(x1, y1, x1 + w, y1 + h, Ash.with(col, 0.55), 1)
  Ash.text(str, x1 + 6, y, size, col, "l")
  return w
end

--- Horizontal meter: track + fill (frac 0..1), optional tick at `mark` (0..1).
function Ash.meter(x1, y1, x2, y2, frac, col, mark)
  frac = math.max(0, math.min(1, tonumber(frac) or 0))
  Ash.rect(x1, y1, x2, y2, { 0.10, 0.13, 0.11, 0.9 })
  if frac > 0 then Ash.rect(x1, y1, x1 + (x2 - x1) * frac, y2, Ash.with(col, 0.92)) end
  if mark then
    local mx = x1 + (x2 - x1) * math.max(0, math.min(1, mark))
    Ash.rect(mx - 1, y1 - 2, mx + 1, y2 + 2, Ash.with(Ash.COL.ink, 0.8))
  end
  Ash.outline(x1, y1, x2, y2, Ash.with(Ash.COL.edge, 0.35), 1)
end

--- Row of dots: n total, k filled. Returns width.
function Ash.dots(x, y, n, k, col, size, gap)
  size = size or 7; gap = gap or 4
  for i = 1, n do
    local x1 = x + (i - 1) * (size + gap)
    if i <= k then
      Ash.rect(x1, y, x1 + size, y + size, Ash.with(col, 0.95))
    else
      Ash.outline(x1, y, x1 + size, y + size, Ash.with(col, 0.7), 1)
    end
  end
  return n * (size + gap)
end

--- Square swatch (filled or outline). Used for belief / faction / mark legends.
function Ash.swatch(x, y, size, col, filled)
  if filled then Ash.rect(x, y, x + size, y + size, col) else Ash.outline(x, y, x + size, y + size, col, 1) end
end

--- Diagonal hatch (lines, not fill) inside a screen rect. Exposure only: it never
-- shares an encoding with belief fill.
function Ash.hatchRect(x1, y1, x2, y2, col, step)
  if x2 <= x1 or y2 <= y1 then return end
  step = step or 4
  Ash.setColor(col or Ash.COL.bad)
  gl.LineWidth(1)
  local w, h = x2 - x1, y2 - y1
  gl.BeginEnd(GL.LINES, function()
    local d = step
    while d < w + h do
      local ax, ay = x1 + d, y1
      if ax > x2 then ax = x2; ay = y1 + (d - w) end
      local bx, by = x1, y1 + d
      if by > y2 then by = y2; bx = x1 + (d - h) end
      gl.Vertex(ax, ay); gl.Vertex(bx, by)
      d = d + step
    end
  end)
end

--- Sparse dot grid inside a rect: "nobody looked". Distinct from hatch (exposure).
function Ash.dotRect(x1, y1, x2, y2, col, step)
  if x2 <= x1 or y2 <= y1 then return end
  step = step or 5
  Ash.setColor(col or Ash.COL.ash)
  gl.PointSize(1.5)
  gl.BeginEnd(GL.POINTS, function()
    local yy = y1 + step * 0.5
    while yy < y2 do
      local xx = x1 + step * 0.5
      while xx < x2 do gl.Vertex(xx, yy); xx = xx + step end
      yy = yy + step
    end
  end)
  gl.PointSize(1)
end

--- Dashed rectangle outline (stale belief).
function Ash.dashedOutline(x1, y1, x2, y2, col, dash)
  dash = dash or 3
  Ash.setColor(col)
  gl.LineWidth(1)
  gl.BeginEnd(GL.LINES, function()
    local x = x1
    while x < x2 do gl.Vertex(x, y1); gl.Vertex(math.min(x2, x + dash), y1); gl.Vertex(x, y2); gl.Vertex(math.min(x2, x + dash), y2); x = x + dash * 2 end
    local y = y1
    while y < y2 do gl.Vertex(x1, y); gl.Vertex(x1, math.min(y2, y + dash)); gl.Vertex(x2, y); gl.Vertex(x2, math.min(y2, y + dash)); y = y + dash * 2 end
  end)
end

--- Soft vignette fill behind a modal card.
function Ash.scrim(x1, y1, x2, y2, alpha)
  Ash.rect(x1, y1, x2, y2, Ash.with(Ash.COL.bg, alpha or 0.72))
end

--- Accent hairline under a kicker.
function Ash.rule(x1, y, x2, col, alpha)
  Ash.rect(x1, y, x2, y + 1, Ash.with(col or Ash.COL.gold, alpha or 0.55))
end

--- Primary action row (EXTRACT / confirm): filled with left rail.
function Ash.actionRow(x1, y1, x2, y2, opts)
  opts = opts or {}
  local fill = opts.fill or Ash.COL.steam
  local focused = opts.focused == true
  Ash.rect(x1, y1, x2, y2, Ash.with(fill, focused and 0.32 or 0.16))
  Ash.rect(x1, y1, x1 + 4, y2, Ash.with(fill, focused and 0.95 or 0.70))
  Ash.rect(x1, y2 - 1, x2, y2, Ash.with(fill, focused and 0.55 or 0.28))
  Ash.rect(x1, y1, x2, y1 + 1, Ash.with(Ash.COL.edge, 0.35))
end

--- Indeterminate progress sweep.
function Ash.progressSweep(x1, y1, x2, y2, col, t)
  local c = col or Ash.COL.steam
  local w = math.max(1, x2 - x1)
  Ash.rect(x1, y1, x2, y2, Ash.with(c, 0.16))
  local pulse = (tonumber(t) or 0) % 1
  local sweep = w * 0.28
  local sx1 = x1 + pulse * (w - sweep)
  Ash.rect(sx1, y1, sx1 + sweep, y2, Ash.with(c, 0.88))
end

--- Screen-space circle outline.
function Ash.ring(cx, cy, r, col, width, segs)
  segs = segs or 32
  Ash.setColor(col)
  gl.LineWidth(width or 1.5)
  gl.BeginEnd(GL.LINE_LOOP, function()
    for i = 0, segs - 1 do
      local a = (i / segs) * math.pi * 2
      gl.Vertex(cx + math.cos(a) * r, cy + math.sin(a) * r)
    end
  end)
  gl.LineWidth(1)
end

function Ash.inRect(x, y, r)
  return r ~= nil and x >= r[1] and x <= r[3] and y >= r[2] and y <= r[4]
end

return Ash
