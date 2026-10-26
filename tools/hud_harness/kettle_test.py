#!/usr/bin/env python3
"""Saint Kettle's radar-guided missile, in real Lua 5.4 (ctypes) against engine stubs.

Runs game_verdance_kettle.lua as shipped and drives it frame by frame: an idle launcher locks onto the
nearest hostile air blip the company has only on radar (inside its reach, never ground, never friends,
never when it already has a target), and a missile in flight puts every hostile unit near it in the
company's sight until it lands. The rapid spray's missiles see nothing.

    VA_WS=$PWD python3 tools/hud_harness/kettle_test.py
"""
import ctypes, glob, json, os, sys

WS = os.environ.get("VA_WS") or os.getcwd()
GADGETS = os.path.join(WS, "mod", "VerdanceAshes.sdd", "luarules", "gadgets")
GADGET = os.path.join(GADGETS, "game_verdance_kettle.lua")

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
local KET, BLIP, GROUND, FRIEND, FAR, SEEN = 10, 20, 21, 22, 23, 24
local ally = { [KET] = 0, [BLIP] = 1, [GROUND] = 1, [FRIEND] = 0, [FAR] = 1, [SEEN] = 1 }
local defs = { [KET] = 7, [BLIP] = 30, [GROUND] = 31, [FRIEND] = 30, [FAR] = 30, [SEEN] = 30 }
local pos = { [KET] = {0, 0, 0}, [BLIP] = {1000, 100, 0}, [GROUND] = {800, 0, 0}, [FRIEND] = {600, 100, 0},
              [FAR] = {2500, 100, 0}, [SEEN] = {400, 100, 0} }
local state = {   -- what the company (ally 0) has of each enemy: los / radar
  [BLIP] = { los = false, radar = true }, [GROUND] = { los = false, radar = true },
  [FAR] = { los = false, radar = true }, [SEEN] = { los = true, radar = true },
  [FRIEND] = { los = true, radar = true },
}
local hasTarget = 0
local log = { targets = {}, revealed = {} }
local projPos = {}

gadget = {}
gadgetHandler = { IsSyncedCode = function() return true end }
VFS = { Include = function(p) if p:find("va_active") then return true end error("unexpected include " .. p) end }
Script = { SetWatchWeapon = function(w, on) log.watch = w end }
UnitDefNames = { va_kettle = { id = 7, weapons = { { weaponDef = 70 }, { weaponDef = 71 } } } }
UnitDefs = { [7] = { weapons = { { weaponDef = 70 }, { weaponDef = 71 } } }, [30] = { canFly = true }, [31] = { canFly = false } }
WeaponDefs = { [70] = { id = 70, range = 1200, customParams = { va_radar_lock = "1", va_sight_radius = "320" } },
               [71] = { id = 71, range = 880, customParams = {} } }
