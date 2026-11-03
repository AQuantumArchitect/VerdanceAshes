"""Mission 1's opening (issue #7): the script and its one pacing table, what the hub writes from them,
and the beats run in real Lua (tools/hud_harness/opening_beats_test.py).

The script is data/escalation/mission1_opening.json; the hub half is verdance.campaign.opening; the
gadget half is luarules/gadgets/include/campaign/beats.lua; the beat sheet is docs/MISSION1_OPENING.md.
"""
from __future__ import annotations

import copy
import glob
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from verdance.campaign import opening as O  # noqa: E402
from verdance.campaign.voice import generate_beats, load_ketha_voice  # noqa: E402

SCRIPT = json.loads((ROOT / O.OPENING_FILE).read_text(encoding="utf-8-sig"))
# Words that never come out of a character's mouth: the engine's vocabulary, and the words Ketha's
# register forbids (data/story/voices/ketha.json).
SYSTEM_WORDS = ("density", "matrix", "qubit", "quantum", "superposition", "eigen", "entangle", "amplitude",
                "wavefunction", "decoherence", "observable", "measurement", "collapse", "axis", "estimate",
                "uncertain", "umwelt", "belief", "divergence", "prior")


def _beats(script=None, generic=None, farm=None):
    return O.merge_opening_beats(script or SCRIPT, generic or [], "GF_NW_BASTION", "Take the Northwest Bastion.", farm)


def _by_id(beats):
    return {b["id"]: b for b in beats}


def _spoken(script=None):
    s = script or SCRIPT
    out = [row["text"] for row in s["briefing"]] + [row["text"] for row in s["lines"].values()]
    return out + [s["card"]["firstGoal"], s["card"]["missionGoal"], s["card"]["pauseLine"]]


# ---------------------------------------------------------------- the script and the table
def test_the_script_is_complete_and_every_tunable_is_explained():
    assert O.problems(SCRIPT) == []
    assert set(SCRIPT["pacing"]) == set(O.PACING_KEYS), "the pacing table and opening.PACING_KEYS disagree"
    assert set(SCRIPT["pacingNotes"]) == set(SCRIPT["pacing"]), "every pacing key needs a note, and only those"
    assert O.load_opening(ROOT) is not None


def test_every_timing_in_the_beats_comes_from_the_one_table():
    # Give every pacing key its own value; every number a beat carries must be one of them, and
    # every timing key must be used by some beat.
    script = copy.deepcopy(SCRIPT)
    for i, k in enumerate(O.PACING_KEYS):
        script["pacing"][k] = 1000 + i
    beats = _beats(script, generate_beats({"missionNumber": 1}, load_ketha_voice(ROOT), "economy",
                                          {"targetZoneId": "GF_NW_BASTION"}, {}))
    tuned = set(script["pacing"].values())
    seen = set()

    def walk(node, key=""):
        if isinstance(node, dict):
            for k, v in node.items():
                walk(v, k)
        elif isinstance(node, list):
            for v in node:
                walk(v, key)
        elif isinstance(node, (int, float)) and not isinstance(node, bool):
            if key in ("seconds", "notBefore", "radius", "stopShort", "minFromPad"):
                seen.add(node)

    opening = [b for b in beats if b["id"].startswith("op_")]
    for b in opening:
        walk(b)
    for b in beats:
        if b.get("notBefore") is not None:
            seen.add(b["notBefore"])
    stray = {n for n in seen if n not in tuned}
    assert not stray, f"literal timings in the opening beats: {sorted(stray)}"
    unused = {k for k in O.PACING_KEYS if script["pacing"][k] not in seen} - {"briefingMaxWords"}
    assert not unused, f"pacing keys no beat uses: {sorted(unused)}"


def test_the_briefing_is_short_and_in_voice():
    assert O.card_words(SCRIPT) <= SCRIPT["pacing"]["briefingMaxWords"] <= 60
    assert all(row["speaker"] == "ketha" for row in SCRIPT["briefing"])
    assert all(len(row["text"]) <= 90 for row in SCRIPT["briefing"]), "Ketha's register: under ~90 characters"
    briefing = O.opening_briefing(SCRIPT)
    assert [l["tag"] for l in briefing["lines"]] == ["opening"] * len(SCRIPT["briefing"])


