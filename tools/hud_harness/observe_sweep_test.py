#!/usr/bin/env python3
"""Scouting adds up: run game_verdance_belief_observe.lua in real Lua 5.4 (ctypes).

One scout (sight radius 700) zig-zags across a 4096 map that is one big zone. A zone is
"seen" by what the company has looked at over the sweep, fading with time: the sweep must
read well over 0.6 (a real finding), a single glance must stay low.

    VA_WS=$PWD python3 tools/hud_harness/observe_sweep_test.py
"""
import ctypes, glob, json, os, sys

WS = os.environ.get("VA_WS") or os.getcwd()
GADGET = os.path.join(WS, "mod", "VerdanceAshes.sdd", "luarules", "gadgets", "game_verdance_belief_observe.lua")
L = ctypes.CDLL(glob.glob('/usr/lib/x86_64-linux-gnu/liblua5.4.so*')[0])
L.luaL_newstate.restype = ctypes.c_void_p
L.luaL_openlibs.argtypes = [ctypes.c_void_p]
L.luaL_loadstring.argtypes = [ctypes.c_void_p, ctypes.c_char_p]
L.lua_pcallk.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_void_p, ctypes.c_void_p]
L.lua_tolstring.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_void_p]
L.lua_tolstring.restype = ctypes.c_char_p

LUA = r'''
local GADGET = %s
SCOUT = { x = -9999, z = -9999 }
local SIGHT = 700
local zoneMap = { zones = { { zoneId = "FIELD", label = "Field", shape = "cells", cellGrid = { cols = 16, rows = 16 }, cells = { { 0, 256 } } } } }
VFS = { Include = function(p)
  if p:find("va_active") then return true end
  if p:find("zone_map_current") then return zoneMap end
  if p:find("va_current") then return { balance = { playerTeamID = 0 } } end
  return nil
end }
Game = { mapSizeX = 4096, mapSizeZ = 4096 }
GG = {}
gadget = {}
gadgetHandler = { IsSyncedCode = function() return true end }
Spring = {
  Echo = function(m) if tostring(m):find("ERR") then io.stderr:write(tostring(m) .. "\n") end end,
  GetGroundHeight = function() return 0 end,
  GetGaiaTeamID = function() return 99 end,
  GetTeamList = function() return { 0, 1 } end,
  GetTeamInfo = function(t) return t, 0, false, false, "", t end,
  GetAllUnits = function() return {} end,
  IsPosInLos = function(x, y, z, ally)
    return ally == 0 and (x - SCOUT.x) ^ 2 + (z - SCOUT.z) ^ 2 <= SIGHT * SIGHT
  end,
  GetPositionLosState = function() return false, false, false, false end,
  SetGameRulesParam = function() end,
  GetGameFrame = function() return 0 end,
}
local chunk = assert(loadfile(GADGET, "t", setmetatable({}, { __index = _G, __newindex = _G })))
chunk()
gadget:Initialize()
if gadget.GameStart then gadget:GameStart() end
local frame = -53  -- the gadget samples when frame %% 60 == 7
local function step(x, z) SCOUT.x, SCOUT.z = x, z; frame = frame + 60; gadget:GameFrame(frame) end
-- a glance: one sample at the corner
step(300, 300)
local glance = tonumber((GG.VA_ObservedZonesJson():match('"FIELD":([%%d%%.]+)'))) or 0
-- the sweep: zig-zag rows 1000 apart, 400 per sample (a scout's pace)
for _, z in ipairs({ 500, 1500, 2500, 3500 }) do
  for x = 0, 4096, 400 do step(x, z) end
end
SCOUT.x, SCOUT.z = -9999, -9999
step(-9999, -9999)
local swept = tonumber((GG.VA_ObservedZonesJson():match('"FIELD":([%%d%%.]+)'))) or 0
return string.format('{"glance":%%.3f,"swept":%%.3f}', glance, swept)
''' % json.dumps(GADGET)

st = L.luaL_newstate()
L.luaL_openlibs(st)
if L.luaL_loadstring(st, LUA.encode()) != 0 or L.lua_pcallk(st, 0, 1, 0, None, None) != 0:
    print("LUA ERROR", L.lua_tolstring(st, -1, None).decode())
    sys.exit(1)
r = json.loads(L.lua_tolstring(st, -1, None).decode())
ok = r["glance"] < 0.2 and r["swept"] >= 0.6
print(("ok   " if r["glance"] < 0.2 else "FAIL ") + f"a glance reads low ({r['glance']})")
print(("ok   " if r["swept"] >= 0.6 else "FAIL ") + f"a scout's sweep adds up to a real finding ({r['swept']})")
print("OBSERVE SWEEP " + ("PASSED" if ok else "FAILED"))
sys.exit(0 if ok else 1)
