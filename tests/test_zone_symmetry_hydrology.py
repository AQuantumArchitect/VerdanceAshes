"""Offline tests for symmetric zone cutting and the planet's water cycle.

The fixture map is an exact north-south mirror with a low centre and ridged
edges, so the symmetry detector, the quotient cut and the flood curves all have
a known right answer.
"""
from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

WS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(WS / "tools"))

import hydrology_v1 as hydro  # noqa: E402
import map_symmetry_v1 as symmetry  # noqa: E402
import verdance_story_engine_v1 as engine  # noqa: E402
import zone_cartographer_v1 as carto  # noqa: E402

RES = 32
SIZE = 8192


def cell_index(row, col):
    return row * RES + col


def build_mirror_terrain(res=RES, size=SIZE):
    """Exact north-south mirror: low centre, ridged north and south edges."""
    cells = []
    for row in range(res):
        mirrored = min(row, res - 1 - row)
        height = 300.0 - 8.0 * mirrored
        slope, water, buildable, tank = 0.03, 0.0, 1.0, 1.0
        if mirrored <= 2:
            height, slope, buildable, tank = 520.0, 0.6, 0.0, 0.0
        for col in range(res):
            # A gentle east-west tilt so the map is mirrored north-south and
            # ONLY north-south -- otherwise a map uniform along each row is
            # symmetric every way at once and the test proves nothing.
            cells.append([height + col * 12.0, slope, water, buildable,
                          0.0, tank * (1.0 - col * 0.02), 0.0, 0, 0])
    return {
        "schemaVersion": "verdance-terrain-raster/1.0",
        "mapId": "mirror_map",
        "mapName": "Mirror Map",
        "size": {"x": size, "z": size},
        "grid": {"res": res, "cellW": size / res, "cellH": size / res,
                 "squareSize": 8, "metalSquare": 16},
        "channels": list(carto.CH),
        "cells": cells,
        "metalSpots": [{"x": size * 0.5, "z": size * 0.5, "metal": 2.0}],
        "startPositions": [{"team": "0", "x": size * 0.5, "z": size * 0.12},
                           {"team": "1", "x": size * 0.5, "z": size * 0.88}],
        "startBoxes": [],
        "teams": [],
        "incompleteRows": [],
    }


def build_lopsided_terrain(res=RES, size=SIZE):
    """Deliberately asymmetric: a ramp with a corner plateau."""
    cells = []
    for row in range(res):
        for col in range(res):
            height = 100.0 + col * 9.0
            slope, water, buildable, tank = 0.04, 0.0, 1.0, 1.0
            if row < res // 2:            # whole northern half is high ground
                height += 260.0
            if row < 6 and col < 6:
                height, slope, buildable = 700.0, 0.55, 0.0
            cells.append([height, slope, water, buildable, 0.0, tank, 0.0, 0, 0])
    return {
        "schemaVersion": "verdance-terrain-raster/1.0",
        "mapId": "lopsided_map",
        "mapName": "Lopsided Map",
        "size": {"x": size, "z": size},
        "grid": {"res": res, "cellW": size / res, "cellH": size / res,
                 "squareSize": 8, "metalSquare": 16},
        "channels": list(carto.CH),
        "cells": cells,
        "metalSpots": [],
        "startPositions": [],
        "startBoxes": [],
        "teams": [],
        "incompleteRows": [],
    }


