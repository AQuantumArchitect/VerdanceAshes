#!/usr/bin/env python3
"""HUD cost per frame: Lua garbage (KB) and GL calls, per widget, under the harness's stubbed
Spring/gl in liblua5.4. Not BAR, and 5.4 sizes differ a little from LuaJIT/5.1, but before/after
on the same stubs is a fair comparison.

    python tools/hud_harness/perf_bench.py                 # the installed field (VA_GEN, below)
    VA_GEN=<dir with va_current.lua + zone_map_current.lua> python tools/hud_harness/perf_bench.py

The field is the one a playtest ran: a Koom Valley sortie, 16 zones cut into 9216 cells. "fight"
means the enemy sees us in four zones (va_seen_*), which is where the hatch used to be painted
cell by cell. "intel" adds a belief for every zone (filled zones), the worst case for the board.
Time runs at 20 fps (the laptop), the observation tick every 2 s like the gadget's.
"""
import json, os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.argv = sys.argv[:1]
import harness as H  # noqa: E402  (builds its own fixtures; we replace the field below)

GEN = os.environ.get("VA_GEN") or os.path.join(H.WS, "mod", "VerdanceAshes.sdd", "singleplayer", "verdance_ashes", "generated")
FPS = 20

def read(p):
    return open(p, encoding="utf-8").read()

files = json.loads(open(os.path.join(HERE, "fx", "files.json"), encoding="utf-8").read()) if os.path.exists(os.path.join(HERE, "fx", "files.json")) else {}
for n in ("va_current.lua", "zone_map_current.lua", "va_pad_current.lua"):
    p = os.path.join(GEN, n)
    if os.path.exists(p):
        files["singleplayer/verdance_ashes/generated/" + n] = read(p)
for inc in sorted(os.listdir(H.INCLUDE)):
    files["luaui/Include/" + inc] = read(os.path.join(H.INCLUDE, inc))
    files["LuaUI/Include/" + inc] = files["luaui/Include/" + inc]
files["LuaRules/Configs/va_active.lua"] = read(os.path.join(H.WS, "mod", "VerdanceAshes.sdd", "luarules", "configs", "va_active.lua"))

# intel: none (what the playtest had), and a full one (every zone believed: fill everywhere)
zone_ids = []
import re
zm = files.get("singleplayer/verdance_ashes/generated/zone_map_current.lua", "")
zone_ids = re.findall(r'zoneId = "([A-Z0-9_]+)"', zm)
map_id = (re.search(r'mapId = "([a-z_]+)"', zm) or [None, "koom_valley"])[1]
empty_intel = 'return { mapId = "%s", zones = {} }' % map_id
rows = []
for i, z in enumerate(zone_ids):
    if i % 3 == 0:
        rows.append('%s = { ours = { v = 0.8, c = 0.6, state = "current" }, held = { v = 0.2, c = 0.6 } }' % z)
    elif i % 3 == 1:
        rows.append('%s = { ours = { v = 0.2, c = 0.5 }, held = { v = 0.8, c = 0.7, faction = "armada", state = "stale" } }' % z)
    else:
        rows.append('%s = { ours = { v = 0.3, c = 0.4 }, held = { v = 0.3, c = 0.4 } }' % z)
full_intel = 'return { mapId = "%s", zones = { %s } }' % (map_id, ", ".join(rows))

heroes = []
for i in range(9):
    heroes.append({"id": "h%d" % i, "name": "Hero Number %d With A Long Name" % i, "unit": 101 if i == 0 else 200 + i, "hp": 0.3 + 0.07 * i,
                   "x": 1200 + 400 * i, "z": 1500 + 300 * i, "onPad": i % 3 == 0, "zone": zone_ids[i % len(zone_ids)] if zone_ids else "",
                   "crit": i == 0, "level": 1 + i % 4, "rank": "Runner", "vet": "hardened" if i % 2 else "", "state": "down" if i == 8 else "alive", "dist": 300 + 900 * i})

def lua_str(s):
    return json.dumps(s)

FIGHT = ["KV_NW_MUSTER", "KV_NW_SPILLWAY", "KV_W_LANE", "KV_W_UPPER_LANE"]

def bench_script(intel_src):
    seen = ", ".join('va_seen_%s = %s' % (z, v) for z, v in zip(FIGHT, (0.6, 0.35, 0.2, 0.08)))
    obs = ", ".join('va_obs_%s = %s' % (z, v) for z, v in zip(FIGHT, (0.9, 0.5, 0.4, 0.1)))
    for name, body in (("bench_files.json", json.dumps(files, ensure_ascii=False)), ("bench_intel.lua", intel_src), ("bench_heroes.json", json.dumps(heroes))):
        open(os.path.join(HERE, "fx", name), "w", encoding="utf-8").write(body)
    rd = lambda n: f'(function() local fh = assert(io.open({json.dumps(os.path.join(HERE, "fx", n))}, "rb")); local s = fh:read("a"); fh:close(); return s end)()'
    return "FILES_JSON = " + rd("bench_files.json") + "\nINTEL = " + rd("bench_intel.lua") + "\nHEROES = " + rd("bench_heroes.json") + r'''
local FS = json_decode(FILES_JSON)
FS["singleplayer/verdance_ashes/generated/va_intel_current.lua"] = INTEL
_G.VFS.Include = function(path)
  local src = FS[path]
  if not src then error("VFS.Include missing " .. tostring(path)) end
  local f, err = load(src, path); if not f then error(err) end
  return f()
end
_G.VFS.FileExists = function(p) return FS[p] ~= nil end
_G.VFS.LoadFile = function(p) return FS[p] end
_G.Game = { mapSizeX = 12288, mapSizeZ = 8192 }
-- the GL stub, counted; display lists run their builder once (counted apart) and replay for free
local C = { rect = 0, vertex = 0, beginend = 0, text = 0, calllist = 0, built = 0 }
local building = 0
_G.CALLS = C
local nextList = 0
local function n(k) if building == 0 then C[k] = C[k] + 1 end end
gl.Rect = function() n("rect") end
gl.Vertex = function() n("vertex") end
gl.Text = function(s) n("text"); assert(type(s) == "string" or type(s) == "number", "gl.Text non-string") end
gl.BeginEnd = function(mode, fn, ...) n("beginend"); fn(...) end
gl.CreateList = function(fn, ...) building = building + 1; C.built = C.built + 1; fn(...); building = building - 1; nextList = nextList + 1; return nextList end
gl.CallList = function() C.calllist = C.calllist + 1 end
gl.DeleteList = function() end
SIMT = 100
os.clock = function() return SIMT end
RULES.va_hud_heroes_json = HEROES
RULES.va_pad_zone = "KV_NW_MUSTER"; RULES.va_pad_x = 1727; RULES.va_pad_z = 1578; RULES.va_pad_r = 560
RULES.va_objective_x = 6100; RULES.va_objective_z = 4100
RULES.va_obs_tick = 1
for k, v in pairs({ ''' + seen + ", " + obs + r''' }) do RULES[k] = v end
'''

