#!/usr/bin/env python3
"""Roads between maps, and the doors at their ends.

A road is a strategic_link in the world graph. Each end is a door: a corner or edge
zone of its map. The rules (owner-approved, 2026-10-23):

  * You can cross a road only while you hold the door you leave by.
  * You hold a door when your presence there (army or defences) outweighed everyone else's
    when you lifted, and reached the claim presence (verdance.world.claim: 400 on Greenest
    Fields, half as much again per road beyond). A door with nothing standing in it stays as
    the company last knew it.
  * Taking a door, the extraction moves onto it once it is yours: you leave by the exit.
  * Lose a door and the road is shut to you until you take it back. Maps already
    opened (walked) stay on the board.
  * Crossing lands you on the far door: your foothold on the new map.
  * The company starts on the start road, holding both of its doors (the ledger's
    default in verdance.campaign.schema).

The door ledger (state["doors"]) is the company's own record, written only at
homecoming from what the sortie measured. Offscreen fighting never touches it, so the
hub never shows a door's truth the company has not seen.

The hub offers at most three sorties: one lean drawn from a seeded softmax over every
legal job, plus the two strongest leftovers. A job is either a crossing (from a held
door to the far door of a map not yet walked) or a door to take (an unheld door on an
open map). Walked maps need no crossing: they stay on the board.
"""
from __future__ import annotations

import hashlib
import json
import math
import random
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from verdance.common import clamp, load_json
from verdance.company.company import score_field_recruit_belief
from verdance.world.claim import claim_need, holder

HOME_MAP_ID = "the_rock_jungle"
PLAYER_FACTIONS = {"ashwalkers", "nullmercs", "legion"}

TEMPERATURE = 0.75
SHUT_MAP = 1.4      # a road onto a map the company has never walked
TAKE_DOOR = 0.9     # a door to take back or take for the first time
Q0_BIAS = 0.35

MAP_NAMES = {
    "greenest_fields": "Greenest Fields",
    "eye_of_horus": "the Eye",
    "koom_valley": "Koom Valley",
    "tabula": "Tabula",
    "ancient_bastion": "the Bastion",
    "the_rock_jungle": "the Rock Jungle",
    "all_that_simmers": "All That Simmers",
}

# Who a map's fight is against. q0 high leans Cortex, low leans Armada.
MAP_FACTION = {
    "greenest_fields": "armada",
    "koom_valley": "armada",
    "tabula": "armada",
    "ancient_bastion": "armada",
    "eye_of_horus": "cortex",
    "the_rock_jungle": None,
    "all_that_simmers": None,
}

_CACHE: Dict[str, Dict[str, Any]] = {}


def _canon_map(map_id: Any) -> str:
    mid = str(map_id or "").strip().lower().replace(" ", "_")
    return HOME_MAP_ID if mid == "rock_jungle" else mid


def load_doors(workspace: Path) -> Dict[str, Dict[str, Any]]:
    """Every door: zone id -> its map, label, and the far door it leads to."""
    key = str(Path(workspace).resolve())
    if key in _CACHE:
        return _CACHE[key]
    data = load_json(Path(workspace) / "data" / "zone_maps" / "world_zone_graph.v1.json", {}) or {}
    nodes = {str(n.get("zoneId")): n for n in (data.get("nodes") or []) if n.get("zoneId")}
    doors: Dict[str, Dict[str, Any]] = {}
    for edge in data.get("edges") or []:
        if str(edge.get("kind") or "") != "strategic_link":
            continue
        a, b = str(edge.get("from") or ""), str(edge.get("to") or "")
        if a not in nodes or b not in nodes:
            continue
        minutes = float(edge.get("travelMinutes") or 0.0)
        for near, far in ((a, b), (b, a)):
            doors[near] = {
                "zoneId": near,
                "mapId": _canon_map(nodes[near].get("mapId")),
                "label": str(nodes[near].get("label") or near),
                "farZoneId": far,
                "farMapId": _canon_map(nodes[far].get("mapId")),
                "farLabel": str(nodes[far].get("label") or far),
                "travelMinutes": minutes,
                "anchor": dict(nodes[near].get("anchor") or {"x": 0.5, "z": 0.5}),
            }
    _CACHE[key] = doors
    return doors


def is_door(zone_id: Any, workspace: Optional[Path]) -> bool:
    return bool(zone_id) and workspace is not None and str(zone_id) in load_doors(Path(workspace))


def held(state: Dict[str, Any], zone_id: str) -> bool:
    rec = (state.get("doors") or {}).get(str(zone_id))
    return bool(isinstance(rec, dict) and rec.get("held"))


