"""Tests for node-agnostic player-proxy muscle claim law (imported from yurt coral)."""
from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path

MUSCLE_PATH = Path(
    r"C:\Users\Luke Spooner\ws-win\yurt-sync\work\_wargen\coral\player_proxy_muscle.py"
)


def _load_muscle():
    spec = importlib.util.spec_from_file_location("player_proxy_muscle", MUSCLE_PATH)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules["player_proxy_muscle"] = mod
    spec.loader.exec_module(mod)
    return mod


@unittest.skipUnless(MUSCLE_PATH.is_file(), "yurt coral muscle module not present")
class TestPlayerProxyMuscle(unittest.TestCase):
    def setUp(self):
        self.m = _load_muscle()

    def test_human_seal_sacred(self):
        self.assertTrue(self.m.is_human_seal("pkt-bar-playtest-s6-retune"))
        self.assertFalse(self.m.is_human_seal(self.m.PLAYER_PROXY_PACKET_ID))
        self.assertIn("pkt-bar-playtest-s6-retune", self.m.HUMAN_SEAL_PACKET_IDS)

    def test_packet_metadata_agnostic(self):
        meta = self.m.packet_claim_metadata()
        self.assertEqual(meta["kind"], "player_proxy")
        self.assertTrue(meta["muscle_claim_only"])
        self.assertTrue(meta["freeable"])
        self.assertFalse(meta["human_seal"])
        self.assertIn("wargen", meta["execution_nodes"])
        self.assertIn("roc", meta["execution_nodes"])

    def test_orchestration_only_nodes(self):
        self.assertTrue(self.m.is_orchestration_only("oa2it77"))
        self.assertTrue(self.m.is_orchestration_only("potato"))
        self.assertFalse(self.m.is_orchestration_only("wargen"))
        self.assertFalse(self.m.is_orchestration_only("roc"))

    def test_capability_with_injected_probe(self):
        face = self.m.local_capability(
            probe={
                "free": True,
                "reason": "free",
                "cpu_percent": 12.0,
                "mem_percent": 40.0,
                "gpu_util": 0.0,
            }
        )
        self.assertEqual(face["kind"], "player_proxy")
        self.assertIn("can_run_player_proxy", face)
        self.assertIn("node", face)
        # If this host is wargen with workspace, free should pass through
        if face.get("can_run_player_proxy") and not face.get("orchestration_only"):
            self.assertTrue(face.get("free"))

    def test_auction_shape(self):
        # publish with busy probe so we do not require a real free window
        self.m.publish_local(
            probe={"free": False, "reason": "test_busy", "cpu_percent": 90}
        )
        auction = self.m.build_auction()
        self.assertEqual(auction["schema"], "player-proxy-mesh/1.0")
        self.assertEqual(auction["kind"], "player_proxy")
        self.assertIn("muscles", auction)
        self.assertIn("free_nodes", auction)
        self.assertIn(self.m.PLAYER_PROXY_PACKET_ID, auction["player_proxy_packet"])
        self.assertIn("pkt-bar-playtest-s6-retune", auction["human_seals"])


if __name__ == "__main__":
    unittest.main()
