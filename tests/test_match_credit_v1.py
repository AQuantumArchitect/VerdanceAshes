"""Credit table + normalize law tests (Campaign ↔ BAR protocol)."""
from __future__ import annotations

import copy
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "tools"
sys.path.insert(0, str(TOOLS))

from verdance.belief import match_credit as mc
from verdance.hub.contract import normalize_result


def _base(**kwargs):
    r = {
        "campaignId": "verdance_ashes",
        "missionId": "va_003",
        "missionNumber": 3,
        "chapterIndex": 1,
        "mapId": "greenest_fields",
        "targetZoneId": "GF_SE_STAGING",
        "frame": 9000,
        "freeTnbMint": True,  # raw may lie — normalize must force false
    }
    r.update(kwargs)
    return r


class TestCreditTable(unittest.TestCase):
    def test_victory_claim_flips(self):
        r = _base(
            status="victory",
            terminalReason="extracted",
            nodeClaimed=True,
            pocketCleared=True,
            captureMode="clear_hold_shell",
            objectiveComplete=True,
            extractionStatus="clean",
            cleanExtract=True,
        )
        c = mc.credit_from_result(r)
        self.assertEqual(c["verdict"], "victory")
        self.assertTrue(c["zoneFlip"])
        self.assertEqual(c["xpTier"], "full")
        self.assertTrue(c["advanceMission"])
        self.assertFalse(c["freeTnbMint"])
        self.assertIn("ch1", c["resultKey"])

    def test_victory_no_claim_no_capture_flip(self):
        r = _base(
            status="victory",
            terminalReason="extracted",
            nodeClaimed=False,
            captureMode="clear_hold_shell",
            objectiveComplete=True,
            extractionStatus="clean",
        )
        c = mc.credit_from_result(r)
        self.assertEqual(c["verdict"], "victory")
        self.assertFalse(c["zoneFlip"])
        self.assertEqual(c["xpTier"], "full")

    def test_partial_no_extract_no_flip(self):
        r = _base(
            status="partial",
            terminalReason="soft_clock_no_extract",
            objectiveComplete=True,
            nodeClaimed=False,
            captureMode="clear_hold_shell",
        )
        c = mc.credit_from_result(r)
        self.assertEqual(c["verdict"], "partial")
        self.assertFalse(c["zoneFlip"])
        self.assertEqual(c["xpTier"], "partial")
        self.assertTrue(c["advanceMission"])
        self.assertFalse(c["fullSuccess"])
        self.assertTrue(c["anyPositive"])

    def test_partial_with_claim_can_flip(self):
        r = _base(
            status="partial",
            terminalReason="soft_clock_no_extract",
            nodeClaimed=True,
            captureMode="clear_hold_shell",
            pocketCleared=True,
        )
        c = mc.credit_from_result(r)
        self.assertEqual(c["verdict"], "partial")
        self.assertTrue(c["zoneFlip"])

    def test_defeat_wipe(self):
        r = _base(status="defeat", terminalReason="player_wiped")
        c = mc.credit_from_result(r)
        self.assertEqual(c["verdict"], "defeat")
        self.assertFalse(c["zoneFlip"])
        self.assertEqual(c["xpTier"], "loss")
        self.assertTrue(c["advanceMission"])

    def test_gameover_external(self):
        r = _base(status="partial", terminalReason="gameover_external")
        c = mc.credit_from_result(r)
        self.assertEqual(c["verdict"], "partial")

    def test_abandon_no_advance(self):
        r = _base(status="abandon", terminalReason="player_abandon")
        c = mc.credit_from_result(r)
        self.assertEqual(c["verdict"], "abandon")
        self.assertFalse(c["advanceMission"])
        self.assertFalse(c["zoneFlip"])
        self.assertEqual(c["xpTier"], "none")

    def test_incomplete_no_apply(self):
        r = _base(status="incomplete", terminalReason="extract_failed")
        c = mc.credit_from_result(r)
        self.assertEqual(c["verdict"], "incomplete")
        self.assertFalse(c["applyState"])
        self.assertFalse(c["advanceMission"])

    def test_partial_not_full_success(self):
        """Regression: partial must never look like full victory success soup."""
        r = _base(
            status="partial",
            destroyedObjectiveIds=["obj1"],
            extractionStatus="clean",
            success=True,  # lying flag
        )
        c = mc.credit_from_result(r)
        self.assertEqual(c["verdict"], "partial")
        self.assertFalse(c["fullSuccess"])

    def test_free_tnb_always_false(self):
        r = _base(status="victory", nodeClaimed=True, freeTnbMint=True)
        c = mc.credit_from_result(r)
        self.assertFalse(c["freeTnbMint"])

    def test_mode_a_chapter_keys_differ(self):
        r1 = _base(chapterIndex=1, frame=1000, status="victory", terminalReason="extracted")
        r2 = _base(chapterIndex=2, frame=5000, status="victory", terminalReason="extracted")
        k1 = mc.credit_from_result(r1)["resultKey"]
        k2 = mc.credit_from_result(r2)["resultKey"]
        self.assertNotEqual(k1, k2)
        self.assertIn("ch1", k1)
        self.assertIn("ch2", k2)

    def test_debrief_duplicate(self):
        c = mc.credit_from_result(_base(status="victory", terminalReason="extracted"))
        d = mc.presentable_debrief(c, duplicate=True)
        self.assertTrue(d["duplicate"])
        self.assertIn("Already", d["headline"])


