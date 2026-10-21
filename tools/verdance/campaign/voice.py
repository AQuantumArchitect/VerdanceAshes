"""Ketha's voice: deterministic, data-driven briefing, debrief and beat lines.

Split out of the single-file story engine in pass ten; the public names are re-exported by
``verdance.campaign`` so ``from verdance.campaign import <name>`` keeps working.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from verdance.common import load_json
from .schema import CAMPAIGN_ID
from .acts import ACT_NAMES, act_for_mission, finale_plan_for_state
from .hydrology import hydrology_beats

# ---------------------------------------------------------------------------
# Ketha voice: data-driven, deterministic dialogue selection.
# Lines live in data/story/ketha_voice.json so the community can retune the
# voice without touching engine code. Selection is hash-seeded (campaign +
# mission + pool) so the same campaign moment always says the same thing.
# ---------------------------------------------------------------------------

FALLBACK_VOICE = {
    "speaker": "ketha",
    "pools": {
        "debrief.victory": ["Done is done. Mark the map and move."],
        "debrief.partial": ["Not a win. Not a loss. A hinge."],
        "debrief.defeat": ["We lost ground, not the thread. But the thread is thinner."],
    },
    "titles": {},
}

_VOICE_CACHE: Dict[str, Dict[str, Any]] = {}


def load_ketha_voice(workspace: Optional[Path]) -> Dict[str, Any]:
    if workspace is None:
        return FALLBACK_VOICE
    key = str(workspace)
    if key in _VOICE_CACHE:
        return _VOICE_CACHE[key]
    path = Path(workspace) / "data" / "story" / "ketha_voice.json"
    voice = FALLBACK_VOICE
    if path.exists():
        try:
            data = load_json(path)
            if isinstance(data, dict) and isinstance(data.get("pools"), dict):
                voice = data
        except (json.JSONDecodeError, OSError):
            pass
    _VOICE_CACHE[key] = voice
    return voice


def pick_line(voice: Dict[str, Any], pool_key: str, *seed_parts: Any) -> Optional[str]:
    pool = voice.get("pools", {}).get(pool_key) or []
    if not pool:
        return None
    digest = hashlib.sha256("|".join([pool_key] + [str(p) for p in seed_parts]).encode("utf-8")).digest()
    return str(pool[digest[0] % len(pool)])


def pick_title(voice: Dict[str, Any], map_id: str, *seed_parts: Any) -> Optional[str]:
    titles = voice.get("titles", {}).get(map_id) or []
    if not titles:
        return None
    digest = hashlib.sha256("|".join([map_id, "title"] + [str(p) for p in seed_parts]).encode("utf-8")).digest()
    return str(titles[digest[0] % len(titles)])


def result_streak(state: Dict[str, Any]) -> Tuple[str, int]:
    """Return (kind, length) of the trailing victory/defeat streak in history."""
    history = state.get("history", []) or []
    streak_kind = ""
    streak = 0
    for bead in reversed(history):
        status = str(bead.get("status", ""))
        kind = "win" if status == "victory" else ("loss" if status in ("defeat", "failed", "failure") else "")
        if not kind:
            break
        if streak_kind and kind != streak_kind:
            break
        streak_kind = kind
        streak += 1
    return streak_kind, streak


def workspace_hint(voice: Dict[str, Any]) -> Optional[Path]:
    """The voice cache is keyed by workspace; recover it so briefing can find outbox."""
    for key, cached in _VOICE_CACHE.items():
        if cached is voice:
            return Path(key)
    return None


def _occasions_briefing_lines(state: Dict[str, Any], workspace: Optional[Path]) -> List[Dict[str, str]]:
    """Briefing lines from outbox/occasions.latest.json when it matches this mission."""
    if workspace is None:
        return []
    path = Path(workspace) / "outbox" / "occasions.latest.json"
    if not path.exists():
        return []
    try:
        occ = json.loads(path.read_text(encoding="utf-8-sig"))
    except Exception:
        return []
    if int(occ.get("missionNumber") or -1) != int(state.get("missionNumber", 1) or 1):
        return []
    out: List[Dict[str, str]] = []
    for row in occ.get("briefing") or []:
        text = str(row.get("text") or "").strip()
        if not text:
            continue
        out.append({"speaker": str(row.get("speaker") or "ketha"), "text": text,
                    "tag": "readings:" + str(row.get("eventClass") or row.get("kind") or "line")})
    return out[:5]


def generate_briefing(state: Dict[str, Any], voice: Dict[str, Any], map_id: str, family: str,
                      objective: Dict[str, Any], pressure: Dict[str, Any],
                      esc_plan: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    seed = (state.get("campaignId", CAMPAIGN_ID), state.get("missionNumber", 1))
    graph = state.get("graph", {})
    comp = state.get("companion", {})
    lines: List[Dict[str, str]] = []

    def add(pool_key: str, tag: str) -> None:
        text = pick_line(voice, pool_key, *seed)
        if text:
            lines.append({"speaker": voice.get("speaker", "ketha"), "text": text, "tag": tag})

    add("briefing.family." + family, "situation")
    # Drop 2: the act is the campaign's chapter voice (ground control /
    # constrained front / finale) — one line, right after the situation.
    mission_num = int(state.get("missionNumber", 1) or 1)
    add("briefing.act." + ACT_NAMES[act_for_mission(mission_num)], "act")
    # Hot raid doctrine: camp not raised yet → Ketha pushes Tnb + extract + home.
    camp = state.get("homeCamp") or {}
    tnb_bank = int((state.get("commerce") or {}).get("tenebrium") or 0)
    if int(camp.get("level") or 0) <= 0 and map_id != str(camp.get("mapId") or "the_rock_jungle"):
        add("briefing.extract_priority", "extract")
    elif tnb_bank < 3 and map_id in ("greenest_fields", "all_that_simmers", "tabula"):
        add("briefing.extract_priority", "extract")
    # Drop 3: finales speak in their path's voice; a fresh recruit gets a nod.
    if act_for_mission(mission_num) >= 3:
        plan = finale_plan_for_state(state)
        if plan:
            add("briefing.finale." + str(plan.get("kind")), "finale")
    joins = state.get("recentHeroJoins") or {}
    if isinstance(joins, dict) and joins.get("names") and int(joins.get("missionNumber") or -1) == mission_num:
        add("briefing.hero_joined", "warband")
    add("briefing.objective." + str(objective.get("kind", "")), "objective")
    # Drop 4: escalation texture — strong objectives and secondary marks each
    # get Ketha's read (raze/purge override the usual "one clean strike" tone).
    esc = esc_plan or {}
    strength = str(esc.get("objectiveStrength") or "")
    if strength in ("raze", "purge"):
        add("briefing." + strength, "escalation")
    esc_secs = esc.get("secondaries") or []
    if any(s.get("required") for s in esc_secs):
        add("briefing.secondary_required", "escalation")
    elif esc_secs:
        add("briefing.secondary_bonus", "escalation")

    # The standing war line: Null Mercs vs Armada is the main conflict, and
    # Ketha reads the mercs by reputation - allied guns or wary neighbors.
    rep = state.get("reputation", {})
    merc_rep = float(rep.get("nullmercs", 43) or 0)
    add("briefing.war.mercs_allied" if merc_rep >= 40 else "briefing.war.mercs_wary", "war")

    # Pillar D: Ketha reacts to the emergent world. A wounded commander and the
    # extremes of the Armada/Cortex axis each earn a line when they hold.
    if (state.get("roster", {}).get("commander", {}) or {}).get("scars"):
        add("briefing.commander.scarred", "warband")
    q0 = float(graph.get("q0_armada_cortex", 0.5) or 0.5)
    if q0 >= 0.62:
        add("briefing.world.cortex_ascendant", "world")
    elif q0 <= 0.38:
        add("briefing.world.armada_ascendant", "world")

    # Readings layer: if the occasions face for this mission exists, the cast's
    # briefing lines (attractor opener + fired event classes) replace the
    # level-triggered pressure line below, which otherwise repeats while an axis
    # stays pinned. Crossings are event classes now, not levels.
    occ_lines = _occasions_briefing_lines(state, workspace_hint(voice))
    if occ_lines:
        # The cast now covers the standing-war read and the new-recruit nod.
        lines[:] = [l for l in lines if l.get("tag") not in ("war", "warband")]
        lines.extend(occ_lines)
        add("briefing.path." + str(state.get("pathSignal", "B")), "path")
        return {"lines": lines}

    # One conditional line: highest-priority campaign pressure wins.
    conditions = [
        (float(comp.get("stress", 0) or 0) >= 40, "briefing.companion.high_stress"),
        (pressure.get("maxHazard", 0) > 0.5, "briefing.hazard.rising"),
        (pressure.get("maxFortification", 0) > 0.55, "briefing.fortress.pressure"),
        (float(graph.get("q7_resource_scarcity", graph.get("q7_scarcity", 0)) or 0) > 0.85, "briefing.graph.scarcity_high"),
        (float(graph.get("q6_contested", 0) or 0) > 0.7, "briefing.graph.contested_high"),
        (float(graph.get("q6_independent", 0) or 0) > 0.45, "briefing.graph.independent_rising"),
        (float(comp.get("morale", 0) or 0) >= 75, "briefing.companion.high_morale"),
    ]
    for triggered, pool_key in conditions:
        if triggered:
            add(pool_key, "pressure")
            break

    add("briefing.path." + str(state.get("pathSignal", "B")), "path")
    return {"lines": lines}


def generate_debrief_candidates(state: Dict[str, Any], voice: Dict[str, Any]) -> Dict[str, str]:
    """Outcome-keyed lines embedded in the mission seed so the in-game HUD can
    react to the terminal state without waiting for campaign advancement."""
    seed = (state.get("campaignId", CAMPAIGN_ID), state.get("missionNumber", 1), "debrief")
    candidates = {}
    for key, pool in [
        ("victory", "debrief.victory"),
        ("victoryClean", "debrief.victory_clean"),
        ("partial", "debrief.partial"),
        ("defeat", "debrief.defeat"),
        ("defeatCommander", "debrief.defeat_commander"),
        ("defeatHero", "debrief.hero_lost"),
        ("objectiveDestroyed", "debrief.objective_destroyed"),
    ]:
        text = pick_line(voice, pool, *seed)
        if text:
            candidates[key] = text
    return candidates


def generate_beats(state: Dict[str, Any], voice: Dict[str, Any], family: str,
                   objective: Dict[str, Any],
                   waterline: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
    """The mission's WC3-style beat script: deterministic per campaign moment,
    authored from the same voice pools as briefings. Markers for objective and
    extraction are placed by the HUD from gadget rules params, so beats carry
    the voice, the mid-fight complication, and the hero moments."""
    seed = (state.get("campaignId", CAMPAIGN_ID), state.get("missionNumber", 1), "beats")
    target_zone = objective.get("targetZoneId")
    beats: List[Dict[str, Any]] = []

    def bark(pool_key: str) -> Optional[Dict[str, Any]]:
        line = pick_line(voice, pool_key, *seed)
        if not line:
            return None
        return {"type": "bark", "speaker": "Ketha", "text": line, "seconds": 7}

    opening = bark("bark.opening." + family)
    if opening:
        beats.append({"id": "b1_move_out", "trigger": {"type": "time", "seconds": 50},
                      "actions": [opening]})
    if target_zone:
        contact = bark("bark.contact." + family)
        if contact:
            beats.append({"id": "b2_contact", "trigger": {"type": "zone_entered", "zoneId": target_zone},
                          "actions": [contact, {"type": "sound", "file": "beep6", "volume": 0.7}]})
    midfight = bark("bark.midfight")
    if midfight:
        beats.append({"id": "b3_midfight", "trigger": {"type": "objective_progress", "atLeast": 0.5},
                      "actions": [midfight]})
    wave_line = bark("bark.wave_warning")
    if wave_line:
        beats.append({"id": "b4_wave", "trigger": {"type": "wave_spawned", "index": 1},
                      "actions": [wave_line]})
    extract_line = bark("bark.extract_order")
    if extract_line:
        beats.append({"id": "b5_run_home", "trigger": {"type": "objective_complete"},
                      "actions": [extract_line]})
    hero_down = bark("bark.hero_down")
    if hero_down:
        beats.append({"id": "b6_hero_down", "trigger": {"type": "hero_down"},
                      "actions": [hero_down]})
    hero_back = bark("bark.hero_recovered")
    if hero_back:
        beats.append({"id": "b7_hero_back", "trigger": {"type": "hero_recovered"},
                      "actions": [hero_back]})
    beats.extend(hydrology_beats(waterline or {}, bark))
    return beats


__all__ = [
    "FALLBACK_VOICE",
    "_VOICE_CACHE",
    "_occasions_briefing_lines",
    "generate_beats",
    "generate_briefing",
    "generate_debrief_candidates",
    "load_ketha_voice",
    "pick_line",
    "pick_title",
    "result_streak",
    "workspace_hint",
]
