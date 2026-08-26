#!/usr/bin/env python3
"""v0.8.4 multi-rate offscreen clock, clash sim, and Tnb BP access."""
from __future__ import annotations

import copy
import sys
import unittest
from pathlib import Path

WS = Path(__file__).resolve().parents[1]
TOOLS = WS / "tools"
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

import offscreen_clash_v1 as clash  # noqa: E402
import verdance_story_engine_v1 as engine  # noqa: E402
import world_tick_v1 as wt  # noqa: E402


def _zone(fac: str, mil: float = 0.3, fort: float = 0.2) -> dict:
    return {
        "zoneId": "Z",
        "label": "Z",
        "controllingFaction": fac,
        "abstract": {
            "militaryPressure": mil,
            "fortification": fort,
            "economyMomentum": 0.2,
            "baseStrength": mil * 0.8,
            "hazardPressure": 0.0,
            "instability": 0.4,
            "control": fac,
        },
    }


class TestMultiRate(unittest.TestCase):
    def test_time_bands(self):
        band, rate = engine.offscreen_time_band("koom_valley", "A", "koom_valley", ["A"])
        self.assertEqual(band, "live")
        self.assertEqual(rate, 0.0)
        band, rate = engine.offscreen_time_band("koom_valley", "B", "koom_valley", ["A"])
        self.assertEqual(band, "near")
        self.assertEqual(rate, 0.5)
        band, rate = engine.offscreen_time_band("eye_of_horus", "C", "koom_valley", ["A"])
        self.assertEqual(band, "far")
        self.assertEqual(rate, 0.25)

    def test_tick_rates_scale_pressure(self):
        # Both zones are "neutral" rather than armada/cortex: this isolates
        # the time-band rate this test targets from the living-world
        # temperament multiplier tick_zone now also applies to armada and
        # cortex zones, which would otherwise vary the ratio by each map's
        # own weather independently of the band rate being tested here.
        state = {
            "campaignClockMinutes": 0.0,
            "graph": {},
            "zoneMemory": {
                "koom_valley": {
                    "LIVE": _zone("neutral", 0.2),
                    "NEAR": _zone("neutral", 0.2),
                },
                "eye_of_horus": {
                    "FAR": _zone("neutral", 0.2),
                },
            },
            "offscreenActors": {
                "koom_valley": {"LIVE": "SimpleAI", "NEAR": "SimpleAI"},
                "eye_of_horus": {"FAR": "SimpleAI"},
            },
        }
        # Fix zone ids
        for mid, zs in state["zoneMemory"].items():
            for zid, zm in zs.items():
                zm["zoneId"] = zid

        before_near = state["zoneMemory"]["koom_valley"]["NEAR"]["abstract"]["militaryPressure"]
        before_far = state["zoneMemory"]["eye_of_horus"]["FAR"]["abstract"]["militaryPressure"]
        before_live = state["zoneMemory"]["koom_valley"]["LIVE"]["abstract"]["militaryPressure"]

        summary = engine.tick_offscreen_zones(state, "koom_valley", ["LIVE"], 20.0)
        self.assertEqual(summary["bands"]["live"], 1)
        self.assertEqual(summary["bands"]["near"], 1)
        self.assertEqual(summary["bands"]["far"], 1)

        after_live = state["zoneMemory"]["koom_valley"]["LIVE"]["abstract"]["militaryPressure"]
        after_near = state["zoneMemory"]["koom_valley"]["NEAR"]["abstract"]["militaryPressure"]
        after_far = state["zoneMemory"]["eye_of_horus"]["FAR"]["abstract"]["militaryPressure"]

        self.assertEqual(after_live, before_live)  # live frozen
        d_near = after_near - before_near
        d_far = after_far - before_far
        self.assertGreater(d_near, 0)
        self.assertGreater(d_far, 0)
        # near is 0.5x, far is 0.25x => near delta ~ 2x far for same actor
        self.assertAlmostEqual(d_near / d_far, 2.0, delta=0.15)
        est = state["zoneMemory"]["eye_of_horus"]["FAR"]["offscreenEstimate"]
        self.assertEqual(est["timeBand"], "far")
        self.assertEqual(est["timeRate"], 0.25)


