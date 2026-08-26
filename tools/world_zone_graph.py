#!/usr/bin/env python3
"""World zone graph kernel loader (WO-020).

Authoritative atlas: data/zone_maps/world_zone_graph.v1.json
Legacy zone_adjacency.json is a fallback / derived cache only.

Session rule (kernel): same-map edges drive legal contracts and promote picks.
strategic_link edges drive Mode B map travel (session host Reload path).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple

GRAPH_REL = Path("data/zone_maps/world_zone_graph.v1.json")
LEGACY_ADJ_REL = Path("data/zone_maps/authored/zone_adjacency.json")
SCHEMA = "verdance-world-zone-graph/1.0"

# Map id aliases kept in sync with story engine expectations.
MAP_ALIASES = {
    "rock_jungle": "the_rock_jungle",
}


def canonical_map_id(map_id: Optional[str]) -> str:
    mid = str(map_id or "").strip()
    return MAP_ALIASES.get(mid, mid)


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def graph_path(workspace: Path) -> Path:
    return Path(workspace) / GRAPH_REL


def load_world_zone_graph(workspace: Path) -> Optional[Dict[str, Any]]:
    """Load the authoritative graph, or None if missing."""
    path = graph_path(workspace)
    if not path.exists():
        return None
    data = load_json(path)
    if not isinstance(data, dict):
        return None
    return data


def nodes_by_id(graph: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    out: Dict[str, Dict[str, Any]] = {}
    for n in graph.get("nodes") or []:
        zid = n.get("zoneId")
        if zid:
            out[str(zid)] = n
    return out


def adjacency_from_graph(
    graph: Dict[str, Any],
    *,
    kinds: Optional[Iterable[str]] = None,
) -> Dict[str, Dict[str, List[str]]]:
    """Build mapId -> zoneId -> neighbors[] from graph edges.

    Default kinds = same_map only (kernel session rule).
    """
    allow = set(kinds) if kinds is not None else {"same_map"}
    nodes = nodes_by_id(graph)
    # zone -> map
    zone_map: Dict[str, str] = {
        zid: canonical_map_id(n.get("mapId")) for zid, n in nodes.items()
    }
    adj: Dict[str, Dict[str, List[str]]] = {}

    def ensure(map_id: str, zone_id: str) -> None:
        adj.setdefault(map_id, {}).setdefault(zone_id, [])

    for zid, mid in zone_map.items():
        if mid:
            ensure(mid, zid)

    for e in graph.get("edges") or []:
        kind = e.get("kind") or "same_map"
        if kind not in allow:
            continue
        a = str(e.get("from") or "")
        b = str(e.get("to") or "")
        if not a or not b:
            continue
        mid = canonical_map_id(e.get("mapId") or zone_map.get(a) or zone_map.get(b))
        if not mid:
            continue
        ensure(mid, a)
        ensure(mid, b)
        if b not in adj[mid][a]:
            adj[mid][a].append(b)
        if a not in adj[mid][b]:
            adj[mid][b].append(a)

    # Stable neighbor order
    for mid, block in adj.items():
        for zid in block:
            block[zid] = sorted(block[zid])
    return adj


def load_legacy_adjacency(workspace: Path) -> Dict[str, Dict[str, List[str]]]:
    path = Path(workspace) / LEGACY_ADJ_REL
    if not path.exists():
        return {}
    raw = load_json(path)
    out: Dict[str, Dict[str, List[str]]] = {}
    for mid, block in (raw or {}).items():
        cmid = canonical_map_id(mid)
        out[cmid] = {
            str(k): [str(x) for x in (v or [])]
            for k, v in (block or {}).items()
        }
    return out


def load_map_adjacency(
    workspace: Path,
    map_id: Optional[str] = None,
    *,
    kinds: Optional[Iterable[str]] = None,
) -> Dict[str, List[str]]:
    """Adjacency for one map (zone -> neighbors). Prefers world graph."""
    full = load_full_adjacency(workspace, kinds=kinds)
    cmid = canonical_map_id(map_id)
    return dict(full.get(cmid) or {})


def load_full_adjacency(
    workspace: Path,
    *,
    kinds: Optional[Iterable[str]] = None,
) -> Dict[str, Dict[str, List[str]]]:
    """Full mapId -> adjacency. Graph first, legacy fallback."""
    graph = load_world_zone_graph(workspace)
    if graph is not None:
        return adjacency_from_graph(graph, kinds=kinds)
    return load_legacy_adjacency(workspace)


def neighbors(
    workspace: Path,
    map_id: str,
    zone_id: str,
    *,
    kinds: Optional[Iterable[str]] = None,
) -> List[str]:
    adj = load_map_adjacency(workspace, map_id, kinds=kinds)
    return list(adj.get(str(zone_id)) or [])


def same_map_contract_candidates(
    workspace: Path,
    map_id: str,
    from_zone_ids: Iterable[str],
) -> List[str]:
    """Zones on the same map adjacent to any from-zone (kernel promote/raid pool)."""
    adj = load_map_adjacency(workspace, map_id, kinds=("same_map",))
    held = {str(z) for z in from_zone_ids if z}
    out: Set[str] = set()
    for fz in held:
        for n in adj.get(fz) or []:
            if n not in held:
                out.add(n)
    return sorted(out)


def zone_node(workspace: Path, zone_id: str) -> Optional[Dict[str, Any]]:
    graph = load_world_zone_graph(workspace)
    if not graph:
        return None
    return nodes_by_id(graph).get(str(zone_id))


def strategic_link_edges(workspace: Path) -> List[Dict[str, Any]]:
    """Raw strategic_link edges from the atlas (authored cross-map corridors)."""
    graph = load_world_zone_graph(workspace)
    if not graph:
        return []
    out: List[Dict[str, Any]] = []
    for e in graph.get("edges") or []:
        if (e.get("kind") or "") != "strategic_link":
            continue
        a = str(e.get("from") or "")
        b = str(e.get("to") or "")
        if not a or not b:
            continue
        out.append(dict(e))
    return out


def mode_b_travel_candidates(
    workspace: Path,
    from_zone_ids: Iterable[str],
    *,
    current_map_id: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Legal Mode B hops off held/from zones via strategic_link edges.

    Each hop lands on a different map (or at least a destination zone node).
    Session host uses these for Reload-path map travel; Mode A ignores them.
    """
    nodes = {}
    graph = load_world_zone_graph(workspace)
    if graph:
        nodes = nodes_by_id(graph)
    held = [str(z) for z in from_zone_ids if z]
    if not held:
        return []
    held_set = set(held)
    cur_map = canonical_map_id(current_map_id) if current_map_id else ""
    hops: List[Dict[str, Any]] = []
    seen: Set[Tuple[str, str]] = set()

    for e in strategic_link_edges(workspace):
        a = str(e.get("from") or "")
        b = str(e.get("to") or "")
        endpoints = ((a, b), (b, a))
        for src, dst in endpoints:
            if src not in held_set:
                continue
            src_node = nodes.get(src) or {}
            dst_node = nodes.get(dst) or {}
            src_map = canonical_map_id(src_node.get("mapId") or e.get("mapId"))
            dst_map = canonical_map_id(dst_node.get("mapId"))
            if not dst_map:
                continue
            # Mode B is map travel: skip if destination is same map as current focus.
            focus = cur_map or src_map
            if focus and dst_map == focus:
                continue
            key = (src, dst)
            if key in seen:
                continue
            seen.add(key)
            hops.append(
                {
                    "id": f"mode_b_{src}_{dst}",
                    "fromZoneId": src,
                    "fromZoneIds": [src],
                    "targetZoneId": dst,
                    "mapId": dst_map,
                    "fromMapId": src_map or focus,
                    "kind": "strategic_link",
                    "edgeKind": "strategic_link",
                    "sessionMode": "reload_travel",
                    "travelMode": "mode_b",
                    "cost": e.get("cost", 2),
                    "notes": e.get("notes") or "",
                    "label": (dst_node.get("label") or dst),
                    "title": f"Travel — {dst_node.get('label') or dst}",
                    "plain": (
                        f"Mode B map travel via strategic_link: "
                        f"{src_map or '?'} → {dst_map} ({dst}). "
                        "Session host Reload path builds + relaunches."
                    ),
                    "objectiveArchetype": "seize_lane",
                    "patron": "nullmercs",
                    "against": "armada",
                }
            )
    # Stable order: cost then map then zone
    hops.sort(key=lambda h: (int(h.get("cost") or 99), str(h.get("mapId")), str(h.get("targetZoneId"))))
    return hops


