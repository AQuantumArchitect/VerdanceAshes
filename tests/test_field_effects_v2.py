#!/usr/bin/env python3
"""Field effects v2 (2026-10-29): a stronger self effect, a weaker aura that reaches the company members
who match it, bonds that boost it, rivals that rub against it, and home ground.

The data checks read data/story/field_effects.json; the behaviour checks run the real
va_field_engine.lua in Lua 5.4 against a stubbed Spring."""
from __future__ import annotations

import collections
import ctypes
import glob
import json
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
S = ROOT / "data" / "story"
INCLUDE = ROOT / "mod" / "VerdanceAshes.sdd" / "luarules" / "gadgets" / "include"
FX = json.loads((S / "field_effects.json").read_text(encoding="utf-8"))
H = FX["heroes"]
LIBS = glob.glob("/usr/lib/x86_64-linux-gnu/liblua5.4.so*")


# ---------------------------------------------------------------- the data

def test_the_lua_is_generated_and_the_data_checks_out():
    out = subprocess.run([sys.executable, str(ROOT / "tools/sync_field_effects.py"), "--check"], capture_output=True, text=True)
    assert out.returncode == 0, out.stdout + out.stderr


def test_every_hero_has_a_self_effect_and_an_aura_within_the_ceilings():
    packs = json.loads((S / "crew_packs.json").read_text(encoding="utf-8-sig"))["heroes"]
    assert set(H) == set(packs)
    for hid, h in H.items():
        assert 0.20 <= h["self"]["bonus"] <= 0.40, hid
        for a in h["auras"]:
            if a["kind"] == "stat":
                assert a["bonus"] <= FX["rules"]["auraCap"], hid
            assert a["note"], hid


def test_the_effects_are_diverse():
    selfs = collections.Counter(h["self"]["stat"] for h in H.values())
    assert len(selfs) == 8 and max(selfs.values()) <= 16, selfs          # no stat is most of the roster any more
    conditional = sum(1 for h in H.values() if h["self"].get("when") or h["self"].get("scale"))
    assert conditional >= 28, conditional                                # nearly half react to the fight
    kinds = collections.Counter(a["kind"] for h in H.values() for a in h["auras"])
    assert set(kinds) == {"stat", "income", "xp", "repair"}
    conds = {c for h in H.values() for c in [h["self"].get("when")] + [a.get("when") for a in h["auras"]] if c}
    assert conds == set(FX["conditions"])


def test_every_hero_has_axes_now():
    um = {h["heroId"]: h for h in json.loads((S / "hero_umwelt.json").read_text(encoding="utf-8"))["heroes"]}
    for hid in H:
        assert any(abs(v) > 0 for v in um[hid]["axes"].values()), hid


def test_the_owner_calls_still_hold():
    # scouts see, artillery reaches, the walkers hit wide, the fast ones fire fast; Hearth feeds fusions
    st = {k: h["self"]["stat"] for k, h in H.items()}
    assert all(st[k] == "vision" for k in ("spoke", "tick", "noctua", "veil", "volt", "rumor"))
    assert all(st[k] == "range" for k in ("halq", "mira", "vale"))
    assert all(st[k] == "splash" for k in ("fatboy", "bro"))
    assert all(st[k] == "reload" for k in ("gale", "yeva", "hundred"))
    assert H["hearth"]["auras"][0]["match"] == {"kinds": ["fusion"]}
    assert H["pavise"]["auras"][0]["match"]["units"] == ["armwar"]


# ---------------------------------------------------------------- the engine, in Lua

