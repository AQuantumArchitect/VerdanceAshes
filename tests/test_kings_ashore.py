"""The kings' showdown (tools/hud_harness/kings_test.lua): a rival king who starts in the sea walks
inland above the tide still to come. All That Simmers' Southeast Shore seat stands in the water: the
Armada commander started at y -47, and through six 90-minute rehearsals on the container rig no army
but torpedoes could reach it while the other kings fell."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import lua_harness  # noqa: E402


class KingsAshoreTests(unittest.TestCase):
    def test_a_king_in_the_sea_walks_inland_above_the_tide(self):
        self.assertIsNone(lua_harness.run("tools/hud_harness/kings_test.lua"))


if __name__ == "__main__":
    unittest.main()
