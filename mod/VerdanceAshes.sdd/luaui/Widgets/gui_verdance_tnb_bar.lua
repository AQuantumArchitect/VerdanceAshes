if not VFS.Include("LuaRules/Configs/va_active.lua") then return false end -- plain BAR unless the hub launched this
local widget = widget

function widget:GetInfo()
  return {
    name = "Verdance Tnb Bar",
    desc = "Tenebrium on BAR's top bar: a black glowing donut and the bank, just left of metal; the number flashes when the bank moves. A Tenebrium crystal that drops is pinged with a reticle.",
    author = "Verdance",
    date = "2026-10-20",
    license = "GPL v2 or later",
    layer = 10,
    enabled = true,
  }
end

-- The ONE place Tenebrium is read on the HUD: the bank (va_tenebrium_bank, published by
-- game_verdance_campaign.lua every 30 frames), one number on BAR's top bar. And the one ping:
-- a crystal the shard handler drops (feature rules param va_tenebrium_shard) gets a reticle on
-- the ground and the minimap for a few seconds.

local vsx, vsy = Spring.GetViewGeometry()
local bank = 0
local lastBank = nil
local flashUntil = 0
local flashKind = nil      -- "good" (bank rose) | "warn" (bank fell)
local lastPoll = -999

local FLASH_SECONDS = 1.5
local PING_SECONDS = 3.0
local fresh = {}   -- featureID -> seconds waiting for the shard tag (it lands just after creation)
local pings = {}   -- { x, y, z, born }

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
local Hud = VFS.Include("luaui/Include/va_hud.lua")
local Ash = Hud.Ash
for k in pairs(COL) do
  if Ash and Ash.COL[k] then COL[k] = Ash.COL[k] end
end
local numParam = Hud.num

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

function widget:FeatureCreated(featureID)
  fresh[featureID] = 0
end

