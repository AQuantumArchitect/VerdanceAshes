"""A build refused for want of Tenebrium says so once per builder and unit type every 30 seconds
(tools/hud_harness/tnb_blocked_test.lua): the every-frame line filled a finale's log with 1.6 million
copies on Luke's PC (2026-11-03) until LuaUI ran out of memory and the sortie went unreported."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import lua_harness  # noqa: E402


class TnbBlockedTests(unittest.TestCase):
    def test_a_refused_build_says_so_every_thirty_seconds_not_every_frame(self):
        self.assertIsNone(lua_harness.run("tools/hud_harness/tnb_blocked_test.lua"))


if __name__ == "__main__":
    unittest.main()
