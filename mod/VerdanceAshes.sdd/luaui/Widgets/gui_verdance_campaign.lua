local widget = widget

function widget:GetInfo()
  return {
    name = "Verdance Campaign Commands",
    desc = "Text command bridge for Verdance campaign dev loop",
    author = "ChatGPT / Luke Spooner",
    date = "2026-06-19",
    license = "GPL v2 or later",
    layer = 0,
    enabled = true,
  }
end

local function say(s)
  Spring.Echo(s)
end

local function send(cmd)
  Spring.SendLuaRulesMsg("VA_CMD:" .. cmd)
end

local function help()
  say("Verdance Campaign commands:")
  say("/vastart starts auto-progress; /vastatus short state; /varesult logs full JSON to infolog.txt")
  say("/vaprogress adds 10s; /vaprogressbig completes; /vawin /vafail /vapartial force outcome")
  say("/vaspawn spawns companion; /vareset resets local debug mission state")
  say("/vazones prints loaded zone map; /vaexport aliases /varesult")
end

function widget:Initialize()
  say("VA_WIDGET_LOADED Verdance commands ready. Type /vahelp")
end

function widget:TextCommand(command)
  if not command then return false end
  local cmd = command:match("^(%S+)")
  if not cmd then return false end
  if cmd == "vahelp" then help(); return true end
  if cmd == "vastart" or cmd == "vastatus" or cmd == "varesult" or cmd == "vaprogress" or cmd == "vaprogressbig" or cmd == "vawin" or cmd == "vafail" or cmd == "vapartial" or cmd == "vaspawn" or cmd == "vareset" or cmd == "vazones" or cmd == "vaexport" then
    if cmd == "vaexport" then send("varesult") else send(cmd) end
    return true
  end
  return false
end





