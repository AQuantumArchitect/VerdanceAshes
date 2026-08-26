"""Overnight kernel phase tests: graph, quests, contracts, scars, loans, Mode A."""
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

import contract_v2 as c2  # noqa: E402
import quest_generator_v1 as qg  # noqa: E402
import world_zone_graph as wzg  # noqa: E402
import verdance_story_engine_v1 as engine  # noqa: E402


class KernelPhaseTests(unittest.TestCase):
    def test_quest_generator_same_map(self):
        state = engine.load_json(WS / "state" / "campaign_state.json")
        # Seed holdings so candidates exist
        state.setdefault("zoneMemory", {}).setdefault("koom_valley", {}).setdefault(
            "KOOM_NW_GREEN_SHELF", {}
        )["controllingFaction"] = "nullmercs"
        cands = qg.generate_quests(WS, state, map_id="koom_valley", limit=5)
        self.assertTrue(cands, "expected at least one koom quest")
        for c in cands:
            self.assertEqual(c["mapId"], "koom_valley")
            self.assertEqual(c.get("graphEdgeKind"), "same_map")
            self.assertNotEqual(c["targetZoneId"], "KOOM_NW_GREEN_SHELF")

    def test_contract_v2_roundtrip(self):
        raw = {
            "mapId": "koom_valley",
            "targetZoneId": "KOOM_CENTRAL_FLUID_SCAR",
            "fromZoneIds": ["KOOM_NW_GREEN_SHELF"],
            "patron": "nullmercs",
            "objectiveArchetype": "seize_lane",
        }
        s2 = c2.normalize_sortie(raw)
        self.assertEqual(s2["schemaVersion"], c2.SORTIE_V2)
        self.assertEqual(s2["sessionMode"], "same_map")
        v1 = c2.sortie_v2_to_v1_order(s2)
        self.assertEqual(v1["mapId"], "koom_valley")
        r2 = c2.normalize_result({
            "resultKey": "t|1|victory",
            "mapId": "koom_valley",
            "status": "victory",
            "tenebriumBank": 3,
            "tenebriumLooted": 1,
            "loanUnitHp": {"corthud": {"count": 6, "avgHpFrac": 0.7, "minHpFrac": 0.4}},
            "shellScars": [{"zoneId": "KOOM_CENTRAL_FLUID_SCAR", "destroyed": True}],
        })
        self.assertEqual(r2["tenebrium"]["bank"], 3)
        flat = c2.result_v2_to_v1_fields(r2)
        self.assertEqual(flat["tenebriumBank"], 3)

    def test_shell_scars_and_faction_banks(self):
        state = engine.default_v1_state()
        engine.ensure_commerce(state, WS)
        result = {
            "resultKey": "scar-test-1",
            "mapId": "koom_valley",
            "status": "victory",
            "shellScars": [
                {"zoneId": "KOOM_CENTRAL_FLUID_SCAR", "unitDefName": "armwin", "destroyed": True, "damageFrac": 1.0}
            ],
            "tenebriumBank": 2,
            "playerSurvivors": {},
        }
        engine.ensure_zone_memory(state, WS)
        out = engine.apply_shell_scars(state, result, "koom_valley")
        self.assertEqual(out["applied"], 1)
        self.assertIn("koom_valley", state["shellScars"])
        banks = engine.ensure_faction_banks(state)
        self.assertEqual(banks["armada"], 0)

    def test_loan_quality_miss(self):
        state = engine.default_v1_state()
        commerce = engine.ensure_commerce(state, WS)
        commerce["owned"]["punch_of_thugs"] = {
            "loan": True,
            "loanCount": 6,
            "unitDef": "corthud",
            "healthFrac": 0.4,
        }
        commerce["credits"] = 50
        commerce["tenebrium"] = 0
        result = {
            "resultKey": "loan-q-1",
            "status": "victory",
            "playerSurvivors": {"corthud": 6},
            "loanUnitHp": {"corthud": {"count": 6, "avgHpFrac": 0.35, "minHpFrac": 0.2}},
            "tenebriumBank": 0,
        }
        settle = engine.settle_commerce_after_sortie(state, result, True, True, False, WS)
        note_blob = " ".join(settle.get("notes") or [])
        self.assertTrue(
            "quality miss" in note_blob or "breach" in note_blob or "better shape" in note_blob
        )
        # 0.35 avg is NOT better than 0.4+0.08 → quality miss
        self.assertIn("quality miss", note_blob)

    def test_loan_quality_ok(self):
        state = engine.default_v1_state()
        commerce = engine.ensure_commerce(state, WS)
        commerce["owned"]["punch_of_thugs"] = {
            "loan": True,
            "loanCount": 6,
            "unitDef": "corthud",
            "healthFrac": 0.4,
        }
        commerce["credits"] = 50
        result = {
            "resultKey": "loan-q-2",
            "status": "victory",
            "playerSurvivors": {"corthud": 6},
            "loanUnitHp": {"corthud": {"count": 6, "avgHpFrac": 0.75, "minHpFrac": 0.5}},
            "tenebriumBank": 1,
        }
        settle = engine.settle_commerce_after_sortie(state, result, True, True, False, WS)
        note_blob = " ".join(settle.get("notes") or [])
        self.assertIn("better shape", note_blob)

    def test_mode_a_materialize_stays_same_map(self):
        state = engine.load_json(WS / "state" / "campaign_state.json")
        engine.ensure_zone_memory(state, WS)
        # Force a home map footprint (engine prefers sessionHomeMap + choice over order)
        (WS / "outbox").mkdir(exist_ok=True)
        state["sessionHomeMap"] = "koom_valley"
        state["sessionMode"] = "same_map"
        order = {
            "schemaVersion": "verdance-sortie-order/1.0",
            "mapId": "koom_valley",
            "targetZoneId": "KOOM_CENTRAL_FLUID_SCAR",
            "fromZoneIds": ["KOOM_NW_GREEN_SHELF"],
            "patron": "nullmercs",
            "objectiveArchetype": "seize_lane",
            "valid": True,
            "sessionMode": "same_map",
            "source": "mode_a_quest",
        }
        # seed holding
        state.setdefault("zoneMemory", {}).setdefault("koom_valley", {}).setdefault(
            "KOOM_NW_GREEN_SHELF", {}
        )["controllingFaction"] = "nullmercs"
        # load_sortie_order prefers next_sortie_choice — write both so stale hub stamps lose
        engine.save_json(WS / "outbox" / "next_sortie_order.json", order)
        engine.save_json(WS / "outbox" / "next_sortie_choice.json", order)
        intent = engine.materialize_next_intent(state, WS)
        self.assertEqual(intent.get("mapId"), "koom_valley")
        self.assertEqual(intent.get("sessionMode"), "same_map")
        self.assertEqual(intent.get("occupationModel"), "living_shell")
        self.assertIn("factionBanks", intent)

    def test_process_result_scars_and_duplicate(self):
        state = engine.default_v1_state()
        engine.ensure_zone_memory(state, WS)
        state["missionNumber"] = 1
        state["currentMissionId"] = "va_test"
        result = {
            "schemaVersion": "0.6",
            "campaignId": "verdance_ashes",
            "missionId": "va_test",
            "missionNumber": 1,
            "resultKey": "overnight-process-1",
            "mapId": "koom_valley",
            "deploymentMapId": "koom_valley",
            "status": "victory",
            "targetZoneId": "KOOM_CENTRAL_FLUID_SCAR",
            "patron": "nullmercs",
            "tenebriumBank": 2,
            "tenebriumLooted": 1,
            "shellScars": [{"zoneId": "KOOM_CENTRAL_FLUID_SCAR", "destroyed": True, "unitDefName": "armsolar"}],
            "playerSurvivors": {"corthud": 4},
            "extractionStatus": "clean",
        }
        with tempfile.TemporaryDirectory() as td:
            tw = Path(td)
            # minimal workspace stubs
            (tw / "outbox").mkdir()
            (tw / "state").mkdir()
            (tw / "data" / "zone_maps" / "authored").mkdir(parents=True)
            # copy graph
            import shutil
            gsrc = WS / "data" / "zone_maps" / "world_zone_graph.v1.json"
            gdst = tw / "data" / "zone_maps" / "world_zone_graph.v1.json"
            gdst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy(gsrc, gdst)
            shutil.copytree(WS / "data" / "zone_maps" / "authored", tw / "data" / "zone_maps" / "authored", dirs_exist_ok=True)
            if (WS / "data" / "commerce").exists():
                shutil.copytree(WS / "data" / "commerce", tw / "data" / "commerce", dirs_exist_ok=True)
            if (WS / "data" / "map_pool").exists():
                shutil.copytree(WS / "data" / "map_pool", tw / "data" / "map_pool", dirs_exist_ok=True)
            state2, bead, intent, events = engine.process_result(state, result, None, tw)
            self.assertTrue(bead.get("processed", True) or bead.get("processed") is not False)
            self.assertIn("koom_valley", state2.get("shellScars") or {})
            # duplicate
            state3, bead2, _, _ = engine.process_result(state2, result, None, tw)
            self.assertEqual(bead2.get("reason"), "duplicate")


if __name__ == "__main__":
    unittest.main()
