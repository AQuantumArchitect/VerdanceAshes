"""Tests for campaign fruit + organic pathway helpers."""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "tools"
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

import campaign_fruit_v1 as fruit  # noqa: E402
import organic_pathway_v1 as pathway  # noqa: E402
import hive_bar_residual_v1 as residual  # noqa: E402


class TestCampaignFruit(unittest.TestCase):
    def test_synthesize_saturated(self):
        ideas = fruit.synthesize_ideas(
            {
                "simpleWin": 1.0,
                "barbWin": 0.5,
                "funSimple": 0.37,
                "funBarb": 0.46,
                "pushDominance": 0.82,
                "openPushSigma": 0.007,
                "ulEcoUpdates": 5,
                "ulMissions": 100,
                "topUl": [{"key": "open|PUSH_OBJECTIVE", "updates": 100, "sigma": 0.007}],
            }
        )
        ids = {i["id"] for i in ideas}
        self.assertIn("fruit-simple-saturated", ids)
        self.assertIn("fruit-push-monoculture", ids)
        self.assertTrue(any(i.get("auto_apply_ok") for i in ideas))

    def test_craft_band_clip(self):
        knobs = {"difficulty": 1.28, "width_late": 0.98, "enemy_aggro": 1.35}
        new, applied, notes = fruit.clamp_craft_delta(
            knobs, {"difficulty": 0.5, "width_late": 0.04}
        )
        self.assertLessEqual(abs(applied["difficulty"]), 0.13 + 1e-6)
        self.assertIn(new["difficulty"], [round(1.28 + applied["difficulty"], 4)])

    def test_harvest_writes(self):
        with tempfile.TemporaryDirectory() as td:
            ws = Path(td)
            (ws / "outbox").mkdir()
            (ws / "app" / "brain").mkdir(parents=True)
            (ws / "VERSION").write_text("0.8.7\n", encoding="utf-8")
            (ws / "outbox" / "proxy_campaign.latest.json").write_text(
                json.dumps(
                    {
                        "difficulty": 1.4,
                        "byStyle": {
                            "simple": {
                                "runs": 1,
                                "meanWinRate": 1.0,
                                "meanFun": 0.3,
                                "meanTnb": 1,
                                "meanClashEvents": 2,
                            },
                            "barbarian": {
                                "runs": 1,
                                "meanWinRate": 0.5,
                                "meanFun": 0.45,
                                "meanTnb": 1,
                                "meanClashEvents": 3,
                            },
                        },
                    }
                ),
                encoding="utf-8",
            )
            (ws / "app" / "brain" / "bar_brain_weights.json").write_text(
                json.dumps(
                    {
                        "samples": 100,
                        "wins": 60,
                        "losses": 40,
                        "action_counts": {"PUSH_OBJECTIVE": 90, "FLANK": 10},
                    }
                ),
                encoding="utf-8",
            )
            (ws / "app" / "brain" / "craft_recipe.json").write_text(
                json.dumps(
                    {
                        "schemaVersion": "verdance-craft-recipe/0.1",
                        "knobs": {"difficulty": 1.28, "width_late": 0.9, "enemy_aggro": 1.2},
                    }
                ),
                encoding="utf-8",
            )
            out = fruit.harvest(workspace=ws, apply_craft=True, also_hive=False)
            self.assertEqual(out["schema"], fruit.SCHEMA)
            self.assertTrue((ws / "outbox" / "campaign_fruit.latest.json").is_file())
            self.assertTrue((ws / "outbox" / "bar_swarm_doctrine_soft.json").is_file())
            self.assertGreaterEqual(len(out.get("ideas") or []), 1)


class TestOrganicPathway(unittest.TestCase):
    def test_adapt_bump(self):
        with tempfile.TemporaryDirectory() as td:
            ws = Path(td)
            (ws / "app" / "brain").mkdir(parents=True)
            pathway.save_difficulty(1.4, workspace=ws, reason="init")
            face = pathway.adapt_difficulty_from_proxy(
                {
                    "byStyle": {
                        "simple": {"meanWinRate": 1.0},
                        "barbarian": {"meanWinRate": 0.5},
                    }
                },
                workspace=ws,
            )
            self.assertTrue(face.get("changed"))
            self.assertGreater(face["difficulty"], 1.4 - 1e-9)

    def test_curriculum_rotation(self):
        with tempfile.TemporaryDirectory() as td:
            ws = Path(td)
            (ws / "app" / "brain").mkdir(parents=True)
            p0 = pathway.curriculum_next(workspace=ws)
            self.assertEqual(p0["slot"], "C0_smoke")
            p1 = pathway.curriculum_next(workspace=ws)
            self.assertIn(p1["slot"], {"C1_ladder", "C2_eco", "C3_width", "C4_manifold_snack"})

    def test_mission_tape(self):
        with tempfile.TemporaryDirectory() as td:
            ws = Path(td)
            (ws / "app" / "brain").mkdir(parents=True)
            rows = pathway.mission_rows_from_train(
                {
                    "missionLogs": [
                        {"won": True, "width_band": "open", "surprise": -0.2, "progress": 0.9, "nTouched": 2}
                    ]
                },
                proxy_report={"difficulty": 1.4},
                ran_on="wargen",
            )
            info = pathway.append_mission_learn_rows(rows, workspace=ws, also_hive=False)
            self.assertEqual(info["appended"], 1)
            tape = (ws / "app" / "brain" / "mission_learn_tape.jsonl").read_text(encoding="utf-8")
            self.assertIn("bar-mission-learn/1.0", tape)


class TestResidual11(unittest.TestCase):
    def test_schema_and_families(self):
        r = residual.build_residual(
            {
                "sorties": 2,
                "byStyle": {
                    "simple": {"runs": 1, "meanWinRate": 1.0, "meanFun": 0.5, "meanTnb": 0, "meanClashEvents": 0},
                    "barbarian": {"runs": 1, "meanWinRate": 0.5, "meanFun": 0.5, "meanTnb": 0, "meanClashEvents": 0},
                },
                "train": {"nMissions": 2},
            },
            workspace=ROOT,
            ran_on="wargen",
        )
        self.assertEqual(r["schema"], residual.SCHEMA)
        self.assertEqual(r["missionCountThisUnit"], 2)
        self.assertIn("ulFamilies", r["brain"])


if __name__ == "__main__":
    unittest.main()
