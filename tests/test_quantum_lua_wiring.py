import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
KERNEL = ROOT / "mod" / "VerdanceAshes.sdd" / "luarules" / "gadgets" / "include" / "va_quantum_campaign.lua"
GADGET = ROOT / "mod" / "VerdanceAshes.sdd" / "luarules" / "gadgets" / "game_verdance_campaign.lua"
DECOY = ROOT / "mod" / "VerdanceAshes.sdd" / "units" / "armdecom_tenebrium.lua"
INSTALLER = ROOT / "scripts" / "install_playable_slice.ps1"
COMPILER = ROOT / "scripts" / "build_next_mission_v1.ps1"


class QuantumLuaWiringTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.kernel = KERNEL.read_text(encoding="utf-8")
        cls.gadget = GADGET.read_text(encoding="utf-8")
        cls.decoy = DECOY.read_text(encoding="utf-8")
        cls.installer = INSTALLER.read_text(encoding="utf-8")
        cls.compiler = COMPILER.read_text(encoding="utf-8")

    def test_kernel_is_spring_independent_and_conserves_transit(self):
        self.assertNotIn("Spring.", self.kernel)
        self.assertIn("a * 131", self.kernel)
        self.assertIn("b * 137", self.kernel)
        self.assertNotIn("16777619", self.kernel)
        self.assertIn('string.format("%05d%05d", a, b)', self.kernel)
        self.assertIn("best.source.mobile = clamp(best.source.mobile - mass)", self.kernel)
        self.assertIn('transit.outcome = "control_changed"', self.kernel)
        self.assertIn("transit.casualtyMass", self.kernel)
        self.assertNotIn("destination.mobile = clamp((destination.mobile or 0) +", self.kernel)

    def test_result_exports_authoritative_snapshot_and_journal(self):
        self.assertIn('"quantumTransitionJournal":', self.gadget)
        self.assertIn('"finalQuantumState":', self.gadget)
        self.assertIn("VAQ.transition", self.gadget)
        self.assertIn("VAQ.processArrivals(frame)", self.gadget)
        headless = re.search(
            r"local function finishHeadlessResult\(outcome\)(.*?)\nend\n\nlocal function startMission",
            self.gadget,
            re.S,
        )
        self.assertIsNotNone(headless)
        self.assertIn("VAQ.transition(terminalReason)", headless.group(1))

    def test_hidden_ingress_has_no_centroid_fallback(self):
        self.assertIn("Spring.GetPositionLosState", self.gadget)
        self.assertIn("Spring.TestMoveOrder", self.gadget)
        self.assertIn('VAQ.kernel:deferArrival', self.gadget)

    def test_survivor_xp_banks_and_reseeds_on_spawn(self):
        self.assertIn("function playerSurvivorXpJson(", self.gadget)
        self.assertIn('"playerSurvivorXp":', self.gadget)
        self.assertIn("va_carry_xp", self.gadget)
        self.assertIn("mission.cadreXp", self.gadget)
        self.assertIn("GG.VA_CraftRefresh", self.gadget)

    def test_headless_switch_actually_autostarts_campaign(self):
        self.assertRegex(
            self.installer,
            r"(?s)elseif \(\$Headless\).*?va_headless_autostart=1;.*?va_headless_fastwin=0;",
        )

    def test_compiler_uses_stable_preplaced_installations(self):
        self.assertIn('installationId = $installationId', self.compiler)
        self.assertIn('pocketId = if ($node.pocketId)', self.compiler)
        self.assertIn('if (-not $Occupation) {', self.compiler)
        self.assertIn('staticAfterInitialization = $true', self.compiler)

    def test_hero_support_modifier_is_applied_at_spawn_and_rez(self):
        self.assertIn("heroBuildPowerMult", self.compiler)
        self.assertIn("applyHeroModifiers(unitID, rec)", self.gadget)
        self.assertIn("applyHeroModifiers(newUnitID, rec)", self.gadget)
        self.assertIn("Spring.SetUnitBuildSpeed", self.gadget)

    def test_greenest_uses_decoy_commanders_and_merc_builder(self):
        self.assertIn('CommanderPolicy = ""', self.compiler)
        self.assertIn('commanderPolicy = if ($commanderPolicy)', self.compiler)
        self.assertIn('unitDefName -match "^(arm|cor|leg)com$"', self.compiler)
        self.assertIn('SimpleAI supplies its own single commander', self.compiler)
        self.assertNotIn('mercRecipe = @((Spec "legcom" 1', self.compiler)

    def test_tenebrium_uses_real_decoy_corpse_and_first_team_claim(self):
        self.assertIn('armdecom = {', self.decoy)
        # Full override (BAR replaces by name). Death = T2 builder boom; wreck
        # uses embedded DEAD/HEAP (metalcost ratios) — never armcom_dead 1250 m.
        self.assertIn('corpse = "DEAD"', self.decoy)
        self.assertIn('explodeas = "mediumexplosiongeneric-builder"', self.decoy)
        self.assertIn('selfdestructas = "mediumExplosionGenericSelfd-builder"', self.decoy)
        self.assertIn('object = "Units/armcom_dead.s3o"', self.decoy)
        self.assertIn('isdecoycommander = true', self.decoy)
        self.assertIn('tenebriumWreckAmount = "1"', self.decoy)
        self.assertNotIn('corpse = "armcom_dead"', self.decoy)
        handlers = (ROOT / "mod" / "VerdanceAshes.sdd" / "luarules" / "gadgets" / "include" / "va_tenebrium_handlers.lua").read_text(encoding="utf-8")
        self.assertIn("local claimant = tonumber(builderTeam)", handlers)
        # Claim gate is split: early rec.claimedByTeam return, then claimant nil check.
        self.assertIn("if not rec or rec.claimedByTeam then return 0 end", handlers)
        self.assertIn("if not claimant then return 0 end", handlers)
        self.assertIn("tenebLoot.addTeamBank(claimant", handlers)
        self.assertIn("tenebLoot.claimEvents = tenebLoot.claimEvents or {}", handlers)
        self.assertIn("tenebLoot.dropOf", handlers)

    def test_tenebrium_result_exposes_salvage_accounting(self):
        for field in (
            '"tenebriumInvested":',
            '"tenebriumLivingStakes":',
            '"tenebriumWrecksCreated":',
            '"tenebriumWrecksClaimed":',
            '"tenebriumWrecksLost":',
            '"tenebriumUnclaimedOnExtraction":',
            '"tenebriumClaimEvents":',
            '"tenebriumTeamBanks":',
            '"tenebriumFactionBanks":',
        ):
            self.assertIn(field, self.gadget)


if __name__ == "__main__":
    unittest.main()
