#!/usr/bin/env python3
"""Drive the synced exfil gadget the way BAR does, in real Lua 5.4 (ctypes), with a tiny map.

The pad is the landing zone: a unit anywhere in it is going; an immobile turret is staying;
"manifest" and "extract:home" reach the gadget through GG.VA_ExfilCmd (the campaign gadget's
hand-off), not only through RecvLuaMsg, which an earlier gadget in BAR swallowed.

    VA_WS=$PWD python3 tools/hud_harness/exfil_gadget_test.py
"""
import ctypes, glob, json, os, sys

WS = os.environ.get("VA_WS") or os.getcwd()
GADGET = os.path.join(WS, "mod", "VerdanceAshes.sdd", "luarules", "gadgets", "game_verdance_exfil.lua")
ACTIVE = os.path.join(WS, "mod", "VerdanceAshes.sdd", "luarules", "configs", "va_active.lua")
L = ctypes.CDLL(glob.glob('/usr/lib/x86_64-linux-gnu/liblua5.4.so*')[0])
L.luaL_newstate.restype = ctypes.c_void_p
L.luaL_openlibs.argtypes = [ctypes.c_void_p]
L.luaL_loadstring.argtypes = [ctypes.c_void_p, ctypes.c_char_p]
L.lua_pcallk.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_void_p, ctypes.c_void_p]
L.lua_tolstring.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_void_p]; L.lua_tolstring.restype = ctypes.c_char_p

