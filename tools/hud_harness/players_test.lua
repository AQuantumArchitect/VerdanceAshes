-- Run with Lua 5.4 from the workspace root. The players in the engine (include/va_players.lua): each
-- engine player is matched to the mission's players by name and told which hero is theirs; with one
-- player, the company's own player is you whatever its name; a player's hero unit carries its index.
local game, unit, said = {}, {}, {}
local players = {}   -- pid -> { name, spectator, team }
Spring = {
  Echo = function(s) said[#said + 1] = s end,
  SetGameRulesParam = function(k, v) game[k] = v end,
  GetGameRulesParam = function(k) return game[k] end,
  SetUnitRulesParam = function(u, k, v) unit[u] = unit[u] or {}; unit[u][k] = v end,
  GetPlayerList = function() local t = {} for pid in pairs(players) do t[#t + 1] = pid end table.sort(t) return t end,
  GetPlayerInfo = function(pid) local p = players[pid] return p.name, true, p.spectator, p.team end,
}
GG = {}
local P = dofile("mod/VerdanceAshes.sdd/luarules/gadgets/include/va_players.lua")

-- co-op: two players, matched by name; a spectator who is nobody gets nothing
players = { [0] = { name = "VerdanceCommander", spectator = false, team = 3 },
            [1] = { name = "VerdancePlayer2", spectator = false, team = 3 },
            [2] = { name = "Watcher", spectator = true, team = 0 } }
local mission = { you = "pavise", players = {
  { player = 0, heroId = "pavise", name = "VerdanceCommander" },
  { player = 1, heroId = "halbard", name = "VerdancePlayer2" } } }
P.publish(mission, 3)
assert(game.va_players == 2)
assert(game.va_player_hero_0 == "pavise" and game.va_player_hero_1 == "halbard" and game.va_player_hero_2 == nil)
assert(GG.VA_Players.pavise == 0 and GG.VA_Players.halbard == 1 and GG.VA_Players.ketha == nil)
P.stamp(77, "halbard"); P.stamp(78, "ketha")
assert(unit[77].va_hero_player == 1 and unit[78] == nil, "only a player's hero is marked")
Spring.GetMyPlayerID = function() return 1 end
assert(P.mine() == "halbard", "the second player's client knows its hero")
assert(said[#said]:find("VA_PLAYERS n=2", 1, true), said[#said])

-- single player: mission.you is player 0, and the company's player is you by team
game, GG = {}, {}
players = { [0] = { name = "SomeoneElse", spectator = false, team = 3 } }
P.publish({ you = "verse" }, 3)
assert(game.va_players == 1 and game.va_player_hero_0 == "verse" and GG.VA_Players.verse == 0)
assert(#P.list({}) == 0, "no mission: nobody")
print("ok: players are matched by name, single player is you, and a player's hero carries its index")
