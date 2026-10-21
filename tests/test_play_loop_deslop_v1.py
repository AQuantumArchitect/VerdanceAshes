"""Static wiring checks for the play-loop deslop wave: scars and the honest compiler flags.

(The continue/EXIT widget checks went with the debrief widget in pass seven.)"""
from __future__ import annotations

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CAMPAIGN = ROOT / "mod" / "VerdanceAshes.sdd" / "luarules" / "gadgets" / "game_verdance_campaign.lua"
COMPILER = ROOT / "scripts" / "build_next_mission_v1.ps1"
PLAY_SESSION = ROOT / "scripts" / "play_session_v1.ps1"
CONTINUITY = ROOT / "tools" / "verdance" / "company" / "continuity_audit.py"
CREW_WIDGET = ROOT / "mod" / "VerdanceAshes.sdd" / "luaui" / "Widgets" / "gui_verdance_crew_select.lua"
OVERMIND = ROOT / "mod" / "VerdanceAshes.sdd" / "luaui" / "Widgets" / "campaign_overmind_widget.lua"


class PlayLoopDeslopTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.campaign = CAMPAIGN.read_text(encoding="utf-8")
        cls.compiler = COMPILER.read_text(encoding="utf-8")
        cls.play_session = PLAY_SESSION.read_text(encoding="utf-8")
        cls.continuity = CONTINUITY.read_text(encoding="utf-8")

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
        from verdance.company.continuity_audit import scar_suppress_set

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