def main(label, intel_src, sections):
    st = H.L.luaL_newstate(); H.L.luaL_openlibs(st)
    rd = lambda n: f'(function() local fh = assert(io.open({json.dumps(os.path.join(HERE, "fx", n))}, "rb")); local s = fh:read("a"); fh:close(); return s end)()'
    pre = H.prelude.replace("FX_JSON_LUA", json.dumps(os.path.join(H.INCLUDE, 'va_json.lua'))).replace("FX_JSON", rd('files.json')).replace("HEROES_JSON", rd('heroes.json')).replace("STATES_JSON", rd('states.json'))
    pre = pre.replace("_G.Spring = {", "_G.Spring = {\n  GetTimer = function() return 0 end, DiffTimers = function() return 0 end,", 1)
    H.run(st, pre, "prelude")
    H.run(st, bench_script(intel_src), "bench")
    for w in ('gui_verdance_voice', 'gui_verdance_minimap', 'gui_verdance_sidebar', 'gui_verdance_infil', 'gui_verdance_exfil', 'gui_verdance_hero_tags', 'gui_verdance_tnb_bar'):
        path = os.path.join(H.WIDGETS, w + '.lua')
        H.run(st, f"W_{w} = LOADW({json.dumps(path)}, {json.dumps(w)}); if W_{w}.Initialize then W_{w}:Initialize() end", w)
    H.run(st, r'''
local FPS = ''' + str(FPS) + r'''
local mm, sb, inf, vo, tnb = W_gui_verdance_minimap, W_gui_verdance_sidebar, W_gui_verdance_infil, W_gui_verdance_voice, W_gui_verdance_tnb_bar
local function measure(name, frames, fn)
  collectgarbage("collect"); collectgarbage("stop")
  for k in pairs(CALLS) do CALLS[k] = 0 end
  local kb0 = collectgarbage("count")
  for i = 1, frames do
    SIMT = SIMT + 1 / FPS; FRAME = FRAME + 1
    if FRAME % (2 * FPS) == 0 then RULES.va_obs_tick = RULES.va_obs_tick + 1 end
    fn(i)
  end
  local kb = collectgarbage("count") - kb0
  collectgarbage("restart")
  local f = frames
  print(string.format("  %-34s %8.1f KB/frame %7.2f MB/s | rect %6.0f vertex %7.0f beginEnd %6.0f text %5.0f callList %4.0f | lists built %d",
    name, kb / f, kb / f * FPS / 1024, CALLS.rect / f, CALLS.vertex / f, CALLS.beginend / f, CALLS.text / f, CALLS.calllist / f, CALLS.built))
end
print("''' + label + r'''")
local frames = 10 * FPS
if ''' + ("true" if "infil" in sections else "false") + r''' then
  measure("infil card (paused, board)", frames, function() inf:DrawScreen() end)
end
inf:KeyPress(13); WG.vaSortieBegan = true; PAUSED = false; WG.vaExfilModal = false
FRAME = 400; sb:GameFrame(FRAME)
measure("minimap board (DrawInMiniMap)", frames, function() mm:Update(); mm:DrawInMiniMap(320, 213) end)
measure("pad ring (DrawWorld)", frames, function() mm:DrawWorld() end)
measure("sidebar (GameFrame+DrawScreen)", frames, function() sb:GameFrame(FRAME); sb:DrawScreen() end)
WG.vaVoice.say("Ketha", "A line for the voice stack to frame.", 600); WG.vaVoice.say("Yeva", "Northwest Spillway was a blank on the map. It is not blank.", 600)
measure("voice (2 lines)", frames, function() vo:DrawScreen() end)
WG["topbar"] = { GetPosition = function() return { 400, 1040, 1920, 1080, 1 } end }
measure("tnb chip", frames, function() tnb:DrawScreen() end)
measure("ALL of the above, one frame", frames, function() mm:Update(); mm:DrawInMiniMap(320, 213); mm:DrawWorld(); sb:GameFrame(FRAME); sb:DrawScreen(); vo:DrawScreen(); tnb:DrawScreen() end)
''', "measure")

if __name__ == "__main__":
    main("== the playtest's field (no intel), fighting in 4 zones", empty_intel, ("infil",))
    main("== full intel (every zone believed), fighting in 4 zones", full_intel, ("infil",))
