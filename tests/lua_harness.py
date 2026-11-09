"""Run a tools/hud_harness/*.lua script under the system's Lua 5.4 (liblua5.4 through ctypes), from
the workspace root. Returns None when it passed, the error text when it failed, and raises
unittest.SkipTest when liblua5.4 is not installed."""
import ctypes
import importlib.util
import os
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

_spec = importlib.util.spec_from_file_location("va_liblua", ROOT / "tools" / "hud_harness" / "liblua.py")
_liblua = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_liblua)


def liblua_paths():
    """The Lua 5.4 libraries found on this machine, best first (see tools/hud_harness/liblua.py)."""
    return _liblua.paths()


COMPAT_51_MATH = (b"math.atan2 = math.atan2 or math.atan; "
                  b"math.pow = math.pow or function(a, b) return a ^ b end; "
                  b"math.log10 = math.log10 or function(x) return math.log(x, 10) end")


def run(script: str):
    libs = liblua_paths()
    if not libs:
        raise unittest.SkipTest("liblua5.4 is not installed")
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
        # BAR runs Lua 5.1, which has math.atan2/pow/log10. Debian's Lua 5.4 keeps them (LUA_COMPAT_MATHLIB);
        # a stock build (Windows, DEVCOM.Lua) does not, so put them back for the gadgets under test.
        L.luaL_loadstring.argtypes = [ctypes.c_void_p, ctypes.c_char_p]
        L.luaL_loadstring(st, COMPAT_51_MATH) or L.lua_pcallk(st, 0, 0, 0, None, None)
        rc = L.luaL_loadfilex(st, script.encode(), None) or L.lua_pcallk(st, 0, 0, 0, None, None)
        return None if rc == 0 else (L.lua_tolstring(st, -1, None) or b"").decode()
    finally:
        os.chdir(here)
