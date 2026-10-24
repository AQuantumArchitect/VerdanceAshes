#!/usr/bin/env python3
"""Halbard's heat ray (owner, 2026-10-24): her own Halberd with a pulsing heat ray in place of the
green cannon, fed by the company's energy bank. The gadget itself runs in
tools/hud_harness/heat_ray_test.py; this guards the wiring and the curve."""
from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MOD = ROOT / "mod" / "VerdanceAshes.sdd"
UNIT = (MOD / "units" / "va_halberd.lua").read_text(encoding="utf-8")
CURVE = (MOD / "luarules" / "gadgets" / "include" / "va_heat_ray.lua").read_text(encoding="utf-8")
STORY = ROOT / "data" / "story"


def _json(name: str) -> dict:
    return json.loads((STORY / name).read_text(encoding="utf-8-sig"))


def _num(src: str, name: str) -> float:
    return float(re.search(rf"\b{name} = ([0-9.]+)", src).group(1))


def test_the_halberd_carries_a_pulsing_heat_ray_not_the_green_cannon():
    assert 'weapontype = "BeamLaser"' in UNIT
    assert 'def = "VA_HEAT_RAY"' in UNIT and "cor_canlaser" not in UNIT.lower()
    # Helios-style: a long beam and a slow reload make it pulse
    assert _num(UNIT, "beamtime") >= 0.5 and _num(UNIT, "reloadtime") >= 1.0


def test_the_baseline_damage_is_stated_once():
    assert re.search(r'va_ray_damage = "190"', UNIT) and re.search(r"default = 190,", UNIT)


def test_the_curve_runs_from_weak_and_short_to_strong_and_long():
    lo = {k: [float(x) for x in re.search(rf"M\.{k} = \{{ ([0-9.]+), ([0-9.]+) \}}", CURVE).groups()]
          for k in ("DAMAGE", "RANGE", "BURN_SECONDS")}
    for k, (a, b) in lo.items():
        assert 0 < a < b, k
    assert lo["DAMAGE"][0] < 1.0 < lo["DAMAGE"][1]
    assert _num(CURVE, "DRAW") > 0


def test_halbard_drives_the_new_unit_everywhere():
    assert _json("crew_packs.json")["heroes"]["halbard"]["unitDef"] == "va_halberd"
    assert next(h for h in _json("hero_roster.json")["heroes"] if h["heroId"] == "halbard")["unitDef"] == "va_halberd"
    assert next(h for h in _json("hero_codex.json")["heroes"] if h["heroId"] == "halbard")["unitDef"] == "va_halberd"
    lua = (MOD / "luarules" / "gadgets" / "include" / "va_crew_roster.lua").read_text(encoding="utf-8")
    halbard = lua.split("halbard = {", 1)[1].split("\n  },", 1)[0]
    assert 'unitDef = "va_halberd"' in halbard
    assert _json("crew_packs.json")["chassis"]["va_halberd"]["label"] == "Halberd"


def test_the_new_unit_costs_what_the_halberd_did():
    u = _json("unit_costs.json")
    assert u["units"]["va_halberd"] == u["units"]["corhal"]
    assert u["names"]["va_halberd"] == "Halberd"


def test_the_recommended_company_says_what_pairs_with_solarium():
    js = (ROOT / "app" / "showoff" / "console" / "company.js").read_text(encoding="utf-8")
    assert "heat ray runs on the energy bank Solarium fills" in js
