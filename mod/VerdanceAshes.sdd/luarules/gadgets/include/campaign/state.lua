-- campaign/state.lua: the sortie itself (mission, zone map, status, teams), the marks registry and the JSON helpers
-- Part of game_verdance_campaign.lua, loaded into that gadget's environment
-- (VFS.Include with the gadget table), so its globals are the gadget's globals.
-- Provides: MarksLib, balance, debugAutoProgress, debugAutoProgressAllowed, fib, gaiaTeamID,
-- headless, holdFrames, jnum, jstr, marks, marksCommit, mission, playerAllyTeamID, playerTeamID,
-- printerUnits, sortieChapter, status, teamAllyTeam, teamFaction, truthy, zoneMap

mission = nil
zoneMap = nil
status = "inactive"
holdFrames = 0
debugAutoProgress = 0
headless = { autoStart = false, fastWin = false, quit = false, started = false, quitFrame = nil }

balance = { exportFrame = nil, exported = false, quitAfterExport = false }
fib = { milestones = {}, idx = 1, quitAfterLast = false }

playerTeamID = 0
playerAllyTeamID = 0
gaiaTeamID = -1
teamAllyTeam = {}                 -- teamID -> allyTeamID
teamFaction = {}                  -- teamID -> world faction (nullmercs/armada/cortex/...)

printerUnits = {}  -- unitID -> { metal/frame, energy/frame, team }

-- Drop 4: marks registry = single SoT for vault / structure / hero_recover.
-- Purge + announce latch stay beside it (victory policy, not mark records).
MarksLib = nil
do
  local ok, mod = pcall(VFS.Include, "luarules/gadgets/include/va_marks_registry.lua")
  if not ok or type(mod) ~= "table" then
    ok, mod = pcall(VFS.Include, "LuaRules/gadgets/include/va_marks_registry.lua")
  end
  if ok and type(mod) == "table" then
    MarksLib = mod
    Spring.Echo("VA_MARKS_REGISTRY_LOADED")
  else
    Spring.Echo("VA_MARKS_REGISTRY_MISSING")
    MarksLib = {
      KIND = { vault = "vault", structure = "structure", hero_recover = "hero_recover" },
      new = function()
        return { groups = {}, order = {}, targets = {}, requiredLeft = 0 }
      end,
      upsert = function() end,
      complete = function() end,
      bindTarget = function() end,
      hasTarget = function() return false end,
      onTargetDestroyed = function() return nil, nil, false end,
      eachTarget = function(_, fn) end,
      enrichFromMission = function() end,
      upsertHeroRecover = function() return nil end,
      completeHeroRecover = function() end,
      publish = function() end,
      doneCount = function() return 0 end,
      requiredLeft = function() return 0 end,
      count = function() return 0 end,
      resultsJson = function() return "[]" end,
      markRequired = function() end,
      targetOf = function() return nil end,
    }
  end
end
marks = MarksLib.new()

function marksCommit(event, sid)
  MarksLib.publish(marks)
  if event and SendToUnsynced then
    SendToUnsynced("VERDANCE_MISSION_EVENT", event, sid or "")
  end
end

-- Chapter index carried in the result key (always 1: there is no same-map continue).
sortieChapter = 1

debugAutoProgressAllowed = false

function truthy(v)
  if v == true or v == 1 then return true end
  if type(v) == "string" then
    v = v:lower()
    return v == "1" or v == "true" or v == "yes" or v == "enabled"
  end
  return false
end

function esc(s)
  s = tostring(s or "")
  s = s:gsub('\\', '\\\\')
  s = s:gsub('"', '\\"')
  return s
end

function jstr(s) return '"' .. esc(s) .. '"' end
function jnum(x, digits)
  x = tonumber(x) or 0
  if digits then return string.format("%." .. digits .. "f", x) end
  return tostring(math.floor(x + 0.5))
end