def record_homecoming(state: Dict[str, Any], result: Dict[str, Any], workspace: Optional[Path]) -> List[Dict[str, Any]]:
    """Write what this sortie measured at its map's doors into the ledger.

    Only doors the gadget reported presence for change: whoever leads holds it, the company only
    with the claim presence (verdance.world.claim). Returns the doors that changed hands."""
    if workspace is None:
        return []
    dv = result.get("zoneDv")
    if not isinstance(dv, dict) or not dv:
        return []
    map_id = _canon_map(result.get("deploymentMapId") or result.get("mapId"))
    ledger = state.setdefault("doors", {})
    mission = int(result.get("missionNumber") or state.get("missionNumber") or 0)
    changed: List[Dict[str, Any]] = []
    need = claim_need(map_id, workspace)
    for zid, door in load_doors(Path(workspace)).items():
        if door["mapId"] != map_id or not isinstance(dv.get(zid), dict):
            continue
        leader, _best = holder(dv[zid], need)
        if not leader:
            continue
        now = leader in PLAYER_FACTIONS
        if now != held(state, zid):
            changed.append({"zoneId": zid, "label": door["label"], "held": now,
                            "farMapId": door["farMapId"], "by": leader})
        ledger[zid] = {"held": now, "since": mission, "by": leader}
    return changed


def open_maps(state: Dict[str, Any]) -> set:
    """Home and every map the company has walked. Opened maps stay on the board."""
    opened = {HOME_MAP_ID}
    camp = state.get("homeCamp") if isinstance(state.get("homeCamp"), dict) else {}
    for mid in (state.get("sessionHomeMap"), state.get("lastSortieMapId"), (camp or {}).get("mapId")):
        if mid:
            opened.add(_canon_map(mid))
    for bead in state.get("history") or []:
        if isinstance(bead, dict) and bead.get("mapId"):
            opened.add(_canon_map(bead.get("mapId")))
    opened.discard("")
    opened.discard("unknown")
    return opened


def door_markers(state: Dict[str, Any], workspace: Optional[Path], map_id: str) -> Dict[str, Dict[str, Any]]:
    """The doors on one map, for the boards: where each leads and whether we hold it."""
    if workspace is None:
        return {}
    opened = open_maps(state)
    out = {}
    for zid, door in load_doors(Path(workspace)).items():
        if door["mapId"] != _canon_map(map_id):
            continue
        out[zid] = {
            "farMapId": door["farMapId"],
            "farMapName": MAP_NAMES.get(door["farMapId"], door["farMapId"]),
            "farZoneId": door["farZoneId"],
            "held": held(state, zid),
            "farOpen": door["farMapId"] in opened,
        }
    return out


def world_surface(state: Dict[str, Any], workspace: Path) -> Dict[str, Any]:
    """The planet for the hub's globe: walked maps, and every road with its two doors.

    Only the company's own record goes in: which maps it has walked and which doors its
    ledger says it holds. Where a road leads past the edge of the walked world, the hub
    draws it into the dark."""
    doors = load_doors(Path(workspace))
    seen, roads = set(), []
    for zid, door in sorted(doors.items()):
        key = tuple(sorted((zid, door["farZoneId"])))
        if key in seen:
            continue
        seen.add(key)
        ends = []
        for z in key:
            d = doors[z]
            ends.append({"zoneId": z, "mapId": d["mapId"], "label": d["label"],
                         "x": round(float(d["anchor"].get("x", 0.5)), 4), "z": round(float(d["anchor"].get("z", 0.5)), 4),
                         "held": held(state, z)})
        roads.append({"a": ends[0], "b": ends[1], "travelMinutes": door["travelMinutes"]})
    return {"openMaps": sorted(open_maps(state)), "homeMapId": HOME_MAP_ID, "roads": roads}


# --- what pulls the company one way or another ---------------------------------

def _leak(state: Dict[str, Any], map_id: str) -> float:
    graph = state.get("graph") if isinstance(state.get("graph"), dict) else {}
    try:
        q6 = float(graph.get("q6_contested") or 0.5)
        q6i = float(graph.get("q6_independent") or 0.0)
    except (TypeError, ValueError):
        q6, q6i = 0.5, 0.0
    rec = (state.get("hydrologyBloom") or {}).get(map_id) if isinstance(state.get("hydrologyBloom"), dict) else None
    try:
        bloom = float((rec or {}).get("bloom") or 0.0) if isinstance(rec, dict) else 0.0
    except (TypeError, ValueError):
        bloom = 0.0
    return clamp(0.50 * q6 + 0.30 * (1.0 - q6i) + 0.20 * bloom, 0.0, 1.0)


