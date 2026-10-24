#!/usr/bin/env python3
"""Legal landing / extract pads for Verdance sorties.

A zone is a legal pad (you land there and lift from there) when either:

1. A door the company holds -- an end of a road between maps, held in the company's door
   ledger (verdance.world.roads). A new campaign holds the two doors of the start road,
   so the first drops land on the road between Greenest Fields and the Rock Jungle; or
2. Ashwalker ground -- `controllingFaction == ashwalkers` AND Ashwalkers hold a majority of
   the zone's defensive-value stack (factionPresence = DV). Claimed / established bases
   with no fresh stack still count (majority vacuously).

There is no landing on open ground: the company arrives by a road and stands on what it holds.
A sortie card may still name its own pad (a crossing lands on the far door); the stamp
accepts the pads its chosen card names.
"""
from __future__ import annotations

from typing import Any, Dict, Optional, Tuple

from verdance.common import edge_score

RIM_EDGE_THRESHOLD = 0.28
ENEMY_CONTROL = frozenset({"armada", "cortex", "wild"})
ASHWALKER_ALIASES = frozenset({"ashwalkers", "legion"})


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
    from verdance.world.roads import held as door_held
    if state and door_held(state, zone_id):
        return True, "held_door"
    if is_ashwalker_majority(state, map_id, zone_id):
        return True, "ashwalker_base"
    return False, "not_ours"


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
