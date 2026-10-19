"""Regression guards for the in-game campaign debrief controls."""
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WIDGET = ROOT / "mod" / "VerdanceAshes.sdd" / "luaui" / "Widgets" / "gui_verdance_objectives.lua"


class DebriefWidgetTests(unittest.TestCase):
    def setUp(self):
        self.source = WIDGET.read_text(encoding="utf-8")

    def test_has_real_click_targets_and_shared_selection_path(self):
        self.assertIn("function widget:MousePress(x, y, button)", self.source)
        self.assertIn("debriefPickRects[i]", self.source)
        self.assertIn("return selectNextMission(i)", self.source)
        self.assertIn(
            "writeNextSortieChoice(nextMissionCandidates[index], index)",
            self.source,
        )


    def test_supports_keyboard_selection_and_confirmation(self):
        self.assertIn("if key == 52 or key == 260 then return 4 end", self.source)
        self.assertIn("key == 13 or key == 271 or key == 32", self.source)
        self.assertIn('Spring.SendLuaRulesMsg("VA_CMD:vacontinue:', self.source)

    def test_shows_extraction_handoff_and_quit_guidance(self):
        self.assertIn('eventStatus == "extraction_complete"', self.source)
        self.assertIn('eventStatus == "campaign_update_complete"', self.source)
        self.assertIn('"UPDATING GAMESTATE..."', self.source)
        # Ash Console handoff copy (BANKED card + compact strip).
        self.assertIn('"GAMESTATE UPDATED"', self.source)
        self.assertIn("Campaign saved. Veteran XP carried. Hub is ready.", self.source)
        self.assertIn("Closing BAR — click LEAVE or press Enter.", self.source)
        self.assertIn("CLICK  ·  LEAVE", self.source)
        self.assertIn("EXIT COMPLETE", self.source)
        self.assertIn("Ash.actionRow", self.source)
        self.assertIn("departureLeaveRect", self.source)
        self.assertIn("confirmLeaveQuit", self.source)
        self.assertIn("armLeaveQuit", self.source)
        # Confirmed leave uses quitforce (native quit dialog was the sticky exit).
        self.assertIn('SendCommands, "quitforce"', self.source)

    def test_marks_extract_candidate_as_exit(self):
        self.assertIn('c.extractOnly == true or c.objectiveArchetype == "extract_leave"', self.source)
        # EXIT is the dedicated leave action that banks and closes BAR.
        self.assertIn('text("EXIT"', self.source)
        self.assertIn("exitCands", self.source)
        # Leave is archetype-addressed so a stale debrief index cannot hit a spent raid.
        self.assertIn('VA_CMD:vacontinue:extract_leave:', self.source)
        self.assertIn("syncCandidatesFromRules", self.source)
        self.assertIn("leaveQuitAt", self.source)
        self.assertIn("VA_UI_LEAVE_QUITFORCE", self.source)