def _wild_on_map(state: Dict[str, Any], map_id: str) -> List[Dict[str, Any]]:
    """Wild field-pool heroes on this map, loudest belief first."""
    field = state.get("fieldPool") if isinstance(state.get("fieldPool"), dict) else {}
    rows: List[Dict[str, Any]] = []
    for hid, entry in (field or {}).items():
        if not isinstance(entry, dict) or str(entry.get("status") or "") != "wild":
            continue
        recruit = entry.get("recruit") if isinstance(entry.get("recruit"), dict) else {}
        home = entry.get("home") if isinstance(entry.get("home"), list) else []
        if _canon_map(recruit.get("mapId") or (home[0] if home else "")) != map_id:
            continue
        belief = float(score_field_recruit_belief(state, entry, map_id=map_id))
        rows.append({"heroId": str(entry.get("heroId") or hid), "name": str(entry.get("name") or hid),
                     "zoneId": str(recruit.get("zoneId") or (home[1] if len(home) > 1 else "") or ""),
                     "belief": round(belief, 4)})
    rows.sort(key=lambda r: (-float(r["belief"]), r["heroId"]))
    return rows


def _rescue(heroes: List[Dict[str, Any]]) -> float:
    """The loudest wild hero carries the term; the rest add a capped chorus."""
    if not heroes:
        return 0.0
    ordered = [float(h["belief"]) for h in heroes]
    return ordered[0] + 0.45 * (1.0 - math.exp(-sum(ordered[1:]) / 3.0)) + 0.07 * min(len(ordered), 8)


def _q0_bias(state: Dict[str, Any], map_id: str) -> float:
    faction = MAP_FACTION.get(map_id)
    if not faction:
        return 0.0
    graph = state.get("graph") if isinstance(state.get("graph"), dict) else {}
    try:
        q0 = float(graph.get("q0_armada_cortex") or 0.5)
    except (TypeError, ValueError):
        q0 = 0.5
    signed = max(-1.0, min(1.0, (q0 - 0.5) * 2.0))
    return Q0_BIAS * signed if faction == "cortex" else -Q0_BIAS * signed


# --- the jobs ------------------------------------------------------------------

def legal_jobs(state: Dict[str, Any], workspace: Path) -> List[Dict[str, Any]]:
    """Every crossing from a held door onto a map not yet walked, and every unheld door on an open map."""
    doors = load_doors(workspace)
    opened = open_maps(state)
    jobs: List[Dict[str, Any]] = []
    for zid, door in sorted(doors.items()):
        if door["mapId"] not in opened:
            continue
        if held(state, zid):
            far_map = door["farMapId"]
            if far_map in opened:
                continue  # an opened map is already on the board: no crossing needed
            heroes = _wild_on_map(state, far_map)
            score = 1.6 * (SHUT_MAP + 0.3 * _leak(state, far_map))
            score += _rescue(heroes) + _q0_bias(state, far_map)
            jobs.append({"kind": "cross", "door": door, "mapId": far_map, "padZoneId": door["farZoneId"],
                         "targetZoneId": door["farZoneId"], "shut": True, "heroes": heroes,
                         "score": round(score, 4), "id": f"road_{zid}"})
        else:
            map_id = door["mapId"]
            heroes = _wild_on_map(state, map_id)
            pad = next((z for z, d in sorted(doors.items()) if d["mapId"] == map_id and held(state, z)), None)
            leads_out = door["farMapId"] not in opened
            score = 1.6 * (TAKE_DOOR + (0.8 if leads_out else 0.0)) + 0.5 * _rescue(heroes) + _q0_bias(state, map_id)
            jobs.append({"kind": "take", "door": door, "mapId": map_id, "padZoneId": pad,
                         "targetZoneId": zid, "shut": leads_out, "heroes": heroes,
                         "claim": claim_need(map_id, workspace),
                         "score": round(score, 4), "id": f"door_{zid}"})
    jobs.sort(key=lambda j: (-float(j["score"]), j["id"]))
    return jobs


