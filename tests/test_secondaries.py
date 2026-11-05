"""Owner call, 2026-11-04: a sortie has one primary (take the ground) and optional secondaries,
scouting and rescues."""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import lua_harness  # noqa: E402
from verdance import campaign as engine  # noqa: E402


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


if __name__ == "__main__":
    unittest.main()
