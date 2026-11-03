"""Mission 1's opening: the briefing, the staged objective and the first five minutes.

The script and its one pacing table live in data/escalation/mission1_opening.json. This module
reads that file and writes what the gadget runs: the briefing lines on the infil card, and a
list of beats for luarules/gadgets/include/campaign/beats.lua. The gadget decides nothing here;
it watches for the facts a beat names (a selection, a move order, a hit, a build) and runs the
beat's actions. The beat sheet is docs/MISSION1_OPENING.md.

    from verdance.campaign.opening import load_opening, opening_briefing, opening_beats
"""
from __future__ import annotations

import copy
import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

OPENING_FILE = Path("data") / "escalation" / "mission1_opening.json"
SCHEMA = "verdance-opening/1.0"
# The generic beats the opening's own beats stand in for (voice.generate_beats ids): the
# "move out" bark at 50 s and the contact bark on entering the target zone.
REPLACED_BEATS = ("b1_move_out", "b2_contact")
# Generic beats that keep their place but wait out the first minute (pacing.heroBarksNotBeforeSeconds).
HERO_BEATS = ("b6_hero_down", "b7_hero_back")

PACING_KEYS = (
    "briefingMaxWords", "selectPromptSeconds", "movePromptSeconds", "revealFallbackSeconds",
    "attackPromptSeconds", "answerDelaySeconds", "probeSeconds", "buildPromptSeconds",
    "wreckMarkSeconds", "reliefLineDelaySeconds", "paviseLineDelaySeconds", "hookSeconds",
    "hookReplySeconds", "columnSeconds", "heroBarksNotBeforeSeconds", "promptShowSeconds",
    "lineShowSeconds", "dispatchShowSeconds", "goalRingRadius", "goalStopShort", "goalMinFromPad", "wreckRingRadius",
)
LINE_KEYS = (
    "selectPrompt", "movePrompt", "reveal", "attackPrompt", "answer", "probe", "buildPrompt",
    "relief", "pavise", "hookDispatch", "hookReply", "hookReplyTaken", "column",
)

_CACHE: Dict[str, Optional[Dict[str, Any]]] = {}


def load_opening(workspace: Optional[Path]) -> Optional[Dict[str, Any]]:
    """The opening script, or None when the file is missing or broken (the generic beats run)."""
    if workspace is None:
        return None
    path = Path(workspace) / OPENING_FILE
    key = str(path)
    if key in _CACHE:
        return _CACHE[key]
    data: Optional[Dict[str, Any]] = None
    if path.is_file():
        try:
            raw = json.loads(path.read_text(encoding="utf-8-sig"))
            if isinstance(raw, dict) and not problems(raw):
                data = raw
            else:
                print("VA_OPENING_INVALID " + "; ".join(problems(raw) if isinstance(raw, dict) else ["not an object"]))
        except (OSError, json.JSONDecodeError) as e:
            print(f"VA_OPENING_UNREADABLE {e}")
    _CACHE[key] = data
    return data


def applies(script: Dict[str, Any], state: Dict[str, Any], sortie: Optional[Dict[str, Any]], map_id: str,
            deploy_zone: Optional[str], target_zone: Optional[str]) -> bool:
    """Is this sortie the one the script is for? The authored opening order says so itself
    (openingMission). A deploy the hub stamped carries no such flag, so it is matched on what the
    script names in appliesTo: the mission, a fresh campaign, the map, the pad and the target."""
    if (sortie or {}).get("openingMission"):
        return True
    want = script.get("appliesTo") or {}
    if not want:
        return False
    if int(state.get("missionNumber", 1) or 1) != int(want.get("missionNumber", 1)):
        return False
    if want.get("freshCampaign") and state.get("history"):
        return False
    for key, have in (("mapId", map_id), ("deploymentZoneId", deploy_zone), ("targetZoneId", target_zone)):
        if want.get(key) and str(want[key]) != str(have or ""):
            return False
    return True


