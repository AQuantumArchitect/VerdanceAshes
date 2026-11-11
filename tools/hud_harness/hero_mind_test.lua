-- Run with Lua 5.4 from the workspace root. The heroes' minds in the field (include/va_hero_mind.lua, in
-- shadow): what a hero sees each think goes into its mind, one Umwelt step per think, published on the
-- unit for the HUD; a hero going down reaches its bonded friend through the bridge, and a rival the
-- other way; a hero with no bond on the drop is a cluster of its own and hears nothing.
local params, hp, said = {}, {}, {}
Spring = {
  Echo = function(s) said[#said + 1] = s end,
  GetUnitHealth = function(uid) return hp[uid], 1000 end,
  GetUnitDefID = function() return 1 end,
  GetUnitPosition = function(uid) return uid * 100, 0, 0 end,
  SetUnitRulesParam = function(uid, k, v) params[uid] = params[uid] or {}; params[uid][k] = v end,
}
Game = { gameSpeed = 30 }
VFS = { Include = function(path) return dofile("mod/VerdanceAshes.sdd/luarules/gadgets/" .. path:gsub("^luarules/gadgets/", "")) end }
local Mind = dofile("mod/VerdanceAshes.sdd/luarules/gadgets/include/va_hero_mind.lua")

local U = { h = 0.01, gammaDiss = 5.0, bridgeStrength = 0.5, rObs = 0.95, catchupMax = 32 }
local mission = { heroMind = {
  roles = { "nerve", "drive", "threat", "pain" }, shared = { "nerve", "drive" },
  clusters = {
    { heroes = { "vane", "ketha", "verse" }, bridges = { { "vane", "ketha", 0.8 }, { "vane", "verse", -0.6 } } },
    { heroes = { "halbard" }, bridges = {} },
  },
  start = {
    vane = { nerve = 0.7, drive = 0.6, threat = 0.5, pain = 0.5 },
    ketha = { nerve = 0.7, drive = 0.6, threat = 0.5, pain = 0.5 },
    verse = { nerve = 0.7, drive = 0.6, threat = 0.5, pain = 0.5 },
    halbard = { nerve = 0.7, drive = 0.6, threat = 0.5, pain = 0.5 },
  },
  umwelt = U, holdS = 0.6,
} }
-- a field where only unit 2 (Ketha) stands under fire
local field = {
  horizon = function(_, h) return 10 end,
  incoming = function(_, x) if x == 200 then return 300 end return 0 end,
}

local st = Mind.load(mission)
assert(st, "a mission with minds loads them")
assert(said[1]:find("VA_HERO_MIND armed heroes=4 clusters=2", 1, true), said[1])
local heroes = { { 1, "vane" }, { 2, "ketha" }, { 3, "verse" }, { 4, "halbard" } }
hp = { [1] = 1000, [2] = 1000, [3] = 1000, [4] = 400 }
local frame = 0
for _ = 1, 10 do
  frame = frame + 18
  Mind.think(st, frame, heroes, field)
end
-- a reading pulls its belief to rObs of the way to its pole: 60% of health lost reads (0.95 * 0.2 + 1) / 2
assert(math.abs(params[4].va_mind_pain - 0.595) < 0.002, "Halbard at 40% health feels it: " .. params[4].va_mind_pain)
assert(params[1].va_mind_pain < 0.1, "Vane, whole, does not: " .. params[1].va_mind_pain)
assert(params[2].va_mind_threat > 0.9, "Ketha under fire sees the threat: " .. params[2].va_mind_threat)
assert(params[1].va_mind_threat < 0.1, "Vane, out of reach, does not: " .. params[1].va_mind_threat)
assert(params[1].va_mind_threat_c > 0.9, "and is sure of it")
local before = { ketha = params[2].va_mind_nerve, verse = params[3].va_mind_nerve, halbard = params[4].va_mind_nerve }

Mind.down(st, frame + 5, "vane")   -- Vane goes down
frame = frame + 18
Mind.think(st, frame, { { 2, "ketha" }, { 3, "verse" }, { 4, "halbard" } }, field)
assert(params[2].va_mind_nerve < before.ketha - 0.01, "her friend Ketha is shaken: " .. before.ketha .. " -> " .. params[2].va_mind_nerve)
assert(params[3].va_mind_nerve > before.verse, "her rival Verse takes it the other way: " .. before.verse .. " -> " .. params[3].va_mind_nerve)
assert(math.abs(params[4].va_mind_nerve - before.halbard) < 0.02, "Halbard, bound to no one here, only forgets as he would have")
local downs = 0
for _, s in ipairs(said) do if s:find("VA_HERO_MIND down hero=vane", 1, true) then downs = downs + 1 end end
assert(downs == 1, "the fall is logged")
assert(Mind.load({}) == nil, "no minds in the mission: nothing runs")
print("ok: hero minds see pain and threat, publish va_mind_*, and a fall reaches a friend and a rival through the bonds")
