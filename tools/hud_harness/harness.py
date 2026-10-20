#!/usr/bin/env python3
"""Run the pass-7 widgets under a stubbed Spring/gl in liblua5.4 (ctypes). Catches runtime
errors in draw/update paths that a syntax check cannot. Not BAR; a smoke test."""
import ctypes, glob, json, sys, os
HERE = os.path.dirname(os.path.abspath(__file__))
# Fixtures: the repo's own (tools/hud_harness → workspace root), overridable with VA_FIXTURES / VA_WS.
WS = os.environ.get("VA_WS") or os.path.abspath(os.path.join(HERE, "..", ".."))
FIX = os.environ.get("VA_FIXTURES") or os.path.join(HERE, "fixtures")
WIDGETS = os.environ.get("VA_WIDGETS") or os.path.join(WS, "mod", "VerdanceAshes.sdd", "luaui", "Widgets")
INCLUDE = os.environ.get("VA_INCLUDE") or os.path.join(WS, "mod", "VerdanceAshes.sdd", "luaui", "Include")
so = glob.glob('/usr/lib/x86_64-linux-gnu/liblua5.4.so*')[0]
L = ctypes.CDLL(so)
L.luaL_newstate.restype = ctypes.c_void_p
L.luaL_openlibs.argtypes = [ctypes.c_void_p]
L.luaL_loadbufferx.argtypes = [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_size_t, ctypes.c_char_p, ctypes.c_char_p]
L.lua_pcallk.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_void_p, ctypes.c_void_p]
L.lua_tolstring.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_void_p]
L.lua_tolstring.restype = ctypes.c_char_p
L.lua_settop.argtypes = [ctypes.c_void_p, ctypes.c_int]

def run(st, src, name):
    rc = L.luaL_loadbufferx(st, src.encode(), len(src.encode()), name.encode(), b"t")
    if rc != 0:
        raise SystemExit("LOAD " + L.lua_tolstring(st, -1, None).decode())
    rc = L.lua_pcallk(st, 0, 0, 0, None, None)
    if rc != 0:
        raise SystemExit("RUN  " + L.lua_tolstring(st, -1, None).decode())

# ---- fixtures: zone map from authored json
auth = json.load(open(os.path.join(WS, 'data', 'zone_maps', 'authored', 'the_rock_jungle.authored.zone_map.json'), encoding='utf-8-sig'))
def lua(v, ind=0):
    pad = "  " * ind
    if v is None: return "nil"
    if isinstance(v, bool): return "true" if v else "false"
    if isinstance(v, (int, float)): return repr(v)
    if isinstance(v, str): return json.dumps(v, ensure_ascii=False)
    if isinstance(v, list): return "{" + ",".join(lua(x, ind+1) for x in v) + "}"
    if isinstance(v, dict):
        rows = []
        for k, x in v.items():
            ks = str(k); key = ks if ks.isidentifier() else f'[{json.dumps(ks)}]'
            rows.append(pad + "  " + key + " = " + lua(x, ind+1))
        return "{\n" + ",\n".join(rows) + "\n" + pad + "}"
    return json.dumps(str(v))
zones = []
for z in auth['zones']:
    zones.append({k: z.get(k) for k in ('zoneId','label','role','shape','cellGrid','cells','bounds','anchor') if z.get(k) is not None})