def problems(script: Dict[str, Any]) -> List[str]:
    """What is missing from a script. Empty means the hub can build the opening from it."""
    out: List[str] = []
    pacing = script.get("pacing") or {}
    for k in PACING_KEYS:
        if not isinstance(pacing.get(k), (int, float)):
            out.append(f"pacing.{k} missing")
    lines = script.get("lines") or {}
    for k in LINE_KEYS:
        row = lines.get(k) or {}
        if not str(row.get("text") or "").strip():
            out.append(f"lines.{k} missing")
    if not script.get("briefing"):
        out.append("briefing missing")
    card = script.get("card") or {}
    for k in ("firstGoal", "missionGoal", "pauseLine"):
        if not str(card.get(k) or "").strip():
            out.append(f"card.{k} missing")
    return out


def words(text: str) -> int:
    return len(re.findall(r"[\w'’-]+", str(text or "")))


def card_words(script: Dict[str, Any]) -> int:
    """Words read before control is handed over: the briefing, the first goal and the pause line."""
    card = script.get("card") or {}
    n = sum(words(row.get("text", "")) for row in script.get("briefing") or [])
    return n + words(card.get("firstGoal", "")) + words(card.get("pauseLine", ""))


def opening_briefing(script: Dict[str, Any]) -> Dict[str, Any]:
    """The infil card's lines. Tagged 'opening' so the card shows these and nothing appended later."""
    return {"lines": [{"speaker": str(row.get("speaker") or "ketha"), "text": str(row["text"]), "tag": "opening"}
                      for row in script.get("briefing") or [] if str(row.get("text") or "").strip()]}


def _zone(workspace: Optional[Path], map_id: str, zone_id: Optional[str]) -> Dict[str, Any]:
    if workspace is not None and map_id and zone_id:
        path = Path(workspace) / "data" / "zone_maps" / "authored" / f"{map_id}.authored.zone_map.json"
        try:
            for z in json.loads(path.read_text(encoding="utf-8-sig")).get("zones") or []:
                if z.get("zoneId") == zone_id:
                    return z
        except (OSError, json.JSONDecodeError):
            pass
    return {}


def _zone_label(workspace: Optional[Path], map_id: str, zone_id: str) -> str:
    return str(_zone(workspace, map_id, zone_id).get("label") or zone_id or "the objective")


def farm_point(pockets: List[Dict[str, Any]], workspace: Optional[Path], map_id: str, pad_zone: Optional[str],
               target_zone: Optional[str]) -> Optional[Dict[str, float]]:
    """The nearest farm to the pad: the living-shell pocket in the target zone closest to the pad's
    anchor (normalised x/z). The first goal is set short of it, on the line from the pad."""
    anchor = _zone(workspace, map_id, pad_zone).get("anchor") or {}
    try:
        px, pz = float(anchor["x"]), float(anchor["z"])
    except (KeyError, TypeError, ValueError):
        return None
    best = None
    for p in pockets or []:
        if p.get("zoneId") != target_zone:
            continue
        c = p.get("center") or [p.get("x"), p.get("z")]
        try:
            x, z = float(c[0]), float(c[1])
        except (TypeError, ValueError, IndexError):
            continue
        d = (x - px) ** 2 + (z - pz) ** 2
        if best is None or d < best[0]:
            best = (d, x, z)
    return {"x": round(best[1], 4), "z": round(best[2], 4)} if best else None


def opening_card(script: Dict[str, Any], workspace: Optional[Path], map_id: str, target_zone: str) -> Dict[str, Any]:
    """What the infil card and the rail say in place of the job text while the job is staged."""
    card = script["card"]
    return {
        "staged": True,
        "firstGoal": card["firstGoal"],
        "missionGoal": card["missionGoal"].replace("{target}", _zone_label(workspace, map_id, target_zone)),
        "pauseLine": card["pauseLine"],
        "cardWords": card_words(script),
        "source": OPENING_FILE.as_posix(),
    }


