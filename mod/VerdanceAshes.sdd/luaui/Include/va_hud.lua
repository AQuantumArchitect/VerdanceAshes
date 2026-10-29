-- The HUD's common ground: what every Verdance widget reads and does the same way.
--
--   local Hud = VFS.Include("luaui/Include/va_hud.lua")
--   local Ash, J, Board = Hud.Ash, Hud.J, Hud.Board
--
-- Facts: the gadgets publish rules params; widgets read them with Hud.num / Hud.str / Hud.on and
-- never rescan units. The shared board (WG.vaBoard, the minimap's) is Hud.board().
-- Verbs: a player's key or click and the rig's player call the same named verb
-- (Hud.verb("extract", fn) registers it, Hud.press("extract") runs it): begin, extract, confirm, back.

local Hud = {}

local function lib(name)
  local ok, mod = pcall(VFS.Include, "luaui/Include/" .. name .. ".lua")
  if not ok or type(mod) ~= "table" then ok, mod = pcall(VFS.Include, "LuaUI/Include/" .. name .. ".lua") end
  if ok and type(mod) == "table" then return mod end
  Spring.Echo("VA_UI_LIB_FAIL " .. name .. " " .. tostring(mod))
  return nil
end
Hud.lib = lib
Hud.Ash = lib("va_ash_tokens")
Hud.J = lib("va_json")
Hud.Board = lib("va_board")
local Ash = Hud.Ash

-- ---------------------------------------------------------------- facts (rules params)
-- An unset param returns no value at all, so every read goes through tonumber((...)).
function Hud.num(name, default) return tonumber((Spring.GetGameRulesParam(name))) or default end
function Hud.str(name)
  local v = Spring.GetGameRulesParam(name)
  if type(v) == "string" and v ~= "" then return v end
  return nil
end
function Hud.on(name) return Hud.num(name, 0) == 1 end
function Hud.json(name)
  local raw = Spring.GetGameRulesParam(name)
  if not Hud.J or type(raw) ~= "string" or raw == "" then return nil end
  return Hud.J.decode(raw)
end

function Hud.seed()
  local ok, m = pcall(VFS.Include, "singleplayer/verdance_ashes/generated/va_current.lua")
  if ok and type(m) == "table" then return m end
  return nil
end

-- ---------------------------------------------------------------- the sortie's state
function Hud.paused()
  if Spring.IsGamePaused then return Spring.IsGamePaused() == true end
  local _, _, p = Spring.GetGameSpeed()
  return p == true
end
function Hud.setPaused(on) pcall(Spring.SendCommands, on and "pause 1" or "pause 0") end
function Hud.begun() return (WG and WG.vaSortieBegan) == true end
function Hud.over() return Hud.on("va_terminal") end
-- One full-screen card at a time (infil, the manifest, the closing card); the rail steps aside.
function Hud.modal() return (WG and WG.vaExfilModal) == true end
function Hud.setModal(on) if WG then WG.vaExfilModal = on and true or false end end

local ownBoard = nil
function Hud.board()
  if WG and WG.vaBoard then return WG.vaBoard end
  if not ownBoard and Hud.Board then ownBoard = Hud.Board.new() end
  return ownBoard
end

-- ---------------------------------------------------------------- verbs
-- WG.vaVerbs[name] = fn. Registered by the widget that owns the verb; pressed by keys, clicks,
-- text commands and the rig's player alike. Each press is echoed (VA_UI_VERB) so a headless run
-- shows the HUD did the work.
function Hud.verb(name, fn)
  if not WG then return end
  WG.vaVerbs = WG.vaVerbs or {}
  WG.vaVerbs[name] = fn
end
function Hud.press(name, ...)
  local fn = WG and WG.vaVerbs and WG.vaVerbs[name]
  if not fn then return false end
  Spring.Echo("VA_UI_VERB " .. name .. " frame=" .. tostring(Spring.GetGameFrame() or 0))
  return fn(...) ~= false
end

-- A UI sound by BAR name (beep4, warning1, ...) or path.
function Hud.sound(file, vol)
  if not Spring.PlaySoundFile then return end
  if not Spring.PlaySoundFile(tostring(file), vol or 1.0, "ui") then
    Spring.PlaySoundFile("sounds/ui/" .. tostring(file) .. ".wav", vol or 1.0, "ui")
  end
end

-- ---------------------------------------------------------------- words
function Hud.clock(sec)
  sec = math.max(0, math.floor(sec + 0.5))
  return string.format("%d:%02d", math.floor(sec / 60), sec % 60)
end
function Hud.dist(d)
  d = tonumber(d) or 0
  if d >= 1000 then return string.format("%.1f km", d / 1000) end
  return string.format("%d m", math.floor(d + 0.5))
end
function Hud.plural(n, one, many) return tostring(n) .. " " .. ((n == 1) and one or many) end

-- Word-wrap to at most maxLines; a cut last line ends in an ellipsis. Remembered: the cards and the
-- rail wrap the same text every frame. The list handed back is shared, so read it, don't change it.
local wrapCache, wrapCount = {}, 0
local wrapOnce
function Hud.wrap(s, size, maxW, maxLines)
  s = tostring(s or "")
  local a = wrapCache[size]; if not a then a = {}; wrapCache[size] = a end
  local b = a[maxW]; if not b then b = {}; a[maxW] = b end
  local c = b[maxLines]; if not c then c = {}; b[maxLines] = c end
  local hit = c[s]
  if hit then return hit end
  wrapCount = wrapCount + 1
  if wrapCount > 500 then wrapCache, wrapCount = {}, 0 end   -- start over; this call's answer is still kept below
  hit = wrapOnce(s, size, maxW, maxLines)
  c[s] = hit
  return hit
end

function wrapOnce(s, size, maxW, maxLines)
  local lines, cur, cut = {}, "", false
  for word in tostring(s or ""):gmatch("%S+") do
    local try = (cur == "") and word or (cur .. " " .. word)
    if Ash.textW(try, size) <= maxW then cur = try
    else
      if cur ~= "" then lines[#lines + 1] = cur end
      cur = word
      if #lines >= maxLines then cut = true; break end
    end
  end
  if cur ~= "" and not cut then
    if #lines < maxLines then lines[#lines + 1] = cur else cut = true end
  end
  if cut and lines[maxLines] then lines[maxLines] = Ash.fit(lines[maxLines] .. " …", size, maxW) end
  return lines
end

-- ---------------------------------------------------------------- chrome shared by the cards
-- A framed column with a kicker line; returns the content's x, top y and right edge.
function Hud.column(x1, y1, x2, y2, kicker, accent)
  Ash.panel(x1, y1, x2, y2, { accent = accent })
  Ash.text(kicker, x1 + 12, y2 - 18, 10, Ash.COL.ash, "l")
  Ash.rule(x1 + 12, y2 - 23, x2 - 12, accent, 0.45)
  return x1 + 12, y2 - 42, x2 - 12
end

-- The board drawn into a box, letterboxed to the map's shape. paintOpts.slot names the surface
-- ("infil", "manifest", ...) so its display list is kept apart from the others (Board:paintCached).
local BOX_BG = { 0.05, 0.09, 0.07, 1 }
local boxes = {}   -- slot -> { x1, y1, x2, y2, proj, rect }
function Hud.boardBox(b, x1, y1, x2, y2, paintOpts)
  local slot = (paintOpts and paintOpts.slot) or "box"
  local bx = boxes[slot]
  if not bx or bx[1] ~= x1 or bx[2] ~= y1 or bx[3] ~= x2 or bx[4] ~= y2 or bx[7] ~= b then
    local proj, rect = b:fitProj(x1, y1, x2, y2)
    bx = { x1, y1, x2, y2, proj, rect, b }
    boxes[slot] = bx
  end
  local proj, rect = bx[5], bx[6]
  Ash.rect(rect[1], rect[2], rect[3], rect[4], BOX_BG)
  if b.paintCached then b:paintCached("box:" .. slot, x1, y1, x2, y2, proj, paintOpts) else b:paint(proj, paintOpts) end
  Ash.outline(rect[1], rect[2], rect[3], rect[4], Ash.with(Ash.COL.edge, 0.4), 1)
  return rect
end

return Hud
