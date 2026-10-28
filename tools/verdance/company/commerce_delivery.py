#!/usr/bin/env python3
"""Living map-web delivery ETA for Verdance broker packs.

Map-web shipments use strategic_link travelMinutes (Dijkstra).
Pawn-launcher packs use a fixed spool (no map hops).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from verdance.common import WORKSPACE_ROOT

from verdance.world.zone_graph import canonical_map_id, load_world_zone_graph, nodes_by_id

PRINT_SPACES_REL = Path("data/commerce/print_spaces.json")
DEFAULT_SEC_PER_MIN = 10.0
DEFAULT_SAME_MAP_SPOOL = 75
DEFAULT_LAUNCHER_MIN = 60
DEFAULT_LAUNCHER_MAX = 120


def _workspace_root(workspace: Optional[Path] = None) -> Path:
    if workspace is not None:
        return Path(workspace)
    return WORKSPACE_ROOT


def load_print_spaces(workspace: Optional[Path] = None) -> Dict[str, Any]:
    root = _workspace_root(workspace)
    path = root / PRINT_SPACES_REL
    if not path.exists():
        return {"schemaVersion": "verdance-print-spaces/1.0", "craft": {}, "spaces": {}, "mapLabels": {}}
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {"craft": {}, "spaces": {}, "mapLabels": {}}


def map_label(map_id: Optional[str], workspace: Optional[Path] = None) -> str:
    mid = canonical_map_id(map_id) if map_id else ""
    spaces = load_print_spaces(workspace)
    labels = spaces.get("mapLabels") or {}
    if mid and mid in labels:
        return str(labels[mid])
    if not mid:
        return "unknown"
    return mid.replace("_", " ").title()


def _zone_to_map(graph: Dict[str, Any]) -> Dict[str, str]:
    out: Dict[str, str] = {}
    for zid, node in nodes_by_id(graph).items():
        out[str(zid)] = canonical_map_id(node.get("mapId"))
    return out


def build_map_hop_graph(workspace: Optional[Path] = None) -> Dict[str, Dict[str, float]]:
    """Undirected mapId -> neighbor mapId -> travelMinutes."""
    root = _workspace_root(workspace)
    graph = load_world_zone_graph(root)
    hops: Dict[str, Dict[str, float]] = {}
    if not graph:
        return hops
    z2m = _zone_to_map(graph)

    def link(a: str, b: str, minutes: float) -> None:
        if not a or not b or a == b:
            return
        hops.setdefault(a, {})
        hops.setdefault(b, {})
        prev = hops[a].get(b)
        if prev is None or minutes < prev:
            hops[a][b] = minutes
            hops[b][a] = minutes

    for edge in graph.get("edges") or []:
        if not isinstance(edge, dict):
            continue
        if str(edge.get("kind") or "") != "strategic_link":
            continue
        a = z2m.get(str(edge.get("from") or ""), "")
        b = z2m.get(str(edge.get("to") or ""), "")
        cost = float(edge.get("cost") or 2)
        minutes = float(edge.get("travelMinutes") or (12.0 * cost))
        link(a, b, minutes)
    return hops


def shortest_map_route(
    source_map: str,
    dest_map: str,
    workspace: Optional[Path] = None,
) -> Tuple[List[str], float]:
    """Dijkstra on map hops. Returns (route mapIds, travelMinutes)."""
    src = canonical_map_id(source_map)
    dst = canonical_map_id(dest_map)
    if not src or not dst:
        return [], 0.0
    if src == dst:
        return [src], 0.0
    hops = build_map_hop_graph(workspace)
    if src not in hops and dst not in hops:
        return [src, dst], 99.0
    dist: Dict[str, float] = {src: 0.0}
    prev: Dict[str, Optional[str]] = {src: None}
    pending = set(hops.keys()) | {src, dst}
    while pending:
        cur = None
        best = None
        for n in pending:
            if n not in dist:
                continue
            if best is None or dist[n] < best:
                best = dist[n]
                cur = n
        if cur is None:
            break
        pending.remove(cur)
        if cur == dst:
            break
        for nb, w in (hops.get(cur) or {}).items():
            nd = dist[cur] + float(w)
            if nb not in dist or nd < dist[nb]:
                dist[nb] = nd
                prev[nb] = cur
    if dst not in dist:
        # Disconnected fallback: rough hop count * 18
        return [src, dst], 54.0
    route: List[str] = []
    node: Optional[str] = dst
    while node is not None:
        route.append(node)
        node = prev.get(node)
    route.reverse()
    return route, float(dist[dst])


def resolve_listing_delivery(
    listing: Dict[str, Any],
    listing_id: str = "",
    workspace: Optional[Path] = None,
) -> Dict[str, Any]:
    """Normalize delivery block from listing + print_spaces."""
    spaces = load_print_spaces(workspace)
    space_table = spaces.get("spaces") or {}
    delivery = dict(listing.get("delivery") or {}) if isinstance(listing.get("delivery"), dict) else {}

    # Infer from print_spaces listings index if catalog omitted delivery.
    if not delivery:
        for key, space in space_table.items():
            if not isinstance(space, dict):
                continue
            if listing_id and listing_id in (space.get("listings") or []):
                delivery = {
                    "mode": space.get("mode") or "map_web",
                    "sourceMapId": space.get("mapId"),
                    "sourceSpaceId": key,
                    "landNear": "infil",
                    "productLabel": listing.get("label") or listing_id,
                }
                break

    mode = str(delivery.get("mode") or "immediate")
    source_space = str(delivery.get("sourceSpaceId") or "")
    if mode == "pawn_launcher" or source_space == "pawn_launcher":
        mode = "pawn_launcher"
        source_space = "pawn_launcher"
    source_map = delivery.get("sourceMapId")
    if source_map:
        source_map = canonical_map_id(source_map)
    space = space_table.get(source_space) if source_space else None
    if not isinstance(space, dict) and source_map:
        for key, cand in space_table.items():
            if isinstance(cand, dict) and canonical_map_id(cand.get("mapId")) == source_map:
                space = cand
                source_space = key
                break
    if isinstance(space, dict) and not source_map:
        source_map = canonical_map_id(space.get("mapId")) if space.get("mapId") else None

    return {
        "mode": mode,
        "sourceMapId": source_map,
        "sourceSpaceId": source_space or None,
        "sourceLabel": (space or {}).get("label") or map_label(source_map, workspace) or "unknown",
        "sourceBlurb": (space or {}).get("blurb") or "",
        "landNear": delivery.get("landNear") or "infil",
        "productLabel": delivery.get("productLabel") or listing.get("label") or listing_id,
        # map_web = mid-sortie inbound. pawn_launcher lands WITH the infil (t=0)
        # so the opening Punch / bought salvos are boots-on-ground, not a 90s wait
        # while a naked warband eats beamers.
        "deferred": mode == "map_web",
    }


def delivery_eta(
    *,
    listing: Optional[Dict[str, Any]] = None,
    listing_id: str = "",
    dest_map_id: Optional[str] = None,
    workspace: Optional[Path] = None,
) -> Dict[str, Any]:
    """Compute ETA paint + numbers for a listing headed to dest_map_id."""
    listing = listing or {}
    spaces = load_print_spaces(workspace)
    craft = spaces.get("craft") or {}
    sec_per_min = float(craft.get("etaSecondsPerCampaignMinute") or DEFAULT_SEC_PER_MIN)
    same_spool = int(craft.get("sameMapSpoolSeconds") or DEFAULT_SAME_MAP_SPOOL)
    launch_min = int(craft.get("pawnLauncherSpoolSecondsMin") or DEFAULT_LAUNCHER_MIN)
    launch_max = int(craft.get("pawnLauncherSpoolSecondsMax") or DEFAULT_LAUNCHER_MAX)

    info = resolve_listing_delivery(listing, listing_id, workspace)
    mode = info["mode"]
    dest = canonical_map_id(dest_map_id) if dest_map_id else ""
    dest_label = map_label(dest, workspace) if dest else "current sortie"

    if mode == "immediate" or not info.get("deferred"):
        return {
            **info,
            "destMapId": dest or None,
            "destLabel": dest_label,
            "hops": 0,
            "travelMinutes": 0.0,
            "etaSeconds": 0,
            "route": [],
            "routeLabels": [],
            "etaText": "ready with your drop",
            "summary": "Deploys with your kit.",
        }

    if mode == "pawn_launcher":
        eta_s = int(round((launch_min + launch_max) * 0.5))
        return {
            **info,
            "destMapId": dest or None,
            "destLabel": dest_label,
            "hops": 0,
            "travelMinutes": 0.0,
            "etaSeconds": eta_s,
            "route": [],
            "routeLabels": [],
            "etaText": f"~{eta_s // 60}:{eta_s % 60:02d} spool",
            "summary": f"Pawn launcher → near infil · ETA {eta_s // 60}:{eta_s % 60:02d}",
        }

    # map_web
    src = info.get("sourceMapId") or ""
    if not src or not dest:
        eta_s = same_spool
        return {
            **info,
            "destMapId": dest or None,
            "destLabel": dest_label,
            "hops": 0,
            "travelMinutes": 0.0,
            "etaSeconds": eta_s,
            "route": [src] if src else [],
            "routeLabels": [info["sourceLabel"]] if src else [],
            "etaText": f"~{eta_s}s spool",
            "summary": f"From {info['sourceLabel']} · ETA ~{eta_s}s",
        }

    route, minutes = shortest_map_route(str(src), dest, workspace)
    if minutes <= 0:
        eta_s = same_spool
        summary = f"Local from {info['sourceLabel']} · spool ~{eta_s}s"
        eta_text = f"~{eta_s}s spool"
    else:
        eta_s = max(30, int(round(minutes * sec_per_min)))
        labels = [map_label(m, workspace) for m in route]
        crumb = " → ".join(labels)
        summary = f"Via {crumb} · field ETA {eta_s // 60}:{eta_s % 60:02d}"
        eta_text = f"~{eta_s // 60}:{eta_s % 60:02d} via {info['sourceLabel']}"

    return {
        **info,
        "destMapId": dest,
        "destLabel": dest_label,
        "hops": max(0, len(route) - 1),
        "travelMinutes": round(float(minutes), 1),
        "etaSeconds": int(eta_s),
        "route": route,
        "routeLabels": [map_label(m, workspace) for m in route],
        "etaText": eta_text,
        "summary": summary,
    }


def make_pending_delivery(
    *,
    listing_id: str,
    listing: Dict[str, Any],
    dest_map_id: Optional[str],
    qty: int = 1,
    workspace: Optional[Path] = None,
    mission_number: int = 1,
) -> Optional[Dict[str, Any]]:
    """Build one pendingDeliveries record for a purchased deferred pack."""
    eta = delivery_eta(listing=listing, listing_id=listing_id, dest_map_id=dest_map_id, workspace=workspace)
    if not eta.get("deferred"):
        return None
    count = int(listing.get("count") or 0) * max(1, int(qty or 1))
    unit_def = listing.get("unitDef")
    if not unit_def or count <= 0:
        return None
    hmin = float(listing.get("spawnHealthFracMin") or 1.0)
    hmax = float(listing.get("spawnHealthFracMax") or 1.0)
    return {
        "id": f"pd_{listing_id}_{mission_number}_{qty}",
        "listingId": listing_id,
        "label": listing.get("label") or listing_id,
        "unitDef": unit_def,
        "count": count,
        "mode": eta.get("mode"),
        "sourceMapId": eta.get("sourceMapId"),
        "sourceSpaceId": eta.get("sourceSpaceId"),
        "sourceLabel": eta.get("sourceLabel"),
        "destMapId": eta.get("destMapId"),
        "destLabel": eta.get("destLabel"),
        "travelMinutes": eta.get("travelMinutes"),
        "etaSeconds": eta.get("etaSeconds"),
        "route": list(eta.get("route") or []),
        "routeLabels": list(eta.get("routeLabels") or []),
        "landNear": eta.get("landNear") or "infil",
        "status": "in_transit",
        "etaText": eta.get("etaText"),
        "summary": eta.get("summary"),
        "healthFracMin": hmin,
        "healthFracMax": hmax,
        "packageTag": listing_id,
    }


def main() -> int:
    import pprint

    ws = _workspace_root()
    demo = {
        "label": "Wasp Flight",
        "count": 4,
        "unitDef": "corape",
        "delivery": {"mode": "map_web", "sourceMapId": "eye_of_horus", "landNear": "infil"},
    }
    pprint.pp(delivery_eta(listing=demo, listing_id="wasp_flight", dest_map_id="greenest_fields", workspace=ws))
    pprint.pp(delivery_eta(listing=demo, listing_id="wasp_flight", dest_map_id="all_that_simmers", workspace=ws))
    punch = {
        "label": "Punch of Thugs",
        "count": 7,
        "unitDef": "corthud",
        "delivery": {"mode": "pawn_launcher", "landNear": "infil"},
    }
    pprint.pp(delivery_eta(listing=punch, listing_id="punch_of_thugs", dest_map_id="greenest_fields", workspace=ws))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