def opening_beats(script: Dict[str, Any], target_zone: Optional[str], mission_goal: str,
                  farm: Optional[Dict[str, float]] = None) -> List[Dict[str, Any]]:
    """The opening's beats, minute 0 to about minute 7. Every number comes from script['pacing'].
    farm: the nearest farm (farm_point); without one the first goal is set toward the objective."""
    P = script["pacing"]
    L = script["lines"]
    F = script.get("forces") or {}

    def bark(key: str, priority: str, seconds_key: str, accent: Optional[str] = None) -> Dict[str, Any]:
        row = L[key]
        out = {"type": "bark", "speaker": row.get("speaker") or "Ketha", "text": row["text"],
               "seconds": P[seconds_key], "priority": priority, "tag": "op_" + key}
        if accent:
            out["accent"] = accent
        if row.get("onlyIfHero"):
            out["onlyIfHero"] = row["onlyIfHero"]
        return out

    def prompt(key: str) -> Dict[str, Any]:
        return bark(key, "prompt", "promptShowSeconds")

    def line(key: str) -> Dict[str, Any]:
        return bark(key, "line", "lineShowSeconds")

    def spawn(force: str) -> Dict[str, Any]:
        out = {"type": "spawn", "team": "enemy", "units": copy.deepcopy(F.get(force) or []), "fightTo": "player"}
        if target_zone:
            out["zoneId"] = target_zone
        return out

    def after(seconds_key: str) -> Dict[str, Any]:
        return {"type": "elapsed", "seconds": P[seconds_key]}

    first = {"type": "objective_stage", "stage": 1, "label": script["card"]["firstGoal"], "at": "overlook",
             "stopShort": P["goalStopShort"], "minFromPad": P["goalMinFromPad"], "radius": P["goalRingRadius"]}
    if farm:
        first["towardX"], first["towardZ"] = farm["x"], farm["z"]
    beats: List[Dict[str, Any]] = [
        # Before the first frame: the job is staged. The card, the rail and the board show the first
        # goal (a gold ring a little way off the pad); the real job waits for footing.
        {"id": "op_stage_first", "trigger": {"type": "sortie_start"},
         "actions": [first]},
        # The opening's clock starts when the company is on the field and the game runs.
        {"id": "op_land", "trigger": {"type": "company_landed"}, "actions": []},
        # SELECT. The company waits on the pad, ringed, until somebody takes it.
        {"id": "op_select_prompt", "afterBeat": "op_land", "trigger": after("selectPromptSeconds"),
         "cancelIf": [{"type": "player_selected"}], "actions": [prompt("selectPrompt")]},
        {"id": "op_selected", "afterBeat": "op_land", "trigger": {"type": "player_selected"},
         "actions": [{"type": "clear_bark", "tag": "op_selectPrompt"}]},
        # MOVE. The gold ring is the reason to move.
        {"id": "op_move_prompt", "afterBeat": "op_selected", "trigger": after("movePromptSeconds"),
         "cancelIf": [{"type": "player_moved"}], "actions": [prompt("movePrompt")]},
        {"id": "op_moved", "afterBeat": "op_land", "trigger": {"type": "player_moved"},
         "actions": [{"type": "clear_bark", "tag": "op_movePrompt"}]},
        # Footing: someone reached the ring (or enough time went by). The real job is revealed.
        {"id": "op_reveal", "afterBeat": "op_land",
         "trigger": {"type": "any_of", "of": [{"type": "near_point", "at": "goal", "radius": P["goalRingRadius"]},
                                               after("revealFallbackSeconds")]},
         "actions": [{"type": "objective_stage", "stage": 2, "label": mission_goal},
                     {"type": "sound", "file": "beep6", "volume": 0.8}, line("reveal")]},
        # ATTACK. The farm is in view; the prompt only if nothing of theirs has been hit.
        {"id": "op_attack_prompt", "afterBeat": "op_reveal", "trigger": after("attackPromptSeconds"),
         "cancelIf": [{"type": "player_attacked"}], "actions": [prompt("attackPrompt")]},
        {"id": "op_attacked", "afterBeat": "op_land", "trigger": {"type": "player_attacked"},
         "actions": [{"type": "clear_bark", "tag": "op_attackPrompt"}]},
        # The enemy answers what the player did: our first hit calls the farm's help. Not before the
        # reveal: a fight on a hot pad in the first seconds must not snowball minute one.
        {"id": "op_answer", "afterBeat": ["op_attacked", "op_reveal"], "trigger": after("answerDelaySeconds"),
         "actions": [spawn("answer"), line("answer")]},
        # ... and a company that sits still gets visited.
        {"id": "op_probe", "afterBeat": "op_reveal", "trigger": after("probeSeconds"),
         "cancelIf": [{"type": "player_attacked"}], "actions": [spawn("probe"), line("probe")]},
        # BUILD. Our first kill leaves a wreck; a ring marks it. Builders reclaim or raise it.
        {"id": "op_first_kill", "afterBeat": "op_land", "trigger": {"type": "enemy_killed", "atLeast": 1},
         "actions": [{"type": "field_mark", "id": "op_wreck", "at": "last_kill", "shape": "wreck", "radius": P["wreckRingRadius"],
                      "seconds": P["wreckMarkSeconds"]},
                     {"type": "sound", "file": "beep4", "volume": 0.6}]},
        {"id": "op_build_prompt", "afterBeat": "op_first_kill", "trigger": after("buildPromptSeconds"),
         "cancelIf": [{"type": "player_built"}], "actions": [prompt("buildPrompt")]},
        {"id": "op_built", "afterBeat": "op_first_kill", "trigger": {"type": "player_built", "fresh": True},
         "actions": [{"type": "clear_mark", "id": "op_wreck"}, {"type": "clear_bark", "tag": "op_buildPrompt"}]},
        # Relief: the first haul.
        {"id": "op_relief", "afterBeat": "op_built", "trigger": after("reliefLineDelaySeconds"),
         "actions": [line("relief")]},
        {"id": "op_pavise", "afterBeat": "op_relief", "trigger": after("paviseLineDelaySeconds"),
         "actions": [line("pavise")]},
        # The hook that ends minute five: the Armada names the commander, and a column is coming.
        # Sooner if the farm falls first (losing it is what makes them call); Ketha's reply follows
        # what is true by then: finish the farm, or get to the pad.
        {"id": "op_hook", "afterBeat": "op_land",
         "trigger": {"type": "any_of", "of": [after("hookSeconds"), {"type": "objective_complete"}]},
         "actions": [bark("hookDispatch", "line", "dispatchShowSeconds", accent="warn"),
                     {"type": "sound", "file": "warning2", "volume": 0.6}]},
        {"id": "op_hook_reply", "afterBeat": "op_hook", "trigger": after("hookReplySeconds"),
         "cancelIf": [{"type": "objective_complete"}], "actions": [line("hookReply")]},
        {"id": "op_hook_reply_taken", "afterBeat": "op_hook",
         "trigger": {"type": "all_of", "of": [after("hookReplySeconds"), {"type": "objective_complete"}]},
         "cancelIf": [{"type": "beat_fired", "beat": "op_hook_reply"}], "actions": [line("hookReplyTaken")]},
        # The column pays the hook off, unless the farm is already taken (then the gadget's own
        # hot-extraction answer is the column).
        {"id": "op_column", "afterBeat": "op_hook", "trigger": after("columnSeconds"),
         "cancelIf": [{"type": "objective_complete"}], "actions": [spawn("column"), line("column")]},
    ]
    return beats


def merge_opening_beats(script: Dict[str, Any], generic: List[Dict[str, Any]], target_zone: Optional[str],
                        mission_goal: str, farm: Optional[Dict[str, float]] = None) -> List[Dict[str, Any]]:
    """The opening's beats, then the generic ones it keeps (midfight, the wave, the run home, heroes)."""
    wait = script["pacing"]["heroBarksNotBeforeSeconds"]
    kept = []
    for b in generic:
        if b.get("id") in REPLACED_BEATS:
            continue
        b = copy.deepcopy(b)
        if b.get("id") in HERO_BEATS:
            b["notBefore"] = wait
        kept.append(b)
    return opening_beats(script, target_zone, mission_goal, farm) + kept


__all__ = [
    "HERO_BEATS", "LINE_KEYS", "OPENING_FILE", "PACING_KEYS", "REPLACED_BEATS", "applies", "card_words", "farm_point",
    "load_opening", "merge_opening_beats", "opening_beats", "opening_briefing", "opening_card", "problems", "words",
]
