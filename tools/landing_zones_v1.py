#!/usr/bin/env python3
"""Legal landing / extract pads for Verdance sorties.

A zone is a legal infil/exfil pad when either:

1. Quiet rim — on the map edge (`edgeScore ≤ RIM_EDGE_THRESHOLD`) and not
   enemy-held / contested, OR
2. Ashwalker base — `controllingFaction == ashwalkers` AND Ashwalkers hold a
   majority of the zone's defensive-value stack (factionPresence = DV).
   Claimed / established bases with no fresh stack still count (majority
   vacuously).

Territory control is DV-only: parked armies do not buy an EXIT pad; teeth do
(Warder Beamer/LLT rings, turrets, fortify). Fresh campaigns have no Ashwalker
ground, so the first raid must enter from a quiet rim. A clean extract with a
holding DV stack seeds that pad as Ashwalker ground for later sorties.
"""
from __future__ import annotations

from typing import Any, Dict, Optional, Tuple

RIM_EDGE_THRESHOLD = 0.28
ENEMY_CONTROL = frozenset({"armada", "cortex", "wild"})
ASHWALKER_ALIASES = frozenset({"ashwalkers", "legion"})


def edge_score(bounds: dict) -> float:
    """Distance from map rim in normalized coords (0 = on edge, 0.5 = dead center)."""
    if not isinstance(bounds, dict):
        return 0.5
    try:
        xmin = float(bounds.get("xMin", 0) or 0)
        xmax = float(bounds.get("xMax", 1) or 1)
        zmin = float(bounds.get("zMin", 0) or 0)
        zmax = float(bounds.get("zMax", 1) or 1)
    except (TypeError, ValueError):
        return 0.5
    cx = (xmin + xmax) * 0.5
    cz = (zmin + zmax) * 0.5
    return min(cx, 1.0 - cx, cz, 1.0 - cz)


def is_rim_zone(bounds: dict, *, threshold: float = RIM_EDGE_THRESHOLD) -> bool:
    return edge_score(bounds) <= threshold


def _zone_mem(state: Optional[dict], map_id: str, zone_id: str) -> dict:
    if not state or not map_id or not zone_id:
        return {}
    zm = (state.get("zoneMemory") or {}).get(map_id) or {}
    z = zm.get(zone_id)
    if isinstance(z, dict):
        return z
    return {}


def zone_control(state: Optional[dict], map_id: str, zone_id: str) -> str:
    z = _zone_mem(state, map_id, zone_id)
    return str(
        z.get("controllingFaction")
        or (z.get("abstract") or {}).get("control")
        or "unknown"
    ).lower()


def zone_faction_presence(state: Optional[dict], map_id: str, zone_id: str) -> Dict[str, float]:
    """Defensive-value stack weights for a zone (territory ownership signal)."""
    z = _zone_mem(state, map_id, zone_id)
    raw = z.get("lastMeasuredRaw") or {}
    fp = raw.get("factionPresence")
    if not isinstance(fp, dict) or not fp:
        abstract = z.get("abstract") or {}
        fp = abstract.get("factionPresence")
    if not isinstance(fp, dict):
        return {}
    out: Dict[str, float] = {}
    for k, v in fp.items():
        try:
            out[str(k).lower()] = float(v or 0)
        except (TypeError, ValueError):
            continue
    return out


def ashwalker_stack_share(state: Optional[dict], map_id: str, zone_id: str) -> Optional[float]:
    """Ashwalker fraction of DV stack, or None when no stack is measured."""
    fp = zone_faction_presence(state, map_id, zone_id)
    if not fp:
        return None
    total = sum(fp.values())
    if total <= 0:
        return None
    ash = sum(v for k, v in fp.items() if k in ASHWALKER_ALIASES)
    return ash / total


def is_ashwalker_majority(state: Optional[dict], map_id: str, zone_id: str) -> bool:
    """Ashwalker control + majority DV stack (or vacuous majority if no stack)."""
    if zone_control(state, map_id, zone_id) not in ASHWALKER_ALIASES:
        return False
    share = ashwalker_stack_share(state, map_id, zone_id)
    if share is None:
        return True
    return share >= 0.5


def zone_is_contested(
    *,
    control: str,
    tags: Optional[list] = None,
    role: str = "",
) -> bool:
    """Enemy-held or explicitly contested — not a quiet approach lane."""
    ctrl = (control or "unknown").lower()
    if ctrl in ENEMY_CONTROL:
        return True
    tagset = {str(t).lower() for t in (tags or [])}
    role_l = (role or "").lower()
    if "contested" in tagset or "contested" in role_l:
        return True
    # Authored hardpoints on the rim are not quiet approach pads unless we hold them.
    if (
        role_l in ("fortress", "bastion", "citadel")
        or "fortress" in tagset
        or "bastion" in tagset
        or "citadel" in tagset
    ):
        return ctrl not in ASHWALKER_ALIASES
    return False


def is_quiet_rim(
    bounds: dict,
    *,
    control: str = "unknown",
    tags: Optional[list] = None,
    role: str = "",
    threshold: float = RIM_EDGE_THRESHOLD,
) -> bool:
    if not is_rim_zone(bounds, threshold=threshold):
        return False
    return not zone_is_contested(control=control, tags=tags, role=role)


