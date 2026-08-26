#!/usr/bin/env python3
"""Describe measured maps. No verdicts.

Reads data/terrain/*.terrain.json (produced by the cartography terrain pass)
and writes a purely descriptive atlas: what each map IS, as the engine sees it.

This tool deliberately does NOT score, grade, or compare maps against any
target. It reports measurements and draws pictures; what those measurements
should imply about zones is a separate, human decision.

    python tools/terrain_atlas_v1.py
    python tools/terrain_atlas_v1.py --maps koom_valley,tabula
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, deque
from pathlib import Path
from typing import Any, Dict, List, Sequence, Tuple

WS_DEFAULT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parent))

from zone_cartographer_v1 import CellGrid, CH  # noqa: E402

RAMP = " .:-=+*#%@"


def load_json(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def components(res: int, member: Sequence[bool]) -> List[List[int]]:
    """Four-connected components over the cells where member is True."""
    seen = [False] * (res * res)
    out: List[List[int]] = []
    for start in range(res * res):
        if seen[start] or not member[start]:
            continue
        comp = []
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


def quantiles(values: Sequence[float]) -> Tuple[float, float, float, float, float]:
    s = sorted(values)
    n = len(s)
    return s[0], s[n // 4], s[n // 2], s[(3 * n) // 4], s[-1]


def histogram(values: Sequence[float], bins: int = 12) -> List[Tuple[float, float, int]]:
    lo, hi = min(values), max(values)
    if hi <= lo:
        return [(lo, hi, len(values))]
    width = (hi - lo) / bins
    counts = Counter(min(bins - 1, int((v - lo) / width)) for v in values)
    return [(lo + b * width, lo + (b + 1) * width, counts.get(b, 0)) for b in range(bins)]


def picture(grid: CellGrid, step: int) -> List[str]:
    """Relief with water and impassable ground called out."""
    res = grid.res
    heights = [c[CH["height"]] for c in grid.cells]
    lo, hi = min(heights), max(heights)
    span = (hi - lo) or 1.0
    rows = []
    for r in range(0, res, step):
        line = ""
        for c in range(0, res, step):
            block = [(r + dr) * res + (c + dc)
                     for dr in range(step) for dc in range(step)
                     if r + dr < res and c + dc < res]
            wet = sum(1 for i in block if grid.cells[i][CH["water"]] >= 0.5)
            blocked = sum(1 for i in block if not grid.passable[i])
            if wet > len(block) / 2:
                line += "~"
            elif blocked > len(block) / 2:
                line += "X"
            else:
                mean = sum(heights[i] for i in block) / len(block)
                line += RAMP[min(len(RAMP) - 1, int((mean - lo) / span * len(RAMP)))]
        rows.append(line)
    return rows


def overlay(grid: CellGrid, step: int, marks: Dict[int, str]) -> List[str]:
    rows = picture(grid, step)
    out = [list(r) for r in rows]
    res = grid.res
    for idx, ch in marks.items():
        row, col = divmod(idx, res)
        r, c = row // step, col // step
        if r < len(out) and c < len(out[r]):
            out[r][c] = ch
    return ["".join(r) for r in out]


def describe(grid: CellGrid) -> Dict[str, Any]:
    res, n = grid.res, grid.res * grid.res
    cells = grid.cells
    heights = [c[CH["height"]] for c in cells]
    slopes = [c[CH["slope"]] for c in cells]
    water = [c[CH["water"]] for c in cells]
    build = [c[CH["buildable"]] for c in cells]
    tank = [c[CH["tankSpeed"]] for c in cells]
    ship = [c[CH["shipSpeed"]] for c in cells]

    wet = [w >= 0.5 for w in water]
    land_comps = components(res, grid.passable)
    water_comps = components(res, wet)

    choke_cells = [i for i in range(n) if grid.choke[i] >= 0.5 and grid.passable[i]]
    choke_comps = components(res, [i in set(choke_cells) for i in range(n)])

    spots = grid.metal_spots
    starts_idx = [grid.world_to_idx(x, z) for x, z in grid.starts]

    return {
        "mapId": grid.map_id,
        "mapName": grid.map_name,
        "size": grid.size,
        "res": res,
        "cellElmos": grid.size[0] / res,
        "height": quantiles(heights),
        "heightHist": histogram(heights),
        "slope": quantiles(slopes),
        "cliffShare": sum(1 for s in slopes if s >= 0.25) / n,
        "waterShare": sum(1 for w in wet if w) / n,
        "waterBodies": [len(c) / n for c in water_comps[:3]],
        "shipShare": sum(1 for s in ship if s > 0.05) / n,
        "buildableMean": sum(build) / n,
        "unbuildableShare": sum(1 for b in build if b < 0.5) / n,
        "tank": quantiles(tank),
        "passableShare": sum(1 for p in grid.passable if p) / n,
        "landComponents": [len(c) / n for c in land_comps[:4]],
        "chokeShare": len(choke_cells) / n,
        "chokePassages": len(choke_comps),
        "chokeSizes": [len(c) for c in choke_comps[:5]],
        "metalSpots": len(spots),
        "featureMetal": sum(c[CH["featureMetal"]] for c in cells),
        "starts": [(x / grid.size[0], z / grid.size[1]) for x, z in grid.starts],
        "startsIdx": starts_idx,
        "chokeIdx": choke_cells,
    }


def render(d: Dict[str, Any], grid: CellGrid, step: int) -> str:
    L: List[str] = []
    L.append(f"## {d['mapName']} (`{d['mapId']}`)")
    L.append("")
    sx, sz = d["size"]
    L.append(f"{sx:.0f} x {sz:.0f} elmos, sampled at {d['res']}x{d['res']} "
             f"({d['cellElmos']:.0f} elmos per cell).")
    L.append("")
    hmin, h25, hmed, h75, hmax = d["height"]
    smin, s25, smed, s75, smax = d["slope"]
    tmin, _, tmed, _, tmax = d["tank"]
    L.append("| Measure | Value |")
    L.append("|---|---|")
    L.append(f"| Height | {hmin:.0f} / {h25:.0f} / {hmed:.0f} / {h75:.0f} / {hmax:.0f} "
             f"(min/q1/med/q3/max), span {hmax - hmin:.0f} |")
    L.append(f"| Slope | med {smed:.3f}, q3 {s75:.3f}, max {smax:.3f}; "
             f"{d['cliffShare'] * 100:.1f}% of cells at slope >= 0.25 |")
    bodies = ", ".join(f"{b * 100:.1f}%" for b in d["waterBodies"])
    L.append(f"| Water | {d['waterShare'] * 100:.1f}% of cells"
             + (f"; largest bodies {bodies}" if bodies else "")
             + f"; ship-passable {d['shipShare'] * 100:.1f}% |")
    L.append(f"| Buildable | mean {d['buildableMean'] * 100:.1f}%; "
             f"{d['unbuildableShare'] * 100:.1f}% of cells below half buildable |")
    L.append(f"| Ground speed (tank) | {tmin:.2f} to {tmax:.2f}, median {tmed:.2f} |")
    L.append(f"| Walkable ground | {d['passableShare'] * 100:.1f}% of cells; "
             f"largest connected pieces "
             f"{', '.join(f'{c * 100:.0f}%' for c in d['landComponents'])} |")
    L.append(f"| Route load | {d['chokePassages']} cluster(s) of cells carrying at least "
             f"half the peak start-to-start route load, covering "
             f"{d['chokeShare'] * 100:.1f}% of the map (sizes {d['chokeSizes'] or 'n/a'}). "
             f"On open ground routes coincide without any physical narrowing; a "
             f"constriction shows up as a small cluster pinched between `X` or `~`. |")
    L.append(f"| Metal | {d['metalSpots']} extractor spots; "
             f"reclaimable feature metal {d['featureMetal']:.0f} |")
    starts = ", ".join(f"({x:.2f},{z:.2f})" for x, z in d["starts"]) or "none reported"
    L.append(f"| Map start positions | {len(d['starts'])}: {starts} |")
    L.append("")

    L.append("Height distribution (each bar is a share of the map at that elevation):")
    L.append("")
    L.append("```")
    total = sum(c for _, _, c in d["heightHist"]) or 1
    for lo, hi, c in d["heightHist"]:
        L.append(f"  {lo:6.0f}-{hi:6.0f}  {c / total * 100:5.1f}%  {'#' * int(c / total * 120)}")
    L.append("```")
    L.append("")

    marks = {i: "@" for i in d["startsIdx"]}
    for i in d["chokeIdx"]:
        marks.setdefault(i, "o")
    L.append("Relief, north at top, west at left. "
             "`@` map start, `o` cell most start-to-start routes cross, "
             "`~` water, `X` ground vehicles cannot cross, ` .:-=+*#%@` low to high:")
    L.append("")
    L.append("```")
    for row in overlay(grid, step, marks):
        L.append("  " + row)
    L.append("```")
    L.append("")
    return "\n".join(L)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Describe measured maps (no verdicts)")
    ap.add_argument("--workspace", default=str(WS_DEFAULT))
    ap.add_argument("--maps", default="")
    ap.add_argument("--out", default="")
    ap.add_argument("--step", type=int, default=2, help="cells per drawn character")
    args = ap.parse_args(argv)

    ws = Path(args.workspace)
    wanted = [m.strip() for m in args.maps.split(",") if m.strip()]
    terrain_dir = ws / "data" / "terrain"
    paths = sorted(terrain_dir.glob("*.terrain.json"))
    if wanted:
        paths = [p for p in paths if p.name.split(".")[0] in wanted]
    if not paths:
        print(f"no terrain rasters in {terrain_dir}", file=sys.stderr)
        return 1

    pool = {}
    pool_path = ws / "data" / "map_pool" / "seven_maps.json"
    if pool_path.exists():
        pool = {m["id"]: m for m in load_json(pool_path).get("maps", [])}

    sections: List[str] = []
    summary: List[str] = []
    for path in paths:
        grid = CellGrid(load_json(path), [])
        d = describe(grid)
        sections.append(render(d, grid, args.step))
        summary.append(
            f"| {d['mapId']} | {d['size'][0]:.0f}x{d['size'][1]:.0f} | "
            f"{d['height'][4] - d['height'][0]:.0f} | {d['waterShare'] * 100:.0f}% | "
            f"{d['cliffShare'] * 100:.0f}% | {d['passableShare'] * 100:.0f}% | "
            f"{len(d['landComponents']) and d['landComponents'][0] * 100:.0f}% | "
            f"{d['chokePassages']} | {d['metalSpots']} | {len(d['starts'])} |"
        )

    out: List[str] = []
    out.append("# Terrain atlas -- what the seven maps measure as")
    out.append("")
    out.append("Measured in-engine by `game_verdance_cartography.lua` "
               "(`scripts/run_zone_cartography_survey.ps1 -Mode terrain`). "
               "Description only: no map is being scored, and nothing here says "
               "what a zone map ought to look like.")
    out.append("")
    out.append("| Map | Size | Height span | Water | Cliff | Walkable | Largest piece | Route clusters | Metal spots | Starts |")
    out.append("|---|---|---|---|---|---|---|---|---|---|")
    out.extend(summary)
    out.append("")
    out.append("Column notes: *Cliff* is the share of cells at slope >= 0.25. "
               "*Walkable* is the share a ground vehicle can occupy; *largest piece* "
               "is how much of the map its biggest connected walkable region holds "
               "(100% means one landmass). *Route clusters* counts the separate "
               "runs of cells carrying at least half the peak start-to-start "
               "route load -- coincidence of routes, which on broken ground "
               "coincides with a physical constriction and on open ground does not.")
    out.append("")
    out.extend(sections)

    text = "\n".join(out)
    dest = Path(args.out) if args.out else ws / "outbox" / "terrain_atlas.latest.md"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(text, encoding="utf-8")
    print(f"{len(paths)} maps -> {dest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
