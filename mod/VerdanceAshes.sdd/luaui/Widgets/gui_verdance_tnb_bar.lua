if not VFS.Include("LuaRules/Configs/va_active.lua") then return false end -- plain BAR unless the hub launched this
local widget = widget

function widget:GetInfo()
  return {
    name = "Verdance Tnb Bar",
    desc = "Tenebrium strip under BAR's resource bar: bank · looted · field, with a pip per Tnb and a flash when the bank moves",
    author = "Verdance",
    date = "2026-10-20",
    license = "GPL v2 or later",
    layer = 10,
    enabled = true,
  }
end

-- The ONE place Tenebrium is read on the HUD. Feeds from game_verdance_campaign.lua
-- publishTenebriumRules(): va_tenebrium_bank / va_tenebrium_looted / va_tenebrium_spent /
-- va_tenebrium_wrecks_unclaimed (every 30 frames). Tooltip-free by design; the numbers
-- are the whole message.

local vsx, vsy = Spring.GetViewGeometry()
local bank, looted, spent, field = 0, 0, 0, 0
local lastBank = nil
local flashUntil = 0
local flashKind = nil      -- "good" (bank rose) | "warn" (bank fell)
local lastPoll = -999

local BAR_W = 260
local BAR_H = 26
local BAR_TOP_GAP = 58     -- just under BAR's resource bar
local PIP_MAX = 12
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
  looted = math.floor(numParam("va_tenebrium_looted", 0) + 0.5)
  spent = math.floor(numParam("va_tenebrium_spent", 0) + 0.5)
  field = math.floor(numParam("va_tenebrium_wrecks_unclaimed", 0) + 0.5)
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

function widget:DrawScreen()
  if Spring.IsGUIHidden() then return end
  local ok, err = pcall(function()
    local x1 = vsx * 0.5 - BAR_W * 0.5
    local x2 = x1 + BAR_W
    local y2 = vsy - BAR_TOP_GAP
    local y1 = y2 - BAR_H

    -- Flash wash (good when the bank rose, warn when it fell) — redundant with the number.
    local now = os.clock()
    local flashA = 0
    if flashKind and now < flashUntil then
      flashA = math.max(0, (flashUntil - now) / FLASH_SECONDS)
    end

    if Ash and Ash.panel then
      Ash.panel(x1, y1, x2, y2, { accent = COL.tnb })
    else
      gl.Color(COL.panel[1], COL.panel[2], COL.panel[3], COL.panel[4] or 0.9)
      gl.Rect(x1, y1, x2, y2)
      gl.Color(COL.tnb[1], COL.tnb[2], COL.tnb[3], 0.85)
      gl.Rect(x1, y1, x1 + 3, y2)
    end
    if flashA > 0 then
      local fc = (flashKind == "good") and COL.good or COL.warn
      gl.Color(fc[1], fc[2], fc[3], 0.28 * flashA)
      gl.Rect(x1 + 3, y1, x2, y2)
    end

    -- Text: "TNB  bank 7  ·  looted 3  ·  field 2" — bank large/bold.
    local tx = x1 + 12
    local ty = y1 + 9
    text("TNB", tx, ty, 10, COL.ash, "l")
    tx = tx + gl.GetTextWidth("TNB") * 10 + 10
    text("bank", tx, ty, 9, COL.muted, "l")
    tx = tx + gl.GetTextWidth("bank") * 9 + 4
    local bankStr = tostring(bank)
    local bankCol = COL.tnb
    if flashA > 0 then
      bankCol = (flashKind == "good") and COL.good or COL.warn
    end
    text(bankStr, tx, ty - 1, 14, bankCol, "l")
    tx = tx + gl.GetTextWidth(bankStr) * 14 + 8
    local rest = string.format("·  looted %d  ·  field %d", looted, field)
    text(rest, tx, ty, 9, COL.muted, "l")

    -- Pip row: one violet pip per Tnb up to PIP_MAX, then "+n".
    local px = x1 + 12
    local py = y1 + 3
    local pips = math.min(PIP_MAX, math.max(0, bank))
    gl.Color(COL.tnb[1], COL.tnb[2], COL.tnb[3], 0.9)
    for i = 1, pips do
      gl.Rect(px + (i - 1) * 9, py, px + (i - 1) * 9 + 6, py + 3)
    end
    if bank > PIP_MAX then
      text("+" .. tostring(bank - PIP_MAX), px + pips * 9 + 2, py - 1, 8, COL.tnb, "l")
    end
    gl.Color(1, 1, 1, 1)
  end)
  if not ok and not widget._vaTnbFailLogged then
    widget._vaTnbFailLogged = true
    Spring.Echo("VA_UI_DRAW_FAIL tnb_bar " .. tostring(err))
  end
end
