"""Unit tests for novel quantum-brain mechanisms + manifold gym smoke."""
from __future__ import annotations

import math
import random
import unittest

from quantum_bar_ai.quantum_membrane import (
    CampaignDensity,
    DualMembraneState,
    LaneDensity,
    PathKet,
    PredicateAmplitudes,
    ProxyBelief,
    partial_trace_proxy,
    path_hint_from_actions,
    solution_entropy_width,
    vector_diversity,
    von_neumann_diag,
)
from quantum_bar_ai.lane_war import LineFront, apply_line_order, decide_line, koom_geometry, tick_lane_combat
from quantum_bar_ai.lane_war import LineOrder


class TestPathKet(unittest.TestCase):
    def test_normalize_probs_sum_one(self):
        k = PathKet.from_weights(1, 2, 3)
        ps = k.probs()
        self.assertAlmostEqual(sum(ps.values()), 1.0, places=5)

    def test_soft_measure_boosts_path(self):
        k = PathKet.from_weights(1, 1, 1)
        before = k.probs()["A"]
        k.soft_measure("A", strength=0.5)
        self.assertGreater(k.probs()["A"], before)

    def test_hard_measure_collapses(self):
        k = PathKet.from_weights(10, 0.01, 0.01)
        lab = k.hard_measure(random.Random(0))
        self.assertEqual(lab, "A")
        self.assertAlmostEqual(k.probs()["A"], 1.0, places=5)

    def test_rotate_preserves_norm(self):
        k = PathKet.from_weights(1, 1, 1)
        k.rotate(0, 0.7)
        n2 = sum(r * r + i * i for r, i in zip(k.re, k.im))
        self.assertAlmostEqual(n2, 1.0, places=5)


class TestCampaignDensity(unittest.TestCase):
    def test_path_weights(self):
        d = CampaignDensity.from_path_weights(0.5, 0.3, 0.2)
        w = d.path_weights()
        self.assertAlmostEqual(sum(w.values()), 1.0, places=5)
        self.assertGreater(w["A"], w["B"])

    def test_dephase_lowers_coherence(self):
        d = CampaignDensity.from_path_weights(0.33, 0.34, 0.33, purity=0.9)
        c0 = d.coherence()
        d.dephase(0.5)
        self.assertLess(d.coherence(), c0)

    def test_evolve_win_nudge(self):
        d = CampaignDensity.from_path_weights(0.33, 0.34, 0.33)
        d.evolve_after_mission(won=True, mission_index=3, path_hint="A", n_missions=15)
        self.assertGreater(d.path_weights()["A"], 0.33)
        self.assertGreater(d.phi, 0.0)

    def test_entropy_width(self):
        pure = CampaignDensity(diag=[1.0, 0.0, 0.0], off_re=[0, 0, 0])
        mixed = CampaignDensity(diag=[1 / 3, 1 / 3, 1 / 3])
        self.assertLess(pure.width_from_entropy(), mixed.width_from_entropy())


class TestProxyBelief(unittest.TestCase):
    def test_observe_hud_updates(self):
        b = ProxyBelief()
        b.observe_hud({"contact": "heavy", "objective_bar": "half"}, {"aggression": 0.4})
        self.assertGreater(b.expect["threat"], 0.0)
        self.assertGreater(b.samples, 0)

    def test_decoy_raises_confusion(self):
        b = ProxyBelief()
        b.coherence = 0.8
        b.apply_decoy_povm(0.3)
        self.assertGreater(b.confusion, 0.2)
        self.assertLess(b.coherence, 0.8)

    def test_partial_trace_never_leaks_diag(self):
        d = CampaignDensity.from_path_weights(0.8, 0.1, 0.1)
        b = partial_trace_proxy(d)
        fair = b.fair_dict()
        self.assertNotIn("diag", fair)
        self.assertNotIn("path_weights", fair)
        self.assertIn("width_band", fair)

    def test_fair_export_no_rho(self):
        dual = DualMembraneState()
        fair = dual.fair_export()
        self.assertNotIn("campaign", fair)
        self.assertIn("belief", fair)
        op = dual.operator_export()
        self.assertIn("campaign", op)


