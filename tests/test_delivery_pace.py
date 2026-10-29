"""A pack's ride in is as fast as the pack: the roads' travel times are a ground column at Brute
speed, a faster pack takes less of them, and a flying one skips the roads' terrain detours."""
from __future__ import annotations

import json
from pathlib import Path

from verdance.company.commerce_delivery import delivery_eta, travel_pace

ROOT = Path(__file__).resolve().parents[1]
CATALOG = json.loads((ROOT / "data" / "commerce" / "commerce_catalog.json").read_text(encoding="utf-8-sig"))
LISTINGS = CATALOG.get("listings") or CATALOG


def _eta(lid, dest):
    return delivery_eta(listing=LISTINGS[lid], listing_id=lid, dest_map_id=dest, workspace=ROOT)["etaSeconds"]


def test_the_wasps_beat_the_brutes_by_far():
    for dest in ("greenest_fields", "the_rock_jungle", "all_that_simmers"):
        brutes, wasps = _eta("crash_of_brutes", dest), _eta("wasp_flight", dest)
        assert wasps * 3 <= brutes, (dest, brutes, wasps)


def test_pace_is_speed_and_flight():
    craft = {"roadPaceSpeed": 72, "airRouteFactor": 0.6}
    assert travel_pace({"speed": 72}, craft) == 1.0                  # the roads' own pace
    assert travel_pace({}, craft) == 1.0                             # no speed given: the roads' pace
    assert abs(travel_pace({"speed": 144}, craft) - 0.5) < 1e-9      # twice as fast, half the time
    assert abs(travel_pace({"speed": 72, "flies": True}, craft) - 0.6) < 1e-9
