#!/usr/bin/env python3
"""Bond perks in real Lua 5.4: lifts VA_BOND_apply out of game_verdance_campaign.lua and checks a
pair's XP and gift land only when both heroes are on the drop.

    VA_WS=$PWD python3 tools/hud_harness/bond_test.py
"""
import ctypes, glob, json, os, sys

WS = os.environ.get("VA_WS") or os.getcwd()
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import campaign_lua  # noqa: E402
SRC = campaign_lua.source()
start = SRC.index("function VA_BOND_apply(")
FN = SRC[start:SRC.index("\nend\n", start) + 5]
L = ctypes.CDLL(glob.glob('/usr/lib/x86_64-linux-gnu/liblua5.4.so*')[0])
L.luaL_newstate.restype = ctypes.c_void_p
L.luaL_openlibs.argtypes = [ctypes.c_void_p]
L.luaL_loadstring.argtypes = [ctypes.c_void_p, ctypes.c_char_p]
L.lua_pcallk.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_void_p, ctypes.c_void_p]
L.lua_tolstring.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_void_p]
L.lua_tolstring.restype = ctypes.c_char_p
CODE = r'''
XP, SPAWNED = { [1] = 0.2, [2] = 0.1, [3] = 0.0 }, {}
heroes = { ceil = { unitID = 1 }, kettle = { unitID = 2 }, fatboy = { unitID = 3 } }
playerTeamID = 0
UnitDefNames = { armhawk = {}, armrl = {} }
Spring = { Echo = function() end, ValidUnitID = function() return true end,
  GetUnitExperience = function(u) return XP[u] end, SetUnitExperience = function(u, x) XP[u] = x end }
function spawnUnitSpec(spec) SPAWNED[spec.unitDefName] = (SPAWNED[spec.unitDefName] or 0) + spec.count; return spec.count end
mission = {
  bondXp = { { a = "ceil", b = "kettle", rank = "A", xp = 0.1 }, { a = "fatboy", b = "kettle", rank = "B", xp = 0.05 } },
  bondGifts = { { a = "ceil", b = "kettle", unitDef = "armhawk", count = 2 }, { a = "fatboy", b = "kettle", unitDef = "armrl", count = 3 } },
}
''' + FN + r'''
local n = VA_BOND_apply({ "ketha", "ceil", "kettle" }, 0, 0, 0)
return string.format('{"n":%d,"ceil":%.3f,"kettle":%.3f,"fatboy":%.3f,"hawk":%d,"rl":%d}', n, XP[1], XP[2], XP[3], SPAWNED.armhawk or 0, SPAWNED.armrl or 0)
'''
st = L.luaL_newstate(); L.luaL_openlibs(st)
if L.luaL_loadstring(st, CODE.encode()) != 0 or L.lua_pcallk(st, 0, 1, 0, None, None) != 0:
    print("LUA ERROR", L.lua_tolstring(st, -1, None).decode()); sys.exit(1)
o = json.loads(L.lua_tolstring(st, -1, None).decode())
ok = abs(o["ceil"] - 0.3) < 1e-6 and abs(o["kettle"] - 0.2) < 1e-6 and o["fatboy"] == 0 and o["hawk"] == 2 and o["rl"] == 0 and o["n"] == 2
print(("ok   " if ok else "FAIL ") + "a pair's XP and gift land only when both drop  " + json.dumps(o))
print("BOND " + ("PASSED" if ok else "FAILED"))
sys.exit(0 if ok else 1)
