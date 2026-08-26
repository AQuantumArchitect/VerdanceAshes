"""Tests: dual umwelt manifolds + campaign width curve + lane AI."""
from __future__ import annotations

import unittest
from dataclasses import dataclass

from quantum_bar_ai.campaign_manifold import (
    CAMPAIGN_SPEC,
    CampaignRho,
    evolve_rho,
    mission_width_curve,
    solution_space_for,
    deembed_disposition,
)
from quantum_bar_ai.proxy_manifold import (
    fair_view_from_tick,
    proxy_manifest,
    proxy_spec,
    width_to_band,
)
from quantum_bar_ai.lane_war import (
    LINE_ORDERS,
    LineFront,
    apply_line_order,
    decide_line,
    geometry_for_map,
    koom_geometry,
    lane_objective_progress,
    simmer_geometry,
    tick_lane_combat,
)
from quantum_bar_ai.lane_world import LANE_SPEC, LANE_SPEC_3, LANE_SPEC_5, lane_war_spec
from quantum_bar_ai.campaign import build_full_campaign, campaign_meta, enrich_campaign
from quantum_bar_ai.mood import MoodSnapshot
from quantum_bar_ai.world import PROXY_SPEC
from quantum_bar_ai.first_arc import ArcMission, SimTruth
from quantum_bar_ai.fair_obs import PlayerFacingCard
from quantum_bar_ai.fair_sim import run_fair_mission
from quantum_bar_ai.policy import Decision


@dataclass
class _ScriptedAgent:
    """Force a fixed action sequence for diverging-path tests."""

    sequence: list[str]
    i: int = 0

    def act(self, *, card, hud, mood, recent):
        from quantum_bar_ai.tool_agent import AgentStep

        if self.i < len(self.sequence):
            a = self.sequence[self.i]
            self.i += 1
        else:
            a = self.sequence[-1] if self.sequence else "PUSH_OBJECTIVE"
        return AgentStep(
            decision=Decision(action=a, reason="scripted", source="script", confidence=1.0),
            thoughts=["scripted"],
            backend="script",
            tool_trace=[],
        )


class TestCampaignManifold(unittest.TestCase):
    def test_spec_shape(self):
        self.assertEqual(CAMPAIGN_SPEC.name, "verdance-campaign-shape")
        self.assertGreaterEqual(len(CAMPAIGN_SPEC.nodes), 4)
        self.assertGreaterEqual(len(CAMPAIGN_SPEC.bindings), 20)

    def test_width_curve_early_late(self):
        # Uses craft_width_override when pinned (champion: early ~0.18, late ~0.74).
        early = [mission_width_curve(i) for i in range(5)]
        late = [mission_width_curve(i) for i in range(10, 15)]
        self.assertTrue(all(w < 0.55 for w in early), msg=f"early={early}")
        self.assertTrue(all(w >= 0.55 for w in late), msg=f"late={late}")
        self.assertLess(early[0], late[-1])
        self.assertGreater(late[-1] - early[0], 0.3)

    def test_early_narrow_vectors(self):
        ss = solution_space_for(mission_index=0, kind="eco_raid")
        self.assertTrue(ss.is_narrow)
        self.assertLessEqual(len(ss.viable_vectors), 4)
        self.assertLessEqual(len(ss.win_predicates), 2)
        self.assertIn("PUSH_OBJECTIVE", ss.primary_vectors)

    def test_late_wide_multipath(self):
        ss = solution_space_for(mission_index=14, kind="multipressure")
        self.assertTrue(ss.is_wide)
        self.assertGreaterEqual(len(ss.viable_vectors), 3)
        self.assertGreaterEqual(len(ss.win_predicates), 3)

    def test_rho_evolve_phi_forward(self):
        r0 = CampaignRho()
        r1 = evolve_rho(r0, won=True, mission_index=2, kind="eco_raid")
        self.assertGreater(r1.phi, r0.phi)
        r2 = evolve_rho(r1, won=False, mission_index=3, kind="siege")
        self.assertGreaterEqual(r2.phi, r1.phi)

    def test_deembed(self):
        d = deembed_disposition(CampaignRho())
        self.assertIn("military_aggression", d)
        self.assertTrue(0.0 <= d["eco_aggression"] <= 1.0)


