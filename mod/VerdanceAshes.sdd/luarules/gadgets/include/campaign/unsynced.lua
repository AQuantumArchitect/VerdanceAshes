-- campaign/unsynced.lua: the unsynced half of game_verdance_campaign.lua.
-- Forwards the synced half's telemetry, mission, hero and beat events to LuaUI widgets, and holds
-- the start-of-sortie pause until it sticks.

-- Unsynced bridge: forward synced telemetry/mission events to LuaUI widgets.
-- Also owns client-side pause requests (start of sortie + end of sortie).
local function isHeadless()
  local mo = Spring.GetModOptions and Spring.GetModOptions() or {}
  local v = mo.va_headless_autostart
  -- An offline bake is headless too: nobody is there to press unpause.
  if v == nil or v == "" then v = mo.va_shell_bake end
  if v == true or v == 1 then return true end
  if type(v) == "string" then
    v = v:lower()
    return v == "1" or v == "true" or v == "yes" or v == "enabled"
  end
  return false
end

local function requestPause(why)
  if isHeadless() then return end
  pcall(Spring.SendCommands, "pause 1")
  Spring.Echo("VA_PAUSE " .. tostring(why or "request"))
end

local function gameIsPaused()
  if Spring.IsGamePaused then
    return Spring.IsGamePaused() == true
  end
  local _, _, paused = Spring.GetGameSpeed()
  return paused == true
end

-- Hold pause until it sticks. One-shot GameStart pause races the engine and
-- often loses (sim runs; nests shoot). After pause is observed, stop asserting
-- so the player can unpause with the normal pause key.
local holdStartPause = true
local sawStartPaused = false
local pauseAssertEchoed = false

-- Co-op: the drop waits for every player (include/va_players.lua). The host's client holds the pause
-- while anyone named in the start script is not in the game yet, so a player who joins late has only
-- the paused opening to catch up. Headless too: the trial rig's players join that way. The host can
-- start without them: /luarules va_go.
local Players = VFS.Include("luarules/gadgets/include/va_players.lua")
local waitForPlayers = true
local waitingSaid = nil
local function holdForPlayers()
  if not waitForPlayers then return false end
  local w = Players.waiting()
  local said = {}
  for i = 1, #w do said[i] = w[i].name .. "=" .. w[i].heroId end
  local line = table.concat(said, " ")
  if line ~= waitingSaid then
    waitingSaid = line
    Spring.Echo(#w > 0 and ("VA_PLAYERS_WAITING " .. line) or "VA_PLAYERS_ALL_IN")
  end
  if #w == 0 then return false end
  if Players.isHost() then pcall(Spring.SendCommands, "pause 1") end
  return true
end

function gadget:Initialize()
  -- Tracked-playtest channel. The synced half already writes every one of these
  -- packets to the infolog; this hands the same strings to LuaUI so a widget can
  -- write the session record itself. That is what lets a played campaign record
  -- itself from inside the client, with no external harvester in the loop.
  -- kind is one of: telemetry | zoneflow | devsample | result.
  gadgetHandler:AddSyncAction("VERDANCE_TRACK", function(_, kind, jsonStr)
    if Script.LuaUI and Script.LuaUI.VerdanceTrack then
      Script.LuaUI.VerdanceTrack(kind, jsonStr)
    end
  end)
  gadgetHandler:AddSyncAction("VERDANCE_MISSION_EVENT", function(_, eventStatus, reason)
    -- The end of the sortie is owned by game_verdance_exfil.lua (manifest, pause, quit).
    if Script.LuaUI and Script.LuaUI.VerdanceMissionEvent then
      Script.LuaUI.VerdanceMissionEvent(eventStatus, reason)
    end
  end)
  gadgetHandler:AddSyncAction("VERDANCE_HERO_EVENT", function(_, event, heroId, name, critical, x, z)
    if Script.LuaUI and Script.LuaUI.VerdanceHeroEvent then
      Script.LuaUI.VerdanceHeroEvent(event, heroId, name, critical, x, z)
    end
  end)
  gadgetHandler:AddChatAction("va_go", function()
    if waitForPlayers then
      waitForPlayers = false
      Spring.Echo("VA_PLAYERS_GO the host starts without " .. tostring(waitingSaid ~= "" and waitingSaid or "anyone"))
    end
    return true
  end, " start the drop without the players still joining")
  gadgetHandler:AddSyncAction("VERDANCE_BEAT", function(_, kind, a, b, c, d)
    if Script.LuaUI and Script.LuaUI.VerdanceBeat then
      Script.LuaUI.VerdanceBeat(kind, a, b, c, d)
    end
  end)
end

function gadget:GameStart()
  holdStartPause = true
  sawStartPaused = false
  requestPause("sortie_start")
end

-- Update runs every drawn frame for the whole match; the modoptions are a fresh ~200-entry table
-- per read, so whether this is headless is read once.
local headless = nil
function gadget:Update()
  if holdForPlayers() then return end
  if not holdStartPause then return end
  if headless == nil then headless = isHeadless() end
  if headless then return end
  if gameIsPaused() then
    if not sawStartPaused then
      sawStartPaused = true
      Spring.Echo("VA_PAUSE_HELD sortie_start_ok")
    end
    -- Pause stuck: release the hold so the player can begin with pause key.
    holdStartPause = false
    return
  end
  -- Re-assert every update until pause sticks (engine often ignores one-shot).
  pcall(Spring.SendCommands, "pause 1")
  if not pauseAssertEchoed then
    pauseAssertEchoed = true
    Spring.Echo("VA_PAUSE sortie_start_hold")
  end
end

function gadget:GameFrame()
  holdForPlayers()
end

function gadget:Shutdown()
  gadgetHandler:RemoveChatAction("va_go")
  gadgetHandler:RemoveSyncAction("VERDANCE_TRACK")
  gadgetHandler:RemoveSyncAction("VERDANCE_MISSION_EVENT")
  gadgetHandler:RemoveSyncAction("VERDANCE_HERO_EVENT")
  gadgetHandler:RemoveSyncAction("VERDANCE_BEAT")
end
