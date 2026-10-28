#!/usr/bin/env python3
"""Resolve spawn-configuration RULES into concrete cartography survey runs.

`data/cartography/spawn_configs.json` says things like "three teams, spread as far
apart as the map allows". This turns that into real start coordinates per map by
reading the map's terrain raster (authored start positions, buildability, metal,
water) when one exists, and falling back to geometry when it does not.

Output: data/cartography/run_plan.json  -- consumed by
scripts/run_zone_cartography_survey.ps1.

Usage:
  python tools/plan_cartography_runs_v1.py [--workspace .] [--maps a,b] [--configs x,y]
"""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

WS_DEFAULT = Path(__file__).resolve().parents[1]

PLAN_SCHEMA = "verdance-cartography-run-plan/1.0"

# Engine-measured sizes, kept as a fallback for maps with no terrain raster yet
# (same table scripts/new_seven_map_authored_surveys.ps1 uses).
FALLBACK_SIZES = {
    "all_that_simmers": (7168, 10240),
    "koom_valley": (12288, 8192),
    "tabula": (8192, 7168),
    "ancient_bastion": (16384, 8192),
    "the_rock_jungle": (10240, 8192),
    "eye_of_horus": (6144, 7168),
    "greenest_fields": (8192, 8192),
}

CH = {name: i for i, name in enumerate(
    ["height", "slope", "water", "buildable", "metal",
     "tankSpeed", "shipSpeed", "featureCount", "featureMetal"])}


def load_json(path: Path) -> Any:
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8-sig"))


def dist(a: Tuple[float, float], b: Tuple[float, float]) -> float:
    return math.hypot(a[0] - b[0], a[1] - b[1])


class MapTerrain:
    """Terrain raster wrapper; degrades to bare geometry when no raster exists."""

    def __init__(self, map_id: str, raster: Optional[Dict[str, Any]]):
        self.map_id = map_id
        self.raster = raster
        if raster:
            self.size = (float(raster["size"]["x"]), float(raster["size"]["z"]))
            self.res = int(raster["grid"]["res"])
            self.cells = raster["cells"]
            self.starts = [(float(s["x"]), float(s["z"])) for s in raster.get("startPositions") or []]
            self.spots = [(float(s["x"]), float(s["z"]), float(s.get("metal") or 0))
                          for s in raster.get("metalSpots") or []]
        else:
            sx, sz = FALLBACK_SIZES.get(map_id, (8192, 8192))
            self.size = (float(sx), float(sz))
            self.res = 0
            self.cells = []
            self.starts = []
            self.spots = []

    @property
    def has_raster(self) -> bool:
        return bool(self.cells)

    def cell_center(self, idx: int) -> Tuple[float, float]:
        row, col = divmod(idx, self.res)
        cw = self.size[0] / self.res
        ch = self.size[1] / self.res
        return ((col + 0.5) * cw, (row + 0.5) * ch)

    def anchor_score(self, idx: int) -> float:
        """How good a cell is as a base site: buildable, dry, flat, near metal."""
        c = self.cells[idx]
        buildable = c[CH["buildable"]]
        water = c[CH["water"]]
        slope = c[CH["slope"]]
        metal = c[CH["metal"]]
        feature = c[CH["featureMetal"]]
        if buildable <= 0 or water >= 0.5:
            return 0.0
        score = buildable * (1.0 - water)
        score *= max(0.15, 1.0 - min(1.0, slope * 2.0))
        score *= 1.0 + min(2.0, metal * 1.5) + min(0.5, feature / 2000.0)
        return score

    def ranked_anchors(self, limit: int = 400) -> List[Tuple[float, Tuple[float, float]]]:
        if not self.has_raster:
            return []
        scored = []
        for idx in range(len(self.cells)):
            s = self.anchor_score(idx)
            if s > 0:
                scored.append((s, self.cell_center(idx)))
        scored.sort(key=lambda t: -t[0])
        return scored[:limit]

    def geometric_anchors(self) -> List[Tuple[float, float]]:
        sx, sz = self.size
        return [(0.15 * sx, 0.15 * sz), (0.85 * sx, 0.85 * sz),
                (0.85 * sx, 0.15 * sz), (0.15 * sx, 0.85 * sz)]

    def best_anchor_near(self, target: Tuple[float, float], avoid: Sequence[Tuple[float, float]],
                         min_sep: float, radius: Optional[float] = None) -> Optional[Tuple[float, float]]:
        candidates = self.ranked_anchors()
        if not candidates:
            return None
        best = None
        best_val = -1.0
        for score, pos in candidates:
            if radius is not None and dist(pos, target) > radius:
                continue
            if any(dist(pos, a) < min_sep for a in avoid):
                continue
            # Prefer high-scoring cells close to the requested target.
            span = math.hypot(*self.size)
            val = score * (1.0 - 0.6 * min(1.0, dist(pos, target) / span))
            if val > best_val:
                best_val, best = val, pos
        return best


