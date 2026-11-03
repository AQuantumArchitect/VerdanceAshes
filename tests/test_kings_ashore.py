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



class KingsSeatTests(unittest.TestCase):
    """The kings start on their seats: the builder marks the kings' showdown StartPosType 3 (the
    startscript's StartPosX/Z) and the installer writes it. With StartPosType 1, BAR put each king on
    one of All That Simmers' own start points in random order, a different one on each BAR build."""

    def test_the_builder_and_the_installer_put_the_kings_on_their_seats(self):
        root = Path(__file__).resolve().parents[1]
        builder = (root / "scripts" / "build_next_mission_v1.ps1").read_text(encoding="utf-8-sig")
        installer = (root / "scripts" / "install_playable_slice.ps1").read_text(encoding="utf-8-sig")
        self.assertIn("startPosType = $(if ($isKings) { 3 } else { 1 })", builder)
        self.assertIn("StartPosType=$startPosType;", installer)
        self.assertIn('$variantObject.PSObject.Properties["startPosType"]', installer)

    def test_the_showdowns_raptor_den_harries_without_deciding_the_throne(self):
        """At normal pace the den's T4 broods took the company's commander at 35 minutes (Luke's PC,
        2026-11-03): the showdown's raptors run at veryeasy with a slower queen; every other field
        keeps normal and the stock clock."""
        root = Path(__file__).resolve().parents[1]
        builder = (root / "scripts" / "build_next_mission_v1.ps1").read_text(encoding="utf-8-sig")
        installer = (root / "scripts" / "install_playable_slice.ps1").read_text(encoding="utf-8-sig")
        self.assertIn('raptorDifficulty = $(if ($isKings) { "veryeasy" } else { "normal" })', builder)
        self.assertIn('raptor_difficulty=$raptorDifficulty;', installer)
        self.assertIn('raptor_queentimemult=$raptorQueenTimeMult;', installer)


if __name__ == "__main__":
    unittest.main()
