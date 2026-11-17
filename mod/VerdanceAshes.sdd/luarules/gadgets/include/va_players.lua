-- va_players.lua: the players, one per hero (verdance.company.players; owner call 2026-11-16: "1 player
-- per hero... shared company co-op").
--
-- mission.players is [{player, heroId, name}] when more than one person plays; a one-player mission
-- carries only mission.you, and that is player 0. Every player is an engine player on the company's
-- team (the start script seats them), so all of them command the whole company. A player's hero is
-- theirs: mission-critical as "you" is, and the HUD marks it.
--
-- What this publishes (synced, once the mission is read):
--   GG.VA_Players                       heroId -> player index (0 is you)
--   game rules  va_players              how many players
--   game rules  va_player_hero_<pid>    the hero id of the engine player <pid> (matched by name)
--   unit rules  va_hero_player          on a player's hero unit: its player index (stamp(), at spawn)

local M = {}

local FIRST = "VerdanceCommander"   -- verdance.company.players.FIRST_PLAYER

function M.list(mission)
  local rows = {}
  if type(mission) ~= "table" then return rows end
  if type(mission.players) == "table" and #mission.players > 0 then
    for i = 1, #mission.players do
      local r = mission.players[i]
      if type(r) == "table" and r.heroId then
        rows[#rows + 1] = { player = tonumber(r.player) or (i - 1), heroId = tostring(r.heroId), name = tostring(r.name or "") }
      end
    end
  elseif mission.you and tostring(mission.you) ~= "" then
    rows[1] = { player = 0, heroId = tostring(mission.you), name = FIRST }
  end
  return rows
end

-- heroId -> player index
function M.heroes(mission)
  local out = {}
  for _, r in ipairs(M.list(mission)) do out[r.heroId] = r.player end
  return out
end

-- Synced: publish who is whom. Engine players are matched to the mission's players by name (the start
-- script's [PLAYERn] Name, which a joining player gives as MyPlayerName); with one player, every
-- engine player on the company's team is player 0.
function M.publish(mission, playerTeamID)
  local rows = M.list(mission)
  local byName, byIndex = {}, {}
  for _, r in ipairs(rows) do byName[r.name] = r; byIndex[r.player] = r end
  GG.VA_Players = M.heroes(mission)
  Spring.SetGameRulesParam("va_players", #rows, { public = true })
  local said = {}
  for _, pid in ipairs(Spring.GetPlayerList() or {}) do
    local name, _, spectator, teamID = Spring.GetPlayerInfo(pid, false)
    local r = byName[tostring(name or "")]
    if not r and #rows == 1 and not spectator and teamID == playerTeamID then r = byIndex[0] end
    if r then
      Spring.SetGameRulesParam("va_player_hero_" .. pid, r.heroId, { public = true })
      said[#said + 1] = tostring(name) .. "=" .. r.heroId
    end
  end
  Spring.Echo("VA_PLAYERS n=" .. #rows .. " " .. table.concat(said, " "))
  return rows
end

-- Synced: a hero unit's player mark, at spawn.
function M.stamp(unitID, heroId)
  local p = GG.VA_Players and GG.VA_Players[tostring(heroId)]
  if p then Spring.SetUnitRulesParam(unitID, "va_hero_player", p, { public = true }) end
end

-- Unsynced: the hero id this client's player is, or nil.
function M.mine()
  local pid = Spring.GetMyPlayerID and Spring.GetMyPlayerID()
  local h = pid and Spring.GetGameRulesParam("va_player_hero_" .. pid)
  if h == nil or h == "" then return nil end
  return tostring(h)
end

return M
