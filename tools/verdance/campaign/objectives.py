"""Objectives, the front summary, the war map and where the next sortie lands.

Split out of the single-file story engine in pass ten; the public names are re-exported by
``verdance.campaign`` so ``from verdance.campaign import <name>`` keeps working.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from verdance.common import WORKSPACE_ROOT, canonical_map_id, clamp, load_json, utc_now
from .schema import ALPHA_SPINE, CAMPAIGN_ID, MAP_DISPLAY, map_family, zone_maps_from_workspace
from .zones import canonical_zone_id
from .hydrology import update_hydrology_bloom
from .measure import expected_presence_band
from verdance.world import landing_zones as _lz, wet_reach as _wet
from verdance.world.zone_graph import load_map_adjacency as _wzg_load_map_adjacency

def update_destroyed_objectives(state: Dict[str, Any], result: Dict[str, Any]) -> None:
    map_id = canonical_map_id(result.get("deploymentMapId") or result.get("mapId"))
    if map_id == "unknown":
        return
    destroyed = state.setdefault("destroyedObjectives", {}).setdefault(map_id, {})
    zone_id = result.get("deploymentZoneId") or "unknown_zone"
    for oid in result.get("destroyedObjectiveIds", []) or []:
        destroyed[str(oid)] = {
            "objectiveId": str(oid),
            "zoneId": zone_id,
            "destroyedAtMinute": state.get("campaignClockMinutes", 0.0),
            "status": "destroyed",
        }


def reset_live_raptors_but_escalate(state: Dict[str, Any], result: Dict[str, Any], elapsed: float,
                                    workspace: Optional[Path] = None) -> None:
    map_id = canonical_map_id(result.get("deploymentMapId") or result.get("mapId"))
    if map_family(map_id) != "wild":
        return
    bloom = update_hydrology_bloom(state, map_id, workspace)
    hazard_map = state.setdefault("hazardState", {}).setdefault(map_id, {})
    destroyed = set(result.get("destroyedObjectiveIds", []) or [])
    for zone_id, hazard in hazard_map.items():
        hive_destroyed = any(zone_id.lower() in str(oid).lower() or "hive" in str(oid).lower() for oid in destroyed)
        if hive_destroyed:
            hazard["hivesSurviving"] = False
            hazard["pressure"] = clamp(float(hazard.get("pressure", 0.0)) * 0.55)
        else:
            hazard["pressure"] = clamp(float(hazard.get("pressure", 0.0)) + 0.01 * elapsed * (1.0 + bloom))
        hazard["liveUnitsReset"] = True
        hazard["lastResetAtMinute"] = state.get("campaignClockMinutes", 0.0)


def append_history_bead(state: Dict[str, Any], result: Dict[str, Any], elapsed: float, graph_delta: Dict[str, float]) -> Dict[str, Any]:
    bead = {
        "missionId": result.get("missionId", state.get("currentMissionId", "va_unknown")),
        "missionNumber": int(result.get("missionNumber", state.get("missionNumber", 1))),
        "status": result.get("status", "unknown"),
        "mapId": canonical_map_id(result.get("deploymentMapId") or result.get("mapId")),
        "deploymentZoneId": result.get("deploymentZoneId"),
        "extractionStatus": result.get("extractionStatus"),
        "extractionZoneId": result.get("extractionZoneId"),
        "elapsedMinutes": elapsed,
        "pathSignal": result.get("pathSignal") or state.get("pathSignal", "B"),
        "graphDelta": graph_delta,
        "destroyedObjectiveIds": list(result.get("destroyedObjectiveIds", []) or []),
        # Drop 4: the kind played, so the quest board can avoid repeating it.
        "objectiveKind": (
            result.get("objectiveArchetype")
            or ((result.get("objectiveTarget") or {}).get("kind")
                if isinstance(result.get("objectiveTarget"), dict) else None)
            or next((str(o.get("kind")) for o in (result.get("objectiveResults") or [])
                     if isinstance(o, dict) and o.get("kind")), None)
        ),
        "storyTags": story_tags_for_result(result, graph_delta),
        "timestamp": utc_now(),
    }
    state.setdefault("history", []).append(bead)
    return bead


def story_tags_for_result(result: Dict[str, Any], graph_delta: Dict[str, float]) -> List[str]:
    tags = [str(result.get("status", "unknown"))]
    if result.get("extractionStatus"):
        tags.append("extract-" + str(result["extractionStatus"]))
    if result.get("destroyedObjectiveIds"):
        tags.append("objective-destroyed")
    if result.get("pathSignal"):
        tags.append("path-" + str(result["pathSignal"]).lower())
    if graph_delta.get("q6_independent", 0) > 0:
        tags.append("ashwalker-gain")
    return tags


def objective_for_map(map_id: str, state: Dict[str, Any],
                      workspace: Optional[Path] = None) -> Dict[str, Any]:
    """Fallback objective for a map, with its target zone id translated forward.

    Every targetZoneId below was authored against a pre-migration zone cut and
    all seven are now retired -- AB_LRPC_EAST_WING, RJ_CENTRAL_LAGOON_MAZE,
    ATS_CENTRAL_HIVE_FLATS, GF_SE_ENERGY_WORKS, EOH_SE_CORTEX_POCKET,
    KOOM_CENTRAL_FLUID_SCAR, TAB_WESTERN_ROCK_GATES. Rather than hand-edit the
    constants on every re-cut (which is what let them go stale in the first
    place), they are translated at the point of use through the same migration
    map canonical_zone_id already reads.

    This path only fires when generate_mode_a_sortie finds no legal contract,
    so it will not show up in an early mission and will show up in a late one.
    """
    raw = _objective_for_map_raw(map_id, state)
    target = raw.get("targetZoneId")
    if target:
        raw["targetZoneId"] = canonical_zone_id(target, workspace)
    return raw


def _objective_for_map_raw(map_id: str, state: Dict[str, Any]) -> Dict[str, Any]:
    mid = canonical_map_id(map_id)
    destroyed = state.get("destroyedObjectives", {}).get(mid, {})
    if mid == "ancient_bastion":
        candidates = [
            ("AB_LRPC_EAST_WING", "Destroy the eastern LRPC"),
            ("AB_OUTER_WALL_NORTH", "Break the northern bastion wing"),
            ("AB_SHIELD_RELAY", "Collapse the shield relay"),
        ]
        for oid, label in candidates:
            if oid not in destroyed:
                return {"id": oid, "kind": "destroy_key_structure", "label": label, "targetZoneId": "AB_EASTERN_BASTION_WALL"}
    if mid == "the_rock_jungle":
        return {"id": "RJ_HIVE_CAUSEWAY", "kind": "hive_clear_or_bypass", "label": "Break a hive or hold a causeway", "targetZoneId": "RJ_CENTRAL_LAGOON_MAZE"}
    if mid == "all_that_simmers":
        return {"id": "ATS_HIVE_OR_FACTION_TARGET", "kind": "choose_target_then_extract", "label": "Choose Armada, Cortex, or hive pressure target", "targetZoneId": "ATS_CENTRAL_HIVE_FLATS"}
    if mid == "greenest_fields":
        return {"id": "GF_ARMADA_ENERGY_WORKS", "kind": "eco_raid", "label": "Raid the Armada energy works", "targetZoneId": "GF_SE_ENERGY_WORKS", "enemyFaction": "armada"}
    if mid == "eye_of_horus":
        return {"id": "EOH_CORTEX_DEALER_RELAY", "kind": "strike_relay", "label": "Destroy the Cortex dealer relay", "targetZoneId": "EOH_SE_CORTEX_POCKET", "enemyFaction": "cortex"}
    if mid == "koom_valley":
        return {"id": "KOOM_FLUID_SCAR_FOOTHOLD", "kind": "seize_lane", "label": "Seize the Central Fluid Scar", "targetZoneId": "KOOM_CENTRAL_FLUID_SCAR"}
    if mid == "tabula":
        return {"id": "TAB_ROCK_GATE_CONTROL", "kind": "gate_control", "label": "Control a rock gate and extract", "targetZoneId": "TAB_WESTERN_ROCK_GATES"}
    return {"id": mid + "_objective", "kind": "sortie", "label": "Complete local objective", "targetZoneId": None}


def choose_next_map_zone(state: Dict[str, Any],
                         workspace: Optional[Path] = None) -> Tuple[str, str]:
    """Map and deployment zone for the next mission, zone id translated forward.

    ALPHA_SPINE may still name legacy ids that migrate forward
    (EOH_NW_CRATER_CAMP, KOOM_NW_GREEN_SHELF, …). It is the deployment-zone
    source for every mission whose intent does not specify one.
    nextMapOverride is authored too, so it goes through the same translation
    rather than being trusted.
    """
    requested = state.get("nextMapOverride")
    if requested:
        return (canonical_map_id(requested.get("mapId")),
                canonical_zone_id(requested.get("deploymentZoneId", "unknown_zone"), workspace))
    # Mission number is the act clock. Geography is the collapse, then the
    # landing a heading extract already wrote. ALPHA_SPINE is not a map picker.
    try:

        arrival = _wet._arrival(state)
        if arrival and arrival.get("mapId") and arrival.get("zoneId"):
            return (
                canonical_map_id(arrival.get("mapId")),
                canonical_zone_id(arrival.get("zoneId"), workspace),
            )
        if workspace is not None:
            collapsed = _wet.collapse_sorties(state, Path(workspace))
            cards = collapsed.get("cards") or []
            if cards:
                effect = cards[0].get("effect") or {}
                return (
                    canonical_map_id(effect.get("mapId")),
                    canonical_zone_id(effect.get("infilZoneId") or "TRJ_NW_OUTER_MUSTER", workspace),
                )
    except Exception:
        pass
    return "the_rock_jungle", canonical_zone_id("TRJ_NW_OUTER_MUSTER", workspace)


def dominant_faction(control_counts: Dict[str, int]) -> str:
    """The faction that holds a region for War Map coloring: the strict leader
    among real factions (neutral ignored); ties or empty read as 'contested'."""
    factions = {k: v for k, v in control_counts.items() if k and k != "neutral"}
    if not factions:
        return "neutral"
    ranked = sorted(factions.items(), key=lambda kv: kv[1], reverse=True)
    if len(ranked) > 1 and ranked[0][1] == ranked[1][1]:
        return "contested"
    return ranked[0][0]


def threat_band(center: float) -> str:
    if center < 4000:
        return "light"
    if center < 9000:
        return "standard"
    if center < 16000:
        return "reinforced"
    return "heavy"


def summarize_front(state: Dict[str, Any], map_id: str) -> Dict[str, Any]:
    """A map's strategic picture from zone memory: who holds it, how hot it is,
    and whether clan ground there is eroding."""
    mid = canonical_map_id(map_id)
    zones = state.get("zoneMemory", {}).get(mid, {})
    control_counts: Dict[str, int] = {}
    threat_center = 0.0
    max_encroach = 0.0
    ashwalker_zones = 0
    for zone_mem in zones.values():
        ctrl = zone_mem.get("controllingFaction") or zone_mem.get("abstract", {}).get("control") or "neutral"
        control_counts[ctrl] = control_counts.get(ctrl, 0) + 1
        if ctrl == "ashwalkers":
            ashwalker_zones += 1
            max_encroach = max(max_encroach, float(zone_mem.get("encroachment", 0.0) or 0.0))
        else:
            band = expected_presence_band(mid, zone_mem)
            threat_center = max(threat_center, float(band.get("center", 0.0)))
    # Dominant enemy faction (ignore player/neutral) for "who's pushing here".
    enemy_counts = {k: v for k, v in control_counts.items() if k in ("armada", "cortex", "nullmercs", "wild")}
    dominant_enemy = max(enemy_counts.items(), key=lambda kv: kv[1])[0] if enemy_counts else None
    name, descriptor = MAP_DISPLAY.get(mid, (mid, ""))
    return {
        "mapId": mid,
        "displayName": name,
        "descriptor": descriptor,
        "family": map_family(mid),
        "controlCounts": control_counts,
        "dominantEnemy": dominant_enemy,
        "threatCenter": int(threat_center),
        "threatBand": threat_band(threat_center),
        "ashwalkerZones": ashwalker_zones,
        "maxEncroachment": round(max_encroach, 3),
        "atRisk": max_encroach >= 0.5,
    }


def consequence_note(front: Dict[str, Any]) -> str:
    """One line on what happens if the player ignores this front."""
    if front.get("atRisk"):
        loser = front.get("dominantEnemy") or "the enemy"
        return "Clan ground here is eroding — leave it and {} takes a zone.".format(loser)
    fam = front.get("family")
    if fam == "wild":
        return "Hives keep multiplying — the hazard only grows the longer it waits."
    dom = front.get("dominantEnemy")
    if dom == "armada":
        return "Armada keeps entrenching — every mission skipped means heavier walls."
    if dom == "cortex":
        return "The Cortex works keep humming — their economy compounds untouched."
    if dom == "nullmercs":
        return "The mercs hold, but an unpaid line drifts if you never show."
    return "Pressure keeps building here while your attention is elsewhere."


def enumerate_front_targets(state: Dict[str, Any], limit: int = 3,
                            workspace: Optional[Path] = None) -> List[Dict[str, Any]]:
    """The collapsed doors, lean first. Mission number does not pick a map."""
    limit = max(1, min(int(limit or 3), 4))
    cards: List[Dict[str, Any]] = []
    try:

        root = workspace or WORKSPACE_ROOT
        cards = list((_wet.collapse_sorties(state, root).get("cards")) or [])
    except Exception:
        cards = []
    seen: List[str] = []
    fronts = []
    lean_map = None
    for card in cards:
        effect = card.get("effect") or {}
        map_id = canonical_map_id(effect.get("mapId"))
        if not map_id or map_id in seen:
            continue
        seen.append(map_id)
        if card.get("recommended") and lean_map is None:
            lean_map = map_id
        front = summarize_front(state, map_id)
        front["deploymentZoneId"] = effect.get("infilZoneId")
        front["objective"] = {
            "kind": effect.get("contractKind"),
            "label": card.get("label"),
        }
        front["recommended"] = bool(card.get("recommended"))
        front["consequenceIfIgnored"] = consequence_note(front)
        fronts.append(front)
        if len(fronts) >= limit:
            break
    if lean_map is None and fronts:
        fronts[0]["recommended"] = True
    return fronts


def build_war_map(state: Dict[str, Any]) -> Dict[str, Any]:
    """The strategic snapshot the console renders during the next-ready pause:
    faction control per region, the offered fronts, and recent territory swings."""
    regions = []
    for map_id, _ in ALPHA_SPINE:
        front = summarize_front(state, map_id)
        front["control"] = dominant_faction(front.get("controlCounts", {}))
        regions.append(front)
    return {
        "schemaVersion": "verdance-war-map/1.0",
        "campaignId": state.get("campaignId", CAMPAIGN_ID),
        "missionNumber": int(state.get("missionNumber", 1)),
        "generatedAt": utc_now(),
        "regions": regions,
        "candidates": enumerate_front_targets(state),
        "frontEvents": list(state.get("frontEvents", []))[-6:],
        "reputation": dict(state.get("reputation", {}) or {}),
        "voidThreat": round(float(state.get("graph", {}).get("q2_void_structure", 0.0) or 0.0), 3),
        "graph": {k: round(float(v), 3) for k, v in (state.get("graph", {}) or {}).items() if isinstance(v, (int, float))},
        "worldReading": world_reading(state.get("graph", {}) or {}),
        "pendingChoice": state.get("nextMapOverride"),
    }


def world_reading(graph: Dict[str, Any]) -> List[str]:
    """Plain-English readout of the quantum graph for the War Map header."""
    q0 = float(graph.get("q0_armada_cortex", 0.5) or 0.5)
    q2 = float(graph.get("q2_void_structure", 0.0) or 0.0)
    q6c = float(graph.get("q6_contested", 0.5) or 0.5)
    q6i = float(graph.get("q6_independent", 0.0) or 0.0)
    q7 = float(graph.get("q7_resource_scarcity", 0.0) or 0.0)
    lines = []
    if q0 >= 0.6:
        lines.append("Cortex is ascendant across the front.")
    elif q0 <= 0.4:
        lines.append("Armada holds the upper hand.")
    else:
        lines.append("Armada and Cortex are deadlocked.")
    lines.append(("The line-world is tearing apart." if q6c > 0.7 else "The front is holding, for now.") )
    if q6i >= 0.45:
        lines.append("Ashwalker sovereignty is rising.")
    elif q6i <= 0.2:
        lines.append("The clans are a fringe force.")
    if q7 > 0.85:
        lines.append("Tenebrium is all but gone — scarcity bites.")
    if q2 > 0.5:
        lines.append("The void is bleeding through — verge zones destabilizing.")
    return lines


def zone_pressure_summary(state: Dict[str, Any], map_id: str) -> Dict[str, Any]:
    zones = state.get("zoneMemory", {}).get(map_id, {})
    if not zones:
        return {"maxHazard": 0.0, "maxFortification": 0.0, "maxMilitary": 0.0, "zones": []}
    bits = []
    max_hazard = 0.0
    max_fort = 0.0
    max_mil = 0.0
    for zone_id, zone in zones.items():
        abstract = zone.get("abstract", {})
        max_hazard = max(max_hazard, float(abstract.get("hazardPressure", 0.0) or 0.0))
        max_fort = max(max_fort, float(abstract.get("fortification", 0.0) or 0.0))
        max_mil = max(max_mil, float(abstract.get("militaryPressure", 0.0) or 0.0))
        bits.append({
            "zoneId": zone_id,
            "label": zone.get("label", zone_id),
            "control": abstract.get("control", zone.get("controllingFaction")),
            "confidence": zone.get("confidence", "estimated"),
            "expectedPresenceBand": expected_presence_band(map_id, zone),
            "abstract": {
                "baseStrength": round(float(abstract.get("baseStrength", 0.0)), 3),
                "militaryPressure": round(float(abstract.get("militaryPressure", 0.0)), 3),
                "fortification": round(float(abstract.get("fortification", 0.0)), 3),
                "hazardPressure": round(float(abstract.get("hazardPressure", 0.0)), 3),
            },
        })
    bits.sort(key=lambda item: item["expectedPresenceBand"]["center"], reverse=True)
    return {
        "maxHazard": round(max_hazard, 3),
        "maxFortification": round(max_fort, 3),
        "maxMilitary": round(max_mil, 3),
        "zones": bits[:6],
    }


def zone_center_norm(zone: Dict[str, Any]) -> Tuple[float, float]:
    # Schema 2.0 zones carry a measured anchor: buildable, dry, flat ground the
    # bots actually used. A rect centre can easily be cliff or open water, so
    # the anchor wins whenever one exists.
    anchor = zone.get("anchor") or {}
    if anchor.get("x") is not None and anchor.get("z") is not None:
        return (float(anchor["x"]), float(anchor["z"]))
    bounds = zone.get("bounds", {}) or {}
    return (
        (float(bounds.get("xMin", 0.0)) + float(bounds.get("xMax", 1.0))) / 2.0,
        (float(bounds.get("zMin", 0.0)) + float(bounds.get("zMax", 1.0))) / 2.0,
    )


def _load_map_adjacency(workspace: Optional[Path], map_id: str) -> Dict[str, List[str]]:
    """Same-map adjacency for kernel walks (extract, promote, contracts).

    Prefers data/zone_maps/world_zone_graph.v1.json; falls back to legacy
    zone_adjacency.json via tools/verdance/world/zone_graph.py.
    """
    if workspace is None:
        return {}
    try:
        # Ensure tools/ is importable when this file is executed as a script.

        return _wzg_load_map_adjacency(Path(workspace), map_id, kinds=("same_map",))
    except Exception:
        pass
    path = Path(workspace) / "data" / "zone_maps" / "authored" / "zone_adjacency.json"
    if not path.exists():
        return {}
    try:
        data = load_json(path)
    except Exception:
        return {}
    block = data.get(canonical_map_id(map_id)) or {}
    return {str(k): [str(x) for x in (v or [])] for k, v in block.items()}


def extraction_zone_for(map_id: str, deployment_zone: str,
                        workspace: Optional[Path] = None,
                        target_zone: Optional[str] = None,
                        mission_number: Optional[int] = None,
                        adjacency_mode: Optional[str] = None,
                        state: Optional[Dict[str, Any]] = None) -> str:
    """Pick extraction LZ.

    Legal pads only: quiet rim OR Ashwalker-majority base. Prefer the deploy
    pad when it is already legal (open-area stack for exfil). WO-039 adjacency
    modes still prefer neighbors of the target, filtered to legal pads.
    """

    legacy = {
        "ancient_bastion": "AB_WESTERN_MUSTER_GROUNDS",
        "the_rock_jungle": "RJ_NW_JUNGLE_SHELF",
        "all_that_simmers": "ATS_NW_CANOPY_START",
    }
    mode = adjacency_mode
    if mode is None and mission_number is not None:
        mode = "required" if int(mission_number) <= 3 else "preferred" if int(mission_number) <= 6 else "forward"
    mode = mode or "forward"

    adj = _load_map_adjacency(workspace, map_id)
    target_nbrs = list(adj.get(str(target_zone), []) or []) if target_zone else []

    zones_by_id: Dict[str, Any] = {}
    if workspace is not None:
        zone_map_early = zone_maps_from_workspace(Path(workspace)).get(canonical_map_id(map_id))
        if zone_map_early:
            zones_by_id = {
                str(z.get("zoneId")): z
                for z in zone_map_early.get("zones", []) or []
                if z.get("zoneId")
            }

    def _rim_score(zone: Dict[str, Any]) -> float:
        return _lz.edge_score(zone.get("bounds") or {})

    def _is_legal(zid: str) -> bool:
        zone = zones_by_id.get(zid) or {}
        bounds = zone.get("bounds") if isinstance(zone.get("bounds"), dict) else None
        return _lz.is_legal_landing(
            state,
            canonical_map_id(map_id),
            zid,
            bounds,
            tags=list(zone.get("tags") or []),
            role=str(zone.get("role") or ""),
        )

    # Prefer returning to the deploy pad when it is already a legal open LZ.
    if deployment_zone and _is_legal(str(deployment_zone)):
        if mode == "forward":
            pass  # still allow a forward quiet rim below
        else:
            return str(deployment_zone)

    # Adjacent / preferred: stay local, legal pads only.
    if mode in ("required", "preferred") and target_zone and target_nbrs:
        pool = [z for z in target_nbrs if z not in (deployment_zone, target_zone)]
        legal_pool = [z for z in pool if _is_legal(z)]
        if legal_pool:
            return legal_pool[0]
        if deployment_zone and deployment_zone in target_nbrs and _is_legal(str(deployment_zone)):
            return str(deployment_zone)
        # No legal neighbor: fall back to deploy if legal, else legacy.
        if deployment_zone and _is_legal(str(deployment_zone)):
            return str(deployment_zone)
        return legacy.get(canonical_map_id(map_id), deployment_zone)

    if workspace is not None and zones_by_id:
        deploy = zones_by_id.get(deployment_zone)
        target = zones_by_id.get(target_zone) if target_zone else None
        if deploy:
            dx, dz = zone_center_norm(deploy)
            tx, tz = zone_center_norm(target) if target else (dx + 0.35, dz + 0.35)
            ax, az = tx - dx, tz - dz
            alen = (ax * ax + az * az) ** 0.5 or 1.0
            ax, az = ax / alen, az / alen
            min_dist = 0.14
            candidates = []
            for zid in sorted(zones_by_id):
                if zid in (deployment_zone, target_zone):
                    continue
                if not _is_legal(zid):
                    continue
                zone = zones_by_id[zid]
                tags = set(str(t).lower() for t in zone.get("tags", []) or [])
                role = str(zone.get("role", "")).lower()
                if "hive" in role or "raptor" in role or "raptors" in tags or "wilds" in tags:
                    continue
                cx, cz = zone_center_norm(zone)
                dist = ((cx - dx) ** 2 + (cz - dz) ** 2) ** 0.5
                forward = (cx - dx) * ax + (cz - dz) * az
                candidates.append((zid, dist, forward, _rim_score(zone)))
            if candidates:
                far = [c for c in candidates if c[1] >= min_dist]
                pool = far or candidates
                pool.sort(key=lambda c: (c[2] + 0.5 * c[1], -c[3]), reverse=True)
                best = pool[0][0]
                if best != deployment_zone:
                    return best
    if deployment_zone and _is_legal(str(deployment_zone)):
        return str(deployment_zone)
    return legacy.get(canonical_map_id(map_id), deployment_zone)


__all__ = [
    "_load_map_adjacency",
    "_objective_for_map_raw",
    "append_history_bead",
    "build_war_map",
    "choose_next_map_zone",
    "consequence_note",
    "dominant_faction",
    "enumerate_front_targets",
    "extraction_zone_for",
    "objective_for_map",
    "reset_live_raptors_but_escalate",
    "story_tags_for_result",
    "summarize_front",
    "threat_band",
    "update_destroyed_objectives",
    "world_reading",
    "zone_center_norm",
    "zone_pressure_summary",
]
