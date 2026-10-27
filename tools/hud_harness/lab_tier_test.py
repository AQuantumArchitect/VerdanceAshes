#!/usr/bin/env python3
"""The lab tier, in real Lua 5.4 (ctypes) against engine stubs.

Runs game_verdance_lab_tier.lua as shipped: the player's constructors (heroes, built, captured) lose
their T2 and experimental factories from the build menu, and creating one is refused; T1 labs stay;
enemy teams keep everything.

    VA_WS=$PWD python3 tools/hud_harness/lab_tier_test.py
"""
import ctypes, glob, json, os, sys

WS = os.environ.get("VA_WS") or os.getcwd()
GADGET = os.path.join(WS, "mod", "VerdanceAshes.sdd", "luarules", "gadgets", "game_verdance_lab_tier.lua")

L = ctypes.CDLL(glob.glob('/usr/lib/x86_64-linux-gnu/liblua5.4.so*')[0])
L.luaL_newstate.restype = ctypes.c_void_p
L.luaL_openlibs.argtypes = [ctypes.c_void_p]
L.luaL_loadstring.argtypes = [ctypes.c_void_p, ctypes.c_char_p]
L.lua_pcallk.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_void_p, ctypes.c_void_p]
L.lua_tolstring.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_void_p]
L.lua_tolstring.restype = ctypes.c_char_p


def run(code):
    st = L.luaL_newstate()
    L.luaL_openlibs(st)
    if L.luaL_loadstring(st, code.encode()) != 0 or L.lua_pcallk(st, 0, 1, 0, None, None) != 0:
        print("LUA ERROR", L.lua_tolstring(st, -1, None).decode())
        sys.exit(1)
    return json.loads(L.lua_tolstring(st, -1, None).decode())


PRELUDE = r'''
local function enc(v)
  if type(v) == "table" then
    local isArr, n = true, 0
    for k in pairs(v) do n = n + 1; if type(k) ~= "number" then isArr = false end end
    local parts = {}
    if isArr and n > 0 then
      for i = 1, #v do parts[#parts + 1] = enc(v[i]) end
      return "[" .. table.concat(parts, ",") .. "]"
    end
    for k, w in pairs(v) do parts[#parts + 1] = string.format("%q:%s", tostring(k), enc(w)) end
    return "{" .. table.concat(parts, ",") .. "}"
  elseif type(v) == "string" then return string.format("%q", v)
  elseif v == nil then return "null" else return tostring(v) end
end
'''

SCENES = PRELUDE + r'''
-- defs: 1 armck (builds 2 armlab, 3 armalab, 4 armvp, 5 armnanotc), 2 armlab (T1), 3 armalab (T2),
-- 4 armvp (T1), 5 armnanotc, 6 a modded lab with techlevel 3 and an unlisted name, 7 va_mask
UnitDefs = {
  [1] = { id = 1, name = "armck", buildOptions = { 2, 3, 4, 5, 6 }, customParams = {} },
  [2] = { id = 2, name = "armlab", isFactory = true, customParams = { techlevel = "1" } },
  [3] = { id = 3, name = "armalab", isFactory = true, customParams = { techlevel = "2" } },
  [4] = { id = 4, name = "armvp", isFactory = true, customParams = { techlevel = "1" } },
  [5] = { id = 5, name = "armnanotc", customParams = {} },
  [6] = { id = 6, name = "future_lab", isFactory = true, customParams = { techlevel = "3" } },
  [7] = { id = 7, name = "va_mask", buildOptions = { 2, 5 }, customParams = {} },
}
UnitDefNames = {}
for id, ud in pairs(UnitDefs) do UnitDefNames[ud.name] = ud end
local menus = { [100] = { -2, -3, -4, -5, -6 }, [101] = { -2, -3, -4, -5, -6 }, [102] = { -2, -5 } }
local team = { [100] = 0, [101] = 1, [102] = 0 }
gadget = {}
gadgetHandler = { IsSyncedCode = function() return true end }
VFS = { Include = function(p) if p:find("va_active") then return true end error(p) end }
Spring = {
  GetGameRulesParam = function(k) if k == "va_player_team" then return 0 end end,
  GetTeamInfo = function(t) return t end,
  GetModOptions = function() return {} end,
  GetTeamUnits = function(t) local o = {} for u, tt in pairs(team) do if tt == t then o[#o + 1] = u end end table.sort(o) return o end,
  GetUnitDefID = function(u) return ({ [100] = 1, [101] = 1, [102] = 7 })[u] end,
  FindUnitCmdDesc = function(u, cmd) for i, c in ipairs(menus[u] or {}) do if c == cmd then return i end end end,
  RemoveUnitCmdDesc = function(u, i) table.remove(menus[u], i) end,
}
dofile(@GADGET@)
gadget:Initialize()
local out = {}
out.playerMenu = menus[100]
out.enemyMenu = { table.unpack(menus[101]) }
out.maskMenu = menus[102]
out.allowT2 = gadget:AllowUnitCreation(3, 100, 0)
out.allowT1 = gadget:AllowUnitCreation(2, 100, 0)
out.allowFuture = gadget:AllowUnitCreation(6, 100, 0)
out.enemyT2 = gadget:AllowUnitCreation(3, 101, 1)
-- a constructor captured from the enemy loses its T2 labs on the way over
team[101] = 0
gadget:UnitGiven(101, 1, 0)
out.capturedMenu = menus[101]
return enc(out)
'''.replace("@GADGET@", json.dumps(GADGET))

ok = True


def check(label, cond, detail=""):
    global ok
    print(("ok   " if cond else "FAIL ") + label + ("  " + json.dumps(detail) if not cond else ""))
    ok = ok and cond


s = run(SCENES)
check("the player's constructor keeps T1 labs, nano and loses the T2 and later labs", s["playerMenu"] == [-2, -4, -5], s)
check("an enemy constructor keeps everything", s["enemyMenu"] == [-2, -3, -4, -5, -6], s)
check("Mask keeps his T1 bot lab", s["maskMenu"] == [-2, -5], s)
check("creating a T2 lab is refused for the player", s["allowT2"] is False and s["allowFuture"] is False, s)
check("a T1 lab is allowed", s["allowT1"] is True, s)
check("the enemy may still raise T2 labs", s["enemyT2"] is True, s)
check("a captured constructor is stripped", s["capturedMenu"] == [-2, -4, -5], s)
print("LAB TIER " + ("PASSED" if ok else "FAILED"))
sys.exit(0 if ok else 1)