class SymmetryDetectionTests(unittest.TestCase):
    def test_detects_the_mirror_it_was_built_with(self):
        info = symmetry.detect(build_mirror_terrain())
        self.assertIn("mirror_ns", info["accepted"])
        self.assertAlmostEqual(info["scores"]["mirror_ns"], 1.0, places=6)
        self.assertEqual(info["order"], 2)
        self.assertEqual(info["domainCells"], RES * RES // 2)

    def test_declines_an_asymmetric_map(self):
        info = symmetry.detect(build_lopsided_terrain(), threshold=0.95)
        self.assertEqual(info["accepted"], [])
        self.assertEqual(info["order"], 1)

    def test_forcing_adopts_the_best_axis_anyway(self):
        terrain = build_lopsided_terrain()
        info = symmetry.detect_forced(terrain, threshold=0.99, force_best=True)
        self.assertTrue(info["forced"])
        self.assertEqual(info["order"], 2)

    def test_fundamental_domain_generates_the_whole_map(self):
        info = symmetry.detect(build_mirror_terrain())
        seen = set()
        for idx in range(RES * RES):
            if info["_domain"][idx]:
                seen.update(symmetry.orbit(idx, RES, info["_ops"]))
        self.assertEqual(len(seen), RES * RES)


class SymmetricCutTests(unittest.TestCase):
    def setUp(self):
        self.terrain = build_mirror_terrain()
        self.info = symmetry.detect(self.terrain)
        grid = carto.CellGrid(self.terrain, [], symmetry=self.info)
        self.zone_map = carto.build_zone_map(grid, 6, 12)
        self.masks = {
            zone["zoneId"]: {i for start, length in zone["cells"]
                             for i in range(start, start + length)}
            for zone in self.zone_map["zones"]
        }

    def test_every_cell_owned_exactly_once(self):
        total = sum(len(m) for m in self.masks.values())
        self.assertEqual(total, RES * RES)
        union = set()
        for mask in self.masks.values():
            self.assertFalse(union & mask, "a cell is claimed twice")
            union |= mask

    def test_every_zone_has_a_mirrored_partner(self):
        op = symmetry.OPS["mirror_ns"]
        for zone_id, cells in self.masks.items():
            image = set()
            for i in cells:
                row, col = divmod(i, RES)
                rr, cc = op(row, col, RES)
                image.add(rr * RES + cc)
            self.assertTrue(any(image == other for other in self.masks.values()),
                            f"{zone_id} has no mirrored partner")

    def test_partners_agree_on_their_role(self):
        by_family = {}
        for zone in self.zone_map["zones"]:
            by_family.setdefault(zone["symmetryFamily"], set()).add(zone["role"])
        for family, roles in by_family.items():
            self.assertEqual(len(roles), 1, f"family {family} disagrees: {roles}")

    def test_the_symmetry_is_recorded_in_the_zone_map(self):
        block = self.zone_map["symmetry"]
        self.assertEqual(block["order"], 2)
        self.assertIn("mirror_ns", block["accepted"])


class HydrologyProfileTests(unittest.TestCase):
    def setUp(self):
        self.terrain = build_mirror_terrain()
        self.profile = hydro.profile(self.terrain, steps=9, amplitude=1.0)

    def test_ladder_is_monotone_and_capped(self):
        rungs = self.profile["rungs"]
        self.assertEqual(len(rungs), 9)
        for earlier, later in zip(rungs, rungs[1:]):
            self.assertLessEqual(earlier["elevation"], later["elevation"])
            self.assertLessEqual(earlier["areaSubmerged"], later["areaSubmerged"])
        self.assertLessEqual(rungs[-1]["areaSubmerged"],
                             hydro.MAX_SUBMERGED_SHARE + 1e-6)

    def test_a_zero_amplitude_map_never_floods(self):
        profile = hydro.profile(self.terrain, steps=9, amplitude=0.0)
        first = profile["rungs"][0]["areaSubmerged"]
        for rung in profile["rungs"]:
            self.assertEqual(rung["areaSubmerged"], first)

    def test_basin_names_are_stable_across_rungs(self):
        known = {b["basinId"] for b in self.profile["basins"]}
        self.assertTrue(known)
        for rung in self.profile["rungs"]:
            for name in rung["basins"]:
                self.assertIn(name, known)

    def test_terraform_delta_matches_the_elevation_it_claims(self):
        for rung in self.profile["rungs"]:
            self.assertAlmostEqual(rung["terraformDelta"],
                                   rung["elevation"] - hydro.SEA_LEVEL, places=3)


class FloodAwareZoneTests(unittest.TestCase):
    def setUp(self):
        self.terrain = build_mirror_terrain()
        self.profile = hydro.profile(self.terrain, steps=9, amplitude=1.0)
        self.grid = carto.CellGrid(self.terrain, [],
                                   symmetry=symmetry.detect(self.terrain),
                                   hydrology=self.profile)
        self.zone_map = carto.build_zone_map(self.grid, 6, 12)

    def test_flood_curves_are_monotone(self):
        for zone in self.zone_map["zones"]:
            curve = zone["hydrology"]["submergedAt"]
            self.assertTrue(curve)
            for earlier, later in zip(curve, curve[1:]):
                self.assertLessEqual(earlier, later, f"{zone['zoneId']} un-floods")

    def test_no_camp_sits_below_the_routine_waterline(self):
        routine = carto.routine_waterline(self.grid)
        self.assertIsNotNone(routine)
        eligible = 0
        for zone in self.zone_map["zones"]:
            if not zone["campEligible"]:
                continue
            anchor = zone["anchor"]
            self.assertIsNotNone(anchor)
            col = min(RES - 1, int(anchor["x"] * RES))
            row = min(RES - 1, int(anchor["z"] * RES))
            height = self.terrain["cells"][row * RES + col][carto.CH["height"]]
            self.assertGreater(height, routine,
                               f"{zone['zoneId']} would camp under water")
            eligible += 1
        self.assertGreater(eligible, 0, "no zone could hold a camp at all")

    def test_the_low_centre_is_the_ground_that_drowns(self):
        flooding = [z for z in self.zone_map["zones"]
                    if z["hydrology"]["floodsAt"] <= 0.7]
        self.assertTrue(flooding, "a map with a basin should have drowning ground")
        for zone in flooding:
            centre_rows = [divmod(i, RES)[0]
                           for start, length in zone["cells"]
                           for i in range(start, start + length)]
            mean_row = sum(centre_rows) / len(centre_rows)
            self.assertGreater(mean_row, RES * 0.2)
            self.assertLess(mean_row, RES * 0.8)


class PlanetWaterCycleTests(unittest.TestCase):
    def setUp(self):
        self.state = {}
        engine.ensure_planet_hydrology(self.state, WS)

    def test_water_is_conserved(self):
        total = self.state["hydrology"]["planetWater"]
        for _ in range(12):
            engine.advance_planet_hydrology(self.state, WS)
            self.assertAlmostEqual(self.state["hydrology"]["planetWater"],
                                   total, places=2)

    def test_every_holder_both_floods_and_drains(self):
        holders = [mid for mid, rec in self.state["hydrology"]["maps"].items()
                   if rec["amplitude"] > 0]
        self.assertTrue(holders)
        seen = {mid: [] for mid in holders}
        for _ in range(13):
            for mid in holders:
                seen[mid].append(self.state["hydrology"]["maps"][mid]["level"])
            engine.advance_planet_hydrology(self.state, WS)
        for mid, levels in seen.items():
            self.assertGreater(max(levels), 0.6, f"{mid} never floods")
            self.assertLess(min(levels), 0.35, f"{mid} never drains")

    def test_a_dry_map_never_takes_water(self):
        dry = [mid for mid, rec in self.state["hydrology"]["maps"].items()
               if rec["amplitude"] == 0.0]
        self.assertTrue(dry, "greenest_fields should hold no cycle water")
        for _ in range(8):
            engine.advance_planet_hydrology(self.state, WS)
            for mid in dry:
                self.assertEqual(self.state["hydrology"]["maps"][mid]["level"], 0.0)

    def test_the_cycle_is_deterministic(self):
        first = {}
        engine.advance_planet_hydrology(self.state, WS)
        first = {mid: rec["level"]
                 for mid, rec in self.state["hydrology"]["maps"].items()}
        other = {}
        engine.ensure_planet_hydrology(other, WS)
        engine.advance_planet_hydrology(other, WS)
        second = {mid: rec["level"] for mid, rec in other["hydrology"]["maps"].items()}
        self.assertEqual(first, second)


class FloodBeatTests(unittest.TestCase):
    def setUp(self):
        self.voice = json.loads(
            (WS / "data" / "story" / "ketha_voice.json").read_text(encoding="utf-8-sig"))
        self.state = {"campaignId": "verdance_ashes", "missionNumber": 4}
        self.objective = {"targetZoneId": "X"}

    def beats_for(self, level, amplitude, next_level=None):
        # The mission's own tide: direction and range now come from where the
        # waterline is actually headed next (map_waterline's nextLevel probe),
        # not a fixed swing-toward-the-opposite-pole guess off the current
        # level alone.
        waterline = {"level": level, "amplitude": amplitude,
                    "nextLevel": level if next_level is None else next_level}
        return engine.generate_beats(self.state, self.voice, "tempo", self.objective, waterline)

    def test_no_event_on_a_map_whose_water_does_not_move(self):
        beats = self.beats_for(0.9, 0.0, next_level=0.4)
        self.assertFalse([b for b in beats if b["id"].startswith("b9")])

    def test_a_full_basin_drains(self):
        beats = self.beats_for(0.9, 1.0, next_level=0.45)
        event = [b for b in beats if b["id"].startswith("b9")]
        self.assertTrue(event)
        action = next(a for a in event[0]["actions"] if a["type"] == "hydrology")
        self.assertLess(action["to"], 0.9)

    def test_an_empty_basin_fills(self):
        beats = self.beats_for(0.1, 1.0, next_level=0.55)
        event = [b for b in beats if b["id"].startswith("b9")]
        self.assertTrue(event)
        action = next(a for a in event[0]["actions"] if a["type"] == "hydrology")
        self.assertGreater(action["to"], 0.1)

    def test_the_event_is_telegraphed_before_it_happens(self):
        beats = self.beats_for(0.9, 1.0, next_level=0.45)
        warning = next(b for b in beats if b["id"].startswith("b8"))
        event = next(b for b in beats if b["id"].startswith("b9"))
        self.assertLess(warning["trigger"]["seconds"], event["trigger"]["seconds"])
        self.assertIn("bark", [a["type"] for a in warning["actions"]])

    def test_a_half_full_basin_is_left_alone(self):
        """Left alone because the waterline is not actually going anywhere
        this mission -- not because of where it currently sits."""
        self.assertFalse([b for b in self.beats_for(0.5, 1.0, next_level=0.5)
                          if b["id"].startswith("b9")])


if __name__ == "__main__":
    unittest.main()


class LandingZoneTests(unittest.TestCase):
    """Deploy and extraction must be dry at THIS mission's waterline."""

    def zone(self, zone_id, floods_at, resting, camp=True):
        return {"zoneId": zone_id, "campEligible": camp,
                "hydrology": {"floodsAt": floods_at, "restingSubmerged": resting}}

    def test_a_zone_that_floods_below_the_current_level_is_not_landable(self):
        wet = self.zone("WET", 0.5, 0.1)
        self.assertFalse(engine.zone_is_landable(wet, 0.72))
        self.assertTrue(engine.zone_is_landable(wet, 0.3))

    def test_a_zone_wet_at_rest_is_never_landable(self):
        marsh = self.zone("MARSH", 2.0, 0.6)
        self.assertFalse(engine.zone_is_landable(marsh, 0.0))

    def test_camp_ineligible_ground_is_never_landable(self):
        cliff = self.zone("CLIFF", 2.0, 0.0, camp=False)
        self.assertFalse(engine.zone_is_landable(cliff, 0.0))

    def test_dry_ground_is_landable_at_any_level(self):
        dry = self.zone("DRY", 2.0, 0.05)
        for level in (0.0, 0.5, 1.0):
            self.assertTrue(engine.zone_is_landable(dry, level))

    def test_the_live_mission_does_not_land_in_water(self):
        intent_path = WS / "outbox" / "next_mission_intent.json"
        if not intent_path.exists():
            self.skipTest("no materialized intent")
        intent = json.loads(intent_path.read_text(encoding="utf-8-sig"))
        level = float((intent.get("hydrology") or {}).get("level") or 0.0)
        zone_map = engine.load_zone_map(str(intent.get("mapId") or ""), WS)
        zones = {str(z.get("zoneId")): z for z in (zone_map.get("zones") or [])}
        if not zones:
            self.skipTest("no zone map for the live mission")
        for key in ("deploymentZoneId", "extractionZoneId"):
            zone_id = intent.get(key)
            self.assertIn(zone_id, zones, f"{key} names a zone that does not exist")
            self.assertTrue(engine.zone_is_landable(zones[zone_id], level),
                            f"{key} {zone_id} is underwater at level {level}")