def farthest_point_set(points: Sequence[Tuple[float, float]], n: int) -> List[Tuple[float, float]]:
    """Greedy max-min spread: start from the widest pair, then keep adding the
    point farthest from everything already chosen."""
    pts = list(points)
    if len(pts) <= n:
        return pts
    best_pair = max(((a, b) for i, a in enumerate(pts) for b in pts[i + 1:]),
                    key=lambda ab: dist(*ab))
    chosen = [best_pair[0], best_pair[1]]
    while len(chosen) < n:
        rest = [p for p in pts if p not in chosen]
        if not rest:
            break
        chosen.append(max(rest, key=lambda p: min(dist(p, c) for c in chosen)))
    return chosen[:n]


def closest_point_set(points: Sequence[Tuple[float, float]], n: int) -> List[Tuple[float, float]]:
    """Tightest cluster of n points -- the folded-map configuration."""
    pts = list(points)
    if len(pts) <= n:
        return pts
    best, best_cost = None, float("inf")
    for i, seed in enumerate(pts):
        group = sorted(pts, key=lambda p: dist(p, seed))[:n]
        cost = sum(dist(a, b) for j, a in enumerate(group) for b in group[j + 1:])
        if cost < best_cost:
            best, best_cost = group, cost
    return list(best or pts[:n])


def resolve_placement(terrain: MapTerrain, placement: str, count: int) -> List[Tuple[float, float]]:
    sx, sz = terrain.size
    center = (sx / 2.0, sz / 2.0)
    min_sep = 0.18 * math.hypot(sx, sz)
    starts = list(terrain.starts)

    if placement == "spread":
        picks = farthest_point_set(starts, count) if len(starts) >= 2 else []
    elif placement == "adjacent":
        picks = closest_point_set(starts, count) if len(starts) >= 2 else []
    elif placement == "center":
        anchor = terrain.best_anchor_near(center, [], 0.0, radius=0.25 * math.hypot(sx, sz))
        return [anchor or center]
    elif placement == "center_and_rim":
        picks = []
        anchor = terrain.best_anchor_near(center, [], 0.0, radius=0.25 * math.hypot(sx, sz))
        picks.append(anchor or center)
        rim = [p for p in farthest_point_set(starts, count) if dist(p, center) > 0.2 * math.hypot(sx, sz)]
        picks.extend(rim[: count - 1])
    elif placement == "derived_corners":
        picks = []
        quadrants = [(0.22, 0.22), (0.78, 0.22), (0.22, 0.78), (0.78, 0.78)]
        for qx, qz in quadrants[:count]:
            target = (qx * sx, qz * sz)
            anchor = terrain.best_anchor_near(target, picks, min_sep * 0.5,
                                              radius=0.35 * math.hypot(sx, sz))
            picks.append(anchor or target)
    else:
        raise ValueError(f"unknown placement: {placement}")

    # Top up from derived anchors (or plain geometry) when the map did not offer
    # enough authored starts for this configuration.
    fallback = terrain.geometric_anchors()
    fi = 0
    while len(picks) < count:
        target = fallback[fi % len(fallback)]
        fi += 1
        anchor = terrain.best_anchor_near(target, picks, min_sep * 0.5) if terrain.has_raster else None
        candidate = anchor or target
        if any(dist(candidate, p) < 1.0 for p in picks):
            continue
        picks.append(candidate)
    return picks[:count]


def milestone_frames(sim_minutes: int, ladder: Sequence[int]) -> List[int]:
    max_frame = int(sim_minutes * 60 * 30)
    frames = [int(m * 60 * 30) for m in ladder if int(m * 60 * 30) <= max_frame]
    if not frames or frames[-1] != max_frame:
        frames.append(max_frame)
    return frames


