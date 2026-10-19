"""Static wiring checks for extract / EXFIL / EXIT loop tightenings."""
from __future__ import annotations

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CAMPAIGN = ROOT / "mod" / "VerdanceAshes.sdd" / "luarules" / "gadgets" / "game_verdance_campaign.lua"
OBJECTIVES = ROOT / "mod" / "VerdanceAshes.sdd" / "luaui" / "Widgets" / "gui_verdance_objectives.lua"


class ExtractLoopWiringTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.campaign = CAMPAIGN.read_text(encoding="utf-8")
        cls.ui = OBJECTIVES.read_text(encoding="utf-8")

    def test_board_rally_arms_without_leave_first(self):
        # Board-complete rally must arm immediately — leave-first stranded HOLD at 0.
        self.assertIn("boardRally", self.campaign)
        self.assertIn("VA_EXTRACT_AUTO_EVAC", self.campaign)
        self.assertIn("AUTO_EVAC_FRAMES", self.campaign)
        self.assertNotIn("VA_EXTRACT_REARM leave_first reason=board_after_exfil", self.campaign)

    def test_side_bail_publishes_extract_open(self):
        self.assertIn('"side_bail"', self.campaign)
        self.assertIn("allowBail and not boardResolved and not extractLoop.opened", self.campaign)
        self.assertIn("raid_partial", self.campaign)

    def test_intent_resolver_avoids_rawget(self):
        intent = (ROOT / "mod" / "VerdanceAshes.sdd" / "luarules" / "gadgets"
                  / "include" / "va_intent_resolver.lua").read_text(encoding="utf-8")
        self.assertNotIn("rawget(", intent)
        self.assertIn("function M.setHeroDoctrine(", intent)
        behavior = (ROOT / "mod" / "VerdanceAshes.sdd" / "luarules" / "gadgets"
                    / "game_verdance_unit_behavior.lua").read_text(encoding="utf-8")
        self.assertIn("setHeroDoctrine", behavior)

    def test_hold_need_dual_publish(self):
        self.assertIn('Spring.SetGameRulesParam("va_extraction_hold_need", needHold', self.campaign)
        self.assertIn('Spring.SetGameRulesParam("va_bail_need", needHold', self.campaign)

    def test_no_zone_latches_opened(self):
        # no_zone path must set extractLoop.opened before return
        idx = self.campaign.find('VA_EXTRACT_OPEN reason=" .. reason .. " no_zone"')
        self.assertGreater(idx, 0)
        window = self.campaign[max(0, idx - 900) : idx]
        self.assertIn("extractLoop.opened = true", window)
        self.assertIn("extractLoop.armed = true", window)

    def test_exit_event_arms_short_auto_quit(self):
        self.assertIn("VA_UI_EXTRACT_LEAVE auto_quit_armed", self.ui)
        self.assertIn("LEAVE_AUTO_QUIT_SEC", self.ui)
        self.assertIn("armLeaveQuit", self.ui)
        self.assertIn("confirmLeaveQuit", self.ui)
        self.assertIn("departureLeaveRect", self.ui)
        # Short auto-close after EXIT; Esc cancels. Never the old +1s race.
        idx = self.ui.find('elseif eventStatus == "extract_leave" then')
        self.assertGreater(idx, 0)
        window = self.ui[idx : idx + 900]
        self.assertIn('armLeaveQuit("extract_leave_ack")', window)
        self.assertNotIn("leaveQuitAt = os.clock() + 1.0", window)

    def test_route_includes_bail_armed(self):
        self.assertIn("boardResolved or extractOpen or exfilReq or bailArmed", self.ui)


if __name__ == "__main__":
    unittest.main()