function widget:Update(dt)
  for fid, waited in pairs(fresh) do
    if Spring.GetFeatureRulesParam(fid, "va_tenebrium_shard") == 1 then
      local x, y, z = Spring.GetFeaturePosition(fid)
      if x then pings[#pings + 1] = { x, y, z, os.clock() } end
      fresh[fid] = nil
    elseif waited > 1.0 or not Spring.ValidFeatureID(fid) then
      fresh[fid] = nil
    else
      fresh[fid] = waited + (dt or 0)
    end
  end
  local now = os.clock()
  for i = #pings, 1, -1 do
    if now - pings[i][4] > PING_SECONDS then table.remove(pings, i) end
  end
end

local function ring(cx, cy, r, segs)
  gl.BeginEnd(GL.LINE_LOOP, function()
    for i = 0, segs - 1 do local t = i / segs * math.pi * 2; gl.Vertex(cx + math.cos(t) * r, cy + math.sin(t) * r) end
  end)
end

-- The reticle: a ring closing in on the crystal, four ticks, a steady inner ring.
local function reticle(cx, cy, r, age)
  local k = age / PING_SECONDS
  local a = 1 - k
  local closing = r * (2.4 - 1.4 * math.min(1, k * 3))
  gl.Color(COL.tnb[1], COL.tnb[2], COL.tnb[3], 0.9 * a)
  gl.LineWidth(2)
  ring(cx, cy, closing, 40)
  gl.LineWidth(1.5)
  ring(cx, cy, r * 0.55, 28)
  gl.BeginEnd(GL.LINES, function()
    for i = 0, 3 do
      local t = i * math.pi * 0.5
      local c, s = math.cos(t), math.sin(t)
      gl.Vertex(cx + c * r * 0.75, cy + s * r * 0.75)
      gl.Vertex(cx + c * r * 1.15, cy + s * r * 1.15)
    end
  end)
end

function widget:DrawScreenEffects()
  if #pings == 0 or Spring.IsGUIHidden() then return end
  local now = os.clock()
  for _, p in ipairs(pings) do
    local sx, sy, sz = Spring.WorldToScreenCoords(p[1], p[2] + 8, p[3])
    if sx and sz and sz < 1 then reticle(sx, sy, 26, now - p[4]) end
  end
  gl.LineWidth(1)
  gl.Color(1, 1, 1, 1)
end

function widget:DrawInMiniMap(mmsx, mmsy)
  if #pings == 0 then return end
  local now = os.clock()
  local mx, mz = Game.mapSizeX, Game.mapSizeZ
  for _, p in ipairs(pings) do
    reticle(p[1] / mx * mmsx, (1 - p[3] / mz) * mmsy, 9, now - p[4])
  end
  gl.LineWidth(1)
  gl.Color(1, 1, 1, 1)
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

-- A disc of triangles; alpha may fall off from centre (a) to rim (b). Drawn every frame, so the
-- vertex loops read module state (D) rather than being fresh closures, and the colours are made once.
local D = { cx = 0, cy = 0, r = 0, c = nil, a = 1, b = 1, segs = 32 }
local function discVerts()
  local cx, cy, r, c, segs = D.cx, D.cy, D.r, D.c, D.segs
  gl.Color(c[1], c[2], c[3], D.a)
  gl.Vertex(cx, cy)
  gl.Color(c[1], c[2], c[3], D.b)
  for i = 0, segs do
    local t = i / segs * math.pi * 2
    gl.Vertex(cx + math.cos(t) * r, cy + math.sin(t) * r)
  end
end
local function loopVerts()
  local cx, cy, r = D.cx, D.cy, D.r
  for i = 0, 31 do local t = i / 32 * math.pi * 2; gl.Vertex(cx + math.cos(t) * r, cy + math.sin(t) * r) end
end
local function disc(cx, cy, r, c, a, b, segs)
  D.cx, D.cy, D.r, D.c, D.a, D.b, D.segs = cx, cy, r, c, a, b, segs
  gl.BeginEnd(GL.TRIANGLE_FAN, discVerts)
end

-- The Tenebrium mark: a black donut breathing a faint violet glow. The hole shows the bar.
local VOID = { 0.012, 0.004, 0.02 }
local HAZE = { 0.23, 0.12, 0.36 }
local HOLE = { 0.07, 0.09, 0.08 }
local function donut(cx, cy, r, glowA)
  disc(cx, cy, r * 1.9, HAZE, glowA, 0.0, 32) -- violet haze
  disc(cx, cy, r, VOID, 0.97, 0.97, 32)       -- the black ring
  gl.Color(COL.tnb[1], COL.tnb[2], COL.tnb[3], 0.55)
  gl.LineWidth(1)
  D.cx, D.cy, D.r = cx, cy, r
  gl.BeginEnd(GL.LINE_LOOP, loopVerts)
  disc(cx, cy, r * 0.42, HOLE, 1.0, 1.0, 20)  -- the hole
end

local labelBank, label = nil, ""
local function drawChip()
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
    if labelBank ~= bank then labelBank, label = bank, tostring(bank) end
    local tw = gl.GetTextWidth(label) * size
    local r = h * 0.2
    right = right - 2 * r   -- clear of the metal bar's own icon: the number never sits under it
    local cy = y1 + h * 0.5
    local cx = right - tw - 10 * scale - r
    donut(cx, cy, r, 0.55 + 0.25 * math.abs(math.sin(now * 1.3)))
    local col = COL.tnb
    if flashA > 0 then col = (flashKind == "good") and COL.good or COL.warn end
    text(label, right, cy - size * 0.35, size, col, "r")
    gl.Color(1, 1, 1, 1)
end

function widget:DrawScreen()
  if Spring.IsGUIHidden() then return end
  local ok, err = pcall(drawChip)   -- a named function: no closure per frame
  if not ok and not widget._vaTnbFailLogged then
    widget._vaTnbFailLogged = true
    Spring.Echo("VA_UI_DRAW_FAIL tnb_bar " .. tostring(err))
  end
end
