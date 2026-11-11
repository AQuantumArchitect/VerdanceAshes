#!/usr/bin/env python3
"""Hero minds (verdance.company.hero_mind, include/va_hero_mind.lua): the drop splits into the clusters
its bonds make (owner direction 2026-11-11: sparse clusters, run apart), the tables carry Umwelt's own
numbers and each hero's temper, and the engine's shadow host sees, steps and publishes."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "tests"))

import lua_harness  # noqa: E402
from verdance.company import hero_mind  # noqa: E402


def test_bonds_make_the_clusters():
    drop = ["vane", "ketha", "verse", "halbard", "veil"]
    bonds = [("vane", "ketha", 0.6), ("halbard", "veil", -0.3), ("verse", "verse", 0.0)]
    assert hero_mind.clusters(drop, bonds) == [["vane", "ketha"], ["verse"], ["halbard", "veil"]]


def test_the_tables_carry_temper_and_umwelts_numbers():
    state = {"attachments": {"pairBonds": {"ketha__vane": {"points": 60}}}, "roster": {"heroes": []}}
    t = hero_mind.mind_tables(state, ["vane", "ketha", "verse"], ROOT,
                              temper={"vane": {"nerve": 0.5, "drive": -1.0}, "ketha": {"nerve": 0.0, "drive": 0.0}})
    assert t["clusters"] == [{"heroes": ["vane", "ketha"], "bridges": [["vane", "ketha", 0.6]]}, {"heroes": ["verse"], "bridges": []}]
    assert t["start"]["vane"] == {"nerve": 0.75, "drive": 0.0, "threat": 0.5, "pain": 0.5}
    assert t["start"]["verse"]["nerve"] == 0.5, "no temper: the mixed centre"
    assert t["umwelt"] == hero_mind.UMWELT and t["holdS"] == hero_mind.HOLD_S
    assert t["shared"] == ["nerve", "drive"]


def test_the_shadow_host_in_the_engine():
    assert lua_harness.run("tools/hud_harness/hero_mind_test.lua") is None
