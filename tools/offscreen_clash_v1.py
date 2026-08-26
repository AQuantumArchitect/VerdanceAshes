#!/usr/bin/env python3
"""Offscreen faction clash sim — abstract BAR-AI pressure duels (no spring.exe).

While the player fights on a focus map, rival zones elsewhere still skirmish.
Deterministic from seed_key + campaign clock. Caps flips so the world does not
explode overnight.
"""
from __future__ import annotations

import hashlib
import math
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

# Actor bias: military / fort / eco multipliers (BAR-AI-shaped, not real AIs)
ACTOR_BIAS: Dict[str, Dict[str, float]] = {
    "SimpleDefenderAI": {"mil": 0.8, "fort": 1.4, "eco": 0.9, "aggression": 0.55},
    "SimpleAI": {"mil": 1.0, "fort": 1.0, "eco": 1.0, "aggression": 0.85},
    "NullMercsAI": {"mil": 1.3, "fort": 0.7, "eco": 0.85, "aggression": 1.15},
    "RaptorsAI": {"mil": 1.1, "fort": 0.4, "eco": 0.3, "aggression": 1.35},
    "Ashwalkers": {"mil": 0.75, "fort": 0.9, "eco": 1.05, "aggression": 0.45},
    "NullMercs": {"mil": 1.3, "fort": 0.7, "eco": 0.85, "aggression": 1.15},
}

RIVAL_FACTIONS = frozenset({"armada", "cortex", "nullmercs", "wild", "ashwalkers", "neutral"})

# Factions that can lose control on a soft flip
SOFT_CONTROLS = frozenset({"neutral", "nullmercs", "ashwalkers", "wild"})

# The player is modelled as bigger than the base template assumes -- landed
# here so it can ride the same per-faction activity plumbing as the
# Armada-NullMercs rivalry rather than needing a second mechanism.
PLAYER_IMPACT = 2.0

MAX_FLIPS_PER_MAP = 2
MAX_CLASHES_PER_MAP = 8
FLIP_RATIO = 2.0
MIN_FORT_FOR_HARD_HOLD = 0.55


def _clamp(x: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, float(x)))


def _canonical_map(map_id: Optional[str]) -> str:
    mid = str(map_id or "").strip()
    if mid == "rock_jungle":
        return "the_rock_jungle"
    return mid


def _hash_roll(seed_key: str, *parts: Any) -> float:
    h = hashlib.md5(
        ("|".join(str(p) for p in (seed_key,) + parts)).encode("utf-8")
    ).hexdigest()
    return int(h[:8], 16) / float(0xFFFFFFFF)


def _faction_of(zone_mem: Dict[str, Any]) -> str:
    fac = zone_mem.get("controllingFaction") or (zone_mem.get("abstract") or {}).get("control")
    return str(fac or "neutral").lower()


def _actor_of(state: Dict[str, Any], map_id: str, zone_id: str, zone_mem: Dict[str, Any]) -> str:
    actors = (state.get("offscreenActors") or {}).get(map_id) or {}
    if isinstance(actors, dict) and zone_id in actors:
        return str(actors[zone_id])
    fac = _faction_of(zone_mem)
    if fac == "wild":
        return "RaptorsAI"
    if fac == "ashwalkers":
        return "Ashwalkers"
    if fac == "nullmercs":
        return "NullMercsAI"
    if fac == "cortex":
        return "SimpleAI"
    if fac == "armada":
        return "SimpleDefenderAI"
    return "SimpleAI"


def zone_strength(zone_mem: Dict[str, Any], actor: str, activity: float = 1.0) -> float:
    absr = zone_mem.get("abstract") or {}
    bias = ACTOR_BIAS.get(actor) or ACTOR_BIAS["SimpleAI"]
    mil = float(absr.get("militaryPressure") or 0.0)
    fort = float(absr.get("fortification") or 0.0)
    eco = float(absr.get("economyMomentum") or 0.0)
    base = float(absr.get("baseStrength") or 0.0)
    haz = float(absr.get("hazardPressure") or zone_mem.get("hazardPressure") or 0.0)
    raw = (
        mil * bias["mil"] * 1.1
        + fort * bias["fort"] * 0.9
        + eco * bias["eco"] * 0.55
        + base * 0.45
        + haz * (1.2 if actor == "RaptorsAI" else 0.15)
    )
    # Floor so empty zones still skirmish weakly, then the faction's current
    # activity (weather-driven temperament, or PLAYER_IMPACT) -- applied
    # after the floor so it is never swallowed by it.
    return max(0.05, raw) * (0.75 + 0.5 * bias.get("aggression", 1.0)) * activity