class TestClash(unittest.TestCase):
    def test_clash_moves_pressure(self):
        state = {
            "campaignClockMinutes": 12.0,
            "missionNumber": 1,
            "sessionHomeMap": "koom_valley",
            "zoneMemory": {
                "koom_valley": {
                    "A": {
                        "zoneId": "A",
                        "label": "A",
                        "controllingFaction": "armada",
                        "abstract": {
                            "militaryPressure": 0.75,
                            "fortification": 0.6,
                            "economyMomentum": 0.4,
                            "baseStrength": 0.5,
                            "control": "armada",
                            "instability": 0.3,
                        },
                    },
                    "B": {
                        "zoneId": "B",
                        "label": "B",
                        "controllingFaction": "nullmercs",
                        "abstract": {
                            "militaryPressure": 0.2,
                            "fortification": 0.05,
                            "economyMomentum": 0.15,
                            "baseStrength": 0.1,
                            "control": "nullmercs",
                            "instability": 0.5,
                        },
                    },
                }
            },
            "offscreenActors": {
                "koom_valley": {"A": "SimpleDefenderAI", "B": "NullMercsAI"},
            },
            "frontEvents": [],
        }
        mil_b0 = state["zoneMemory"]["koom_valley"]["B"]["abstract"]["militaryPressure"]
        r = clash.run_offscreen_clashes(
            state, None, active_map_id="koom_valley", dt_minutes=24.0, seed_key="test-clash"
        )
        self.assertGreaterEqual(r["clashes"], 1)
        mil_b1 = state["zoneMemory"]["koom_valley"]["B"]["abstract"]["militaryPressure"]
        # Stronger Armada should pressure the merc pocket (usually down)
        self.assertNotEqual(mil_b0, mil_b1)
        self.assertIn("lastOffscreenClash", state)

    def test_deterministic(self):
        def once():
            st = {
                "campaignClockMinutes": 5.0,
                "missionNumber": 1,
                "sessionHomeMap": "koom_valley",
                "zoneMemory": {
                    "koom_valley": {
                        "A": {
                            "zoneId": "A",
                            "controllingFaction": "armada",
                            "abstract": {
                                "militaryPressure": 0.5,
                                "fortification": 0.4,
                                "economyMomentum": 0.3,
                                "baseStrength": 0.3,
                                "control": "armada",
                            },
                        },
                        "B": {
                            "zoneId": "B",
                            "controllingFaction": "nullmercs",
                            "abstract": {
                                "militaryPressure": 0.4,
                                "fortification": 0.2,
                                "economyMomentum": 0.2,
                                "baseStrength": 0.2,
                                "control": "nullmercs",
                            },
                        },
                    }
                },
                "offscreenActors": {
                    "koom_valley": {"A": "SimpleAI", "B": "NullMercsAI"},
                },
                "frontEvents": [],
            }
            return clash.run_offscreen_clashes(
                st, None, active_map_id="koom_valley", dt_minutes=12.0, seed_key="same"
            )

        a, b = once(), once()
        self.assertEqual(a["clashes"], b["clashes"])
        self.assertEqual(a["flips"], b["flips"])


class TestBpAccess(unittest.TestCase):
    def test_bank_zero_blocks(self):
        state = {"commerce": {"tenebrium": 0}}
        a = engine.bp_access(state)
        self.assertEqual(a["maxPlayerBuildPower"], 0)
        self.assertFalse(a["newBuildersAllowed"])

    def test_bank_one_allows_150(self):
        state = {"commerce": {"tenebrium": 1}}
        a = engine.bp_access(state)
        self.assertEqual(a["maxPlayerBuildPower"], 150)
        self.assertTrue(a["newBuildersAllowed"])

    def test_invested_counts(self):
        state = {"commerce": {"tenebrium": 0, "bpInvestedTotal": 2}}
        a = engine.bp_access(state)
        self.assertEqual(a["accessTnb"], 2)
        self.assertEqual(a["maxPlayerBuildPower"], 300)

    def test_commerce_intent_exposes_bp(self):
        state = engine.default_v1_state()
        engine.ensure_commerce(state, WS)
        state["commerce"]["tenebrium"] = 1
        intent_c = engine.build_commerce_intent(state, WS)
        self.assertIn("bpAccess", intent_c)
        self.assertEqual(intent_c["bpAccess"]["maxPlayerBuildPower"], 150)


class TestWorldTickClash(unittest.TestCase):
    def test_world_tick_runs_clash(self):
        state = engine.default_v1_state()
        engine.ensure_zone_memory(state, WS)
        engine.ensure_commerce(state, WS)
        # Seed a rival pair on home
        home = "koom_valley"
        state["sessionHomeMap"] = home
        zm = state["zoneMemory"][home]
        ids = list(zm.keys())[:2]
        if len(ids) >= 2:
            zm[ids[0]]["controllingFaction"] = "armada"
            zm[ids[0]].setdefault("abstract", {})["control"] = "armada"
            zm[ids[0]]["abstract"]["militaryPressure"] = 0.6
            zm[ids[1]]["controllingFaction"] = "nullmercs"
            zm[ids[1]].setdefault("abstract", {})["control"] = "nullmercs"
            zm[ids[1]]["abstract"]["militaryPressure"] = 0.25
        report = wt.world_tick(state, hours_offline=2.0, map_id=home, workspace=WS)
        self.assertIn("clash", report)
        self.assertIn("regrowByMap", report)


if __name__ == "__main__":
    unittest.main()
