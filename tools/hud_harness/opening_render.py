#!/usr/bin/env python3
"""Mission 1's opening, beat by beat, as PNGs: the widgets' own draw calls, driven by the gadget's
own beats.lua running the beats the hub writes.

Not BAR: there is no terrain and no unit models (headless BAR draws nothing). The field is a
top-down schematic of the north-west of Greenest Fields: the company's belief board painted at
field scale, our units as green squares, Armada's as blue, the field marks' rings and the route
line where BAR would draw them on the ground. The rail, the voice stack and the cards are drawn
by the real widgets (gui_verdance_sidebar / _voice / _infil / _field_marks / _minimap).

    UMWELT_SRC=/path/to/umwelt/src python3 tools/hud_harness/opening_render.py [outdir]
    # default outdir: docs/screens/mission1_opening
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import harness as H  # noqa: E402
import render as R  # noqa: E402

WS = Path(H.WS)
sys.path.insert(0, str(WS / "tools"))
umwelt = os.environ.get("UMWELT_SRC")
if umwelt and umwelt not in sys.path:
    sys.path.append(umwelt)
from verdance.campaign import engine as E  # noqa: E402

OUT = Path(sys.argv[1]) if len(sys.argv) > 1 else WS / "docs" / "screens" / "mission1_opening"
SCALE = 0.75


def opening_intent():
    """A fresh campaign's mission 1, materialised by the hub in a throwaway workspace."""
    tmp = Path(tempfile.mkdtemp(prefix="va_opening_"))
    os.symlink(WS / "data", tmp / "data")
    (tmp / "outbox").mkdir()
    state = E.migrate_state(E.default_v1_state())
    E.ensure_zone_memory(state, tmp)
    intent = E.materialize_next_intent(state, tmp)
    assert intent.get("openingMission") and intent.get("opening"), "the fresh campaign did not open on the opening raid"
    read = lambda n: (tmp / "outbox" / n).read_text(encoding="utf-8") if (tmp / "outbox" / n).is_file() else None
    return intent, read("va_intel_current.lua"), read("va_pad_current.lua")


def zone_map_lua(map_id: str) -> str:
    auth = json.load(open(WS / "data" / "zone_maps" / "authored" / f"{map_id}.authored.zone_map.json", encoding="utf-8-sig"))
    zones = [{k: z.get(k) for k in ("zoneId", "label", "role", "shape", "cellGrid", "cells", "bounds", "anchor") if z.get(k) is not None}
             for z in auth["zones"]]
    return "return " + H.lua({"mapId": auth["mapId"], "zones": zones})


def seed_for(intent) -> dict:
    obj = intent["objectiveTarget"]
    return {
        "missionId": intent["missionId"], "missionNumber": 1, "title": intent.get("title"),
        "deploymentMapId": intent["mapId"], "deploymentZoneId": intent["deploymentZoneId"],
        "pad": {"zoneId": intent["deploymentZoneId"]},
        "objective": {"description": obj.get("description"), "kind": obj.get("kind"), "targetZoneId": obj.get("targetZoneId"),
                      "requiredFrames": 8 * 60 * 30, "secondaryCaptureZoneIds": []},
        "storyIntent": {k: intent.get(k) for k in ("title", "storyReason", "briefing", "opening", "missionNumber")},
        "difficulty": {"label": (intent.get("difficultyPresentation") or {}).get("label")},
        "heroes": [{"id": "ketha", "name": "Ketha", "missionCritical": True, "level": 1, "rank": "Runner"},
                   {"id": "pavise", "name": "Pavise", "missionCritical": False, "level": 1, "rank": "Runner"}],
        "roster": {"cadre": {"leglob": 5, "legrezbot": 4}},
        "doors": intent.get("doors") or [],
        "beats": intent["beats"],
    }