def _are_rivals(fa: str, fb: str) -> bool:
    if fa == fb:
        return False
    if fa not in RIVAL_FACTIONS or fb not in RIVAL_FACTIONS:
        return False
    # Neutral only fights if other is not neutral
    if fa == "neutral" and fb == "neutral":
        return False
    return True


def load_map_adjacency(workspace: Optional[Path], map_id: str) -> Dict[str, List[str]]:
    """map zoneId -> neighbors for one map. Falls back to empty."""
    mid = _canonical_map(map_id)
    if not workspace:
        return {}
    try:
        import world_zone_graph as wzg  # type: ignore

        g = wzg.load_world_zone_graph(Path(workspace))
        if g:
            full = wzg.adjacency_from_graph(g, kinds={"same_map"})
            return dict(full.get(mid) or {})
    except Exception:
        pass
    # legacy adjacency file
    try:
        import json

        leg = Path(workspace) / "data" / "zone_maps" / "authored" / "zone_adjacency.json"
        if leg.exists():
            data = json.loads(leg.read_text(encoding="utf-8-sig"))
            block = data.get(mid) or data.get("maps", {}).get(mid) or {}
            if isinstance(block, dict):
                return {str(k): list(v or []) for k, v in block.items() if isinstance(v, (list, tuple))}
    except Exception:
        pass
    return {}


def _pair_edges(adj: Dict[str, List[str]]) -> List[Tuple[str, str]]:
    seen = set()
    edges: List[Tuple[str, str]] = []
    for a, nbs in adj.items():
        for b in nbs or []:
            key = tuple(sorted((str(a), str(b))))
            if key in seen:
                continue
            seen.add(key)
            edges.append((key[0], key[1]))
    return edges


def resolve_clash(
    za: Dict[str, Any],
    zb: Dict[str, Any],
    actor_a: str,
    actor_b: str,
    *,
    dt_minutes: float,
    roll: float,
    allow_flip: bool,
    activity_a: float = 1.0,
    activity_b: float = 1.0,
    rivalry_unlock: bool = False,
) -> Dict[str, Any]:
    """Mutate zone abstracts; return event dict (may be clash-only, no flip)."""
    sa = zone_strength(za, actor_a, activity_a)
    sb = zone_strength(zb, actor_b, activity_b)
    fa = _faction_of(za)
    fb = _faction_of(zb)
    total = sa + sb
    if total <= 0:
        return {"skipped": True}
    ratio = sa / max(1e-6, sb)
    # Scale transfer by dt (normalized to ~12 min sortie)
    scale = _clamp(float(dt_minutes) / 12.0, 0.05, 2.5)
    transfer = 0.02 * scale * (0.6 + 0.8 * roll)

    abs_a = za.setdefault("abstract", {})
    abs_b = zb.setdefault("abstract", {})
    mil_a = float(abs_a.get("militaryPressure") or 0.0)
    mil_b = float(abs_b.get("militaryPressure") or 0.0)
    fort_a = float(abs_a.get("fortification") or 0.0)
    fort_b = float(abs_b.get("fortification") or 0.0)

    if sa >= sb:
        winner, loser = "a", "b"
        mil_a = _clamp(mil_a + transfer * 0.7)
        mil_b = _clamp(mil_b - transfer)
        fort_b = _clamp(fort_b - transfer * 0.35)
        fort_a = _clamp(fort_a + transfer * 0.15)
        win_fac, lose_fac = fa, fb
        lose_zone, win_zone = zb, za
        lose_fort = fort_b
        win_ratio = ratio
    else:
        winner, loser = "b", "a"
        mil_b = _clamp(mil_b + transfer * 0.7)
        mil_a = _clamp(mil_a - transfer)
        fort_a = _clamp(fort_a - transfer * 0.35)
        fort_b = _clamp(fort_b + transfer * 0.15)
        win_fac, lose_fac = fb, fa
        lose_zone, win_zone = za, zb
        lose_fort = fort_a
        win_ratio = (sb / max(1e-6, sa))

    abs_a["militaryPressure"] = round(mil_a, 4)
    abs_b["militaryPressure"] = round(mil_b, 4)
    abs_a["fortification"] = round(fort_a, 4)
    abs_b["fortification"] = round(fort_b, 4)
    # Contested scar
    abs_a["instability"] = _clamp(float(abs_a.get("instability") or 0.4) + 0.01 * scale)
    abs_b["instability"] = _clamp(float(abs_b.get("instability") or 0.4) + 0.01 * scale)

    event: Dict[str, Any] = {
        "type": "offscreen_clash",
        "winnerFaction": win_fac,
        "loserFaction": lose_fac,
        "strengthA": round(sa, 4),
        "strengthB": round(sb, 4),
        "transfer": round(transfer, 4),
        "flipped": False,
    }

    # The Armada-NullMercs front: whichever the weather favours can push the
    # other's border even though Armada is not normally a soft control --
    # checked against the actual pairing here, never trusted blindly from
    # the caller, so the unlock can never leak into an unrelated clash on
    # the same map that mission.
    rivalry_ok = rivalry_unlock and win_fac == "nullmercs" and lose_fac == "armada"
    if (
        allow_flip
        and win_ratio >= FLIP_RATIO
        and (lose_fac in SOFT_CONTROLS or rivalry_ok)
        and lose_fort < MIN_FORT_FOR_HARD_HOLD
        and roll > 0.55
    ):
        lose_zone["controllingFaction"] = win_fac
        lose_zone.setdefault("abstract", {})["control"] = win_fac
        lose_zone["encroachment"] = 0.0
        event["flipped"] = True
        event["type"] = "offscreen_zone_flip"
        event["toFaction"] = win_fac
        event["fromFaction"] = lose_fac
        event["zoneId"] = lose_zone.get("zoneId") or lose_zone.get("label")
        event["label"] = lose_zone.get("label") or event.get("zoneId")

    return event


