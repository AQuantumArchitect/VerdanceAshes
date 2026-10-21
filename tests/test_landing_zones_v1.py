#!/usr/bin/env python3
"""Quiet rim + Ashwalker-majority landing pad rules."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from verdance.world import landing_zones as lz
from verdance import campaign as engine


class TestLandingZones(unittest.TestCase):
    def test_quiet_rim_vs_midfield(self):
        rim = {"xMin": 0.0, "xMax": 0.2, "zMin": 0.0, "zMax": 0.2}
        mid = {"xMin": 0.35, "xMax": 0.65, "zMin": 0.35, "zMax": 0.65}
        ok, reason = lz.legal_landing_reason({}, "greenest_fields", "Z_RIM", rim)
        self.assertTrue(ok)
        self.assertEqual(reason, "quiet_rim")
        ok, reason = lz.legal_landing_reason({}, "greenest_fields", "Z_MID", mid)
        self.assertFalse(ok)
        self.assertEqual(reason, "midfield_unowned")

    def test_enemy_rim_is_contested(self):
        rim = {"xMin": 0.0, "xMax": 0.2, "zMin": 0.0, "zMax": 0.2}
        state = {
            "zoneMemory": {
                "greenest_fields": {
                    "Z_RIM": {
                        "controllingFaction": "armada",
                        "abstract": {"control": "armada"},
                    }
                }
            }
        }
        ok, reason = lz.legal_landing_reason(state, "greenest_fields", "Z_RIM", rim)
        self.assertFalse(ok)
        self.assertEqual(reason, "contested_rim")

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
        self.assertEqual(reason, "midfield_unowned")

    def test_opening_uses_quiet_rim(self):
        opening = engine.opening_sortie_order(engine.default_v1_state())
        # Standard safe GF infil/exfil is the shell-free north desert.
        self.assertEqual(opening["deploymentZoneId"], "GF_NE_PLATEAU")
        self.assertEqual(opening["extractionZoneId"], "GF_NE_PLATEAU")
        authored = ROOT / "data" / "zone_maps" / "authored" / "greenest_fields.authored.zone_map.json"
        import json

        data = json.loads(authored.read_text(encoding="utf-8"))
        by_id = {z.get("zoneId"): z for z in data["zones"]}
        for zid in ("GF_NE_PLATEAU", "GF_NW_MUSTER"):
            meta = by_id.get(zid)
            self.assertIsNotNone(meta, zid)
            ok, reason = lz.legal_landing_reason(
                {},
                "greenest_fields",
                zid,
                meta["bounds"],
                tags=meta.get("tags"),
                role=str(meta.get("role") or ""),
            )
            self.assertTrue(ok, f"{zid}: {reason}")
            self.assertEqual(reason, "quiet_rim")


if __name__ == "__main__":
    unittest.main()