class TestLaneDensity(unittest.TestCase):
    def test_hold_line_rephases(self):
        ld = LaneDensity(n=4)
        ld.coh = [0.05, 0.05, 0.05]
        ld.apply_order("HOLD_LINE")
        self.assertGreater(ld.mean_coherence(), 0.05)

    def test_breakthrough_collapses(self):
        ld = LaneDensity(n=4)
        ld.coh = [0.25, 0.25, 0.25]
        ld.apply_order("BREAKTHROUGH", lane=1)
        self.assertLess(ld.coh[0], 0.1)
        self.assertLess(ld.coh[1], 0.1)

    def test_line_front_has_density(self):
        geo = koom_geometry(4)
        front = LineFront(geometry=geo)
        self.assertIsNotNone(front.density)
        order = decide_line(front, aggression=0.6, width=0.3)
        apply_line_order(front, order)
        tick_lane_combat(front, player_strength=0.7, enemy_strength=0.5, rng=random.Random(1))
        self.assertGreater(front.coherence, 0.0)

    def test_koom_3_to_5(self):
        for n in (3, 4, 5):
            g = koom_geometry(n)
            self.assertEqual(g.lane_count, n)
            front = LineFront(geometry=g)
            self.assertEqual(len(front.lanes), n)
            self.assertEqual(front.density.n, n)


class TestPredicateInterference(unittest.TestCase):
    def test_classical_any(self):
        pa = PredicateAmplitudes.from_scores(
            {"objective_hold": 0.9, "eco_wreck": 0.1},
            ["objective_hold", "eco_wreck"],
        )
        self.assertTrue(pa.classical_any(0.72))

    def test_interference_vs_thrash(self):
        scores = {"objective_hold": 0.7, "lane_hold": 0.7, "eco_wreck": 0.65}
        pa = PredicateAmplitudes.from_scores(scores, list(scores.keys()))
        good = pa.interference_score()
        bad = pa.thrash_penalty(20)
        self.assertLessEqual(bad, good)

    def test_solution_entropy_width_scales(self):
        narrow = solution_entropy_width(["PUSH_OBJECTIVE"], ["PUSH_OBJECTIVE"])
        wide = solution_entropy_width(
            ["PUSH_OBJECTIVE", "FLANK", "BUILD_MEX", "DEFEND_BASE", "RALLY"],
            ["PUSH_OBJECTIVE"],
        )
        self.assertLess(narrow, wide)


class TestPathHints(unittest.TestCase):
    def test_push_is_path_a(self):
        self.assertEqual(
            path_hint_from_actions(["PUSH_OBJECTIVE"] * 8 + ["FLANK"] * 3),
            "A",
        )

    def test_eco_is_path_b(self):
        self.assertEqual(
            path_hint_from_actions(["BUILD_MEX"] * 6 + ["BUILD_ENERGY"] * 4),
            "B",
        )

    def test_diversity(self):
        mono = vector_diversity(["PUSH_OBJECTIVE"] * 10)
        multi = vector_diversity(
            ["PUSH_OBJECTIVE", "FLANK", "HOLD_AND_HEAL", "PROBE", "BUILD_ENERGY"] * 2
        )
        self.assertLess(mono, multi)


class TestGymSmoke(unittest.TestCase):
    def test_one_gen_smoke(self):
        from quantum_bar_ai.manifold_gym import CraftKnobs, run_generation
        from quantum_bar_ai.quantum_membrane import (
            CampaignDensity,
            DualMembraneState,
            PathKet,
        )
        from quantum_bar_ai.campaign_manifold import CampaignRho
        from quantum_bar_ai.bar_brain import seed_manifold_priors

        knobs = CraftKnobs(difficulty=0.95)
        dual = DualMembraneState(
            campaign=CampaignDensity.from_path_weights(0.33, 0.34, 0.33),
            path_ket=PathKet.from_weights(0.33, 0.34, 0.33),
        )
        metrics, new_knobs, dual2, rho, weights = run_generation(
            gen=0,
            knobs=knobs,
            dual=dual,
            rho=CampaignRho(),
            weights=seed_manifold_priors(),
            seeds=[7],
            verbose=False,
        )
        self.assertIn("overall_win_rate", metrics)
        self.assertIn("arc_rates", metrics)
        self.assertIn("craft_score", metrics)
        self.assertGreaterEqual(metrics["overall_win_rate"], 0.0)
        self.assertLessEqual(metrics["overall_win_rate"], 1.0)
        self.assertIsInstance(new_knobs.difficulty, float)
        self.assertGreater(dual2.campaign.phi, 0.0)
        self.assertGreater(weights.samples, 0)


