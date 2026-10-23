"""Playtest infra: attachments, world tick, kernel sim, power response.

The kernel-sim and strategic-seat classes run whole proxy campaigns through the belief field
(minutes each); they are skipped unless VA_SLOW=1 is set.
"""
from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path

WS = Path(__file__).resolve().parents[1]
TOOLS = WS / "tools"
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

from verdance.company import attachments as att
from verdance.world import world_tick as wt
from verdance import campaign as engine


class AttachmentTests(unittest.TestCase):
    def test_ensure_and_fair_dossier(self):
        state = engine.default_v1_state()
        a = att.ensure_attachments(state)
        self.assertEqual(a["schemaVersion"], att.SCHEMA)
        self.assertIn("vane", a["agents"])
        fair = att.fair_dossier(state)
        self.assertIn("bondBand", fair["agents"]["vane"])
        # no raw bond float required in fair (bands only)
        self.assertNotIn("bond", fair["agents"]["vane"])

    def test_wound_and_rest(self):
        state = engine.default_v1_state()
        att.ensure_attachments(state)
        result = {
            "mapId": "koom_valley",
            "targetZoneId": "KOOM_CENTRAL_FLUID_SCAR",
            "status": "victory",
            "namedOutcomes": [{"charId": "vane", "outcome": "wounded"}],
        }
        d = att.update_attachments_from_result(state, result, success=True)
        self.assertGreaterEqual(state["attachments"]["agents"]["vane"]["wounds"], 1)
        self.assertTrue(d.get("memories"))
        att.apply_rest(state, "vane")
        self.assertEqual(state["attachments"]["agents"]["vane"]["wounds"], 0)

    def test_talk_bond(self):
        state = engine.default_v1_state()
        att.ensure_attachments(state)
        before = state["attachments"]["agents"]["ketha"]["bond"]
        r = att.apply_talk_bond(state, "ketha")
        self.assertTrue(r["ok"])
        self.assertGreater(state["attachments"]["agents"]["ketha"]["bond"], before)


class WorldTickTests(unittest.TestCase):
    def test_power_response_high_tnb(self):
        state = {
            "missionNumber": 5,
            "campaignClockMinutes": 100,
            "commerce": {"tenebrium": 9, "metalK": 4},
            "nodeClaims": {"koom_valley": [{"z": 1}, {"z": 2}, {"z": 3}]},
            "zoneMemory": {},
            "graph": {},
            "reputation": {"nullmercs": 60},
        }
        att.ensure_attachments(state)
        pr = wt.power_response(state)
        self.assertTrue(pr.get("denseTeeth") or pr.get("loanScrutiny"))
        self.assertTrue(pr.get("pushbackEvents"))

    def test_world_tick_moves_q7(self):
        state = engine.default_v1_state()
        engine.ensure_zone_memory(state, WS)
        att.ensure_attachments(state)
        q7_before = float(state["graph"]["q7_resource_scarcity"])
        # force mid scarcity
        state["graph"]["q7_resource_scarcity"] = 0.4
        rep = wt.world_tick(state, hours_offline=3.0, map_id="koom_valley")
        self.assertGreater(state["graph"]["q7_resource_scarcity"], 0.4)
        self.assertIn("power", rep)

    def test_self_test(self):
        r = wt.self_test()
        self.assertIn("pushback", r)
        self.assertGreater(r["strengthComposite"], 0.3)


if __name__ == "__main__":
    unittest.main()
