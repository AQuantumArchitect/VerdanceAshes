#!/usr/bin/env python3
"""Measured hydrology: where the water goes, and what it costs when it does.

Spring's sea is a fixed plane at y=0 and there is no synced setter for it, so a
rising waterline is realised by sinking the world instead: lowering the whole
heightmap by D puts every cell below elevation D underwater, and because the
shift is uniform it changes no slope and no relative height -- only the shore
moves. `Spring.AdjustHeightMap(0, 0, mapSizeX, mapSizeZ, -D)` does that in one
engine call, and `RevertHeightMap` drains it.

That makes the waterline a single scalar per map, which is exactly what the
density matrix's hydrology anchor wants. This module measures what each value
of that scalar actually costs: how much ground drowns, how many extractor spots
go under, which zones become unusable, and which basins fill first.

    python tools/hydrology_v1.py
    python tools/hydrology_v1.py --maps koom_valley --steps 12
"""

from __future__ import annotations

import argparse
import heapq
import json
import sys
from collections import deque
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

WS_DEFAULT = Path(__file__).resolve().parents[1]

from zone_cartographer_v1 import CH, COMPASS_CODE  # noqa: E402

SCHEMA = "verdance-hydrology/1.0"

# Spring's water plane. Terrain below this is submerged.
SEA_LEVEL = 0.0

# The waterline ladder stops here: past half the map underwater there is no
# game left to play, only a boat race.
MAX_SUBMERGED_SHARE = 0.50

# How far the planet's water cycle actually swings each map, as a fraction of
# MAX_SUBMERGED_SHARE. This is a DESIGN dial, not a measurement: the owner wants
# water to matter on Koom Valley, Tabula and All That Simmers, and Koom to be
# the dramatic one. Greenest Fields is a bone-dry metal-free desert -- flooding
# it would be a lie about the map, so its amplitude is zero and none of the
# hydrology roles or camp exclusions fire there at all.
MAP_AMPLITUDE = {
    "koom_valley": 1.0,
    "tabula": 1.0,
    "all_that_simmers": 1.0,
    "the_rock_jungle": 0.6,     # already a quarter underwater at rest
    "eye_of_horus": 0.3,
    "ancient_bastion": 0.25,
    "greenest_fields": 0.0,
}
DEFAULT_AMPLITUDE = 0.5

# A submerged component smaller than this is a puddle, not a basin.
MIN_BASIN_SHARE = 0.02

# A zone is "flooded" once this much of it is under water.
ZONE_FLOODED_AT = 0.5


