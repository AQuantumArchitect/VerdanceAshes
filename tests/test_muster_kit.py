#!/usr/bin/env python3
"""A Rock Jungle muster brings a builder (owner call, 2026-11-11: "do a sortie while the builders spend
all their Tnb"). In the 11-10 trials no sortie brought one, the commander is swept at game start, and the
Tenebrium bank sat at 3 for fourteen sorties. The muster's kit carries a constructor and the scenario says
it is a muster, so the autopilot stays to build past the secured gate."""
from __future__ import annotations

import copy
import gzip
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from verdance.mission_builder import build_scenario  # noqa: E402
from verdance.world.roads import MUSTER_ID  # noqa: E402

CASE = ROOT / "tests" / "fixtures" / "mission_builder" / "tour02"


def _load(name: str):
    return json.loads(gzip.decompress((CASE / name).read_bytes()).decode("utf-8-sig"))


def _build(choice: str | None):
    intent, state = _load("intent.json.gz"), _load("state.json.gz")
    intent = copy.deepcopy(intent)
    if choice:
        intent["hubChoiceId"] = choice
    sc, _ = build_scenario(ROOT, intent, state, log=lambda _l: None, ps1_faults=True)
    return json.loads(json.dumps(sc))


def _constructors(sc) -> int:
    """Constructors in the company's kit (the player kit recipe; ashwalker_player_kit is its alias)."""
    kit = (sc.get("baseRecipes") or {}).get("legion_player_kit") or []
    return sum(int(u.get("count") or 1) for u in kit if u.get("unitDefName") == "legck")


def test_a_muster_brings_a_constructor_and_says_it_is_a_muster():
    plain, muster = _build(None), _build(MUSTER_ID)
    assert _constructors(muster) == _constructors(plain) + 1
    kit = muster["baseRecipes"]["legion_player_kit"]
    assert any(s.get("unitDefName") == "legck" and s.get("muster") for s in kit),         "flagged, or the crew kit drops it at spawn (setup.lua: only the sealed company lands)"
    assert muster["missionBase"]["muster"]["choiceId"] == MUSTER_ID
    assert "muster" not in plain["missionBase"], "any other sortie keeps the PS1's shape"
