"""Run one Lua file with the system Lua 5.4 (the hud_harness *_test.lua files): python tools/test_rig/run_lua.py FILE.lua"""
import ctypes,glob,os,sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'hud_harness'))
import liblua  # noqa: E402
L=ctypes.CDLL(liblua.paths()[0])
L.luaL_newstate.restype=ctypes.c_void_p
L.luaL_openlibs.argtypes=[ctypes.c_void_p]
L.luaL_loadfilex.argtypes=[ctypes.c_void_p,ctypes.c_char_p,ctypes.c_char_p]
L.lua_pcallk.argtypes=[ctypes.c_void_p,ctypes.c_int,ctypes.c_int,ctypes.c_int,ctypes.c_void_p,ctypes.c_void_p]
L.lua_tolstring.argtypes=[ctypes.c_void_p,ctypes.c_int,ctypes.c_void_p]; L.lua_tolstring.restype=ctypes.c_char_p
st=L.luaL_newstate(); L.luaL_openlibs(st)
rc=L.luaL_loadfilex(st,sys.argv[1].encode(),None) or L.lua_pcallk(st,0,0,0,None,None)
print(rc,(L.lua_tolstring(st,-1,None) or b"").decode())
