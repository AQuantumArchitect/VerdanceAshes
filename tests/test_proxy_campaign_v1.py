"""Proxy campaign: quantum seat + story engine, no BAR."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "tools"
sys.path.insert(0, str(TOOLS))

# umwelt (optional for unit tests that only hit pure helpers)
UMWELT = Path(r"C:\Users\Luke Spooner\ws-win\umwelt\src")
if UMWELT.is_dir():
    sys.path.insert(0, str(UMWELT))


class TestEnemyStyles(unittest.TestCase):
    def test_styles_map_to_bar(self):
        import proxy_campaign_v1 as pc

        self.assertEqual(pc.ENEMY_STYLES["simple"]["bar_controller"], "simple")
        self.assertEqual(
            pc.ENEMY_STYLES["barbarian"]["bar_controller"], "barbarian_aggressive"
        )
        self.assertLess(
            pc.ENEMY_STYLES["simple"]["enemy_scale_mul"],
            pc.ENEMY_STYLES["barbarian"]["enemy_scale_mul"],
        )


class TestIntentMission(unittest.TestCase):
    def test_intent_to_mission_shape(self):
        try:
            import umwelt  # noqa: F401
        except ImportError:
            self.skipTest("umwelt not installed")
        import proxy_campaign_v1 as pc

        intent = {
            "missionId": "va_proxy_001",
            "mapId": "koom_valley",
            "missionNumber": 1,
            "objectiveTarget": {
                "kind": "seize_lane",
                "targetZoneId": "KOOM_NW_GREEN_SHELF",
            },
            "deploymentZoneId": "KOOM_NW_GREEN_SHELF",
        }
        state = {"sessionHomeMap": "koom_valley", "missionNumber": 1}
        m = pc.intent_to_arc_mission(
            intent,
            state,
            enemy_style="barbarian",
            difficulty=1.0,
            duration_ticks=32,
            sortie_index=1,
        )
        self.assertEqual(m.id, "va_proxy_001")
        self.assertEqual(m.kind, "seize_lane")
        self.assertEqual(m.map_id, "koom_valley")
        self.assertGreater(m.truth.enemy_scale, 1.0)
        self.assertTrue(m.truth.fortified)


class TestFairToMatch(unittest.TestCase):
    def test_won_maps_to_victory(self):
        try:
            import umwelt  # noqa: F401
        except ImportError:
            self.skipTest("umwelt not installed")
        import random
        import proxy_campaign_v1 as pc
        from quantum_bar_ai.fair_sim import FairMissionResult

        fair = FairMissionResult(
            mission_id="va_x",
            verdict="extracted",
            ticks=40,
            progress=0.95,
            heroes_alive_frac=1.0,
            actions=["PROBE", "PUSH_OBJECTIVE", "EXTRACT"],
        )
        intent = {
            "missionId": "va_x",
            "mapId": "tabula",
            "missionNumber": 2,
            "objectiveTarget": {"kind": "seize_lane", "targetZoneId": "TAB_MID"},
        }
        state = {"commerce": {"tenebrium": 0}, "campaignId": "verdance_ashes"}
        r = pc.fair_to_match_result(
            fair, intent, state, enemy_style="simple", sortie_index=2, rng=random.Random(1)
        )
        self.assertEqual(r["schemaVersion"], "verdance-match-result/1.0")
        self.assertEqual(r["status"], "victory")
        self.assertTrue(r["success"])
        self.assertEqual(r["proxy"]["enemyStyle"], "simple")
        self.assertIn("playerBarPlan", r["proxy"])


class TestProxyCampaignSmoke(unittest.TestCase):
    def test_two_sortie_simple(self):
        try:
            import umwelt  # noqa: F401
        except ImportError:
            self.skipTest("umwelt not installed")
        import proxy_campaign_v1 as pc

        rep = pc.run_proxy_campaign(
            ROOT,
            sorties=2,
            seed=5,
            home_map="the_rock_jungle",
            enemy_style="simple",
            difficulty=1.0,
            duration_ticks=20,
            verbose=False,
        )
        self.assertEqual(len(rep["history"]), 2)
        self.assertTrue(all(h.get("processed") for h in rep["history"]))
        self.assertIn("bpAccess", rep["end"])
        self.assertEqual(rep["enemyBarController"], "simple")


if __name__ == "__main__":
    unittest.main()