# The gadget's world, beside the widgets in one Lua state: beats.lua with the few gadget globals it
# reads, units the scenes move by hand, SendToUnsynced handed straight to the widgets' globals.
WORLD = r'''
UNITS, NEXT_ID, ROUTE = {}, 100, nil
heroes = {}
playerTeamID, gaiaTeamID, objectiveTeamID, mercTeamID = 0, 9, 1, nil
VA_HOT = { pending = false }
targetZoneRect = { 0, 0, 2730, 4096 }
objectiveTargetCount, objectiveTargetsDestroyed, objectiveComplete = 24, 0, false
waves = { spawned = 0, baseSize = 4 }
extraObj = { announced = false }
MarksLib = { upsert = function() end, KIND = { structure = "structure" } }
marks = {}
function marksCommit() end
function heroInState(id, s1, s2) local r = heroes[id]; return r ~= nil and (r.state == s1 or r.state == s2) end
function heroWasRecovered(id) local r = heroes[id]; return r ~= nil and r.state == "alive" and r.everDown end
function VA_padPoint() return RULES.va_pad_x, RULES.va_pad_z end
function zoneRectFor(id) return nil end
function normalizedToElmos(v, size) v = tonumber(v) or 0; if v <= 1 then return math.floor(v * size + 0.5) end return v end
function teamUnitCentroid(team) local n, sx, sz = 0, 0, 0; for _, u in pairs(UNITS) do if u.team == team then n = n + 1; sx = sx + u.x; sz = sz + u.z end end; if n == 0 then return nil end; return sx / n, sz / n end
function enemyEntry(team, defs, x, z) return 160, 2300 end
function enemyResponseTarget() return RULES.va_pad_x, RULES.va_pad_z end
function spawnWave() end
function vaBeginWaterline() end
-- start.lua's: the objective mark on the centroid of the claimed targets (here, the farm below)
function publishObjectiveMarker() RULES.va_objective_x, RULES.va_objective_z = 3260, 2460 end
function scanZoneRect() return false end
function truthy(v) return v == true or v == 1 or v == "1" end
CMD = { MOVE = 10, FIGHT = 16, PATROL = 15, ATTACK = 20, RECLAIM = 90, RESURRECT = 125, REPAIR = 40 }
UnitDefNames.armpw = { id = 11, humanName = "Pawn" }; UnitDefNames.armham = { id = 12, humanName = "Mace" }; UnitDefNames.armfav = { id = 13, humanName = "Rover" }
function ADD(x, z, team, kind, label) NEXT_ID = NEXT_ID + 1; UNITS[NEXT_ID] = { x = x, z = z, team = team, kind = kind, label = label }; return NEXT_ID end
Spring.SetGameRulesParam = function(k, v) RULES[k] = v end
Spring.GetUnitsInCylinder = function(x, z, r, team) local out = {}; for id, u in pairs(UNITS) do if u.team == team and (u.x - x) ^ 2 + (u.z - z) ^ 2 <= r * r then out[#out + 1] = id end end; return out end
Spring.GetTeamUnitCount = function(team) local n = 0; for _, u in pairs(UNITS) do if u.team == team then n = n + 1 end end; return n end
Spring.GetTeamUnits = function(team) local out = {}; for id, u in pairs(UNITS) do if u.team == team and u.kind ~= "wreck" then out[#out + 1] = id end end; table.sort(out); return out end
Spring.GetUnitPosition = function(id) local u = UNITS[id]; if u then return u.x, 0, u.z end end
Spring.GetUnitTeam = function(id) local u = UNITS[id]; return u and u.team end
Spring.GetUnitRadius = function() return 22 end
Spring.AreTeamsAllied = function(a, b) return a == b end
Spring.GetPlayerInfo = function() return "player", true, false, 0 end
Spring.CreateUnit = function(def, x, y, z, f, team) return ADD(x, z, team, "unit", nil) end
Spring.GiveOrderToUnit = function() end
SELECTED = 0
Spring.GetSelectedUnitsCount = function() return SELECTED end
Spring.MarkerAddLine = function(x1, y1, z1, x2, y2, z2) ROUTE = { x1, z1, x2, z2 } end
Spring.SendLuaRulesMsg = function(m) if m:sub(1, 18) == "VA_CMD:vabeatfact " then beatsNoteFact(m:sub(19), 0) end end
SendToUnsynced = function(ch, kind, a, b, c, d)
  if ch == "VERDANCE_BEAT" and GLOBALS.VerdanceBeat then GLOBALS.VerdanceBeat(kind, a, b, c, d)
  elseif ch == "VERDANCE_MISSION_EVENT" and GLOBALS.VerdanceMissionEvent then GLOBALS.VerdanceMissionEvent(kind, a) end
end
do
  local fh = assert(io.open(BEATS_PATH, "rb")); local src = fh:read("a"); fh:close()
  assert(load(src, "beats.lua"))()
end
mission = VFS.Include("singleplayer/verdance_ashes/generated/va_current.lua")
configureBeats({ va_beats = "1" }, false)
'''

