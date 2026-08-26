"""Offline tests for the campaign-flow density matrix.

Two things are being defended here.

The first is that rho is genuinely a density matrix. It is assembled from
faction amplitude fields rather than written down element by element, which
should make Hermiticity, positive semi-definiteness and unit trace automatic --
but "should" is why there are tests. If any of these fail, every observable
downstream is meaningless.

The second is that its off-diagonal structure means what the report claims it
means: two zones are coupled only when a power's reach actually runs through
both. A coupling between places the lattice does not join would be the same
class of error as the old similarity-based packet, where two empty zones on
opposite corners of the map read as maximally entangled.

Runs against the real lattice on disk, so it also catches the day a zone re-cut
or a graph rebuild quietly breaks the assumptions.
"""
from __future__ import annotations

import json
import math
import sys
import tempfile
import unittest
from pathlib import Path

WS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(WS / "tools"))

import campaign_flow_matrix_v1 as flow  # noqa: E402
import verdance_story_engine_v1 as engine  # noqa: E402


def load_state():
    return json.loads((WS / "state" / "campaign_state.json").read_text(encoding="utf-8-sig"))


class LatticeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.lattice = flow.Lattice(WS)

    def test_every_zone_in_the_graph_is_in_the_basis(self):
        graph = json.loads(
            (WS / "data" / "zone_maps" / "world_zone_graph.v1.json").read_text(encoding="utf-8-sig"))
        self.assertEqual(len({n["zoneId"] for n in graph["nodes"]}), self.lattice.n)
        self.assertEqual(self.lattice.dim, self.lattice.n + 1)

    def test_zone_weights_sum_to_one_and_each_map_carries_a_seventh(self):
        self.assertAlmostEqual(sum(self.lattice.weight.values()), 1.0, places=9)
        share = 1.0 / len(self.lattice.maps)
        for map_id in self.lattice.maps:
            got = sum(self.lattice.weight[z] for z in self.lattice.zones_by_map[map_id])
            self.assertAlmostEqual(got, share, places=9, msg=map_id)

    def test_no_zone_is_weightless(self):
        for zone_id, w in self.lattice.weight.items():
            self.assertGreater(w, 0.0, zone_id)

    def test_submerged_share_never_falls_as_the_water_rises(self):
        for zone_id in self.lattice.zone_ids:
            previous = -1.0
            for step in range(0, 21):
                level = step / 20.0
                share = self.lattice.submerged(zone_id, level)
                self.assertGreaterEqual(share, previous - 1e-9, (zone_id, level))
                self.assertTrue(0.0 <= share <= 1.0)
                previous = share

    def test_strategic_links_are_thinner_than_same_map_borders(self):
        self.assertLess(flow.LINK_WEIGHT["strategic_link"], flow.LINK_WEIGHT["same_map"])


class DensityMatrixTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.lattice = flow.Lattice(WS)
        cls.state = load_state()
        cls.occ = flow.seed_occupation(cls.lattice, cls.state)
        cls.levels = flow.waterlines(cls.state, WS, 0.0)
        names, vecs, weights = flow.faction_states(cls.lattice, cls.occ, cls.levels, flow.FLOW)
        cls.names, cls.vecs, cls.weights = names, vecs, weights
        cls.rho = flow.density(cls.lattice, names, vecs, weights)
        cls.matrix = flow.dense(cls.lattice, cls.rho)

    def test_trace_is_one(self):
        trace = sum(self.matrix[i][i] for i in range(self.lattice.dim))
        self.assertAlmostEqual(trace, 1.0, places=9)
        self.assertAlmostEqual(sum(self.rho["eigenvalues"]), 1.0, places=9)

    def test_hermitian(self):
        for i in range(self.lattice.dim):
            for j in range(i + 1, self.lattice.dim):
                self.assertAlmostEqual(self.matrix[i][j], self.matrix[j][i], places=12)

    def test_positive_semi_definite(self):
        for value in self.rho["eigenvalues"]:
            self.assertGreaterEqual(value, -1e-12)

    def test_rank_is_the_number_of_live_powers(self):
        significant = [v for v in self.rho["eigenvalues"] if v > 1e-9]
        self.assertEqual(len(significant), len(self.names))
        self.assertLessEqual(len(self.names), 8)

    def test_gram_spectrum_equals_the_full_matrix_spectrum(self):
        """The whole speed argument: the 6x6 Gram matrix carries rho's spectrum
        exactly, not approximately. If this drifts, the fast path is lying."""
        vals, _vecs = engine.jacobi_eigen(self.matrix)
        full = sorted((v for v in vals if v > 1e-9), reverse=True)
        fast = sorted((v for v in self.rho["eigenvalues"] if v > 1e-9), reverse=True)
        self.assertEqual(len(full), len(fast))
        for a, b in zip(full, fast):
            self.assertAlmostEqual(a, b, places=8)

    def test_diagonal_matches_the_reported_diagonal(self):
        for i in range(self.lattice.dim):
            self.assertAlmostEqual(self.matrix[i][i], self.rho["diagonal"][i], places=12)

    def test_purity_lies_between_the_maximally_mixed_bound_and_one(self):
        purity = sum(v * v for v in self.rho["eigenvalues"])
        self.assertGreaterEqual(purity, 1.0 / len(self.names) - 1e-9)
        self.assertLessEqual(purity, 1.0 + 1e-9)

    def test_ground_nobody_holds_or_reaches_couples_to_nothing(self):
        """The difference from a similarity measure, stated as a test.

        Under the old army-value-similarity packet two equally empty zones read
        as identical and therefore maximally entangled. Here an unheld,
        unreached zone has no amplitude in any power's state, so its whole row
        of rho is zero -- it is not entangled with anything, including the other
        empty places.
        """
        empty = [i for i in range(self.lattice.n) if self.matrix[i][i] < 1e-15]
        self.assertGreaterEqual(len(empty), 3,
                                "the opening position should leave some ground untouched")
        for i in empty:
            for j in range(self.lattice.dim):
                self.assertAlmostEqual(self.matrix[i][j], 0.0, places=15,
                                       msg=self.lattice.zone_ids[i])

        # Sharper: with the reach switched off, only ground a power actually
        # stands on has any amplitude, and the great majority of the opening
        # planet should be a dead row.
        tight = dict(flow.FLOW)
        tight["steps"] = 0.0
        names, vecs, weights = flow.faction_states(self.lattice, self.occ, self.levels, tight)
        matrix = flow.dense(self.lattice, flow.density(self.lattice, names, vecs, weights))
        unheld = [i for i in range(self.lattice.n) if matrix[i][i] < 1e-15]
        self.assertGreater(len(unheld), 60,
                           "82 of 102 zones read unclaimed at the opening")
        for i in unheld:
            for j in range(self.lattice.dim):
                self.assertAlmostEqual(matrix[i][j], 0.0, places=15,
                                       msg=self.lattice.zone_ids[i])

    def test_unclaimed_ground_is_not_a_power(self):
        """Unclaimed ground cannot move along a corridor, so it gets no state.

        Given one to itself it would span all seven maps as a single coherent
        mode and lead every spectrum in the campaign -- a fact about the
        modelling wearing the costume of a fact about the war.
        """
        self.assertNotIn(flow.NEUTRAL, self.names)
        self.assertGreater(self.occ.get(flow.NEUTRAL, {}).get(
            sorted(self.occ[flow.NEUTRAL])[0], 0.0), 0.0,
            "unclaimed ground still has to exist in the occupation")
        # ... and it is still counted honestly in the control readout.
        obs = flow.observables(self.lattice, self.rho, self.occ)
        self.assertGreater(obs["control"].get(flow.NEUTRAL, 0.0), 0.5)

    def test_coupling_needs_a_power_standing_in_both_places(self):
        """Every non-zero off-diagonal traces to some power with amplitude at
        both ends -- by reach along the lattice, or by holding both at once."""
        checked = 0
        for i in range(0, self.lattice.n, 3):
            for j in range(i + 1, self.lattice.n, 7):
                if abs(self.matrix[i][j]) < 1e-12:
                    continue
                checked += 1
                self.assertTrue(
                    any(abs(v[i]) > 1e-12 and abs(v[j]) > 1e-12 for v in self.vecs),
                    msg=(self.lattice.zone_ids[i], self.lattice.zone_ids[j]))
        self.assertGreater(checked, 50, "expected plenty of couplings to check")

    def test_neighbouring_zones_do_couple(self):
        found = 0
        for zone_id, neighbours in self.lattice.same_map_neighbours.items():
            i = self.lattice.index[zone_id]
            for other in neighbours:
                j = self.lattice.index[other]
                if abs(self.matrix[i][j]) > 1e-9:
                    found += 1
        self.assertGreater(found, 100, "the lattice should be richly coupled")


class WaterTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.lattice = flow.Lattice(WS)
        cls.state = load_state()

    def _water_weight(self, levels):
        occ = flow.seed_occupation(self.lattice, self.state)
        names, vecs, weights = flow.faction_states(self.lattice, occ, levels, flow.FLOW)
        rho = flow.density(self.lattice, names, vecs, weights)
        return rho["diagonal"][self.lattice.hydro_index]

    def test_a_drier_planet_puts_less_weight_on_the_water_mode(self):
        dry = self._water_weight({m: 0.0 for m in self.lattice.maps})
        wet = self._water_weight({m: 1.0 for m in self.lattice.maps})
        self.assertGreater(wet, dry)

    def test_a_dry_map_never_contributes_water(self):
        """Greenest Fields is a metal-free desert with amplitude 0. Flooding it
        would be a lie about the map, and the cycle must never try.

        Its zone map does carry a flood curve -- the cartographer measures every
        map the same way -- so the guarantee has to come from the circulation
        refusing to send it any water, not from the curve being empty.
        """
        for step in range(0, 13):
            phase = round(step * engine.HYDRO_PHASE_STEP, 6)
            levels = flow.waterlines(self.state, WS, phase)
            self.assertAlmostEqual(levels.get("greenest_fields", 0.0), 0.0, places=9)
        zones = self.lattice.zones_by_map["greenest_fields"]
        total = sum(self.lattice.weight[z] for z in zones)
        drowned = sum(self.lattice.weight[z] * self.lattice.submerged(z, 0.0) for z in zones)
        self.assertLess(drowned / total, 1e-3)

    def test_diffusion_does_not_inflate_the_ground_against_the_water(self):
        """(I + beta*W) is not norm preserving. Left uncorrected it buries the
        water mode under a scaling artefact, which would read as a finding."""
        occ = flow.seed_occupation(self.lattice, self.state)
        levels = {m: 1.0 for m in self.lattice.maps}
        _n, vecs, _w = flow.faction_states(self.lattice, occ, levels, flow.FLOW)
        for vec in vecs:
            self.assertAlmostEqual(sum(x * x for x in vec), 1.0, places=9)
        no_reach = dict(flow.FLOW)
        no_reach["steps"] = 0.0
        _n2, vecs2, _w2 = flow.faction_states(self.lattice, occ, levels, no_reach)
        # Whether or not the amplitude has been allowed to spread, the share of
        # a power that reads as water must be the same.
        for spread, tight in zip(vecs, vecs2):
            self.assertAlmostEqual(spread[self.lattice.hydro_index],
                                   tight[self.lattice.hydro_index], places=6)

    def test_the_water_cycle_conserves_the_planets_water(self):
        totals = []
        for mission in range(1, 13):
            phase = round((mission - 1) * engine.HYDRO_PHASE_STEP, 6)
            levels = flow.waterlines(self.state, WS, phase)
            probe = json.loads(json.dumps(self.state))
            hydro = engine.ensure_planet_hydrology(probe, WS)
            hydro["phase"] = phase
            engine.distribute_planet_water(hydro)
            totals.append(sum(float(r.get("fill", 0.0)) for r in hydro["maps"].values()))
            self.assertTrue(all(0.0 <= v <= 1.0 for v in levels.values()))
        for value in totals[1:]:
            self.assertAlmostEqual(value, totals[0], places=3)


class ArcTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.lattice = flow.Lattice(WS)
        cls.state = load_state()

    def test_ground_is_moved_but_never_created_or_destroyed(self):
        occ = flow.seed_occupation(self.lattice, self.state)
        opening = sum(sum(z.values()) for z in occ.values())
        self.assertAlmostEqual(opening, 1.0, places=9)
        for mission in range(1, 12):
            stop = flow.mission_stop(self.lattice, self.state, mission, WS)
            levels = flow.waterlines(self.state, WS,
                                     round((mission - 1) * engine.HYDRO_PHASE_STEP, 6))
            flow.resolve_mission(self.lattice, occ, stop, levels.get(stop["mapId"], 0.0), flow.FLOW)
            self.assertAlmostEqual(sum(sum(z.values()) for z in occ.values()), 1.0, places=9)

    def test_a_sortie_leaves_the_player_holding_more_than_before(self):
        occ = flow.seed_occupation(self.lattice, self.state)
        before = sum(occ.get(flow.PLAYER, {}).values())
        stop = flow.mission_stop(self.lattice, self.state, 1, WS)
        flow.resolve_mission(self.lattice, occ, stop, 0.0, flow.FLOW)
        self.assertGreater(sum(occ.get(flow.PLAYER, {}).values()), before)

    def test_a_drowned_zone_resists_being_claimed(self):
        stop = flow.mission_stop(self.lattice, self.state, 3, WS)
        gains = []
        for level in (0.0, 1.0):
            occ = flow.seed_occupation(self.lattice, self.state)
            before = sum(occ.get(flow.PLAYER, {}).values())
            flow.resolve_mission(self.lattice, occ, stop, level, flow.FLOW)
            gains.append(sum(occ.get(flow.PLAYER, {}).values()) - before)
        self.assertGreater(gains[0], gains[1],
                           "flooding Koom Valley should make its ground harder to take")

    def test_deploy_and_objective_are_never_the_same_place(self):
        """Migration folded some old rectangles together. The engine separates
        them again when it materialises an intent; so must this."""
        for mission in range(1, 15):
            stop = flow.mission_stop(self.lattice, self.state, mission, WS)
            self.assertNotEqual(stop["deployZoneId"], stop["targetZoneId"],
                                "mission {0}".format(mission))
            self.assertIn(stop["deployZoneId"], self.lattice.index)
            self.assertIn(stop["targetZoneId"], self.lattice.index)

    def test_the_arc_is_deterministic(self):
        a = flow.run_arc(self.lattice, self.state, WS, 11, "clean")
        b = flow.run_arc(self.lattice, self.state, WS, 11, "clean")
        self.assertEqual(json.dumps(a, sort_keys=True), json.dumps(b, sort_keys=True))

    def test_scouting_never_writes_campaign_state(self):
        path = WS / "state" / "campaign_state.json"
        before = path.read_bytes()
        flow.run_arc(self.lattice, self.state, WS, 11, "clean")
        flow.waterlines(self.state, WS, 0.5)
        self.assertEqual(path.read_bytes(), before)
        self.assertNotIn("hydrology", self.state,
                         "ensure_planet_hydrology must run on a copy, not the caller's state")

    def test_who_the_story_ends_up_being_about_depends_on_the_knobs(self):
        """The campaign concentrates either way. What the authored knobs decide
        is which power it concentrates around -- and that turns out to be a
        binary, not a slider: the player either leads the dominant mode or
        never touches it."""
        leads = {}
        for profile in ("sweeping", "clean", "grinding", "losing"):
            arc = flow.run_arc(self.lattice, self.state, WS, 11, profile)
            entropy = [s["observables"]["entropy"] for s in arc["steps"]]
            self.assertLess(entropy[-1], entropy[0], profile)
            coeffs = arc["steps"][-1]["observables"]["leadCoeffs"]
            leads[profile] = max(coeffs.items(), key=lambda kv: abs(kv[1]))[0]
        self.assertEqual(leads["sweeping"], flow.PLAYER)
        self.assertEqual(leads["clean"], flow.PLAYER)
        self.assertNotEqual(leads["losing"], flow.PLAYER)

    def test_the_upper_bound_still_bounds(self):
        """Purity is no longer monotone in the claim rate -- with living
        factions a losing campaign concentrates around the antagonist instead
        of not concentrating at all. What must survive is the ceiling: the
        past-any-player `sweeping` profile closes tighter than every real one."""
        finals = {}
        for profile in ("losing", "grinding", "clean", "sweeping"):
            arc = flow.run_arc(self.lattice, self.state, WS, 11, profile)
            finals[profile] = arc["steps"][-1]["observables"]["purity"]
        for profile in ("losing", "grinding", "clean"):
            self.assertGreater(finals["sweeping"], finals[profile], profile)


