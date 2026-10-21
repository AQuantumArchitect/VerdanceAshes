"""Offline tests for the zone cartography pipeline.

Covers the whole chain without BAR: the infolog format the gadget emits ->
parser -> rasters -> cartographer -> zone map schema 2.0 -> scorecard, plus the
run planner's placement rules.

The fixture map has known ground truth: two base corners, a ridge across the
middle with a single gap, and a lagoon in the southeast.
"""
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

WS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(WS / "tools"))

import derive_zone_adjacency as adjacency  # noqa: E402
import migrate_zone_ids_v1 as migrate  # noqa: E402
import parse_cartography_log_v1 as parser  # noqa: E402
import plan_cartography_runs_v1 as planner  # noqa: E402
from verdance.company import quest_generator as qg
import zone_cartographer_v1 as carto  # noqa: E402
import zone_scorecard_v1 as scorecard  # noqa: E402

RES = 32
SIZE = 8192


def idx(row, col):
    return row * RES + col


def build_terrain():
    cells = []
    for row in range(RES):
        for col in range(RES):
            water, height, slope, buildable = 0.0, 100.0, 0.05, 1.0
            metal, tank, ship = 0.0, 1.0, 0.0
            if 15 <= row <= 17 and not (14 <= col <= 17):      # ridge with one gap
                height, slope, buildable, tank = 420.0, 0.62, 0.0, 0.0
            if row >= 20 and col >= 20:                        # lagoon
                water, height, buildable, tank, ship = 1.0, -25.0, 0.0, 0.0, 1.0
            if row <= 8 and col <= 8:
                height = 260.0
                metal = 2.2 if (3 <= row <= 6 and 3 <= col <= 6) else 0.4
            if row >= 23 and col <= 8:
                metal = 2.0 if (25 <= row <= 28 and 3 <= col <= 6) else 0.3
            cells.append([height, slope, water, buildable, metal, tank, ship, 0, 0])
    return {
        "schemaVersion": "verdance-terrain-raster/1.0",
        "mapId": "fixture_map",
        "mapName": "Fixture Map 1.0",
        "size": {"x": SIZE, "z": SIZE},
        "grid": {"res": RES, "cellW": SIZE / RES, "cellH": SIZE / RES,
                 "squareSize": 8, "metalSquare": 16},
        "channels": list(carto.CH),
        "cells": cells,
        "metalSpots": [{"x": 1200, "z": 1200, "metal": 1.5}],
        "startPositions": [{"team": "1", "x": 1150, "z": 1150},
                           {"team": "2", "x": 1150, "z": 6800}],
        "startBoxes": [],
        "teams": [{"team": 0, "allyTeam": 0, "side": "armada", "ai": True, "dead": False},
                  {"team": 1, "allyTeam": 1, "side": "cortex", "ai": True, "dead": False}],
        "incompleteRows": [],
    }


def build_raster():
    channels = {ally: {k: {} for k in ("presence", "structure", "loss", "traffic", "defence")}
                for ally in ("0", "1")}

    def bump(ally, key, i, value):
        store = channels[ally][key]
        store[str(i)] = store.get(str(i), 0) + value

    for row in range(2, 8):
        for col in range(2, 8):
            bump("0", "presence", idx(row, col), 3000)
            bump("0", "structure", idx(row, col), 2200)
            bump("0", "defence", idx(row, col), 400)
    for row in range(24, 30):
        for col in range(2, 8):
            bump("1", "presence", idx(row, col), 3000)
            bump("1", "structure", idx(row, col), 2200)
            bump("1", "defence", idx(row, col), 400)
    for row in range(13, 20):
        for col in range(14, 18):
            bump("0", "presence", idx(row, col), 900)
            bump("1", "presence", idx(row, col), 850)
            bump("0", "loss", idx(row, col), 1400)
            bump("1", "loss", idx(row, col), 1500)
            bump("0", "traffic", idx(row, col), 60)
            bump("1", "traffic", idx(row, col), 55)
    for row in range(22, 28):
        for col in range(22, 28):
            bump("1", "presence", idx(row, col), 220)
            bump("1", "traffic", idx(row, col), 25)
    return {
        "schemaVersion": "verdance-behaviour-raster/1.0",
        "mapId": "fixture_map",
        "configId": "mirror_1v1_a",
        "grid": {"res": RES},
        "teams": [{"team": 0, "allyTeam": 0, "side": "armada", "ai": True, "dead": False},
                  {"team": 1, "allyTeam": 1, "side": "cortex", "ai": True, "dead": False}],
        "milestones": [{"frame": 37800, "seconds": 1260.0, "samples": 126,
                        "allies": channels, "contact": {str(idx(16, 16)): 9000}}],
    }