def test_no_system_vocabulary_in_anyone_s_mouth():
    for text in _spoken():
        low = text.lower()
        for w in SYSTEM_WORDS:
            assert not re.search(r"\b" + w, low), f"'{w}' in: {text}"


def test_field_lines_fit_their_frame():
    for key, row in SCRIPT["lines"].items():
        assert len(row["text"]) <= 66, f"{key} is {len(row['text'])} characters: {row['text']}"


# ---------------------------------------------------------------- the beats the hub writes
def test_staged_objective_first_goal_then_the_job():
    beats = _by_id(_beats(farm={"x": 0.4, "z": 0.3}))
    first = beats["op_stage_first"]
    assert first["trigger"] == {"type": "sortie_start"}
    act = first["actions"][0]
    assert act["type"] == "objective_stage" and act["stage"] == 1 and act["at"] == "overlook"
    assert act["label"] == SCRIPT["card"]["firstGoal"]
    assert (act["towardX"], act["towardZ"]) == (0.4, 0.3), "the ring is set toward the hub's nearest farm"
    reveal = beats["op_reveal"]
    assert reveal["afterBeat"] == "op_land"
    kinds = [t["type"] for t in reveal["trigger"]["of"]]
    assert reveal["trigger"]["type"] == "any_of" and kinds == ["near_point", "elapsed"]
    stage2 = [a for a in reveal["actions"] if a["type"] == "objective_stage"][0]
    assert stage2["stage"] == 2 and stage2["label"] == "Take the Northwest Bastion."


def test_each_control_is_learned_by_doing_with_a_stall_prompt():
    beats = _by_id(_beats())
    for control, fact, prompt_id, done_id, tag in (
        ("select", "player_selected", "op_select_prompt", "op_selected", "op_selectPrompt"),
        ("move", "player_moved", "op_move_prompt", "op_moved", "op_movePrompt"),
        ("attack", "player_attacked", "op_attack_prompt", "op_attacked", "op_attackPrompt"),
        ("build", "player_built", "op_build_prompt", "op_built", "op_buildPrompt"),
    ):
        p = beats[prompt_id]
        assert p["trigger"]["type"] == "elapsed", control
        assert [c["type"] for c in p["cancelIf"]] == [fact], f"{control}: the prompt must cancel when the player does it"
        bark = p["actions"][0]
        assert bark["priority"] == "prompt" and bark["tag"] == tag, control
        done = beats[done_id]
        assert done["trigger"]["type"] == fact, control
        assert {"type": "clear_bark", "tag": tag} in done["actions"], f"{control}: doing it takes the prompt down"


def test_the_enemy_answers_what_the_player_does():
    beats = _by_id(_beats())
    assert beats["op_answer"]["afterBeat"] == "op_attacked"
    assert any(a["type"] == "spawn" and a["fightTo"] == "player" for a in beats["op_answer"]["actions"])
    probe = beats["op_probe"]
    assert [c["type"] for c in probe["cancelIf"]] == ["player_attacked"], "they only come to a company that sits still"


def test_minute_five_ends_on_a_hook_that_is_paid_off():
    beats = _by_id(_beats())
    hook = beats["op_hook"]
    assert hook["afterBeat"] == "op_land" and 240 <= hook["trigger"]["seconds"] <= 300
    assert beats["op_hook_reply"]["afterBeat"] == "op_hook"
    column = beats["op_column"]
    assert column["afterBeat"] == "op_hook" and any(a["type"] == "spawn" for a in column["actions"])


def test_generic_beats_the_opening_keeps_and_drops():
    generic = generate_beats({"missionNumber": 1}, load_ketha_voice(ROOT), "economy", {"targetZoneId": "GF_NW_BASTION"}, {})
    ids = [b["id"] for b in generic]
    assert ids[:7] == ["b1_move_out", "b2_contact", "b3_midfight", "b4_wave", "b5_run_home", "b6_hero_down", "b7_hero_back"]
    merged = _by_id(_beats(generic=generic))
    assert "b1_move_out" not in merged and "b2_contact" not in merged
    for bid in ("b3_midfight", "b4_wave", "b5_run_home"):
        assert bid in merged and "notBefore" not in merged[bid]
    for bid in O.HERO_BEATS:
        assert merged[bid]["notBefore"] == SCRIPT["pacing"]["heroBarksNotBeforeSeconds"]
    assert "notBefore" not in generic[5], "merging must not touch the generic list it was given"