class DynamicsTests(unittest.TestCase):
    """The living-world mechanisms: temperaments, the bloom, the transition,
    the opening drafts. Each test pins the mechanism, not the tuning -- the
    knobs are guesses by design and the experiments exist to argue with them.
    """

    @classmethod
    def setUpClass(cls):
        cls.lattice = flow.Lattice(WS)
        cls.state = load_state()
        cls.dyn = flow.Dynamics(cls.lattice, cls.state, WS, 11)

    def test_swing_is_bounded_and_a_dry_map_never_swings(self):
        """Greenest Fields' waterline can do what it likes -- its flood moves
        no ground, so its swing is zero by fiat and the mercs never sleep
        there."""
        for number in range(0, 12):
            for mid in self.lattice.maps:
                s = self.dyn.swing_at(mid, number)
                self.assertGreaterEqual(s, 0.0)
                self.assertLessEqual(s, 1.0)
            self.assertEqual(self.dyn.swing_at("greenest_fields", number), 0.0)

    def test_temperaments_pull_opposite_ways(self):
        """The owner's judgment call, at the mechanism level: a still world
        wakes the mercs, a swinging world wakes the armada."""
        still = flow.Dynamics(self.lattice, self.state, WS, 11, force_swing=0.0)
        storm = flow.Dynamics(self.lattice, self.state, WS, 11, force_swing=1.0)
        for mid in self.lattice.maps:
            self.assertGreater(still.activity("nullmercs", mid, 3),
                               still.activity("armada", mid, 3))
            self.assertGreater(storm.activity("armada", mid, 3),
                               storm.activity("nullmercs", mid, 3))

    def test_the_weather_decides_who_grows(self):
        """The same directional truth at the occupation level: roll the same
        arc under pinned weather and watch which empire outgrows the other."""
        growth = {}
        for label, force in (("still", 0.0), ("storm", 1.0)):
            dyn = flow.Dynamics(self.lattice, self.state, WS, 11,
                                force_swing=force)
            arc = flow.run_arc(self.lattice, self.state, WS, 11, "clean",
                               dyn=dyn, opening="cold_war")
            first = arc["steps"][0]["observables"]["control"]
            last = arc["steps"][-1]["observables"]["control"]
            growth[label] = {
                f: last.get(f, 0.0) - first.get(f, 0.0)
                for f in ("armada", "nullmercs")
            }
        self.assertGreater(growth["still"]["nullmercs"],
                           growth["still"]["armada"])
        self.assertGreater(growth["storm"]["armada"],
                           growth["storm"]["nullmercs"])

    def test_bloom_fires_after_recession_and_decays_in_still_water(self):
        series = flow.bloom_series([0.0, 0.0, 0.9, 0.0, 0.0, 0.0],
                                   gain=0.6, decay=0.45)
        self.assertEqual(series[0], 0.0)
        self.assertEqual(series[1], 0.0)
        self.assertGreater(series[2], 0.0)
        for a, b in zip(series[2:], series[3:]):
            self.assertLess(b, a)
        self.assertLess(series[-1], 0.15 * series[2])

    def test_the_bloom_lives_on_the_wild_maps(self):
        occ = flow.seed_occupation(self.lattice, self.state)
        wild_maps = sorted({self.lattice.map_of[z]
                            for z, held in (occ.get("wild") or {}).items()
                            if held > 0.0})
        self.assertEqual(self.dyn.wild_maps, wild_maps)
        self.assertTrue(wild_maps, "the planet should have raptor country")
        for mid in self.lattice.maps:
            if mid not in wild_maps:
                for number in range(0, 12):
                    self.assertEqual(self.dyn.bloom_at(mid, number), 0.0)

    def test_cortex_ground_yields_at_the_bunker_rate(self):
        occ = {"cortex": {"z": 1.0}, "armada": {"y": 1.0}}
        took_cortex = flow.convert(occ, "z", flow.PLAYER, 0.5)
        took_armada = flow.convert(occ, "y", flow.PLAYER, 0.5)
        self.assertAlmostEqual(took_cortex, 0.5 * flow.CORTEX_HOLD, places=9)
        self.assertAlmostEqual(took_armada, 0.5, places=9)

    def test_cortex_is_the_constant(self):
        """Bunker and scout: the cortex never attacks anyone, and its share of
        the planet barely moves across the whole arc."""
        arc = flow.run_arc(self.lattice, self.state, WS, 11, "clean",
                           opening="cold_war")
        shares = []
        for step in arc["steps"]:
            shares.append(step["observables"]["control"].get("cortex", 0.0))
            outcome = step.get("outcome") or {}
            self.assertNotIn("cortex", outcome.get("rivalry") or {})
        self.assertGreater(min(shares), 0.0)
        self.assertLess(max(shares) - min(shares), 0.3 * max(shares))

    def test_mass_is_conserved_under_full_dynamics(self):
        occ = flow.apply_opening(self.lattice,
                                 flow.seed_occupation(self.lattice, self.state),
                                 "cold_war")
        for mission in range(1, 12):
            stop = flow.mission_stop(self.lattice, self.state, mission, WS)
            level = self.dyn.levels_at(mission).get(stop["mapId"], 0.0)
            flow.resolve_mission(self.lattice, occ, stop, level, flow.FLOW,
                                 self.dyn)
            total = sum(sum(z.values()) for z in occ.values())
            self.assertAlmostEqual(total, 1.0, places=9,
                                   msg="mission {0}".format(mission))

    def test_the_player_dips_and_comes_back_under_defaults(self):
        """The default knobs must live on the ridge the regression experiment
        maps: visible ground given in the transition window, earned back with
        interest by the finale."""
        arc = flow.run_arc(self.lattice, self.state, WS, 11, "clean",
                           opening="cold_war")
        masses = [s["observables"]["control"].get(flow.PLAYER, 0.0)
                  for s in arc["steps"]]
        start = int(flow.PLAYER_ARC["regressStart"])
        end = int(flow.PLAYER_ARC["regressEnd"])
        pre = masses[start - 1]
        self.assertLess(min(masses[start:end + 1]), pre,
                        "the transition should visibly cost ground")
        self.assertGreater(masses[-1], pre,
                           "the factory press should earn it back with interest")

    def test_regression_pressure_stays_inside_the_window(self):
        arc = flow.run_arc(self.lattice, self.state, WS, 11, "clean",
                           opening="cold_war")
        start = int(flow.PLAYER_ARC["regressStart"])
        end = int(flow.PLAYER_ARC["regressEnd"])
        for step in arc["steps"][1:]:
            regressed = (step.get("outcome") or {}).get("regressed", 0.0)
            if start <= step["missionNumber"] <= end:
                self.assertGreater(regressed, 0.0)
            else:
                self.assertEqual(regressed, 0.0)

    def test_opening_drafts_conserve_mass_and_the_player(self):
        for name in flow.OPENING_NAMES:
            occ = flow.apply_opening(
                self.lattice, flow.seed_occupation(self.lattice, self.state),
                name)
            total = sum(sum(z.values()) for z in occ.values())
            self.assertAlmostEqual(total, 1.0, places=9, msg=name)
            base = flow.seed_occupation(self.lattice, self.state)
            self.assertEqual(occ.get(flow.PLAYER), base.get(flow.PLAYER), name)
            self.assertEqual(occ.get("wild"), base.get("wild"), name)

    def test_opening_drafts_are_deterministic_and_denser(self):
        for name in ("cold_war", "armada_ascendant", "patchwork"):
            a = flow.apply_opening(
                self.lattice, flow.seed_occupation(self.lattice, self.state), name)
            b = flow.apply_opening(
                self.lattice, flow.seed_occupation(self.lattice, self.state), name)
            self.assertEqual(json.dumps(a, sort_keys=True),
                             json.dumps(b, sort_keys=True), name)
            neutral = sum((a.get(flow.NEUTRAL) or {}).values())
            base_neutral = sum(flow.seed_occupation(
                self.lattice, self.state).get(flow.NEUTRAL, {}).values())
            self.assertLess(neutral, base_neutral, name)

    def test_the_second_mode_is_never_the_lead(self):
        arc = flow.run_arc(self.lattice, self.state, WS, 11, "clean",
                           opening="cold_war")
        for step in arc["steps"]:
            o = step["observables"]
            coeffs = o.get("leadCoeffs") or {}
            if not coeffs or o.get("secondMode") is None:
                continue
            lead = max(coeffs.items(), key=lambda kv: abs(kv[1]))[0]
            self.assertNotEqual(o["secondMode"], lead)

    def test_scouting_with_dynamics_never_writes_campaign_state(self):
        path = WS / "state" / "campaign_state.json"
        before = path.read_bytes()
        flow.Dynamics(self.lattice, self.state, WS, 4)
        flow.run_arc(self.lattice, self.state, WS, 4, "clean",
                     opening="armada_ascendant")
        flow.experiment_bloom(self.lattice, self.state, WS, 4,
                              gains=(0.6,), decays=(0.45,))
        self.assertEqual(path.read_bytes(), before)
        self.assertNotIn("hydrology", self.state)


