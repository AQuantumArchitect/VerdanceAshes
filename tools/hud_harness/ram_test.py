#!/usr/bin/env python3
"""Bro's Tzar in real Lua 5.4 against stubs: crushes light enemies it touches, rams heavier ones by
speed (once a second per victim), ignores allies, and other Tzars do nothing.

    VA_WS=$PWD python3 tools/hud_harness/ram_test.py
"""
import ctypes, glob, json, os, sys

WS = os.environ.get("VA_WS") or os.getcwd()
G = os.path.join(WS, "mod", "VerdanceAshes.sdd", "luarules", "gadgets", "game_verdance_ram.lua")
L = ctypes.CDLL(glob.glob('/usr/lib/x86_64-linux-gnu/liblua5.4.so*')[0])
L.luaL_newstate.restype = ctypes.c_void_p
L.luaL_openlibs.argtypes = [ctypes.c_void_p]
L.luaL_loadstring.argtypes = [ctypes.c_void_p, ctypes.c_char_p]
L.lua_pcallk.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_void_p, ctypes.c_void_p]
L.lua_tolstring.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_void_p]
L.lua_tolstring.restype = ctypes.c_char_p
CODE = r'''
UnitDefs = {
  [1] = { name = "corgol", speed = 39, mass = 1650, customParams = {} },
  [2] = { name = "armpw", speed = 80, mass = 54, customParams = {} },
  [3] = { name = "armbull", speed = 50, mass = 950, customParams = {} },
  [4] = { name = "armllt", speed = 0, mass = 90, isBuilding = true, customParams = {} },
}
UNITS = { [10] = { def = 1, team = 0, hero = "bro", v = 1.3 }, [11] = { def = 1, team = 0, v = 1.3 },
  [20] = { def = 2, team = 1 }, [21] = { def = 3, team = 1 }, [22] = { def = 4, team = 1 }, [23] = { def = 2, team = 0 } }
DESTROYED, DAMAGE, WATCHED, FRAME = {}, {}, {}, 100
Script = { SetWatchUnit = function(id) WATCHED[#WATCHED + 1] = id end }
VFS = { Include = function() return true end }
Spring = {
  Echo = function() end, GetGameFrame = function() return FRAME end,
  GetUnitRulesParam = function(u, k) return UNITS[u] and UNITS[u].hero end,
  ValidUnitID = function(u) return UNITS[u] ~= nil end, GetUnitIsDead = function(u) return DESTROYED[u] == true end,
  GetUnitTeam = function(u) return UNITS[u] and UNITS[u].team end, AreTeamsAllied = function(a, b) return a == b end,
  GetUnitDefID = function(u) return UNITS[u] and UNITS[u].def end, GetUnitVelocity = function(u) return 0, 0, 0, UNITS[u].v or 0 end,
  DestroyUnit = function(u) DESTROYED[u] = true end, AddUnitDamage = function(u, d) DAMAGE[u] = (DAMAGE[u] or 0) + d end,
}
gadgetHandler = { IsSyncedCode = function() return true end }
gadget = {}
assert(loadfile(%s, "t", setmetatable({}, { __index = _G, __newindex = _G })))()
gadget:Initialize()
local function bump(a, b) gadget:UnitUnitCollision(a, b); gadget:GameFrame(FRAME) end
bump(10, 20)          -- crush a Pawn
bump(21, 10)          -- a Bull drives into the Tzar: rammed
bump(10, 21)          -- same frame: cooldown
FRAME = FRAME + 40; bump(10, 21)
bump(10, 22)          -- a structure is never crushed (it is rammed like a heavy unit)
bump(10, 23)          -- allied Pawn: nothing
bump(11, 20)          -- a Tzar that is not Bro's: nothing
return string.format('{"watched":%d,"pawn":%s,"bull":%.1f,"llt_destroyed":%s,"ally":%s,"plain":%s}', #WATCHED,
  tostring(DESTROYED[20] == true), DAMAGE[21] or 0, tostring(DESTROYED[22] == true), tostring(DESTROYED[23] == true), tostring(DAMAGE[20] ~= nil))
'''.replace("%s", json.dumps(G), 1)
st = L.luaL_newstate(); L.luaL_openlibs(st)
if L.luaL_loadstring(st, CODE.encode()) != 0 or L.lua_pcallk(st, 0, 1, 0, None, None) != 0:
    print("LUA ERROR", L.lua_tolstring(st, -1, None).decode()); sys.exit(1)
o = json.loads(L.lua_tolstring(st, -1, None).decode())
checks = [
    ("only Tzars are watched", o["watched"] == 1),
    ("a light enemy under the treads is crushed", o["pawn"] is True),
    ("a heavy enemy is rammed, once a second", abs(o["bull"] - 1800) < 1),
    ("structures are not crushed", o["llt_destroyed"] is False),
    ("allies are safe", o["ally"] is False),
    ("a Tzar that is not Bro's does nothing", o["plain"] is False),
]
ok = all(c for _, c in checks)
for label, c in checks:
    print(("ok   " if c else "FAIL ") + label + ("" if c else "  " + json.dumps(o)))
print("RAM " + ("PASSED" if ok else "FAILED"))
sys.exit(0 if ok else 1)
