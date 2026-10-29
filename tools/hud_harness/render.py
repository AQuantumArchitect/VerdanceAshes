#!/usr/bin/env python3
"""Render the pass-7 screens from recorded gl calls (harness stub) to PNG, so the layout can be
looked at before it ever runs in BAR. Approximate: DejaVu Sans for BAR's font, no $minimap."""
import json, os, sys
from PIL import Image, ImageDraw, ImageFont
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import harness as H

RECORDER = r'''
_G.REC = {}
local cur = {1,1,1,1}
local lw = 1
local function emit(t) REC[#REC+1] = t end
gl.Color = function(r, g, b, a) if type(r) == "table" then cur = { r[1], r[2], r[3], r[4] or 1 } else cur = { r or 1, g or 1, b or 1, a or 1 } end end
gl.Rect = function(x1, y1, x2, y2) emit({ "rect", x1, y1, x2, y2, cur[1], cur[2], cur[3], cur[4] }) end
gl.Text = function(s, x, y, size, opts) emit({ "text", tostring(s), x, y, size or 12, tostring(opts or ""), cur[1], cur[2], cur[3], cur[4] }) end
gl.LineWidth = function(w) lw = w or 1 end
gl.BeginEnd = function(mode, fn)
  local pts = {}
  local old = gl.Vertex
  gl.Vertex = function(x, y, z) if z ~= nil then pts[#pts+1] = { x, z } else pts[#pts+1] = { x, y } end end
  fn()
  gl.Vertex = old
  emit({ "prim", mode, pts, cur[1], cur[2], cur[3], cur[4], lw })
end
gl.Shape = function(mode, verts)
  local pts = {}
  for i = 1, #verts do pts[#pts+1] = { verts[i].v[1], verts[i].v[2] } end
  emit({ "prim", mode, pts, cur[1], cur[2], cur[3], cur[4], lw })
end
gl.PointSize = function() end
function DUMP(path)
  local fh = assert(io.open(path, "w"))
  local function q(s) return '"' .. tostring(s):gsub('\\', '\\\\'):gsub('"', '\\"'):gsub('\n', ' ') .. '"' end
  fh:write("[")
  for i, t in ipairs(REC) do
    if i > 1 then fh:write(",") end
    if t[1] == "rect" then fh:write(string.format('["rect",%g,%g,%g,%g,%g,%g,%g,%g]', t[2], t[3], t[4], t[5], t[6], t[7], t[8], t[9]))
    elseif t[1] == "text" then fh:write(string.format('["text",%s,%g,%g,%g,%s,%g,%g,%g,%g]', q(t[2]), t[3], t[4], t[5], q(t[6]), t[7], t[8], t[9], t[10]))
    else
      local ps = {}
      for _, p in ipairs(t[3]) do ps[#ps+1] = string.format("[%g,%g]", p[1], p[2]) end
      fh:write(string.format('["prim",%d,[%s],%g,%g,%g,%g,%g]', t[2], table.concat(ps, ","), t[4], t[5], t[6], t[7], t[8]))
    end
  end
  fh:write("]")
  fh:close()
  REC = {}
end
'''

def render(path, out, W=1920, Hh=1080, flipy=True, scale=1.0):
    rec = json.load(open(path))
    img = Image.new("RGBA", (int(W*scale), int(Hh*scale)), (14, 30, 22, 255))
    d = ImageDraw.Draw(img, "RGBA")
    fonts = {}
    def font(sz):
        k = max(6, int(round(sz*scale*1.15)))
        if k not in fonts: fonts[k] = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", k)
        return fonts[k]
    def col(r, g, b, a): return (int(r*255), int(g*255), int(b*255), int(max(0, min(1, a))*255))
    def Y(y): return (Hh - y)*scale if flipy else y*scale
    for t in rec:
        if t[0] == "rect":
            _, x1, y1, x2, y2, r, g, b, a = t
            xa, xb = sorted((x1*scale, x2*scale)); ya, yb = sorted((Y(y1), Y(y2)))
            if xb - xa < 1: xb = xa + 1
            if yb - ya < 1: yb = ya + 1
            ov = Image.new("RGBA", img.size, (0,0,0,0)); ImageDraw.Draw(ov).rectangle([xa, ya, xb, yb], fill=col(r,g,b,a)); img.alpha_composite(ov)
            d = ImageDraw.Draw(img, "RGBA")
        elif t[0] == "text":
            _, s, x, y, size, opts, r, g, b, a = t
            f = font(size)
            w = d.textlength(s, font=f)
            align = "l"
            for ch in opts:
                if ch in "lcr": align = ch
            xx = x*scale - (w/2 if align == "c" else (w if align == "r" else 0))
            yy = Y(y) - f.size*0.95
            if "o" in opts:
                d.text((xx, yy), s, font=f, fill=(0,0,0,int(180*a)), stroke_width=1, stroke_fill=(0,0,0,int(160*a)))
            d.text((xx, yy), s, font=f, fill=col(r,g,b,a))
        else:
            _, mode, pts, r, g, b, a, lw = t
            P = [(p[0]*scale, Y(p[1])) for p in pts]
            c = col(r,g,b,a); wdt = max(1, int(round(lw*scale)))
            if mode == 1:
                for i in range(0, len(P)-1, 2): d.line([P[i], P[i+1]], fill=c, width=wdt)
            elif mode == 2 and len(P) > 1:
                d.line(P + [P[0]], fill=c, width=wdt)
            elif mode == 0:
                for p in P: d.point(p, fill=c)
            elif mode == 7:   # GL.QUADS: filled, four corners each
                ov = Image.new("RGBA", img.size, (0,0,0,0)); od = ImageDraw.Draw(ov)
                for i in range(0, len(P) - 3, 4): od.polygon(P[i:i+4], fill=c)
                img.alpha_composite(ov); d = ImageDraw.Draw(img, "RGBA")
            elif len(P) > 1:
                d.line(P, fill=c, width=wdt)
    img.convert("RGB").save(out)
    print("wrote", out)