zone_map_lua = "return " + lua({"mapId": auth['mapId'], "zones": zones})
os.makedirs(os.path.join(HERE, 'fx'), exist_ok=True); open(os.path.join(HERE, 'fx/zone_map_current.lua'), 'w').write(zone_map_lua)
intel_lua = open(os.path.join(FIX, 'va_intel_current.lua'), encoding='utf-8').read()
pad_lua = open(os.path.join(FIX, 'va_pad_current.lua'), encoding='utf-8').read()
# give the intel a faction and an objective zone believed held
intel_lua = intel_lua.replace('held = {\n        v = 0.58,\n        c = 0.161,\n        state = "stale",', 'held = {\n        v = 0.58,\n        c = 0.161,\n        state = "stale", faction = "armada",', 1)
zids = [z['zoneId'] for z in auth['zones']]
mission_lua = "return " + lua({
    "missionId": "test_m1", "missionNumber": 1, "title": "Test", "deploymentMapId": auth['mapId'], "deploymentZoneId": "TRJ_SW_LANE",
    "pad": {"zoneId": "TRJ_SW_LANE"},
    "objective": {"description": "Wreck the fuel works at Central Gate and hold the gate until the clock.", "kind": "eco_raid", "targetZoneId": zids[3], "requiredFrames": 19800, "secondaryCaptureZoneIds": [zids[5]]},
    "missionCard": {"plainObjective": "Wreck the works at the gate. Hold until the clock, then lift from the pad.", "threats": "Expected opposition: reinforced"},
    "storyIntent": {"title": "Ash on the Gate", "storyReason": "The gate feeds the jungle.", "briefing": {"lines": ["Land quiet. Wreck loud. Lift with everyone.", "Second line."]}},
    "difficulty": {"label": "Expected opposition: reinforced, fortified"},
    "heroes": [{"id": "vane", "name": "Vane", "missionCritical": True, "level": 5, "rank": "Captain"}, {"id": "grath", "name": "Grath", "missionCritical": False, "level": 2, "rank": "Runner"}],
    "playableSetup": {"forces": [{"teamID": 0, "groups": [{"units": [{"unitDefName": "corthud", "count": 6}, {"unitDefName": "legrezbot", "count": 2}]}]}]},
})
files = {
    "singleplayer/verdance_ashes/generated/va_current.lua": mission_lua,
    "singleplayer/verdance_ashes/generated/zone_map_current.lua": zone_map_lua,
    "singleplayer/verdance_ashes/generated/va_intel_current.lua": intel_lua,
    "singleplayer/verdance_ashes/generated/va_pad_current.lua": pad_lua,
}
for inc in ('va_ash_tokens.lua', 'va_json.lua', 'va_board.lua'):
    files["luaui/Include/" + inc] = open(os.path.join(INCLUDE, inc), encoding='utf-8').read()
    files["LuaUI/Include/" + inc] = files["luaui/Include/" + inc]
fx_json = json.dumps(files, ensure_ascii=False)

heroes_json = json.dumps([
    {"id": "vane", "name": "Vane", "unit": 101, "hp": 0.72, "x": 1200, "z": 7000, "onPad": True, "zone": "TRJ_SW_LANE", "crit": True, "level": 5, "rank": "Captain", "vet": "hardened", "state": "alive", "dist": 120},
    {"id": "grath", "name": "Grath", "unit": 102, "hp": 0.3, "x": 4000, "z": 3000, "onPad": False, "zone": zids[3], "crit": False, "level": 2, "rank": "Runner", "vet": "", "state": "alive", "dist": 4900},
    {"id": "tal", "name": "Tal", "x": 5000, "z": 5000, "zone": zids[5], "state": "down", "feature": 7},
])
states_json = json.dumps({"vane": {"name": "Vane", "state": "alive", "missionCritical": True}, "grath": {"name": "Grath", "state": "alive"}, "old": {"name": "Old Roe", "state": "lost"}})