def validate_mode_b_hop(
    workspace: Path,
    from_zone_id: str,
    target_zone_id: str,
) -> Optional[Dict[str, Any]]:
    """Return the hop dict if strategic_link connects from→to (either direction)."""
    src = str(from_zone_id or "")
    dst = str(target_zone_id or "")
    if not src or not dst:
        return None
    for hop in mode_b_travel_candidates(workspace, [src]):
        if hop.get("targetZoneId") == dst and hop.get("fromZoneId") == src:
            return hop
    # Also accept when from is any endpoint and target matches
    for hop in mode_b_travel_candidates(workspace, [src]):
        if hop.get("targetZoneId") == dst:
            return hop
    return None


def graph_stats(workspace: Path) -> Dict[str, Any]:
    graph = load_world_zone_graph(workspace)
    if not graph:
        legacy = load_legacy_adjacency(workspace)
        return {
            "source": "legacy_adjacency" if legacy else "missing",
            "mapCount": len(legacy),
            "nodeCount": sum(len(v) for v in legacy.values()),
        }
    kinds: Dict[str, int] = {}
    for e in graph.get("edges") or []:
        k = e.get("kind") or "?"
        kinds[k] = kinds.get(k, 0) + 1
    maps = sorted({canonical_map_id(n.get("mapId")) for n in graph.get("nodes") or [] if n.get("mapId")})
    return {
        "source": "world_zone_graph",
        "schemaVersion": graph.get("schemaVersion"),
        "nodeCount": graph.get("nodeCount") or len(graph.get("nodes") or []),
        "edgeCount": graph.get("edgeCount") or len(graph.get("edges") or []),
        "kinds": kinds,
        "maps": maps,
    }


def main() -> int:
    import argparse

    p = argparse.ArgumentParser(description="World zone graph kernel probe")
    p.add_argument("--workspace", default=".", help="Workspace root")
    p.add_argument("--map", default="", help="Optional mapId for adjacency dump")
    p.add_argument(
        "--mode-b-from",
        default="",
        help="Zone id: dump Mode B strategic_link travel candidates",
    )
    args = p.parse_args()
    ws = Path(args.workspace).resolve()
    print(json.dumps(graph_stats(ws), indent=2))
    if args.map:
        adj = load_map_adjacency(ws, args.map)
        print(json.dumps({"mapId": canonical_map_id(args.map), "adjacency": adj}, indent=2))
    if args.mode_b_from:
        hops = mode_b_travel_candidates(ws, [args.mode_b_from])
        print(json.dumps({"fromZoneId": args.mode_b_from, "modeBHops": hops}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
