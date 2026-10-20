#!/usr/bin/env python3
"""Real Lua syntax check via liblua5.4 (ctypes). Lua 5.1 widget code parses under 5.4 bar 'goto'."""
import ctypes, sys, glob
so = (glob.glob('/usr/lib/x86_64-linux-gnu/liblua5.4.so*') or [None])[0]
L = ctypes.CDLL(so)
L.luaL_newstate.restype = ctypes.c_void_p
L.luaL_loadbufferx.argtypes = [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_size_t, ctypes.c_char_p, ctypes.c_char_p]
L.lua_tolstring.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_void_p]
L.lua_tolstring.restype = ctypes.c_char_p
L.lua_close.argtypes = [ctypes.c_void_p]
bad = 0
for p in sys.argv[1:]:
    src = open(p, 'rb').read()
    st = L.luaL_newstate()
    rc = L.luaL_loadbufferx(st, src, len(src), p.encode(), b"t")
    if rc != 0:
        print("FAIL", L.lua_tolstring(st, -1, None).decode(errors='replace')); bad += 1
    else:
        print("ok  ", p)
    L.lua_close(st)
sys.exit(1 if bad else 0)