prelude = r'''
local FILES = FX_JSON
local json_decode
do
  -- reuse our own decoder for the fixture map
  local chunk = loadfile(FX_JSON_LUA)
  json_decode = chunk().decode
end
local FS = json_decode(FILES)
_G.VFS = { Include = function(path)
  local src = FS[path]
  if not src then error("VFS.Include missing " .. tostring(path)) end
  local f, err = load(src, path)
  if not f then error(err) end
  return f()
end, FileExists = function(p) return FS[p] ~= nil end, LoadFile = function(p) return FS[p] end }
_G.Game = { mapSizeX = 8192, mapSizeZ = 8192 }
_G.GL = { LINES = 1, LINE_LOOP = 2, QUADS = 7, POINTS = 0, TRIANGLES = 4 }
local calls = { text = 0, rect = 0, vertex = 0 }
_G.CALLS = calls
_G.gl = {
  Color = function() end, Rect = function() calls.rect = calls.rect + 1 end, Text = function(s) calls.text = calls.text + 1; assert(type(s) == "string" or type(s) == "number", "gl.Text non-string") end,
  GetTextWidth = function(s) return #tostring(s) * 0.6 end, LineWidth = function() end, PointSize = function() end,
  BeginEnd = function(mode, fn) fn() end, Vertex = function() calls.vertex = calls.vertex + 1 end, Texture = function() end, TexCoord = function() end,
  Shape = function() end, Scissor = function() end, DepthTest = function() end, Blending = function() end, ColorMask = function() end,
}
_G.RULES = { va_pad_x = 1578, va_pad_z = 6357, va_pad_r = 560, va_pad_zone = "TRJ_SW_LANE", va_objective_x = 4000, va_objective_z = 3000,
  va_secondary_total = 2, va_sec1_label = "Fuel dump", va_sec1_req = 1, va_sec1_x = 5000, va_sec1_z = 5000, va_sec1_kind = "structure",
  va_sec2_label = "RECOVER: Tal", va_sec2_req = 0, va_sec2_x = 5100, va_sec2_z = 5100, va_sec2_kind = "hero_recover",
  va_objective_total = 5, va_objective_destroyed = 2, va_pad_people = 1, va_pad_units = 4, va_pad_off_units = 3, va_pad_off_structures = 2, va_pad_enemy_live = 1,
  va_hud_heroes_json = HEROES_JSON, va_heroes_json = STATES_JSON, va_inbound_total = 2, va_obs_tick = 1, va_seen_TRJ_SW_LANE = 0.4, va_obs_TRJ_SW_LANE = 0.9, va_obs_enemy_TRJ_NW_MUSTER = 0,
  va_obs_TRJ_NW_MUSTER = 0.8, va_tenebrium_bank = 3,
}
_G.PAUSED = false
_G.FRAME = 0
_G.SENT = {}
_G.Spring = {
  GetGameRulesParam = function(n) return RULES[n] end,
  GetViewGeometry = function() return 1920, 1080 end,
  Echo = function(...) local t = {...}; for i = 1, #t do t[i] = tostring(t[i]) end; print("  [echo] " .. table.concat(t, " ")) end,
  GetGameFrame = function() return FRAME end, GetGameSeconds = function() return FRAME / 30 end,
  IsGUIHidden = function() return false end, IsGamePaused = function() return PAUSED end, GetGameSpeed = function() return 1, 1, PAUSED end,
  SendCommands = function(c) if c == "pause 1" then PAUSED = true elseif c == "pause 0" then PAUSED = false end; SENT[#SENT+1] = c end,
  SendLuaRulesMsg = function(m) SENT[#SENT+1] = m end,
  GetGroundHeight = function() return 10 end, MarkerAddLine = function(...) SENT[#SENT+1] = "line" end, MarkerAddPoint = function() error("no pings allowed") end,
  PlaySoundFile = function() return true end, GetUnitRulesParam = function() return nil end, GetUnitDefID = function() return nil end,
  ValidUnitID = function(u) return u == 101 or u == 102 end, SelectUnitArray = function(t) SENT[#SENT+1] = "select " .. tostring(t[1]) end,
  SetCameraTarget = function(x, y, z) SENT[#SENT+1] = "cam " .. tostring(x) end, WorldToScreenCoords = function(x, y, z) return 100, 100, 0.5 end,
  GetMyTeamID = function() return 0 end, GetTeamUnits = function() return {} end, GetAllFeatures = function() return {} end,
  GetUnitPosition = function() return 0, 0, 0 end, IsUnitVisible = function() return true end, GetFeatureRulesParam = function() return nil end,
  ValidFeatureID = function() return false end, GetFeaturePosition = function() return 0, 0, 0 end,
}
_G.UnitDefs = {}
_G.UnitDefNames = { corthud = { humanName = "Thud" }, legrezbot = { humanName = "Rez Bot" } }
_G.WG = {}
_G.GLOBALS = {}
_G.widgetHandler = { RegisterGlobal = function(self, w, name, fn) GLOBALS[name] = fn end, DeregisterGlobal = function() end, AddAction = function() end, RemoveAction = function() end }
_G.os = os
function LOADW(path, name)
  _G.widget = {}
  local fh = assert(io.open(path, "rb")); local src = fh:read("a"); fh:close()
  local f, err = load(src, name)
  if not f then error(err) end
  f()
  return _G.widget
end
'''

