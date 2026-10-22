if not VFS.Include("LuaRules/Configs/va_active.lua") then return false end -- plain BAR unless the hub launched this
local gadget = gadget

function gadget:GetInfo()
  return {
    name = "Verdance Shell Bake",
    desc = "Headless grow dump: emit VA_SHELL_UNIT lines at freeze frame for living-shell templates",
    author = "Verdance",
    date = "2026-07-27",
    license = "GPL v2 or later",
    layer = 5,
    enabled = true,
  }
end

if not gadgetHandler:IsSyncedCode() then
  return
end

local function modFlag(name)
  local mo = Spring.GetModOptions and Spring.GetModOptions() or {}
  local v = mo[name]
  if v == true or v == 1 then return true end
  if type(v) == "string" then
    v = v:lower()
    return v == "1" or v == "true" or v == "yes" or v == "enabled"
  end
  return false
end

local function modInt(name, default)
  local mo = Spring.GetModOptions and Spring.GetModOptions() or {}
  local v = mo[name]
  if v == nil then return default end
  return tonumber(v) or default
end

local bakeEnabled = false
local bakeFrames = 27000
local dumped = false
local quitFrame = nil

function gadget:Initialize()
  bakeEnabled = modFlag("va_shell_bake")
  bakeFrames = modInt("va_shell_bake_frames", 27000)
  if bakeEnabled then
    Spring.Echo("VA_SHELL_BAKE_ARMED frames=" .. tostring(bakeFrames))
    -- Headless often stalls forever building IconsAtlas; push icons off.
    -- useOverlay (the third arg) keeps these in memory only. Without it they are
    -- written through to the player's springsettings.cfg and survive the process,
    -- so one bake silently disables LuaUI for every later GUI session.
    if Spring.SetConfigInt then
      Spring.SetConfigInt("UnitIconsAsUI", 0, true)
      Spring.SetConfigInt("UnitIconDist", 99999, true)
      Spring.SetConfigInt("LuaUI", 0, true)
    end
    -- Speed up headless grow (AI still builds; sim clock races).
    if Spring.SendCommands then
      Spring.SendCommands("setmaxspeed 20")
      Spring.SendCommands("setminspeed 20")
      Spring.SendCommands("cheat")
      Spring.SendCommands("globallos")
    end
  end
end

local function dumpAllUnits()
  local mapX = Game.mapSizeX or 0
  local mapZ = Game.mapSizeZ or 0
  Spring.Echo("VA_SHELL_MAP " .. tostring(mapX) .. " " .. tostring(mapZ))
  Spring.Echo("VA_SHELL_DUMP_BEGIN")
  local count = 0
  local units = Spring.GetAllUnits() or {}
  for _, unitID in ipairs(units) do
    local defID = Spring.GetUnitDefID(unitID)
    local ud = defID and UnitDefs[defID]
    if ud and ud.name then
      local x, _, z = Spring.GetUnitPosition(unitID)
      local facing = 0
      if Spring.GetUnitBuildFacing then
        facing = Spring.GetUnitBuildFacing(unitID) or 0
      end
      -- Elmos absolute; strip script normalizes if needed.
      Spring.Echo(string.format(
        "VA_SHELL_UNIT %s %.1f %.1f %d",
        ud.name,
        x or 0,
        z or 0,
        facing
      ))
      count = count + 1
    end
  end
  Spring.Echo("VA_SHELL_DUMP_END count=" .. tostring(count))
  return count
end

function gadget:GameFrame(frame)
  if not bakeEnabled or dumped then
    if quitFrame and frame >= quitFrame then
      Spring.Echo("VA_SHELL_BAKE_QUIT")
      Spring.SendCommands("quitforce")
    end
    return
  end
  -- Re-assert speed early; some BAR widgets reset maxspeed at start.
  if frame == 1 or frame == 30 then
    if Spring.SendCommands then
      Spring.SendCommands("setmaxspeed 20")
      Spring.SendCommands("setminspeed 20")
    end
  end
  if frame > 0 and frame % 1800 == 0 then
    Spring.Echo("VA_SHELL_BAKE_TICK frame=" .. tostring(frame) .. " target=" .. tostring(bakeFrames))
  end
  if frame < bakeFrames then return end
  dumped = true
  local n = dumpAllUnits()
  Spring.Echo("VA_SHELL_BAKE_DONE count=" .. tostring(n) .. " frame=" .. tostring(frame))
  quitFrame = frame + 30
end
