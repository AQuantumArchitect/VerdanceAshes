"""Unit tests for WO-003: Sortie contract validator."""
import json
import os
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "tools"))
import validate_sortie_contract as vc

# Minimal adjacency graph for testing
MOCK_ADJ = {
    "eye_of_horus": {
        "EOH_NW_CRATER_CAMP": ["EOH_GLASSED_CENTER", "EOH_WESTERN_DEBRIS_LANE"],
        "EOH_GLASSED_CENTER": ["EOH_NW_CRATER_CAMP", "EOH_WESTERN_DEBRIS_LANE", "EOH_EASTERN_DEBRIS_LANE", "EOH_SOUTHERN_CROSSFIRE_SHELF", "EOH_SE_CORTEX_POCKET"],
        "EOH_WESTERN_DEBRIS_LANE": ["EOH_NW_CRATER_CAMP", "EOH_GLASSED_CENTER", "EOH_SOUTHERN_CROSSFIRE_SHELF"],
        "EOH_EASTERN_DEBRIS_LANE": ["EOH_GLASSED_CENTER", "EOH_SE_CORTEX_POCKET", "EOH_SOUTHERN_CROSSFIRE_SHELF"],
        "EOH_SOUTHERN_CROSSFIRE_SHELF": ["EOH_WESTERN_DEBRIS_LANE", "EOH_GLASSED_CENTER", "EOH_SE_CORTEX_POCKET", "EOH_EASTERN_DEBRIS_LANE"],
        "EOH_SE_CORTEX_POCKET": ["EOH_GLASSED_CENTER", "EOH_EASTERN_DEBRIS_LANE", "EOH_SOUTHERN_CROSSFIRE_SHELF"],
    }
}

MOCK_STATE = {
    "zoneMemory": {
        "eye_of_horus": {
            "EOH_NW_CRATER_CAMP": {"controllingFaction": "ashwalkers"},
            "EOH_GLASSED_CENTER": {"controllingFaction": "neutral"},
            "EOH_WESTERN_DEBRIS_LANE": {"controllingFaction": "nullmercs"},
            "EOH_EASTERN_DEBRIS_LANE": {"controllingFaction": "neutral"},
            "EOH_SOUTHERN_CROSSFIRE_SHELF": {"controllingFaction": "neutral"},
            "EOH_SE_CORTEX_POCKET": {"controllingFaction": "cortex"},
        }
    }
}


class TestSortieContractValidator(unittest.TestCase):

    def test_legal_contract_passes(self):
        """Nullmercs can take the Glassed Center since they hold Western Debris Lane which borders it."""
        sortie = {
            "mapId": "eye_of_horus",
            "targetZoneId": "EOH_GLASSED_CENTER",
            "patron": "nullmercs",
            "fromZoneIds": ["EOH_WESTERN_DEBRIS_LANE"],
        }
        errors = vc.validate_contract(sortie, MOCK_ADJ, MOCK_STATE)
        self.assertEqual(errors, [], f"Expected no errors, got: {errors}")

    def test_invalid_patron_rejected(self):
        sortie = {
            "mapId": "eye_of_horus",
            "targetZoneId": "EOH_GLASSED_CENTER",
            "patron": "wild",
        }
        errors = vc.validate_contract(sortie, MOCK_ADJ, MOCK_STATE)
        self.assertTrue(any("INVALID_PATRON" in e for e in errors))

    def test_zone_already_held_by_patron_rejected(self):
        """Nullmercs trying to take EOH_NW_CRATER_CAMP which is ashwalkers (same bloc)."""
        sortie = {
            "mapId": "eye_of_horus",
            "targetZoneId": "EOH_NW_CRATER_CAMP",
            "patron": "nullmercs",
            "fromZoneIds": ["EOH_WESTERN_DEBRIS_LANE"],
        }
        errors = vc.validate_contract(sortie, MOCK_ADJ, MOCK_STATE)
        self.assertTrue(any("ALREADY_HELD" in e for e in errors))

    def test_non_adjacent_zone_rejected(self):
        """Cortex cannot take EOH_NW_CRATER_CAMP since SE_CORTEX_POCKET doesn't border it."""
        sortie = {
            "mapId": "eye_of_horus",
            "targetZoneId": "EOH_NW_CRATER_CAMP",
            "patron": "cortex",
            "fromZoneIds": ["EOH_SE_CORTEX_POCKET"],
        }
        errors = vc.validate_contract(sortie, MOCK_ADJ, MOCK_STATE)
        self.assertTrue(any("NOT_ADJACENT" in e for e in errors))

    def test_no_target_zone_rejected(self):
        sortie = {"mapId": "eye_of_horus", "patron": "nullmercs"}
        errors = vc.validate_contract(sortie, MOCK_ADJ, MOCK_STATE)
        self.assertTrue(any("NO_TARGET_ZONE" in e for e in errors))

    def test_unknown_map_rejected(self):
        sortie = {"mapId": "nonexistent_map", "targetZoneId": "X", "patron": "armada"}
        errors = vc.validate_contract(sortie, MOCK_ADJ, MOCK_STATE)
        self.assertTrue(any("UNKNOWN_MAP" in e for e in errors))

    def test_terse_packet_parsing(self):
        packet = """VA-SORTIE/1
MAP eye_of_horus
ZONE EOH_SE_CORTEX_POCKET
PATRON nullmercs
AGAINST cortex
OBJ strike_relay
FROM EOH_GLASSED_CENTER,EOH_EASTERN_DEBRIS_LANE
DIFF 3/5 target=10min
XP 480
PATH B
GRAPH q0=.703 q2=.207 q6c=.825 q7=.985"""
        parsed = vc.parse_terse_packet(packet)
        self.assertEqual(parsed["mapId"], "eye_of_horus")
        self.assertEqual(parsed["targetZoneId"], "EOH_SE_CORTEX_POCKET")
        self.assertEqual(parsed["patron"], "nullmercs")
        self.assertIn("EOH_GLASSED_CENTER", parsed["fromZoneIds"])
        self.assertEqual(parsed["contractXp"], 480)
        self.assertEqual(parsed["difficulty"], 3)


if __name__ == "__main__":
    unittest.main()
