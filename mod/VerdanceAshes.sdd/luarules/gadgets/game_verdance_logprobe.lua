if not VFS.Include("LuaRules/Configs/va_active.lua") then return false end -- plain BAR unless the hub launched this
local gadget = gadget

function gadget:GetInfo()
  return {
    name = "Verdance Log Probe",
    desc = "Test rig only (va_logprobe=1): one line per logging route, to see which reach the player's console",
    author = "Verdance tools",
    date = "2026-11-09",
    license = "GPL v2 or later",
    layer = 50,
    enabled = true,
  }
end

-- The mod's VA_ lines (hundreds per sortie) are for the test tools, which read them from the infolog;
-- through Spring.Echo every one also lands in the player's chat console. This probe writes one line
-- per route at game second 18 (and a screenshot rig run shows the console), so the quiet route can be
-- picked: one that reaches the infolog and not the console.
local opts = (Spring.GetModOptions and Spring.GetModOptions()) or {}
if tostring(opts.va_logprobe) ~= "1" then return false end
if not gadgetHandler:IsSyncedCode() then return end

local done = false
function gadget:GameFrame(f)
  if done or f < 540 then return end   -- game second 18: the screenshot rig's first shot is at 20
  done = true
  Spring.Echo("VA_PROBE route=echo")
  if Spring.Log then
    pcall(Spring.Log, "Verdance", LOG and LOG.NOTICE or "notice", "VA_PROBE route=log_notice")
    pcall(Spring.Log, "Verdance", LOG and LOG.INFO or "info", "VA_PROBE route=log_info")
    pcall(Spring.Log, "Verdance", LOG and LOG.DEBUG or "debug", "VA_PROBE route=log_debug")
    -- BAR's chat (gui_chat.lua AddConsoleLine) drops priority L_DEPRECATED lines; does the infolog keep
    -- them, every time (twice, to catch de-duplication)?
    Spring.Echo("VA_PROBE LOG.DEPRECATED=" .. tostring(LOG and LOG.DEPRECATED))
    pcall(Spring.Log, "Verdance", LOG and LOG.DEPRECATED or "deprecated", "VA_PROBE route=log_deprecated n=1")
    pcall(Spring.Log, "Verdance", LOG and LOG.DEPRECATED or "deprecated", "VA_PROBE route=log_deprecated n=1")
    pcall(Spring.Log, "Verdance", LOG and LOG.DEPRECATED or "deprecated", "VA_PROBE route=log_deprecated n=2")
  end
end
