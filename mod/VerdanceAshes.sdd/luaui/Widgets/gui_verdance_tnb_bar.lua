if not VFS.Include("LuaRules/Configs/va_active.lua") then return false end -- plain BAR unless the hub launched this
local widget = widget

function widget:GetInfo()
  return {
    name = "Verdance Tnb Bar",
    desc = "Tenebrium on BAR's top bar: a black glowing donut and the bank, just left of metal; the number flashes when the bank moves",
    author = "Verdance",
    date = "2026-10-20",
    license = "GPL v2 or later",
    layer = 10,
    enabled = true,
  }
end

-- The ONE place Tenebrium is read on the HUD: the bank (va_tenebrium_bank, published by
-- game_verdance_campaign.lua every 30 frames), one number on BAR's top bar.

local vsx, vsy = Spring.GetViewGeometry()
local bank = 0
local lastBank = nil
local flashUntil = 0
local flashKind = nil      -- "good" (bank rose) | "warn" (bank fell)
local lastPoll = -999

local FLASH_SECONDS = 1.5

local COL = {
  tnb = { 0.788, 0.627, 1.000, 1.0 },
  ink = { 0.933, 0.965, 0.933, 1.0 },
  ash = { 0.604, 0.545, 0.447, 1.0 },
  muted = { 0.490, 0.584, 0.518, 1.0 },
  good = { 0.490, 1.000, 0.541, 1.0 },
  warn = { 0.878, 0.627, 0.376, 1.0 },
  panel = { 0.031, 0.063, 0.047, 0.90 },
  edge = { 0.239, 0.561, 0.333, 1.0 },
}
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

local function numParam(name, default)
  local v = Spring.GetGameRulesParam(name)
  return tonumber(v) or default
end

local function text(str, x, y, size, col, align)
  if Ash and Ash.text then
    Ash.text(str, x, y, size, col, align)
    return
  end
  gl.Color(col[1], col[2], col[3], col[4] or 1)
  gl.Text(tostring(str), x, y, size, (align or "l") .. "o")
end

local function poll()
  bank = math.floor(numParam("va_tenebrium_bank", 0) + 0.5)
  if lastBank ~= nil and bank ~= lastBank then
    flashKind = (bank > lastBank) and "good" or "warn"
    flashUntil = os.clock() + FLASH_SECONDS
  end
  lastBank = bank
end

function widget:Initialize()
  poll()
  Spring.Echo("VA_UI_TNB_BAR armed")
end

function widget:ViewResize(x, y)
  vsx, vsy = x, y
end

function widget:GameFrame(frame)
  if frame - lastPoll >= 30 then
    lastPoll = frame
    poll()
  end
end

-- A disc of triangles; alpha may fall off from centre (a) to rim (b).
local function disc(cx, cy, r, c, a, b, segs)
  gl.BeginEnd(GL.TRIANGLE_FAN, function()
    gl.Color(c[1], c[2], c[3], a)
    gl.Vertex(cx, cy)
    gl.Color(c[1], c[2], c[3], b)
    for i = 0, segs do
      local t = i / segs * math.pi * 2
      gl.Vertex(cx + math.cos(t) * r, cy + math.sin(t) * r)
    end
  end)
end

-- The Tenebrium mark: a black donut breathing a faint violet glow. The hole shows the bar.
local VOID = { 0.012, 0.004, 0.02 }
local function donut(cx, cy, r, glowA)
  disc(cx, cy, r * 1.9, { 0.23, 0.12, 0.36 }, glowA, 0.0, 32) -- violet haze
  disc(cx, cy, r, VOID, 0.97, 0.97, 32)                   -- the black ring
  gl.Color(COL.tnb[1], COL.tnb[2], COL.tnb[3], 0.55)
  gl.LineWidth(1)
  gl.BeginEnd(GL.LINE_LOOP, function()
    for i = 0, 31 do local t = i / 32 * math.pi * 2; gl.Vertex(cx + math.cos(t) * r, cy + math.sin(t) * r) end
  end)
  disc(cx, cy, r * 0.42, { 0.07, 0.09, 0.08 }, 1.0, 1.0, 20) -- the hole
end

function widget:DrawScreen()
  if Spring.IsGUIHidden() then return end
  local ok, err = pcall(function()
    -- Just left of BAR's metal bar (WG.topbar publishes its area); top-centre if it is absent.
    local pos = WG and WG["topbar"] and WG["topbar"].GetPosition and WG["topbar"].GetPosition()
    local h, scale, right, y1
    if pos then
      scale = pos[5] or 1
      h = (pos[4] - pos[2])
      right, y1 = pos[1] - 6 * scale, pos[2]
    else
      scale, h = 1, 40
      right, y1 = vsx * 0.5, vsy - h
    end
    local now = os.clock()
    local flashA = (flashKind and now < flashUntil) and math.max(0, (flashUntil - now) / FLASH_SECONDS) or 0
    local size = math.floor(h * 0.42)
    local label = tostring(bank)
    local tw = gl.GetTextWidth(label) * size
    local r = h * 0.2
    local cy = y1 + h * 0.5
    local cx = right - tw - 10 * scale - r
    donut(cx, cy, r, 0.55 + 0.25 * math.abs(math.sin(now * 1.3)))
    local col = COL.tnb
    if flashA > 0 then col = (flashKind == "good") and COL.good or COL.warn end
    text(label, right, cy - size * 0.35, size, col, "r")
    gl.Color(1, 1, 1, 1)
  end)
  if not ok and not widget._vaTnbFailLogged then
    widget._vaTnbFailLogged = true
    Spring.Echo("VA_UI_DRAW_FAIL tnb_bar " .. tostring(err))
  end
end
