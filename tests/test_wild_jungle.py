#!/usr/bin/env python3
"""The Rock Jungle is wild ground: raptors hold every zone the company does not."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from verdance.campaign import default_v1_state, migrate_state  # noqa: E402
from verdance.campaign.engine import wild_zones_for  # noqa: E402
from verdance.campaign.schema import ensure_zone_memory  # noqa: E402


def _fresh():
    s = migrate_state(default_v1_state())
    ensure_zone_memory(s, ROOT)
    return s


def test_a_new_jungle_is_the_wilds_except_the_home_door():
    s = _fresh()
    jungle = s["zoneMemory"]["the_rock_jungle"]
    wild = set(wild_zones_for(s, "the_rock_jungle", ROOT))
    assert jungle["TRJ_NW_OUTER_MUSTER"]["controllingFaction"] == "ashwalkers"
    assert wild == set(jungle) - {"TRJ_NW_OUTER_MUSTER"}
    assert "TRJ_SW_LANE" in wild  # the hive's corner


def test_an_old_save_with_unclaimed_jungle_goes_wild():
    s = _fresh()
    zm = s["zoneMemory"]["the_rock_jungle"]["TRJ_NE_RIM"]
    zm["controllingFaction"] = "neutral"
    zm["abstract"]["control"] = "neutral"
    ensure_zone_memory(s, ROOT)
    assert s["zoneMemory"]["the_rock_jungle"]["TRJ_NE_RIM"]["controllingFaction"] == "wild"


def test_ground_the_company_took_stays_taken():
    s = _fresh()
    zm = s["zoneMemory"]["the_rock_jungle"]["TRJ_NW_GATE"]
    zm["controllingFaction"] = "ashwalkers"
    zm["abstract"]["control"] = "ashwalkers"
    ensure_zone_memory(s, ROOT)
    assert "TRJ_NW_GATE" not in wild_zones_for(s, "the_rock_jungle", ROOT)
