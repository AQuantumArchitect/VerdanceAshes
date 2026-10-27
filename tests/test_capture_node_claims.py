"""Phase D: capture = clear living-shell pocket + hold under regrow; no free Tnb."""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

WS = Path(__file__).resolve().parents[1]
TOOLS = WS / "tools"
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

from verdance.company import capture_node_claims as cnc
from verdance.hub import contract as c2
from verdance.company import quest_generator as qg
from verdance import campaign as engine


class CaptureNodeClaimsTests(unittest.TestCase):
    def test_module_self_test(self):
        self.assertEqual(cnc._self_test(), 0)

    def test_pocket_clear_fraction(self):
        self.assertFalse(cnc.pocket_cleared(5, 10))
        self.assertTrue(cnc.pocket_cleared(6, 10))
        self.assertTrue(cnc.pocket_cleared(0, 0))

    def test_phase_machine(self):
        self.assertEqual(cnc.capture_phase(destroyed=2, total=10, hold_frames=0), "clear")
        self.assertEqual(cnc.capture_phase(destroyed=6, total=10, hold_frames=100), "hold")
        self.assertEqual(cnc.capture_phase(destroyed=6, total=10, hold_frames=900), "claimed")

    def test_claim_never_mints_tnb(self):
        r = cnc.node_claim_result(
            destroyed=8,
            total=10,
            hold_frames=900,
            patron="nullmercs",
            target_zone_id="KOOM_CENTRAL_FLUID_SCAR",
            map_id="koom_valley",
        )
        self.assertTrue(r["nodeClaimed"])
        self.assertFalse(r["freeTnbMint"])
        self.assertEqual(r["tenebriumFromClaim"], 0)
        self.assertEqual(r["captureMode"], "clear_hold_shell")

    def test_abstract_regrow_heals_scars(self):
        st = {
            "shellScars": {
                "koom_valley": {
                    "byZone": {
                        "KOOM_CENTRAL_FLUID_SCAR": {"destroyedCount": 20, "damageSum": 20.0}
                    },
                    "units": [{"zoneId": "KOOM_CENTRAL_FLUID_SCAR"}] * 30,
                }
            },
            "zoneMemory": {
                "koom_valley": {
                    "KOOM_CENTRAL_FLUID_SCAR": {
                        "abstract": {"shellScar": 0.9, "control": "armada"}
                    }
                }
            },
        }
        out = cnc.apply_abstract_regrow(st, "koom_valley", 180.0)  # 3h
        self.assertGreaterEqual(out["regrown"], 1)
        dmg = st["shellScars"]["koom_valley"]["byZone"]["KOOM_CENTRAL_FLUID_SCAR"]["damageSum"]
        self.assertLess(dmg, 20.0)

    def test_hub_capture_contracts(self):
        state = engine.load_json(WS / "state" / "campaign_state.json")
        state.setdefault("zoneMemory", {}).setdefault("koom_valley", {}).setdefault(
            "KOOM_NW_GREEN_SHELF", {}
        )["controllingFaction"] = "nullmercs"
        contracts = cnc.hub_capture_contracts(WS, state, map_id="koom_valley", limit=4)
        self.assertTrue(contracts, "expected hub capture contracts on koom")
        for c in contracts:
            self.assertEqual(c.get("freeTnbMint"), False)
            self.assertIn(
                c.get("captureMode"),
                ("clear_hold_shell", "raid_scar", "other", cnc.CAPTURE_MODE),
            )

    def test_apply_node_claim_requires_clear_hold(self):
        state = {
            "zoneMemory": {
                "koom_valley": {
                    "KOOM_CENTRAL_FLUID_SCAR": {
                        "controllingFaction": "armada",
                        "abstract": {"control": "armada"},
                    }
                }
            }
        }
        incomplete = {
            "mapId": "koom_valley",
            "targetZoneId": "KOOM_CENTRAL_FLUID_SCAR",
            "status": "victory",
            "captureMode": "clear_hold_shell",
            "capturePhase": "hold",
            "pocketCleared": True,
            "nodeClaimed": False,
            "patron": "nullmercs",
            "freeTnbMint": False,
        }
        rep = cnc.apply_node_claim(state, incomplete, success=True)
        self.assertFalse(rep["claimed"])
        complete = {**incomplete, "nodeClaimed": True, "capturePhase": "claimed"}
        rep2 = cnc.apply_node_claim(state, complete, success=True)
        self.assertTrue(rep2["claimed"])
        self.assertFalse(cnc.free_tnb_mint_allowed(complete))

    def test_quest_generator_stamps_capture_mode(self):
        state = engine.load_json(WS / "state" / "campaign_state.json")
        # The company stands at the northwest muster (a claim, not a zoneMemory truth read).
        cands = qg.generate_quests(WS, state, map_id="koom_valley", from_zone_ids=["KV_NW_MUSTER"], limit=5)
        self.assertTrue(cands)
        seize = [c for c in cands if c.get("objectiveArchetype") in cnc.CAPTURE_KINDS]
        if seize:
            self.assertEqual(seize[0].get("captureMode"), "clear_hold_shell")
            self.assertEqual(seize[0].get("freeTnbMint"), False)

    def test_contract_v2_capture_mode(self):
        s2 = c2.normalize_sortie(
            {
                "mapId": "koom_valley",
                "targetZoneId": "KOOM_CENTRAL_FLUID_SCAR",
                "patron": "nullmercs",
                "objectiveArchetype": "seize_lane",
            }
        )
        self.assertEqual(s2.get("captureMode"), "clear_hold_shell")
        self.assertEqual(s2.get("freeTnbMint"), False)

    def test_process_result_claim_no_free_tnb(self):
        state = engine.default_v1_state()
        engine.ensure_zone_memory(state, WS)
        engine.ensure_commerce(state, WS)
        state["missionNumber"] = 1
        state["currentMissionId"] = "va_cap"
        state.setdefault("zoneMemory", {}).setdefault("koom_valley", {}).setdefault(
            "KOOM_CENTRAL_FLUID_SCAR",
            {"controllingFaction": "armada", "abstract": {"control": "armada"}},
        )
        state.setdefault("shellScars", {})["koom_valley"] = {
            "byZone": {"KOOM_EAST_RIDGE_POCKET": {"destroyedCount": 8, "damageSum": 8.0}},
            "units": [],
        }
        tnb_before = int((state.get("commerce") or {}).get("tenebrium") or 0)
        result = {
            "schemaVersion": "0.6",
            "campaignId": "verdance_ashes",
            "missionId": "va_cap",
            "missionNumber": 1,
            "resultKey": "capture-claim-1",
            "mapId": "koom_valley",
            "deploymentMapId": "koom_valley",
            "status": "victory",
            "targetZoneId": "KOOM_CENTRAL_FLUID_SCAR",
            "patron": "nullmercs",
            "nodeClaimed": True,
            "pocketCleared": True,
            "capturePhase": "claimed",
            "captureMode": "clear_hold_shell",
            "freeTnbMint": False,
            "tenebriumBank": tnb_before,
            "tenebriumLooted": 0,
            "shellScars": [
                {
                    "zoneId": "KOOM_CENTRAL_FLUID_SCAR",
                    "destroyed": True,
                    "unitDefName": "armllt",
                }
            ],
            "playerSurvivors": {"corthud": 4},
            "extractionStatus": "clean",
            "elapsedMinutes": 8,
        }
        with tempfile.TemporaryDirectory() as td:
            tw = Path(td)
            (tw / "outbox").mkdir()
            (tw / "state").mkdir()
            import shutil

            for rel in (
                "data/zone_maps/world_zone_graph.v1.json",
                "data/zone_maps/authored",
                "data/commerce",
                "data/map_pool",
            ):
                src = WS / rel
                dst = tw / rel
                if src.is_dir():
                    shutil.copytree(src, dst, dirs_exist_ok=True)
                elif src.is_file():
                    dst.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy(src, dst)
            state2, report, intent, events = engine.process_result(state, result, None, tw)
            self.assertTrue(report.get("zoneFlipped") or report.get("nodeClaimed"))
            self.assertEqual(report.get("freeTnbMint"), False)
            zm = state2["zoneMemory"]["koom_valley"]["KOOM_CENTRAL_FLUID_SCAR"]
            self.assertEqual(zm.get("controllingFaction"), "nullmercs")
            # claimedNodes ledger from apply_node_claim
            claimed = (state2.get("claimedNodes") or {}).get("koom_valley") or {}
            self.assertIn("KOOM_CENTRAL_FLUID_SCAR", claimed)
            tnb_after = int((state2.get("commerce") or {}).get("tenebrium") or 0)
            # Capture suppresses free mint rolls; bank carry may equal tenebriumBank
            self.assertLessEqual(tnb_after, tnb_before + 0)

    def test_commerce_catalog_no_flip_tnb(self):
        cat = json.loads(
            (WS / "data" / "commerce" / "commerce_catalog.json").read_text(encoding="utf-8")
        )
        # Tenebrium comes only from reclaim: no sortie reward, zone or mission, mints it (2026-10-27).
        rewards = cat.get("sortieRewards") or {}
        self.assertFalse([k for k in rewards if k.lower().startswith("tenebrium")])
        # the stockpile is the income; a win only tops it up
        self.assertLessEqual(int((rewards.get("metalOnVictory") or {}).get("max") or 0), 1)
        self.assertIn("metalOnExtract", rewards)


