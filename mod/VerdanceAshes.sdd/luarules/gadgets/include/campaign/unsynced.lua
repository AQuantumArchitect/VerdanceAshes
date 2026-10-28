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

function gadget:Update()
  if isHeadless() or not holdStartPause then return end
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

function gadget:Shutdown()
  gadgetHandler:RemoveSyncAction("VERDANCE_TRACK")
  gadgetHandler:RemoveSyncAction("VERDANCE_MISSION_EVENT")
  gadgetHandler:RemoveSyncAction("VERDANCE_HERO_EVENT")
  gadgetHandler:RemoveSyncAction("VERDANCE_BEAT")
end
