if not VFS.Include("LuaRules/Configs/va_active.lua") then return false end -- plain BAR unless the hub launched this
local widget = widget

function widget:GetInfo()
  return {
    name = "Verdance Rig Player",
    desc = "Headless test rig only (modoption va_autopilot=1): plays the HUD the way a player does, by pressing its verbs",
    author = "Verdance tools",
    date = "2026-10-28",
    license = "GPL v2 or later",
    layer = 50,
    enabled = true,
  }
end

-- The autopilot gadget (game_verdance_autopilot.lua) fights with an AI and decides when the company
-- leaves. This widget says VA_RIG:hud once the game runs; from then on the autopilot says leave with
-- va_autopilot_leave and waits for the HUD. This widget is the hands on the HUD:
--   the infil card up        → begin    (gui_verdance_infil)
--   the autopilot says leave → extract  (gui_verdance_sidebar: asks the exfil gadget for the manifest)
--   the manifest is open     → confirm  (gui_verdance_exfil: the lift, to the first destination)
-- Every press goes through Hud.press, the same verb a key or a click runs, so a headless sortie
-- that ends "extracted" has been through the whole HUD loop. VA_RIG lines mark each step.

local opts = (Spring.GetModOptions and Spring.GetModOptions()) or {}
if tostring(opts.va_autopilot) ~= "1" then return false end

local Hud = VFS.Include("luaui/Include/va_hud.lua")

local pressed = {}            -- verb -> os.clock() of the last press
local seenManifest = 0
local lastRail = nil

local function press(verb, why)
  local now = os.clock()
  if pressed[verb] and now - pressed[verb] < 3 then return end
  pressed[verb] = now
  local ok = Hud.press(verb)
  Spring.Echo("VA_RIG press=" .. verb .. " ok=" .. tostring(ok) .. " why=" .. why)
end

function widget:Initialize()
  Spring.Echo("VA_RIG armed")
end

local announced = false

function widget:Update()
  -- tell the autopilot the HUD is here, so the company leaves through it (once the game runs)
  if not announced and (Spring.GetGameFrame() or 0) > 0 then
    announced = true
    Spring.SendLuaRulesMsg("VA_RIG:hud")
  end
  if Hud.over() then
    if not pressed.over then
      pressed.over = os.clock()
      Spring.Echo("VA_RIG over status=" .. tostring(Hud.str("va_status")) .. " modal=" .. tostring(Hud.modal())
        .. " last_rail=" .. tostring(lastRail))
    end
    return
  end
  local rail = WG and WG.vaRail
  if rail and rail.sentence then lastRail = rail.sentence end
  if not Hud.begun() then
    if WG and WG.vaVerbs and WG.vaVerbs.begin then press("begin", "the infil card is up") end
    return
  end
  local leave = Hud.str("va_autopilot_leave")
  if not leave then return end
  local seq = Hud.num("va_manifest_seq", 0)
  if Hud.modal() and seq > seenManifest then
    seenManifest = seq
    press("confirm", "the manifest is open (seq " .. seq .. ")")
  elseif not Hud.modal() then
    press("extract", "the autopilot leaves: " .. leave)
  end
end
