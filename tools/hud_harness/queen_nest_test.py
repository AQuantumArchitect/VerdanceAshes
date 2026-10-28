#!/usr/bin/env python3
"""The Queen's Nest, in real Lua 5.4 (ctypes) against stubs.

Spawner half: lifts the wake rule out of raptor_spawner_defense.lua and checks that with a nest on
the field, burning roosts down to one does not wake the queen, and the nest falling does.
Widget half: runs gui_verdance_queen_nest.lua and checks the nest is called out the first time it
comes into sight (once), painted while it stands, and that its fall is announced.

    VA_WS=$PWD python3 tools/hud_harness/queen_nest_test.py
"""
import ctypes, glob, json, os, re, sys

WS = os.environ.get("VA_WS") or os.getcwd()
MOD = os.path.join(WS, "mod", "VerdanceAshes.sdd")
SPAWNER = open(os.path.join(MOD, "luarules", "gadgets", "raptor_spawner_defense.lua"), encoding="utf-8").read()
WIDGET = os.path.join(MOD, "luaui", "Widgets", "gui_verdance_queen_nest.lua")

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
    local parts = {}
    for k, w in pairs(v) do parts[#parts + 1] = string.format("%q:%s", tostring(k), enc(w)) end
    return "{" .. table.concat(parts, ",") .. "}"
  elseif type(v) == "string" then return string.format("%q", v)
  elseif v == nil then return "null" else return tostring(v) end
end
'''

# the wake rule: the three lines that decide, as the spawner has them
m = re.search(r"(\t*local nestWakes = .*?\n\t*local countWakes = .*?\n)\t*if (queenAnger >= 100 or .*?) then", SPAWNER, re.S)
assert m, "wake rule not found in raptor_spawner_defense.lua"
RULE = m.group(1) + "return " + m.group(2)

SPAWN = ENC + r'''
config = { gracePeriod = 60 }
local function wakes(nest, burrowCount, queenAnger, t)
  VA_NEST = nest
  local f = load("local burrowCount, queenAnger, t = ...\n" .. %s)
  return f(burrowCount, queenAnger, t) == true
end
local out = {}
out.roostsDown = wakes({ id = 7, fallen = false }, 1, 20, 600)
out.nestDown = wakes({ id = 7, fallen = true }, 2, 20, 600)
out.anger = wakes({ id = 7, fallen = false }, 3, 100, 600)
out.stockCount = wakes({ id = nil, fallen = false }, 1, 20, 600)
out.grace = wakes({ id = 7, fallen = true }, 2, 20, 30)
return enc(out)
''' % json.dumps(RULE)

WIDGET_RUN = ENC + r'''
RULES, SAID, PAINT, TEXTS = {}, {}, 0, {}
UnitDefNames = { va_queen_nest = { id = 42 } }
local uiOpen, UI_DIR = io.open, %s   -- the HUD's own libraries come from disk
VFS = { Include = function(p)
  if p:find("va_active") then return true end
  local name = p:match("[Ii]nclude/(va_[%%w_]+%%.lua)$")
  local fh = name and uiOpen(UI_DIR .. "/" .. name, "rb")
  if not fh then error("no include " .. p) end
  local src = fh:read("a"); fh:close()
  return assert(load(src, p))()
end }
local units = { [7] = { def = 42, x = 1000, z = 2000 } }
Spring = {
  GetGameRulesParam = function(k) return RULES[k] end, GetUnitDefID = function(u) return units[u] and units[u].def end,
  GetVisibleUnits = function() return {} end, ValidUnitID = function(u) return units[u] ~= nil end,
  GetUnitIsDead = function() return false end, GetUnitPosition = function(u) local q = units[u]; if q then return q.x, 50, q.z end end,
  GetGroundHeight = function() return 50 end, IsGUIHidden = function() return false end,
  WorldToScreenCoords = function() return 500, 400, 0.5 end, GetViewGeometry = function() return 1920, 1080 end,
  PlaySoundFile = function() return true end, Echo = function() end,
}
WG = { vaVoice = { say = function(who, text) SAID[#SAID + 1] = text end } }
GL = { LINE_LOOP = 2 }
gl = { Color = function() end, LineWidth = function() end, DepthTest = function() end, Text = function(s) TEXTS[#TEXTS + 1] = s end,
       BeginEnd = function(_, fn) PAINT = PAINT + 1; fn() end, Vertex = function() end }
for _, k in ipairs({ "Color", "Rect", "Text", "GetTextWidth", "LineWidth", "PointSize", "BeginEnd", "Vertex", "Texture", "TexCoord", "Shape", "Scissor", "DepthTest", "Blending", "PushMatrix", "PopMatrix", "Translate", "Scale", "Rotate" }) do
  gl[k] = gl[k] or function(s) if k == "GetTextWidth" then return #tostring(s) * 0.6 end end
end
GL = GL or { LINES = 1, LINE_LOOP = 2, QUADS = 7, POINTS = 0, TRIANGLES = 4, TRIANGLE_FAN = 6, LINE_STRIP = 3 }
widget = {}
local chunk = assert(loadfile(%s, "t", setmetatable({}, { __index = _G, __newindex = _G })))
chunk()
widget:Initialize()
local out = {}
widget:DrawWorld(); out.paintedUnseen = PAINT
widget:UnitEnteredLos(7)
widget:UnitEnteredLos(7)
out.calls = #SAID
widget:DrawWorld(); out.paintedSeen = PAINT
widget:DrawScreen(); widget:DrawScreenEffects()
out.label = TEXTS[#TEXTS]
RULES.va_queen_nest_fallen = 1
widget:GameFrame(11)
out.fallCalls = #SAID
out.fallLine = SAID[#SAID]
return enc(out)
''' % (json.dumps(os.path.join(MOD, 'luaui', 'Include')), json.dumps(WIDGET))

ok = True


def check(label, cond, detail=""):
    global ok
    print(("ok   " if cond else "FAIL ") + label + ("  " + json.dumps(detail) if not cond else ""))
    ok = ok and cond


s = run(SPAWN)
check("burning the roosts down to one does not wake her while the nest stands", s["roostsDown"] is False, s)
check("the nest falling wakes her", s["nestDown"] is True, s)
check("full anger still wakes her", s["anger"] is True, s)
check("without a nest, the stock roost count still decides", s["stockCount"] is True, s)
check("nothing wakes her inside the grace period but anger", s["grace"] is False, s)

w = run(WIDGET_RUN)
check("an unseen nest is not painted", w["paintedUnseen"] == 0, w)
check("the nest is called out once, the first time it is seen", w["calls"] == 1, w)
check("a seen nest is painted in rings", w["paintedSeen"] > 0, w)
check("its fall is announced", w["fallCalls"] == 2 and "coming" in (w.get("fallLine") or ""), w)
print("QUEEN NEST " + ("PASSED" if ok else "FAILED"))
sys.exit(0 if ok else 1)
