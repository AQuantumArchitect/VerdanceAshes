#!/usr/bin/env python3
"""Pads: a door the company holds, or Ashwalker-majority ground. Never open ground."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from verdance.world import landing_zones as lz
from verdance import campaign as engine


class TestLandingZones(unittest.TestCase):
    def test_open_ground_is_never_a_pad(self):
        rim = {"xMin": 0.0, "xMax": 0.2, "zMin": 0.0, "zMax": 0.2}
        mid = {"xMin": 0.35, "xMax": 0.65, "zMin": 0.35, "zMax": 0.65}
        for zid, b in (("Z_RIM", rim), ("Z_MID", mid)):
            ok, reason = lz.legal_landing_reason({}, "greenest_fields", zid, b)
            self.assertFalse(ok)
            self.assertEqual(reason, "not_ours")

    def test_a_held_door_is_a_pad(self):
        state = engine.default_v1_state()
        ok, reason = lz.legal_landing_reason(state, "greenest_fields", "GF_NW_MUSTER", {})
        self.assertTrue(ok)
        self.assertEqual(reason, "held_door")
        # the far door of the Koom road is not ours until we walk it
        ok, reason = lz.legal_landing_reason(state, "greenest_fields", "GF_SE_PLATEAU", {})
        self.assertFalse(ok)

    def test_ashwalker_majority_unlocks_midfield(self):
        mid = {"xMin": 0.35, "xMax": 0.65, "zMin": 0.35, "zMax": 0.65}
        state = engine.default_v1_state()
        lz.seed_ashwalker_pad(state, "greenest_fields", "Z_FOB", stack_weight=3.0)
        # Minority enemy residual still leaves Ashwalker majority.
        z = state["zoneMemory"]["greenest_fields"]["Z_FOB"]
        z["lastMeasuredRaw"]["factionPresence"] = {
            "ashwalkers": 3.0,
            "armada": 1.0,
        }
        ok, reason = lz.legal_landing_reason(state, "greenest_fields", "Z_FOB", mid)
        self.assertTrue(ok)
        self.assertEqual(reason, "ashwalker_base")

    def test_ashwalker_minority_stack_rejected(self):
        mid = {"xMin": 0.35, "xMax": 0.65, "zMin": 0.35, "zMax": 0.65}
        state = {
            "zoneMemory": {
                "greenest_fields": {
                    "Z_FOB": {
                        "controllingFaction": "ashwalkers",
                        "abstract": {"control": "ashwalkers"},
                        "lastMeasuredRaw": {
                            "factionPresence": {"ashwalkers": 1.0, "armada": 3.0}
                        },
                    }
                }
            }
        }
        ok, reason = lz.legal_landing_reason(state, "greenest_fields", "Z_FOB", mid)
        self.assertFalse(ok)
        self.assertEqual(reason, "not_ours")

    def test_opening_lands_on_the_start_road(self):
        state = engine.default_v1_state()
        opening = engine.opening_sortie_order(state)
        # The opening lands on the start road's door on Greenest Fields, and lifts from it.
        self.assertEqual(opening["deploymentZoneId"], "GF_NW_MUSTER")
        self.assertEqual(opening["extractionZoneId"], "GF_NW_MUSTER")
        for zid in ("GF_NW_MUSTER", "TRJ_NW_OUTER_MUSTER"):
            map_id = "greenest_fields" if zid.startswith("GF_") else "the_rock_jungle"
            ok, reason = lz.legal_landing_reason(state, map_id, zid, {})
            self.assertTrue(ok, f"{zid}: {reason}")


if __name__ == "__main__":
    unittest.main()
