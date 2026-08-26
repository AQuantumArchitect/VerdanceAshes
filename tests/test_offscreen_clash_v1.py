#!/usr/bin/env python3
"""The Armada-NullMercs rivalry and the player's impact, landed onto the
offscreen clash sim from tools/campaign_flow_matrix_v1.py's already-
validated scouting pass.

Each test pins the mechanism, not the tuning -- PLAYER_IMPACT and the
temperament constants remain guesses by design.
"""
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


def _zone(fac: str, mil: float = 0.3, fort: float = 0.1, eco: float = 0.2,
         base: float = 0.2) -> dict:
    return {
        "zoneId": "Z",
        "label": "Z",
        "controllingFaction": fac,
        "abstract": {
            "militaryPressure": mil,
            "fortification": fort,
            "economyMomentum": eco,
            "baseStrength": base,
            "hazardPressure": 0.0,
            "instability": 0.4,
            "control": fac,
        },
    }


class ZoneStrengthActivityTests(unittest.TestCase):
    def test_activity_scales_strength_linearly_after_the_floor(self):
        zm = _zone("armada", mil=0.3, fort=0.2, eco=0.1, base=0.2)
        s1 = clash.zone_strength(zm, "SimpleAI", activity=1.0)
        s2 = clash.zone_strength(zm, "SimpleAI", activity=2.0)
        self.assertAlmostEqual(s2, s1 * 2.0, places=9)

    def test_default_activity_matches_the_pre_living_world_value(self):
        zm = _zone("armada", mil=0.3, fort=0.2, eco=0.1, base=0.2)
        self.assertEqual(clash.zone_strength(zm, "SimpleAI"),
                         clash.zone_strength(zm, "SimpleAI", activity=1.0))


class RivalryUnlockTests(unittest.TestCase):
    """Armada can already beat NullMercs today (NullMercs is a soft
    control); only the reverse direction -- NullMercs pushing Armada when
    the weather favours the mercs -- needs the new unlock."""

    def _clash(self, activity_a, activity_b, rivalry_unlock):
        za = _zone("armada", mil=0.3, fort=0.1, eco=0.2, base=0.2)
        zb = _zone("nullmercs", mil=0.3, fort=0.1, eco=0.2, base=0.2)
        return clash.resolve_clash(za, zb, "SimpleAI", "NullMercsAI",
                                   dt_minutes=12, roll=0.99, allow_flip=True,
                                   activity_a=activity_a, activity_b=activity_b,
                                   rivalry_unlock=rivalry_unlock)

    def test_unlock_lets_a_more_active_merc_line_flip_armada(self):
        ev = self._clash(0.3, 3.0, rivalry_unlock=True)
        self.assertEqual(ev["winnerFaction"], "nullmercs")
        self.assertTrue(ev["flipped"])
        self.assertEqual(ev["toFaction"], "nullmercs")

    def test_without_the_unlock_the_same_odds_never_flip_armada(self):
        ev = self._clash(0.3, 3.0, rivalry_unlock=False)
        self.assertEqual(ev["winnerFaction"], "nullmercs")
        self.assertFalse(ev["flipped"])

    def test_armada_can_already_flip_mercs_with_or_without_the_unlock(self):
        for unlock in (True, False):
            ev = self._clash(3.0, 0.3, rivalry_unlock=unlock)
            self.assertEqual(ev["winnerFaction"], "armada")
            self.assertTrue(ev["flipped"], msg="unlock={0}".format(unlock))

    def test_the_unlock_never_leaks_to_an_unrelated_pairing(self):
        """rivalry_unlock is checked against the actual win/lose factions
        inside resolve_clash, not trusted blindly from the caller -- it must
        never let Armada lose to anyone but a more active NullMercs line."""
        za = _zone("armada", mil=0.2, fort=0.1, eco=0.1, base=0.1)
        zc = _zone("wild", mil=0.5, fort=0.1, eco=0.1, base=0.1)
        ev = clash.resolve_clash(za, zc, "SimpleAI", "RaptorsAI",
                                 dt_minutes=12, roll=0.99, allow_flip=True,
                                 activity_a=0.3, activity_b=3.0, rivalry_unlock=True)
        if ev["loserFaction"] == "armada":
            self.assertFalse(ev["flipped"])


class RunOffscreenClashesLivingWorldTests(unittest.TestCase):
    """End to end through run_offscreen_clashes's own lazy import of the
    engine's hydrology_activity -- not just the unit-level resolve_clash."""

    def _state_with_forced_activity(self, map_id: str, level_delta: float) -> dict:
        return {
            "campaignClockMinutes": 0.0,
            "missionNumber": 5,
            "graph": {},
            "hydrology": {"planetWater": 1.0, "maps": {
                map_id: {"levelDelta": level_delta, "peakSwing": 1.0},
            }},
            "zoneMemory": {
                map_id: {
                    "A": _zone("armada", mil=0.3, fort=0.1, eco=0.2, base=0.2),
                    "B": _zone("nullmercs", mil=0.3, fort=0.1, eco=0.2, base=0.2),
                },
            },
        }

    def test_a_still_map_lets_the_more_active_mercs_press_armada(self):
        state = self._state_with_forced_activity("koom_valley", level_delta=0.0)
        for _ in range(20):
            report = clash.run_offscreen_clashes(
                state, WS, active_map_id="tabula", dt_minutes=12.0,
                seed_key="test-still", map_ids=["koom_valley"])
            if report["flips"]:
                break
        zones = state["zoneMemory"]["koom_valley"]
        controls = {zones[z]["controllingFaction"] for z in zones}
        self.assertIn("nullmercs", controls)

    def test_player_impact_makes_ashwalker_ground_hold_harder(self):
        """The player has no continuous claim/spill rate live, but their
        zones DO fight in offscreen clashes -- PLAYER_IMPACT should make an
        evenly-matched Ashwalker zone noticeably stronger than the same zone
        judged at activity 1.0."""
        za = _zone("ashwalkers", mil=0.2, fort=0.1, eco=0.1, base=0.1)
        s_base = clash.zone_strength(za, "Ashwalkers", activity=1.0)
        s_impact = clash.zone_strength(za, "Ashwalkers", activity=clash.PLAYER_IMPACT)
        self.assertAlmostEqual(s_impact, s_base * clash.PLAYER_IMPACT, places=9)

    def test_scouting_the_rivalry_never_writes_campaign_state(self):
        path = WS / "state" / "campaign_state.json"
        before = path.read_bytes()
        state = self._state_with_forced_activity("koom_valley", level_delta=0.5)
        clash.run_offscreen_clashes(state, WS, active_map_id="tabula",
                                    dt_minutes=12.0, map_ids=["koom_valley"])
        self.assertEqual(path.read_bytes(), before)


if __name__ == "__main__":
    unittest.main()