def load_json(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def components(res: int, member: Sequence[bool]) -> List[List[int]]:
    """Four-connected components over the cells where member is True."""
    seen = [False] * (res * res)
    out: List[List[int]] = []
    for start in range(res * res):
        if seen[start] or not member[start]:
            continue
        comp: List[int] = []
        queue = deque([start])
        seen[start] = True
        while queue:
            idx = queue.popleft()
            comp.append(idx)
            row, col = divmod(idx, res)
            for nb, ok in ((idx - res, row > 0), (idx + res, row < res - 1),
                           (idx - 1, col > 0), (idx + 1, col < res - 1)):
                if ok and not seen[nb] and member[nb]:
                    seen[nb] = True
                    queue.append(nb)
        out.append(comp)
    out.sort(key=len, reverse=True)
    return out


def closed_depressions(heights: Sequence[float], res: int) -> Dict[str, Any]:
    """Priority flood: how high water would stand in each cell if it rose from
    off-map. Cells where that exceeds the ground are in a real depression.

    This is descriptive metadata -- a map whose low ground runs to the edge (Koom
    Valley's central valley does) has no closed depression at all, and still
    floods perfectly well when the waterline rises."""
    n = res * res
    spill = [float("inf")] * n
    heap: List[Tuple[float, int]] = []
    for idx in range(n):
        row, col = divmod(idx, res)
        if row in (0, res - 1) or col in (0, res - 1):
            spill[idx] = heights[idx]
            heapq.heappush(heap, (heights[idx], idx))
    while heap:
        level, idx = heapq.heappop(heap)
        if level > spill[idx]:
            continue
        row, col = divmod(idx, res)
        for nb, ok in ((idx - res, row > 0), (idx + res, row < res - 1),
                       (idx - 1, col > 0), (idx + 1, col < res - 1)):
            if not ok:
                continue
            candidate = max(heights[nb], level)
            if candidate < spill[nb] - 1e-9:
                spill[nb] = candidate
                heapq.heappush(heap, (candidate, nb))
    sunk = [spill[i] > heights[i] + 1e-6 for i in range(n)]
    comps = components(res, sunk)
    out = []
    for comp in comps:
        if len(comp) / n < MIN_BASIN_SHARE:
            continue
        out.append({
            "cells": len(comp),
            "areaShare": round(len(comp) / n, 4),
            "spillLevel": round(min(spill[i] for i in comp), 1),
            "floor": round(min(heights[i] for i in comp), 1),
        })
    return {"count": len(out), "depressions": out}


def compass_of(cells: Sequence[int], res: int) -> str:
    rows = [divmod(i, res)[0] for i in cells]
    cols = [divmod(i, res)[1] for i in cells]
    cz = (sum(rows) / len(rows)) / res
    cx = (sum(cols) / len(cols)) / res
    ns = "North" if cz < 0.34 else ("South" if cz > 0.66 else "")
    ew = "West" if cx < 0.34 else ("East" if cx > 0.66 else "")
    name = (ns + ew) if (ns and ew) else (ns or ew or "Central")
    return COMPASS_CODE.get(name, "C")


def waterline_ladder(heights: Sequence[float], steps: int,
                     amplitude: float = 1.0) -> List[float]:
    """Absolute elevations for normalized flood 0.0 .. 1.0.

    Rungs are spaced by AREA, not by elevation, so one step of the dial drowns
    the same share of every map. Even elevation steps would be useless here:
    Ancient Bastion's middle is a flat plain that goes from 1% to 50% underwater
    inside two elmos of waterline, while Koom Valley's valley fills gradually.

    Step 0 is the map's resting state -- real sea level where the map has water,
    and the low point where it sits entirely above the sea (Koom Valley's floor
    is 401 elmos up, so dry IS step 0 for it)."""
    ordered = sorted(heights)
    n = len(ordered)

    def area_at(level: float) -> float:
        lo, hi = 0, n
        while lo < hi:
            mid = (lo + hi) // 2
            if ordered[mid] <= level:
                lo = mid + 1
            else:
                hi = mid
        return lo / n

    def level_for_area(share: float) -> float:
        idx = min(n - 1, max(0, int(round(share * n)) - 1))
        return ordered[idx]

    resting = max(SEA_LEVEL, ordered[0])
    base_share = area_at(resting) if resting > ordered[0] else area_at(SEA_LEVEL)
    ceiling = max(base_share, MAX_SUBMERGED_SHARE * max(0.0, min(1.0, amplitude)))
    base_share = max(0.0, min(base_share, ceiling))
    span = ceiling - base_share

    out: List[float] = []
    for i in range(steps):
        share = base_share + span * (i / float(steps - 1))
        level = resting if i == 0 else level_for_area(share)
        # Monotone: a higher rung can never sit below a lower one.
        if out and level < out[-1]:
            level = out[-1]
        out.append(round(level, 1))
    return out


def spot_heights(terrain: Dict[str, Any]) -> List[float]:
    res = int(terrain["grid"]["res"])
    heights = [c[CH["height"]] for c in terrain["cells"]]
    sx = float(terrain["size"]["x"])
    sz = float(terrain["size"]["z"])
    out = []
    for spot in terrain.get("metalSpots") or []:
        col = min(res - 1, max(0, int(float(spot["x"]) / sx * res)))
        row = min(res - 1, max(0, int(float(spot["z"]) / sz * res)))
        out.append(heights[row * res + col])
    return out


def profile(terrain: Dict[str, Any], steps: int = 9,
            zones: Optional[Sequence[Dict[str, Any]]] = None,
            amplitude: Optional[float] = None) -> Dict[str, Any]:
    res = int(terrain["grid"]["res"])
    n = res * res
    map_id = str(terrain.get("mapId") or "")
    if amplitude is None:
        amplitude = MAP_AMPLITUDE.get(map_id, DEFAULT_AMPLITUDE)
    heights = [c[CH["height"]] for c in terrain["cells"]]
    ladder = waterline_ladder(heights, steps, amplitude)
    spots = spot_heights(terrain)

    # Basins are named at FULL flood, where they are fewest and largest, then
    # inherited downward. Naming them per rung instead would rename a basin the
    # moment two puddles merged, and a beat that says "flood BASIN_C" would
    # start pointing at different ground between missions.
    full_mask = [h <= ladder[-1] for h in heights]
    canonical: List[Dict[str, Any]] = []
    owner = [-1] * n
    for comp in components(res, full_mask):
        if len(comp) / n < MIN_BASIN_SHARE:
            continue
        code = compass_of(comp, res)
        bid = f"BASIN_{code}"
        suffix = 1
        while any(b["basinId"] == bid for b in canonical):
            suffix += 1
            bid = f"BASIN_{code}{suffix}"
        slot = len(canonical)
        for j in comp:
            owner[j] = slot
        canonical.append({
            "basinId": bid,
            "floor": round(min(heights[j] for j in comp), 1),
            "firstLevel": None,
            "cellsAtFull": len(comp),
            "areaShareAtFull": round(len(comp) / n, 4),
            "cells": comp,
        })

    rungs: List[Dict[str, Any]] = []
    for i, level in enumerate(ladder):
        norm = round(i / float(steps - 1), 3)
        mask = [h <= level for h in heights]
        area = sum(1 for m in mask if m) / n
        lost = (sum(1 for h in spots if h <= level) / len(spots)) if spots else 0.0
        present: List[str] = []
        for comp in components(res, mask):
            if len(comp) / n < MIN_BASIN_SHARE:
                continue
            slots = {owner[j] for j in comp if owner[j] >= 0}
            for slot in sorted(slots):
                bid = canonical[slot]["basinId"]
                if bid in present:
                    continue
                present.append(bid)
                if canonical[slot]["firstLevel"] is None:
                    canonical[slot]["firstLevel"] = norm
        rungs.append({
            "level": norm,
            "elevation": level,
            "terraformDelta": round(level - SEA_LEVEL, 1),
            "areaSubmerged": round(area, 4),
            "metalSpotsSubmerged": round(lost, 4),
            "basins": present,
        })
    basin_seen = {b["basinId"]: b for b in canonical}

    zone_flood: Dict[str, Any] = {}
    if zones:
        for zone in zones:
            cells = zone_cells(zone, res)
            if not cells:
                continue
            fractions = []
            for level in ladder:
                wet = sum(1 for j in cells if heights[j] <= level)
                fractions.append(round(wet / len(cells), 3))
            flood_at = None
            for i, frac in enumerate(fractions):
                if frac >= ZONE_FLOODED_AT:
                    flood_at = round(i / float(steps - 1), 3)
                    break
            zone_flood[str(zone.get("zoneId"))] = {
                "submergedAt": fractions,
                "floodsAt": flood_at,
                "restingSubmerged": fractions[0],
            }

    return {
        "schemaVersion": SCHEMA,
        "mapId": terrain.get("mapId"),
        "mapName": terrain.get("mapName"),
        "res": res,
        "seaLevel": SEA_LEVEL,
        "amplitude": round(float(amplitude), 3),
        "restingElevation": ladder[0],
        "levels": [r["level"] for r in rungs],
        "elevations": ladder,
        "rungs": [{k: v for k, v in r.items()} for r in rungs],
        "basins": [{k: v for k, v in b.items() if k != "cells"}
                   for b in basin_seen.values()],
        "basinCells": {b["basinId"]: b["cells"] for b in basin_seen.values()},
        "closedDepressions": closed_depressions(heights, res),
        "zones": zone_flood,
    }


def zone_cells(zone: Dict[str, Any], res: int) -> List[int]:
    """Cells of a schema-2.0 zone (RLE) or a legacy rect zone."""
    runs = zone.get("cells")
    if runs:
        out: List[int] = []
        for start, length in runs:
            out.extend(range(int(start), int(start) + int(length)))
        return out
    bounds = zone.get("bounds") or {}
    if not bounds:
        return []
    out = []
    for r in range(res):
        zn = (r + 0.5) / res
        if not (float(bounds["zMin"]) <= zn < float(bounds["zMax"])):
            continue
        for c in range(res):
            if float(bounds["xMin"]) <= (c + 0.5) / res < float(bounds["xMax"]):
                out.append(r * res + c)
    return out


def rung_for_level(prof: Dict[str, Any], level: float) -> Dict[str, Any]:
    """Nearest measured rung to a normalized water level."""
    rungs = prof["rungs"]
    return min(rungs, key=lambda r: abs(float(r["level"]) - float(level)))


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Measure map hydrology from terrain rasters")
    ap.add_argument("--workspace", default=str(WS_DEFAULT))
    ap.add_argument("--maps", default="")
    ap.add_argument("--steps", type=int, default=9)
    ap.add_argument("--amplitude", type=float, default=-1.0,
                    help="override the per-map water-cycle amplitude")
    ap.add_argument("--zones", default="authored",
                    help="zone map directory under data/zone_maps (or 'none')")
    args = ap.parse_args(argv)

    ws = Path(args.workspace)
    wanted = [m.strip() for m in args.maps.split(",") if m.strip()]
    paths = sorted((ws / "data" / "terrain").glob("*.terrain.json"))
    if wanted:
        paths = [p for p in paths if p.name.split(".")[0] in wanted]
    if not paths:
        print("no terrain rasters found", file=sys.stderr)
        return 1

    out_dir = ws / "data" / "hydrology"
    out_dir.mkdir(parents=True, exist_ok=True)
    print(f"{'map':<18}{'amp':>6}{'resting':>9}{'half-flood':>12}{'spots lost':>12}  basins")
    for path in paths:
        terrain = load_json(path)
        map_id = str(terrain.get("mapId"))
        zones = None
        if args.zones != "none":
            zp = ws / "data" / "zone_maps" / args.zones / f"{map_id}.authored.zone_map.json"
            if not zp.exists():
                zp = ws / "data" / "zone_maps" / args.zones / f"{map_id}.zone_map.json"
            if zp.exists():
                zones = load_json(zp).get("zones")
        amp = None if args.amplitude < 0 else args.amplitude
        prof = profile(terrain, args.steps, zones, amp)
        dest = out_dir / f"{map_id}.hydrology.json"
        dest.write_text(json.dumps(prof, indent=2), encoding="utf-8")
        mid = rung_for_level(prof, 0.5)
        names = ",".join(b["basinId"] for b in prof["basins"]) or "none"
        print(f"{map_id:<18}{prof['amplitude']:6.2f}{prof['restingElevation']:9.0f}"
              f"{mid['areaSubmerged'] * 100:11.1f}%{mid['metalSpotsSubmerged'] * 100:11.1f}%  {names}")
    print(f"-> {out_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