def main():
    st = L.luaL_newstate(); L.luaL_openlibs(st)
    open(os.path.join(HERE, 'fx/files.json'), 'w', encoding='utf-8').write(fx_json)
    open(os.path.join(HERE, 'fx/heroes.json'), 'w').write(heroes_json)
    open(os.path.join(HERE, 'fx/states.json'), 'w').write(states_json)
    rd = lambda n: f'(function() local fh = assert(io.open({json.dumps(os.path.join(HERE, "fx", n))}, "rb")); local s = fh:read("a"); fh:close(); return s end)()'
    pre = prelude.replace("FX_JSON_LUA", json.dumps(os.path.join(INCLUDE, 'va_json.lua'))).replace("FX_JSON", rd('files.json')).replace("HEROES_JSON", rd('heroes.json')).replace("STATES_JSON", rd('states.json'))
    run(st, pre, "prelude")
    widgets = {}
    for w in ('gui_verdance_voice', 'gui_verdance_minimap', 'gui_verdance_sidebar', 'gui_verdance_infil', 'gui_verdance_exfil', 'gui_verdance_hero_tags'):
        path = os.path.join(WIDGETS, w + '.lua')
        run(st, f"W_{w} = LOADW({json.dumps(path)}, {json.dumps(w)}); if W_{w}.Initialize then W_{w}:Initialize() end; print('init ok {w}')", w)
    script = r'''
local function step(label, fn)
  local ok, err = pcall(fn)
  print((ok and "ok   " or "FAIL ") .. label .. (ok and "" or ("  " .. tostring(err))))
  if not ok then FAILED = true end
end
local mm, sb, inf, ex, vo, ht = W_gui_verdance_minimap, W_gui_verdance_sidebar, W_gui_verdance_infil, W_gui_verdance_exfil, W_gui_verdance_voice, W_gui_verdance_hero_tags
step("board shared", function() assert(WG.vaBoard and #WG.vaBoard.zones > 5, "zones " .. tostring(WG.vaBoard and #WG.vaBoard.zones)) end)
step("board roles", function() local b = WG.vaBoard; assert(b.padId == "TRJ_SW_LANE", b.padId); assert(b.objectiveId, "obj"); local px = b:pad(); assert(px == 1578, tostring(px)) end)
step("believed", function() local s, c, f = WG.vaBoard:believed("TRJ_NW_MUSTER"); assert(s == "held" and f == "armada", s .. " " .. tostring(f)) end)
step("sentence", function() print("    " .. WG.vaBoard:sentence("TRJ_NW_MUSTER")); print("    " .. WG.vaBoard:sentence("TRJ_SE_MUSTER")) end)
-- infil: holds pause, draws, Enter begins
step("infil update (pause hammer)", function() inf:Update(); assert(PAUSED, "not paused"); inf:Update() end)
step("infil draw", function() inf:DrawScreen(); assert(CALLS.text > 20, "little drawn " .. CALLS.text) end)
step("infil modal fences sidebar", function() assert(WG.vaExfilModal == true); sb:DrawScreen(); vo:DrawScreen() end)
step("infil Enter begins", function() assert(inf:KeyPress(13)); assert(not PAUSED); assert(WG.vaSortieBegan == true); assert(WG.vaExfilModal == false) end)
-- sidebar after begin
FRAME = 400
step("sidebar poll+route", function() sb:GameFrame(400); assert(WG.vaRoute and WG.vaRoute.stage == "push", tostring(WG.vaRoute and WG.vaRoute.stage)); assert(WG.vaHeroes and #WG.vaHeroes == 4, "heroes " .. tostring(WG.vaHeroes and #WG.vaHeroes)) end)
step("route painted once", function() local n = 0; for _, s in ipairs(SENT) do if s == "line" then n = n + 1 end end; assert(n == 1, "lines " .. n); sb:GameFrame(430); n = 0; for _, s in ipairs(SENT) do if s == "line" then n = n + 1 end end; assert(n == 1, "repainted") end)
step("sidebar draw", function() CALLS.text = 0; sb:DrawScreen(); assert(CALLS.text > 15, "little drawn " .. CALLS.text) end)
step("minimap draw", function() mm:Update(); mm:DrawInMiniMap(300, 300); mm:DrawWorld() end)
step("voice draw", function() WG.vaVoice.say("Ketha", "Test line", 5); vo:DrawScreen() end)
step("hero tags", function() ht:GameFrame(30); ht:DrawScreenEffects() end)
-- hero card click: find rect
step("hero card click/dblclick", function()
  sb:DrawScreen()
  local hit = false
  -- probe a grid of points on the right rail for a hero rect
  for y = 1000, 100, -4 do
    if sb:MousePress(1800, y, 1) then hit = true end
  end
  assert(hit, "no hero rect hit")
  local sel = false; for _, s in ipairs(SENT) do if s:find("^select") then sel = true end end
  assert(sel, "no select")
end)
step("extract press", function()
  sb:DrawScreen()
  local pressed = false
  for y = 1000, 20, -3 do
    local before = #SENT
    sb:MousePress(1850, y, 1)
    if SENT[#SENT] == "VA_CMD:manifest" then pressed = true; break end
  end
  assert(pressed, "EXTRACT not found")
end)
-- exfil manifest
local manifest = [[{"schema":"verdance-manifest/1","pad":{"zoneId":"TRJ_SW_LANE","label":"Southwest Lane","x":1578,"z":6357,"radius":560},
 "destinations":[{"id":"home","label":"Back to camp","kind":"camp"},{"id":"TRJ_NW_MUSTER","label":"Northwest Muster","mapId":"the_rock_jungle","kind":"link"}],
 "going":{"heroes":[{"heroId":"vane","name":"Vane"}],"units":{"corthud":4},"unitCount":4},
 "staying":{"heroes":[{"heroId":"grath","name":"Grath","zoneId":"]] .. WG.vaBoard.objectiveId .. [["}],"units":{"TRJ_NW_MUSTER":3},"unitCount":3,"structures":{"TRJ_SW_LANE":{"count":2,"metal":400}},"structureCount":2},
 "enemyOnPad":1,"seen":{"TRJ_SW_LANE":0.9,"TRJ_NW_MUSTER":0.8},"tenebrium":3}]]
step("exfil manifest open", function() GLOBALS.VerdanceManifest(manifest); assert(WG.vaExfilModal and PAUSED) end)
step("exfil draw", function() CALLS.text = 0; ex:DrawScreen(); assert(CALLS.text > 20, "little drawn " .. CALLS.text) end)
step("exfil dest keys", function() ex:KeyPress(275); ex:DrawScreen(); ex:KeyPress(276) end)
step("exfil esc then enter", function() ex:KeyPress(27); assert(not WG.vaExfilModal); GLOBALS.VerdanceManifest(manifest); ex:KeyPress(13); assert(SENT[#SENT - 1] == "VA_CMD:extract:home", SENT[#SENT - 1]); ex:DrawScreen() end)
step("sortie over", function() RULES.va_terminal = 1; RULES.va_status = "extracted"; ex:Update(); ex:DrawScreen(); GLOBALS.VerdanceMissionEvent("sortie_over", "extracted"); sb:DrawScreen(); mm:DrawWorld() end)
step("mission events", function() RULES.va_terminal = 0; GLOBALS.VerdanceMissionEvent("objective_complete", "x"); GLOBALS.VerdanceHeroEvent("down", "grath", "Grath", 0, 1, 2); GLOBALS.VerdanceBeat("bark", "Ketha", "ambient line", 5); GLOBALS.VerdanceBeat("wave_warning", 1, 2, 3, "north"); GLOBALS.VerdanceVetRank(101, "green", "hardened", 1, 2, 3, "m"); vo:DrawScreen() end)
step("infil reopen", function() inf:TextCommand("vabrief"); inf:DrawScreen(); inf:KeyPress(13) end)
print(FAILED and "HARNESS FAILED" or "HARNESS PASSED")
'''
    run(st, script, "script")

if __name__ == '__main__':
    main()