LUA = r'''
local GADGET, ACTIVE = %s, %s
-- 4x4 grid on a 4096 map: zone PAD = top two rows (cells 0..7), zone FAR = the rest.
local zoneMap = { mapId = "t", zones = {
  { zoneId = "PAD", label = "Landing", shape = "cells", cellGrid = { cols = 4, rows = 4 }, cells = { { 0, 8 } }, anchor = { x = 0.5, z = 0.25 } },
  { zoneId = "FAR", label = "Far Field", shape = "cells", cellGrid = { cols = 4, rows = 4 }, cells = { { 8, 8 } }, anchor = { x = 0.5, z = 0.75 } },
} }
local mission = { missionId = "t1", deploymentMapId = "t", deploymentZoneId = "PAD", zoneMap = zoneMap,
  pad = { zoneId = "PAD", x = 0.5, z = 0.25, radius = 300 }, exitDoorZoneId = "FAR" }
-- units: 1 hero near the pad point, 2 a unit at the zone's far corner (outside the old circle),
-- 3 an immobile turret in the pad zone (Solarium), 4 a unit in FAR, 9 an enemy in the pad zone.
local U = {
  [1] = { x = 2048, z = 1024, def = 1, team = 0, hero = "pavise" },
  [2] = { x = 100,  z = 100,  def = 1, team = 0 },
  [5] = { x = 300,  z = 300,  def = 1, team = 0, tag = "crew_escort_pavise_1" },  -- an escort: pack, not army
  [3] = { x = 3900, z = 1900, def = 2, team = 0, hero = "solarium" },
  [4] = { x = 2048, z = 3500, def = 1, team = 0 },
  [9] = { x = 300,  z = 1800, def = 1, team = 1 },
  [10] = { x = 600, z = 600, def = 2, team = 1 },  -- an enemy wall/turret in the pad zone: not "on the pad"
}
UnitDefs = { [1] = { name = "corthud", speed = 50, metalCost = 100 }, [2] = { name = "armnanotc", speed = 0, metalCost = 200 } }
Game = { mapSizeX = 4096, mapSizeZ = 4096 }
RULES, SENT, ENDED, GG = { va_dropped_heroes = "pavise,solarium,ketha" }, {}, {}, {}
GG.VA_EndSortie = function(kind) ENDED[#ENDED + 1] = kind end
VFS = { Include = function(p)
  if p:find("va_active") then return dofile(ACTIVE) end
  if p:find("va_current") then return mission end
  return nil
end }
Spring = {
  GetModOptions = function() return { va_campaign = "1" } end,
  Echo = function(...) end, Log = function() end,
  SetGameRulesParam = function(k, v) RULES[k] = v end, GetGameRulesParam = function(k) return RULES[k] end,
  GetGameFrame = function() return 300 end,
  GetTeamUnits = function(t) local o = {} for id, u in pairs(U) do if u.team == t then o[#o + 1] = id end end table.sort(o) return o end,
  GetUnitsInCylinder = function(x, z, r) local o = {} for id, u in pairs(U) do if (u.x - x)^2 + (u.z - z)^2 <= r * r then o[#o + 1] = id end end return o end,
  ValidUnitID = function(id) return U[id] ~= nil end, GetUnitIsDead = function() return false end,
  GetUnitPosition = function(id) local u = U[id]; return u.x, 0, u.z end,
  GetUnitDefID = function(id) return U[id].def end, GetUnitTeam = function(id) return U[id].team end,
  GetUnitRulesParam = function(id, k) local u = U[id]; if k == "va_hero_id" or k == "va_hero_name" then return u.hero end; if k == "va_package_tag" then return u.tag end end,
  AreTeamsAllied = function(a, b) return a == b end,
  GetUnitHealth = function() return 80, 100 end, GetUnitExperience = function() return 0 end,
  GetTeamList = function() return { 0, 1 } end, GetGaiaTeamID = function() return -1 end,
  GetMyTeamID = function() return 0 end, GetTeamInfo = function(t) return t, 0, false, false, "", t end,
  GetPlayerList = function() return { 0 } end, GetPlayerInfo = function() return "p", true, false, 0, 0 end,
  GetFeatureList = function() return {} end, GetAllFeatures = function() return {} end,
}
function SendToUnsynced(name, json) SENT[#SENT + 1] = { name, json } end
gadget = {}
gadgetHandler = { IsSyncedCode = function() return true end }
local chunk = assert(loadfile(GADGET))
assert(chunk() ~= false, "gadget stood down")
if gadget.Initialize then gadget:Initialize() end
if gadget.GameStart then gadget:GameStart() end
assert(GG.VA_ExfilCmd, "GG.VA_ExfilCmd not registered")
-- the once-a-second HUD scan (GameFrame) must run clean: it killed LuaRules in a playtest
for f = 1, 61 do gadget:GameFrame(f) end
assert(RULES.va_hud_heroes_json and RULES.va_hud_heroes_json:find('"dist"'), "hud scan published no heroes")
print("ok   hud scan runs and publishes heroes")
GG.VA_ExfilCmd("manifest")
assert(RULES.va_manifest_seq == 1 and type(RULES.va_manifest_json) == "string", "no manifest posted")
local m = RULES.va_manifest_json
local function has(pat, why) assert(m:find(pat, 1, true), why .. "\n" .. m) end
has('"going":{"heroes":[{"heroId":"pavise"', "hero in the pad zone goes")
has('"packUnits":{"corthud":1}', "an escort is counted as pack, not army")
has('"unitCount":2', "a unit at the zone's far corner (outside the old circle) goes, and the escort")
has('{"heroId":"solarium","name":"solarium","unitDef":"armnanotc"}]', "an immobile hero off the pad is packed up and lifts (Hearth was stranded)")
has('"staying":{"heroes":[]', "... and is not left behind as a person in the field")
has('"units":{"FAR":1}', "a unit outside the pad zone stays")
has('"enemyOnPad":1', "a mobile enemy anywhere in the pad zone is on the pad; a wall is not")
has('"dropped":["pavise","solarium","ketha"]', "the manifest names who dropped (Python buries whoever is nowhere)")
print("ok   manifest: pad is the landing zone; an immobile hero lifts from where it stands")
-- taking a door: once the objective is done the extraction moves onto it
assert(RULES.va_pad_zone == "PAD", "the pad starts on the landing zone")
RULES.va_objective_complete = 1
for f = 62, 92 do gadget:GameFrame(f) end
assert(RULES.va_pad_zone == "FAR" and RULES.va_pad_moved == 1, "the pad did not move to the exit door")
GG.VA_ExfilCmd("manifest")
m = RULES.va_manifest_json
has('"units":{"corthud":1}', "on the exit door, the unit standing there goes")
print("ok   taking a door: the extraction moves onto it once the objective is done")
GG.VA_ExfilCmd("extract:home")
assert(ENDED[1] == "extracted", "extract did not end the sortie")
print("ok   extract through the campaign hand-off ends the sortie")
'''

def main():
    st = L.luaL_newstate(); L.luaL_openlibs(st)
    out = []
    src = LUA % (json.dumps(GADGET), json.dumps(ACTIVE))
    # capture print
    src = "local __p = print; print = function(...) __p(...) end\n" + src
    rc = L.luaL_loadstring(st, src.encode()) or L.lua_pcallk(st, 0, 0, 0, None, None)
    if rc:
        print("FAIL", L.lua_tolstring(st, -1, None).decode()); return 1
    return 0

if __name__ == "__main__":
    sys.exit(main())