def run_offscreen_clashes(
    state: Dict[str, Any],
    workspace: Optional[Path] = None,
    *,
    active_map_id: Optional[str] = None,
    dt_minutes: float = 12.0,
    seed_key: Optional[str] = None,
    map_ids: Optional[Sequence[str]] = None,
    far_rate: float = 0.25,
    near_rate: float = 0.5,
) -> Dict[str, Any]:
    """Run abstract skirmishes across maps. Focus map uses near_rate on unmeasured logic externally.

    For clash intensity we scale dt by map band: focus map near_rate, others far_rate.
    """
    active = _canonical_map(active_map_id or state.get("sessionHomeMap"))
    clock = float(state.get("campaignClockMinutes") or 0.0)
    seed = seed_key or f"clash|{clock}|{state.get('missionNumber')}"
    zm_all = state.get("zoneMemory") or {}
    if not isinstance(zm_all, dict):
        return {"clashes": 0, "flips": 0, "events": []}

    targets = list(map_ids) if map_ids else list(zm_all.keys())
    events: List[Dict[str, Any]] = []
    clash_n = 0
    flip_n = 0

    # Lazy import record_front_event and the living world's per-map activity
    record = None
    activity_by_map: Dict[str, Dict[str, float]] = {}
    try:
        import verdance_story_engine_v1 as engine  # type: ignore

        record = engine.record_front_event
        activity_by_map = engine.hydrology_activity(state, workspace)
    except Exception:
        record = None
        activity_by_map = {}

    for map_id in targets:
        mid = _canonical_map(map_id)
        zones = zm_all.get(map_id) or zm_all.get(mid)
        if not isinstance(zones, dict) or len(zones) < 2:
            continue
        rate = near_rate if mid == active else far_rate
        dt = float(dt_minutes) * float(rate)
        if dt <= 0:
            continue
        adj = load_map_adjacency(workspace, mid)
        if not adj:
            # Fallback: pair first soft-control zone with strongest enemy on map
            adj = _synthetic_adj(zones)

        # This map's living-world activity: the Armada-NullMercs front moves
        # toward whichever the weather currently favours; the player's own
        # zones fight at PLAYER_IMPACT regardless of map.
        map_activity = activity_by_map.get(mid, {})
        rivalry_unlock = float(map_activity.get("nullmercs", 1.0)) > float(map_activity.get("armada", 1.0))

        def _activity_for(fac: str) -> float:
            if fac == "ashwalkers":
                return PLAYER_IMPACT
            return float(map_activity.get(fac, 1.0))

        edges = _pair_edges(adj)
        # Prefer rival edges; sort by strength gap for drama
        scored: List[Tuple[float, str, str]] = []
        for a, b in edges:
            za, zb = zones.get(a), zones.get(b)
            if not isinstance(za, dict) or not isinstance(zb, dict):
                continue
            fa, fb = _faction_of(za), _faction_of(zb)
            if not _are_rivals(fa, fb):
                continue
            aa = _actor_of(state, mid, a, za)
            ab = _actor_of(state, mid, b, zb)
            gap = abs(zone_strength(za, aa, _activity_for(fa)) - zone_strength(zb, ab, _activity_for(fb)))
            scored.append((gap, a, b))
        scored.sort(key=lambda t: -t[0])
        flips_here = 0
        for i, (_gap, a, b) in enumerate(scored[:MAX_CLASHES_PER_MAP]):
            za, zb = zones[a], zones[b]
            # ensure zoneId fields
            za.setdefault("zoneId", a)
            zb.setdefault("zoneId", b)
            aa = _actor_of(state, mid, a, za)
            ab = _actor_of(state, mid, b, zb)
            roll = _hash_roll(seed, mid, a, b, i, int(clock))
            allow_flip = flips_here < MAX_FLIPS_PER_MAP
            ev = resolve_clash(za, zb, aa, ab, dt_minutes=dt, roll=roll, allow_flip=allow_flip,
                               activity_a=_activity_for(_faction_of(za)),
                               activity_b=_activity_for(_faction_of(zb)),
                               rivalry_unlock=rivalry_unlock)
            if ev.get("skipped"):
                continue
            clash_n += 1
            ev["mapId"] = mid
            ev["zoneA"] = a
            ev["zoneB"] = b
            if ev.get("flipped"):
                flips_here += 1
                flip_n += 1
                if not ev.get("zoneId"):
                    ev["zoneId"] = a if _faction_of(za) == ev.get("toFaction") else b
            events.append(ev)
            if record:
                try:
                    record(state, {k: v for k, v in ev.items() if k != "skipped"})
                except Exception:
                    pass

    report = {
        "clashes": clash_n,
        "flips": flip_n,
        "events": events[:40],
        "activeMapId": active,
        "dtMinutes": round(float(dt_minutes), 3),
        "seedKey": seed,
    }
    state["lastOffscreenClash"] = {
        "clashes": clash_n,
        "flips": flip_n,
        "eventCount": len(events),
        "activeMapId": active,
    }
    return report