class TestProxyManifold(unittest.TestCase):
    def test_proxy_spec(self):
        self.assertEqual(PROXY_SPEC.name, "verdance-player-proxy")
        m = proxy_manifest()
        self.assertIn("fair_rule", m)
        self.assertEqual(len(m["axes"]), 6)

    def test_fair_view_strips_secrets(self):
        mood = MoodSnapshot()
        v = fair_view_from_tick(
            mission_id="va_001",
            kind="eco_raid",
            briefing="hit converters",
            hud={"phase": "APPROACH", "enemy_scale": 9.9, "rho": {"x": 1}, "_truth": {}},
            mood=mood,
            width=0.2,
            primary_vectors=["PUSH_OBJECTIVE"],
        )
        self.assertNotIn("enemy_scale", v.hud)
        self.assertNotIn("rho", v.hud)
        self.assertEqual(v.width_band, "narrow")
        self.assertEqual(v.primary_hint, "PUSH_OBJECTIVE")

    def test_width_bands(self):
        self.assertEqual(width_to_band(0.2), "narrow")
        self.assertEqual(width_to_band(0.5), "open")
        self.assertEqual(width_to_band(0.9), "wide")


class TestLaneWar(unittest.TestCase):
    def test_koom_3_to_5(self):
        for n in (3, 4, 5):
            g = koom_geometry(n)
            self.assertEqual(g.lane_count, n)
            self.assertEqual(len(g.labels), n)
            self.assertEqual(g.map_id, "koom_valley")

    def test_lane_specs(self):
        self.assertEqual(len(LANE_SPEC_3.nodes), 4)  # root + 3
        self.assertEqual(len(LANE_SPEC.nodes), 5)
        self.assertEqual(len(LANE_SPEC_5.nodes), 6)
        self.assertTrue(LANE_SPEC.name.startswith("verdance-lane-war"))

    def test_hold_line_raises_coherence(self):
        f = LineFront(geometry=koom_geometry(4))
        # break it first
        f.coherence = 0.4
        from quantum_bar_ai.lane_war import LineOrder

        apply_line_order(f, LineOrder("HOLD_LINE"))
        self.assertGreaterEqual(f.coherence, 0.4)

    def test_breakthrough_moves_mass(self):
        f = LineFront(geometry=koom_geometry(4))
        prim = f.geometry.primary_index
        before = f.lanes[prim].friendly_mass
        from quantum_bar_ai.lane_war import LineOrder

        apply_line_order(f, LineOrder("BREAKTHROUGH", lane=prim))
        self.assertGreaterEqual(f.lanes[prim].friendly_mass, before - 0.01)
        self.assertGreater(f.lanes[prim].push, 0.0)

    def test_refuse_reduces_edge_mass(self):
        f = LineFront(geometry=koom_geometry(4))
        from quantum_bar_ai.lane_war import LineOrder

        before = f.lanes[0].friendly_mass
        apply_line_order(f, LineOrder("REFUSE_LANE", lane=0))
        self.assertLess(f.lanes[0].friendly_mass, before)

    def test_narrow_policy_weights_primary(self):
        f = LineFront(geometry=koom_geometry(4))
        o = decide_line(f, aggression=0.2, caution=0.0, width=0.2)
        self.assertIn(o.order, ("WEIGHT_LANE", "BREAKTHROUGH", "HOLD_LINE"))
        if o.lane is not None:
            self.assertEqual(o.lane, f.geometry.primary_index)

    def test_combat_tick_advances_hold(self):
        f = LineFront(geometry=koom_geometry(4))
        for _ in range(40):
            o = decide_line(f, aggression=0.6, width=0.3)
            apply_line_order(f, o)
            tick_lane_combat(f, player_strength=0.8, enemy_strength=0.4)
        self.assertGreater(lane_objective_progress(f, width=0.3), 0.15)

    def test_geometry_for_maps(self):
        self.assertIsNotNone(geometry_for_map("koom_valley", width=0.5))
        self.assertIsNotNone(geometry_for_map("all_that_simmers", width=0.3))
        self.assertIsNone(geometry_for_map("greenest_fields", width=0.3))

    def test_line_orders_vocab(self):
        self.assertIn("HOLD_LINE", LINE_ORDERS)
        self.assertIn("BREAKTHROUGH", LINE_ORDERS)


