#!/usr/bin/env python3
"""Mission 1's opening beats, run in real Lua 5.4 (ctypes) against a tiny stubbed world.

The beats are the ones the hub writes (verdance.campaign.opening, from
data/escalation/mission1_opening.json); the engine is the gadget's own beats.lua. Each scenario
plays a different player and checks what the beats did:

  stalled    lands and touches nothing: every prompt fires in turn, the job is revealed on the
             fallback timer, the enemy comes to the company, the hook lands at minute 4:45
  quick      selects, moves, reaches the ring, attacks, kills and reclaims: no prompt ever shows,
             the reveal comes from the ring, the farm answers the first hit, the wreck ring clears
  late       does each thing a little after its prompt: the prompt shows, then is taken down
  hot pad    fights on the pad before the reveal: the farm's answer still waits for the reveal;
             a hero bay printing on its own is not the player building
  fast       takes the farm before minute five: the hook comes when the farm falls, and Ketha's
             reply sends the company to the pad instead of back to the farm
  heroes     a field recruit lying as a wreck from frame 2 is not "hero down"; a company hero
             down in the first minute waits until the minute is up
  generic    the beats of any other mission still run as before (time, objective progress)

    VA_WS=$PWD python3 tools/hud_harness/opening_beats_test.py      # prints ok/FAIL per check
"""
from __future__ import annotations

import ctypes
import glob
import json
import os
import sys
from pathlib import Path

WS = Path(os.environ.get("VA_WS") or os.getcwd()).resolve()
sys.path.insert(0, str(WS / "tools"))
from verdance.campaign import opening as O  # noqa: E402
from verdance.campaign.voice import generate_beats, load_ketha_voice  # noqa: E402

BEATS_LUA = WS / "mod" / "VerdanceAshes.sdd" / "luarules" / "gadgets" / "include" / "campaign" / "beats.lua"

L = ctypes.CDLL(glob.glob('/usr/lib/x86_64-linux-gnu/liblua5.4.so*')[0])
L.luaL_newstate.restype = ctypes.c_void_p
L.luaL_openlibs.argtypes = [ctypes.c_void_p]
L.luaL_loadstring.argtypes = [ctypes.c_void_p, ctypes.c_char_p]
L.lua_pcallk.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_void_p, ctypes.c_void_p]
L.lua_tolstring.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_void_p]
L.lua_tolstring.restype = ctypes.c_char_p


def lua(v) -> str:
    if v is None:
        return "nil"
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, (int, float)):
        return repr(v)
    if isinstance(v, str):
        return json.dumps(v, ensure_ascii=False)
    if isinstance(v, list):
        return "{" + ",".join(lua(x) for x in v) + "}"
    return "{" + ",".join(f"[{json.dumps(str(k))}]={lua(x)}" for k, x in v.items()) + "}"


