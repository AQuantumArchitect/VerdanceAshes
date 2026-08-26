"""Tests for living-shell character membrane (campaign-compatible)."""
from __future__ import annotations

import unittest
from pathlib import Path

from quantum_bar_ai.shell_character_membrane import (
    MAP_PRIORS,
    SHELL_AXES,
    ShellCharacter,
    build_seven_map_membrane,
    load_shell_from_workspace,
    shell_solution_geometry,
)

WS = Path(r"C:\Users\Luke Spooner\Documents\BAR_Verdance_Workspace")


class TestShellPriors(unittest.TestCase):
    def test_seven_maps_present(self):
        expected = {
            "greenest_fields",
            "eye_of_horus",
            "koom_valley",
            "tabula",
            "ancient_bastion",
            "the_rock_jungle",
            "all_that_simmers",
        }
        self.assertEqual(set(MAP_PRIORS.keys()), expected)

    def test_greenest_is_eco_heavy(self):
        sc = ShellCharacter.from_prior("greenest_fields")
        e = sc.expect()
        self.assertGreater(e["eco_surface"], e["fortress"])
        self.assertEqual(sc.raid_hint(), "raid_eco_extract")

    def test_bastion_is_siege(self):
        sc = ShellCharacter.from_prior("ancient_bastion")
        self.assertEqual(sc.raid_hint(), "bite_outer_rings")
        self.assertIn("siege", sc.fair_briefing_tags())

    def test_jungle_is_wild(self):
        sc = ShellCharacter.from_prior("the_rock_jungle")
        self.assertEqual(sc.raid_hint(), "survive_pathing")
        self.assertIn("wild", sc.fair_briefing_tags())

    def test_koom_is_lane(self):
        sc = ShellCharacter.from_prior("koom_valley")
        self.assertEqual(sc.raid_hint(), "seize_or_raid_lane")

    def test_grow_profile_tilts_fortress(self):
        sc = ShellCharacter.from_prior("greenest_fields")
        before = sc.expect()["fortress"]
        sc.apply_grow_profile("fortify_hard", weight=1.5)
        self.assertGreater(sc.expect()["fortress"], before)
        self.assertIn("fortify_hard", sc.grow_profiles)


@unittest.skipUnless(WS.is_dir(), "workspace missing")
class TestShellWorkspace(unittest.TestCase):
    def test_load_greenest_has_units(self):
        sc = load_shell_from_workspace(WS, "greenest_fields")
        self.assertGreater(sc.unit_count, 100)
        self.assertGreater(sc.pockets, 3)
        self.assertTrue(any(p.startswith("sprawl") or p == "sprawl" for p in sc.grow_profiles) or "sprawl" in sc.grow_profiles)

    def test_character_spread(self):
        pack = build_seven_map_membrane(WS)
        counts = {m: pack["maps"][m]["unit_count"] for m in pack["maps"]}
        # Jungle sparse, bastion/tabula/greenest dense (rate character).
        self.assertLess(counts["the_rock_jungle"], 40)
        self.assertGreater(counts["ancient_bastion"], counts["the_rock_jungle"] * 5)
        self.assertGreater(counts["greenest_fields"], 200)

    def test_solution_geometry_has_extract(self):
        sc = load_shell_from_workspace(WS, "eye_of_horus")
        geo = shell_solution_geometry(sc)
        self.assertIn("EXTRACT", geo["viable_vectors"])
        self.assertTrue(geo["win_predicates"])
        self.assertEqual(len(SHELL_AXES), 8)


if __name__ == "__main__":
    unittest.main()