SCENES = r'''
local vo, mm, sb, inf, fm = W_gui_verdance_voice, W_gui_verdance_minimap, W_gui_verdance_sidebar, W_gui_verdance_infil, W_gui_verdance_field_marks
local ARMADA = Ash.faction("armada")
local GREEN = Ash.COL.edge
-- the field: the north-west of Greenest Fields, framed as a camera over it would be
local FX0, FZ0, FSIZE, FW, FH = 0, 450, 2900, 1640, 1080
local function fproj(wx, wz) local s = FH / FSIZE; return (wx - FX0) * s, FH - (wz - FZ0) * s end

local function frame()
  FRAME = FRAME + 30
  sb:GameFrame(FRAME)
  mm:Update(); fm:Update()
  checkBeats(FRAME)
end
local function runTo(sec, each) while FRAME < sec * 30 do frame(); if each then each(FRAME / 30) end end end

local function drawUnits()
  for _, u in pairs(UNITS) do
    local sx, sy = fproj(u.x, u.z)
    if u.kind == "wreck" then
      Ash.text("✚", sx, sy - 7, 16, Ash.with(Ash.COL.ash, 0.9), "c")
    else
      local col = (u.team == 0) and GREEN or ARMADA
      local r = (u.kind == "building") and 9 or 5
      gl.Color(col[1], col[2], col[3], 0.95); gl.Rect(sx - r, sy - r, sx + r, sy + r)
      gl.Color(0, 0, 0, 0.7); gl.Rect(sx - r, sy - r, sx + r, sy - r + 1)
      if u.label then Ash.text(u.label, sx, sy + 9, 11, Ash.COL.ink, "c") end
    end
  end
end

local function drawField(caption)
  gl.Color(0.075, 0.13, 0.085, 1); gl.Rect(0, 0, 1920, 1080)
  local b = WG.vaBoard
  b:paint(fproj, { fade = false, labels = true, glyphSize = 18 })
  -- the route the rail paints on the field (MarkerAddLine)
  if ROUTE then
    local ax, ay = fproj(ROUTE[1], ROUTE[2]); local bx, by = fproj(ROUTE[3], ROUTE[4])
    gl.Color(0.95, 0.95, 0.95, 0.55); gl.LineWidth(2)
    gl.BeginEnd(GL.LINES, function() gl.Vertex(ax, ay); gl.Vertex(bx, by) end)
  end
  drawUnits()
  -- the ground rings, drawn where BAR draws them: world x/z through the field projection
  local oldBE = gl.BeginEnd
  gl.BeginEnd = function(mode, fn)
    oldBE(mode, function()
      local oldV = gl.Vertex
      gl.Vertex = function(x, y, z) local sx, sy = fproj(x, z); oldV(sx, sy) end
      fn()
      gl.Vertex = oldV
    end)
  end
  fm:DrawWorld()
  gl.BeginEnd = oldBE
  -- the minimap in its corner, as BAR places it
  do
    local ox, oy, S = 12, 12, 300
    local oldRect, oldText, oldBE2 = gl.Rect, gl.Text, gl.BeginEnd
    gl.Rect = function(x1, y1, x2, y2) oldRect(ox + x1, oy + y1, ox + x2, oy + y2) end
    gl.Text = function(s, x, y, size, o) oldText(s, ox + x, oy + y, size, o) end
    gl.BeginEnd = function(mode, fn) oldBE2(mode, function() local oldV = gl.Vertex; gl.Vertex = function(x, y, z) oldV(ox + x, oy + y) end; fn(); gl.Vertex = oldV end) end
    gl.Color(0.05, 0.09, 0.07, 1); gl.Rect(0, 0, S, S)
    if WG.vaBoard.dropCaches then WG.vaBoard:dropCaches() end   -- the stub's display lists replay nothing
    mm:DrawInMiniMap(S, S)
    gl.Rect, gl.Text, gl.BeginEnd = oldRect, oldText, oldBE2
  end
  sb:DrawScreen()
  vo:DrawScreen()
  Ash.text(caption, 330, 22, 13, Ash.with(Ash.COL.ash, 0.95), "l")
end

local function shot(name, caption) drawField(caption); DUMP(OUT .. "/" .. name .. ".json"); SHOTS[#SHOTS + 1] = name end
SHOTS = {}

-- the nearest decoy farm in the Bastion (the shell pocket gf_central_n, 0.40 / 0.30): turbines and
-- panels, two decoy commanders tending them, a sentry
local farm = {}
for i, p in ipairs({ { 3150, 2380 }, { 3260, 2420 }, { 3380, 2460 }, { 3200, 2540 }, { 3320, 2580 }, { 3450, 2380 }, { 3100, 2500 } }) do
  farm[i] = ADD(p[1], p[2], 1, "building", nil)
end
local decoy = ADD(3050, 2340, 1, "unit", "Commander")
ADD(3420, 2520, 1, "unit", "Commander")
ADD(2980, 2420, 1, "building", "Sentry")

-- 0. the card, paused, before anyone has moved
beatsOnGameStart()
mm:Update()
inf:Update(); inf:Update(); inf:DrawScreen(); DUMP(OUT .. "/01_briefing.json"); SHOTS[#SHOTS + 1] = "01_briefing"
inf:KeyPress(13); PAUSED = false

-- the company lands on the muster
local company = {}
local px, pz = RULES.va_pad_x, RULES.va_pad_z
company.ketha = ADD(px - 40, pz + 10, 0, "unit", "Ketha")
company.pavise = ADD(px + 50, pz + 30, 0, "unit", "Pavise")
heroes.ketha = { id = "ketha", state = "alive" }; heroes.pavise = { id = "pavise", state = "alive" }
for i = 1, 4 do company["z" .. i] = ADD(px - 110 + i * 30, pz - 60, 0, "unit", nil) end
for i = 1, 5 do company["s" .. i] = ADD(px - 60 + i * 30, pz + 90, 0, "unit", nil) end
RULES.va_hud_heroes_json = '[{"id":"ketha","name":"Ketha","unit":101,"hp":1,"x":' .. px .. ',"z":' .. pz .. ',"onPad":true,"zone":"GF_NW_MUSTER","crit":true,"level":1,"rank":"Runner","state":"alive","dist":40},{"id":"pavise","name":"Pavise","unit":102,"hp":1,"x":' .. px .. ',"z":' .. pz .. ',"onPad":true,"zone":"GF_NW_MUSTER","crit":false,"level":1,"rank":"Runner","state":"alive","dist":60}]'
RULES.va_pad_people, RULES.va_pad_units = 2, 11

runTo(3)
shot("02_landed", "0:02  landed · the company ringed on the pad, the first goal ringed in gold, the rail says only that")
runTo(14)
shot("03_select_prompt", "0:14  nothing selected after selectPromptSeconds: the select prompt (blue, framed)")
SELECTED = 11
runTo(16)
runTo(32)
shot("04_move_prompt", "0:32  selected, nobody ordered to move after movePromptSeconds: the move prompt")
beatsOnUnitCommand(0, CMD.MOVE, false)
local gx, gz = RULES.va_op_goal_x, RULES.va_op_goal_z
local start = {}
for k, id in pairs(company) do start[k] = { UNITS[id].x, UNITS[id].z } end
local offset = {}
local n = 0
for k in pairs(company) do n = n + 1; offset[k] = { ((n % 4) - 1.5) * 40, (math.floor(n / 4) - 1) * 40 } end
runTo(52, function(t)
  local f = math.min(1, (t - 33) / 16)
  for k, id in pairs(company) do
    UNITS[id].x = start[k][1] + (gx + offset[k][1] - start[k][1]) * f
    UNITS[id].z = start[k][2] + (gz + offset[k][2] - start[k][2]) * f
  end
  if t == 45 then
    RULES.va_capture_mode, RULES.va_capture_phase, RULES.va_objective_total, RULES.va_pocket_clear_need, RULES.va_objective_destroyed = 1, "clear", 24, 15, 0
    RULES.va_claim_need, RULES.va_claim_value = 1500, 300
    RULES.va_pad_people, RULES.va_pad_units = 0, 0
    RULES.va_hud_heroes_json = '[{"id":"ketha","name":"Ketha","unit":101,"hp":1,"x":' .. gx .. ',"z":' .. gz .. ',"onPad":false,"zone":"GF_NW_BASTION","crit":true,"level":1,"rank":"Runner","state":"alive","dist":1900},{"id":"pavise","name":"Pavise","unit":102,"hp":0.9,"x":' .. gx .. ',"z":' .. gz .. ',"onPad":false,"zone":"GF_NW_BASTION","crit":false,"level":1,"rank":"Runner","state":"alive","dist":1920}]'
  end
end)
shot("05_reveal", "0:52  a unit reached the ring: the real job is revealed (rail, board, route, Ketha)")
runTo(77)
shot("06_attack_prompt", "1:17  nothing of theirs hit after attackPromptSeconds: the attack prompt")
beatsOnUnitCommand(0, CMD.ATTACK, false)
runTo(102)
shot("07_answer", "1:42  our first hit +answerDelaySeconds: the farm's answer comes in from Armada's edge")
UNITS[decoy].kind = "wreck"; UNITS[decoy].team = 9; UNITS[decoy].label = nil
beatsOnUnitDestroyed(decoy, 1, 0)
RULES.va_objective_destroyed = 3
runTo(112)
shot("08_first_kill", "1:52  our first kill: a blue dashed ring on the wreck, no words")
runTo(137)
shot("09_build_prompt", "2:17  no builder on it after buildPromptSeconds: the build prompt")
beatsOnFeatureBuildStep(0)
RULES.va_objective_destroyed = 6
runTo(150)
shot("10_relief", "2:30  a Zagreus strips the wreck: the ring clears, Ketha, then Pavise")
objectiveTargetsDestroyed = 13; RULES.va_objective_destroyed = 13
runTo(200)
shot("11_midfight", "3:20  half the farm down: the mission's own midfight line (kept from the generic beats)")
RULES.va_objective_destroyed = 15; RULES.va_capture_phase = "hold"; RULES.va_zone_hold = 240; RULES.va_zone_hold_need = 600
runTo(291)
shot("12_hook", "4:51  hookSeconds after landing: Armada's intercepted dispatch names the commander; Ketha answers")
'''