def build_plan(ws: Path, only_maps: Sequence[str], only_configs: Sequence[str]) -> Dict[str, Any]:
    cfg = load_json(ws / "data" / "cartography" / "spawn_configs.json")
    if not cfg:
        raise SystemExit("data/cartography/spawn_configs.json not found")
    pool = load_json(ws / "data" / "map_pool" / "seven_maps.json") or {"maps": []}
    profiles = cfg.get("aiProfiles") or {}
    ladder = cfg.get("milestoneMinutes") or [1, 2, 3, 5, 8, 13, 21]

    runs: List[Dict[str, Any]] = []
    warnings: List[str] = []

    for map_entry in pool.get("maps") or []:
        map_id = str(map_entry.get("id"))
        if only_maps and map_id not in only_maps:
            continue
        raster = load_json(ws / "data" / "terrain" / f"{map_id}.terrain.json")
        terrain = MapTerrain(map_id, raster)
        if not terrain.has_raster:
            warnings.append(f"{map_id}: no terrain raster yet -- placements fall back to geometry")
        elif not terrain.starts:
            warnings.append(f"{map_id}: terrain raster has no authored start positions -- using derived anchors")

        for config in cfg.get("configs") or []:
            config_id = str(config.get("id"))
            if only_configs and config_id not in only_configs:
                continue
            maps_filter = config.get("maps")
            if isinstance(maps_filter, list) and map_id not in maps_filter:
                continue

            count = int(config.get("teams") or 2)
            positions = resolve_placement(terrain, str(config.get("placement") or "spread"), count)
            sides = list(config.get("sides") or ["Armada", "Cortex"])
            ai_keys = list(config.get("ai") or ["aggressive"] * count)
            variants = ["a", "b"] if config.get("mirror") else ["a"]

            for variant in variants:
                ordered = list(positions) if variant == "a" else list(reversed(positions))
                teams = []
                ally = 0
                for i in range(count):
                    ai_key = ai_keys[i % len(ai_keys)]
                    teams.append({
                        "team": i,
                        "allyTeam": ally,
                        "side": sides[i % len(sides)],
                        "x": round(ordered[i][0], 1),
                        "z": round(ordered[i][1], 1),
                        "ai": dict(profiles.get(ai_key) or {"shortName": "BARb", "version": "stable"}),
                        "aiKey": ai_key,
                    })
                    ally += 1
                for extra in config.get("extraTeams") or []:
                    pos = resolve_placement(terrain, str(extra.get("placement") or "center"), 1)[0]
                    teams.append({
                        "team": len(teams),
                        "allyTeam": ally,
                        "side": str(extra.get("side") or "Armada"),
                        "x": round(pos[0], 1),
                        "z": round(pos[1], 1),
                        "ai": dict(profiles.get(str(extra.get("ai"))) or {"shortName": "RaptorsAI",
                                                                          "version": "<not-versioned>"}),
                        "aiKey": str(extra.get("ai")),
                    })
                    ally += 1

                sim_minutes = int(config.get("simMinutes") or 13)
                runs.append({
                    "runId": f"{map_id}__{config_id}__{variant}",
                    "mapId": map_id,
                    "mapName": map_entry.get("mapName") or map_id,
                    "configId": config_id,
                    "variant": variant,
                    "label": f"{config.get('label') or config_id} ({variant})",
                    "reveals": config.get("reveals") or "",
                    "simMinutes": sim_minutes,
                    "maxFrame": int(sim_minutes * 60 * 30),
                    "milestoneFrames": milestone_frames(sim_minutes, ladder),
                    "gridRes": int(cfg.get("gridRes") or 48),
                    "sampleFrames": int(cfg.get("sampleFrames") or 300),
                    "modOptions": dict(config.get("modOptions") or {}),
                    "placement": config.get("placement"),
                    "usedAuthoredStarts": bool(terrain.starts),
                    "teams": teams,
                })

    return {
        "schemaVersion": PLAN_SCHEMA,
        "gridRes": int(cfg.get("gridRes") or 48),
        "sampleFrames": int(cfg.get("sampleFrames") or 300),
        "schedule": cfg.get("schedule") or {},
        "warnings": warnings,
        "runCount": len(runs),
        "estimatedWallMinutes": sum(int(r["simMinutes"] * 1.35) + 4 for r in runs),
        "runs": runs,
    }


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="Plan zone cartography survey runs")
    ap.add_argument("--workspace", default=str(WS_DEFAULT))
    ap.add_argument("--maps", default="")
    ap.add_argument("--configs", default="")
    ap.add_argument("--out", default="")
    args = ap.parse_args(argv)

    ws = Path(args.workspace)
    only_maps = [m.strip() for m in args.maps.split(",") if m.strip()]
    only_configs = [c.strip() for c in args.configs.split(",") if c.strip()]
    plan = build_plan(ws, only_maps, only_configs)

    out = Path(args.out) if args.out else ws / "data" / "cartography" / "run_plan.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(plan, indent=1), encoding="utf-8")

    print(f"{plan['runCount']} runs -> {out}")
    print(f"estimated wall time: ~{plan['estimatedWallMinutes'] // 60}h{plan['estimatedWallMinutes'] % 60:02d}m")
    for w in plan["warnings"]:
        print(f"  warning: {w}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
