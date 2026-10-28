#!/usr/bin/env python3
"""The field-effect pass (owner, 2026-10-24): one thematic tag per hero, nothing at no XP, named
heroes at 2× health, and both units of the Javelin and Turtle pairs named."""
from __future__ import annotations

import ctypes
import glob
import json
import re
from pathlib import Path

import unittest

ROOT = Path(__file__).resolve().parents[1]
INCLUDE = ROOT / "mod" / "VerdanceAshes.sdd" / "luarules" / "gadgets" / "include"
LIBS = glob.glob('/usr/lib/x86_64-linux-gnu/liblua5.4.so*')


def _fields() -> dict:
    """{heroId: [label, stat, mult at 0 XP, mult at 2.4 XP]} from va_hero_tags.lua, run in Lua."""
    if not LIBS:
        raise unittest.SkipTest("liblua5.4 is not installed")
    L = ctypes.CDLL(LIBS[0])
    L.luaL_newstate.restype = ctypes.c_void_p
    L.luaL_openlibs.argtypes = [ctypes.c_void_p]
    L.luaL_loadstring.argtypes = [ctypes.c_void_p, ctypes.c_char_p]
    L.lua_pcallk.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_void_p, ctypes.c_void_p]
    L.lua_tolstring.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_void_p]
    L.lua_tolstring.restype = ctypes.c_char_p
    src = r'''
local M = dofile(%s)
local rows = {}
for id in pairs(M.HERO_DEFAULTS) do
  local r = M.resolve(M.collectFromHero({ traits = { "saint", "captain" } }, {}, id))
  local s = r.primaryStat
  rows[#rows + 1] = string.format('"%%s":["%%s","%%s",%%.4f,%%.4f]', id, r.labels[1], s, M.composeField(r, 0)[s], M.composeField(r, 2.4)[s])
end
return "{" .. table.concat(rows, ",") .. "}"
''' % json.dumps(str(INCLUDE / "va_hero_tags.lua"))
    st = L.luaL_newstate()
    L.luaL_openlibs(st)
    assert not (L.luaL_loadstring(st, src.encode()) or L.lua_pcallk(st, 0, 1, 0, None, None)), L.lua_tolstring(st, -1, None)
    return json.loads(L.lua_tolstring(st, -1, None).decode())


def test_every_hero_has_one_field_effect():
    heroes = set(json.loads((ROOT / "data" / "story" / "crew_packs.json").read_text(encoding="utf-8-sig"))["heroes"])
    fields = _fields()
    assert set(fields) == heroes
    assert all(row[1] for row in fields.values())


def test_field_effects_are_nothing_at_no_xp():
    for hid, (_label, _stat, at0, at24) in _fields().items():
        assert at0 == 1.0, hid
        assert at24 != 1.0, hid


def test_field_effects_match_the_hero():
    f = {hid: row[1] for hid, row in _fields().items()}
    for hid in ("halq", "mira", "vale"):                # artillery reaches farther
        assert f[hid] == "range", hid
    for hid in ("ceil", "gale", "yeva"):                # Roughnecks, Cutlasses, Whisper fire faster
        assert f[hid] == "reload", hid
    for hid in ("spoke", "tick", "noctua", "veil", "volt", "rumor"):   # scouts see farther
        assert f[hid] == "vision", hid
    for hid in ("fatboy", "bro"):                       # the siege walkers hit wider
        assert f[hid] == "splash", hid


def test_named_heroes_are_twice_as_tough():
    import campaign_lua
    src = campaign_lua.source()
    assert re.search(r"^VA_HERO_HP_MULT = 2\.0$", src, re.M)
    assert "VA_HERO_HP_MULT or 3.0" not in src


def test_the_pairs_are_both_named():
    packs = json.loads((ROOT / "data" / "story" / "crew_packs.json").read_text(encoding="utf-8-sig"))["heroes"]
    assert (packs["verse"]["fieldName"], packs["verse"]["partners"]) == ("Verse", ["Adder"])
    assert (packs["anvil"]["fieldName"], packs["anvil"]["partners"]) == ("Anvil", ["Mire"])
    lua = (INCLUDE / "va_crew_roster.lua").read_text(encoding="utf-8")
    assert 'partners = { "Adder" }' in lua and 'partners = { "Mire" }' in lua


def test_proper_names():
    roster = {h["heroId"]: h["name"] for h in json.loads((ROOT / "data" / "story" / "hero_roster.json").read_text(encoding="utf-8-sig"))["heroes"]}
    for hid in ("fatboy", "halbard", "consul", "twitch", "spoke", "tick", "noctua"):
        assert roster[hid] not in ("Fatboy Contract", "Halbard", "Armada Consul", "Twitcher", "Spoke", "Tick Stream", "Noctua Bay"), hid