class WeatherSystemsTests(unittest.TestCase):
    """The weather beneath the weather: seasons, tides, wind, the re-tuned
    theatres, and the owner's calibration of the player's true size."""

    @classmethod
    def setUpClass(cls):
        cls.lattice = flow.Lattice(WS)
        cls.state = load_state()

    def test_the_storm_turns_with_the_season(self):
        dyn = flow.Dynamics(self.lattice, self.state, WS, 11,
                            seasons={"period": 8.0, "depth": 0.6})
        self.assertAlmostEqual(dyn.storm(1), 0.0, places=9)
        self.assertAlmostEqual(dyn.storm(5), 1.0, places=9)
        self.assertAlmostEqual(dyn.storm(9), 0.0, places=9)
        for n in range(0, 13):
            self.assertTrue(0.0 <= dyn.storm(n) <= 1.0)

    def test_seasons_give_the_planet_a_real_calm(self):
        """The conserved travelling wave keeps planetary churn nearly
        constant; the amplitude envelope is what lets the planet as a whole
        have quiet stretches for the mercs to write contracts in."""
        def spread(depth):
            dyn = flow.Dynamics(self.lattice, self.state, WS, 11,
                                seasons={"depth": depth})
            sw = [dyn.planet_swing(n) for n in range(1, 12)]
            return max(sw) - min(sw)
        self.assertGreater(spread(0.8), spread(0.0) + 0.15)

    def test_koom_valley_keeps_its_flats(self):
        """Owner direction: room for permanent infrastructure on the flats
        away from the pools. The waterline never passes the cap, and at the
        cap most of the valley is dry ground."""
        cap = flow.HYDRO_TUNE["koom_valley"]["cap"]
        for step in range(13):
            levels = flow.waterlines(self.state, WS, step / 12.0)
            self.assertLessEqual(levels["koom_valley"], cap + 1e-9)
        dyn = flow.Dynamics(self.lattice, self.state, WS, 11)
        for n in range(-2, 12):
            self.assertLessEqual(dyn.levels_at(n).get("koom_valley", 0.0),
                                 cap + 1e-9)
        zids = self.lattice.zones_by_map["koom_valley"]
        total = sum(self.lattice.weight[z] for z in zids)
        flooded = sum(self.lattice.weight[z] * self.lattice.submerged(z, cap)
                      for z in zids) / total
        self.assertLess(flooded, 0.30, "the flats must stay dry")

    def test_the_rock_jungle_water_now_moves_ground(self):
        """Owner direction: more water dynamics to drive raptor presence.
        The deepened karst response turns the jungle's standing water into
        living water, and the bloom actually fires there."""
        self.assertGreater(self.lattice.flood_swing("the_rock_jungle"), 0.2)
        dyn = flow.Dynamics(self.lattice, self.state, WS, 11)
        self.assertGreater(max(dyn.bloom_at("the_rock_jungle", n)
                               for n in range(1, 12)), 0.1)

    def test_the_tide_feeds_the_bloom_on_the_way_up(self):
        """Rising water arrives as intermittent floods, and every pulse that
        recedes feeds the raptors the same mission -- no beat of lag."""
        quiet = flow.Dynamics(self.lattice, self.state, WS, 11,
                              tide={"bloomFeed": 0.0})
        loud = flow.Dynamics(self.lattice, self.state, WS, 11)

        def total(dyn):
            return sum(dyn.bloom_at(m, n)
                       for m in dyn.wild_maps for n in range(1, 12))
        self.assertGreater(total(loud), total(quiet))

    def test_the_mission_fights_the_average_of_the_tide(self):
        dyn = flow.Dynamics(self.lattice, self.state, WS, 11)
        checked = 0
        rising = 0
        for n in range(1, 12):
            for mid in self.lattice.maps:
                tide = dyn.tide_at(mid, n)
                if tide["dir"] == "slack":
                    continue
                if tide["dir"] == "rising":
                    rising += 1
                    self.assertGreater(tide["pulses"], 0)
                now = dyn.levels_at(n).get(mid, 0.0)
                prev = dyn.levels_at(n - 1).get(mid, 0.0)
                for zid in self.lattice.zones_by_map[mid][:3]:
                    lo = min(self.lattice.submerged(zid, now),
                             self.lattice.submerged(zid, prev))
                    hi = max(self.lattice.submerged(zid, now),
                             self.lattice.submerged(zid, prev))
                    eff = dyn.mission_submerged(self.lattice, zid, n)
                    self.assertGreaterEqual(eff, lo - 1e-9, (mid, zid, n))
                    self.assertLessEqual(eff, hi + 1e-9, (mid, zid, n))
                    checked += 1
        self.assertGreater(checked, 10)
        self.assertGreater(rising, 0, "the arc should have rising missions")

    def test_the_wind_is_real_and_sets_the_pace(self):
        """Every map's wind range comes off the authored map pool, and the
        wind is what sets the pace of everyone's economy."""
        self.assertEqual(set(self.lattice.wind), set(self.lattice.maps))
        for mid, rec in self.lattice.wind.items():
            self.assertLess(rec["min"], rec["max"], mid)
        dyn = flow.Dynamics(self.lattice, self.state, WS, 11,
                            seasons={"period": 8.0, "depth": 0.6})
        lo = flow.WIND["floor"]
        hi = flow.WIND["floor"] + flow.WIND["gain"]
        for n in range(1, 12):
            for mid in self.lattice.maps:
                eco = dyn.eco(mid, n)
                self.assertTrue(lo - 1e-9 <= eco <= hi + 1e-9, (mid, n, eco))
        # The storm runs the wind up its range ...
        self.assertGreater(dyn.eco("tabula", 5), dyn.eco("tabula", 1))
        # ... and the windier map runs faster at the same hour.
        self.assertGreater(dyn.eco("tabula", 5),
                           dyn.eco("all_that_simmers", 5))

    def test_a_bigger_player_is_a_bigger_story(self):
        """Owner calibration: "expect the player to be massively more
        impactful then you expect." More impact must mean more final ground
        and a no-later arrival at the head of the dominant mode."""
        finals, leads = {}, {}
        for impact in (1.0, 2.5):
            dyn = flow.Dynamics(self.lattice, self.state, WS, 11,
                                player_impact=impact)
            arc = flow.run_arc(self.lattice, self.state, WS, 11, "clean",
                               dyn=dyn, opening="cold_war")
            finals[impact] = arc["steps"][-1]["observables"]["control"].get(
                flow.PLAYER, 0.0)
            leads[impact] = flow.player_leads_at(arc)
        self.assertGreater(finals[2.5], finals[1.0])
        self.assertLessEqual(leads[2.5] or 99, leads[1.0] or 99)