STUB = r'''
local units = {}          -- id -> {def=, x=, z=, vx=, hp=, max=, team=, rules={}, xp=}
local defs = {}
local resources = { metal = 0, energy = 0 }
local los = {}
UnitDefs = {}
WeaponDefs = { [1] = { range = 500, reload = 2, damageAreaOfEffect = 48 } }
local function def(id, t) t.name = t.name or ("d" .. id); t.weapons = t.weapons or { { weaponDef = 1 } }; UnitDefs[id] = t end
def(1, { name = "armwar" })                        -- a Centurion
def(2, { name = "armfig", canFly = true })          -- an air unit
def(3, { name = "armpw" })                          -- a plain bot
def(4, { name = "armfus", isBuilding = true, energyMake = 1000, weapons = {} })
def(5, { name = "armcom" })
GG = {}
Spring = {
  GetTeamUnits = function(team) local out = {} for id, u in pairs(units) do if u.team == team then out[#out + 1] = id end end table.sort(out) return out end,
  ValidUnitID = function(id) return units[id] ~= nil end,
  GetUnitIsDead = function(id) return false end,
  GetUnitPosition = function(id) local u = units[id] return u.x, 0, u.z end,
  GetUnitDefID = function(id) return units[id].def end,
  GetUnitRulesParam = function(id, k) return units[id].rules[k] end,
  SetUnitRulesParam = function(id, k, v) units[id].rules[k] = v end,
  GetUnitVelocity = function(id) return units[id].vx or 0, 0, 0 end,
  GetUnitHealth = function(id) local u = units[id] return u.hp, u.max end,
  SetUnitHealth = function(id, v) units[id].hp = v end,
  SetUnitMaxHealth = function(id, v) units[id].max = v end,
  GetUnitNearestEnemy = function(id) return units[id].enemy end,
  IsUnitInLos = function(id, at) return los[id] == true end,
  GetAllyTeamList = function() return { 0, 1 } end,
  GetTeamInfo = function(team) return team, 0, false, false, "", team end,
  GetGaiaTeamID = function() return 9 end,
  GetGroundHeight = function(x, z) return (x < 0) and -20 or 50 end,
  GetUnitExperience = function(id) return units[id].xp or 0 end,
  SetUnitExperience = function(id, v) units[id].xp = v end,
  AddTeamResource = function(team, r, v) resources[r] = resources[r] + v end,
  SetUnitWeaponState = function(id, i, k, v) units[id].rules["w_" .. k] = v end,
  SetUnitMaxRange = function() end,
  SetUnitSensorRadius = function(id, k, v) units[id].rules["los_" .. k] = v end,
  SetUnitWeaponDamages = function(id, i, k, v) units[id].rules["dmg_" .. k] = v end,
  SetUnitResourcing = function(id, k, v) units[id].rules["res_" .. k] = v end,
  SetUnitBuildSpeed = function(id, v) units[id].rules.bp = v end,
}
local Tags = dofile(INCLUDE .. "va_hero_tags.lua")
local E = dofile(INCLUDE .. "va_field_engine.lua")
E.Tags = Tags
local heroes = {}
local function add(id, defId, x, z, extra)
  units[id] = { def = defId, x = x, z = z, hp = 1000, max = 1000, team = 0, rules = {} }
  for k, v in pairs(extra or {}) do units[id][k] = v end
  return units[id]
end
local function hero(hid, id, defId, x, z, xp, extra)
  add(id, defId, x, z, extra)
  heroes[hid] = { unitID = id, peakXp = xp or 2.4 }
end
local function mate(id, defId, lead, x, z, extra)
  local u = add(id, defId, x, z, extra)
  u.rules.va_pack_leader = lead
  return u
end
local function tick(mapId) return E.tick({ teamID = 0, heroes = heroes, mapId = mapId, dt = 1 }) end
local function fx(id, stat) return units[id].rules["va_fx_" .. stat] or 1 end
local function reset() for k in pairs(units) do units[k] = nil end for k in pairs(heroes) do heroes[k] = nil end
  for k in pairs(E.applied) do E.applied[k] = nil end resources.metal = 0 resources.energy = 0 for k in pairs(los) do los[k] = nil end end
'''


def _lua(body: str) -> dict:
    if not LIBS:
        raise unittest.SkipTest("liblua5.4 is not installed")
    L = ctypes.CDLL(LIBS[0])
    L.luaL_newstate.restype = ctypes.c_void_p
    L.luaL_openlibs.argtypes = [ctypes.c_void_p]
    L.luaL_loadstring.argtypes = [ctypes.c_void_p, ctypes.c_char_p]
    L.lua_pcallk.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_void_p, ctypes.c_void_p]
    L.lua_tolstring.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_void_p]
    L.lua_tolstring.restype = ctypes.c_char_p
    src = "local INCLUDE = %s\n" % json.dumps(str(INCLUDE) + "/") + STUB + body
    st = L.luaL_newstate()
    L.luaL_openlibs(st)
    err = L.luaL_loadstring(st, src.encode()) or L.lua_pcallk(st, 0, 1, 0, None, None)
    assert not err, L.lua_tolstring(st, -1, None)
    return json.loads(L.lua_tolstring(st, -1, None).decode())


