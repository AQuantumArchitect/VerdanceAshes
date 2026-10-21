"""One field-effect stat per hero; scout/factory mentors bank subordinate XP."""
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TAGS = ROOT / "mod" / "VerdanceAshes.sdd" / "luarules" / "gadgets" / "include" / "va_hero_tags.lua"
CAMPAIGN = ROOT / "mod" / "VerdanceAshes.sdd" / "luarules" / "gadgets" / "game_verdance_campaign.lua"
CREW = ROOT / "data" / "story" / "crew_packs.json"


class HeroFieldEffectTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tags = TAGS.read_text(encoding="utf-8")
        cls.campaign = CAMPAIGN.read_text(encoding="utf-8")
        cls.crew = CREW.read_text(encoding="utf-8")

    def test_each_hero_default_is_single_tag(self):
        # HERO_DEFAULTS rows should list exactly one tag (or empty for deprecated).
        block = re.search(r"M\.HERO_DEFAULTS\s*=\s*\{(.*?)\n\}", self.tags, re.S)
        self.assertIsNotNone(block)
        body = block.group(1)
        for m in re.finditer(r"(\w+)\s*=\s*\{([^}]*)\}", body):
            hero, vals = m.group(1), m.group(2)
            quoted = re.findall(r'"([^"]+)"', vals)
            self.assertEqual(
                len(quoted),
                1,
                f"{hero} should have exactly one field-effect tag, got {quoted}",
            )

    def test_hearth_is_energy_field(self):
        self.assertIn('hearth = { "pad_heart" }', self.tags)
        self.assertIn("energy = 1.35", self.tags)
        self.assertIn("function M.applyFusionEnergyAura(", self.tags)
        self.assertIn("VA_HEARTH_FUSION_AURA", self.tags)

    def test_mentor_roster_covers_scouts_and_factories(self):
        for hid in ("spoke", "tick", "noctua", "consul", "twitch"):
            self.assertIn(f"{hid} = true", self.tags)

    def test_campaign_harvests_and_refreshes_field(self):
        self.assertIn("function harvestMentorXp(", self.campaign)
        self.assertIn("function refreshMentorFieldEffect(", self.campaign)
        self.assertIn("pollMentorSubordinateXp(frame)", self.campaign)
        self.assertIn("VA_MENTOR_HARVEST", self.campaign)
        self.assertIn("VA_HERO_FIELD", self.campaign)

    def test_compose_scales_primary_only(self):
        self.assertIn("function M.composeField(", self.tags)
        self.assertIn("tag base × XP scale on primary (+ rare secondaries)", self.tags)
        self.assertIn("function M.applyFieldToUnit(", self.tags)
        self.assertIn("applyVisionMult", self.tags)
        self.assertIn("applyEnergyMult", self.tags)



if __name__ == "__main__":
    unittest.main()