def test_farm_point_picks_the_nearest_pocket_in_the_target_zone():
    pockets = [{"zoneId": "GF_NW_BASTION", "center": [0.35, 0.5]}, {"zoneId": "GF_NW_BASTION", "center": [0.4, 0.3]},
               {"zoneId": "GF_SE_PLATEAU", "center": [0.16, 0.12]}]
    assert O.farm_point(pockets, ROOT, "greenest_fields", "GF_NW_MUSTER", "GF_NW_BASTION") == {"x": 0.4, "z": 0.3}
    assert O.farm_point([], ROOT, "greenest_fields", "GF_NW_MUSTER", "GF_NW_BASTION") is None


# ---------------------------------------------------------------- the intent (hub end to end)
def _fresh_workspace():
    tmp = tempfile.TemporaryDirectory()
    ws = Path(tmp.name)
    try:
        os.symlink(ROOT / "data", ws / "data")
    except (OSError, NotImplementedError):
        tmp.cleanup()
        return None, None
    (ws / "outbox").mkdir()
    return tmp, ws


def test_a_fresh_campaign_opens_with_the_authored_opening():
    from verdance.campaign import engine as E
    tmp, ws = _fresh_workspace()
    if ws is None:
        return  # no symlinks here (Windows without developer mode): the unit tests above still ran
    with tmp:
        state = E.migrate_state(E.default_v1_state())
        E.ensure_zone_memory(state, ws)
        intent = E.materialize_next_intent(state, ws)
        assert intent["openingMission"] and intent["mapId"] == "greenest_fields"
        assert intent["opening"]["staged"] and intent["opening"]["cardWords"] <= 60
        assert intent["opening"]["missionGoal"] == "Take the Northwest Bastion: break the farm, then hold the ground."
        assert [l["text"] for l in intent["briefing"]["lines"] if l["tag"] == "opening"] == [r["text"] for r in SCRIPT["briefing"]]
        ids = [b["id"] for b in intent["beats"]]
        assert ids[0] == "op_stage_first" and "b1_move_out" not in ids and "b5_run_home" in ids
        first = intent["beats"][0]["actions"][0]
        assert first.get("towardX") is not None, "the hub found the Bastion's nearest farm"


def test_other_missions_keep_the_generic_briefing_and_beats():
    from verdance.campaign import engine as E
    tmp, ws = _fresh_workspace()
    if ws is None:
        return
    with tmp:
        state = E.migrate_state(E.default_v1_state())
        state["missionNumber"], state["currentMissionId"] = 2, "va_002"
        state["history"] = [{"missionId": "va_001", "status": "victory", "mapId": "greenest_fields"}]
        E.ensure_zone_memory(state, ws)
        intent = E.materialize_next_intent(state, ws)
        assert not intent.get("openingMission") and intent.get("opening") is None
        assert all(not b["id"].startswith("op_") for b in intent["beats"])
        assert "b1_move_out" in [b["id"] for b in intent["beats"]]
        assert all(l.get("tag") != "opening" for l in intent["briefing"]["lines"])


# ---------------------------------------------------------------- the beats in Lua
def test_the_opening_beats_run_in_lua():
    harness = ROOT / "tools" / "hud_harness" / "opening_beats_test.py"
    if not glob.glob('/usr/lib/x86_64-linux-gnu/liblua5.4.so*') or not harness.is_file():
        return  # no Lua here, or a SHIP -Dev tree (the HUD harness stays in the workspace)
    r = subprocess.run([sys.executable, str(harness)], capture_output=True, text=True,
                       env=dict(os.environ, VA_WS=str(ROOT)), timeout=120)
    assert r.returncode == 0 and "FAIL" not in r.stdout, r.stdout + r.stderr


# ---------------------------------------------------------------- the beat sheet
def test_the_beat_sheet_names_every_beat_and_every_tunable():
    doc = (ROOT / "docs" / "MISSION1_OPENING.md").read_text(encoding="utf-8")
    for b in _beats():
        assert f"`{b['id']}`" in doc, f"docs/MISSION1_OPENING.md does not mention {b['id']}"
    for k in O.PACING_KEYS:
        assert f"`{k}`" in doc, f"docs/MISSION1_OPENING.md does not mention pacing.{k}"