class CartographyLogParserTests(unittest.TestCase):
    """The gadget's infolog format is a contract; this is the other half of it."""

    def make_log(self):
        lines = [
            "[f=0000030] VA_CART_ARMED mapId=fixture_map config=mirror_1v1_a res=4 "
            "sample=300 terrainOnly=false milestones=1800,3600",
            "[f=0000030] VA_CARTO_TEAM team=0 ally=0 side=armada ai=true dead=false",
            "[f=0000030] VA_CARTO_TEAM team=1 ally=1 side=cortex ai=true dead=false",
            "[f=0000030] VA_TERRAIN_MAPNAME Fixture Map 1.0",
            "[f=0000030] VA_TERRAIN_META mapId=fixture_map sx=8192 sz=8192 res=4 "
            "cellW=2048.00 cellH=2048.00 squareSize=8 metalSquare=16",
        ]
        for row in range(4):
            cells = "|".join("100.0,0.05,0,1,0.5,1,0,2,50" for _ in range(4))
            lines.append(f"[f=0000030] VA_TERRAIN_ROW {row} {cells}")
        lines += [
            "[f=0000030] VA_TERRAIN_SPOTS count=1 source=resource_spot_finder",
            "[f=0000030] VA_TERRAIN_SPOT 1024.0 2048.0 1.5000",
            "[f=0000030] VA_TERRAIN_STARTPOS 1 900.0 900.0",
            "[f=0000030] VA_TERRAIN_STARTBOX 0 0.0 0.0 0.2 0.2",
            "[f=0000030] VA_TERRAIN_END rows=4",
            "[f=0001800] VA_CARTO_MILESTONE mapId=fixture_map config=mirror_1v1_a "
            "frame=1800 seconds=60.0 res=4 samples=6",
            "[f=0001800] VA_CARTO_CELLS f=1800 a=0 c=1 3,1200,800,10,4,250;4,900,0,0,7,0",
            "[f=0001800] VA_CARTO_CONTACT f=1800 c=1 3,1500",
            "[f=0001800] VA_CARTO_MILESTONE_END frame=1800",
        ]
        return "\n".join(lines)

    def test_terrain_and_behaviour_round_trip(self):
        parsed = parser.parse_log(self.make_log())
        terrain = parser.build_terrain(parsed)
        self.assertEqual(terrain["mapId"], "fixture_map")
        self.assertEqual(terrain["mapName"], "Fixture Map 1.0")   # spaces survive
        self.assertEqual(len(terrain["cells"]), 16)
        self.assertEqual(len(terrain["cells"][0]), len(carto.CH))
        self.assertEqual(terrain["incompleteRows"], [])
        self.assertEqual(terrain["metalSpots"][0]["metal"], 1.5)
        self.assertEqual(terrain["startPositions"][0]["x"], 900)

        behaviour = parser.build_behaviour(parsed)
        self.assertEqual(behaviour["configId"], "mirror_1v1_a")
        milestone = behaviour["milestones"][0]
        self.assertEqual(milestone["samples"], 6)
        self.assertEqual(milestone["allies"]["0"]["presence"]["3"], 1200)
        self.assertEqual(milestone["allies"]["0"]["defence"]["3"], 250)
        self.assertEqual(milestone["contact"]["3"], 1500)

    def test_missing_rows_are_reported_not_silently_zeroed(self):
        log = "\n".join(line for line in self.make_log().splitlines()
                        if not line.endswith("|100.0,0.05,0,1,0.5,1,0,2,50")
                        or "VA_TERRAIN_ROW 2" not in line)
        terrain = parser.build_terrain(parser.parse_log(log))
        self.assertEqual(terrain["incompleteRows"], [2])


