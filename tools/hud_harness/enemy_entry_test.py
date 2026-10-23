#!/usr/bin/env python3
"""The enemy entry rule, run in real Lua 5.4 (ctypes) against a stub map.

Lifts `unseenByPlayer` and `enemyEntry` out of game_verdance_campaign.lua and checks the rule:
reinforcements enter only on the map edge, only inside a zone their faction truly holds
(mission.entryZones), and, if hostile, never where the player sees or stands near.

    VA_WS=$PWD python3 tools/hud_harness/enemy_entry_test.py
"""
import ctypes, glob, json, os, re, sys

WS = os.environ.get("VA_WS") or os.getcwd()
SRC = open(os.path.join(WS, "mod", "VerdanceAshes.sdd", "luarules", "gadgets", "game_verdance_campaign.lua"), encoding="utf-8").read()
start = SRC.index("local SIGHT_MARGIN = 2200")
end = SRC.index('return nil, "every_owned_edge_in_sight"\nend', start) + len('return nil, "every_owned_edge_in_sight"\nend')
RULE = SRC[start:end]

L = ctypes.CDLL(glob.glob('/usr/lib/x86_64-linux-gnu/liblua5.4.so*')[0])
L.luaL_newstate.restype = ctypes.c_void_p
L.luaL_openlibs.argtypes = [ctypes.c_void_p]
L.luaL_loadstring.argtypes = [ctypes.c_void_p, ctypes.c_char_p]
L.lua_pcallk.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_void_p, ctypes.c_void_p]
L.lua_tolstring.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_void_p]
L.lua_tolstring.restype = ctypes.c_char_p

STUBS = r'''
-- 4096 x 4096 map. West strip (x < 1024) is ARM_W, held by Armada; the rest is HOME, the player's.
Game = { mapSizeX = 4096, mapSizeZ = 4096 }
playerTeamID, playerAllyTeamID = 0, 0
teamFaction = { [0] = "ashwalkers", [1] = "armada", [2] = "nullmercs" }
mission = { entryZones = { armada = { "ARM_W" } } }
local PLAYER_UNITS = { { 3000, 3000 } }
SEEN = function(x, z) return false end
function zoneForPosition(x, z) return { zoneId = (x < 1024) and "ARM_W" or "HOME" } end
UnitDefNames = { armpw = { id = 1 }, armflea = { id = 2 } }
Spring = {
  AreTeamsAllied = function(a, b) return (a == 0 or a == 2) and (b == 0 or b == 2) end,
  GetGroundHeight = function() return 0 end,
  GetPositionLosState = function(x, y, z, ally) local s = SEEN(x, z); return s, s, false, false end,
  GetTeamList = function() return { 0, 1, 2 } end,
  GetTeamUnits = function(t) if t == 0 then return { 1 } end return {} end,
  GetUnitPosition = function(u) local p = PLAYER_UNITS[u]; return p[1], 0, p[2] end,
  TestMoveOrder = function() return true end,
}
function setPlayerAt(x, z) PLAYER_UNITS[1] = { x, z } end
LIVE_DV = {}
function zoneDvTable() return LIVE_DV end
'''

CHECKS = r'''
local out = {}
local defs = { "armpw", "armpw", "armflea" }
-- 1. Armada comes in on an edge, inside its own zone, unseen.
local x, z = enemyEntry(1, defs, 3000, 3000)
out.armada = { x = x, z = z, zone = x and zoneForPosition(x, z).zoneId }
-- 2. A faction holding nothing sends no one.
mission.entryZones = { armada = {} }
local nx, why = enemyEntry(1, defs, 3000, 3000)
out.nothing = { x = nx, why = why }
mission.entryZones = { armada = { "ARM_W" } }
-- 3. Every owned edge spot in the player's sight: no one.
SEEN = function(x, z) return x < 1024 end
local sx, swhy = enemyEntry(1, defs, 3000, 3000)
out.seen = { x = sx, why = swhy }
SEEN = function() return false end
-- 4. The player standing on the west edge: nothing within 2200 of them.
setPlayerAt(160, 2048)
local px, pz = enemyEntry(1, defs, 3000, 3000)
out.near = { x = px, z = pz, d = px and math.sqrt((px - 160) ^ 2 + (pz - 2048) ^ 2) }
setPlayerAt(3000, 3000)
-- 5. Live ownership alone is enough: the kernel sent nothing, but Armada's defences stand in ARM_W.
mission.entryZones = {}
LIVE_DV = { ARM_W = { armada = 1200 } }
local lx, lz = enemyEntry(1, defs, 3000, 3000)
out.live = { x = lx, z = lz, zone = lx and zoneForPosition(lx, lz).zoneId }
-- 6. Out-built: the player has more defensive value in ARM_W now, so Armada cannot enter there.
LIVE_DV = { ARM_W = { armada = 300, ashwalkers = 900 } }
local ox, owhy = enemyEntry(1, defs, 3000, 3000)
out.outbuilt = { x = ox, why = owhy }
LIVE_DV = {}
-- 7. Mercs (allied) enter on their own ground and may be seen doing it.
mission.entryZones = { ashwalkers = { "HOME" } }
SEEN = function() return true end
local mx, mz = enemyEntry(2, defs, 3000, 3000)
out.mercs = { x = mx, z = mz, zone = mx and zoneForPosition(mx, mz).zoneId }
local function enc(v)
  if type(v) == "table" then
    local parts = {}
    for k, w in pairs(v) do parts[#parts + 1] = string.format("%q:%s", k, enc(w)) end
    return "{" .. table.concat(parts, ",") .. "}"
  elseif type(v) == "string" then return string.format("%q", v)
  elseif v == nil then return "null" else return tostring(v) end
end
RESULT = enc(out)
'''

st = L.luaL_newstate()
L.luaL_openlibs(st)
code = STUBS + "\n" + RULE + "\n" + CHECKS + "\nreturn RESULT"
if L.luaL_loadstring(st, code.encode()) != 0 or L.lua_pcallk(st, 0, 1, 0, None, None) != 0:
    print("LUA ERROR", L.lua_tolstring(st, -1, None).decode())
    sys.exit(1)
r = json.loads(L.lua_tolstring(st, -1, None).decode())
ok = True


def check(label, cond, detail=""):
    global ok
    print(("ok   " if cond else "FAIL ") + label + ("  " + json.dumps(detail) if not cond else ""))
    ok = ok and cond


a = r["armada"]
on_edge = a.get("x") is not None and (min(a["x"], a["z"]) <= 160 or max(a["x"], a["z"]) >= 4096 - 160)
check("Armada enters on a map edge", on_edge, a)
check("... inside its own zone", a.get("zone") == "ARM_W", a)
check("a faction holding nothing sends no one", r["nothing"].get("x") is None and r["nothing"].get("why") == "no_owned_zone", r["nothing"])
check("no entry anywhere the player can see", r["seen"].get("x") is None, r["seen"])
n = r["near"]
check("no entry within 2200 of the player", n.get("x") is None or n["d"] >= 2200, n)
check("live defensive value alone opens a zone to its holder", r["live"].get("zone") == "ARM_W", r["live"])
check("a zone the player out-builds is closed to the enemy", r["outbuilt"].get("x") is None, r["outbuilt"])
check("allied Mercs enter on their own ground, seen or not", r["mercs"].get("zone") == "HOME", r["mercs"])
print("ENEMY ENTRY " + ("PASSED" if ok else "FAILED"))
sys.exit(0 if ok else 1)