def _synthetic_adj(zones: Dict[str, Any]) -> Dict[str, List[str]]:
    """When graph missing, connect each zone to up to 2 others (stable order)."""
    ids = sorted(str(z) for z in zones.keys())
    adj: Dict[str, List[str]] = {z: [] for z in ids}
    for i, z in enumerate(ids):
        for j in (i - 1, i + 1):
            if 0 <= j < len(ids):
                adj[z].append(ids[j])
    return adj


def self_test() -> None:
    state = {
        "campaignClockMinutes": 30.0,
        "missionNumber": 2,
        "sessionHomeMap": "koom_valley",
        "zoneMemory": {
            "koom_valley": {
                "A": {
                    "zoneId": "A",
                    "label": "A",
                    "controllingFaction": "armada",
                    "abstract": {
                        "militaryPressure": 0.7,
                        "fortification": 0.6,
                        "economyMomentum": 0.4,
                        "baseStrength": 0.5,
                        "control": "armada",
                    },
                },
                "B": {
                    "zoneId": "B",
                    "label": "B",
                    "controllingFaction": "nullmercs",
                    "abstract": {
                        "militaryPressure": 0.25,
                        "fortification": 0.1,
                        "economyMomentum": 0.2,
                        "baseStrength": 0.15,
                        "control": "nullmercs",
                    },
                },
            },
            "eye_of_horus": {
                "C": {
                    "zoneId": "C",
                    "label": "C",
                    "controllingFaction": "cortex",
                    "abstract": {
                        "militaryPressure": 0.5,
                        "fortification": 0.4,
                        "economyMomentum": 0.5,
                        "baseStrength": 0.4,
                        "control": "cortex",
                    },
                },
                "D": {
                    "zoneId": "D",
                    "label": "D",
                    "controllingFaction": "nullmercs",
                    "abstract": {
                        "militaryPressure": 0.2,
                        "fortification": 0.05,
                        "economyMomentum": 0.1,
                        "baseStrength": 0.1,
                        "control": "nullmercs",
                    },
                },
            },
        },
        "offscreenActors": {
            "koom_valley": {"A": "SimpleDefenderAI", "B": "NullMercsAI"},
            "eye_of_horus": {"C": "SimpleAI", "D": "NullMercsAI"},
        },
        "frontEvents": [],
    }
    r = run_offscreen_clashes(state, None, active_map_id="koom_valley", dt_minutes=12.0, seed_key="self")
    assert r["clashes"] >= 1, r
    print("offscreen_clash_v1 self_test OK", r["clashes"], "clashes", r["flips"], "flips")


if __name__ == "__main__":
    self_test()
