"""Act structure (story pacing only, never a build lock) and the finale plans.

Split out of the single-file story engine in pass ten; the public names are re-exported by
``verdance.campaign`` so ``from verdance.campaign import <name>`` keeps working.
"""
from __future__ import annotations

import copy
from pathlib import Path
from typing import Any, Dict, Optional


# ---------------------------------------------------------------------------
# Act structure (story pacing only — NOT a build lock):
#   Acts still label chapters / finales. Fabrication is unconstrained BAR;
#   Tenebrium + concurrent BP ceiling is the only build-power gate.
# ---------------------------------------------------------------------------

ACT1_END_MISSION = 5
ACT2_END_MISSION = 10

ACT_NAMES = {1: "ground_control", 2: "constrained_rts", 3: "unbound_finale"}
ACT_LABELS = {
    1: "Act I — Opening Front: full fab; Tnb gates constructors",
    2: "Act II — Mid Front: full fab; Tnb gates constructors",
    3: "Act III — The Finale: full unconstrained war, massive starts",
}

# Path-keyed finales on the three designated maps (owner map-pool decision):
# ancient_bastion = overthrow (A), all_that_simmers = sovereignty (B),
# the_rock_jungle = spire jump (C).
FINALE_PLANS = {
    "A": {
        "pathKey": "A",
        "kind": "overthrow",
        "mapId": "ancient_bastion",
        "deploymentZoneId": "AB_E_RIDGE",
        "title": "Finale — Overthrow",
        "objective": {
            "id": "FINALE_OVERTHROW",
            "kind": "destroy_key_structure",
            "label": "Overthrow — break the castle guns and the command post in the Keep",
            "targetZoneId": "AB_W_KEEP",
            "enemyFaction": "armada",
        },
    },
    "B": {
        "pathKey": "B",
        "kind": "sovereignty",
        "mapId": "all_that_simmers",
        "deploymentZoneId": "ATS_NW_SPILLWAY",
        "title": "Finale — Sovereignty",
        "objective": {
            "id": "FINALE_SOVEREIGNTY",
            "kind": "destroy_key_structure",
            "label": "Sovereignty — break both empires' command posts on the simmering ground",
            "targetZoneId": "ATS_NE_PLATEAU",
            "enemyFaction": "armada",
        },
    },
    "C": {
        "pathKey": "C",
        "kind": "spire_jump",
        "mapId": "the_rock_jungle",
        "deploymentZoneId": "TRJ_NW_MUSTER",
        "title": "Finale — Spire Jump",
        "objective": {
            "id": "FINALE_SPIRE_JUMP",
            "kind": "hive_clear_or_bypass",
            "label": "Spire Jump — burn the hive heart and take the spires",
            "targetZoneId": "TRJ_C_INNER_SPILLWAY",
            "enemyFaction": "wild",
        },
    },
}


def act_for_mission(mission_number: int) -> int:
    n = int(mission_number or 1)
    if n <= ACT1_END_MISSION:
        return 1
    if n <= ACT2_END_MISSION:
        return 2
    return 3


def act_profile_for_state(state: Dict[str, Any]) -> Dict[str, Any]:
    n = int(state.get("missionNumber", 1) or 1)
    act = act_for_mission(n)
    return {
        "act": act,
        "name": ACT_NAMES[act],
        "label": ACT_LABELS[act],
        "missionNumber": n,
        "act1EndMission": ACT1_END_MISSION,
        "act2EndMission": ACT2_END_MISSION,
    }


def finale_path_for_state(state: Dict[str, Any]) -> str:
    """The path whose signal leads decides which finale fires; the current
    pathSignal letter breaks ties (deterministic)."""
    graph = state.get("graph", {}) or {}
    current = str(state.get("pathSignal") or "B")
    if current not in FINALE_PLANS:
        current = "B"
    signals = {
        "A": float(graph.get("pathSignalA", 0.0) or 0.0),
        "B": float(graph.get("pathSignalB", 0.0) or 0.0),
        "C": float(graph.get("pathSignalC", 0.0) or 0.0),
    }
    best = max(signals.values())
    leaders = sorted(k for k, v in signals.items() if v >= best - 1e-9)
    if current in leaders:
        return current
    return leaders[0]


def finale_plan_for_state(state: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    if act_for_mission(int(state.get("missionNumber", 1) or 1)) < 3:
        return None
    path = finale_path_for_state(state)
    plan = copy.deepcopy(FINALE_PLANS[path])
    plan["massiveStart"] = True
    plan["pathSignals"] = {
        k: round(float((state.get("graph", {}) or {}).get("pathSignal" + k, 0.0) or 0.0), 3)
        for k in ("A", "B", "C")
    }
    return plan


__all__ = [
    "ACT1_END_MISSION",
    "ACT2_END_MISSION",
    "ACT_LABELS",
    "ACT_NAMES",
    "FINALE_PLANS",
    "act_for_mission",
    "act_profile_for_state",
    "finale_path_for_state",
    "finale_plan_for_state",
]
