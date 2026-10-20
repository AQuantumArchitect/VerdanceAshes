"""Static wiring checks for play-loop deslop wave (Mode A/B, EXIT, scars)."""
from __future__ import annotations

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CAMPAIGN = ROOT / "mod" / "VerdanceAshes.sdd" / "luarules" / "gadgets" / "game_verdance_campaign.lua"
OBJECTIVES = ROOT / "mod" / "VerdanceAshes.sdd" / "luaui" / "Widgets" / "gui_verdance_objectives.lua"
COMPILER = ROOT / "scripts" / "build_next_mission_v1.ps1"
PLAY_SESSION = ROOT / "scripts" / "play_session_v1.ps1"
CONTINUITY = ROOT / "tools" / "continuity_audit_v1.py"
CREW_WIDGET = ROOT / "mod" / "VerdanceAshes.sdd" / "luaui" / "Widgets" / "gui_verdance_crew_select.lua"
OVERMIND = ROOT / "mod" / "VerdanceAshes.sdd" / "luaui" / "Widgets" / "campaign_overmind_widget.lua"


class PlayLoopDeslopTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.campaign = CAMPAIGN.read_text(encoding="utf-8")
        cls.ui = OBJECTIVES.read_text(encoding="utf-8")
        cls.compiler = COMPILER.read_text(encoding="utf-8")
        cls.play_session = PLAY_SESSION.read_text(encoding="utf-8")
        cls.continuity = CONTINUITY.read_text(encoding="utf-8")

    def test_spent_stay_filtered_and_refreshed(self):
        self.assertIn("function zoneHasPromotableOccupation(", self.campaign)
        self.assertIn("VA_CONTINUE_REJECT spent_target", self.campaign)
        self.assertIn("candidates_refresh", self.campaign)
        # Still promote-only — no battlefield mutate on stay.
        match_start = self.campaign.find("function applyContinueCandidate(cand, requestId)")
        self.assertGreater(match_start, 0)
        body = self.campaign[match_start : match_start + 4500]
        self.assertNotIn("spawnContinueCamp(", body)

    def test_exit_pinned_in_publish_cap(self):
        self.assertIn("maxStay = (#exits > 0) and 7 or 8", self.campaign)
        self.assertIn('title = "EXIT — bank and close"', self.campaign)
        self.assertIn('va_cand_" .. i .. "_travel"', self.campaign)
        self.assertIn('va_cand_" .. i .. "_session"', self.campaign)

    def test_mode_b_gated_on_session_host(self):
        self.assertIn("VA_MODE_B_SKIP no_session_host", self.campaign)
        self.assertIn("va_session_host", self.campaign)
        self.assertIn("va_session_host=1", self.play_session)
        # UI no longer dual-injects Mode B on Initialize.
        self.assertIn("Do not dual-inject travel rows here", self.ui)
        self.assertIn("return cands or {}", self.ui)
        self.assertIn("Deprecated dual-writer", self.ui)

    def test_exit_copy_not_extract_for_leave(self):
        self.assertIn('text("EXIT"', self.ui)
        self.assertIn("EXIT selected — saving and closing BAR.", self.ui)
        self.assertIn("or EXIT to save and close BAR.", self.ui)
        self.assertIn('text("EXIT COMPLETE"', self.ui)
        # Mid-mission EXFIL stays.
        self.assertIn("EXFIL NOW", self.ui)

    def test_scar_exact_suppress(self):
        self.assertIn("function Get-ScarSuppressSet", self.compiler)
        self.assertIn("-ScarSuppress $scarSuppress", self.compiler)
        self.assertIn("def scar_suppress_set(", self.continuity)
        self.assertIn("$ScarSuppress.ContainsKey", self.compiler)
        self.assertIn('"$defKey|$pocketId"', self.compiler)

    def test_dead_continue_rules_stripped(self):
        self.assertIn("Honest flags only", self.compiler)
        self.assertNotIn("carryHeroes = $true", self.compiler)
        self.assertNotIn("metalCarryFraction = 0.5", self.compiler)
        self.assertIn("promoteOccupationOnContinue = $true", self.compiler)

    def test_dead_widgets_quarantined(self):
        self.assertFalse(CREW_WIDGET.exists(), "crew select must stay out of Widgets/")
        self.assertFalse(OVERMIND.exists(), "overmind must stay out of Widgets/")


class ScarSuppressUnitTests(unittest.TestCase):
    def test_scar_suppress_set_keys(self):
        import sys

        tools = str(ROOT / "tools")
        if tools not in sys.path:
            sys.path.insert(0, tools)
        from continuity_audit_v1 import scar_suppress_set

        state = {
            "shellScars": {
                "greenest_fields": {
                    "units": [
                        {
                            "unitDefName": "armsolar",
                            "pocketId": "pk_a",
                            "zoneId": "GF_NE",
                            "destroyed": True,
                        },
                        {
                            "unitDefName": "armwin",
                            "zoneId": "GF_SW",
                            "destroyed": True,
                        },
                        {
                            "unitDefName": "armfus",
                            "pocketId": "pk_keep",
                            "destroyed": False,
                        },
                    ]
                }
            }
        }
        keys = scar_suppress_set(state, "greenest_fields")
        self.assertIn("armsolar|pk_a", keys)
        self.assertIn("armwin|GF_SW", keys)
        self.assertNotIn("armfus|pk_keep", keys)


if __name__ == "__main__":
    unittest.main()
