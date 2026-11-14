#!/usr/bin/env python3
"""Ground the company holds at extraction stays the company's at home (Luke, Rock Jungle,
2026-11-13: "I took the tabula lane, but it's saying it still belongs to the, the wild ... I have
like towers, and I have a bunch of units, and I have some metal extractors, all built along the
two lanes").

The gadget measured the lanes right (result.zoneDv) and apply_zone_dv flipped them to the
company, then the offscreen tick, in the same homecoming, re-estimated every Rock Jungle zone that
wasn't in the telemetry file: actor_for_zone tested raptor hazard before control, so any wild-map
zone with hazard pressure was ticked by RaptorsAI and written back to "wild" (the hub's "the wild").
Now every zone measured at extraction is live for the homecoming, and held ground is ticked as the
company's on later homecomings too.
"""
from __future__ import annotations

import copy
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from verdance import campaign as engine  # noqa: E402
from verdance.campaign import measure  # noqa: E402

MAP = "the_rock_jungle"
NE, SW, RIM = "TRJ_NE_LANE", "TRJ_SW_LANE", "TRJ_NE_RIM"


def _wild(zid):
    return {"zoneId": zid, "controllingFaction": "wild", "hazardPressure": 0.4,
            "abstract": {"control": "wild", "hazardPressure": 0.4}}


def _state():
    s = engine.default_v1_state()
    s["zoneMemory"] = {MAP: {z: _wild(z) for z in (NE, SW, RIM, "TRJ_C_SPILLWAY")}}
    return s


def _result(**over):
    r = {
        "missionId": "va_003", "missionNumber": 3, "campaignId": "verdance_ashes",
        "status": "extracted", "terminalReason": "extracted", "mapId": MAP,
        "deploymentMapId": MAP, "deploymentZoneId": "TRJ_NW_OUTER_MUSTER", "targetZoneId": NE,
        "extractionZoneId": "TRJ_NW_OUTER_MUSTER", "patron": "nullmercs", "elapsedMinutes": 24.0,
        "frame": 43200, "resultKey": "verdance_ashes|va_003|3|ch1|extracted|extracted|f43200",
        "objectiveKind": "seize_lane", "objectiveComplete": False,
        # Towers and an army on both lanes; a few raptors left in the lanes and the rim.
        "zoneDv": {NE: {"ashwalkers": 5200, "raptors": 300}, SW: {"ashwalkers": 3900, "raptors": 120},
                   RIM: {"ashwalkers": 2600}},
    }
    r.update(over)
    return r


def test_lane_measured_at_extraction_is_live_this_homecoming():
    live = measure.live_zone_ids(["TRJ_C_SPILLWAY"], _result(), ROOT)
    assert set(live) >= {NE, SW, RIM, "TRJ_C_SPILLWAY"}


def test_held_wild_ground_is_ticked_as_the_company_not_the_raptors():
    zm = {"controllingFaction": "ashwalkers", "hazardPressure": 0.5, "abstract": {"control": "ashwalkers"}}
    assert measure.actor_for_zone({}, MAP, NE, zm) == "Ashwalkers"
    assert measure.actor_for_zone({}, MAP, NE, _wild(NE)) == "RaptorsAI"


def test_held_lanes_survive_the_homecoming_with_no_telemetry():
    state2, _report, _, _ = engine.process_result(copy.deepcopy(_state()), _result(), None, ROOT, None)
    zm = state2["zoneMemory"][MAP]
    for z in (NE, SW, RIM):
        assert zm[z]["controllingFaction"] == "ashwalkers", (z, zm[z]["controllingFaction"])
    assert zm["TRJ_C_SPILLWAY"]["controllingFaction"] == "wild"      # unmeasured raptor ground stays wild
    # The Tabula road's door on the Rock Jungle is the Northeast Rim: held, the road is open.
    assert (state2.get("doors") or {}).get(RIM, {}).get("held") is True


def test_held_lanes_stay_held_through_a_later_homecoming_elsewhere():
    state2, _r, _, _ = engine.process_result(copy.deepcopy(_state()), _result(), None, ROOT, None)
    measure.tick_offscreen_zones(state2, "koom_valley", [], 120.0, ROOT)
    assert state2["zoneMemory"][MAP][NE]["controllingFaction"] == "ashwalkers"


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print("ok", name)