local function dist2(a, b) return (a[1]-b[1])^2 + (a[2]-b[2])^2 + (a[3]-b[3])^2 end
Spring = {
  GetAllUnits = function() return { KET, BLIP, GROUND, FRIEND, FAR, SEEN } end,
  GetUnitDefID = function(u) return defs[u] end,
  GetUnitAllyTeam = function(u) return ally[u] end,
  GetUnitTeam = function(u) return ally[u] end,
  GetUnitPosition = function(u) local p = pos[u]; if p then return p[1], p[2], p[3] end end,
  GetUnitMaxRange = function() return 1200 end,
  GetUnitWeaponTarget = function() return hasTarget end,
  GetUnitsInSphere = function(x, y, z, r)
    local out = {}
    for u, p in pairs(pos) do if dist2({x, y, z}, p) <= r * r then out[#out + 1] = u end end
    table.sort(out)
    return out
  end,
  GetUnitLosState = function(u, at) return state[u] end,
  SetUnitLosState = function(u, at, st) log.revealed[#log.revealed + 1] = { u, at } end,
  SetUnitTarget = function(u, t, user, manual, w) log.targets[#log.targets + 1] = { u, t, user, manual, w }; return true end,
  GetProjectilePosition = function(p) local q = projPos[p]; if q then return q[1], q[2], q[3] end end,
}
dofile(@GADGET@)
gadget:Initialize()
local function frames(a, b) for f = a, b do gadget:GameFrame(f) end end
local out = {}

-- an idle launcher locks the nearest radar-only enemy in reach, ground or air: not the friend,
-- not the far one (past 1200), not the one already in sight
frames(1, 6)
out.watched = log.watch
out.locks = #log.targets
out.lock = log.targets[1]
-- the blip is shown to the company so the launcher can aim at it
out.blipShown = false
for _, r in ipairs(log.revealed) do if r[1] == GROUND and r[2] == 0 then out.blipShown = true end end

-- with the ground blip in sight, the air blip is next
state[GROUND] = { los = true, radar = true }
log.targets = {}
frames(7, 12)
out.airLock = log.targets[1]
state[GROUND] = { los = false, radar = true }

-- a launcher that already has a target is left alone
log.targets = {}
hasTarget = 1
frames(13, 24)
out.busyLocks = #log.targets
hasTarget = 0

-- a missile of the long-range weapon sees what it passes: the enemy ground blip within 320
log.revealed = {}
gadget:ProjectileCreated(900, KET, 70)
projPos[900] = { 800, 0, 200 }
frames(25, 26)
out.eyes = {}
for _, r in ipairs(log.revealed) do out.eyes[tostring(r[1])] = r[2] end
-- ...and not what is out of its sight
out.sawFar = out.eyes[tostring(FAR)] ~= nil
-- it flies on: it sees the next thing, and not the last
log.revealed = {}
projPos[900] = { 2500, 100, 100 }
frames(27, 27)
out.eyes2 = {}
for _, r in ipairs(log.revealed) do out.eyes2[tostring(r[1])] = r[2] end

-- the spray's missile sees nothing; neither does a missile that has landed
log.revealed = {}
gadget:ProjectileCreated(901, KET, 71)
projPos[901] = { 800, 0, 0 }
gadget:ProjectileDestroyed(900)
frames(28, 29)
out.revealedAfter = #log.revealed

-- a dead Kettle is let go
gadget:UnitDestroyed(KET)
log.targets = {}
frames(30, 60)
out.afterDeath = #log.targets
return enc(out)
'''.replace("@GADGET@", json.dumps(GADGET))

ok = True


def check(label, cond, detail=""):
    global ok
    print(("ok   " if cond else "FAIL ") + label + ("  " + json.dumps(detail) if not cond else ""))
    ok = ok and cond


s = run(SCENES)
check("the long-range missile is the one watched", s["watched"] == 70, s)
check("an idle launcher locks exactly one blip", s["locks"] == 1, s)
check("on the nearest radar-only unit (the ground one), weapon 1, not as a user order", s["lock"] == [10, 21, False, False, 1], s)
check("with the ground one in sight, on the radar-only air unit", s["airLock"] == [10, 20, False, False, 1], s)
check("and shows it to the company so it can be aimed at", s["blipShown"] is True, s)
check("a launcher with a target is left alone", s["busyLocks"] == 0, s)
check("a missile in flight sees the enemy ground unit it passes", s["eyes"].get("21") == 0, s)
check("it does not see its own side", "22" not in s["eyes"], s)
check("it does not see what is beyond its sight", s["sawFar"] is False, s)
check("flying on, it sees the next unit near it", s["eyes2"].get("23") == 0 and "21" not in s["eyes2"], s)
check("the spray and a landed missile see nothing", s["revealedAfter"] == 0, s)
check("a dead Kettle locks nothing", s["afterDeath"] == 0, s)
print("KETTLE " + ("PASSED" if ok else "FAILED"))
sys.exit(0 if ok else 1)
