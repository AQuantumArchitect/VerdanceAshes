#!/usr/bin/env python3
"""The roads between maps: doors, holding them, and what the hub offers."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from verdance.campaign import default_v1_state, migrate_state  # noqa: E402
from verdance.world import roads  # noqa: E402


def _state(*walked):
    s = migrate_state(default_v1_state())
    s["history"] = [{"mapId": m, "resultKey": f"k{i}"} for i, m in enumerate(walked)]
    return s


def _ids(s):
    return {j["id"] for j in roads.legal_jobs(s, ROOT)}


def test_the_ring_and_the_shortcut():
    doors = roads.load_doors(ROOT)
    assert len(doors) == 16  # eight roads, two doors each
    assert doors["TRJ_NE_RIM"]["farZoneId"] == "T_W_CAUSEWAY"
    assert doors["GF_SE_PLATEAU"]["farMapId"] == "koom_valley"
    assert doors["AB_NE_HEIGHTS"]["farMapId"] == "tabula"
    assert doors["AB_SE_HEIGHTS"]["farMapId"] == "all_that_simmers"


def test_a_new_company_holds_the_start_road():
    s = _state()
    assert roads.held(s, "TRJ_NW_OUTER_MUSTER") and roads.held(s, "GF_NW_MUSTER")
    assert not roads.held(s, "GF_SE_PLATEAU")
    # home is open; the start road crosses to Greenest Fields
    assert "road_TRJ_NW_OUTER_MUSTER" in _ids(s)


def test_a_door_you_do_not_hold_is_a_job_not_a_road():
    s = _state("greenest_fields")
    ids = _ids(s)
    assert "door_GF_SE_PLATEAU" in ids and "road_GF_SE_PLATEAU" not in ids
    # Greenest Fields is walked: no crossing is offered onto it any more
    assert "road_TRJ_NW_OUTER_MUSTER" not in ids


def test_holding_a_door_opens_its_road_and_losing_it_shuts_it():
    s = _state("greenest_fields")
    taken = roads.record_homecoming(s, {"mapId": "greenest_fields", "zoneDv": {"GF_SE_PLATEAU": {"ashwalkers": 1800, "armada": 100}}}, ROOT)
    assert [d["zoneId"] for d in taken] == ["GF_SE_PLATEAU"] and taken[0]["held"]
    card = next(j for j in roads.legal_jobs(s, ROOT) if j["id"] == "road_GF_SE_PLATEAU")
    assert card["mapId"] == "koom_valley" and card["padZoneId"] == "KV_NW_MUSTER"  # land on the far door
    lost = roads.record_homecoming(s, {"mapId": "greenest_fields", "zoneDv": {"GF_SE_PLATEAU": {"armada": 1900, "ashwalkers": 200}}}, ROOT)
    assert lost and not lost[0]["held"]
    assert "road_GF_SE_PLATEAU" not in _ids(s) and "door_GF_SE_PLATEAU" in _ids(s)


def test_nothing_standing_leaves_a_door_as_the_company_knew_it():
    s = _state("greenest_fields")
    assert roads.record_homecoming(s, {"mapId": "greenest_fields", "zoneDv": {"GF_C_GATE": {"armada": 500}}}, ROOT) == []
    assert roads.held(s, "GF_NW_MUSTER")


def test_offscreen_truth_does_not_move_the_ledger():
    s = _state("greenest_fields")
    s.setdefault("zoneMemory", {}).setdefault("greenest_fields", {})["GF_NW_MUSTER"] = {"controllingFaction": "armada"}
    assert roads.held(s, "GF_NW_MUSTER")
    assert roads.door_markers(s, ROOT, "greenest_fields")["GF_NW_MUSTER"]["held"]


def test_the_hub_gets_at_most_three_cards_lean_first():
    s = _state("greenest_fields")
    cards = roads.road_sorties(s, ROOT)["cards"]
    assert 1 <= len(cards) <= 3
    assert cards[0]["recommended"] and not any(c["recommended"] for c in cards[1:])
    for c in cards:
        e = c["effect"]
        if e.get("preferredDeployZoneId"):
            assert e["padLocked"]


def test_the_first_sortie_on_a_map_founds_a_base():
    """Owner call (2026-10-29): like Koom's crossing, the Rock Jungle's first sortie digs in on the
    door the company holds; it is not a march across the map to the Eye's door."""
    from verdance.campaign import engine
    state = engine.default_v1_state()
    state["history"] = [{"mapId": "greenest_fields"}]          # the opener walked Greenest Fields
    jobs = roads.legal_jobs(state, ROOT)
    jungle = [j for j in jobs if j["mapId"] == "the_rock_jungle"]
    assert [j["kind"] for j in jungle] == ["found"], jungle
    card = roads._card(jungle[0], False)
    assert card["effect"]["contractKind"] == "fortify_zone"
    assert card["effect"]["preferredDeployZoneId"] == "TRJ_NW_OUTER_MUSTER"
    assert card["effect"]["preferredCaptureZoneId"] == "TRJ_NW_GATE"
    assert card["effect"]["journey"] == "home_founding"
    # walked: its doors are the work
    state["history"].append({"mapId": "the_rock_jungle"})
    kinds = {j["kind"] for j in roads.legal_jobs(state, ROOT) if j["mapId"] == "the_rock_jungle"}
    assert "found" not in kinds and "take" in kinds
