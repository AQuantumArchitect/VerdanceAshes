#!/usr/bin/env python3
"""The hot drop, run in real Lua 5.4 (ctypes) against stubs.

Gadget half: lifts VA_HOT_drop out of game_verdance_campaign.lua and checks that a drop with the
wrong token lands nobody, the right one lands the chosen packs and no more of the reserve than
was asked for (and no more than was compiled in), and a second drop is ignored.
Widget half: runs gui_verdance_hotdrop.lua and checks it holds the pause while the field waits,
ignores a drop file from another game, sends the right one to the gadget, and unpauses with the
camera on the pad once the company is down.

    VA_WS=$PWD python3 tools/hud_harness/hot_drop_test.py
"""
import ctypes, glob, json, os, sys, tempfile

WS = os.environ.get("VA_WS") or os.getcwd()
MOD = os.path.join(WS, "mod", "VerdanceAshes.sdd")
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import campaign_lua  # noqa: E402
SRC = campaign_lua.source()
start = SRC.index("function VA_HOT_drop(line)")
end = SRC.index("\nend\n", start) + len("\nend\n")
DROP_FN = SRC[start:end]
WIDGET = os.path.join(MOD, "luaui", "Widgets", "gui_verdance_hotdrop.lua")

L = ctypes.CDLL(glob.glob('/usr/lib/x86_64-linux-gnu/liblua5.4.so*')[0])
L.luaL_newstate.restype = ctypes.c_void_p
L.luaL_openlibs.argtypes = [ctypes.c_void_p]
L.luaL_loadstring.argtypes = [ctypes.c_void_p, ctypes.c_char_p]
L.lua_pcallk.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_void_p, ctypes.c_void_p]
L.lua_tolstring.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_void_p]
L.lua_tolstring.restype = ctypes.c_char_p


def run(code):
    st = L.luaL_newstate()
    L.luaL_openlibs(st)
    if L.luaL_loadstring(st, code.encode()) != 0 or L.lua_pcallk(st, 0, 1, 0, None, None) != 0:
        print("LUA ERROR", L.lua_tolstring(st, -1, None).decode())
        sys.exit(1)
    return json.loads(L.lua_tolstring(st, -1, None).decode())


ENC = r'''
local function enc(v)
  if type(v) == "table" then
    local isList = #v > 0
    local parts = {}
    if isList then for _, w in ipairs(v) do parts[#parts + 1] = enc(w) end return "[" .. table.concat(parts, ",") .. "]" end
    for k, w in pairs(v) do parts[#parts + 1] = string.format("%q:%s", tostring(k), enc(w)) end
    return "{" .. table.concat(parts, ",") .. "}"
  elseif type(v) == "string" then return string.format("%q", v)
  elseif v == nil then return "null" else return tostring(v) end
end
'''

GADGET = ENC + r'''
RULES = {}
Spring = { Echo = function() end, SetGameRulesParam = function(k, v) RULES[k] = v end }
SPAWNED, PICKS, SWEEPS = {}, nil, 0
function spawnUnitSpec(spec, teamID) SPAWNED[spec.unitDefName] = (SPAWNED[spec.unitDefName] or 0) + spec.count; return spec.count end
function VA_CREW_confirm(picks) PICKS = picks end
function sweepPlayerCommanders() SWEEPS = SWEEPS + 1 end
VA_HOT = { token = "abc123", pending = true, reserve = {
  { spec = { unitDefName = "corthud", count = 5, reserve = true }, teamID = 0, baseX = 0, baseZ = 0, groupX = 0, groupZ = 0 },
  { spec = { unitDefName = "armwar", count = 2, reserve = true }, teamID = 0, baseX = 0, baseZ = 0, groupX = 0, groupZ = 0 },
} }
''' + DROP_FN + r'''
local out = {}
out.stale = VA_HOT_drop("zzz999|pavise|corthud:3")
out.staleSpawned = SPAWNED.corthud or 0
out.ok = VA_HOT_drop("abc123|pavise,halbard|corthud:3,armwar:9,legbar:4")
out.picks = PICKS
out.corthud = SPAWNED.corthud or 0
out.armwar = SPAWNED.armwar or 0
out.legbar = SPAWNED.legbar or 0
out.sweeps = SWEEPS
out.pending = VA_HOT.pending
out.rule = RULES.va_hotdrop_pending
out.again = VA_HOT_drop("abc123|pavise|corthud:1")
out.corthudAfter = SPAWNED.corthud or 0
return enc(out)
'''