def old_infil():
    """The card as it was on master (for the before/after): its widget, same seed."""
    try:
        src = subprocess.run(["git", "-C", str(WS), "show", "origin/master:mod/VerdanceAshes.sdd/luaui/Widgets/gui_verdance_infil.lua"],
                             capture_output=True, text=True, check=True).stdout
    except Exception:
        return False
    path = Path(tempfile.mkdtemp(prefix="va_old_infil_")) / "gui_verdance_infil_master.lua"
    path.write_text(src, encoding="utf-8")
    return str(path)


def main():
    intent, intel, pad = opening_intent()
    files = dict(H.files)
    files["singleplayer/verdance_ashes/generated/va_current.lua"] = "return " + H.lua(seed_for(intent))
    files["singleplayer/verdance_ashes/generated/zone_map_current.lua"] = zone_map_lua(intent["mapId"])
    if intel:
        files["singleplayer/verdance_ashes/generated/va_intel_current.lua"] = intel
    if pad:
        files["singleplayer/verdance_ashes/generated/va_pad_current.lua"] = pad
    fx = HERE / "fx"
    fx.mkdir(exist_ok=True)
    (fx / "files.json").write_text(json.dumps(files, ensure_ascii=False), encoding="utf-8")
    (fx / "heroes.json").write_text("[]")
    (fx / "states.json").write_text("{}")
    rd = lambda n: f'(function() local fh = assert(io.open({json.dumps(str(fx / n))}, "rb")); local s = fh:read("a"); fh:close(); return s end)()'
    pre = H.prelude.replace("FX_JSON_LUA", json.dumps(os.path.join(H.INCLUDE, "va_json.lua"))).replace("FX_JSON", rd("files.json")) \
        .replace("HEROES_JSON", rd("heroes.json")).replace("STATES_JSON", rd("states.json"))
    OUT.mkdir(parents=True, exist_ok=True)
    tmp_out = Path(tempfile.mkdtemp(prefix="va_opening_render_"))
    beats_path = WS / "mod" / "VerdanceAshes.sdd" / "luarules" / "gadgets" / "include" / "campaign" / "beats.lua"
    shots = []

    def state_with(widgets):
        st = H.L.luaL_newstate(); H.L.luaL_openlibs(st)
        H.run(st, pre, "prelude")
        H.run(st, R.RECORDER, "recorder")
        # the pad and the objective as the gadgets publish them on Greenest Fields (a real run:
        # pad 1236,896; before the shell is claimed the objective point is the Bastion's box centre)
        H.run(st, "RULES = { va_pad_x = 1236, va_pad_z = 896, va_pad_r = 560, va_pad_zone = 'GF_NW_MUSTER', va_objective_x = 1365, va_objective_z = 2048, va_tenebrium_bank = 3 }\n"
              "Ash = VFS.Include('luaui/Include/va_ash_tokens.lua')\n"
              "UnitDefNames.legrezbot = { humanName = 'Zagreus' }; UnitDefNames.leglob = { humanName = 'Satyr' }", "rules")
        for name, path in widgets:
            H.run(st, f"W_{name} = LOADW({json.dumps(str(path))}, {json.dumps(name)}); if W_{name}.Initialize then W_{name}:Initialize() end", name)
        return st

    widgets = [(w, Path(H.WIDGETS) / f"{w}.lua") for w in
               ("gui_verdance_voice", "gui_verdance_minimap", "gui_verdance_sidebar", "gui_verdance_infil", "gui_verdance_field_marks")]
    st = state_with(widgets)
    H.run(st, f"BEATS_PATH = {json.dumps(str(beats_path))}\n" + WORLD, "world")
    H.run(st, f"OUT = {json.dumps(str(tmp_out))}\n" + SCENES, "scenes")
    names = ["01_briefing", "02_landed", "03_select_prompt", "04_move_prompt", "05_reveal", "06_attack_prompt", "07_answer",
             "08_first_kill", "09_build_prompt", "10_relief", "11_midfight", "12_hook"]
    # before: master's card on the same seed (it printed the briefing line as a Lua table address)
    old = old_infil()
    if old:
        st2 = state_with([("gui_verdance_minimap", Path(H.WIDGETS) / "gui_verdance_minimap.lua"), ("gui_verdance_infil", Path(old))])
        H.run(st2, f"OUT = {json.dumps(str(tmp_out))}\n" + "W_gui_verdance_minimap:Update(); W_gui_verdance_infil:Update(); W_gui_verdance_infil:Update(); W_gui_verdance_infil:DrawScreen(); DUMP(OUT .. '/00_briefing_before.json')", "before")
        names.insert(0, "00_briefing_before")
    for n in names:
        R.render(str(tmp_out / f"{n}.json"), str(tmp_out / f"{n}.full.png"))
        from PIL import Image
        img = Image.open(tmp_out / f"{n}.full.png")
        img = img.resize((int(img.width * SCALE), int(img.height * SCALE)), Image.LANCZOS)
        img.save(OUT / f"{n}.png", optimize=True)
        shots.append(OUT / f"{n}.png")
    print("\n".join(str(p) for p in shots))


if __name__ == "__main__":
    main()