# The world: an 8192 map, the pad at (1200, 900), the objective at (800, 1750). Player units are
# moved by the scenario; the facts arrive through the gadget call-ins beats.lua provides.
STUB = r'''
local ENC
ENC = function(v)
  if type(v) == "table" then
    local parts = {}
    if #v > 0 then for _, w in ipairs(v) do parts[#parts + 1] = ENC(w) end return "[" .. table.concat(parts, ",") .. "]" end
    for k, w in pairs(v) do parts[#parts + 1] = string.format("%q:%s", tostring(k), ENC(w)) end
    return "{" .. table.concat(parts, ",") .. "}"
  elseif type(v) == "string" then return string.format("%q", v)
  elseif v == nil then return "null" else return tostring(v) end
end
FRAME = 0
RULES, SENT, EVENTS, ECHO, SPAWNED, REMOVED = {}, {}, {}, {}, {}, {}
UNITS = {}   -- id -> { x, z, team }
Spring = {
  Echo = function(s) ECHO[#ECHO + 1] = tostring(s) end,
  GetGameFrame = function() return FRAME end,
  SetGameRulesParam = function(k, v) RULES[k] = v end,
  GetGameRulesParam = function(k) return RULES[k] end,
  GetGroundHeight = function() return 0 end,
  GetUnitsInCylinder = function(x, z, r, team)
    local out = {}
    for id, u in pairs(UNITS) do
      if u.team == team and (u.x - x) ^ 2 + (u.z - z) ^ 2 <= r * r then out[#out + 1] = id end
    end
    return out
  end,
  GetTeamUnitCount = function(team) local n = 0; for _, u in pairs(UNITS) do if u.team == team then n = n + 1 end end; return n end,
  AreTeamsAllied = function(a, b) return a == b end,
  GetUnitPosition = function(id) local u = UNITS[id]; if u then return u.x, 0, u.z end end,
  GetUnitTeam = function(id) local u = UNITS[id]; return u and u.team end,
  GetUnitDefID = function(id) local u = UNITS[id]; return u and u.def end,
  GetPlayerInfo = function(pid) return "p", true, false, 0 end,
  CreateUnit = function(def, x, y, z, f, team) SPAWNED[#SPAWNED + 1] = def; return 900 + #SPAWNED end,
  GiveOrderToUnit = function() end,
}
SendToUnsynced = function(ch, kind, a, b, c, d)
  if ch == "VERDANCE_BEAT" then SENT[#SENT + 1] = { kind = kind, a = a, b = b, c = c, d = d, t = FRAME / 30 }
  else EVENTS[#EVENTS + 1] = { ch = ch, kind = kind, a = a, t = FRAME / 30 } end
end
gadgetHandler = { RemoveCallIn = function(self, name) REMOVED[#REMOVED + 1] = name end }
Game = { mapSizeX = 8192, mapSizeZ = 8192 }
UnitDefNames = { armpw = { id = 1 }, armham = { id = 2 }, armfav = { id = 3 } }
UnitDefs = { [7] = { name = "legap", isFactory = true }, [8] = { name = "legrezbot" } }
CMD = { MOVE = 10, FIGHT = 16, PATROL = 15, ATTACK = 20, RECLAIM = 90, RESURRECT = 125, REPAIR = 40, FIRE_STATE = 45 }
playerTeamID, gaiaTeamID, objectiveTeamID, mercTeamID = 0, 9, 1, nil
VA_HOT = { pending = false }
heroes = {}
function heroInState(id, s1, s2) local r = heroes[id]; return r ~= nil and (r.state == s1 or r.state == s2) end
function heroWasRecovered(id) local r = heroes[id]; return r ~= nil and r.state == "alive" and r.everDown end
function VA_padPoint() return 1200, 900 end
targetZoneRect = { 400, 1400, 1200, 2100 }
function zoneRectFor(id) if id == "GF_NW_BASTION" then return targetZoneRect end return nil end
function normalizedToElmos(v, size) v = tonumber(v) or 0; if v <= 1 then return math.floor(v * size + 0.5) end return v end
function teamUnitCentroid(team) return 1200, 900 end
function enemyEntry(team, defs, x, z) return 100, 1800 end
function enemyResponseTarget() return 1200, 900 end
function spawnWave() end
function vaBeginWaterline() end
function scanZoneRect(rect) for _, u in pairs(UNITS) do if u.team == 0 and u.x >= rect[1] and u.x <= rect[3] and u.z >= rect[2] and u.z <= rect[4] then return true end end return false end
function truthy(v) return v == true or v == 1 or v == "1" end
objectiveTargetCount, objectiveTargetsDestroyed, objectiveComplete = 10, 0, false
waves = { spawned = 0, baseSize = 4 }
extraObj = { announced = false }
MarksLib = { upsert = function() end, KIND = { structure = "structure" } }
marks = {}
function marksCommit() end
'''