def test_the_self_effect_reaches_the_pack_and_waits_on_its_condition():
    r = _lua(r'''
hero("rusk", 10, 3, 100, 100)          -- reload +30% while still
mate(11, 3, "rusk", 120, 100)
local a = { still = fx(11, "reload") }
units[10].vx = 3                       -- moving
tick()
a.moving = fx(11, "reload")
units[10].vx = 0
tick()
a.back = fx(11, "reload")
return string.format('{"still":%s,"moving":%s,"back":%s,"first":%s}', a.still, a.moving, a.back, (function() tick() return fx(11,"reload") end)())
'''.replace('local a = { still = fx(11, "reload") }', 'tick()\nlocal a = { still = fx(11, "reload") }'))
    assert abs(r["still"] - 1 / 1.30) < 1e-3 and r["moving"] == 1 and abs(r["back"] - 1 / 1.30) < 1e-3


def test_nothing_green_and_all_of_it_at_full_xp():
    r = _lua(r'''
hero("fatboy", 10, 3, 0, 0, 0.0)
tick()
local green = fx(10, "splash")
heroes.fatboy.peakXp = 2.4
tick()
return string.format('{"green":%s,"full":%s}', green, fx(10, "splash"))
''')
    assert r["green"] == 1 and abs(r["full"] - 1.40) < 1e-3


def test_an_aura_reaches_only_what_matches_and_the_shared_part_is_capped():
    r = _lua(r'''
hero("pavise", 10, 1, 0, 0)            -- +15% hp to Centurions and holding allies within 520
add(20, 1, 100, 0)                      -- a plain Centurion, no hero
add(21, 3, 100, 0)                      -- a plain bot: no match
add(22, 1, 2000, 0)                     -- a Centurion out of range
hero("nox", 30, 3, 50, 0)               -- hold/pad: matches Pavise; Nox's own aura (+10% hp to pad/hold when still) is on too
add(23, 4, 60, 0)                        -- a fusion: a structure = pad and hold
tick()
return string.format('{"cent":%s,"bot":%s,"far":%s,"nox":%s,"fus":%s}', fx(20,"hp"), fx(21,"hp"), fx(22,"hp"), fx(30,"hp"), fx(23,"hp"))
''')
    assert abs(r["cent"] - 1.15) < 1e-3 and r["bot"] == 1 and r["far"] == 1
    assert abs(r["fus"] - 1.15) < 1e-3                       # Pavise 15% + Nox 10% on the fusion, capped at 15%
    assert abs(r["nox"] - (1 + 0.30 + 0.15)) < 1e-3          # Nox's own +30% (still) plus Pavise's capped 15%


def test_bonds_boost_the_aura_and_rivals_feel_friction():
    ties = {}
    web = json.loads((S / "support_web.json").read_text(encoding="utf-8-sig"))
    ally = {"bond", "attract", "sibling", "mentor", "mirror"}
    for e in web["edges"]:
        if e.get("authored"):
            ties.setdefault(e["a"], {})[e["b"]] = e["polarity"] in ally
            ties.setdefault(e["b"], {})[e["a"]] = e["polarity"] in ally
    # Kettle: +10% hp to everyone near. Find a bonded and a rival hero of Kettle's.
    friend = next(k for k, v in ties["kettle"].items() if v)
    rival = next(k for k, v in ties["kettle"].items() if not v)
    stranger = next(k for k in H if k not in ties["kettle"] and k != "kettle" and H[k]["self"]["stat"] != "hp")
    body = r'''
hero("kettle", 10, 3, 0, 0)
hero("%s", 20, 3, 100, 0, 0.0)
hero("%s", 30, 3, 0, 100, 0.0)
hero("%s", 40, 3, 100, 100, 0.0)
tick()
return string.format('{"friend":%%s,"rival":%%s,"stranger":%%s}', fx(20,"hp"), fx(30,"hp"), fx(40,"hp"))
''' % (friend, rival, stranger)
    r = _lua(body)
    assert abs(r["stranger"] - 1.10) < 1e-3
    assert abs(r["friend"] - 1.15) < 1e-3             # 10% x1.5 = 15%, at the ceiling
    assert abs(r["rival"] - 0.96) < 1e-3               # -40% of the aura


def test_the_effect_leaves_when_the_hero_does():
    r = _lua(r'''
hero("kettle", 10, 3, 0, 0)
add(20, 3, 100, 0)
tick()
local on = fx(20, "hp")
units[10] = nil
heroes.kettle = nil
tick()
return string.format('{"on":%s,"off":%s}', on, fx(20, "hp"))
''')
    assert abs(r["on"] - 1.10) < 1e-3 and r["off"] == 1


