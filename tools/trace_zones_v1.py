#!/usr/bin/env python3
"""Trace a map's zones from what is drawn on it.

The cartographer (tools/zone_cartographer_v1.py) cuts zones from bot behaviour,
which on a map with strong built features can slice straight through them: on
Ancient Bastion it cut the castle into horizontal strips and called a crater
field a bastion. A trace follows the map's own shapes instead -- the castle's
paved floor, the three outer walls, the crater basin, the highlands -- read off
the measured terrain raster, and keeps the cartographer's evidence, anchors and
hydrology so every consumer reads it the same way.

Output goes to data/zone_maps/derived/; tools/migrate_zone_ids_v1.py promotes
it and carries the campaign across.

    python tools/trace_zones_v1.py --maps ancient_bastion
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, deque
from pathlib import Path
from typing import Callable, Dict, List, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parent))
import map_symmetry_v1  # noqa: E402
import zone_cartographer_v1 as carto  # noqa: E402

WS_DEFAULT = Path(__file__).resolve().parents[1]
CH = carto.CH


def smoothed(grid: carto.CellGrid, channel: str) -> List[float]:
    """3x3 mean of a terrain channel, so a threshold follows ground, not noise."""
    res, k = grid.res, CH[channel]
    out = []
    for r in range(res):
        for q in range(res):
            vals = [grid.cells[rr * res + qq][k]
                    for rr in range(max(0, r - 1), min(res, r + 2))
                    for qq in range(max(0, q - 1), min(res, q + 2))]
            out.append(sum(vals) / len(vals))
    return out


# --- Ancient Bastion ---------------------------------------------------------
# A 2:1 map, mirrored north/south. West: a castle on a paved plateau -- the keep,
# a rampart wing with a round tower at each end, two gatehouses on its east face.
# Outside its corners, a rocky tor. Then three detached walls (north, centre,
# south) across the approach; then a crater basin; then highlands along the north
# and south edges, meeting in a ridge that runs into the basin from the east.

AB_ZONES = {
    # id: (label, role)
    "AB_W_KEEP": ("The Keep", "fortress"),
    "AB_W_GATEHOUSES": ("Gatehouses", "gate"),
    "AB_NW_RAMPART": ("North Rampart", "citadel"),
    "AB_SW_RAMPART": ("South Rampart", "citadel"),
    "AB_NW_TOR": ("Northwest Tor", "reserve"),
    "AB_SW_TOR": ("Southwest Tor", "reserve"),
    "AB_N_WALL": ("North Wall", "causeway"),
    "AB_C_WALL": ("Centre Wall", "lane"),
    "AB_S_WALL": ("South Wall", "causeway"),
    "AB_NE_CRATERS": ("North Craters", "main_field"),
    "AB_SE_CRATERS": ("South Craters", "main_field"),
    "AB_NE_HEIGHTS": ("North Heights", "plateau"),
    "AB_SE_HEIGHTS": ("South Heights", "plateau"),
    "AB_E_RIDGE": ("East Ridge", "rim_control"),
}


def trace_ancient_bastion(grid: carto.CellGrid) -> Dict[int, str]:
    height = smoothed(grid, "height")
    owner: Dict[int, str] = {}
    for i in range(grid.res * grid.res):
        x, z = grid.cell_norm(i)
        north = z < 0.5
        m = z if north else 1.0 - z           # distance from the nearer long edge
        paved = grid.cells[i][CH["tankSpeed"]] >= 1.05
        if x < 0.33:
            if paved:
                if m < 0.285:
                    owner[i] = "AB_NW_RAMPART" if north else "AB_SW_RAMPART"
                elif x < 0.225:
                    owner[i] = "AB_W_KEEP"
                else:
                    owner[i] = "AB_W_GATEHOUSES"
            elif m >= 0.285 and x >= 0.2:
                owner[i] = "AB_W_GATEHOUSES"   # the forecourt between the gates
            else:
                owner[i] = "AB_NW_TOR" if north else "AB_SW_TOR"
        elif x < 0.52:
            owner[i] = ("AB_N_WALL" if north else "AB_S_WALL") if m < 0.3 else "AB_C_WALL"
        elif height[i] >= 235.0:
            if m >= 0.3 and x > 0.7:
                owner[i] = "AB_E_RIDGE"
            else:
                owner[i] = "AB_NE_HEIGHTS" if north else "AB_SE_HEIGHTS"
        else:
            owner[i] = "AB_NE_CRATERS" if north else "AB_SE_CRATERS"
    return owner


TRACES: Dict[str, Tuple[Callable[[carto.CellGrid], Dict[int, str]], Dict[str, Tuple[str, str]]]] = {
    "ancient_bastion": (trace_ancient_bastion, AB_ZONES),
}


def one_piece(grid: carto.CellGrid, owner: Dict[int, str]) -> Dict[int, str]:
    """Every zone in one connected piece: strays join the neighbour they touch most."""
    res = grid.res

    def nbrs(i: int):
        r, q = divmod(i, res)
        for dr, dq in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            rr, qq = r + dr, q + dq
            if 0 <= rr < res and 0 <= qq < res:
                yield rr * res + qq

    for _ in range(8):
        moved = False
        pieces: Dict[str, List[List[int]]] = {}
        seen: set = set()
        for i in owner:
            if i in seen:
                continue
            zid, comp, dq = owner[i], [], deque([i])
            seen.add(i)
            while dq:
                c = dq.popleft()
                comp.append(c)
                for n in nbrs(c):
                    if n not in seen and owner[n] == zid:
                        seen.add(n)
                        dq.append(n)
            pieces.setdefault(zid, []).append(comp)
        for zid, comps in pieces.items():
            comps.sort(key=len, reverse=True)
            for comp in comps[1:]:
                touch = Counter(owner[n] for c in comp for n in nbrs(c) if owner[n] != zid)
                if touch:
                    new = touch.most_common(1)[0][0]
                    for c in comp:
                        owner[c] = new
                    moved = True
        if not moved:
            break
    return owner


def zone_record(grid: carto.CellGrid, zid: str, label: str, role: str, cells: List[int]) -> Dict:
    sig = carto.region_signature(grid, cells)
    routine = carto.routine_waterline(grid)
    anchor_idx = carto.pick_anchor(grid, cells, dry_above=routine)
    flood_safe = anchor_idx is not None
    if anchor_idx is None:
        anchor_idx = carto.pick_anchor(grid, cells)
    anchor = None
    if anchor_idx is not None:
        ax, az = grid.cell_norm(anchor_idx)
        anchor = {"x": round(ax, 4), "z": round(az, 4)}
    rows = [divmod(i, grid.res)[0] for i in cells]
    cols = [divmod(i, grid.res)[1] for i in cells]
    cx = sum(grid.cell_norm(i)[0] for i in cells) / len(cells)
    cz = sum(grid.cell_norm(i)[1] for i in cells) / len(cells)
    tags = []
    if sig["relativeHeight"] >= 0.55:
        tags.append("high")
    elif sig["relativeHeight"] <= 0.3:
        tags.append("low")
    if sig["metal"] >= 0.5:
        tags.append("metal")
    if sig["choke"] >= 0.55:
        tags.append("choke")
    if sig["contest"] >= 0.35:
        tags.append("contested")
    if sig["hasStart"]:
        tags.append("start")
    if role in ("fortress", "citadel", "gate"):
        tags.append("fortress")
    tags.append(carto.compass_name(cx, cz).lower())
    return {
        "zoneId": zid,
        "label": label,
        "role": role,
        "shape": "cells",
        "cellGrid": {"cols": grid.res, "rows": grid.res},
        "cells": carto.rle(cells),
        "bounds": {
            "xMin": round(min(cols) / grid.res, 4), "xMax": round((max(cols) + 1) / grid.res, 4),
            "zMin": round(min(rows) / grid.res, 4), "zMax": round((max(rows) + 1) / grid.res, 4),
        },
        "anchor": anchor,
        "campEligible": anchor is not None and flood_safe,
        "deployEligible": anchor is not None and flood_safe,
        "extractEligible": anchor is not None and flood_safe,
        "symmetryFamily": zid.replace("_NW_", "_W_").replace("_SW_", "_W_").replace("_NE_", "_E_")
                             .replace("_SE_", "_E_").replace("_N_", "_C_").replace("_S_", "_C_"),
        "hydrology": {
            "floodsAt": sig["floodsAt"],
            "restingSubmerged": sig["restingSubmerged"],
            "submergedAt": sig.get("submergedAt", []),
            "metalSpots": sig.get("metalSpots", 0),
            "drownedMetal": sig.get("drownedMetal", 0.0),
            "anchorAboveWaterline": flood_safe,
        },
        "tags": tags,
        "evidence": {k: round(v, 4) if isinstance(v, float) else v
                     for k, v in sig.items() if k != "submergedAt"},
    }


def trace(ws: Path, map_id: str) -> Dict:
    fn, names = TRACES[map_id]
    terrain = carto.load_json(ws / "data" / "terrain" / f"{map_id}.terrain.json")
    bdir = ws / "data" / "behavior" / map_id
    rasters = [r for r in (carto.load_json(p) for p in sorted(bdir.glob("*.raster.json"))) if r] if bdir.exists() else []
    symmetry = map_symmetry_v1.detect(terrain, 0.90)
    hydrology = carto.load_json(ws / "data" / "hydrology" / f"{map_id}.hydrology.json")
    grid = carto.CellGrid(terrain, rasters, symmetry=symmetry, hydrology=hydrology)
    owner = one_piece(grid, fn(grid))
    by_zone: Dict[str, List[int]] = {}
    for i, zid in owner.items():
        by_zone.setdefault(zid, []).append(i)
    missing = set(names) - set(by_zone)
    if missing:
        raise SystemExit(f"{map_id}: trace lost zones {sorted(missing)}")
    zones = [zone_record(grid, zid, *names[zid], sorted(by_zone[zid])) for zid in names]
    return {
        "schemaVersion": carto.ZONE_SCHEMA,
        "mapId": map_id,
        "mapName": grid.map_name,
        "coordinateSystem": "normalized-xz",
        "authoringStatus": "traced",
        "grid": {"res": grid.res},
        "targetZoneRange": [len(zones), len(zones)],
        "symmetry": {
            "group": (symmetry or {}).get("group", ["identity"]),
            "order": (symmetry or {}).get("order", 1),
            "scores": (symmetry or {}).get("scores", {}),
            "accepted": (symmetry or {}).get("accepted", []),
        },
        "hydrologyRef": f"data/hydrology/{map_id}.hydrology.json" if hydrology else None,
        "waterline": {
            "levels": (hydrology or {}).get("levels", []),
            "elevations": (hydrology or {}).get("elevations", []),
            "routine": carto.routine_waterline(grid),
            "basins": [b["basinId"] for b in (hydrology or {}).get("basins", [])],
        },
        "derivedFrom": {
            "terrain": f"data/terrain/{map_id}.terrain.json",
            "configs": grid.configs,
            "measuredActivity": round(grid.total_presence, 1),
            "behaviourSource": grid.behaviour_source,
        },
        "notes": ("Traced by tools/trace_zones_v1.py along the map's own features (paved castle "
                  "floor, outer walls, crater basin, highlands) read off the terrain raster; "
                  "evidence, anchors and hydrology measured as the cartographer measures them. "
                  "Cells are run-length encoded [startIndex, length] over a row-major cellGrid."),
        "zones": zones,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--workspace", default=str(WS_DEFAULT))
    ap.add_argument("--maps", default=",".join(TRACES))
    ap.add_argument("--out-dir", default="")
    args = ap.parse_args()
    ws = Path(args.workspace)
    out_dir = Path(args.out_dir) if args.out_dir else ws / "data" / "zone_maps" / "derived"
    out_dir.mkdir(parents=True, exist_ok=True)
    for map_id in [m.strip() for m in args.maps.split(",") if m.strip()]:
        zm = trace(ws, map_id)
        (out_dir / f"{map_id}.authored.zone_map.json").write_text(json.dumps(zm, indent=1), encoding="utf-8")
        print(f"{map_id}: " + ", ".join(f"{z['zoneId']}({len(sum((list(range(a, a + n)) for a, n in z['cells']), []))})"
                                        for z in zm["zones"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
