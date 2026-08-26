#!/usr/bin/env python3
"""Measure a map's symmetry, so zones can be cut symmetrically.

A zone map that is not symmetric on a symmetric map is unfair twice over: the
two sides of the war are not comparable to a player, and in the density matrix
zone i and its mirror carry different weight for no physical reason.

This module scores each terrain raster under the candidate symmetry operations,
accepts the ones that clear a threshold, closes them into a group, and hands
back the fundamental domain -- the patch of map you cut zones in before
replicating them.

Operations are expressed in CELL space. The grid is a uniform affine map of the
world, so a symmetry of the cell grid is a symmetry of the map whether or not
the map is square.

    python tools/map_symmetry_v1.py
    python tools/map_symmetry_v1.py --maps koom_valley --threshold 0.9
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Callable, Dict, List, Sequence, Tuple

WS_DEFAULT = Path(__file__).resolve().parents[1]

# Channel index -> weight in the symmetry score. Height dominates: it is the
# map's shape. Water and buildability catch mirrored lakes and mirrored bases
# that a pure height comparison can miss.
CHANNEL_WEIGHTS = {"height": 0.55, "water": 0.20, "buildable": 0.15, "tankSpeed": 0.10}

DEFAULT_THRESHOLD = 0.90

Op = Callable[[int, int, int], Tuple[int, int]]

# Named generators. Every op is an involution or a rotation of order 2, so the
# closure of any subset stays small (order 1, 2, 4 or 8).
OPS: Dict[str, Op] = {
    "mirror_ew": lambda r, c, n: (r, n - 1 - c),
    "mirror_ns": lambda r, c, n: (n - 1 - r, c),
    "rot180": lambda r, c, n: (n - 1 - r, n - 1 - c),
    "diagonal": lambda r, c, n: (c, r),
    "antidiagonal": lambda r, c, n: (n - 1 - c, n - 1 - r),
}

# Ops that only make sense when the map's world aspect ratio is 1:1. A diagonal
# flip of a 2:1 map maps real ground onto ground it does not resemble.
SQUARE_ONLY = ("diagonal", "antidiagonal")


def load_json(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def score_op(cells: Sequence[Sequence[float]], res: int, channels: Sequence[str],
             op: Op) -> float:
    """1.0 = the op maps the map exactly onto itself; 0.0 = no resemblance."""
    idx_of = {name: i for i, name in enumerate(channels)}
    total_weight = 0.0
    total_score = 0.0
    for name, weight in CHANNEL_WEIGHTS.items():
        ci = idx_of.get(name)
        if ci is None:
            continue
        values = [c[ci] for c in cells]
        lo, hi = min(values), max(values)
        span = (hi - lo) or 1.0
        diff = 0.0
        for r in range(res):
            for c in range(res):
                rr, cc = op(r, c, res)
                diff += abs(values[r * res + c] - values[rr * res + cc])
        total_score += weight * (1.0 - (diff / (res * res)) / span)
        total_weight += weight
    return total_score / (total_weight or 1.0)


def compose(a: Op, b: Op) -> Op:
    return lambda r, c, n: a(*b(r, c, n), n)


def close_group(names: Sequence[str], res: int) -> List[str]:
    """Closure of the accepted generators, named by their cell permutation.

    Composition can produce an op we already have a name for (mirror_ew after
    mirror_ns IS rot180), so the group is identified by behaviour, not by which
    generators the scorer happened to accept.
    """
    def signature(op: Op) -> Tuple[Tuple[int, int], ...]:
        # A permutation of a handful of probe cells identifies the op uniquely
        # for the grid sizes we use, and is cheap to hash.
        probes = [(0, 0), (0, res - 1), (res - 1, 0), (1, 2), (2, 1), (res // 3, res // 2)]
        return tuple(op(r, c, res) for r, c in probes)

    identity: Op = lambda r, c, n: (r, c)
    found: Dict[Tuple[Tuple[int, int], ...], str] = {signature(identity): "identity"}
    ordered = ["identity"]
    frontier = [identity]
    named = {name: OPS[name] for name in names if name in OPS}

    while frontier:
        nxt: List[Op] = []
        for base in frontier:
            for name, gen in named.items():
                combined = compose(gen, base)
                sig = signature(combined)
                if sig in found:
                    continue
                # Prefer a canonical name when the composition equals a known op.
                label = name
                for known, kop in OPS.items():
                    if signature(kop) == sig:
                        label = known
                        break
                found[sig] = label
                ordered.append(label)
                nxt.append(combined)
        frontier = nxt
    return ordered


def group_ops(names: Sequence[str]) -> List[Op]:
    """Concrete callables for a closed group, identity first."""
    out: List[Op] = [lambda r, c, n: (r, c)]
    for name in names:
        if name != "identity" and name in OPS:
            out.append(OPS[name])
    return out


def orbit(idx: int, res: int, ops: Sequence[Op]) -> List[int]:
    r, c = divmod(idx, res)
    seen = set()
    for op in ops:
        rr, cc = op(r, c, res)
        seen.add(rr * res + cc)
    return sorted(seen)


def fundamental_domain(res: int, ops: Sequence[Op]) -> List[bool]:
    """Cells that are the canonical (lowest-index) member of their orbit."""
    return [orbit(i, res, ops)[0] == i for i in range(res * res)]


def detect(terrain: Dict[str, Any], threshold: float = DEFAULT_THRESHOLD) -> Dict[str, Any]:
    res = int(terrain["grid"]["res"])
    cells = terrain["cells"]
    channels = terrain["channels"]
    size = (float(terrain["size"]["x"]), float(terrain["size"]["z"]))
    square = abs(size[0] - size[1]) < 1.0

    scores: Dict[str, float] = {}
    for name, op in OPS.items():
        if name in SQUARE_ONLY and not square:
            continue
        scores[name] = round(score_op(cells, res, channels, op), 4)

    accepted = sorted((n for n, s in scores.items() if s >= threshold),
                      key=lambda n: -scores[n])
    forced = False
    if not accepted and scores:
        # A map with no accepted symmetry still gets zones; the caller decides
        # whether to force the best candidate for fairness.
        accepted = []
    group = close_group(accepted, res) if accepted else ["identity"]
    ops = group_ops(group)
    domain = fundamental_domain(res, ops)
    return {
        "mapId": terrain.get("mapId"),
        "res": res,
        "square": square,
        "threshold": threshold,
        "scores": scores,
        "best": max(scores, key=lambda n: scores[n]) if scores else None,
        "bestScore": max(scores.values()) if scores else 0.0,
        "accepted": accepted,
        "forced": forced,
        "group": group,
        "order": len(ops),
        "domainCells": sum(1 for d in domain if d),
        "_ops": ops,
        "_domain": domain,
    }


def detect_forced(terrain: Dict[str, Any], threshold: float = DEFAULT_THRESHOLD,
                  force_best: bool = False) -> Dict[str, Any]:
    """detect(), optionally adopting the best-scoring op even below threshold.

    greenest_fields scores 0.898 on the north-south mirror -- a real axis on a
    map that is otherwise a featureless ramp. Forcing it buys fairness at the
    cost of zones that follow the axis more than the ground.
    """
    info = detect(terrain, threshold)
    if info["accepted"] or not force_best or not info["best"]:
        return info
    res = info["res"]
    group = close_group([info["best"]], res)
    ops = group_ops(group)
    domain = fundamental_domain(res, ops)
    info.update({
        "accepted": [info["best"]],
        "forced": True,
        "group": group,
        "order": len(ops),
        "domainCells": sum(1 for d in domain if d),
        "_ops": ops,
        "_domain": domain,
    })
    return info


def public(info: Dict[str, Any]) -> Dict[str, Any]:
    """The serialisable part -- callables stripped."""
    return {k: v for k, v in info.items() if not k.startswith("_")}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Measure map symmetry from terrain rasters")
    ap.add_argument("--workspace", default=str(WS_DEFAULT))
    ap.add_argument("--maps", default="")
    ap.add_argument("--threshold", type=float, default=DEFAULT_THRESHOLD)
    ap.add_argument("--force-best", action="store_true")
    ap.add_argument("--out", default="")
    args = ap.parse_args(argv)

    ws = Path(args.workspace)
    wanted = [m.strip() for m in args.maps.split(",") if m.strip()]
    paths = sorted((ws / "data" / "terrain").glob("*.terrain.json"))
    if wanted:
        paths = [p for p in paths if p.name.split(".")[0] in wanted]
    if not paths:
        print("no terrain rasters found", file=sys.stderr)
        return 1

    out: Dict[str, Any] = {"schemaVersion": "verdance-map-symmetry/1.0", "maps": {}}
    names = [n for n in OPS]
    header = f"{'map':<18}" + "".join(f"{n:>14}" for n in names) + "   group"
    print(header)
    for path in paths:
        info = detect_forced(load_json(path), args.threshold, args.force_best)
        out["maps"][str(info["mapId"])] = public(info)
        row = f"{str(info['mapId']):<18}"
        for n in names:
            s = info["scores"].get(n)
            row += f"{'n/a':>14}" if s is None else f"{s:14.3f}"
        tag = ",".join(info["accepted"]) or "none"
        if info["forced"]:
            tag += " (forced)"
        print(row + f"   order {info['order']}: {tag}")

    if args.out:
        Path(args.out).write_text(json.dumps(out, indent=2), encoding="utf-8")
        print(f"-> {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