class CartographerTests(unittest.TestCase):
    def setUp(self):
        self.grid = carto.CellGrid(build_terrain(), [build_raster()])
        self.zone_map = carto.build_zone_map(self.grid, min_zones=6, max_zones=12)

    def test_every_cell_owned_exactly_once(self):
        seen = set()
        for zone in self.zone_map["zones"]:
            for start, length in zone["cells"]:
                for i in range(start, start + length):
                    self.assertNotIn(i, seen, "cell claimed by two zones")
                    seen.add(i)
        self.assertEqual(len(seen), RES * RES, "every cell must belong to a zone")

    def test_zone_count_respects_the_cap_and_the_absolute_floor(self):
        # The maximum is hard. The minimum is a target: folding dead ground away
        # is allowed to take a sparse map below it, down to min_zones - 2.
        count = len(self.zone_map["zones"])
        self.assertLessEqual(count, 12)
        self.assertGreaterEqual(count, 4)
        self.assertEqual(self.zone_map["targetZoneRange"], [6, 12])

    def test_roles_are_readable_by_the_quest_generator(self):
        # The Drop 4 lesson: a role the generator cannot read collapses the
        # whole board to the seize_lane default.
        for zone in self.zone_map["zones"]:
            self.assertIn(zone["role"], qg.ROLE_ARCHETYPE,
                          f"{zone['zoneId']} role {zone['role']} is unreadable")

    def test_a_coarser_raster_is_re_indexed_not_piled_into_the_corner(self):
        # Behaviour binned on a different grid than the terrain must be mapped
        # by position. Raw indices from a half-res run would land every cell in
        # the top-left quadrant and invent a base where none was measured.
        half = RES // 2
        blob = {}
        for row in range(half - 4, half):
            for col in range(half - 4, half):
                blob[str(row * half + col)] = 5000.0
        coarse = {
            "schemaVersion": "verdance-behaviour-raster/1.0",
            "mapId": "fixture_map",
            "configId": "coarse",
            "grid": {"res": half},
            "teams": [{"team": 0, "allyTeam": 0, "side": "armada", "ai": True, "dead": False}],
            "milestones": [{"frame": 3600, "seconds": 120.0, "samples": 12,
                            "allies": {"0": {"presence": blob}}, "contact": {}}],
        }
        grid = carto.CellGrid(build_terrain(), [coarse])
        mass = [(i, v) for i, v in enumerate(grid.presence) if v > 0]
        self.assertTrue(mass, "coarse raster contributed nothing")
        rows = [divmod(i, RES)[0] for i, _ in mass]
        cols = [divmod(i, RES)[1] for i, _ in mass]
        # The blob sat in the bottom-right of the coarse grid; it must stay there.
        self.assertGreaterEqual(min(rows), RES // 2, "mass drifted north")
        self.assertGreaterEqual(min(cols), RES // 2, "mass drifted west")
        self.assertAlmostEqual(sum(v for _, v in mass), 16 * 5000.0, places=3)

    def test_path_cost_follows_elmos_not_cell_hops(self):
        # A res x res grid over a 2:1 map has 2:1 cells. An east-west step must
        # cost twice a north-south one, or every derived route bends east.
        terrain = build_terrain()
        terrain["size"] = {"x": 16384, "z": 8192}
        grid = carto.CellGrid(terrain, [])
        east = grid.step_cost(idx(4, 4), idx(4, 5))
        south = grid.step_cost(idx(4, 4), idx(5, 4))
        self.assertAlmostEqual(east / south, 2.0, places=6)
        square = carto.CellGrid(build_terrain(), [])
        self.assertAlmostEqual(square.step_cost(idx(4, 4), idx(4, 5)), 1.0, places=6)
        self.assertAlmostEqual(square.step_cost(idx(4, 4), idx(5, 4)), 1.0, places=6)

    def test_finds_both_starts_and_the_chokepoint(self):
        roles = [z["role"] for z in self.zone_map["zones"]]
        self.assertGreaterEqual(roles.count("start"), 2, "both authored starts should be zones")
        self.assertIn("gate", roles, "the single ridge gap should read as a gate")
        gate = next(z for z in self.zone_map["zones"] if z["role"] == "gate")
        self.assertGreater(gate["evidence"]["choke"], 0.5)
        self.assertGreater(gate["evidence"]["transitDensity"], 1.2)

    def test_water_body_is_not_called_a_land_lane(self):
        water_zones = [z for z in self.zone_map["zones"] if z["evidence"]["water"] >= 0.5]
        self.assertTrue(water_zones, "the lagoon should survive as its own zone")
        for zone in water_zones:
            self.assertEqual(zone["role"], "island_chain")
            self.assertFalse(zone["campEligible"], "no camp can stand on open water")
            self.assertIsNone(zone["anchor"])

    def test_anchors_are_buildable_dry_and_flat(self):
        for zone in self.zone_map["zones"]:
            anchor = zone.get("anchor")
            if not anchor:
                continue
            col = min(RES - 1, int(anchor["x"] * RES))
            row = min(RES - 1, int(anchor["z"] * RES))
            cell = self.grid.cells[row * RES + col]
            self.assertGreater(cell[carto.CH["buildable"]], 0.4, zone["zoneId"])
            self.assertLess(cell[carto.CH["water"]], 0.25, zone["zoneId"])
            self.assertLess(cell[carto.CH["slope"]], 0.30, zone["zoneId"])

    def test_no_dead_zones_survive(self):
        for zone in self.zone_map["zones"]:
            self.assertGreaterEqual(zone["evidence"]["presenceShare"], carto.DEAD_ZONE_SHARE,
                                    f"{zone['zoneId']} is dead ground and should have merged")

    def test_deterministic(self):
        again = carto.build_zone_map(carto.CellGrid(build_terrain(), [build_raster()]),
                                     min_zones=6, max_zones=12)
        self.assertEqual([z["zoneId"] for z in again["zones"]],
                         [z["zoneId"] for z in self.zone_map["zones"]])
        self.assertEqual([z["cells"] for z in again["zones"]],
                         [z["cells"] for z in self.zone_map["zones"]])

    def test_terrain_only_still_produces_zones(self):
        grid = carto.CellGrid(build_terrain(), [])
        zone_map = carto.build_zone_map(grid, min_zones=6, max_zones=12)
        self.assertGreaterEqual(len(zone_map["zones"]), 6)


class ScorecardRasterTests(unittest.TestCase):
    def setUp(self):
        self.terrain = build_terrain()
        self.raster = build_raster()
        grid = carto.CellGrid(self.terrain, [self.raster])
        self.zone_map = carto.build_zone_map(grid, min_zones=6, max_zones=12)

    def test_derived_zones_cover_the_measured_war(self):
        entry = scorecard.score_raster_map("fixture_map", self.zone_map, self.terrain, [self.raster])
        self.assertGreaterEqual(entry["coverage"], scorecard.COVERAGE_PASS)
        self.assertEqual(entry["coverageStatus"], "PASS")
        self.assertEqual(entry["deadZones"], [])

    def test_rect_zones_lose_coverage_and_get_caught(self):
        # A single small rectangle in one corner: most of the war happens outside it.
        rect_map = {
            "mapId": "fixture_map",
            "zones": [{"zoneId": "RECT", "label": "Corner Rect", "role": "lane",
                       "bounds": {"xMin": 0.0, "xMax": 0.2, "zMin": 0.0, "zMax": 0.2}}],
        }
        entry = scorecard.score_raster_map("fixture_map", rect_map, self.terrain, [self.raster])
        self.assertLess(entry["coverage"], scorecard.COVERAGE_PASS)
        self.assertEqual(entry["zones"][0]["anchor"], "unmeasured")

    def test_zone_cells_handles_rle_and_rects(self):
        rle_zone = {"cells": [[0, 3], [10, 2]]}
        self.assertEqual(carto.rle([0, 1, 2, 10, 11]), [[0, 3], [10, 2]])
        self.assertEqual(scorecard.zone_cells(rle_zone, RES), [0, 1, 2, 10, 11])
        rect_zone = {"bounds": {"xMin": 0.0, "xMax": 1.0, "zMin": 0.0, "zMax": 1.0}}
        self.assertEqual(len(scorecard.zone_cells(rect_zone, RES)), RES * RES)


class ScorecardLegacyTests(unittest.TestCase):
    def test_role_claims_are_checked_against_behaviour(self):
        zone_map = {
            "mapId": "fixture_map", "mapName": "Fixture",
            "zones": [
                {"zoneId": "Z_LANE", "label": "Quiet Lane", "role": "lane"},
                {"zoneId": "Z_BASE", "label": "Home", "role": "legion_start"},
                {"zoneId": "Z_DEAD", "label": "Nowhere", "role": "plateau"},
            ],
        }
        agg = {
            "samples": 4, "runs": ["r1"], "frames": [1800], "variants": {"authored_baseline": 4},
            "mapValue": 1000.0, "zonedValue": 1000.0,
            "zoneValue": {"Z_LANE": 500.0, "Z_BASE": 495.0, "Z_DEAD": 1.0},
            "zoneStructure": {"Z_LANE": 0.0, "Z_BASE": 60.0, "Z_DEAD": 0.0},
            "zoneDefensive": {"Z_LANE": 0.0, "Z_BASE": 200.0, "Z_DEAD": 0.0},
            "zoneHazard": {},
            "zoneContestHits": {"Z_LANE": 0, "Z_BASE": 0, "Z_DEAD": 0},
            "zoneActiveHits": {"Z_LANE": 4, "Z_BASE": 4, "Z_DEAD": 1},
            "zoneFirstFrame": {},
        }
        entry = scorecard.score_legacy_map("fixture_map", zone_map, agg)
        rows = {z["zoneId"]: z for z in entry["zones"]}
        self.assertEqual(rows["Z_LANE"]["status"], "FAIL")     # claims a lane, never contested
        self.assertEqual(rows["Z_DEAD"]["status"], "FAIL")     # nothing ever happens there
        self.assertEqual(rows["Z_BASE"]["status"], "PASS")     # a real base
        self.assertIn("Z_DEAD", entry["deadZones"])

    def test_contest_is_conditional_on_the_zone_being_reached(self):
        zone_map = {"mapId": "m", "zones": [{"zoneId": "Z", "label": "Z", "role": "lane"}]}
        agg = {
            "samples": 10, "runs": [], "frames": [], "variants": {},
            "mapValue": 100.0, "zonedValue": 100.0,
            "zoneValue": {"Z": 100.0}, "zoneStructure": {}, "zoneDefensive": {}, "zoneHazard": {},
            "zoneContestHits": {"Z": 2}, "zoneActiveHits": {"Z": 2}, "zoneFirstFrame": {},
        }
        entry = scorecard.score_legacy_map("m", zone_map, agg)
        # Reached twice, contested both times: a real lane that is rarely used,
        # not a lane that is never fought over.
        self.assertEqual(entry["zones"][0]["contested"], 1.0)
        self.assertEqual(entry["zones"][0]["activeFraction"], 0.2)


class RunPlannerTests(unittest.TestCase):
    def test_placements_use_authored_starts_when_available(self):
        terrain = planner.MapTerrain("fixture_map", build_terrain())
        self.assertTrue(terrain.has_raster)
        spread = planner.resolve_placement(terrain, "spread", 2)
        self.assertEqual(len(spread), 2)
        self.assertGreater(planner.dist(spread[0], spread[1]), 4000)

    def test_corner_placement_spreads_across_quadrants(self):
        terrain = planner.MapTerrain("fixture_map", build_terrain())
        picks = planner.resolve_placement(terrain, "derived_corners", 4)
        self.assertEqual(len(picks), 4)
        quadrants = {(p[0] > SIZE / 2, p[1] > SIZE / 2) for p in picks}
        self.assertEqual(len(quadrants), 4, "one anchor per quadrant")

    def test_placement_falls_back_to_geometry_without_a_raster(self):
        terrain = planner.MapTerrain("greenest_fields", None)
        picks = planner.resolve_placement(terrain, "spread", 3)
        self.assertEqual(len(picks), 3)
        for x, z in picks:
            self.assertTrue(0 <= x <= terrain.size[0] and 0 <= z <= terrain.size[1])

    def test_milestone_frames_end_on_the_run_length(self):
        frames = planner.milestone_frames(8, [1, 2, 3, 5, 8, 13, 21])
        self.assertEqual(frames[-1], 8 * 60 * 30)
        self.assertTrue(all(f <= 8 * 60 * 30 for f in frames))

    def test_plan_is_written_for_every_pool_map(self):
        with tempfile.TemporaryDirectory() as tmp:
            plan = planner.build_plan(WS, [], ["mirror_1v1"])
            self.assertGreater(plan["runCount"], 0)
            for run in plan["runs"]:
                self.assertTrue(run["teams"], run["runId"])
                self.assertEqual(len(run["teams"]), 2)
                self.assertTrue(run["milestoneFrames"])
                for team in run["teams"]:
                    self.assertIn("shortName", team["ai"])
            out = Path(tmp) / "plan.json"
            out.write_text(json.dumps(plan), encoding="utf-8")
            self.assertTrue(out.exists())


class AdjacencyTests(unittest.TestCase):
    def test_cell_contact_beats_rect_proximity(self):
        # Two zones split by an impassable ridge: rectangles say neighbours,
        # cells plus terrain say there is no way across.
        res = 4
        terrain = {"cells": [[100.0, 0.05, 0, 1, 0, 1, 0, 0, 0] for _ in range(res * res)]}
        for col in range(res):                      # row 1 is a sheer cliff
            terrain["cells"][1 * res + col] = [400.0, 0.9, 0, 0, 0, 0, 0, 0, 0]
        zone_map = {
            "mapId": "m", "grid": {"res": res},
            "zones": [
                {"zoneId": "NORTH", "cells": [[0, res]],
                 "bounds": {"xMin": 0, "xMax": 1, "zMin": 0.0, "zMax": 0.25}},
                {"zoneId": "RIDGE", "cells": [[res, res]],
                 "bounds": {"xMin": 0, "xMax": 1, "zMin": 0.25, "zMax": 0.5}},
                {"zoneId": "SOUTH", "cells": [[res * 2, res * 2]],
                 "bounds": {"xMin": 0, "xMax": 1, "zMin": 0.5, "zMax": 1.0}},
            ],
        }
        adj = adjacency.derive_adjacency_for_map(zone_map, terrain)
        # The two halves of the map do not touch through a cliff...
        self.assertNotIn("SOUTH", adj["NORTH"])
        self.assertNotIn("NORTH", adj["SOUTH"])
        # ...so neither half has a real land edge at all, and each is tied to
        # the ridge only by the deliberate no-stranding fallback.
        self.assertEqual(adj["NORTH"], ["RIDGE"])
        self.assertEqual(adj["SOUTH"], ["RIDGE"])
        for zone_id, neighbours in adj.items():
            self.assertTrue(neighbours, f"{zone_id} has no neighbours at all")

        # Without terrain the same cells read as one continuous surface.
        blind = adjacency.derive_adjacency_for_map(zone_map, None)
        self.assertIn("RIDGE", blind["NORTH"])

    def test_legacy_rect_maps_still_work(self):
        zone_map = {"mapId": "m", "zones": [
            {"zoneId": "A", "bounds": {"xMin": 0, "xMax": 0.5, "zMin": 0, "zMax": 0.5}},
            {"zoneId": "B", "bounds": {"xMin": 0.5, "xMax": 1, "zMin": 0, "zMax": 0.5}},
            {"zoneId": "C", "bounds": {"xMin": 0, "xMax": 1, "zMin": 0.9, "zMax": 1.0}},
        ]}
        adj = adjacency.derive_adjacency_for_map(zone_map)
        self.assertIn("B", adj["A"])
        self.assertTrue(adj["C"], "isolated rect zone still gets connected")


class MigrationTests(unittest.TestCase):
    """A re-cut must carry the campaign with it: control, standing orders and
    baked base templates all name zones."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.ws = Path(self.tmp.name)
        res = 4
        self.old_map = {
            "mapId": "m1", "zones": [
                {"zoneId": "OLD_NORTH", "label": "Old North", "role": "lane",
                 "bounds": {"xMin": 0, "xMax": 1, "zMin": 0, "zMax": 0.5}},
                {"zoneId": "OLD_SOUTH", "label": "Old South", "role": "plateau",
                 "bounds": {"xMin": 0, "xMax": 1, "zMin": 0.5, "zMax": 1}},
            ],
        }
        self.new_map = {
            "mapId": "m1", "grid": {"res": res}, "zones": [
                {"zoneId": "M1_N_GATE", "label": "North Gate", "role": "gate",
                 "cells": [[0, res * 2]], "anchor": {"x": 0.4, "z": 0.2},
                 "bounds": {"xMin": 0, "xMax": 1, "zMin": 0, "zMax": 0.5}},
                {"zoneId": "M1_S_MUSTER", "label": "South Muster", "role": "start",
                 "cells": [[res * 2, res * 2]], "anchor": {"x": 0.4, "z": 0.8},
                 "bounds": {"xMin": 0, "xMax": 1, "zMin": 0.5, "zMax": 1}},
            ],
        }

    def tearDown(self):
        self.tmp.cleanup()

    def test_old_zones_map_to_the_new_zone_that_covers_them(self):
        result = migrate.map_zone_ids(self.ws, self.old_map, self.new_map)
        self.assertEqual(result["mapping"], {"OLD_NORTH": "M1_N_GATE", "OLD_SOUTH": "M1_S_MUSTER"})
        self.assertTrue(all(row["share"] > 0.9 for row in result["detail"]))

    def test_zone_memory_is_rebuilt_and_carries_control(self):
        state = {"zoneMemory": {"m1": {
            "OLD_NORTH": {"zoneId": "OLD_NORTH", "controllingFaction": "armada",
                          "abstract": {"control": "armada", "instability": 0.5}},
            "OLD_SOUTH": {"zoneId": "OLD_SOUTH", "controllingFaction": "wild",
                          "abstract": {"control": "wild", "instability": 0.5}},
        }}}
        (self.ws / "state").mkdir(parents=True, exist_ok=True)
        migrate.save_json(self.ws / "state" / "campaign_state.json", state)
        mapping = {"OLD_NORTH": "M1_N_GATE", "OLD_SOUTH": "M1_S_MUSTER"}
        migrate.rebuild_zone_memory(self.ws, {"m1": self.new_map}, mapping, apply=True)

        after = migrate.load_json(self.ws / "state" / "campaign_state.json")
        zones = after["zoneMemory"]["m1"]
        self.assertEqual(set(zones), {"M1_N_GATE", "M1_S_MUSTER"})
        self.assertEqual(zones["M1_N_GATE"]["controllingFaction"], "armada")
        self.assertEqual(zones["M1_S_MUSTER"]["controllingFaction"], "wild")
        self.assertEqual(zones["M1_N_GATE"]["label"], "North Gate")

    def test_standing_orders_are_repointed(self):
        order = {"mapId": "m1", "targetZoneId": "OLD_NORTH", "deploymentZoneId": "OLD_SOUTH",
                 "extractionZoneId": "OLD_SOUTH", "captureZoneIds": ["OLD_NORTH"],
                 "fromZoneIds": ["OLD_SOUTH"]}
        migrate.save_json(self.ws / "outbox" / "next_sortie_order.json", order)
        notes = migrate.remap_orders(self.ws, {"OLD_NORTH": "M1_N_GATE", "OLD_SOUTH": "M1_S_MUSTER"},
                                     apply=True)
        self.assertTrue(notes)
        after = migrate.load_json(self.ws / "outbox" / "next_sortie_order.json")
        self.assertEqual(after["targetZoneId"], "M1_N_GATE")
        self.assertEqual(after["captureZoneIds"], ["M1_N_GATE"])
        self.assertEqual(after["fromZoneIds"], ["M1_S_MUSTER"])

    def test_shell_pockets_are_retagged_from_where_their_units_stand(self):
        terrain = {"size": {"x": 1000, "z": 1000}, "grid": {"res": 4},
                   "cells": [[0] * 9 for _ in range(16)]}
        migrate.save_json(self.ws / "data" / "terrain" / "m1.terrain.json", terrain)
        shell = {"mapId": "m1", "pockets": [
            {"zoneId": "OLD_NORTH", "x": 500, "z": 900, "label": "South scrap"},
        ]}
        migrate.save_json(self.ws / "data" / "base_templates" / "m1" / "living_shell_v1.json", shell)
        migrate.retag_base_templates(self.ws, {"m1": self.new_map},
                                     {"OLD_NORTH": "M1_N_GATE"}, apply=True)
        after = migrate.load_json(self.ws / "data" / "base_templates" / "m1" / "living_shell_v1.json")
        # The pocket sits in the south, so it follows the ground rather than the
        # id mapping of the zone it used to be labelled with.
        self.assertEqual(after["pockets"][0]["zoneId"], "M1_S_MUSTER")


if __name__ == "__main__":
    unittest.main()