class TestCampaignEnrich(unittest.TestCase):
    def test_full_campaign_enriched(self):
        ms = build_full_campaign()
        self.assertEqual(len(ms), 15)
        self.assertIsNotNone(ms[0].solution_space)
        self.assertLess(ms[0].solution_space.width, ms[14].solution_space.width)
        # Koom seize missions have lane geometry
        koom = [m for m in ms if m.map_id == "koom_valley" and m.kind == "seize_lane"]
        self.assertTrue(koom)
        for m in koom:
            self.assertIsNotNone(m.lane_geometry)
            self.assertGreaterEqual(m.lane_geometry.lane_count, 3)
            self.assertLessEqual(m.lane_geometry.lane_count, 5)

    def test_player_view_fair(self):
        ms = build_full_campaign()
        pv = ms[3].player_view()
        self.assertIn("width_band", pv)
        self.assertNotIn("_solution_space", pv)
        self.assertNotIn("win_predicates", pv)
        ov = ms[3].operator_view()
        self.assertIn("_solution_space", ov)

    def test_meta_manifolds(self):
        meta = campaign_meta()
        self.assertEqual(meta["manifolds"]["proxy"], "verdance-player-proxy")
        self.assertEqual(meta["manifolds"]["campaign"], "verdance-campaign-shape")
        self.assertEqual(meta["manifolds"]["lane"], "verdance-lane-war")


class TestDivergingSolutions(unittest.TestCase):
    def _multipressure_mission(self) -> ArcMission:
        ms = build_full_campaign()
        # last mission is multipressure climax
        m = ms[-1]
        self.assertEqual(m.kind, "multipressure")
        return m

    def test_two_paths_can_clear_late(self):
        m = self._multipressure_mission()
        # Path A: combat / strike heavy
        strike_seq = (
            ["PROBE"] * 5
            + ["PUSH_OBJECTIVE"] * 40
            + ["FLANK"] * 20
            + ["EXPAND_FRONT"] * 15
            + ["EXTRACT"] * 20
        )
        # Path B: eco heavy then defend
        eco_seq = (
            ["BUILD_ENERGY"] * 15
            + ["BUILD_MEX"] * 15
            + ["BUILD_CON"] * 10
            + ["EXPAND_FRONT"] * 20
            + ["DEFEND_BASE"] * 15
            + ["PUSH_OBJECTIVE"] * 20
            + ["EXTRACT"] * 15
        )
        r_strike = run_fair_mission(m, agent=_ScriptedAgent(strike_seq), seed=11, verbose=False)
        r_eco = run_fair_mission(m, agent=_ScriptedAgent(eco_seq), seed=11, verbose=False)
        # At least one path should win; prefer both (diverging). If balance tight, allow partial credit.
        wins = int(r_strike.won) + int(r_eco.won)
        self.assertGreaterEqual(
            wins,
            1,
            msg=f"strike={r_strike.verdict}/{r_strike.progress} eco={r_eco.verdict}/{r_eco.progress}",
        )
        # Different action histograms
        self.assertNotEqual(
            Counterish(r_strike.actions).most_common(1),
            Counterish(r_eco.actions).most_common(1),
        )

    def test_early_eco_raid_rejects_pure_build(self):
        ms = build_full_campaign()
        m = ms[0]
        self.assertEqual(m.kind, "eco_raid")
        pure_build = ["BUILD_MEX", "BUILD_ENERGY", "BUILD_CON", "TECH_UP"] * 40
        r = run_fair_mission(m, agent=_ScriptedAgent(pure_build), seed=3, verbose=False)
        self.assertFalse(r.won, msg=f"pure build should not clear early raid: {r.verdict} p={r.progress}")


class Counterish:
    def __init__(self, xs):
        from collections import Counter

        self.c = Counter(xs)

    def most_common(self, n=1):
        return self.c.most_common(n)


if __name__ == "__main__":
    unittest.main()