def legal_landing_reason(
    state: Optional[dict],
    map_id: str,
    zone_id: str,
    bounds: Optional[dict],
    *,
    tags: Optional[list] = None,
    role: str = "",
) -> Tuple[bool, str]:
    """Return (ok, reason_code). reason_code is for stamp errors / UI."""
    if is_ashwalker_majority(state, map_id, zone_id):
        return True, "ashwalker_base"
    control = zone_control(state, map_id, zone_id) if state else "unknown"
    if bounds is not None and is_quiet_rim(
        bounds, control=control, tags=tags, role=role
    ):
        return True, "quiet_rim"
    if bounds is not None and is_rim_zone(bounds):
        return False, "contested_rim"
    return False, "midfield_unowned"


def is_legal_landing(
    state: Optional[dict],
    map_id: str,
    zone_id: str,
    bounds: Optional[dict],
    *,
    tags: Optional[list] = None,
    role: str = "",
) -> bool:
    ok, _ = legal_landing_reason(
        state, map_id, zone_id, bounds, tags=tags, role=role
    )
    return ok


def fortress_neighbor_penalty(
    zone_id: str,
    *,
    zones_by_id: Optional[Dict[str, dict]] = None,
    adjacency: Optional[Dict[str, list]] = None,
) -> int:
    """How many fortress/bastion/citadel neighbors a pad has (higher = hotter approach)."""
    zones_by_id = zones_by_id or {}
    adjacency = adjacency or {}
    penalty = 0
    for nbr in adjacency.get(str(zone_id), []) or []:
        meta = zones_by_id.get(str(nbr)) or {}
        role = str(meta.get("role") or "").lower()
        tags = {str(t).lower() for t in (meta.get("tags") or [])}
        if role in ("fortress", "bastion", "citadel") or tags & {"fortress", "bastion", "citadel"}:
            penalty += 2
        ctrl = str(meta.get("controllingFaction") or (meta.get("abstract") or {}).get("control") or "").lower()
        if ctrl in ENEMY_CONTROL:
            penalty += 1
    return penalty


def pick_quiet_rim_pad(
    map_id: str,
    *,
    state: Optional[dict] = None,
    zones: Optional[list] = None,
    adjacency: Optional[Dict[str, list]] = None,
    preferred: Optional[list] = None,
) -> Optional[str]:
    """Best quiet-rim LZ: legal, fewest fortress/enemy neighbors, then true edge."""
    if not zones:
        return None
    zones_by_id = {
        str(z.get("zoneId")): z
        for z in zones
        if isinstance(z, dict) and z.get("zoneId")
    }
    preferred = list(preferred or [])
    pref_rank = {str(z): i for i, z in enumerate(preferred)}
    scored: list[tuple] = []
    for z in zones:
        zid = str(z.get("zoneId") or "")
        if not zid:
            continue
        bounds = z.get("bounds") if isinstance(z.get("bounds"), dict) else None
        ok, reason = legal_landing_reason(
            state,
            map_id,
            zid,
            bounds,
            tags=list(z.get("tags") or []),
            role=str(z.get("role") or ""),
        )
        if not ok or reason != "quiet_rim":
            # Ashwalker bases also fine, but opening wants quiet rim first.
            if not (ok and reason == "ashwalker_base"):
                continue
        pen = fortress_neighbor_penalty(
            zid, zones_by_id=zones_by_id, adjacency=adjacency
        )
        # Lower = better. Explicit preferred order beats generic rim scoring.
        pref = pref_rank.get(zid, len(preferred) + 1)
        role = str(z.get("role") or "").lower()
        tags = {str(t).lower() for t in (z.get("tags") or [])}
        startish = 0 if (role == "start" or "start" in tags or "muster" in tags) else 1
        scored.append((pen, pref, startish, edge_score(bounds or {}), zid))
    if not scored:
        return None
    scored.sort()
    return scored[0][4]


def seed_ashwalker_pad(
    state: dict,
    map_id: str,
    zone_id: str,
    *,
    stack_weight: float = 1.0,
    label: Optional[str] = None,
) -> dict:
    """Mark an extract / FOB pad as Ashwalker-held with a majority DV stack."""
    if not map_id or not zone_id:
        return {"ok": False, "reason": "missing_ids"}
    zone_memory = state.setdefault("zoneMemory", {})
    zones = zone_memory.setdefault(map_id, {})
    z = zones.get(zone_id)
    if not isinstance(z, dict):
        z = {
            "mapId": map_id,
            "zoneId": zone_id,
            "label": label or zone_id,
            "lastMeasuredRaw": {},
            "abstract": {},
            "controllingFaction": "ashwalkers",
            "confidence": "estimated",
        }
        zones[zone_id] = z
    abstract = z.setdefault("abstract", {})
    z["controllingFaction"] = "ashwalkers"
    abstract["control"] = "ashwalkers"
    weight = max(0.1, float(stack_weight or 1.0))
    fp = {"ashwalkers": weight}
    # Preserve residual enemy presence but keep Ashwalkers strictly majority.
    prev = zone_faction_presence(state, map_id, zone_id)
    for fac, val in prev.items():
        if fac in ASHWALKER_ALIASES:
            continue
        fp[fac] = min(float(val or 0), weight * 0.4)
    raw = z.setdefault("lastMeasuredRaw", {})
    raw["factionPresence"] = fp
    abstract["factionPresence"] = dict(fp)
    abstract["baseStrength"] = round(
        max(float(abstract.get("baseStrength") or 0.0), min(1.0, weight)), 4
    )
    z["confidence"] = z.get("confidence") or "estimated"
    actors = state.setdefault("offscreenActors", {})
    map_actors = actors.setdefault(map_id, {})
    map_actors[zone_id] = "Ashwalkers"
    return {"ok": True, "mapId": map_id, "zoneId": zone_id, "factionPresence": fp}
