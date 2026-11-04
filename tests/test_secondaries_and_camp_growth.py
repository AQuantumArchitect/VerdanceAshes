"""Owner call, 2026-11-04: a sortie has one primary (take the ground) and optional secondaries,
scouting and rescues; whoever stays off the drop is at base, and constructors left there grow
the camp while the company is away."""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import lua_harness  # noqa: E402
from verdance import campaign as engine  # noqa: E402
from verdance.campaign.home import CAMP_GROWTH_PENDING_MAX, CAMP_GROWTH_PER_SORTIE_MAX  # noqa: E402


class ScoutSecondaries(unittest.TestCase):
    def test_the_gadget_arms_and_completes_a_scout_mark(self):
        self.assertIsNone(lua_harness.run("tools/hud_harness/scout_marks_test.lua"))

    def test_the_ladder_resolves_to_optional_scouting(self):
        src = (ROOT / "tools/verdance/campaign/sorties.py").read_text(encoding="utf-8")
        self.assertIn('"kind": "scout"', src)
        self.assertIn('"required": False', src)
        builder = (ROOT / "scripts/build_next_mission_v1.ps1").read_text(encoding="utf-8-sig")
        self.assertIn('if ([string]$sec.kind -eq "scout")', builder, "a scout mark builds no enemy camp")

    def test_scouting_and_rescues_do_not_pay_merc_standing(self):
        src = (ROOT / "tools/verdance/campaign/engine.py").read_text(encoding="utf-8")
        self.assertIn('s.get("kind") not in ("scout", "hero_recover")', src)


class CampGrowth(unittest.TestCase):
    def test_builders_left_home_grow_the_camp_while_away(self):
        st = engine.default_v1_state()
        reserve = {"legck": 3, "legcv": 1, "legbal": 6}
        n = engine.grow_camp_while_away(st, reserve, {"legck": 1}, "tabula")
        self.assertEqual(n, min(CAMP_GROWTH_PER_SORTIE_MAX, 2 * 3), "two constructors and a vehicle stayed home")
        for _ in range(10):
            engine.grow_camp_while_away(st, reserve, {}, "koom_valley")
        self.assertEqual(st["homeCamp"]["growthPending"], CAMP_GROWTH_PENDING_MAX)

    def test_a_rock_jungle_sortie_places_it(self):
        st = engine.default_v1_state()
        engine.grow_camp_while_away(st, {"legck": 2}, {}, "greenest_fields")
        self.assertGreater(st["homeCamp"]["growthPending"], 0)
        engine.grow_camp_while_away(st, {"legck": 2}, {}, "the_rock_jungle")
        self.assertEqual(st["homeCamp"]["growthPending"], 0)

    def test_nobody_home_nothing_grows(self):
        st = engine.default_v1_state()
        self.assertEqual(engine.grow_camp_while_away(st, {"legck": 2}, {"legck": 2}, "tabula"), 0)

    def test_the_gadget_places_it_round_the_pad(self):
        self.assertIsNone(lua_harness.run("tools/hud_harness/camp_growth_test.lua"))

    def test_the_builder_carries_it_onto_a_rock_jungle_sortie(self):
        builder = (ROOT / "scripts/build_next_mission_v1.ps1").read_text(encoding="utf-8-sig")
        self.assertIn('campGrowth = $(if ([string]$intent.mapId -eq "the_rock_jungle"', builder)


if __name__ == "__main__":
    unittest.main()
