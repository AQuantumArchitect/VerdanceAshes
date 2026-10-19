import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
KERNEL = ROOT / "mod" / "VerdanceAshes.sdd" / "luarules" / "gadgets" / "include" / "va_quantum_campaign.lua"
GADGET = ROOT / "mod" / "VerdanceAshes.sdd" / "luarules" / "gadgets" / "game_verdance_campaign.lua"
WIDGET = ROOT / "mod" / "VerdanceAshes.sdd" / "luaui" / "Widgets" / "gui_verdance_objectives.lua"
DECOY = ROOT / "mod" / "VerdanceAshes.sdd" / "units" / "armdecom_tenebrium.lua"
INSTALLER = ROOT / "scripts" / "install_playable_slice.ps1"
COMPILER = ROOT / "scripts" / "build_next_mission_v1.ps1"


class QuantumLuaWiringTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.kernel = KERNEL.read_text(encoding="utf-8")
        cls.gadget = GADGET.read_text(encoding="utf-8")
        cls.widget = WIDGET.read_text(encoding="utf-8")
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
        self.assertIn("1200 * 1200", self.gadget)

    def test_stay_path_does_not_mutate_battlefield(self):
        match = re.search(
            r"function applyContinueCandidate\(cand, requestId\)(.*?)\nend\n\nfunction tryContinueByIndex",
            self.gadget,
            re.S,
        )
        self.assertIsNotNone(match)
        body = match.group(1)
        self.assertNotIn("spawnContinueCamp(", body)
        self.assertNotIn("destroyEnemyInRect(", body)
        self.assertNotIn("Spring.CreateUnit", body)
        self.assertIn("promoteOccupationInZone(targetZone, kind, cand.pocketId)", body)
        self.assertNotIn("waves.nextFrame", body)
        # EXIT must resolve by archetype, never fall through to spent_target promote.
        self.assertIn('kind == "extract_leave" or cand.extractOnly == true', body)
        self.assertIn("VA_CONTINUE_EXTRACT_LEAVE", body)

    def test_exit_leave_is_index_safe_and_auto_closes(self):
        self.assertIn("function ensureExitCandidate(", self.gadget)
        self.assertIn("function tryContinueExtractLeave(", self.gadget)
        # Lua patterns have no | — leave must be two separate matches (not one
        # alternation group that Spring treats as a literal pipe string).
        self.assertIn('vacontinue[:%s]+extract_leave[:%s]*', self.gadget)
        self.assertIn('vacontinue[:%s]+exit[:%s]*', self.gadget)
        self.assertNotRegex(
            self.gadget,
            r'cmd:match\(\s*["\']\^vacontinue.{0,40}extract_leave\|exit',
        )
        self.assertIn("VA_LEAVE_QUITFORCE", self.gadget)
        self.assertIn('Spring.SendLuaRulesMsg("VA_CMD:vacontinue:extract_leave:"', self.widget)
        self.assertIn("quitforce", self.widget)
        self.assertIn("VA_UI_LEAVE_QUITFORCE", self.widget)
        # Soft-continue stays cold until soft terminal (prevents hub leave race).
        self.assertIn(
            "-- Soft-continue is armed only at soft terminal.",
            self.gadget,
        )

    def test_survivor_xp_banks_and_reseeds_on_spawn(self):
        self.assertIn("function playerSurvivorXpJson(", self.gadget)
        self.assertIn('"playerSurvivorXp":', self.gadget)
        self.assertIn("va_carry_xp", self.gadget)
        self.assertIn("mission.cadreXp", self.gadget)
        self.assertIn("GG.VA_CraftRefresh", self.gadget)

    def test_every_debrief_choice_requests_synced_ack(self):
        self.assertIn('Spring.SendLuaRulesMsg("VA_CMD:vacontinue:"', self.widget)
        self.assertIn("debriefPending", self.widget)
        self.assertIn("debriefVisible = false", self.widget)
        self.assertIn("debriefVisible = true", self.widget)
        self.assertNotIn("idx and candidateIsSameMap(cand) and", self.widget)

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

    def test_extraction_pauses_and_explains_quantum_update(self):
        # Loader events must NOT pause (deferred crunch needs GameFrame). Soft
        # terminal / campaign_update_complete pause; extract_leave arms quitforce.
        self.assertIn('SendToUnsynced("VERDANCE_MISSION_EVENT", "extraction_complete"', self.gadget)
        self.assertIn('SendToUnsynced("VERDANCE_MISSION_EVENT", "campaign_update_begin"', self.gadget)
        self.assertIn('SendToUnsynced("VERDANCE_MISSION_EVENT", "campaign_update_complete"', self.gadget)
        self.assertIn('or eventStatus == "campaign_update_complete"', self.gadget)
        self.assertIn('eventStatus == "extract_leave"', self.gadget)
        self.assertIn('"extracted"', self.gadget)

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
        self.assertTrue(
            ("EXPLICIT_TNB_COST" in handlers) or ("STRUCTURE_TNB_COST" in handlers)
        )
        # Combat (incl. T3 heavies) is free; only builders / fabs / nanos stake.
        self.assertIn("Combat (including T3 heavies) is free to build and free to rez.", handlers)
        self.assertIn("armshltx = 7", handlers)         # Experimental Foundry
        self.assertIn("STRUCTURE_NO_DROP", handlers)
        self.assertIn("math.ceil(bp / per)", handlers)
        self.assertIn("armmakr = true", handlers)

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
