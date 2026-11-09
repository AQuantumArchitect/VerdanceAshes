#!/usr/bin/env python3
"""Field recruit wrecks (include/campaign/field_recruits.lua): a recruit is seeded by birthing its unit
and killing it quietly, so the engine leaves a resurrectable corpse. An aircraft killed that way leaves
none: Rookery (armca) and Stiletto (armstil) were "lost" at frame 120 with cause=no_wreck on every Rock
Jungle visit of the 11-04 and 11-09 hard-AI runs (TESTING.md open item 2). Air seeds take a ground
constructor of the same faction, and the rez promotes it to the real chassis."""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LUA = ROOT / "mod" / "VerdanceAshes.sdd" / "luarules" / "gadgets" / "include" / "campaign" / "field_recruits.lua"


def test_an_air_seed_becomes_a_ground_constructor_that_promotes_back():
    src = LUA.read_text(encoding="utf-8")
    body = src[src.index("local function spawnFieldRecruitWreck"):src.index("function tickFieldRecruitPendingDeath")]
    swap = body.index("sud.canFly")
    create = body.index("Spring.CreateUnit(seedDef")
    promote = body.index("rec.needsChassisPromote = true")
    assert swap < create < promote, "the air check must run before the seed unit is created"
    assert re.search(r'arm\s*=\s*"armck".*cor\s*=\s*"corck".*leg\s*=\s*"legck"', body)
    assert "VA_FIELD_RECRUIT_AIR_PROXY" in body
