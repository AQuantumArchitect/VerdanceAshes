#!/usr/bin/env python3
"""The drop carries the shop: the field loads while the player is still buying, so whatever
was bought up to the drop rides on the drop line, and only hires that change who lands reload."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from verdance_kernel import hot_drop as hd
from verdance_kernel.api import _plan_key


def _decode(field):
    deploy, pending = [], []
    for item in filter(None, field.split(";")):
        rec = dict(kv.split("=", 1) for kv in item.split(","))
        (pending if rec.pop("kind") == "pending" else deploy).append(rec)
    return deploy, pending


def test_kit_round_trip():
    kit = hd.kit_field(
        [{"kind": "package", "listingId": "punch_of_thugs", "label": "Punch, of; thugs", "unitDef": "corthud",
          "count": 7, "loan": False}],
        [{"listingId": "wasp_flight", "unitDef": "corape", "count": 4, "etaSeconds": 98},
         {"listingId": "old", "unitDef": "corak", "count": 1, "status": "arrived"}],
    )
    deploy, pending = _decode(kit)
    assert deploy == [{"listingId": "punch_of_thugs", "label": "Punch of thugs", "unitDef": "corthud",
                       "count": "7", "loan": "0"}], deploy
    assert pending == [{"listingId": "wasp_flight", "unitDef": "corape", "count": "4", "etaSeconds": "98"}], pending


def test_drop_line_fields():
    assert hd.drop_line("t", ["pavise"], {"corthud": 3}) == "t|pavise|corthud:3"
    assert hd.drop_line("t", ["pavise"], {}, "") == "t|pavise||"          # bought nothing: an empty kit, not the seed's
    assert hd.drop_line("t", ["a", "b"], {"x": 0}, "kind=package") == "t|a,b||kind=package"


def test_drop_line_walker():
    assert hd.drop_line("t", ["pavise"], {}, None, "corcom") == "t|pavise|||corcom"   # an empty kit stays a field
    assert hd.drop_line("t", [], {}, "kind=package", "") == "t|||kind=package|"
    assert hd.drop_line("t", [], {}, "", "cor|com;x") == "t||||corcomx"


def test_plan_key_never_reloads_for_a_hire():
    """Hires ride the drop: a rented hero spawns from the mod's own roster, the suit's walker is
    fielded by the drop (crew.lua fieldWalker). Only the field itself is in the key."""
    plan = {"mapId": "greenest_fields", "contractKind": "raid", "marks": {"deployZoneId": "pad", "captureZoneIds": ["b", "a"]}}
    base = _plan_key(plan, {"commerce": {"owned": {}}})
    for owned in ({"punch_of_thugs": {"kind": "purchase_package"}},
                  {"cortex_commander_suit": {"kind": "commander_suit"}},
                  {"some_hero": {"kind": "hero_rental"}}):
        assert _plan_key(plan, {"commerce": {"owned": owned}}) == base, owned
    assert _plan_key(dict(plan, mapId="eye_of_horus")) != base


if __name__ == "__main__":
    test_kit_round_trip(); test_drop_line_fields(); test_drop_line_walker(); test_plan_key_never_reloads_for_a_hire(); print("ok")
