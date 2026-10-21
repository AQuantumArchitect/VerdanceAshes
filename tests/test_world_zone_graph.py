"""Kernel tests: world_zone_graph is the authoritative atlas."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

WS = Path(__file__).resolve().parents[1]
TOOLS = WS / "tools"
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

from verdance.world import zone_graph as wzg


class WorldZoneGraphKernelTests(unittest.TestCase):
    def test_graph_present_and_stats(self):
        stats = wzg.graph_stats(WS)
        self.assertEqual(stats.get("source"), "world_zone_graph")
        self.assertGreaterEqual(stats.get("nodeCount", 0), 40)
        self.assertIn("koom_valley", stats.get("maps") or [])

    def test_same_map_adjacency_koom(self):
        # Asserted on the CONTRACT, not on zone names: a re-cut renames every
        # zone on the map, and a test that hardcodes ids only ever measures how
        # recently someone edited it.
        adj = wzg.load_map_adjacency(WS, "koom_valley", kinds=("same_map",))
        self.assertTrue(adj, "koom_valley has no same-map adjacency")
        for zone_id, neighbours in adj.items():
            self.assertNotIn(zone_id, neighbours, f"{zone_id} is its own neighbour")
            self.assertTrue(neighbours, f"{zone_id} is stranded")
            for other in neighbours:
                self.assertIn(zone_id, adj.get(other, []),
                              f"{zone_id}->{other} is not symmetric")

    def test_contract_candidates_exclude_held(self):
        adj = wzg.load_map_adjacency(WS, "koom_valley", kinds=("same_map",))
        held = [sorted(adj)[0]]
        cands = wzg.same_map_contract_candidates(WS, "koom_valley", held)
        self.assertTrue(cands)
        self.assertNotIn(held[0], cands)

    def test_strategic_links_not_in_same_map_adj(self):
        # strategic_link Greenest->Eye must not appear as same_map neighbor
        adj = wzg.load_map_adjacency(WS, "greenest_fields", kinds=("same_map",))
        for zid, nbrs in adj.items():
            for n in nbrs:
                node = wzg.zone_node(WS, n)
                self.assertIsNotNone(node)
                self.assertEqual(node.get("mapId"), "greenest_fields")

    def test_full_adjacency_seven_maps(self):
        full = wzg.load_full_adjacency(WS, kinds=("same_map",))
        self.assertEqual(len(full), 7)


if __name__ == "__main__":
    unittest.main()
