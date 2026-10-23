if not VFS.Include("LuaRules/Configs/va_active.lua") then return false end -- plain BAR unless the hub launched this
local widget = widget

function widget:GetInfo()
  return {
    name = "Verdance Campaign Commands",
    desc = "Text commands for the Verdance campaign (status and playtest tools)",
    author = "Luke Spooner",
    date = "2026-10-22",
    license = "GPL v2 or later",
    layer = 0,
    enabled = true,
  }
end

-- Forwarded to the campaign gadget. The ones marked (cheats) do nothing without /cheat.
local FORWARD = { vastatus = true, varesult = true, vazones = true, vapack = true,
  vastart = true, vatnb = true, vabrutecrash = true, vareset = true }

local function help()
  Spring.Echo("Verdance commands:")
  Spring.Echo("/vastatus  sortie state · /vazones  zone map · /varesult  result JSON to infolog (cheats)")
  Spring.Echo("/vapack status|on|off|drag on|drag off  pack glue test")
  Spring.Echo("Playtest (cheats): /vatnb N  grant Tenebrium · /vabrutecrash N · /vastart · /vareset")
end

function widget:TextCommand(command)
  local cmd = command and command:match("^(%S+)")
  if not cmd then return false end
  if cmd == "vahelp" then help(); return true end
  if cmd == "vaexport" then command, cmd = "varesult", "varesult" end
  if FORWARD[cmd] then
    Spring.SendLuaRulesMsg("VA_CMD:" .. command)
    return true
  end
  return false
end