tmp = tempfile.mkdtemp()
DROP = os.path.join(tmp, "drop.txt").replace("\\", "/")
WIDGET_RUN = ENC + r'''
local DROPPATH = %s
RULES = { va_hotdrop_pending = 1, va_hotdrop_token = "abc123", va_pad_x = 1200, va_pad_z = 3400 }
PAUSED, SENT, CMDS, CAMERA, REMOVED = false, {}, {}, nil, false
VFS = { Include = function(p) if p:find("va_active") then return true end error("no include " .. p) end, LoadFile = function() return nil end, RAW = 1 }
local realOpen = io.open
io.open = function(p, mode) if p == "LuaUI/Config/verdance/drop.txt" then return realOpen(DROPPATH, mode) end return nil end
Spring = {
  GetGameRulesParam = function(k) return RULES[k] end,
  IsGamePaused = function() return PAUSED end,
  SendCommands = function(c) CMDS[#CMDS + 1] = c; if c == "pause 1" then PAUSED = true elseif c == "pause 0" then PAUSED = false end end,
  SendLuaRulesMsg = function(m) SENT[#SENT + 1] = m end,
  SetCameraTarget = function(x, y, z) CAMERA = { x, z } end,
  GetGroundHeight = function() return 0 end,
  GetViewGeometry = function() return 1920, 1080 end,
  Echo = function() end,
}
gl = { Color = function() end, Text = function() end }
widget = {}
widgetHandler = { RemoveWidget = function() REMOVED = true end }
local chunk = assert(loadfile(%s, "t", setmetatable({}, { __index = _G, __newindex = _G })))
chunk()
local out = {}
local function step(n) for _ = 1, n do widget:Update(0.25); widget:DrawScreen() end end
-- waiting, no drop file: the pause holds
step(4)
out.heldPause = PAUSED
out.sentEarly = #SENT
-- the sim ticks with the window minimized (no Update): GameFrame holds the pause too
PAUSED = false
widget:GameFrame(1)
out.frameHeld = PAUSED
-- a drop file from another game
local f = realOpen(DROPPATH, "w"); f:write("old999|vane|\n"); f:close()
step(4)
out.sentStale = #SENT
-- the real drop
f = realOpen(DROPPATH, "w"); f:write("abc123|pavise,halbard|corthud:3\n"); f:close()
step(4)
out.sent = SENT[1]
out.stillPausedAfterSend = PAUSED
-- the gadget lands them: the field stays paused, the panel says so
RULES.va_hotdrop_pending = 0
step(3)
out.pausedOnPad = PAUSED
out.camera = CAMERA
out.removedEarly = REMOVED
-- the player unpauses: the widget steps aside
PAUSED = false
step(1)
out.playerUnpaused = not PAUSED
out.removed = REMOVED
return enc(out)
''' % (json.dumps(DROP), json.dumps(WIDGET))

ok = True


def check(label, cond, detail=""):
    global ok
    print(("ok   " if cond else "FAIL ") + label + ("  " + json.dumps(detail) if not cond else ""))
    ok = ok and cond


g = run(GADGET)
check("a drop with another game's token lands nobody", g["stale"] is False and g["staleSpawned"] == 0, g)
check("the right drop lands the chosen packs", g["ok"] is True and g["picks"] == ["pavise", "halbard"], g)
check("... and only the reserve asked for, never more than compiled in", g["corthud"] == 3 and g["armwar"] == 2 and g["legbar"] == 0, g)
check("... and clears the wait for the board", g["pending"] is False and g["rule"] == 0 and g["sweeps"] == 1, g)
check("a second drop is ignored", g["again"] is False and g["corthudAfter"] == 3, g)

w = run(WIDGET_RUN)
check("the widget holds the pause while the field waits", w["heldPause"] is True and w["sentEarly"] == 0, w)
check("it ignores a drop file from another game", w["sentStale"] == 0, w)
check("it sends the real drop to the gadget", w.get("sent") == "VA_CMD:vahotdrop abc123|pavise,halbard|corthud:3", w)
check("once the company is down the field stays paused on the pad",
      w["pausedOnPad"] is True and w["camera"] == [1200, 3400] and w["removedEarly"] is False, w)
check("the pause holds from GameFrame (a minimized window still ticks the sim)", w["frameHeld"] is True, w)
check("the player's unpause starts the fight and the widget steps aside",
      w["playerUnpaused"] is True and w["removed"] is True, w)
print("HOT DROP " + ("PASSED" if ok else "FAILED"))
sys.exit(0 if ok else 1)
