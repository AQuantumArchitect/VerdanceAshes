#!/usr/bin/env python3
"""The Halberd's heat ray, in real Lua 5.4 (ctypes) against engine stubs.

Runs game_verdance_heatray.lua as shipped and drives it frame by frame: the ray's damage and reach
follow the energy bank, a pulse draws from the bank and leaves the target burning (for as long as
the bank allowed), veterancy's reach rides under the bank's, and a dead Halberd is let go.

    VA_WS=$PWD python3 tools/hud_harness/heat_ray_test.py
"""
import ctypes, glob, json, os, sys

WS = os.environ.get("VA_WS") or os.getcwd()
GADGETS = os.path.join(WS, "mod", "VerdanceAshes.sdd", "luarules", "gadgets")
GADGET = os.path.join(GADGETS, "game_verdance_heatray.lua")
CURVE = os.path.join(GADGETS, "include", "va_heat_ray.lua")

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

local HAL, FOE = 50, 99
local bankEnergy, bankStorage = 0, 1000
local reloadState, vet = 0, 1
local alive = { [HAL] = true, [FOE] = true }
local log = { used = {}, damages = {}, ranges = {}, maxRanges = {}, hurt = {} }
local params = {}

gadget = {}
gadgetHandler = { IsSyncedCode = function() return true end }
VFS = { Include = function(p)
  if p:find("va_active") then return true end
  if p:find("va_heat_ray") then return dofile(@CURVE@) end
  error("unexpected include " .. p)
end }
UnitDefNames = { va_halberd = { id = 7 } }
UnitDefs = { [7] = { weapons = { { weaponDef = 70 } } } }
WeaponDefs = { [70] = { range = 330, customParams = { va_ray_damage = "190" } } }
Spring = {
  GetAllUnits = function() return { HAL } end,
  GetUnitDefID = function(u) return u == HAL and 7 or 1 end,
  GetUnitTeam = function() return 0 end,
  GetTeamResources = function() return bankEnergy, bankStorage end,
  UseTeamResource = function(_, _, n) log.used[#log.used + 1] = n; bankEnergy = bankEnergy - n; return true end,
  GetUnitWeaponState = function() return reloadState end,
  SetUnitWeaponState = function(_, _, k, v) if k == "range" then log.ranges[#log.ranges + 1] = v end return true end,
  SetUnitWeaponDamages = function(_, _, k, v) log.damages[#log.damages + 1] = v return true end,
  SetUnitMaxRange = function(_, v) log.maxRanges[#log.maxRanges + 1] = v end,
  GetUnitWeaponTarget = function() return 1, false, FOE end,
  GetUnitRulesParam = function(_, k) if k == "va_vet_range_mult" then return vet end end,
  SetUnitRulesParam = function(_, k, v) params[k] = v end,
  ValidUnitID = function(u) return alive[u] == true end,
  GetUnitIsDead = function(u) return alive[u] ~= true end,
  AddUnitDamage = function(u, d, _, by) log.hurt[#log.hurt + 1] = { u, d, by } end,
  GetUnitPosition = function() return 100, 10, 100 end,
  SpawnCEG = function() end,
}
dofile(@GADGET@)
gadget:Initialize()
local function frames(a, b) for f = a, b do gadget:GameFrame(f) end end
local function last(t) return t[#t] end
'''.replace("@CURVE@", json.dumps(CURVE)).replace("@GADGET@", json.dumps(GADGET))

SCENES = PRELUDE + r'''
local out = {}

-- an empty small bank
bankEnergy, bankStorage = 0, 1000
frames(1, 10)
out.emptyDamage, out.emptyRange, out.emptyCharge = last(log.damages), last(log.ranges), params.va_ray_charge

-- a full 4000 bank
bankEnergy, bankStorage = 4000, 4000
frames(11, 20)
out.fullDamage, out.fullRange, out.fullBurn, out.maxRange = last(log.damages), last(log.ranges), params.va_ray_burn_seconds, last(log.maxRanges)

-- a bigger economy at half: charge is a fraction of the deeper bank
bankEnergy, bankStorage = 10000, 20000
frames(21, 30)
out.halfCharge = params.va_ray_charge

-- veterancy reach rides under the bank's
bankEnergy, bankStorage = 4000, 4000
vet = 1.2
frames(31, 40)
out.vetRange = last(log.ranges)
vet = 1

-- a pulse at full bank: draws 6% of the bank and leaves the target burning
log.used, log.hurt = {}, {}
bankEnergy, bankStorage = 4000, 4000
frames(41, 50)
reloadState = 60
frames(51, 60)
out.drawn = log.used[1]
frames(61, 160)
out.burnTicks, out.burnEach, out.burnBy = #log.hurt, log.hurt[1] and log.hurt[1][2], log.hurt[1] and log.hurt[1][3]

-- a pulse with only 100 in the bank takes what there is, and burns shorter
log.used, log.hurt = {}, {}
bankEnergy, bankStorage = 100, 4000
reloadState = 100
frames(161, 170)
out.thinDrawn = log.used[1]
frames(171, 260)
out.thinTicks = #log.hurt

-- the Halberd dies: no more retuning
alive[HAL] = false
local before = #log.damages
frames(261, 300)
out.afterDeath = #log.damages - before
return enc(out)
'''

ok = True


def check(label, cond, detail=""):
    global ok
    print(("ok   " if cond else "FAIL ") + label + ("  " + json.dumps(detail) if not cond else ""))
    ok = ok and cond


def near(a, b, tol=0.5):
    return a is not None and abs(a - b) <= tol


s = run(SCENES)
check("an empty bank runs the ray at 55% damage", near(s["emptyDamage"], 190 * 0.55), s)
check("an empty bank shortens it to 85% reach", near(s["emptyRange"], 330 * 0.85), s)
check("charge reads 0 for an empty bank", s["emptyCharge"] == 0, s)
check("a full bank runs it at 220% damage", near(s["fullDamage"], 190 * 2.2), s)
check("a full bank reaches 140%", near(s["fullRange"], 330 * 1.4) and near(s["maxRange"], 330 * 1.4), s)
check("a full bank burns the target for 3s", near(s["fullBurn"], 3.0, 0.01), s)
check("charge is a fraction of the deeper bank", near(s["halfCharge"], 0.5, 0.001), s)
check("veterancy's reach rides under the bank's", near(s["vetRange"], 330 * 1.4 * 1.2), s)
check("a pulse draws 6% of the bank", near(s["drawn"], 240, 0.01), s)
check("it burns for 3s at 10-frame ticks", s["burnTicks"] in (8, 9, 10), s)
check("each tick is the pulse's damage x burn rate x 1/3s", near(s["burnEach"], 190 * 0.2 * 2.2 / 3, 0.2), s)
check("the burn is credited to the Halberd", s["burnBy"] == 50, s)
check("a thin bank gives what it has", near(s["thinDrawn"], 100, 0.01), s)
check("and burns for less time", 0 < s["thinTicks"] < s["burnTicks"], s)
check("a dead Halberd is let go", s["afterDeath"] == 0, s)
print("HEAT RAY " + ("PASSED" if ok else "FAILED"))
sys.exit(0 if ok else 1)
