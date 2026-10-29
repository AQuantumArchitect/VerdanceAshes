#!/usr/bin/env python3
"""Tests for living map-web commerce delivery ETA + punch retcon."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from verdance.company.commerce_delivery import delivery_eta, shortest_map_route
from verdance.campaign import (
    build_commerce_intent,
    ensure_commerce,
    listing_available,
    load_commerce_catalog,
    purchase_listing,
)


def test_eye_to_greenest_runs_through_home():
    route, minutes = shortest_map_route("eye_of_horus", "greenest_fields", ROOT)
    assert route == ["eye_of_horus", "the_rock_jungle", "greenest_fields"], route
    assert minutes == 36.0


def test_greenest_to_simmers_is_long_haul():
    route, minutes = shortest_map_route("greenest_fields", "all_that_simmers", ROOT)
    # a long haul: at least two maps between the ends, whichever corridor the graph authors
    assert route[0] == "greenest_fields" and route[-1] == "all_that_simmers"
    assert len(route) >= 4, route
    assert minutes >= 50.0


def test_wasp_eta_from_eye():
    listing = (load_commerce_catalog(ROOT).get("listings") or {})["wasp_flight"]
    eta = delivery_eta(
        listing=listing,
        listing_id="wasp_flight",
        dest_map_id="greenest_fields",
        workspace=ROOT,
    )
    assert eta["mode"] == "map_web"
    assert eta["sourceMapId"] == "eye_of_horus"
    assert eta["deferred"] is True
    assert eta["etaSeconds"] == 98      # by air at Wasp speed: the Brutes take 360 on the same roads
    assert "Eye of Horus" in (eta["summary"] or "")


def test_punch_is_pawn_launcher_t0():
    listing = (load_commerce_catalog(ROOT).get("listings") or {})["punch_of_thugs"]
    assert listing["kind"] == "purchase_package"
    assert listing["count"] == 7
    assert listing.get("loan") is False
    eta = delivery_eta(
        listing=listing,
        listing_id="punch_of_thugs",
        dest_map_id="greenest_fields",
        workspace=ROOT,
    )
    assert eta["mode"] == "pawn_launcher"
    # Punch lands with the infil — not a mid-fight spool that leaves you naked.
    assert eta["deferred"] is False
    assert eta["route"] == []
    assert int(eta["etaSeconds"] or 0) == 0


def test_crash_of_brutes_from_the_eye():
    listing = (load_commerce_catalog(ROOT).get("listings") or {})["crash_of_brutes"]
    eta = delivery_eta(
        listing=listing,
        listing_id="crash_of_brutes",
        dest_map_id="greenest_fields",
        workspace=ROOT,
    )
    assert eta["sourceMapId"] == "eye_of_horus"
    assert eta["deferred"] is True


def test_loan_retire_and_deferred_intent():
    state = {
        "missionNumber": 9,
        "sessionHomeMap": "greenest_fields",
        "reputation": {"nullmercs": 50, "cortex": 70, "armada": 18},
        "commerce": {
            "tenebrium": 3,
            "metalK": 20,
            "owned": {
                "punch_of_thugs": {
                    "qty": 1,
                    "loan": True,
                    "kind": "loan_package",
                    "unitDef": "corthud",
                    "loanCount": 6,
                    "count": 6,
                },
                "wasp_flight": {
                    "qty": 1,
                    "loan": False,
                    "kind": "purchase_package",
                    "unitDef": "corape",
                    "count": 4,
                },
            },
            "upgrades": {},
            "ledger": [],
            "pendingDeliveries": [],
        },
    }
    ensure_commerce(state, ROOT)
    punch = state["commerce"]["owned"]["punch_of_thugs"]
    assert punch.get("loan") is False
    assert punch.get("kind") == "purchase_package"
    assert int(punch.get("count") or 0) == 7

    intent = build_commerce_intent(state, ROOT)
    assert intent["destMapId"] == "greenest_fields"
    packages = [d for d in intent["deploy"] if d.get("kind") == "package"]
    deploy_ids = {d.get("listingId") for d in packages}
    assert "punch_of_thugs" in deploy_ids  # pawn launcher = t=0
    pending_ids = {p["listingId"] for p in intent["pendingDeliveries"]}
    assert "wasp_flight" in pending_ids  # map-web stays deferred
    assert "punch_of_thugs" not in pending_ids

    # Repeat punch buy stacks qty onto the t=0 deploy bag.
    receipt = purchase_listing(state, "punch_of_thugs", ROOT)
    assert receipt.get("ok") is True
    assert receipt.get("delivery", {}).get("mode") == "pawn_launcher"
    assert int(state["commerce"]["owned"]["punch_of_thugs"]["qty"]) == 2
    intent2 = build_commerce_intent(state, ROOT)
    punch_deploy = next(
        d for d in intent2["deploy"] if d.get("listingId") == "punch_of_thugs"
    )
    assert int(punch_deploy.get("count") or 0) == 14  # 7 × qty 2


def test_punch_available_when_owned():
    catalog = load_commerce_catalog(ROOT)
    listing = catalog["listings"]["punch_of_thugs"]
    state = {
        "missionNumber": 3,
        "reputation": {"nullmercs": 40},
        "commerce": {
            "tenebrium": 0,
            "metalK": 10,
            "owned": {"punch_of_thugs": {"qty": 1, "kind": "purchase_package"}},
            "upgrades": {},
        },
    }
    ok, reason = listing_available("punch_of_thugs", listing, state, state["commerce"])
    assert ok, reason


if __name__ == "__main__":
    test_eye_to_greenest_is_short_corridor()
    test_eye_to_simmers_is_long_haul()
    test_crash_eta_from_eye()
    test_punch_is_pawn_launcher_t0()
    test_crash_of_brutes_from_the_eye()
    test_loan_retire_and_deferred_intent()
    test_punch_available_when_owned()
    print("ok")
