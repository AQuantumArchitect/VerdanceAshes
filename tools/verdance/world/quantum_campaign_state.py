#!/usr/bin/env python3
"""Bootstrap the in-BAR quantum campaign state from legacy campaign memory.

This module is intentionally projection-only. Once a playable seed enters BAR,
the synced Lua kernel is the authority for evolution; Python merely persists the
exported snapshot on return.
"""
from __future__ import annotations

import copy
import hashlib
import json
import math
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

from verdance.common import clamp, load_json

SCHEMA = "verdance-quantum-campaign/1.0"
FORMATION_EPM = 5400.0
DEFAULT_MAP_ELOMS = 16384.0


def _stable_hash(payload: Dict[str, Any]) -> str:
    body = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(body.encode("ascii")).hexdigest()[:20]


def _zone_components(zone: Dict[str, Any]) -> Dict[str, float]:
    abstract = zone.get("abstract") or {}
    return {
        "mobile": clamp(abstract.get("militaryPressure")),
        "economy": clamp(abstract.get("economyMomentum")),
        "fortification": clamp(abstract.get("fortification")),
        "hazard": clamp(abstract.get("hazardPressure") or zone.get("hazardPressure")),
        "instability": clamp(abstract.get("instability")),
    }


def _zone_control(zone: Dict[str, Any]) -> str:
    """Ownership label — derived upstream from defensive value only."""
    abstract = zone.get("abstract") or {}
    return str(zone.get("controllingFaction") or abstract.get("control") or "neutral").lower()


def _edge_minutes(edge: Dict[str, Any], nodes: Dict[str, Dict[str, Any]]) -> float:
    if edge.get("travelMinutes") is not None:
        return max(0.5, float(edge["travelMinutes"]))
    kind = str(edge.get("kind") or "same_map")
    cost = max(1.0, float(edge.get("cost") or 1.0))
    if kind == "strategic_link":
        return 12.0 * cost
    a, b = nodes.get(str(edge.get("from"))), nodes.get(str(edge.get("to")))
    if a and b:
        aa, ba = a.get("anchor") or {}, b.get("anchor") or {}
        dx = float(aa.get("x", 0.5)) - float(ba.get("x", 0.5))
        dz = float(aa.get("z", 0.5)) - float(ba.get("z", 0.5))
        distance = math.sqrt(dx * dx + dz * dz) * DEFAULT_MAP_ELOMS
        return max(0.75, distance / FORMATION_EPM)
    return 3.0 * cost


def _factorize(zones: Dict[str, Dict[str, Any]], zone_order: List[str]) -> Dict[str, Any]:
    factions: Dict[str, List[float]] = {}
    masses: Dict[str, float] = {}
    for index, zone_id in enumerate(zone_order):
        zone = zones[zone_id]
        faction = str(zone.get("control") or "neutral")
        if faction == "neutral":
            continue
        vector = factions.setdefault(faction, [0.0] * len(zone_order))
        mass = max(0.0, float(zone.get("mobile") or 0.0))
        mass += 0.55 * float(zone.get("economy") or 0.0)
        mass += 0.75 * float(zone.get("fortification") or 0.0)
        mass += float(zone.get("hazard") or 0.0)
        vector[index] = math.sqrt(max(0.0, mass))
        masses[faction] = masses.get(faction, 0.0) + mass

    names, vectors, weights = [], [], []
    total = sum(masses.values()) or 1.0
    diagonal = [0.0] * len(zone_order)
    for faction in sorted(factions):
        raw = factions[faction]
        norm = math.sqrt(sum(value * value for value in raw)) or 1.0
        vector = [value / norm for value in raw]
        weight = masses[faction] / total
        names.append(faction)
        vectors.append([round(value, 7) for value in vector])
        weights.append(round(weight, 7))
        for index, value in enumerate(vector):
            diagonal[index] += weight * value * value
    purity = sum(weight * weight for weight in weights)
    return {
        "names": names,
        "vectors": vectors,
        "weights": weights,
        "diagonal": [round(value, 7) for value in diagonal],
        "eigenvalues": sorted((round(weight, 7) for weight in weights), reverse=True),
        "purity": round(purity, 7),
    }


