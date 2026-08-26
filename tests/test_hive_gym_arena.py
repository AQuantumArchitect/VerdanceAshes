"""Tests for hive gym arena scoring."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "tools"
UMWELT = Path(r"C:\Users\Luke Spooner\ws-win\umwelt\src")
for p in (str(TOOLS), str(UMWELT)):
    if p not in sys.path:
        sys.path.insert(0, p)

from quantum_bar_ai.hive_gym_arena import score_residual  # noqa: E402


class TestHiveGymArena(unittest.TestCase):
    def test_pass_honest_ladder(self):
        residual = {
            "schema": "hive-bar-residual/1.0",
            "byStyle": {
                "simple": {"meanWinRate": 0.8, "meanFun": 0.7, "meanClashEvents": 1},
                "barbarian": {"meanWinRate": 0.5, "meanFun": 0.6, "meanClashEvents": 2},
            },
            "headToHead": {"winRateDelta_barb_minus_simple": -0.3},
            "brain": {"samples": 80, "wins": 30, "ulUpdateCount": 10, "ulMeanSigma": 1.0},
            "honesty": {
                "barDensifyBanned": True,
                "fairRoomOnly": True,
                "nObsWall": 15,
                "godBrainMerge": False,
            },
        }
        r = score_residual(residual, pre_brain={"samples": 40, "ulUpdateCount": 0, "ulMeanSigma": 1.5})
        self.assertTrue(r["pass"])
        self.assertTrue(r["ladderHonesty"]["ok"])
        self.assertEqual(r["fraudFlags"], [])
        self.assertEqual(r["brainScarDelta"]["samples"], 40)

    def test_fail_saturated(self):
        residual = {
            "schema": "hive-bar-residual/1.0",
            "byStyle": {
                "simple": {"meanWinRate": 1.0, "meanFun": 0.8, "meanClashEvents": 0},
                "barbarian": {"meanWinRate": 1.0, "meanFun": 0.8, "meanClashEvents": 0},
            },
            "honesty": {"barDensifyBanned": True, "fairRoomOnly": True, "nObsWall": 15, "godBrainMerge": False},
            "brain": {},
        }
        r = score_residual(residual)
        self.assertFalse(r["ladderHonesty"]["ok"])
        self.assertEqual(r["ladderHonesty"]["note"], "both_saturated_raise_difficulty")

    def test_fail_fraud_densify(self):
        residual = {
            "schema": "hive-bar-residual/1.0",
            "byStyle": {"simple": {"meanWinRate": 0.5, "meanFun": 0.5, "meanClashEvents": 0}},
            "honesty": {"barDensifyBanned": False, "fairRoomOnly": True, "nObsWall": 15},
            "brain": {},
        }
        r = score_residual(residual)
        self.assertFalse(r["pass"])
        self.assertIn("densify_not_banned", r["fraudFlags"])


if __name__ == "__main__":
    unittest.main()
