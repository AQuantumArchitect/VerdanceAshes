#!/usr/bin/env python3
"""v0.8.3 theater map, home jungle, rim stamp, rep curve."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from verdance.hub import stamp_deploy_plan as stamp
from verdance import campaign as engine
from verdance.hub.build_hub_state import HOME_MAP_ID, build_open_node, build_theater, pick_focus_region


class TestRepDefaults(unittest.TestCase):
    def test_fresh_rep_curve(self):
        st = engine.default_v1_state()
        rep = st["reputation"]
        self.assertEqual(rep["armada"], 18)
        self.assertEqual(rep["cortex"], 70)
        self.assertEqual(rep["nullmercs"], 48.0)
        self.assertEqual(st.get("sessionHomeMap"), "the_rock_jungle")
        self.assertIn("homeCamp", st)
        self.assertIn("flags", st)


class TestCortexGrudge(unittest.TestCase):
    def test_crater_victory_plummets_cortex(self):
        st = engine.default_v1_state()
        self.assertEqual(st["reputation"]["cortex"], 70)
        result = {
            "status": "victory",
            "verdict": "victory",
            "mapId": "eye_of_horus",
            "against": "cortex",
            "destroyedObjectiveIds": ["EOH_CORE"],
            "extractionStatus": "clean",
        }
        engine.apply_reputation_companion(st, result, 12.0)
        self.assertLess(st["reputation"]["cortex"], 55)
        self.assertGreaterEqual(st["reputation"]["cortex"], 0)

    def test_partial_crater_hits_less(self):
        st = engine.default_v1_state()
        result = {
            "status": "partial",
            "verdict": "partial",
            "mapId": "eye_of_horus",
            "against": "cortex",
            "destroyedObjectiveIds": ["EOH_CORE"],
        }
        engine.apply_reputation_companion(st, result, 8.0)
        c = st["reputation"]["cortex"]
        self.assertLess(c, 70)
        self.assertGreater(c, 50)


class TestPadStamp(unittest.TestCase):
    def test_unowned_midfield_deploy_invalidates(self):
        # Central spillway is midfield + unowned on Rock Jungle → illegal LZ.
        plan = {
            "mapId": "the_rock_jungle",
            "contractKind": "hive_clear_or_bypass",
            "marks": {
                "deployZoneId": "TRJ_C_SPILLWAY",
                "extractZoneId": "TRJ_NE_RIM",
                "captureZoneIds": ["TRJ_C_SPILLWAY"],
            },
        }
        warns = stamp.soft_validate(stamp.normalize_plan(plan), ROOT, {})
        self.assertTrue(any(w.startswith("LZ_DEPLOY") for w in warns), warns)
        report = stamp.stamp(plan, ROOT)
        self.assertFalse(report.get("ok"), report)



class TestHomeCamp(unittest.TestCase):
    def test_home_build_costs_tnb(self):
        st = engine.default_v1_state()
        st["commerce"]["tenebrium"] = 2
        st["commerce"]["metalK"] = 4
        r = engine.apply_home_build(st, None)
        self.assertTrue(r.get("ok"), r)
        self.assertEqual(st["homeCamp"]["level"], 1)
        self.assertEqual(st["commerce"]["tenebrium"], 1)
        self.assertEqual(st["commerce"]["metalK"], 3)

    def test_home_build_blocks_without_tnb(self):
        st = engine.default_v1_state()
        st["commerce"]["tenebrium"] = 0
        st["commerce"]["metalK"] = 10
        r = engine.apply_home_build(st, None)
        self.assertFalse(r.get("ok"))

    def test_home_clear_ready_from_camp(self):
        st = engine.default_v1_state()
        st["homeCamp"]["level"] = 1
        ev = engine.evaluate_home_clear(st)
        self.assertTrue(ev.get("homeClearReady"))


class TestHubHome(unittest.TestCase):
    def test_pick_focus_defaults_rock_jungle(self):
        regions = [
            {"mapId": "greenest_fields", "family": "economy"},
            {"mapId": "the_rock_jungle", "family": "wild"},
        ]
        self.assertEqual(pick_focus_region(regions, {}), HOME_MAP_ID)
        self.assertEqual(
            pick_focus_region(regions, {"sessionHomeMap": "the_rock_jungle"}),
            HOME_MAP_ID,
        )

    def test_open_node_has_home_choices(self):
        st = engine.default_v1_state()
        regions = [
            {
                "mapId": "the_rock_jungle",
                "displayName": "The Rock Jungle",
                "family": "wild",
            },
            {
                "mapId": "greenest_fields",
                "displayName": "Greenest Fields",
                "family": "economy",
            },
            {
                "mapId": "eye_of_horus",
                "displayName": "Eye of Horus",
                "family": "tempo",
            },
        ]
        aces = [{"id": "vane", "deployable": True}, {"id": "ketha", "deployable": True}]
        node = build_open_node(st, regions, aces, st["reputation"])
        kinds = {c.get("kind") for c in node["choices"]}
        self.assertIn("deploy", kinds)
        maps = {
            (c.get("effect") or {}).get("mapId")
            for c in node["choices"]
            if c.get("kind") == "deploy"
        }
        self.assertIn("the_rock_jungle", maps)

    def test_theater_intel_shape(self):
        st = engine.default_v1_state()
        st["zoneMemory"] = {
            "the_rock_jungle": {
                "RJ_CENTRAL_LAGOON_MAZE": {
                    "label": "Central Lagoon Maze",
                    "controllingFaction": "wild",
                    "confidence": "estimated",
                    "abstract": {"control": "wild"},
                }
            }
        }
        th = build_theater(st, "the_rock_jungle", [])
        self.assertEqual(th["mapId"], "the_rock_jungle")
        self.assertTrue(th["zones"])
        self.assertIn("RJ_CENTRAL_LAGOON_MAZE", th["intelByZone"])


if __name__ == "__main__":
    unittest.main()
