"""
Unit test for WO-001: Real zone adjacency graph.
Asserts symmetry, complete coverage, valid ID resolution, and absence of self-loops.
"""
import os
import json
import unittest

AUTHORED_DIR = os.path.join("data", "zone_maps", "authored")
ADJACENCY_PATH = os.path.join(AUTHORED_DIR, "zone_adjacency.json")

EXPECTED_MAPS = [
    "greenest_fields",
    "eye_of_horus",
    "koom_valley",
    "tabula",
    "ancient_bastion",
    "the_rock_jungle",
    "all_that_simmers"
]

class TestZoneAdjacency(unittest.TestCase):

    def setUp(self):
        self.assertTrue(os.path.exists(ADJACENCY_PATH), f"Missing {ADJACENCY_PATH}")
        with open(ADJACENCY_PATH, "r", encoding="utf-8-sig") as f:
            self.graph = json.load(f)

    def test_maps_presence(self):
        for map_key in EXPECTED_MAPS:
            self.assertIn(map_key, self.graph, f"Map {map_key} missing from adjacency graph!")

    def test_all_authored_zones_covered(self):
        for map_key in EXPECTED_MAPS:
            authored_file = os.path.join(AUTHORED_DIR, f"{map_key}.authored.zone_map.json")
            self.assertTrue(os.path.exists(authored_file), f"Missing {authored_file}")
            with open(authored_file, "r", encoding="utf-8-sig") as f:
                authored_data = json.load(f)
            authored_zones = {z["zoneId"] for z in authored_data.get("zones", [])}
            graph_zones = set(self.graph[map_key].keys())
            self.assertEqual(authored_zones, graph_zones, f"Zone mismatch in {map_key}!")

    def test_symmetry_and_valid_neighbors(self):
        for map_key, map_graph in self.graph.items():
            for zone_id, neighbors in map_graph.items():
                self.assertNotIn(zone_id, neighbors, f"Self loop detected in {map_key}:{zone_id}")
                for neighbor_id in neighbors:
                    self.assertIn(neighbor_id, map_graph, f"Unknown neighbor {neighbor_id} in {map_key}:{zone_id}")
                    self.assertIn(
                        zone_id,
                        map_graph[neighbor_id],
                        f"Symmetry broken between {zone_id} and {neighbor_id} in {map_key}!"
                    )

if __name__ == "__main__":
    unittest.main()
