#!/usr/bin/env python3
"""WO-020a: Build world_zone_graph.v1.json from authored zone maps + adjacency."""
from __future__ import annotations

import json
import sys
from pathlib import Path

WS = Path(__file__).resolve().parents[1]
AUTHORED = WS / "data" / "zone_maps" / "authored"
OUT = WS / "data" / "zone_maps" / "world_zone_graph.v1.json"
ADJ = AUTHORED / "zone_adjacency.json"

# Authored narrative cross-map links (campaign arc).
STRATEGIC_LINKS = [
    {"from": "GF_SE_STAGING", "to": "EOH_NW_CRATER_CAMP", "kind": "strategic_link", "cost": 2, "notes": "Greenest -> Eye corridor"},
    {"from": "EOH_SE_CORTEX_POCKET", "to": "KOOM_NW_GREEN_SHELF", "kind": "strategic_link", "cost": 2, "notes": "Eye -> Koom approach"},
    {"from": "KOOM_SE_GREEN_SHELF", "to": "TAB_NW_PLATEAU", "kind": "strategic_link", "cost": 2, "notes": "Koom south -> Tabula north"},
    {"from": "TAB_SE_PLATEAU", "to": "AB_WESTERN_MUSTER_GROUNDS", "kind": "strategic_link", "cost": 2, "notes": "Tabula -> Bastion"},
    {"from": "TAB_EASTERN_ROCK_GATES", "to": "RJ_NW_JUNGLE_SHELF", "kind": "strategic_link", "cost": 3, "notes": "Tabula east -> Rock Jungle"},
    {"from": "AB_EASTERN_BASTION_WALL", "to": "ATS_NW_CANOPY_START", "kind": "strategic_link", "cost": 3, "notes": "Bastion -> All That Simmers"},
    {"from": "RJ_SE_JUNGLE_SHELF", "to": "ATS_SW_ARMADA_LAGOON", "kind": "strategic_link", "cost": 3, "notes": "Jungle south -> Simmers"},
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
        edge = dict(link)
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