def collapse_seed(state: Dict[str, Any]) -> int:
    """Last result key plus the rounded graph. A hub refresh does not reshuffle."""
    hist = state.get("history") or []
    key = str(hist[-1].get("resultKey") or "") if hist and isinstance(hist[-1], dict) else ""
    graph = state.get("graph") if isinstance(state.get("graph"), dict) else {}
    rounded = {str(k): round(float(v), 2) for k, v in sorted((graph or {}).items())
               if isinstance(v, (int, float)) and not isinstance(v, bool)}
    blob = json.dumps({"k": key, "g": rounded}, sort_keys=True)
    return int(hashlib.sha256(blob.encode("utf-8")).hexdigest()[:12], 16)


def _draw(jobs: List[Dict[str, Any]], seed: int) -> Tuple[Optional[Dict[str, Any]], List[Dict[str, Any]]]:
    if len(jobs) <= 1:
        return (jobs[0] if jobs else None), []
    rng = random.Random(seed)
    peak = max(float(j["score"]) for j in jobs)
    weights = [math.exp((float(j["score"]) - peak) / TEMPERATURE) for j in jobs]
    roll, acc, pick = rng.random() * sum(weights), 0.0, len(jobs) - 1
    for i, w in enumerate(weights):
        acc += w
        if roll <= acc:
            pick = i
            break
    rest = [j for i, j in enumerate(jobs) if i != pick]
    return jobs[pick], rest[:2]


def _card(job: Dict[str, Any], lean: bool) -> Dict[str, Any]:
    door = job["door"]
    map_name = MAP_NAMES.get(job["mapId"], job["mapId"])
    heroes = job.get("heroes") or []
    along = (f"Along the way: {', '.join(h['name'] for h in heroes[:4])}."
             if heroes else "")
    if job["kind"] == "cross":
        far = door["farLabel"]
        label = f"Open {map_name} through {door['label']}"
        lines = [f"You hold {door['label']}, the door to {map_name}. Cross the road and land on its far door, {far}.",
                 f"Hold {far} and the road home through it stays yours."]
        contract = "fortify_zone"
    else:
        far_name = MAP_NAMES.get(door["farMapId"], door["farMapId"])
        label = f"Take {door['label']} on {map_name}, the door to {far_name}"
        lines = [f"{door['label']} is the door to {far_name}, and you do not hold it.",
                 f"Stand there with {int(job.get('claim') or 0)} metal of army or defences, more than anyone else, and it is yours. "
                 "Then the extraction moves onto the door: leave by it and the road opens."]
        contract = "seize_lane"
    if job["mapId"] == "all_that_simmers":
        # Every drop on All That Simmers is the kings' showdown (verdance.world.theaters).
        label = f"The kings' showdown on {map_name}, from {door['label'] if job['kind'] != 'cross' else door['farLabel']}"
        lines = ["Armada, Null Mercs and the company each start with one commander and nothing else.",
                 "Last commander standing takes the throne. The packs and the reserve stay home."]
        contract = "kings_showdown"
    if along and contract != "kings_showdown":
        lines.append(along)
    lines.append("The world leans this way." if lean else "Still open.")
    effect: Dict[str, Any] = {
        "mapId": job["mapId"],
        "contractKind": contract,
        "preferredCaptureZoneId": job["targetZoneId"],
        "sessionMode": "same_map" if job["mapId"] == HOME_MAP_ID else "map_travel",
        "against": "wild" if job["mapId"] == HOME_MAP_ID else (MAP_FACTION.get(job["mapId"]) or "armada"),
        "journey": "road" if job["kind"] == "cross" else "door",
        "door": {"zoneId": door["zoneId"], "farMapId": door["farMapId"], "farZoneId": door["farZoneId"]},
    }
    if job.get("padZoneId"):
        effect["preferredDeployZoneId"] = job["padZoneId"]
        effect["padLocked"] = True
    return {"id": job["id"], "label": ("Lean · " if lean else "") + label, "blurb": "\n".join(lines),
            "kind": "deploy", "lean": lean, "recommended": lean, "score": job["score"], "effect": effect}


def road_sorties(state: Dict[str, Any], workspace: Path, *, seed: Optional[int] = None) -> Dict[str, Any]:
    """One seeded lean plus the two strongest leftovers."""
    jobs = legal_jobs(state, Path(workspace))
    used = collapse_seed(state) if seed is None else int(seed)
    lean, rest = _draw(jobs, used)
    cards = ([_card(lean, True)] if lean else []) + [_card(j, False) for j in rest]
    voice = ""
    if cards:
        voice = ("Doors are the way between maps. Hold the door you leave by and the road is open; "
                 "lose it and the road shuts until you take it back.")
    return {"seed": used, "openMaps": sorted(open_maps(state)), "jobs": jobs, "cards": cards, "voice": voice}
