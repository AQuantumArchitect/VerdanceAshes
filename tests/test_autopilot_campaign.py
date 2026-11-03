"""The AI launch must preserve opponents and consume only its own result log; the autopilot gadget's
orders (tools/hud_harness/autopilot_test.lua) run under liblua5.4 when it is installed."""
import ctypes
import glob
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from autopilot_campaign_v1 import archive_log, finale_state, isolate_bar, patch_startscript, sorties_came_home


class AutopilotTests(unittest.TestCase):
    def test_a_finale_rehearsal_lands_on_its_path(self):
        """--finale A|B|C: the campaign starts at mission 11 with that path leading; B gets a suit."""
        from verdance.campaign import default_v1_state
        from verdance.campaign.acts import finale_plan_for_state
        for path, kind in (("A", "overthrow"), ("B", "sovereignty"), ("C", "spire_jump")):
            st = finale_state(default_v1_state(), path)
            self.assertEqual(st["missionNumber"], 11)
            self.assertEqual(finale_plan_for_state(st)["kind"], kind, path)
            self.assertGreaterEqual(st["commerce"]["tenebrium"], 12, "a walked campaign's bank, not a fresh one's")

    def test_a_capped_rehearsal_passes_when_every_sortie_came_home(self):
        """The stock rehearsal (--stock --sorties 1) on 2026-11-02: one sortie, engine exit 0, result
        applied, watch 'home'. The campaign is not complete after one sortie, and that is not a failure."""
        home = {"watch": "home", "engineExitCode": 0}
        self.assertTrue(sorties_came_home([home], 1))
        self.assertFalse(sorties_came_home([home], 2))                        # stopped early
        self.assertFalse(sorties_came_home([], 1))
        self.assertFalse(sorties_came_home([{"watch": "closed-without-result", "engineExitCode": 3221225477}], 1))
        self.assertFalse(sorties_came_home([dict(home, crashed={"lastVerdanceLine": None})], 1))
        self.assertFalse(sorties_came_home([dict(home, stall="engine wall timeout", killed=True)], 1))

    def test_run_owns_its_mod_and_seeds(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "installed"
            (source / "games" / "BAR.sdd").mkdir(parents=True)
            player_mod = source / "games" / "VerdanceAshes.sdd"
            player_mod.mkdir()
            (player_mod / "seed.lua").write_text("player campaign")
            (source / "engine").mkdir()
            (source / "maps").mkdir()
            bar = isolate_bar(root / "run", source)
            self.assertTrue((bar / "games" / "BAR.sdd").is_dir())
            own_mod = bar / "games" / "VerdanceAshes.sdd"
            self.assertFalse(own_mod.exists())
            own_mod.mkdir()
            (own_mod / "seed.lua").write_text("AI campaign")
            self.assertEqual((player_mod / "seed.lua").read_text(), "player campaign")

    def test_company_seat_preserves_sparse_opponents_and_real_objectives(self):
        script = """[GAME]
{
 NumUsers=3;
 RecordDemo=1;
 [MODOPTIONS] { va_campaign=1; }
 [AI0] { Team=1; ShortName=BARb; }
 [AI3] { Team=2; ShortName=SimpleAI; }
 [PLAYER0] { Team=7; Spectator=0; }
}
"""
        patched, team = patch_startscript(script, profile="hard_aggressive", speed=8, minutes=15, settle=40)
        self.assertEqual(team, 7)
        self.assertIn("[AI4]", patched)
        self.assertIn("[AI3] { Team=2; ShortName=SimpleAI; }", patched)
        self.assertIn("Team=7; Spectator=1;", patched)
        self.assertIn("NumUsers=4;", patched)
        self.assertIn("profile=hard_aggressive;", patched)
        self.assertIn("va_headless_fastwin=0;", patched)
        self.assertNotIn("va_autopilot_force_complete", patched)
        self.assertNotIn("va_extract_anywhere", patched)
        self.assertNotIn("va_beats", patched)
        with_beats, _ = patch_startscript(script, profile="hard", speed=8, minutes=15, settle=40, beats=True)
        self.assertIn("va_beats=1;", with_beats)

    def test_process_log_archive_includes_result_and_ignores_shared_infolog(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            result = b"VA_RESULT_JSON_BEGIN\nVA_RESULT_JSON_END\n"
            (root / "sortie_01.engine.txt").write_bytes(result)
            (root / "infolog.txt").write_text("unrelated launch")
            self.assertEqual(archive_log(root, 1).read_bytes(), result)


    def test_hud_flag_keeps_the_widgets(self):
        script = "[GAME]\n{\n NumUsers=1;\n RecordDemo=1;\n [MODOPTIONS] { va_campaign=1; }\n [PLAYER0] { Team=0; Spectator=0; }\n}\n"
        plain, _ = patch_startscript(script, profile="medium", speed=8, minutes=15, settle=40)
        hud, _ = patch_startscript(script, profile="medium", speed=8, minutes=15, settle=40, hud=True)
        self.assertIn("va_no_ui=1;", plain)
        self.assertNotIn("va_no_ui", hud)


class AutopilotGadgetTests(unittest.TestCase):
    def test_rescue_orders_departure_and_leaving(self):
        libs = glob.glob("/usr/lib/x86_64-linux-gnu/liblua5.4.so*")
        if not libs:
            self.skipTest("liblua5.4 is not installed")
        L = ctypes.CDLL(libs[0])
        L.luaL_newstate.restype = ctypes.c_void_p
        L.luaL_openlibs.argtypes = [ctypes.c_void_p]
        L.luaL_loadfilex.argtypes = [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_char_p]
        L.lua_pcallk.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_void_p, ctypes.c_void_p]
        L.lua_tolstring.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_void_p]
        L.lua_tolstring.restype = ctypes.c_char_p
        root = Path(__file__).resolve().parents[1]
        import os
        here = os.getcwd()
        os.chdir(root)
        try:
            st = L.luaL_newstate()
            L.luaL_openlibs(st)
            rc = L.luaL_loadfilex(st, b"tools/hud_harness/autopilot_test.lua", None) or L.lua_pcallk(st, 0, 0, 0, None, None)
            self.assertEqual(rc, 0, (L.lua_tolstring(st, -1, None) or b"").decode())
        finally:
            os.chdir(here)


if __name__ == "__main__":
    unittest.main()
