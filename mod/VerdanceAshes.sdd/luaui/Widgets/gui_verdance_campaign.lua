if not VFS.Include("LuaRules/Configs/va_active.lua") then return false end -- plain BAR unless the hub launched this
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
  say("/vaspawn spawns companion; /vareset resets local debug latch only (hub RESET.bat wipes campaign)")
  say("/vazones prints loaded zone map; /vaexport aliases /varesult")
  say("/vacontinue N  continue on this map into debrief pick N (1-3)")
  say("/vanext N      pick next mission candidate (same as debrief 1/2/3)")
  say("/vasurface     Phase 4: echo campaign_surface (kernel / mission card)")
  say("/vapack status|on|off|drag on|drag off  — A/B pack glue (line-spread test)")
end

-- Phase 4: try known VFS / write paths for campaign_surface.latest.json
local function tryReadSurface()
  local paths = {
    "campaign_surface.latest.json",
    "LuaUI/Config/verdance_campaign_surface.json",
    "LuaUI/Widgets/campaign_surface.latest.json",
  }
  for _, p in ipairs(paths) do
    if VFS and VFS.FileExists and VFS.FileExists(p) then
      local raw = VFS.LoadFile(p)
      if raw and #raw > 0 then
        return p, raw
      end
    end
  end
  -- io may be restricted; best-effort
  if io and io.open then
    local candidates = {
      "campaign_surface.latest.json",
    }
    for _, p in ipairs(candidates) do
      local f = io.open(p, "r")
      if f then
        local raw = f:read("*a")
        f:close()
        if raw and #raw > 0 then
          return p, raw
        end
      end
    end
  end
  return nil, nil
end

local function showSurface()
  local path, raw = tryReadSurface()
  if not raw then
    say("VA_SURFACE missing — kernel writes outbox/campaign_surface.latest.json outside BAR.")
    say("VA_SURFACE Mission card / Ketha line still come from the seed briefing.")
    send("vastatus")
    return
  end
  say("VA_SURFACE path=" .. tostring(path))
  -- Log first ~400 chars so infolog stays readable
  local snippet = raw
  if #snippet > 400 then
    snippet = snippet:sub(1, 400) .. "..."
  end
  say("VA_SURFACE " .. snippet:gsub("\n", " "))
end

function widget:Initialize()
  say("VA_WIDGET_LOADED Verdance commands ready. Type /vahelp")
end

function widget:TextCommand(command)
  if not command then return false end
  local cmd = command:match("^(%S+)")
  if not cmd then return false end
  if cmd == "vahelp" then help(); return true end
  if cmd == "vasurface" then showSurface(); return true end
  if cmd == "vacontinue" then
    send(command) -- full "vacontinue N"
    return true
  end
  if cmd == "vanext" then
    send(command)
    return true
  end
  if cmd == "vapack" then
    send(command) -- full "vapack …" for mid-Drop pack A/B
    return true
  end
  if cmd == "vastart" or cmd == "vastatus" or cmd == "varesult" or cmd == "vaprogress" or cmd == "vaprogressbig" or cmd == "vawin" or cmd == "vafail" or cmd == "vapartial" or cmd == "vaspawn" or cmd == "vareset" or cmd == "vazones" or cmd == "vaexport" then
    if cmd == "vaexport" then send("varesult") else send(cmd) end
    return true
  end
  return false
end






