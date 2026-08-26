#!/usr/bin/env python3
"""Validate world_zone_graph.v1.json structure and edge endpoints."""
from __future__ import annotations

import json
import sys
from pathlib import Path

WS = Path(__file__).resolve().parents[1]
GRAPH = WS / "data" / "zone_maps" / "world_zone_graph.v1.json"


def main() -> int:
    if not GRAPH.exists():
        print(f"MISSING {GRAPH}", file=sys.stderr)
        return 2
    g = json.loads(GRAPH.read_text(encoding="utf-8"))
    nodes = {n["zoneId"]: n for n in g.get("nodes") or [] if n.get("zoneId")}
    errors = []
    if g.get("schemaVersion") != "verdance-world-zone-graph/1.0":
        errors.append(f"bad schemaVersion {g.get('schemaVersion')}")
    if len(nodes) < 40:
        errors.append(f"expected ~45 nodes, got {len(nodes)}")
    for e in g.get("edges") or []:
        for end in ("from", "to"):
            if e.get(end) not in nodes:
                errors.append(f"edge {e} missing node {e.get(end)}")
    kinds = {}
    for e in g.get("edges") or []:
        k = e.get("kind") or "?"
        kinds[k] = kinds.get(k, 0) + 1
    if errors:
        print("INVALID")
        for err in errors:
            print(" -", err)
        return 1
    print(f"OK nodes={len(nodes)} edges={len(g.get('edges') or [])} kinds={kinds}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