def test_income_xp_and_repair():
    r = _lua(r'''
hero("grath", 10, 3, 0, 0)          -- 0.6 metal/s per ledger hero in the company (Grath is one)
hero("veil", 20, 3, 3000, 0)        -- ledger, no tie to Grath (his rival the Auditor would not pay)
hero("ketha", 30, 3, 6000, 0)       -- repair 1.5%/s below half health
add(31, 3, 6100, 0, { hp = 300 })
add(32, 3, 6100, 0, { hp = 900 })
hero("mask", 40, 3, 9000, 0)        -- veterancy to allies near
add(41, 3, 9100, 0)
tick()
return string.format('{"metal":%s,"hurt":%s,"fine":%s,"xp":%s}', resources.metal, units[31].hp, units[32].hp, units[41].xp)
''')
    assert abs(r["metal"] - 1.2) < 1e-6                           # Grath and Veil, 0.6 each
    assert r["hurt"] > 300 and r["fine"] == 900 and r["xp"] > 0


def test_home_ground():
    r = _lua(r'''
return string.format('{"miraEye":%s,"miraGreen":%s,"yevaJungle":%s,"ketha":%s}',
  E.terrainFactor("mira", "eye_of_horus"), E.terrainFactor("mira", "greenest_fields"),
  E.terrainFactor("yeva", "the_rock_jungle"), E.terrainFactor("ketha", nil))
''')
    assert r["miraEye"] > 1.3 and r["miraGreen"] == 1 and r["yevaJungle"] > 1.15 and r["ketha"] == 1


def test_conditions_on_water_unseen_and_crowd():
    r = _lua(r'''
hero("triton", 10, 3, -100, 0)    -- speed +30% on water (ground below 0 at x<0)
hero("yeva", 20, 3, 500, 0)        -- reload +35% unseen
los[20] = true
hero("arc", 30, 3, 9000, 0)        -- reload +10% to allies near once three or more are close
add(31, 3, 9050, 0) add(32, 3, 9060, 0)
tick()
local a = { tri = fx(10, "speed"), seen = fx(20, "reload"), few = fx(31, "reload") }
hero("rusk", 34, 3, 9080, 0) hero("mason", 35, 3, 9090, 0) hero("loom", 36, 3, 9070, 0)
los[20] = false
tick()
return string.format('{"tri":%s,"seen":%s,"unseen":%s,"few":%s,"crowd":%s}', a.tri, a.seen, fx(20, "reload"), a.few, fx(31, "reload"))
''')
    assert r["tri"] > 1.29 and r["seen"] == 1 and abs(r["unseen"] - 1 / 1.35) < 1e-3
    assert r["few"] == 1 and r["crowd"] < 1 / 1.09         # three packs close: the choir sings (a bond may lift it)


# ---------------------------------------------------------------- field fit steers who you meet

def test_field_fit_draws_the_strangers_the_party_s_auras_would_reach():
    sys.path.insert(0, str(ROOT / "tools"))
    from collections import namedtuple
    from verdance.company import encounters as EN
    axes = {h["heroId"]: h["axes"] for h in json.loads((S / "hero_umwelt.json").read_text(encoding="utf-8"))["heroes"]}
    assert EN.field_fit("veil", "commando", H, axes) >= 1          # Veil's haze reaches fog allies; Cinder Hook is fog
    assert EN._aura_reaches(H["kettle"]["auras"][0], ["hold"], {}) is False  # an aura on everyone says nothing about fit
    fake = type("E", (), {"Relation": namedtuple("Relation", "a b polarity weight")})
    st = {"company": {"core": ["ketha"], "band": ["yeva", "veil", "vale"], "joinedLater": []}, "roster": {"heroes": []}}
    rel = EN._relations(fake, st, ROOT)
    fit = [r for r in rel if r.polarity == "field_fit"]
    web = json.loads((S / "support_web.json").read_text(encoding="utf-8-sig"))
    written = {frozenset((e["a"], e["b"])) for e in web["edges"] if e.get("authored")}
    assert fit and all(frozenset((r.a, r.b)) not in written for r in fit)
    assert all(r.a in ("ketha", "yeva", "veil", "vale") and r.weight <= 0.4 + 1e-9 for r in fit)
    assert EN.rules(ROOT)["fieldFit"]["weight"] == 0.2