DRIVER = r'''
local fh = assert(io.open(BEATS_PATH, "rb")); local src = fh:read("a"); fh:close()
assert(load(src, "beats.lua"))()
mission = { beats = BEATS }
configureBeats({ va_beats = "1" }, false)
RULES.va_objective_x, RULES.va_objective_z = 800, 1750
beatsOnGameStart()
-- the sortie runs; checkBeats every 30 frames, as tickObjectiveChecks does
function RUN_TO(sec, each)
  while FRAME < sec * 30 do
    FRAME = FRAME + 30
    if each then each(FRAME / 30) end
    checkBeats(FRAME)
  end
end
function LAND() UNITS[1] = { x = 1200, z = 900, team = 0 }; UNITS[2] = { x = 1210, z = 910, team = 0 } end
function FIRED(id) for _, e in ipairs(ECHO) do if e == "VA_BEAT_FIRED id=" .. id then return true end end return false end
function CANCELLED(id) for _, e in ipairs(ECHO) do if e:find("VA_BEAT_CANCELLED id=" .. id .. " ", 1, true) then return true end end return false end
function SAID(tag) for _, s in ipairs(SENT) do if s.kind == "bark" and tostring(s.d):find("|" .. tag .. "$") then return s.t end end return nil end
function SENT_KIND(kind, a) for _, s in ipairs(SENT) do if s.kind == kind and (a == nil or s.a == a) then return s.t end end return nil end
function STAGE_AT(n) for _, e in ipairs(EVENTS) do if e.kind == "objective_stage" and e.a == tostring(n) then return e.t end end return nil end
'''


def beats_for(script, generic=None):
    return O.merge_opening_beats(script, generic or [], "GF_NW_BASTION", "Take the Northwest Bastion.")


def run(beats, body: str):
    st = L.luaL_newstate()
    L.luaL_openlibs(st)
    code = (STUB + f"\nBEATS = {lua(beats)}\nBEATS_PATH = {json.dumps(str(BEATS_LUA))}\n" + DRIVER + body
            + "\nreturn ENC(OUT)")
    if L.luaL_loadstring(st, code.encode()) != 0 or L.lua_pcallk(st, 0, 1, 0, None, None) != 0:
        raise RuntimeError("LUA " + L.lua_tolstring(st, -1, None).decode())
    return json.loads(L.lua_tolstring(st, -1, None).decode())


FAILED = []


def check(label, cond, detail=""):
    print(("ok   " if cond else "FAIL ") + label + ("" if cond else f"  {detail}"))
    if not cond:
        FAILED.append(label)


