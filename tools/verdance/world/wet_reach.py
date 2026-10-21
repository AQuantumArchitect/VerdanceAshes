#!/usr/bin/env python3
"""Wet reach: a sortie is two mouths, and the recommendation is a collapse.

Mouths are the ends of a strategic_link. A card stands on one open map, infil
at one mouth and exfil at another. Extracting at the exfil mouth opens the far
map and sets the next landing. The hub draws one lean from a seeded softmax
and keeps the two strongest leftovers. Territory that opens a shut map is the
heavy term; rescues and holds are the same kind of term with less weight.

Pure read, except apply_heading, which process_result calls on a real extract.
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

HOME_MAP_ID = "the_rock_jungle"
TEMPERATURE = 0.75
ARRIVAL_BIAS = 4.2
Q0_BIAS = 0.35
SHUT_ROAD = 1.4
OPEN_ROAD = 0.4

MAP_NAMES = {
    "greenest_fields": "Greenest Fields",
    "eye_of_horus": "the Eye",
    "koom_valley": "Koom Valley",
    "tabula": "Tabula",
    "ancient_bastion": "the Bastion",
    "the_rock_jungle": "the Rock Jungle",
    "all_that_simmers": "All That Simmers",
}

# q0 high leans Cortex, q0 low leans Armada. Wild and mixed maps take no bias.
FAR_FACTION = {
    "greenest_fields": "armada",
    "koom_valley": "armada",
    "tabula": "armada",
    "ancient_bastion": "armada",
    "eye_of_horus": "cortex",
    "the_rock_jungle": None,
    "all_that_simmers": None,
}

PLAYER_CONTROL = {"ashwalkers", "nullmercs", "legion"}

_ON_PAD_REASONS = {
    "extracted",
    "extracted_auto",
    "extracted_voluntary",
    "extracted_bypass",
    "extracted_raid_partial",
    "extracted_bail",
}

_MOUTH_CACHE: Dict[str, Dict[str, Any]] = {}


def _canon_map(map_id: Any) -> str:
    mid = str(map_id or "").strip().lower().replace(" ", "_")
    if mid == "rock_jungle":
        return HOME_MAP_ID
    return mid


def load_mouths(workspace: Path) -> Dict[str, Any]:
    """Strategic-link mouths. Each end knows the map and zone it opens."""
    key = str(Path(workspace).resolve())
    cached = _MOUTH_CACHE.get(key)
    if cached is not None:
        return cached
    graph_path = Path(workspace) / "data" / "zone_maps" / "world_zone_graph.v1.json"
    # No world graph (a bare test workspace): no strategic links, so no mouths.
    data = load_json(graph_path, {}) or {}
    nodes = {
        str(n.get("zoneId")): n
        for n in (data.get("nodes") or [])
        if n.get("zoneId")
    }
    far: Dict[str, Tuple[str, str]] = {}
    for edge in data.get("edges") or []:
        if str(edge.get("kind") or "") != "strategic_link":
            continue
        a = str(edge.get("from") or "")
        b = str(edge.get("to") or "")
        if not a or not b or a not in nodes or b not in nodes:
            continue
        far[a] = (_canon_map(nodes[b].get("mapId")), b)
        far[b] = (_canon_map(nodes[a].get("mapId")), a)
    by_map: Dict[str, List[str]] = {}
    labels: Dict[str, str] = {}
    zone_map: Dict[str, str] = {}
    for zone_id, (fmap, _fzone) in far.items():
        node = nodes.get(zone_id) or {}
        mid = _canon_map(node.get("mapId"))
        by_map.setdefault(mid, [])
        if zone_id not in by_map[mid]:
            by_map[mid].append(zone_id)
        labels[zone_id] = str(node.get("label") or zone_id)
        zone_map[zone_id] = mid
    packed = {
        "far": far,
        "by_map": by_map,
        "labels": labels,
        "zone_map": zone_map,
    }
    _MOUTH_CACHE[key] = packed
    return packed


def is_mouth(zone_id: Any, workspace: Optional[Path], map_id: Optional[str] = None) -> bool:
    if not zone_id or workspace is None:
        return False
    mouths = load_mouths(Path(workspace))
    zid = str(zone_id)
    if zid not in mouths["far"]:
        return False
    if map_id:
        return mouths["zone_map"].get(zid) == _canon_map(map_id)
    return True


def open_maps(state: Dict[str, Any]) -> set:
    """Home, maps already walked, and maps a heading extract has opened."""
    opened = {HOME_MAP_ID}
    for key in ("sessionHomeMap", "lastSortieMapId", "homeMapId"):
        mid = _canon_map(state.get(key))
        if mid and mid != "unknown":
            opened.add(mid)
    camp = state.get("homeCamp") if isinstance(state.get("homeCamp"), dict) else {}
    camp_map = _canon_map((camp or {}).get("mapId"))
    if camp_map:
        opened.add(camp_map)
    for bead in state.get("history") or []:
        if isinstance(bead, dict):
            mid = _canon_map(bead.get("mapId"))
            if mid and mid != "unknown":
                opened.add(mid)
    prints = state.get("playerFootprints")
    if isinstance(prints, dict):
        for mid, bag in prints.items():
            if bag:
                opened.add(_canon_map(mid))
    reach = state.get("wetReach") if isinstance(state.get("wetReach"), dict) else {}
    for mid in (reach or {}).get("opened") or []:
        canon = _canon_map(mid)
        if canon:
            opened.add(canon)
    opened.discard("")
    opened.discard("unknown")
    return opened


def _leak(state: Dict[str, Any], map_id: str) -> float:
    graph = state.get("graph") if isinstance(state.get("graph"), dict) else {}
    try:
        q6 = float(graph.get("q6_contested") or 0.5)
    except (TypeError, ValueError):
        q6 = 0.5
    try:
        q6i = float(graph.get("q6_independent") or 0.0)
    except (TypeError, ValueError):
        q6i = 0.0
    bloom = 0.0
    store = state.get("hydrologyBloom") if isinstance(state.get("hydrologyBloom"), dict) else {}
    rec = store.get(map_id) if isinstance(store, dict) else None
    if isinstance(rec, dict):
        try:
            bloom = float(rec.get("bloom") or 0.0)
        except (TypeError, ValueError):
            bloom = 0.0
    return clamp(0.50 * q6 + 0.30 * (1.0 - q6i) + 0.20 * bloom, 0.0, 1.0)


def _zone_encroachment(state: Dict[str, Any], map_id: str, zone_id: str) -> float:
    zm = ((state.get("zoneMemory") or {}).get(map_id) or {}).get(zone_id) or {}
    if not isinstance(zm, dict):
        return 0.0
    try:
        return max(0.0, float(zm.get("encroachment") or 0.0))
    except (TypeError, ValueError):
        return 0.0


def _player_hold(state: Dict[str, Any], map_id: str) -> float:
    zones = (state.get("zoneMemory") or {}).get(map_id) or {}
    if not isinstance(zones, dict):
        return 0.0
    worst = 0.0
    for zone_id, zm in zones.items():
        if not isinstance(zm, dict):
            continue
        abstract = zm.get("abstract") if isinstance(zm.get("abstract"), dict) else {}
        ctrl = str(zm.get("controllingFaction") or abstract.get("control") or "").lower()
        if ctrl not in PLAYER_CONTROL:
            continue
        worst = max(worst, _zone_encroachment(state, map_id, str(zone_id)))
    return worst


def _wild_on_map(state: Dict[str, Any], map_id: str) -> List[Dict[str, Any]]:
    """Wild field-pool heroes on this map, loudest belief first.

    A hero whose status has left wild is not on the card.
    """
    field = state.get("fieldPool") if isinstance(state.get("fieldPool"), dict) else {}
    rows: List[Dict[str, Any]] = []
    for hid, entry in (field or {}).items():
        if not isinstance(entry, dict):
            continue
        if str(entry.get("status") or "") != "wild":
            continue
        recruit = entry.get("recruit") if isinstance(entry.get("recruit"), dict) else {}
        home = entry.get("home") if isinstance(entry.get("home"), list) else []
        rmap = _canon_map(recruit.get("mapId") or (home[0] if home else ""))
        if rmap != map_id:
            continue
        zone = str(recruit.get("zoneId") or (home[1] if len(home) > 1 else "") or "")
        if score_field_recruit_belief is not None:
            belief = float(score_field_recruit_belief(state, entry, map_id=map_id))
        else:
            belief = 0.15
        enc = _zone_encroachment(state, map_id, zone) if zone else 0.0
        boosted = belief + min(1.25, enc)
        rows.append({
            "heroId": str(entry.get("heroId") or hid),
            "name": str(entry.get("name") or hid),
            "zoneId": zone,
            "belief": round(belief, 4),
            "boosted": round(boosted, 4),
        })
    rows.sort(key=lambda r: (-float(r["boosted"]), r["heroId"]))
    return rows


def _rescue(heroes: List[Dict[str, Any]]) -> float:
    """Belief of the wild heroes, saturated.

    The loudest hero carries the term. The rest add a capped chorus plus a
    small headcount, so eleven names outweigh an empty shelf and a shut road
    stays heavier than a quiet crowd. One hot shelf can still outrank it.
    """
    if not heroes:
        return 0.0
    ordered = [float(h["boosted"]) for h in heroes]
    loud = ordered[0]
    chorus = sum(ordered[1:])
    crowd = 0.07 * min(len(ordered), 8)
    return loud + 0.45 * (1.0 - math.exp(-chorus / 3.0)) + crowd


def _q0_bias(state: Dict[str, Any], far_map: str) -> float:
    faction = FAR_FACTION.get(far_map)
    if not faction:
        return 0.0
    graph = state.get("graph") if isinstance(state.get("graph"), dict) else {}
    try:
        q0 = float(graph.get("q0_armada_cortex") or 0.5)
    except (TypeError, ValueError):
        q0 = 0.5
    signed = max(-1.0, min(1.0, (q0 - 0.5) * 2.0))
    # Positive q0 is Cortex-ascendant.
    if faction == "cortex":
        return Q0_BIAS * signed
    return -Q0_BIAS * signed


def _arrival(state: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    reach = state.get("wetReach") if isinstance(state.get("wetReach"), dict) else {}
    arrival = (reach or {}).get("arrival")
    if not isinstance(arrival, dict):
        return None
    if not arrival.get("mapId") or not arrival.get("zoneId"):
        return None
    return arrival


def legal_pairs(state: Dict[str, Any], workspace: Path) -> List[Dict[str, Any]]:
    """Every ordered pair of mouths on an open map. Inland pockets are not doors."""
    mouths = load_mouths(workspace)
    opened = open_maps(state)
    arrival = _arrival(state)
    pairs: List[Dict[str, Any]] = []
    for map_id in sorted(opened):
        doors = list(mouths["by_map"].get(map_id) or [])
        if len(doors) < 2:
            continue
        leak = _leak(state, map_id)
        heroes = _wild_on_map(state, map_id)
        rescue = _rescue(heroes)
        hold = _player_hold(state, map_id)
        for infil in doors:
            for exfil in doors:
                if infil == exfil:
                    continue
                far_map, far_zone = mouths["far"][exfil]
                shut = far_map not in opened
                road = (SHUT_ROAD if shut else OPEN_ROAD) + 0.3 * leak
                score = 1.6 * road + 1.0 * rescue + 0.7 * hold
                score += _q0_bias(state, far_map)
                if (
                    arrival
                    and _canon_map(arrival.get("mapId")) == map_id
                    and str(arrival.get("zoneId")) == infil
                ):
                    score += ARRIVAL_BIAS
                pairs.append({
                    "id": f"wr_{infil}__{exfil}",
                    "mapId": map_id,
                    "infilZoneId": infil,
                    "exfilZoneId": exfil,
                    "headingMapId": far_map,
                    "headingZoneId": far_zone,
                    "shut": shut,
                    "leak": round(leak, 4),
                    "road": round(road, 4),
                    "rescue": round(rescue, 4),
                    "hold": round(hold, 4),
                    "score": round(score, 4),
                    "heroes": heroes,
                })
    pairs.sort(key=lambda p: (-float(p["score"]), p["id"]))
    return pairs


def collapse_seed(state: Dict[str, Any]) -> int:
    """Last result key plus the rounded graph. A hub refresh does not reshuffle."""
    key = ""
    hist = state.get("history") or []
    if hist and isinstance(hist[-1], dict):
        key = str(hist[-1].get("resultKey") or "")
    graph = state.get("graph") if isinstance(state.get("graph"), dict) else {}
    rounded: Dict[str, float] = {}
    for name in sorted(graph or {}):
        value = graph.get(name)
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            rounded[str(name)] = round(float(value), 2)
    blob = json.dumps({"k": key, "g": rounded}, sort_keys=True)
    return int(hashlib.sha256(blob.encode("utf-8")).hexdigest()[:12], 16)


def _draw(pairs: List[Dict[str, Any]], seed: int) -> Tuple[Optional[Dict[str, Any]], List[Dict[str, Any]]]:
    if not pairs:
        return None, []
    if len(pairs) == 1:
        return pairs[0], []
    rng = random.Random(seed)
    temp = TEMPERATURE
    peak = max(float(p["score"]) for p in pairs)
    weights = [math.exp((float(p["score"]) - peak) / temp) for p in pairs]
    total = sum(weights) or 1.0
    roll = rng.random() * total
    acc = 0.0
    pick = len(pairs) - 1
    for i, weight in enumerate(weights):
        acc += weight
        if roll <= acc:
            pick = i
            break
    lean = pairs[pick]
    rest = [p for i, p in enumerate(pairs) if i != pick]
    rest.sort(key=lambda p: (-float(p["score"]), p["id"]))
    return lean, rest[:2]


def _along_line(heroes: List[Dict[str, Any]]) -> str:
    if not heroes:
        return "Along the way: the shelf is quiet."
    names = [str(h.get("name") or h.get("heroId")) for h in heroes[:4]]
    extra = len(heroes) - len(names)
    shown = ", ".join(names)
    if extra > 0:
        shown = f"{shown} +{extra}"
    return f"Along the way: {shown}."


def _came_from(pair: Dict[str, Any], arrival: Optional[Dict[str, Any]]) -> str:
    if (
        arrival
        and _canon_map(arrival.get("mapId")) == pair["mapId"]
        and str(arrival.get("zoneId")) == pair["infilZoneId"]
    ):
        origin = _canon_map(arrival.get("fromMap"))
        if origin == HOME_MAP_ID or not origin:
            return "home"
        return MAP_NAMES.get(origin, origin)
    if pair["mapId"] == HOME_MAP_ID:
        return "home"
    return "a road already open"


def _card(pair: Dict[str, Any], *, lean: bool, arrival: Optional[Dict[str, Any]], mouths: Dict[str, Any]) -> Dict[str, Any]:
    labels = mouths["labels"]
    infil_label = labels.get(pair["infilZoneId"], pair["infilZoneId"])
    exfil_label = labels.get(pair["exfilZoneId"], pair["exfilZoneId"])
    map_name = MAP_NAMES.get(pair["mapId"], pair["mapId"])
    far_name = MAP_NAMES.get(pair["headingMapId"], pair["headingMapId"])
    came = _came_from(pair, arrival)
    road_verb = "opens" if pair["shut"] else "returns to"
    heroes = list(pair.get("heroes") or [])
    target = heroes[0]["zoneId"] if heroes and heroes[0].get("zoneId") else pair["exfilZoneId"]
    if pair["shut"] or float(pair["hold"]) <= float(pair["rescue"]):
        kind = "seize_lane"
    else:
        kind = "hold_plateau"
    if pair["mapId"] == HOME_MAP_ID:
        against = "wild"
        session = "same_map"
    elif FAR_FACTION.get(pair["mapId"]) == "cortex" or FAR_FACTION.get(pair["headingMapId"]) == "cortex":
        against = "cortex"
        session = "map_travel"
    else:
        against = "armada"
        session = "map_travel"
    lean_line = "The world leans this way." if lean else "Still open."
    blurb = "\n".join([
        f"You are at {infil_label}, {map_name}. You came in from {came}.",
        f"Heading {exfil_label}. That road {road_verb} {far_name}.",
        _along_line(heroes),
        lean_line,
    ])
    short = "Open" if pair["shut"] else "Walk"
    label = f"{short} {far_name} through {exfil_label}"
    if lean:
        label = f"Lean · {label}"
    return {
        "id": pair["id"],
        "label": label,
        "blurb": blurb,
        "kind": "deploy",
        "lean": lean,
        "recommended": lean,
        "score": pair["score"],
        "effect": {
            "mapId": pair["mapId"],
            "contractKind": kind,
            "preferredCaptureZoneId": target,
            "preferredDeployZoneId": pair["infilZoneId"],
            "preferredExtractionZoneId": pair["exfilZoneId"],
            "infilZoneId": pair["infilZoneId"],
            "exfilZoneId": pair["exfilZoneId"],
            "headingMapId": pair["headingMapId"],
            "headingZoneId": pair["headingZoneId"],
            "alongTheWay": [h["heroId"] for h in heroes],
            "wetReach": True,
            "sessionMode": session,
            "against": against,
            "journey": "wet_reach",
        },
    }


def collapse_sorties(
    state: Dict[str, Any],
    workspace: Path,
    *,
    seed: Optional[int] = None,
) -> Dict[str, Any]:
    """One seeded lean plus the two strongest leftovers. At most three doors."""
    mouths = load_mouths(Path(workspace))
    pairs = legal_pairs(state, Path(workspace))
    used = collapse_seed(state) if seed is None else int(seed)
    lean, residuals = _draw(pairs, used)
    arrival = _arrival(state)
    cards: List[Dict[str, Any]] = []
    if lean is not None:
        cards.append(_card(lean, lean=True, arrival=arrival, mouths=mouths))
    for pair in residuals:
        cards.append(_card(pair, lean=False, arrival=arrival, mouths=mouths))
    voice = ""
    if cards:
        effect = cards[0]["effect"]
        far = MAP_NAMES.get(str(effect.get("headingMapId")), effect.get("headingMapId"))
        voice = (
            f"The world leans toward {far}. "
            f"You are at the door you can leave from, and that extract chooses the next map. "
            f"Two other doors stay open if you refuse it."
        )
    return {
        "seed": used,
        "temperature": TEMPERATURE,
        "openMaps": sorted(open_maps(state)),
        "pairs": pairs,
        "cards": cards,
        "voice": voice,
    }


def real_heading_extract(result: Dict[str, Any]) -> bool:
    """True only when they held the extract pad. A quit off the mouth is not this."""
    reason = str(result.get("terminalReason") or "")
    if reason in _ON_PAD_REASONS or reason.startswith("extracted_side_"):
        return True
    if reason == "extracted_recruit_lost":
        # The soft clock uses this reason without a completed hold.
        return str(result.get("extractionStatus") or "") in ("clean", "contested")
    return False


def apply_heading(
    state: Dict[str, Any],
    result: Dict[str, Any],
    workspace: Optional[Path] = None,
) -> Optional[Dict[str, Any]]:
    """Open the far map when the extract zone is a mouth they actually held.

    Dying, quitting, or timing out off that mouth leaves the board where it was.
    """
    if not real_heading_extract(result):
        return None
    if workspace is None:
        return None
    zone = str(result.get("extractionZoneId") or "")
    mouths = load_mouths(Path(workspace))
    far = mouths["far"].get(zone)
    if not far:
        return None
    far_map, far_zone = far
    from_map = _canon_map(result.get("mapId") or result.get("deploymentMapId") or mouths["zone_map"].get(zone))
    reach = state.setdefault("wetReach", {})
    if not isinstance(reach, dict):
        reach = {}
        state["wetReach"] = reach
    opened = [ _canon_map(m) for m in (reach.get("opened") or []) if _canon_map(m) ]
    if far_map not in opened:
        opened.append(far_map)
    reach["opened"] = opened
    stamp = {
        "mapId": far_map,
        "zoneId": far_zone,
        "fromMap": from_map,
        "fromZone": zone,
        "resultKey": str(result.get("resultKey") or ""),
    }
    reach["arrival"] = stamp
    return stamp
