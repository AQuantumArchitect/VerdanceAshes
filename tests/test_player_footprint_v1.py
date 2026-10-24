"""Player structure footprint: extract write → credit store → Drop rehydrate SoT."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "tools"
sys.path.insert(0, str(TOOLS))

from verdance import campaign as engine
from verdance.hub.contract import normalize_result, result_v2_to_v1_fields


class TestPlayerFootprint(unittest.TestCase):
    def test_apply_replaces_map_footprint(self):
        state = engine.default_v1_state()
        result = {
            "resultKey": "test-fp-1",
            "deploymentZoneId": "GF_NW_MUSTER",
            "playerFootprint": [
                {
                    "unitDefName": "legsolar",
                    "x": 1200.5,
                    "z": 3400.0,
                    "facing": 2,
                    "hpFrac": 0.8,
                    "zoneId": "GF_NW_MUSTER",
                    "owner": "player",
                    "role": "player_footprint",
                },
                {
                    "unitDefName": "leglab",
                    "x": 1280.0,
                    "z": 3480.0,
                    "facing": 0,
                    "hpFrac": 1.0,
                    "zoneId": "GF_NW_MUSTER",
                },
            ],
        }
        out = engine.apply_player_footprint(state, result, "greenest_fields")
        self.assertEqual(out["kept"], 2)
        bag = state["playerFootprints"]["greenest_fields"]
        self.assertEqual(len(bag["units"]), 2)
        self.assertEqual(bag["units"][0]["unitDefName"], "legsolar")
        self.assertEqual(bag["units"][0]["facing"], 2)
        self.assertAlmostEqual(bag["units"][0]["x"], 1200.5)
        self.assertEqual(bag["units"][1]["role"], "player_footprint")

        # Last extract wins — empty wipe clears prior pads.
        out2 = engine.apply_player_footprint(
            state,
            {"resultKey": "test-fp-2", "playerFootprint": []},
            "greenest_fields",
        )
        self.assertEqual(out2["kept"], 0)
        self.assertEqual(state["playerFootprints"]["greenest_fields"]["units"], [])

    def test_skips_bad_rows_and_caps(self):
        state = engine.default_v1_state()
        rows = [{"unitDefName": "", "x": 1, "z": 1}]
        rows.extend(
            {
                "unitDefName": "legllt",
                "x": float(i),
                "z": float(i + 10),
                "facing": 0,
            }
            for i in range(450)
        )
        out = engine.apply_player_footprint(
            state, {"playerFootprint": rows, "resultKey": "cap"}, "greenest_fields"
        )
        self.assertEqual(out["kept"], 400)   # a whole base, converters and storage included

    def test_normalize_preserves_footprint(self):
        raw = {
            "campaignId": "verdance_ashes",
            "missionId": "va_002",
            "missionNumber": 2,
            "mapId": "greenest_fields",
            "status": "partial",
            "terminalReason": "extracted_voluntary",
            "playerFootprint": [
                {"unitDefName": "legsolar", "x": 100.0, "z": 200.0, "facing": 1},
            ],
            "survivingInstalls": [
                {"pocketId": "gf_c_gate_fus", "zoneId": "GF_C_GATE", "owner": "player", "units": []},
            ],
        }
        n = normalize_result(raw)
        self.assertEqual(len(n.get("playerFootprint") or []), 1)
        self.assertTrue(n.get("playerFootprintPresent"))
        self.assertEqual(len(n.get("survivingInstalls") or []), 1)
        flat = result_v2_to_v1_fields(n)
        self.assertEqual(flat["playerFootprint"][0]["unitDefName"], "legsolar")
        state = engine.default_v1_state()
        out = engine.apply_player_footprint(state, flat, "greenest_fields")
        self.assertEqual(out["kept"], 1)

    def test_absent_footprint_keeps_prior(self):
        state = engine.default_v1_state()
        engine.apply_player_footprint(
            state,
            {
                "resultKey": "seed",
                "playerFootprint": [
                    {"unitDefName": "legllt", "x": 10.0, "z": 20.0, "facing": 0},
                ],
            },
            "greenest_fields",
        )
        self.assertEqual(len(state["playerFootprints"]["greenest_fields"]["units"]), 1)
        # Truncated/legacy result with no footprint key must not wipe.
        out = engine.apply_player_footprint(
            state,
            {"resultKey": "legacy-no-fp", "status": "partial"},
            "greenest_fields",
        )
        self.assertEqual(out.get("skipped"), "absent")
        self.assertEqual(out["kept"], 1)
        self.assertEqual(len(state["playerFootprints"]["greenest_fields"]["units"]), 1)
        # Normalize without key → flat omits playerFootprint → still keep.
        n = normalize_result(
            {
                "campaignId": "verdance_ashes",
                "missionId": "va_003",
                "missionNumber": 3,
                "mapId": "greenest_fields",
                "status": "partial",
            }
        )
        self.assertFalse(n.get("playerFootprintPresent"))
        self.assertIsNone(n.get("playerFootprint"))
        flat = result_v2_to_v1_fields(n)
        self.assertNotIn("playerFootprint", flat)
        out2 = engine.apply_player_footprint(state, flat, "greenest_fields")
        self.assertEqual(out2.get("skipped"), "absent")
        self.assertEqual(len(state["playerFootprints"]["greenest_fields"]["units"]), 1)


if __name__ == "__main__":
    unittest.main()
