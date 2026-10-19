"""Playtest infra: attachments, world tick, kernel sim, power response."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

WS = Path(__file__).resolve().parents[1]
TOOLS = WS / "tools"
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

import attachments_v1 as att  # noqa: E402
import world_tick_v1 as wt  # noqa: E402
import kernel_campaign_sim_v1 as ksim  # noqa: E402
import verdance_story_engine_v1 as engine  # noqa: E402


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


class KernelSimTests(unittest.TestCase):
    def test_one_sortie_settles(self):
        run = ksim.run_campaign(WS, sorties=2, seed=7, home_map="koom_valley")
        self.assertEqual(len(run["history"]), 2)
        self.assertTrue(all(h.get("processed") is not False for h in run["history"]))
        self.assertEqual(run["end"].get("sessionHomeMap"), "koom_valley")

    def test_multi_seed_divergence_runs(self):
        runs = [
            ksim.run_campaign(WS, sorties=5, seed=s, home_map="koom_valley")
            for s in (1, 2, 3, 4, 5)
        ]
        for r in runs:
            r["fun"] = ksim.fun_score(r)
        div = ksim.divergence_report(runs)
        self.assertEqual(div["seeds"], 5)
        # At least some spread expected
        self.assertGreaterEqual(div["clusterCount"], 1)
        mean_fun = sum(r["fun"]["score"] for r in runs) / 5
        self.assertGreater(mean_fun, 0.15)

    def test_same_seed_deterministic_profiles_path(self):
        a = ksim.run_campaign(WS, sorties=3, seed=99, home_map="koom_valley")
        b = ksim.run_campaign(WS, sorties=3, seed=99, home_map="koom_valley")
        self.assertEqual(
            [h["profile"] for h in a["history"]],
            [h["profile"] for h in b["history"]],
        )


class StrategicSeatImportTests(unittest.TestCase):
    def test_seat_one_seed(self):
        # Load file directly — quantum_bar_ai package __init__ needs umwelt.
        import importlib.util

        path = TOOLS / "quantum_bar_ai" / "strategic_seat.py"
        spec = importlib.util.spec_from_file_location("strategic_seat_mod", path)
        seat = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        spec.loader.exec_module(seat)

        r = seat.run_seat(WS, sorties=4, seed=3, home_map="koom_valley")
        self.assertGreaterEqual(r["deployed"], 3)
        self.assertIn("fun", r)
        self.assertIn("vane", r["attachments"]["agents"])


if __name__ == "__main__":
    unittest.main()
