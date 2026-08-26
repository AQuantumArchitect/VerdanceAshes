"""Lightweight unit tests for quantum_bar_ai (no network)."""
from __future__ import annotations

import unittest

from quantum_bar_ai.brain import parse_action_line
from quantum_bar_ai.mood import MoodSnapshot, pack_wall_sensors, pack_claim_sensors
from quantum_bar_ai.policy import decide, ACTIONS
from quantum_bar_ai.sim import EARLY_ARC, run_mission
from quantum_bar_ai.bar_map import plan_from_mood
from quantum_bar_ai.world import PROXY_SPEC


class TestQuantumBarAI(unittest.TestCase):
    def test_spec_shape(self):
        self.assertEqual(PROXY_SPEC.name, "verdance-player-proxy")
        self.assertGreaterEqual(len(PROXY_SPEC.nodes), 4)
        self.assertGreaterEqual(len(PROXY_SPEC.bindings), 20)

    def test_parse_action(self):
        d = parse_action_line("ACTION FALLBACK | gtfo")
        self.assertIsNotNone(d)
        self.assertEqual(d.action, "FALLBACK")
        self.assertIn("gtfo", d.reason)

    def test_policy_extract_when_done(self):
        m = MoodSnapshot(objective=0.95, progress=0.95)
        d = decide(m)
        self.assertEqual(d.action, "EXTRACT")

    def test_policy_anti_flank_stall(self):
        m = MoodSnapshot(
            aggression=0.5,
            caution=0.4,
            focus=0.4,
            pressure=0.3,
            cohesion=0.5,
            momentum=0.2,
            objective=0.15,
            progress=0.15,
            threat=0.45,
            advantage=0.55,
            player_strength=0.6,
            enemy_strength=0.5,
            hero_vane_alive=0.9,
            hero_ketha_alive=0.9,
        )
        recent = ["FLANK"] * 8
        d = decide(m, recent=recent)
        self.assertEqual(d.action, "PUSH_OBJECTIVE")

    def test_wall_sensors_keys(self):
        s = pack_wall_sensors(
            {
                "progress": 0.3,
                "threat": 0.4,
                "clock_frac": 0.2,
                "player_strength": 0.7,
                "enemy_strength": 0.5,
                "approach": 0.4,
                "heroes_alive_frac": 1.0,
                "cohesion_proxy": 0.8,
                "vane_alive": 1.0,
                "ketha_alive": 1.0,
            }
        )
        self.assertIn("proxy_aggression_wall", s)
        self.assertIn("mission_progress_wall", s)

    def test_claim_sensors(self):
        m = MoodSnapshot()
        c = pack_claim_sensors("PUSH_OBJECTIVE", m)
        self.assertTrue(any(k.endswith("_claim") for k in c))

    def test_bar_map(self):
        plan = plan_from_mood(MoodSnapshot(aggression=0.9, caution=0.1, momentum=0.8))
        self.assertIn(plan.player_controller, ("simple", "barbarian_aggressive"))

    def test_sim_first_mission_wins(self):
        r = run_mission(EARLY_ARC[0], seed=3, verbose=False)
        self.assertIn(r.verdict, ("extracted", "objective_complete"))
        self.assertGreaterEqual(r.progress, 0.9)
        self.assertTrue(all(a in ACTIONS for a in r.actions))


if __name__ == "__main__":
    unittest.main()