class ReportTests(unittest.TestCase):
    def test_report_and_json_are_written(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            rc = flow.main([
                "--workspace", str(WS),
                "--missions", "6",
                "--profile", "clean",
                "--no-regime",
                "--no-experiments",
                "--json", str(out / "flow.json"),
                "--report", str(out / "flow.md"),
            ])
            self.assertEqual(rc, 0)
            payload = json.loads((out / "flow.json").read_text(encoding="utf-8"))
            self.assertEqual(payload["schemaVersion"], flow.SCHEMA)
            self.assertEqual(len(payload["arcs"][0]["steps"]), 7)  # opening + 6
            text = (out / "flow.md").read_text(encoding="utf-8")
            self.assertIn("Campaign flow, as a density matrix", text)
            self.assertIn("Water against the spine", text)
            self.assertIn("world's pulse", text)
            self.assertTrue(text.isascii(), "the report must stay ASCII")

    def test_experiment_sections_render_and_stay_ascii(self):
        lattice = flow.Lattice(WS)
        state = load_state()
        payload = {
            "generatedFrom": {"zones": lattice.n, "maps": len(lattice.maps),
                              "dimension": lattice.dim, "missions": 4},
            "arcs": [flow.run_arc(lattice, state, WS, 4, "clean")],
            "experiments": {
                "bloom": flow.experiment_bloom(lattice, state, WS, 4,
                                               gains=(0.6,), decays=(0.45,)),
                "openings": flow.experiment_openings(lattice, state, WS, 4,
                                                     profiles=("clean",)),
                "seasons": flow.experiment_seasons(lattice, state, WS, 4,
                                                   periods=(7.0,),
                                                   depths=(0.6,)),
                "impact": flow.experiment_impact(lattice, state, WS, 4,
                                                 impacts=(2.0,)),
            },
        }
        with tempfile.TemporaryDirectory() as tmp:
            report = Path(tmp) / "flow.md"
            flow.write_report(payload, report)
            text = report.read_text(encoding="utf-8")
            self.assertIn("The bloom: punctuation or power", text)
            self.assertIn("The four drafted worlds", text)
            self.assertIn("The seasons: a calm to be calm in", text)
            self.assertIn("How big the player really is", text)
            self.assertIn("Where these shapes would land", text)
            self.assertTrue(text.isascii(), "the report must stay ASCII")


if __name__ == "__main__":
    unittest.main()