if __name__ == "__main__":
    st = H.L.luaL_newstate(); H.L.luaL_openlibs(st)
    files = H.files; fx_json = H.fx_json
    open(os.path.join(HERE, 'fx/files.json'), 'w', encoding='utf-8').write(fx_json)
    open(os.path.join(HERE, 'fx/heroes.json'), 'w').write(H.heroes_json)
    open(os.path.join(HERE, 'fx/states.json'), 'w').write(H.states_json)
    rd = lambda n: f'(function() local fh = assert(io.open({json.dumps(os.path.join(HERE, "fx", n))}, "rb")); local s = fh:read("a"); fh:close(); return s end)()'
    pre = H.prelude.replace("FX_JSON_LUA", json.dumps(os.path.join(H.INCLUDE, 'va_json.lua'))).replace("FX_JSON", rd('files.json')).replace("HEROES_JSON", rd('heroes.json')).replace("STATES_JSON", rd('states.json'))
    H.run(st, pre, "prelude")
    H.run(st, RECORDER, "recorder")
    for w in ('gui_verdance_voice', 'gui_verdance_minimap', 'gui_verdance_sidebar', 'gui_verdance_infil', 'gui_verdance_exfil'):
        p = os.path.join(H.WIDGETS, w + '.lua')
        H.run(st, f"W_{w} = LOADW({json.dumps(p)}, {json.dumps(w)}); if W_{w}.Initialize then W_{w}:Initialize() end", w)
    outdir = os.environ.get("VA_OUT") or os.path.join(HERE, "out")
    os.makedirs(outdir, exist_ok=True)
    scenes = r'''
local sb, inf, ex, vo, mm = W_gui_verdance_sidebar, W_gui_verdance_infil, W_gui_verdance_exfil, W_gui_verdance_voice, W_gui_verdance_minimap
-- 1. infil
inf:Update(); inf:Update(); inf:DrawScreen(); DUMP(OUT .. "/p7_infil.json")
-- 2. field: sidebar + voice + a minimap panel drawn into a 300x300 box bottom-left (offset by hand)
inf:KeyPress(13); FRAME = 2400
sb:GameFrame(2400); sb:DrawScreen()
WG.vaVoice.say("Ketha", "Primary's yours — finish the required marks, then bring them home.", 30); WG.vaVoice.say("Yeva", "Northwest Muster was briefed as theirs. There is nobody there.", 30); vo:DrawScreen()
-- minimap: translate by wrapping gl calls
do
  local ox, oy, S = 20, 20, 300
  local oldRect, oldText, oldBE = gl.Rect, gl.Text, gl.BeginEnd
  gl.Rect = function(x1, y1, x2, y2) oldRect(ox + x1, oy + y1, ox + x2, oy + y2) end
  gl.Text = function(s, x, y, size, o) oldText(s, ox + x, oy + y, size, o) end
  gl.BeginEnd = function(mode, fn)
    -- the recorder's BeginEnd swaps gl.Vertex in, so take it from inside (not before the call)
    oldBE(mode, function() local oldV = gl.Vertex; gl.Vertex = function(x, y, z) oldV(ox + x, oy + y) end; fn(); gl.Vertex = oldV end)
  end
  gl.Color(0.05, 0.09, 0.07, 1); gl.Rect(0, 0, S, S)
  mm:Update(); mm:DrawInMiniMap(S, S)
  gl.Rect, gl.Text, gl.BeginEnd = oldRect, oldText, oldBE
end
DUMP(OUT .. "/p7_field.json")
-- 3. exfil manifest
local manifest = [[{"schema":"verdance-manifest/1","pad":{"zoneId":"TRJ_SW_LANE","label":"Southwest Lane","x":1578,"z":6357,"radius":560},
 "destinations":[{"id":"home","label":"Back to camp","kind":"camp"},{"id":"TRJ_NW_MUSTER","label":"Northwest Muster","mapId":"the_rock_jungle","kind":"link"}],
 "going":{"heroes":[{"heroId":"vane","name":"Vane"}],"units":{"corthud":4,"legrezbot":1},"unitCount":5},
 "staying":{"heroes":[{"heroId":"grath","name":"Grath","zoneId":"]] .. WG.vaBoard.objectiveId .. [["}],"units":{"TRJ_NW_MUSTER":3},"unitCount":3,"structures":{"TRJ_SW_LANE":{"count":2,"metal":400}},"structureCount":2},
 "enemyOnPad":1,"seen":{"TRJ_SW_LANE":0.9,"TRJ_NW_MUSTER":0.8,"]] .. WG.vaBoard.objectiveId .. [[":0.35},"tenebrium":3}]]
RULES.va_manifest_json = manifest; RULES.va_manifest_seq = (RULES.va_manifest_seq or 0) + 1; ex:Update(); ex:DrawScreen(); DUMP(OUT .. "/p7_exfil.json")
ex:KeyPress(13); RULES.va_terminal = 1; RULES.va_status = "extracted"; ex:Update(); ex:DrawScreen(); DUMP(OUT .. "/p7_over.json")
'''
    H.run(st, "OUT = " + json.dumps(outdir) + "\n" + scenes, "scenes")
    for n in ("p7_infil", "p7_field", "p7_exfil", "p7_over"):
        render(os.path.join(outdir, n + ".json"), os.path.join(outdir, n + ".png"))
