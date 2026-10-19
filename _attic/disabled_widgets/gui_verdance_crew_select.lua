function widget:GetInfo()
  return {
    name = "Verdance Crew Select",
    desc = "DISABLED — muster lives on the HTML hub; BAR only receives a sealed crew packet",
    author = "Verdance",
    date = "2026-09-06",
    license = "GPLv2",
    layer = 55,
    enabled = false,
  }
end

local COL = {
  bg = { 0.016, 0.035, 0.027, 0.94 },
  panel = { 0.031, 0.063, 0.047, 0.92 },
  ink = { 0.933, 0.965, 0.933, 1 },
  muted = { 0.490, 0.584, 0.518, 1 },
  gold = { 0.831, 0.769, 0.604, 1 },
  edge = { 0.239, 0.561, 0.333, 1 },
  tnb = { 0.788, 0.627, 1.000, 1 },
  good = { 0.490, 1.000, 0.541, 1 },
  bad = { 1.000, 0.490, 0.490, 1 },
  warn = { 0.878, 0.627, 0.376, 1 },
}

local roster
local visible = false
local selected = {} -- set of heroId
local hoverId = nil
local seatCap = 3
local wallet = 5
local walletKm = 7
local panel = { x = 0, y = 0, w = 720, h = 520 }

local function loadRoster()
  local ok, mod = pcall(VFS.Include, "luaui/Include/va_crew_roster.lua")
  if not ok or type(mod) ~= "table" then
    ok, mod = pcall(VFS.Include, "LuaUI/Include/va_crew_roster.lua")
  end
  if ok and type(mod) == "table" then
    roster = mod
    seatCap = tonumber(mod.SEAT_CAP) or 3
    wallet = tonumber(mod.START_WALLET_TNB) or 5
  end
end

local function rulesPending()
  local v = Spring.GetGameRulesParam and Spring.GetGameRulesParam("va_crew_pending")
  return tonumber(v) == 1
end

local function rulesReady()
  local v = Spring.GetGameRulesParam and Spring.GetGameRulesParam("va_crew_ready")
  return tonumber(v) == 1
end

local function syncWallet()
  local w = Spring.GetGameRulesParam and Spring.GetGameRulesParam("va_crew_wallet")
  if w ~= nil then wallet = tonumber(w) or wallet end
  local km = Spring.GetGameRulesParam and Spring.GetGameRulesParam("va_crew_wallet_km")
  if km ~= nil then walletKm = tonumber(km) or walletKm end
end

