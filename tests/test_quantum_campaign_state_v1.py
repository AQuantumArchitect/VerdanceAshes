import copy
import unittest
from pathlib import Path

import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import quantum_campaign_state_v1 as quantum


class QuantumCampaignStateTests(unittest.TestCase):
    def test_bootstrap_is_deterministic_and_uses_authored_corridors(self):
        state = {
            "campaignClockMinutes": 12,
            "graph": {"pathSignalA": 0.2, "pathSignalB": 0.6, "pathSignalC": 0.2},
            "zoneMemory": {},
            "offscreenActors": {},
        }
        first = quantum.bootstrap(copy.deepcopy(state), ROOT)
        second = quantum.bootstrap(copy.deepcopy(state), ROOT)
        self.assertEqual(first, second)
        self.assertEqual(quantum.SCHEMA, first["schemaVersion"])
        self.assertGreaterEqual(len(first["zones"]), 100)
        strategic = [edge for edge in first["edges"] if edge["kind"] == "strategic_link"]
        self.assertEqual(7, len(strategic))
        self.assertTrue(all(edge["travelMinutes"] >= 14 for edge in strategic))
        self.assertAlmostEqual(1.0, sum(first["narrative"][key] for key in ("pathA", "pathB", "pathC")))

    def test_host_adopts_valid_lua_snapshot_as_projection_only(self):
        prior = quantum.bootstrap({"zoneMemory": {}, "graph": {}}, ROOT)
        snapshot = copy.deepcopy(prior)
        snapshot["transitionIndex"] = 1
        snapshot["clockMinutes"] = 17.5
        snapshot["stateHash"] = "1a2b3c4d"
        snapshot["transitionJournal"] = [{
            "transitionIndex": 1,
            "requestId": "contract_1",
            "beforeHash": "lua_bootstrap",
            "afterHash": "1a2b3c4d",
        }]
        zone_id = snapshot["zoneOrder"][0]
        snapshot["zones"][zone_id]["mobile"] = 0.42
        state = {"campaignQuantumState": prior, "zoneMemory": {}, "graph": {}}
        result = {"finalQuantumState": snapshot, "deploymentMapId": snapshot["zones"][zone_id]["mapId"]}
        self.assertTrue(quantum.persist_exported(state, result))
        self.assertEqual(1, state["campaignQuantumState"]["transitionIndex"])
        self.assertEqual(17.5, state["campaignClockMinutes"])
        map_id = snapshot["zones"][zone_id]["mapId"]
        self.assertEqual(0.42, state["zoneMemory"][map_id][zone_id]["abstract"]["militaryPressure"])
        self.assertEqual("lua_quantum_kernel", state["lastSpectral"]["source"])

    def test_host_rejects_broken_or_replayed_chain(self):
        previous = quantum.bootstrap({"zoneMemory": {}, "graph": {}}, ROOT)
        previous["transitionIndex"] = 2
        previous["stateHash"] = "prior000"
        state = {"campaignQuantumState": previous, "zoneMemory": {}, "graph": {}}

        broken = copy.deepcopy(previous)
        broken["transitionIndex"] = 3
        broken["stateHash"] = "next0000"
        broken["transitionJournal"] = [{
            "transitionIndex": 3,
            "beforeHash": "wrong000",
            "afterHash": "next0000",
        }]
        self.assertFalse(quantum.persist_exported(state, {"finalQuantumState": broken}))

        replay = copy.deepcopy(previous)
        replay["stateHash"] = "different"
        self.assertFalse(quantum.persist_exported(state, {"finalQuantumState": replay}))


if __name__ == "__main__":
    unittest.main()
