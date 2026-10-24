if not VFS.Include("LuaRules/Configs/va_active.lua") then return false end -- plain BAR unless the hub launched this
function widget:GetInfo()
  return {
    name    = "Verdance Hot Drop",
    desc    = "Waits with the field loaded and paused until the hub's Drop, then sends the chosen "
           .. "company in and leaves the field paused until the player unpauses.",
    author  = "Verdance",
    date    = "2026",
    license = "GNU GPL, v2 or later",
    layer   = 0,
    enabled = true,
  }
end

--------------------------------------------------------------------------------
-- The kernel launched this field when the player picked the sortie (tools/verdance_kernel/
-- hot_drop.py). The campaign gadget holds the company off the field (va_hotdrop_pending) and
-- this widget holds the pause meanwhile. On Drop the kernel writes one line to
-- LuaUI/Config/verdance/drop.txt:
--   token|pack,pack|unitdef:n,unitdef:n
-- This widget reads it, checks the token against the mission's (va_hotdrop_token, so a file left
-- from an earlier game drops nobody) and hands it to the gadget. The company lands paused: the
-- fight starts when the player unpauses, so a minimized window never misses the opening.
-- The pause is held from GameFrame as well as Update: the sim keeps ticking when the window is
-- minimized even if drawing does not.
--------------------------------------------------------------------------------

local DROP_FILE = "LuaUI/Config/verdance/drop.txt"
local POLL_SECONDS = 0.5

local Ash
do
  local ok, mod = pcall(VFS.Include, "luaui/Include/va_ash_tokens.lua")
  if not ok or type(mod) ~= "table" then ok, mod = pcall(VFS.Include, "LuaUI/Include/va_ash_tokens.lua") end
  Ash = (ok and type(mod) == "table") and mod or nil
end

local sent = false
local sentAt = 0
local nudged = false
local landed = false     -- the gadget has the company on the field
local heldDown = false   -- ...and the pause has taken since: the next unpause is the player's
local since = 0
local clock = 0

local function pending() return Spring.GetGameRulesParam("va_hotdrop_pending") == 1 end
local function paused()
  if Spring.IsGamePaused then return Spring.IsGamePaused() == true end
  local _, _, p = Spring.GetGameSpeed()
  return p == true
end

local function holdPause()
  if not paused() then Spring.SendCommands("pause 1") end
end

local function readDropLine()
  local body
  if io and io.open then
    local f = io.open(DROP_FILE, "r")
    if f then body = f:read("*l"); f:close() end
  end
  if not body and VFS and VFS.LoadFile then
    local ok, text = pcall(VFS.LoadFile, DROP_FILE, VFS.RAW)
    if ok and type(text) == "string" then body = text:match("^[^\r\n]*") end
  end
  return body and body:match("^%s*(.-)%s*$") or nil
end

function widget:GameStart()
  if pending() then holdPause() end
end

function widget:GameFrame()
  if (pending() and not (sent and nudged)) or (landed and not heldDown) then holdPause() end
end

function widget:Update(dt)
  if landed then
    if paused() then heldDown = true
    elseif heldDown then widgetHandler:RemoveWidget(self)   -- the player unpaused: the fight is on
    else holdPause() end
    return
  end
  clock = clock + (dt or 0)
  if sent then
    -- If the engine waits for a sim frame to deliver the message, give it one.
    if pending() and not nudged and clock - sentAt > 1.0 then
      nudged = true
      Spring.SendCommands("pause 0")
    end
    if not pending() then            -- the gadget has the company on the field: stay paused
      landed = true
      holdPause()
      local px, pz = tonumber((Spring.GetGameRulesParam("va_pad_x"))), tonumber((Spring.GetGameRulesParam("va_pad_z")))
      if px and pz and px >= 0 and Spring.SetCameraTarget then
        Spring.SetCameraTarget(px, Spring.GetGroundHeight(px, pz) or 0, pz, 0.6)
      end
      Spring.Echo("VA_HOTDROP_LANDED")
    end
    return
  end
  if not pending() then return end
  -- Nothing moves until the company is down: hold the pause the start of the sortie set.
  holdPause()
  since = since + (dt or 0)
  if since < POLL_SECONDS then return end
  since = 0
  local line = readDropLine()
  if not line or line == "" then return end
  local token = line:match("^([^|]*)")
  if token ~= tostring(Spring.GetGameRulesParam("va_hotdrop_token") or "") then return end
  Spring.SendLuaRulesMsg("VA_CMD:vahotdrop " .. line)
  sent = true
  sentAt = clock
  Spring.Echo("VA_HOTDROP_SENT " .. line)
end

function widget:DrawScreen()
  if not landed and not pending() then return end
  local vsx, vsy = Spring.GetViewGeometry()
  local title = landed and "The company is down" or sent and "Dropping…" or "The field is ready"
  local line = landed and "The field is paused. Unpause (Pause / Break) when you are ready to fight."
    or sent and "The company is landing on the pad."
    or "Choose who goes on the hub, then press Drop. The company lands with the field still paused."
  if Ash then
    local w = math.min(vsx - 40, 640)
    local x1, y1 = (vsx - w) / 2, vsy * 0.62
    Ash.panel(x1, y1, x1 + w, y1 + 86, {})
    Ash.text(title, vsx / 2, y1 + 52, 22, Ash.COL.gold, "c")
    Ash.text(line, vsx / 2, y1 + 20, 14, Ash.COL.ink, "c")
  else
    gl.Color(1, 1, 1, 1)
    gl.Text(title, vsx / 2, vsy * 0.62 + 52, 22, "c")
    gl.Text(line, vsx / 2, vsy * 0.62 + 20, 14, "c")
  end
end
