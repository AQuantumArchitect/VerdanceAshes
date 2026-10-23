#!/usr/bin/env python3
"""Build world_zone_graph.v1.json from the authored zone maps, their adjacency, and the roads."""
from __future__ import annotations

import json
import sys
from pathlib import Path

WS = Path(__file__).resolve().parents[1]
AUTHORED = WS / "data" / "zone_maps" / "authored"
OUT = WS / "data" / "zone_maps" / "world_zone_graph.v1.json"
ADJ = AUTHORED / "zone_adjacency.json"

# The roads between maps (owner-approved rewiring, 2026-10-23). Each end is a door:
# a corner or edge zone of its map, never a finale pad. A ring runs
# Rock Jungle -> Greenest Fields -> Koom Valley -> Tabula -> Ancient Bastion ->
# All That Simmers -> Eye of Horus -> Rock Jungle, with one shortcut from the
# Rock Jungle to Tabula. The first road is the start road.
STRATEGIC_LINKS = [
    {"from": "TRJ_NW_OUTER_MUSTER", "to": "GF_NW_MUSTER", "travelMinutes": 16, "notes": "The start road: home to Greenest Fields"},
    {"from": "GF_SE_PLATEAU", "to": "KV_NW_MUSTER", "travelMinutes": 16, "notes": "Greenest Fields' lower desert to Koom Valley"},
    {"from": "KV_SE_MUSTER", "to": "T_NW_RESERVE", "travelMinutes": 15, "notes": "Koom Valley to Tabula"},
    {"from": "T_SE_RESERVE", "to": "AB_NE_HEIGHTS", "travelMinutes": 18, "notes": "Tabula to the Bastion's north heights"},
    {"from": "AB_SE_HEIGHTS", "to": "ATS_NW_SHORE", "travelMinutes": 24, "notes": "The Bastion's south heights to All That Simmers"},
    {"from": "ATS_SW_MUSTER", "to": "EOH_SE_BASTION", "travelMinutes": 20, "notes": "All That Simmers to the Eye"},
    {"from": "EOH_NW_BASTION", "to": "TRJ_SE_OUTER_MUSTER", "travelMinutes": 20, "notes": "The Eye back home"},
    {"from": "T_W_CAUSEWAY", "to": "TRJ_NE_RIM", "travelMinutes": 22, "notes": "The shortcut: Tabula's west causeway to home"},
]


def load(p: Path):
    return json.loads(p.read_text(encoding="utf-8-sig"))


def main() -> int:
    adj = load(ADJ) if ADJ.exists() else {}
    nodes = []
    edges = []
    edge_set = set()

    for f in sorted(AUTHORED.glob("*.authored.zone_map.json")):
        data = load(f)
        map_id = data.get("mapId") or f.name.split(".")[0]
        map_name = data.get("mapName") or map_id
        for z in data.get("zones") or []:
            zid = z.get("zoneId")
            if not zid:
                continue
            tags = list(z.get("tags") or [])
            # Schema 2.0 zones answer these themselves: a zone with no dry
            # buildable ground cannot host a deploy or an extraction.
            camp_ok = z.get("campEligible")
            deploy = z.get("deployEligible")
            if deploy is None:
                deploy = "start" in tags or "shelf" in str(z.get("role", "")).lower()
            extract = z.get("extractEligible")
            if extract is None:
                extract = True
            node = {
                "zoneId": zid,
                "mapId": map_id,
                "mapName": map_name,
                "label": z.get("label") or zid,
                "role": z.get("role"),
                "tags": tags,
                "bounds": z.get("bounds"),
                "deployEligible": bool(deploy) and camp_ok is not False,
                "extractEligible": bool(extract) and camp_ok is not False,
            }
            if z.get("anchor"):
                node["anchor"] = z["anchor"]
            if z.get("evidence"):
                node["evidence"] = z["evidence"]
            nodes.append(node)
        map_adj = adj.get(map_id) or {}
        for src, nbrs in map_adj.items():
            for dst in nbrs or []:
                key = tuple(sorted((src, dst))) + ("same_map",)
                if key in edge_set:
                    continue
                edge_set.add(key)
                edges.append({
                    "from": src,
                    "to": dst,
                    "kind": "same_map",
                    "cost": 1,
                    "mapId": map_id,
                })

    # Cross-map arc links are authored against zone ids. After a remap those ids
    # change, so translate through the migration map and say plainly when a link
    # can no longer be placed rather than emitting an edge into nothing.
    migration = load(AUTHORED / "zone_id_migration.json") if (AUTHORED / "zone_id_migration.json").exists() else {}
    id_map = (migration.get("zones") if isinstance(migration, dict) else None) or migration or {}
    known = {n["zoneId"] for n in nodes}
    for link in STRATEGIC_LINKS:
        edge = {"kind": "strategic_link", "cost": 2, **link}
        for end in ("from", "to"):
            mapped = id_map.get(edge[end])
            if isinstance(mapped, str):
                edge[end] = mapped
        if edge["from"] not in known or edge["to"] not in known:
            print(f"  warning: strategic link {link['from']} -> {link['to']} "
                  "has no surviving zone; skipped")
            continue
        edges.append(edge)

    graph = {
        "schemaVersion": "verdance-world-zone-graph/1.0",
        "nodeCount": len(nodes),
        "edgeCount": len(edges),
        "nodes": nodes,
        "edges": edges,
        "notes": "Same-map edges from zone_adjacency.json; strategic_link edges authored for campaign arc.",
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(graph, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {OUT} nodes={len(nodes)} edges={len(edges)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
