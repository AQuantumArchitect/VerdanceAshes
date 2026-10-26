#!/usr/bin/env python3
"""Saint Kettle's missiles (owner, 2026-10-25): her long-range anti-air missile (not the rapid spray)
is radar-guided and carries eyes. The gadget runs in tools/hud_harness/kettle_test.py; this guards
the unit and the wiring."""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
MOD = ROOT / "mod" / "VerdanceAshes.sdd"
UNIT = (MOD / "units" / "va_kettle.lua").read_text(encoding="utf-8")
STORY = ROOT / "data" / "story"


def _json(name: str) -> dict:
    return json.loads((STORY / name).read_text(encoding="utf-8-sig"))


def _weapon(name: str) -> str:
    body = UNIT.split("weapondefs = {", 1)[1]
    return body.split(f"{name} = {{", 1)[1].split("\n\t\t\t},", 1)[0]


def _num(src: str, key: str) -> float:
    return float(re.search(rf"\b{key} = ([0-9.]+)", src).group(1))


def test_only_the_long_range_missile_is_radar_guided_and_sees():
    lr, sr = _weapon("longrangemissile"), _weapon("shortrangemissile")
    assert 'va_radar_lock = "1"' in lr and "va_sight_radius" in lr
    assert "va_radar_lock" not in sr and "va_sight_radius" not in sr


def test_the_long_range_missile_reaches_1200_and_hits_ground_and_air():
    lr = _weapon("longrangemissile")
    assert _num(lr, "range") == 1200 and "canattackground = true" in lr
    assert _num(lr, "default") > 0 and _num(lr, "vtol") > 0
    w1 = UNIT.split("weapons = {", 1)[1].split("[2] = {", 1)[0]
    assert 'def = "LONGRANGEMISSILE"' in w1 and "VTOL" not in w1
    assert _num(_weapon("shortrangemissile"), "range") == 880


def test_she_is_still_an_archangel():
    assert _num(UNIT, "health") == 2200 and _num(UNIT, "metalcost") == 520
    assert 'objectname = "Units/ARMAAK.s3o"' in UNIT and 'name = "Archangel"' in UNIT
    assert 'def = "LONGRANGEMISSILE"' in UNIT and 'def = "SHORTRANGEMISSILE"' in UNIT


def test_kettle_drives_the_new_unit_everywhere():
    assert _json("crew_packs.json")["heroes"]["kettle"]["unitDef"] == "va_kettle"
    assert next(h for h in _json("hero_roster.json")["heroes"] if h["heroId"] == "kettle")["unitDef"] == "va_kettle"
    assert next(h for h in _json("hero_codex.json")["heroes"] if h["heroId"] == "kettle")["unitDef"] == "va_kettle"
    lua = (MOD / "luarules" / "gadgets" / "include" / "va_crew_roster.lua").read_text(encoding="utf-8")
    assert 'unitDef = "va_kettle"' in lua.split("kettle = {", 1)[1].split("\n  },", 1)[0]
    assert _json("crew_packs.json")["chassis"]["va_kettle"]["label"] == "Archangel"
    js = (ROOT / "app" / "showoff" / "crew_packs.embed.js").read_text(encoding="utf-8-sig")
    assert '"va_kettle": {' in js


def test_the_new_unit_costs_what_the_archangel_did():
    u = _json("unit_costs.json")
    assert u["units"]["va_kettle"] == u["units"]["armaak"] and u["names"]["va_kettle"] == "Archangel"


def test_a_save_made_on_the_stock_archangel_moves_onto_hers(tmp_path=None):
    import json as _j, tempfile
    import rename_heroes_v1 as r
    state = {"characters": {"kettle": {"unitDef": "armaak", "name": "Saint Kettle"}},
             "fieldPool": {"kettle": {"unitDef": "armaak", "name": "Saint Kettle"}},
             "roster": {"cadreXp": {"armaak": {"xp": 1.0}}, "heroes": [{"heroId": "kettle", "unitDef": "armaak", "name": "Saint Kettle"}]}}
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "campaign_state.json"
        p.write_text(_j.dumps(state), encoding="utf-8")
        r.rename_state(p)
        out = _j.loads(p.read_text(encoding="utf-8"))
    assert out["characters"]["kettle"]["unitDef"] == "va_kettle"
    assert out["roster"]["heroes"][0]["unitDef"] == "va_kettle"
    assert out["roster"]["cadreXp"]["va_kettle"] == {"xp": 1.0} and "armaak" in out["roster"]["cadreXp"]
