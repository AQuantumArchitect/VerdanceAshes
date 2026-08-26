"""Tests for hive-bar residual hose."""
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

import hive_bar_residual_v1 as residual  # noqa: E402


class TestHiveBarResidual(unittest.TestCase):
    def test_build_schema_and_honesty(self):
        ws = ROOT
        proxy = {
            "sorties": 4,
            "seeds": 2,
            "difficulty": 1.4,
            "byStyle": {
                "simple": {"runs": 2, "meanWinRate": 0.9, "meanFun": 0.7, "meanTnb": 1, "meanClashEvents": 1},
                "barbarian": {"runs": 2, "meanWinRate": 0.6, "meanFun": 0.65, "meanTnb": 0.5, "meanClashEvents": 2},
            },
        }
        r = residual.build_residual(proxy, workspace=ws, ran_on="wargen")
        self.assertEqual(r["schema"], residual.SCHEMA)
        self.assertTrue(r["honesty"]["barDensifyBanned"])
        self.assertEqual(r["honesty"]["nObsWall"], 15)
        self.assertFalse(r["honesty"]["godBrainMerge"])
        self.assertTrue(r["honesty"].get("humanSealBotClearForbidden"))
        self.assertEqual(r["kind"], "player_proxy")
        self.assertEqual(r["ran_on"], "wargen")
        self.assertEqual(r["muscleNode"], "wargen")
        self.assertIn("simple", r["byStyle"])
        self.assertAlmostEqual(r["headToHead"]["winRateDelta_barb_minus_simple"], -0.3)

    def test_ran_on_agnostic_tag(self):
        r = residual.build_residual(
            {"byStyle": {"simple": {"runs": 1, "meanWinRate": 1.0, "meanFun": 0.5, "meanTnb": 0, "meanClashEvents": 0}}},
            workspace=ROOT,
            ran_on="roc",
        )
        self.assertEqual(r["ran_on"], "roc")
        self.assertEqual(r["kind"], "player_proxy")

    def test_write_temp(self):
        with tempfile.TemporaryDirectory() as td:
            ws = Path(td)
            (ws / "outbox").mkdir()
            (ws / "VERSION").write_text("0.8.5\n", encoding="utf-8")
            (ws / "app" / "brain").mkdir(parents=True)
            (ws / "app" / "brain" / "bar_brain_weights.json").write_text(
                json.dumps({"samples": 10, "wins": 5, "losses": 5}), encoding="utf-8"
            )
            proxy = {
                "byStyle": {
                    "simple": {"runs": 1, "meanWinRate": 1.0, "meanFun": 0.8, "meanTnb": 0, "meanClashEvents": 0}
                }
            }
            r = residual.build_residual(proxy, workspace=ws)
            # skip hive path by writing operator only via also_hive False
            result = residual.write_residual(r, ws, also_hive=False)
            self.assertTrue(any("hive_bar_residual" in w for w in result["written"]))
            op = ws / "outbox" / "hive_bar_residual.latest.json"
            self.assertTrue(op.is_file())
            loaded = json.loads(op.read_text(encoding="utf-8"))
            self.assertEqual(loaded["brain"]["samples"], 10)
            vitals = ws / "outbox" / "playtest_infra_vitals.latest.json"
            self.assertTrue(vitals.is_file())
            v = json.loads(vitals.read_text(encoding="utf-8"))
            self.assertTrue(v.get("barDensifyBanned"))


if __name__ == "__main__":
    unittest.main()