def bootstrap(state: Dict[str, Any], workspace: Path) -> Dict[str, Any]:
    existing = state.get("campaignQuantumState")
    if isinstance(existing, dict) and existing.get("schemaVersion") == SCHEMA:
        return copy.deepcopy(existing)

    graph = load_json(Path(workspace) / "data" / "zone_maps" / "world_zone_graph.v1.json")
    graph_nodes = {str(node["zoneId"]): node for node in graph.get("nodes") or [] if node.get("zoneId")}
    zone_order = sorted(graph_nodes)
    zones: Dict[str, Dict[str, Any]] = {}
    memory = state.get("zoneMemory") or {}
    actors = state.get("offscreenActors") or {}
    for zone_id in zone_order:
        node = graph_nodes[zone_id]
        map_id = str(node.get("mapId") or "")
        source = (memory.get(map_id) or {}).get(zone_id) or {}
        components = _zone_components(source)
        zones[zone_id] = {
            "zoneId": zone_id,
            "mapId": map_id,
            "label": node.get("label") or zone_id,
            "control": _zone_control(source),
            "actor": str((actors.get(map_id) or {}).get(zone_id) or "SimpleAI"),
            "anchor": copy.deepcopy(node.get("anchor") or {"x": 0.5, "z": 0.5}),
            **components,
        }

    edges = []
    for index, edge in enumerate(graph.get("edges") or []):
        a, b = str(edge.get("from") or ""), str(edge.get("to") or "")
        if a not in zones or b not in zones:
            continue
        edges.append({
            "id": str(edge.get("id") or f"edge_{index:03d}_{a}_{b}"),
            "from": a,
            "to": b,
            "kind": str(edge.get("kind") or "same_map"),
            "travelMinutes": round(_edge_minutes(edge, graph_nodes), 4),
            "blocked": bool(edge.get("blocked", False)),
        })

    narrative = {
        "pathA": clamp((state.get("graph") or {}).get("pathSignalA")),
        "pathB": clamp((state.get("graph") or {}).get("pathSignalB"), 0.0, 1.0),
        "pathC": clamp((state.get("graph") or {}).get("pathSignalC")),
        "axes": copy.deepcopy(state.get("graph") or {}),
    }
    path_total = narrative["pathA"] + narrative["pathB"] + narrative["pathC"]
    if path_total <= 0:
        narrative.update({"pathA": 0.0, "pathB": 1.0, "pathC": 0.0})
    else:
        for key in ("pathA", "pathB", "pathC"):
            narrative[key] = round(narrative[key] / path_total, 7)

    quantum = {
        "schemaVersion": SCHEMA,
        "clockMinutes": round(float(state.get("campaignClockMinutes") or 0.0), 4),
        "transitionIndex": 0,
        "zoneOrder": zone_order,
        "zones": zones,
        "edges": edges,
        "narrative": narrative,
        "density": _factorize(zones, zone_order),
        "transitQueue": [],
        "transitionJournal": [],
    }
    quantum["stateHash"] = _stable_hash(quantum)
    return quantum


def persist_exported(state: Dict[str, Any], result: Dict[str, Any]) -> bool:
    """Adopt a Lua-authored snapshot without running a competing transition."""
    snapshot = result.get("finalQuantumState")
    if not isinstance(snapshot, dict) or snapshot.get("schemaVersion") != SCHEMA:
        return False
    previous = state.get("campaignQuantumState") or {}
    previous_index = int(previous.get("transitionIndex") or 0)
    snapshot_index = int(snapshot.get("transitionIndex") or 0)
    if snapshot_index < previous_index:
        return False
    journal = snapshot.get("transitionJournal") or []
    if not isinstance(journal, list):
        return False
    indexed = [
        row for row in journal
        if isinstance(row, dict) and int(row.get("transitionIndex") or 0) > previous_index
    ]
    expected = previous_index + 1
    prior_hash = previous.get("stateHash")
    for row in indexed:
        if int(row.get("transitionIndex") or 0) != expected:
            return False
        # The initial bootstrap crosses Python/Lua hash formats. Subsequent
        # transitions must link directly to the persisted Lua snapshot.
        if previous_index > 0 and expected == previous_index + 1 and prior_hash \
                and row.get("beforeHash") != prior_hash:
            return False
        prior_hash = row.get("afterHash")
        expected += 1
    if snapshot_index > previous_index and expected - 1 != snapshot_index:
        return False
    if indexed and indexed[-1].get("afterHash") != snapshot.get("stateHash"):
        return False
    if snapshot_index == previous_index and previous.get("stateHash") not in (
            None, snapshot.get("stateHash")):
        return False
    state["campaignQuantumState"] = copy.deepcopy(snapshot)
    state["campaignClockMinutes"] = round(float(snapshot.get("clockMinutes") or 0.0), 4)
    # Compatibility projection for the hub and older narrative surfaces. These
    # values are views of Lua-authored truth, never a second evolution pass.
    memory = state.setdefault("zoneMemory", {})
    for zone_id, zone in (snapshot.get("zones") or {}).items():
        map_id = str(zone.get("mapId") or "")
        if not map_id:
            continue
        target = memory.setdefault(map_id, {}).setdefault(zone_id, {"zoneId": zone_id})
        target["controllingFaction"] = zone.get("control") or "neutral"
        abstract = target.setdefault("abstract", {})
        abstract["control"] = target["controllingFaction"]
        abstract["militaryPressure"] = clamp(zone.get("mobile"))
        abstract["economyMomentum"] = clamp(zone.get("economy"))
        abstract["fortification"] = clamp(zone.get("fortification"))
        abstract["hazardPressure"] = clamp(zone.get("hazard"))
        abstract["instability"] = clamp(zone.get("instability"))
        target["lastUpdatedCampaignMinute"] = state["campaignClockMinutes"]
        target["confidence"] = "measured" if map_id == result.get("deploymentMapId") else "estimated"
    density = snapshot.get("density") or {}
    state["lastSpectral"] = {
        "dominantEigenvalue": float((density.get("eigenvalues") or [0.0])[0] or 0.0),
        "energy": sum(float(x or 0.0) ** 2 for x in density.get("eigenvalues") or []),
        "participation": len(density.get("names") or []),
        "spread": 1.0 - float(density.get("purity") or 0.0),
        "factionWeights": dict(zip(density.get("names") or [], density.get("weights") or [])),
        "zones": len(snapshot.get("zoneOrder") or []),
        "source": "lua_quantum_kernel",
    }
    narrative = snapshot.get("narrative") or {}
    axes = narrative.get("axes") or {}
    if isinstance(axes, dict):
        state.setdefault("graph", {}).update(copy.deepcopy(axes))
    state["graph"]["pathSignalA"] = float(narrative.get("pathA") or 0.0)
    state["graph"]["pathSignalB"] = float(narrative.get("pathB") or 0.0)
    state["graph"]["pathSignalC"] = float(narrative.get("pathC") or 0.0)
    return True