def main() -> int:
    script = O.load_opening(WS)
    assert script, "no opening script"
    P = script["pacing"]
    beats = beats_for(script)

    # ---- stalled: lands, touches nothing
    out = run(beats, r'''
OUT = {}
OUT.stage1 = STAGE_AT(1); OUT.goalX = RULES.va_op_goal_x; OUT.goalZ = RULES.va_op_goal_z; OUT.goalLabel = RULES.va_op_goal_label
LAND()
RUN_TO(460)
OUT.select = SAID("op_selectPrompt"); OUT.move = SAID("op_movePrompt"); OUT.attack = SAID("op_attackPrompt")
OUT.build = SAID("op_buildPrompt"); OUT.stage2 = STAGE_AT(2); OUT.job = RULES.va_op_job_label
OUT.probe = FIRED("op_probe"); OUT.answer = FIRED("op_answer"); OUT.hook = SAID("op_hookDispatch")
OUT.reply = SAID("op_hookReply"); OUT.spawned = #SPAWNED; OUT.column = FIRED("op_column")
OUT.removed = REMOVED[1]
''')
    land = 1  # the first check after landing (frame 30)
    check("stalled: the first goal is staged before the first frame", out.get("stage1") == 0 and out.get("goalLabel") == script["card"]["firstGoal"], out)
    gx, gz = out.get("goalX"), out.get("goalZ")
    dist = ((gx - 1200) ** 2 + (gz - 900) ** 2) ** 0.5 if gx is not None else 0
    check("stalled: the gold ring sits off the pad, toward the objective", gx is not None and dist >= P["goalMinFromPad"] - 1 and gz > 900, (gx, gz, dist))
    check("stalled: the select prompt comes after selectPromptSeconds", out.get("select") == land + P["selectPromptSeconds"], out.get("select"))
    check("stalled: no move prompt before anything is selected", out.get("move") is None, out.get("move"))
    check("stalled: the job is revealed on the fallback timer", out.get("stage2") == land + P["revealFallbackSeconds"], out.get("stage2"))
    check("stalled: the revealed job says what to take", out.get("job") == "Take the Northwest Bastion.", out.get("job"))
    check("stalled: the attack prompt comes after the reveal", out.get("attack") == land + P["revealFallbackSeconds"] + P["attackPromptSeconds"], out.get("attack"))
    check("stalled: they come to a company that sits still", out.get("probe") is True and not out.get("answer"), out)
    check("stalled: the hook lands at hookSeconds, Ketha answers it", out.get("hook") == land + P["hookSeconds"] and out.get("reply") == land + P["hookSeconds"] + P["hookReplySeconds"], (out.get("hook"), out.get("reply")))
    check("stalled: no build prompt without a wreck", out.get("build") is None, out.get("build"))
    check("stalled: the column pays the hook off", out.get("column") is True and out.get("spawned", 0) >= 2, out)

    # ---- quick: does everything before being asked
    out = run(beats, r'''
OUT = {}
LAND()
RUN_TO(60, function(t)
  if t == 3 then beatsNoteFact("selected", 0) end
  if t == 5 then beatsOnUnitCommand(0, CMD.MOVE, false) end
  if t == 40 then UNITS[1].x, UNITS[1].z = RULES.va_op_goal_x, RULES.va_op_goal_z end
  if t == 50 then beatsOnUnitDamaged(1, 0) end
  if t == 58 then UNITS[50] = { x = 900, z = 1600, team = 1 }; beatsOnUnitDestroyed(50, 1, 0) end
end)
OUT.reveal = STAGE_AT(2)
RUN_TO(200, function(t) if t == 70 then beatsOnFeatureBuildStep(0) end end)
OUT.prompts = {}
for _, tag in ipairs({ "op_selectPrompt", "op_movePrompt", "op_attackPrompt", "op_buildPrompt" }) do if SAID(tag) then OUT.prompts[#OUT.prompts + 1] = tag end end
OUT.cancelled = {}
for _, id in ipairs({ "op_select_prompt", "op_move_prompt", "op_attack_prompt", "op_build_prompt", "op_probe" }) do if CANCELLED(id) then OUT.cancelled[#OUT.cancelled + 1] = id end end
OUT.answer = SENT_KIND("bark") and SAID("op_answer"); OUT.spawned = #SPAWNED
OUT.mark = SENT_KIND("field_mark", "op_wreck"); OUT.cleared = SENT_KIND("clear_mark", "op_wreck")
for _, s in ipairs(SENT) do if s.kind == "field_mark" then OUT.markX, OUT.markZ = s.b, s.c end end
OUT.relief = SAID("op_relief"); OUT.pavise = SAID("op_pavise")
OUT.removed = REMOVED[1]
''')
    check("quick: no prompt ever shows", not out.get("prompts"), out.get("prompts"))
    check("quick: every prompt and the probe are cancelled", sorted(out.get("cancelled") or []) == sorted(
        ["op_select_prompt", "op_move_prompt", "op_attack_prompt", "op_build_prompt", "op_probe"]), out.get("cancelled"))
    check("quick: reaching the ring reveals the job", out.get("reveal") == 40, out.get("reveal"))
    check("quick: the farm answers our first hit after answerDelaySeconds", out.get("answer") == 50 + P["answerDelaySeconds"], out.get("answer"))
    check("quick: the first wreck gets a ring where it fell", out.get("mark") == 58 and out.get("markX") == 900 and out.get("markZ") == 1600, out)
    check("quick: the ring clears when a builder works the wreck", out.get("cleared") == 70, out.get("cleared"))
    check("quick: Ketha's relief line follows the first haul", out.get("relief") == 70 + P["reliefLineDelaySeconds"], out.get("relief"))
    check("quick: Pavise's line is skipped when Pavise did not drop", out.get("pavise") is None, out.get("pavise"))
    check("quick: the damage call-in is released after the first hit", out.get("removed") == "UnitDamaged", out.get("removed"))

    # ---- late: acts a little after each prompt; the prompt is taken down when they do
    sel = 1 + P["selectPromptSeconds"] + 2
    out = run(beats, r'''
OUT = {}
LAND()
heroes.pavise = { id = "pavise", state = "alive" }
RUN_TO(90, function(t)
  if t == %d then beatsOnUnitCommand(0, CMD.FIRE_STATE, false) end
  if t == %d then beatsNoteFact("selected", 0) end
end)
OUT.select = SAID("op_selectPrompt"); OUT.clearSelect = SENT_KIND("clear_bark", "op_selectPrompt")
OUT.move = SAID("op_movePrompt")
RUN_TO(400, function(t)
  if t == 120 then beatsOnUnitCommand(0, CMD.MOVE, false) end
  if t == 135 then beatsOnUnitCommand(0, CMD.ATTACK, false) end
  if t == 150 then UNITS[50] = { x = 900, z = 1600, team = 1 }; beatsOnUnitDestroyed(50, 1, 0) end
  if t == 150 + %d + 3 then beatsOnUnitCreated(0, 1) end
end)
OUT.clearMove = SENT_KIND("clear_bark", "op_movePrompt"); OUT.build = SAID("op_buildPrompt")
OUT.clearBuild = SENT_KIND("clear_bark", "op_buildPrompt"); OUT.pavise = SAID("op_pavise")
for _, s in ipairs(SENT) do if s.kind == "bark" and tostring(s.d):find("op_selectPrompt") then OUT.style = s.d; OUT.seconds = s.c end end
''' % (sel - 4, sel, P["buildPromptSeconds"]))
    check("late: a fire-state toggle is not a selection", out.get("select") == 1 + P["selectPromptSeconds"], out.get("select"))
    check("late: selecting takes the select prompt down", out.get("clearSelect") == sel, out.get("clearSelect"))
    check("late: the move prompt counts from the selection", out.get("move") == sel + P["movePromptSeconds"], out.get("move"))
    check("late: moving takes the move prompt down", out.get("clearMove") == 120, out.get("clearMove"))
    check("late: the build prompt comes after buildPromptSeconds, and goes when a builder works", out.get("build") == 150 + P["buildPromptSeconds"] and out.get("clearBuild") == 150 + P["buildPromptSeconds"] + 3, (out.get("build"), out.get("clearBuild")))
    check("late: a prompt is styled as a prompt and lasts promptShowSeconds", out.get("style") == "prompt||op_selectPrompt" and out.get("seconds") == P["promptShowSeconds"], (out.get("style"), out.get("seconds")))
    check("late: Pavise speaks when Pavise dropped", out.get("pavise") is not None, out.get("pavise"))

    # ---- hot pad: a fight in the first seconds, a hero bay printing on repeat
    out = run(beats, r'''
OUT = {}
LAND()
UNITS[20] = { x = 1250, z = 950, team = 0, def = 7 }   -- a bay, printing on its own
RUN_TO(80, function(t)
  if t == 4 then beatsOnUnitDamaged(1, 0) end
  if t == 6 then beatsOnUnitCreated(0, 20) end
  if t == 30 then UNITS[1].x, UNITS[1].z = RULES.va_op_goal_x, RULES.va_op_goal_z end
  if t == 40 then UNITS[50] = { x = 900, z = 1600, team = 1 }; beatsOnUnitDestroyed(50, 1, 0) end
end)
OUT.reveal = STAGE_AT(2); OUT.answer = SAID("op_answer"); OUT.build = SAID("op_buildPrompt")
''')
    check("hot pad: the farm's answer counts from the reveal, not from a fight on the pad", out.get("answer") == out.get("reveal", 0) + P["answerDelaySeconds"], out)
    check("hot pad: a bay printing on its own is not the player building", out.get("build") == 40 + P["buildPromptSeconds"], out.get("build"))

    # ---- fast: the farm falls before minute five
    out = run(beats, r'''
OUT = {}
LAND()
RUN_TO(400, function(t)
  if t == 3 then beatsNoteFact("selected", 0); beatsOnUnitCommand(0, CMD.FIGHT, false) end
  if t == 190 then objectiveComplete = true end
end)
OUT.hook = SAID("op_hookDispatch"); OUT.reply = SAID("op_hookReply"); OUT.taken = SAID("op_hookReplyTaken")
OUT.column = FIRED("op_column"); OUT.replyCancelled = CANCELLED("op_hook_reply"); OUT.columnCancelled = CANCELLED("op_column")
''')
    check("fast: the hook comes when the farm falls", out.get("hook") == 190, out.get("hook"))
    check("fast: Ketha sends them to the pad, not back to the farm", out.get("taken") == 190 + P["hookReplySeconds"] and out.get("reply") is None and out.get("replyCancelled"), out)
    check("fast: no second column (taking the farm brings the gadget's own)", out.get("column") is False and out.get("columnCancelled"), out)

    # ---- heroes: generic hero beats only for the company, and not in the first minute
    voice = load_ketha_voice(WS)
    generic = generate_beats({"campaignId": "verdance_ashes", "missionNumber": 1}, voice, "economy", {"targetZoneId": "GF_NW_BASTION"}, {})
    out = run(beats_for(script, generic), r'''
OUT = {}
heroes.cauter = { id = "cauter", state = "down", wasFieldRecruit = true, recruitable = true }
LAND()
RUN_TO(20)
OUT.downEarly = FIRED("b6_hero_down")
heroes.ketha = { id = "ketha", state = "down" }
RUN_TO(%d)
OUT.downBefore = FIRED("b6_hero_down")
RUN_TO(%d)
OUT.downAt = FIRED("b6_hero_down")
OUT.contact = FIRED("b2_contact"); OUT.moveOut = FIRED("b1_move_out")
''' % (P["heroBarksNotBeforeSeconds"] - 2, P["heroBarksNotBeforeSeconds"] + 1))
    check("heroes: a field recruit's wreck is not 'hero down'", out.get("downEarly") is False, out)
    check("heroes: a company hero down waits out the first minute", out.get("downBefore") is False and out.get("downAt") is True, out)
    check("heroes: the opening replaces the generic move-out and contact barks", not out.get("contact") and not out.get("moveOut"), out)

    # ---- generic: another mission's beats run as they did
    out = run(generic, r'''
OUT = {}
LAND()
RUN_TO(60)
OUT.moveOut = FIRED("b1_move_out")
objectiveTargetsDestroyed = 6
RUN_TO(62)
OUT.mid = FIRED("b3_midfight")
heroes.cauter = { id = "cauter", state = "down", wasFieldRecruit = true, recruitable = true }
RUN_TO(64)
OUT.down = FIRED("b6_hero_down")
heroes.vane = { id = "vane", state = "down" }
RUN_TO(66)
OUT.down2 = FIRED("b6_hero_down")
for _, s in ipairs(SENT) do if s.kind == "bark" then OUT.style = s.d; break end end
''')
    check("generic: the move-out bark still fires at 50 s", out.get("moveOut") is True, out)
    check("generic: objective progress still fires", out.get("mid") is True, out)
    check("generic: hero down ignores field recruits, hears the company", out.get("down") is False and out.get("down2") is True, out)
    check("generic: old barks stay ambient", out.get("style") == "ambient||", out.get("style"))

    print("OPENING BEATS " + ("FAILED: " + ", ".join(FAILED) if FAILED else "PASSED"))
    return 1 if FAILED else 0


if __name__ == "__main__":
    sys.exit(main())
