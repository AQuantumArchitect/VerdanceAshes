"""Run a tools/hud_harness/*.lua script under the system's Lua 5.4 (liblua5.4 through ctypes), from
the workspace root. Returns None when it passed, the error text when it failed, and raises
unittest.SkipTest when liblua5.4 is not installed."""
import ctypes
import glob
import os
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def run(script: str):
    libs = glob.glob("/usr/lib/x86_64-linux-gnu/liblua5.4.so*")
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
        rc = L.luaL_loadfilex(st, script.encode(), None) or L.lua_pcallk(st, 0, 0, 0, None, None)
        return None if rc == 0 else (L.lua_tolstring(st, -1, None) or b"").decode()
    finally:
        os.chdir(here)
