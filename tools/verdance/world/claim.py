#!/usr/bin/env python3
"""Taking ground: how much presence the company needs to claim a zone, and who holds it.

The rule (owner, 2026-10-24):

  * Presence is metal standing in a zone at extraction: the factions' armed structures, and for
    the company its armed units too (an army on the ground is enough to claim it when you lift).
  * The company claims a zone only with at least CLAIM_BASE presence there on Greenest Fields,
    half as much again for every road between that map and Greenest Fields.
  * Leading below that claims nothing: the zone stays as it was believed. The factions need no
    minimum; whoever leads holds.

The gadget reads the same number (mission.objective.claimValue) so a zone-taking objective only
completes once the company stands there in force.
"""
from __future__ import annotations

from collections import deque
from pathlib import Path
from typing import Dict, Optional, Tuple

from verdance.common import load_json

CLAIM_BASE = 400.0
CLAIM_GROWTH = 1.5
ORIGIN_MAP = "greenest_fields"
PLAYER_FACTIONS = {"ashwalkers", "nullmercs", "legion"}

_HOPS: Dict[str, Dict[str, int]] = {}


def _canon(map_id: object) -> str:
    mid = str(map_id or "").strip().lower().replace(" ", "_")
    return "the_rock_jungle" if mid == "rock_jungle" else mid


def map_hops(workspace: Path) -> Dict[str, int]:
    """Roads from Greenest Fields to every map (breadth-first over the strategic links)."""
    key = str(Path(workspace).resolve())
    if key in _HOPS:
        return _HOPS[key]
    data = load_json(Path(workspace) / "data" / "zone_maps" / "world_zone_graph.v1.json", {}) or {}
    map_of = {str(n.get("zoneId")): _canon(n.get("mapId")) for n in data.get("nodes") or [] if n.get("zoneId")}
    links: Dict[str, set] = {}
    for e in data.get("edges") or []:
        if str(e.get("kind") or "") != "strategic_link":
            continue
        a, b = map_of.get(str(e.get("from") or "")), map_of.get(str(e.get("to") or ""))
        if a and b and a != b:
            links.setdefault(a, set()).add(b)
            links.setdefault(b, set()).add(a)
    hops, todo = {ORIGIN_MAP: 0}, deque([ORIGIN_MAP])
    while todo:
        here = todo.popleft()
        for there in sorted(links.get(here, ())):
            if there not in hops:
                hops[there] = hops[here] + 1
                todo.append(there)
    _HOPS[key] = hops
    return hops


def claim_need(map_id: object, workspace: Optional[Path]) -> float:
    """Presence the company needs to claim a zone on this map."""
    hops = map_hops(workspace).get(_canon(map_id), 0) if workspace is not None else 0
    return round(CLAIM_BASE * CLAIM_GROWTH ** hops)


def holder(presence: Dict[str, float], need: float) -> Tuple[Optional[str], float]:
    """Who holds a zone given its presence row, or (None, best) when nothing changes: nobody stands
    there, or the company leads without the presence to claim it."""
    vals = {str(f).lower(): float(v or 0) for f, v in (presence or {}).items()}
    if not vals:
        return None, 0.0
    leader, best = max(vals.items(), key=lambda kv: kv[1])
    if best <= 0 or (leader in PLAYER_FACTIONS and best < need):
        return None, best
    return leader, best
