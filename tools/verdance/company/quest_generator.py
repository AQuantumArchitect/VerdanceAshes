#!/usr/bin/env python3
"""Quest generator v1 — walk world_zone_graph same_map edges → legal VA-SORTIE candidates.

Kernel only. UI ranking paint is out of scope.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

from verdance.common import WORKSPACE_ROOT, load_json

from verdance.world import zone_graph as wzg
from verdance.belief import hub_belief

WS_DEFAULT = WORKSPACE_ROOT

# Objective archetypes preferred by zone role / tags.
# Drop 4: the authored zone vocabulary is richer than this map used to be —
# causeways, island chains, fortresses, and raptor wilds were ALL falling
# through to the seize_lane default, flattening every board into one kind.
ROLE_ARCHETYPE = {
    "energy_edge": "eco_raid",
    "main_field": "eco_raid",
    "lane": "seize_lane",
    "contested_default": "seize_lane",
    "gate": "gate_control",
    "plateau": "hold_plateau",
    "citadel": "siege",
    "relay": "strike_relay",
    "wild": "survive_wilds",
    "swamp": "multipressure",
    "raptor_wilds": "survive_wilds",
    "raptor_hazard": "survive_wilds",
    "causeway": "gate_control",
    "siege_approach": "gate_control",
    "scar_entrance": "gate_control",
    "approach_lane": "gate_control",
    "island_chain": "hold_plateau",
    "rim_control": "hold_plateau",
    "flank_pocket": "hold_plateau",
    "central_objective": "hold_plateau",
    "fortress": "siege",
    "armada_start": "siege",
    "cortex_start": "siege",
    # Second sweep (zone scorecard, 2026-08-24): these nine roles were still
    # falling through to the seize_lane default across 20 of 45 authored zones.
    "legion_start": "siege",
    "defender_start": "siege",
    "start": "siege",
    "primary_lane": "seize_lane",
    "exposed_crossing": "seize_lane",
    "crossfire_route": "seize_lane",
    "approach_gate": "gate_control",
    "flank_lane": "strike_relay",
    "secondary_route": "strike_relay",
    "reserve": "eco_raid",
    # Hydrology roles (tools/zone_cartographer_v1.py). Ground the campaign's
    # water cycle takes and gives back: a drained basin is a metal rush, a
    # spillway is the pinch the water and the army both come through.
    "basin_floor": "eco_raid",
    "shoreline": "seize_lane",
    "spillway": "gate_control",
}

TAG_ARCHETYPE = {
    "wind": "eco_raid",
    "solar": "eco_raid",
    "economy": "eco_raid",
    "energy": "eco_raid",
    "lane": "seize_lane",
    "gate": "gate_control",
    "relay": "strike_relay",
    "fort": "siege",
    "raptor": "survive_wilds",
    "raptors": "survive_wilds",
    "causeway": "gate_control",
    "islands": "hold_plateau",
}

BLOC = {
    "ashwalkers": "nullmercs",
    "nullmercs": "nullmercs",
    "armada": "armada",
    "cortex": "cortex",
    "wild": "wild",
    "neutral": "neutral",
}

# Drop 3 Wave 3: act-1 objective matrix. Ground-control missions rotate their
# preferred archetype by mission slot so the first act plays raid → seize →
# gate → hold → strike instead of whatever the map's zone roles default to.
# A preference bonus, not a mandate — maps without a matching zone fall back.
ACT1_KIND_ROTATION = {
    1: "eco_raid",
    2: "seize_lane",
    3: "gate_control",
    4: "hold_plateau",
    5: "strike_relay",
}
ACT1_ROTATION_BONUS = 0.9
ANTI_REPEAT_PENALTY = 0.35


# Two perspectives on who holds a zone. "truth" is the engine's own (zoneMemory) and is only for
# building the actual match. "belief" is what the company has seen (hub_belief): anything that
# reaches the player — hub capture contracts, `against` on a card — must come from here.
def _belief_rows(workspace: Optional[Path], state: Dict[str, Any], map_id: str) -> Dict[str, Dict[str, Any]]:
    try:
        return hub_belief.belief_surface(Path(workspace or WS_DEFAULT), state, map_id).get("zones") or {}
    except Exception:
        return {}


def believed_control(state: Dict[str, Any], map_id: str, zone_id: str, workspace: Optional[Path] = None,
                     rows: Optional[Dict[str, Dict[str, Any]]] = None) -> str:
    """ashwalkers | <faction> | held | empty | unknown — never a zoneMemory read."""
    rows = _belief_rows(workspace, state, map_id) if rows is None else rows
    return hub_belief.believed_holder(rows.get(str(zone_id)))


def zone_control(state: Dict[str, Any], map_id: str, zone_id: str, *, perspective: str = "truth",
                 workspace: Optional[Path] = None, rows: Optional[Dict[str, Dict[str, Any]]] = None) -> str:
    if perspective == "belief":
        try:
            word = believed_control(state, map_id, zone_id, workspace, rows)
        except Exception:
            word = "unknown"
        return {"empty": "neutral", "unknown": "neutral"}.get(word, word)
    zm = (state.get("zoneMemory") or {}).get(map_id, {}).get(zone_id, {}) or {}
    return zm.get("controllingFaction") or (zm.get("abstract") or {}).get("control") or "neutral"


def patron_held_zones(state: Dict[str, Any], map_id: str, patron: str, *, perspective: str = "truth",
                      workspace: Optional[Path] = None) -> List[str]:
    bloc = BLOC.get(patron, patron)
    held = []
    rows = _belief_rows(workspace, state, map_id) if perspective == "belief" else None
    for zid, zm in ((state.get("zoneMemory") or {}).get(map_id) or {}).items():
        ctrl = zone_control(state, map_id, str(zid), perspective=perspective, workspace=workspace, rows=rows)
        if BLOC.get(ctrl, ctrl) == bloc:
            held.append(str(zid))
    return sorted(held)


def archetype_for_node(node: Dict[str, Any]) -> str:
    role = str(node.get("role") or "").lower()
    if role in ROLE_ARCHETYPE:
        return ROLE_ARCHETYPE[role]
    for tag in node.get("tags") or []:
        t = str(tag).lower()
        if t in TAG_ARCHETYPE:
            return TAG_ARCHETYPE[t]
    return "seize_lane"


def score_candidate(
    state: Dict[str, Any],
    map_id: str,
    zone_id: str,
    node: Dict[str, Any],
    against: str,
    ctrl: Optional[str] = None,
) -> float:
    """Higher = better next contract. Uses q-scalars + rep lightly."""
    graph = state.get("graph") or {}
    rep = state.get("reputation") or {}
    q6 = float(graph.get("q6_contested") or graph.get("q6_independent") or 0.5)
    q7 = float(graph.get("q7_resource_scarcity") or 0.5)
    score = 1.0
    arch = archetype_for_node(node)
    mission = int(state.get("missionNumber", 1) or 1)
    if ACT1_KIND_ROTATION.get(mission) == arch:
        score += ACT1_ROTATION_BONUS
    # Drop 4: anti-repeat — the same archetype twice in a row reads as filler,
    # so last mission's kind pays a penalty (rotation bonus still outbids it).
    hist = state.get("history") or []
    if hist and isinstance(hist[-1], dict):
        if str(hist[-1].get("objectiveKind") or "") == arch:
            score -= ANTI_REPEAT_PENALTY
    if arch == "eco_raid":
        score += 0.4 + 0.3 * q7  # scarcity pushes scavenger raids
    if arch in ("seize_lane", "hold_plateau", "gate_control"):
        score += 0.3 + 0.4 * q6
    if arch == "strike_relay" and against == "cortex":
        score += 0.5
    merc = float(rep.get("nullmercs") or 0)
    if merc >= 40:
        score += 0.15
    # Prefer not already flipped to nullmercs/ashwalkers
    ctrl = ctrl if ctrl is not None else zone_control(state, map_id, zone_id)
    if BLOC.get(ctrl, ctrl) == "nullmercs":
        score -= 2.0
    if ctrl == "neutral":
        score += 0.1
    tags = [str(t).lower() for t in (node.get("tags") or [])]
    if "primary" in tags or node.get("deployEligible"):
        score += 0.05
    return score


def generate_quests(
    workspace: Path,
    state: Dict[str, Any],
    *,
    map_id: Optional[str] = None,
    patron: str = "nullmercs",
    limit: int = 6,
    from_zone_ids: Optional[List[str]] = None,
    perspective: str = "truth",
) -> List[Dict[str, Any]]:
    """Return ranked legal sortie candidates (same_map only).

    perspective="truth" (engine: build the real match) reads zoneMemory. perspective="belief"
    (anything the hub shows) reads only what the company has seen; `against` is then the believed
    holder or "unknown"."""
    if map_id:
        maps = [wzg.canonical_map_id(map_id)]
    else:
        # Prefer map with current mission footprint; else all maps with holdings.
        cur = None
        # last history map if any
        hist = state.get("history") or []
        if hist and isinstance(hist[-1], dict):
            cur = hist[-1].get("mapId")
        maps = [wzg.canonical_map_id(cur)] if cur else []
        if not maps or not maps[0]:
            full = wzg.load_full_adjacency(workspace)
            maps = sorted(full.keys())

    out: List[Dict[str, Any]] = []
    for mid in maps:
        held = list(from_zone_ids) if from_zone_ids else patron_held_zones(state, mid, patron, perspective=perspective, workspace=workspace)
        rows = _belief_rows(workspace, state, mid) if perspective == "belief" else None
        if not held:
            # Seed from deploy-eligible nodes so fresh campaigns still get options.
            graph = wzg.load_world_zone_graph(workspace) or {}
            for n in graph.get("nodes") or []:
                if wzg.canonical_map_id(n.get("mapId")) == mid and n.get("deployEligible"):
                    held.append(str(n["zoneId"]))
            held = sorted(set(held))[:3]
        if not held:
            continue
        targets = wzg.same_map_contract_candidates(workspace, mid, held)
        adj = wzg.load_map_adjacency(workspace, mid)
        for zid in targets:
            node = wzg.zone_node(workspace, zid) or {"zoneId": zid, "mapId": mid}
            ctrl = zone_control(state, mid, zid, perspective=perspective, workspace=workspace, rows=rows)
            if perspective == "belief":
                against = ctrl if ctrl not in ("neutral", "nullmercs", "ashwalkers") else "unknown"
            else:
                against = ctrl if ctrl not in ("neutral", "nullmercs", "ashwalkers") else "armada"
            if BLOC.get(ctrl, ctrl) == BLOC.get(patron, patron):
                continue  # already held by patron bloc
            # Neighbors among held become fromZoneIds
            nbrs = set(adj.get(zid) or [])
            from_z = sorted(nbrs.intersection(held)) or held[:1]
            arch = archetype_for_node(node)
            sc = score_candidate(state, mid, zid, node, against, ctrl)
            capture_mode = None
            if arch in ("seize_lane", "gate_control", "hold_plateau"):
                capture_mode = "clear_hold_shell"
            out.append({
                "schemaVersion": "verdance-sortie-order/1.0",
                "mapId": mid,
                "targetZoneId": zid,
                "fromZoneIds": from_z,
                "patron": patron,
                "against": against,
                "objectiveArchetype": arch,
                "captureMode": capture_mode,
                "freeTnbMint": False,
                "occupationModel": "living_shell",
                "sessionMode": "same_map",
                "label": node.get("label") or zid,
                "score": round(sc, 4),
                "source": "quest_generator_v1",
                "graphEdgeKind": "same_map",
            })
    out.sort(key=lambda c: (-float(c.get("score") or 0), c.get("mapId") or "", c.get("targetZoneId") or ""))
    return out[: max(1, int(limit))]


def write_quest_batch(workspace: Path, candidates: List[Dict[str, Any]], path: Optional[Path] = None) -> Path:
    out_path = path or (Path(workspace) / "outbox" / "quest_batch.latest.json")
    payload = {
        "schemaVersion": "verdance-quest-batch/1.0",
        "count": len(candidates),
        "candidates": candidates,
    }
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return out_path


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="Generate same-map quest candidates from world_zone_graph")
    ap.add_argument("--workspace", default=str(WS_DEFAULT))
    ap.add_argument("--map", default="", help="Restrict to one mapId (Mode A)")
    ap.add_argument("--patron", default="nullmercs")
    ap.add_argument("--limit", type=int, default=6)
    ap.add_argument("--write", action="store_true", help="Write outbox/quest_batch.latest.json")
    ap.add_argument("--pick", type=int, default=0, help="Also write top N as next_sortie_order.json")
    args = ap.parse_args(argv)
    ws = Path(args.workspace).resolve()
    state = load_json(ws / "state" / "campaign_state.json", {})
    cands = generate_quests(
        ws,
        state,
        map_id=args.map or None,
        patron=args.patron,
        limit=args.limit,
    )
    if args.write or args.pick:
        write_quest_batch(ws, cands)
    if args.pick and cands:
        pick = cands[min(args.pick, len(cands)) - 1] if args.pick > 0 else cands[0]
        order = {k: v for k, v in pick.items() if k not in ("score", "source", "graphEdgeKind", "label")}
        order["valid"] = True
        order["campaignId"] = state.get("campaignId", "verdance_ashes")
        out = ws / "outbox" / "next_sortie_order.json"
        out.write_text(json.dumps(order, indent=2), encoding="utf-8")
        print(f"PICKED → {out}")
    print(json.dumps({"count": len(cands), "candidates": cands}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
