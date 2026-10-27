#!/usr/bin/env python3
"""The kings' showdown gadget, run in real Lua 5.4 (ctypes) against stubs.

Three kings (the company on team 0, Armada on 1, Null Mercs on 2). Checks that nobody falls
before the commanders are on the field, that a king falls when its team has no commander left
and the fall is credited to whoever killed it, that the objective completes only when every rival
has fallen while ours stands, and that GG.VA_KingsJson reports it all.

    VA_WS=$PWD python3 tools/hud_harness/kings_test.py
"""
import ctypes, glob, json, os, sys

WS = os.environ.get("VA_WS") or os.getcwd()
GADGET = os.path.join(WS, "mod", "VerdanceAshes.sdd", "luarules", "gadgets", "game_verdance_kings.lua")

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


CODE = r'''
MODROOT = %s
local COM, TANK = 1, 2
UnitDefs = { [COM] = { customParams = { iscommander = "1" } }, [TANK] = { customParams = {} } }
UNITS = { [0] = {}, [1] = {}, [2] = {} }
DEAD = {}
DEFS = {}
RULES = {}
DONE = nil
GG = { VA_ObjectiveComplete = function(how) DONE = how end }
VFS = { Include = function(p)
  if p:find("va_active") then return true end
  if p:find("va_current") then return { balance = { playerTeamID = 0 }, kings = {
    { teamID = 0, faction = "ashwalkers", label = "The company" },
    { teamID = 1, faction = "armada", label = "Armada king" },
    { teamID = 2, faction = "nullmercs", label = "Null Mercs king" } } } end
  if p:find("va_commanders") then return dofile(MODROOT .. "/" .. p) end
  error("no include " .. p) end }
Spring = {
  Echo = function() end,
  SetGameRulesParam = function(k, v) RULES[k] = v end,
  GetTeamUnits = function(t) return UNITS[t] end,
  GetUnitDefID = function(u) return DEFS[u] end,
  GetUnitIsDead = function(u) return DEAD[u] == true end,
}
gadgetHandler = { IsSyncedCode = function() return true end, RemoveGadget = function() REMOVED = true end }
gadget = {}
local chunk = assert(loadfile(%s, "t", setmetatable({}, { __index = _G, __newindex = _G })))
chunk()
gadget:Initialize()
local frame = 0
local function step(n) for _ = 1, n do frame = frame + 15; gadget:GameFrame(frame) end end
local function spawn(id, team, def) DEFS[id] = def; table.insert(UNITS[team], id) end
local function kill(id, team, byTeam)
  gadget:UnitDestroyed(id, DEFS[id], team, 99, TANK, byTeam)
  for i, u in ipairs(UNITS[team]) do if u == id then table.remove(UNITS[team], i) break end end
end
local out = {}
step(4)                                  -- nobody on the field yet: nobody falls
out.earlyFalls = (RULES.va_king_armada == 0) or (RULES.va_king_nullmercs == 0)
spawn(10, 0, COM); spawn(11, 1, COM); spawn(12, 2, COM); spawn(13, 2, COM); spawn(14, 1, TANK)
step(2)
kill(11, 1, 0)                           -- the company kills the Armada king; a tank does not count
step(2)
out.armadaFallen = RULES.va_king_armada == 0
kill(12, 2, 1)                           -- one Null Mercs commander down, one still standing
step(2)
out.mercsStillStand = RULES.va_king_nullmercs == 1
out.doneEarly = DONE
kill(13, 2, 0)
step(2)
out.done = DONE
out.json = GG.VA_KingsJson()
return (function(v)
  local parts = {}
  for k, w in pairs(v) do
    local s = type(w) == "string" and string.format("%%q", w) or tostring(w)
    if w == nil then s = "null" end
    parts[#parts + 1] = string.format("%%q:%%s", k, s)
  end
  return "{" .. table.concat(parts, ",") .. "}"
end)(out)
''' % (json.dumps(os.path.join(WS, "mod", "VerdanceAshes.sdd")), json.dumps(GADGET))

ok = True


def check(label, cond, detail=""):
    global ok
    print(("ok   " if cond else "FAIL ") + label + ("  " + json.dumps(detail) if not cond else ""))
    ok = ok and cond


o = run(CODE)
kings = json.loads(o["json"])
by = {k["faction"]: k for k in kings}
check("nobody falls before the commanders are on the field", o["earlyFalls"] is False, o)
check("a king falls when its team has no commander left", o["armadaFallen"] is True and by["armada"]["fallen"], o)
check("... credited to whoever killed it", by["armada"]["by"] == "ashwalkers" and by["nullmercs"]["by"] == "ashwalkers", kings)
check("a team with a commander still standing has not fallen", o["mercsStillStand"] is True and o.get("doneEarly") is None, o)
check("every rival down and ours standing: the objective is done", o.get("done") == "kings_fallen" and not by["ashwalkers"]["fallen"], o)
check("the facts carry the minute of each fall", isinstance(by["armada"]["minute"], (int, float)), kings)
print("KINGS " + ("PASSED" if ok else "FAILED"))
sys.exit(0 if ok else 1)