class PlayerImpactClaimSeedingTests(unittest.TestCase):
    """The other half of the player's regression arc (claims sag during the
    window, press harder once it closes) and PLAYER_IMPACT both land here,
    on the one real claim event -- there is no continuous claim rate live."""

    def test_claim_rate_mult_matches_the_regression_window(self):
        self.assertEqual(cnc.claim_rate_mult(1), 1.0)
        self.assertEqual(cnc.claim_rate_mult(3), 1.0)
        self.assertEqual(cnc.claim_rate_mult(4), 0.5)
        self.assertEqual(cnc.claim_rate_mult(6), 0.5)
        self.assertEqual(cnc.claim_rate_mult(7), 1.25)

    def _claim_state(self, mission_number: int) -> dict:
        return {
            "missionNumber": mission_number,
            "zoneMemory": {
                "koom_valley": {
                    "KOOM_CENTRAL_FLUID_SCAR": {
                        "controllingFaction": "armada",
                        "abstract": {"control": "armada"},
                    }
                }
            },
        }

    def _claim_result(self) -> dict:
        return {
            "mapId": "koom_valley",
            "targetZoneId": "KOOM_CENTRAL_FLUID_SCAR",
            "status": "victory",
            "captureMode": "clear_hold_shell",
            "capturePhase": "claimed",
            "pocketCleared": True,
            "nodeClaimed": True,
            "patron": "nullmercs",
            "freeTnbMint": False,
        }

    def test_a_claim_seeds_the_zones_combat_stats(self):
        state = self._claim_state(1)
        rep = cnc.apply_node_claim(state, self._claim_result(), success=True)
        self.assertTrue(rep["claimed"])
        absr = state["zoneMemory"]["koom_valley"]["KOOM_CENTRAL_FLUID_SCAR"]["abstract"]
        self.assertGreater(absr["baseStrength"], 0.0)
        self.assertGreater(absr["fortification"], 0.0)

    def test_the_seed_never_lowers_an_existing_stronger_zone(self):
        state = self._claim_state(1)
        state["zoneMemory"]["koom_valley"]["KOOM_CENTRAL_FLUID_SCAR"]["abstract"]["baseStrength"] = 9.0
        cnc.apply_node_claim(state, self._claim_result(), success=True)
        absr = state["zoneMemory"]["koom_valley"]["KOOM_CENTRAL_FLUID_SCAR"]["abstract"]
        self.assertEqual(absr["baseStrength"], 9.0)

    def test_the_seed_is_smaller_inside_the_regression_window(self):
        during = self._claim_state(5)
        cnc.apply_node_claim(during, self._claim_result(), success=True)
        after_window = self._claim_state(8)
        cnc.apply_node_claim(after_window, self._claim_result(), success=True)
        during_seed = during["zoneMemory"]["koom_valley"]["KOOM_CENTRAL_FLUID_SCAR"]["abstract"]["baseStrength"]
        after_seed = after_window["zoneMemory"]["koom_valley"]["KOOM_CENTRAL_FLUID_SCAR"]["abstract"]["baseStrength"]
        self.assertLess(during_seed, after_seed)

    def test_player_impact_import_matches_offscreen_clash(self):
        from verdance.world import offscreen_clash as oc
        self.assertEqual(cnc._player_impact(), oc.PLAYER_IMPACT)


if __name__ == "__main__":
    unittest.main()