class TestNormalizeLaw(unittest.TestCase):
    def test_normalize_forces_free_tnb_false(self):
        raw = _base(status="victory", freeTnbMint=True, nodeClaimed=True)
        n = normalize_result(raw)
        self.assertFalse(n["freeTnbMint"])
        self.assertEqual(n["verdict"], "victory")
        self.assertFalse(n["success"] is False and n["verdict"] == "victory")

    def test_normalize_partial_not_success(self):
        raw = _base(status="partial", terminalReason="soft_clock_no_extract")
        n = normalize_result(raw)
        self.assertEqual(n["verdict"], "partial")
        self.assertFalse(n["success"])

    def test_normalize_rescue_fail_partial(self):
        raw = _base(
            status="partial",
            terminalReason="extracted_recruit_lost",
            objectiveFailed=True,
            objectiveFailReason="wreck_destroyed",
            objectiveFailHero="fatboy",
        )
        c = mc.credit_from_result(raw)
        self.assertEqual(c["verdict"], "partial")
        self.assertTrue(c["objectiveFailed"])
        self.assertIn("rescue", c["reasonHint"].lower())
        n = normalize_result(raw)
        self.assertTrue(n["objectiveFailed"])
        self.assertEqual(n["objectiveFailReason"], "wreck_destroyed")
        self.assertEqual(n["objectiveFailHero"], "fatboy")
        self.assertTrue(n["rescueContractFailed"])
        d = mc.presentable_debrief(c)
        self.assertTrue(d["objectiveFailed"])
        self.assertTrue(d.get("reasonHint"))

    def test_normalize_includes_credits(self):
        raw = _base(
            status="victory",
            nodeClaimed=True,
            captureMode="clear_hold_shell",
            objectiveComplete=True,
        )
        n = normalize_result(raw)
        self.assertIsInstance(n.get("credits"), dict)
        self.assertTrue(n["credits"].get("nodeClaimed"))


class TestProcessResultCredit(unittest.TestCase):
    """Integration with process_result when state is minimal."""

    def setUp(self):
        from verdance.campaign import default_v1_state, migrate_state

        self.state = migrate_state(default_v1_state())
        # Ensure zone memory for flip tests
        self.state.setdefault("zoneMemory", {}).setdefault("greenest_fields", {})[
            "GF_SE_STAGING"
        ] = {
            "zoneId": "GF_SE_STAGING",
            "controllingFaction": "armada",
            "abstract": {"control": "armada"},
        }
        self.ws = ROOT

    def test_partial_does_not_flip_capture(self):
        from verdance.campaign import process_result

        state = copy.deepcopy(self.state)
        result = _base(
            status="partial",
            terminalReason="soft_clock_no_extract",
            mapId="greenest_fields",
            deploymentMapId="greenest_fields",
            targetZoneId="GF_SE_STAGING",
            captureMode="clear_hold_shell",
            nodeClaimed=False,
            objectiveComplete=True,
            elapsedMinutes=5,
        )
        state, report, _, _ = process_result(state, result, None, self.ws, None)
        self.assertTrue(report.get("processed"))
        self.assertFalse(report.get("zoneFlipped"))
        self.assertEqual(report.get("verdict"), "partial")
        zm = state["zoneMemory"]["greenest_fields"]["GF_SE_STAGING"]
        self.assertEqual(zm.get("controllingFaction"), "armada")

    def test_victory_claim_flips(self):
        from verdance.campaign import process_result

        state = copy.deepcopy(self.state)
        result = _base(
            status="victory",
            terminalReason="extracted",
            mapId="greenest_fields",
            deploymentMapId="greenest_fields",
            targetZoneId="GF_SE_STAGING",
            captureMode="clear_hold_shell",
            nodeClaimed=True,
            pocketCleared=True,
            capturePhase="claimed",
            objectiveComplete=True,
            extractionStatus="clean",
            elapsedMinutes=8,
        )
        state, report, _, _ = process_result(state, result, None, self.ws, None)
        self.assertTrue(report.get("processed"))
        self.assertTrue(report.get("zoneFlipped") or report.get("nodeClaimed"))
        self.assertFalse(report.get("freeTnbMint", True))

    def test_duplicate_noop(self):
        from verdance.campaign import process_result

        state = copy.deepcopy(self.state)
        result = _base(
            status="victory",
            terminalReason="extracted",
            mapId="greenest_fields",
            deploymentMapId="greenest_fields",
            nodeClaimed=True,
            captureMode="clear_hold_shell",
            capturePhase="claimed",
            elapsedMinutes=3,
        )
        state, r1, _, _ = process_result(state, result, None, self.ws, None)
        self.assertTrue(r1.get("processed"))
        state, r2, _, _ = process_result(state, result, None, self.ws, None)
        self.assertFalse(r2.get("processed"))
        self.assertEqual(r2.get("reason"), "duplicate")

    def test_abandon_no_mission_bump(self):
        from verdance.campaign import process_result

        state = copy.deepcopy(self.state)
        before = int(state.get("missionNumber") or 1)
        result = {
            "status": "abandon",
            "terminalReason": "player_abandon",
            "campaignId": "verdance_ashes",
            "missionId": "va_001",
            "missionNumber": before,
            "chapterIndex": 1,
            "mapId": "greenest_fields",
        }
        state, report, _, _ = process_result(state, result, None, self.ws, None)
        self.assertTrue(report.get("processed"))
        self.assertEqual(report.get("verdict"), "abandon")
        self.assertEqual(int(state.get("missionNumber") or 1), before)
        self.assertFalse(report.get("zoneFlipped"))


if __name__ == "__main__":
    unittest.main()