class TestBarBrainWidthLane(unittest.TestCase):
    def test_width_priors_exist(self):
        from quantum_bar_ai.bar_brain import seed_manifold_priors, bias_from_weights

        w = seed_manifold_priors()
        self.assertIn("narrow", w.width_action)
        self.assertIn("wide", w.width_action)
        sn = bias_from_weights(w, kind="eco_raid", width_band="narrow")
        sw = bias_from_weights(w, kind="multipressure", width_band="wide")
        # narrow should prefer PUSH relatively more vs wide
        self.assertGreater(sn.get("PUSH_OBJECTIVE", 0), 0.0)
        self.assertGreater(sw.get("EXPAND_FRONT", 0), 0.0)


class TestPathAnneal(unittest.TestCase):
    def test_reheats_collapsed_path(self):
        from quantum_bar_ai.anneal_paths import anneal_path_space, craft_nudge_from_anneal
        from quantum_bar_ai.quantum_membrane import CampaignDensity, PathKet

        d = CampaignDensity.from_path_weights(0.92, 0.04, 0.04)
        k = PathKet.from_weights(0.92, 0.04, 0.04)
        r = anneal_path_space(d, k, gen=1)
        self.assertTrue(r.annealed)
        self.assertLess(d.path_weights()["A"], 0.92)
        self.assertGreater(d.path_weights()["B"], 0.04)
        nudge = craft_nudge_from_anneal(r)
        self.assertIn("path_purity_target", nudge)


class TestEnemyLineAI(unittest.TestCase):
    def test_plans_and_applies(self):
        from quantum_bar_ai.enemy_line_ai import plan_enemy_line, apply_enemy_plan
        from quantum_bar_ai.lane_war import LineFront, koom_geometry
        from quantum_bar_ai.campaign_manifold import CampaignRho
        from quantum_bar_ai.quantum_membrane import CampaignDensity

        front = LineFront(geometry=koom_geometry(4))
        plan = plan_enemy_line(
            front,
            rho=CampaignRho(arm_cor=0.8),
            density=CampaignDensity.from_path_weights(0.5, 0.3, 0.2),
            width=0.6,
            rng=random.Random(3),
        )
        self.assertIn(plan.order.order, {
            "HOLD_LINE", "WEIGHT_LANE", "REFUSE_LANE", "REINFORCE_LANE",
            "BREAKTHROUGH", "REFUSE_FLANK", "STAGGER_ADVANCE",
        })
        apply_enemy_plan(front, plan)
        self.assertAlmostEqual(sum(L.enemy_mass for L in front.lanes), 1.0, places=4)

    def test_interference_tuner_nudge(self):
        from quantum_bar_ai.interference_tuner import (
            score_mission_interference,
            aggregate_craft_nudge,
        )

        r = score_mission_interference(
            kind="multipressure",
            width=0.85,
            predicate_scores={"objective_hold": 0.6, "eco_wreck": 0.55, "lane_hold": 0.5},
            predicates=["objective_hold", "eco_wreck", "lane_hold"],
            actions=["PUSH_OBJECTIVE", "BUILD_MEX", "FLANK", "HOLD_AND_HEAL", "BUILD_ENERGY"] * 3,
        )
        self.assertIn(r.recommended, ("reward_multipath", "punish_thrash", "ok", "narrow_ok"))
        nudge = aggregate_craft_nudge([r])
        self.assertIsInstance(nudge, dict)


if __name__ == "__main__":
    unittest.main()