local function selectedList()
  local out = {}
  if not roster then return out end
  for _, id in ipairs(roster.BAND_ORDER or {}) do
    if selected[id] then out[#out + 1] = id end
  end
  return out
end

local function spentTnb()
  local n = 0
  if not roster then return 0 end
  for id in pairs(selected) do
    n = n + ((roster.hireCost and roster.hireCost(id)) or 0)
  end
  return n
end

local function spentKm()
  local n = 0
  if not roster then return 0 end
  for id in pairs(selected) do
    n = n + ((roster.hireKmCost and roster.hireKmCost(id)) or 0)
  end
  return n
end

local function seatCount()
  local n = 0
  for _ in pairs(selected) do n = n + 1 end
  return n
end

local function sendConfirm()
  local picks = selectedList()
  local cmd = "vacrewconfirm " .. table.concat(picks, ",")
  if Spring.SendLuaRulesMsg then
    Spring.SendLuaRulesMsg("VA_CMD:" .. cmd)
  elseif Spring.SendCommands then
    Spring.SendCommands("luarules " .. cmd)
  end
  Spring.Echo("VA_CREW_UI_CONFIRM " .. table.concat(picks, ","))
end

local function toggle(id)
  if not roster or not id then return end
  if roster.isCore and roster.isCore(id) then return end
  if selected[id] then
    selected[id] = nil
    return
  end
  if seatCount() >= seatCap then return end
  local cost = (roster.hireCost and roster.hireCost(id)) or 0
  local costKm = (roster.hireKmCost and roster.hireKmCost(id)) or 0
  if spentTnb() + cost > wallet then return end
  if spentKm() + costKm > walletKm then return end
  selected[id] = true
end

local function text(str, x, y, size, col, align)
  gl.Color(col[1], col[2], col[3], col[4] or 1)
  gl.Text(str, x, y, size, (align or "o") .. "n")
end

local function rect(x, y, w, h, col)
  gl.Color(col[1], col[2], col[3], col[4] or 1)
  gl.Rect(x, y, x + w, y + h)
end

local function layout()
  local vsx, vsy = gl.GetViewSizes()
  panel.w = math.min(760, vsx * 0.72)
  panel.h = math.min(560, vsy * 0.78)
  panel.x = (vsx - panel.w) * 0.5
  panel.y = (vsy - panel.h) * 0.52
end

function widget:Initialize()
  loadRoster()
  layout()
  Spring.Echo("VA_CREW_UI_LOADED Muster the Band")
end

function widget:ViewResize()
  layout()
end

function widget:Update()
  local pending = rulesPending()
  local ready = rulesReady()
  if pending and not ready then
    if not visible then
      visible = true
      selected = {}
      syncWallet()
    end
  elseif visible and ready then
    visible = false
  end
end

function widget:DrawScreen()
  if not visible or not roster then return end
  layout()
  syncWallet()
  local x, y, w, h = panel.x, panel.y, panel.w, panel.h
  rect(x - 4, y - 4, w + 8, h + 8, { 0.239, 0.561, 0.333, 0.35 })
  rect(x, y, w, h, COL.panel)

  text("MUSTER THE BAND", x + 18, y + h - 28, 20, COL.gold, "o")
  text(string.format("Wallet  %d Tnb  ·  %d km$  ·  Seats %d / %d",
      wallet - spentTnb(), walletKm - spentKm(), seatCount(), seatCap),
    x + w - 18, y + h - 26, 13, COL.tnb, "r")

  text("CORE (always)", x + 18, y + h - 56, 12, COL.muted, "o")
  local cx = x + 18
  for _, id in ipairs(roster.CORE or {}) do
    local hrec = roster.get and roster.get(id) or (roster.HEROES and roster.HEROES[id])
    if hrec then
      rect(cx, y + h - 118, 210, 52, { 0.05, 0.12, 0.08, 0.95 })
      text(hrec.name or id, cx + 10, y + h - 78, 13, COL.good, "o")
      local pack = string.format("%s  ·  pack %d", hrec.unitDef or "?", hrec.packTotal or 1)
      text(pack, cx + 10, y + h - 96, 11, COL.muted, "o")
      if hrec.noTnbStake then text("no Tnb stake", cx + 10, y + h - 110, 10, COL.tnb, "o") end
      cx = cx + 220
    end
  end

  text("BAND — click to hire / refund", x + 18, y + h - 140, 12, COL.muted, "o")
  local cards = roster.BAND_ORDER or {}
  local cols = 3
  local cardW = (w - 48) / cols
  local cardH = 58
  local startY = y + h - 158 - cardH
  for i, id in ipairs(cards) do
    local hrec = roster.get and roster.get(id) or (roster.HEROES and roster.HEROES[id])
    if hrec then
      local col = (i - 1) % cols
      local row = math.floor((i - 1) / cols)
      local cx2 = x + 18 + col * cardW
      local cy = startY - row * (cardH + 8)
      local on = selected[id]
      local cost = (roster.hireCost and roster.hireCost(id)) or 0
      local costKm = (roster.hireKmCost and roster.hireKmCost(id)) or 0
      local canAfford = ((spentTnb() + cost) <= wallet and (spentKm() + costKm) <= walletKm) or on
      local full = seatCount() >= seatCap and not on
      local bg = on and { 0.12, 0.22, 0.14, 0.95 } or { 0.04, 0.08, 0.06, 0.92 }
      if not canAfford or full then bg = { 0.06, 0.05, 0.05, 0.85 } end
      if hoverId == id then bg = { 0.10, 0.18, 0.12, 0.98 } end
      rect(cx2, cy, cardW - 10, cardH, bg)
      local nameCol = on and COL.gold or (canAfford and not full and COL.ink or COL.muted)
      text(hrec.name or id, cx2 + 8, cy + cardH - 18, 12, nameCol, "o")
      local price = (costKm > 0) and string.format("%d km$", costKm)
        or ((cost > 0) and string.format("%d Tnb", cost) or "free")
      text(string.format("%s · ×%d · %s", hrec.unitDef or "?", hrec.packTotal or 1, price),
        cx2 + 8, cy + cardH - 34, 10, COL.muted, "o")
      text(hrec.blurb or "", cx2 + 8, cy + 8, 9, COL.muted, "o")
      hrec._card = { x = cx2, y = cy, w = cardW - 10, h = cardH, id = id }
    end
  end

  local preview = {}
  for _, id in ipairs(roster.CORE or {}) do preview[#preview + 1] = id end
  for _, id in ipairs(selectedList()) do preview[#preview + 1] = id end
  text("DROP  " .. table.concat(preview, "  ·  "), x + 18, y + 48, 11, COL.ink, "o")

  local btnW, btnH = 180, 36
  local bx = x + w - btnW - 18
  local by = y + 14
  local canConfirm = seatCount() <= seatCap and spentTnb() <= wallet and spentKm() <= walletKm
  rect(bx, by, btnW, btnH, canConfirm and { 0.18, 0.35, 0.22, 0.95 } or { 0.2, 0.1, 0.1, 0.9 })
  text("CONFIRM DROP", bx + btnW * 0.5, by + 12, 14, canConfirm and COL.gold or COL.bad, "c")
  panel._confirm = { x = bx, y = by, w = btnW, h = btnH }

  text("Space still only closes briefing · Pause key begins after drop", x + 18, y + 18, 10, COL.muted, "o")
end

local function hit(mx, my, r)
  return r and mx >= r.x and mx <= r.x + r.w and my >= r.y and my <= r.y + r.h
end

function widget:MousePress(mx, my, button)
  if not visible or not roster or button ~= 1 then return false end
  if panel._confirm and hit(mx, my, panel._confirm) then
    sendConfirm()
    return true
  end
  for _, id in ipairs(roster.BAND_ORDER or {}) do
    local hrec = roster.get and roster.get(id) or (roster.HEROES and roster.HEROES[id])
    if hrec and hrec._card and hit(mx, my, hrec._card) then
      toggle(id)
      return true
    end
  end
  return false
end

function widget:MouseMove(mx, my)
  if not visible or not roster then return end
  hoverId = nil
  for _, id in ipairs(roster.BAND_ORDER or {}) do
    local hrec = roster.get and roster.get(id) or (roster.HEROES and roster.HEROES[id])
    if hrec and hrec._card and hit(mx, my, hrec._card) then
      hoverId = id
      break
    end
  end
end

function widget:TextCommand(cmd)
  if type(cmd) ~= "string" then return false end
  if cmd == "vacrew" or cmd == "vamuster" then
    visible = true
    syncWallet()
    return true
  end
  return false
end
