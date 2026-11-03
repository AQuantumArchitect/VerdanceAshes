"""A build refused for want of Tenebrium says so once per builder and unit type every 30 seconds
(tools/hud_harness/tnb_blocked_test.lua): the every-frame line filled a finale's log with 1.6 million
copies on Luke's PC (2026-11-03) until LuaUI ran out of memory and the sortie went unreported."""
import ctypes
import glob
import os
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class TnbBlockedTests(unittest.TestCase):
    def test_a_refused_build_says_so_every_thirty_seconds_not_every_frame(self):
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
        here = os.getcwd()
        os.chdir(ROOT)
        try:
            st = L.luaL_newstate()
            L.luaL_openlibs(st)
            rc = L.luaL_loadfilex(st, b"tools/hud_harness/tnb_blocked_test.lua", None) or L.lua_pcallk(st, 0, 0, 0, None, None)
            self.assertEqual(rc, 0, (L.lua_tolstring(st, -1, None) or b"").decode())
        finally:
            os.chdir(here)


if __name__ == "__main__":
    unittest.main()
