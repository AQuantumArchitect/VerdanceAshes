-- Ash Console tokens + draw helpers for Verdance BAR widgets.
-- Keep in sync with docs/UI_ASH_CONSOLE.md and app/showoff/index.html :root.
-- Also keep verdict copy in sync with tools/match_credit_v1.py _HEADLINES.

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
  -- map markers
  deploy = { 0.490, 1.000, 0.541, 0.75 },
  objective = { 0.878, 0.627, 0.376, 0.75 },
  extract = { 0.494, 0.784, 1.000, 0.75 },
}

-- Display copy — sync with match_credit_v1._HEADLINES
Ash.VERDICT = {
  victory = {
    banner = "SECURED",
    headline = "Secured.",
    color = "good",
  },
  partial = {
    banner = "HINGE",
    headline = "Hinge. Not a win.",
    color = "warn",
  },
  defeat = {
    banner = "FIELD COSTS",
    headline = "Field costs.",
    color = "bad",
  },
  abandon = {
    banner = "LEFT THE FIELD",
    headline = "Left the field.",
    color = "muted",
  },
  incomplete = {
    banner = "RESULT NOT HOME",
    headline = "Result not home — Retry extract or Abandon.",
    color = "steam",
  },
}

function Ash.color(name, alpha)
  local c = Ash.COL[name] or Ash.COL.ink
  if alpha ~= nil then
    return { c[1], c[2], c[3], alpha }
  end
  return c
end

function Ash.verdictInfo(verdict)
  local key = tostring(verdict or "incomplete"):lower()
  return Ash.VERDICT[key] or Ash.VERDICT.incomplete
end

--- Map gadget status / resultCode to protocol verdict for display only.
function Ash.displayVerdict(status, resultCode, terminalReason)
  local st = tostring(status or ""):lower()
  local reason = tostring(terminalReason or ""):lower()
  if st == "victory" or st == "victoryclean" or resultCode == 1 then
    return "victory"
  end
  if st == "defeat" or st == "failed" or st == "failure" or resultCode == 2 then
    return "defeat"
  end
  if st == "abandon" or st == "abandoned" or reason == "abandon" then
    return "abandon"
  end
  if st == "incomplete" or st == "unknown" or st == "active" or st == "inactive" then
    return "incomplete"
  end
  if st == "partial" or st == "extracted" or resultCode == 3 then
    return "partial"
  end
  if resultCode == 1 then return "victory" end
  if resultCode == 2 then return "defeat" end
  return "partial"
end

function Ash.setColor(col)
  if not col then
    gl.Color(1, 1, 1, 1)
    return
  end
  gl.Color(col[1], col[2], col[3], col[4] or 1)
end

function Ash.text(str, x, y, size, col, align)
  Ash.setColor(col or Ash.COL.ink)
  gl.Text(tostring(str or ""), x, y, size or 12, (align or "c") .. "o")
end

--- Filled panel with edge border and left accent strip (Ash Console chrome).
function Ash.panel(x1, y1, x2, y2, opts)
  opts = opts or {}
  local fill = opts.fill or Ash.COL.panel
  local edge = opts.edge or Ash.COL.edge
  local accent = opts.accent -- left strip color, or nil
  local edgeA = opts.edgeA or 0.55

  Ash.setColor(fill)
  gl.Rect(x1, y1, x2, y2)

  if accent then
    Ash.setColor({ accent[1], accent[2], accent[3], accent[4] or 0.85 })
    gl.Rect(x1, y1, x1 + 3, y2)
  end

  Ash.setColor({ edge[1], edge[2], edge[3], edgeA })
  gl.LineWidth(1.25)
  gl.BeginEnd(GL.LINE_LOOP, function()
    gl.Vertex(x1, y1)
    gl.Vertex(x2, y1)
    gl.Vertex(x2, y2)
    gl.Vertex(x1, y2)
  end)
  gl.LineWidth(1)
end

--- Framed voice block (matches hub .voice).
-- speaker may be "" for system lines.
function Ash.voiceBlock(cx, y, maxW, speaker, line, alpha)
  alpha = alpha or 1
  local w = maxW or 520
  local x1 = cx - w / 2
  local x2 = cx + w / 2
  local h = 42
  local y1 = y - h / 2
  local y2 = y + h / 2

  Ash.setColor({ Ash.COL.panel[1], Ash.COL.panel[2], Ash.COL.panel[3], 0.88 * alpha })
  gl.Rect(x1, y1, x2, y2)
  Ash.setColor({ Ash.COL.edge[1], Ash.COL.edge[2], Ash.COL.edge[3], 0.9 * alpha })
  gl.Rect(x1, y1, x1 + 3, y2)

  local textY = y + 4
  if speaker and speaker ~= "" then
    Ash.text(string.upper(tostring(speaker)), cx, y + 12, 10, {
      Ash.COL.edge[1], Ash.COL.edge[2], Ash.COL.edge[3], alpha
    }, "c")
    textY = y - 6
  end
  local body = tostring(line or "")
  if speaker and speaker ~= "" then
    body = '"' .. body .. '"'
  end
  Ash.text(body, cx, textY, 13, {
    Ash.COL.gold[1], Ash.COL.gold[2], Ash.COL.gold[3], alpha
  }, "c")
  return h
end

--- Small label chip: dark fill, colored text.
function Ash.chipLabel(str, x, y, size, col)
  Ash.text(str, x, y, size or 11, col or Ash.COL.muted, "c")
end

return Ash
