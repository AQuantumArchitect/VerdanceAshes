#!/usr/bin/env python3
"""Sweep the abstract proxy campaign across every map and every enemy seat.

proxy_campaign_v1.py runs one home map per invocation and its CLI writes learned
brain weights as a side effect of --write. For a measurement sweep neither is
wanted: the point is to compare the three BAR seats (SimpleAI / BARb hard / BARb
aggressive) on identical seeds across all seven theatres, with the learned brain
held still so the differences are attributable to the seat.

This drives compare_enemy_styles() in-process (one umwelt engine build for the
whole sweep instead of one per map) and never touches app/brain or the hive
mirror. Every campaign still runs in its own temp workspace, so state/ is safe.

Usage:
  python tools/proxy_seat_sweep_v1.py --workspace . --sorties 6 --seeds 3
  python tools/proxy_seat_sweep_v1.py --workspace . --maps greenest_fields,tabula
"""
from __future__ import annotations

import argparse
import io
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

TOOLS = Path(__file__).resolve().parent
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

import proxy_campaign_v1 as proxy  # noqa: E402

ALL_MAPS = list(proxy.MAP_LABELS)


def run_sweep(
    workspace: Path,
    maps: List[str],
    styles: List[str],
    *,
    sorties: int,
    seeds: int,
    base_seed: int,
    difficulty: float,
    ticks: int,
    verbose: bool,
) -> Dict[str, Any]:
    started = time.time()
    per_map: Dict[str, Any] = {}

    for map_id in maps:
        t0 = time.time()
        print(f"[sweep] {map_id}: {len(styles)} style(s) x {seeds} seed(s) x {sorties} sortie(s)")
        try:
            report = proxy.compare_enemy_styles(
                workspace,
                styles=styles,
                sorties=sorties,
                seeds=seeds,
                base_seed=base_seed,
                home_map=map_id,
                difficulty=difficulty,
                duration_ticks=ticks,
                hours_between=0.75,
                verbose=verbose,
            )
        except Exception as exc:  # keep the sweep going; one bad map is not the night
            print(f"[sweep] {map_id} FAILED: {exc}")
            per_map[map_id] = {"error": str(exc)}
            continue

        by_style = report.get("byStyle") or {}
        per_map[map_id] = {
            "label": proxy.MAP_LABELS.get(map_id, map_id),
            "byStyle": {
                s: {
                    "runs": v.get("runs"),
                    "meanWinRate": v.get("meanWinRate"),
                    "meanFun": v.get("meanFun"),
                    "meanTnb": v.get("meanTnb"),
                    "meanClashEvents": v.get("meanClashEvents"),
                    "barEnemy": v.get("barEnemy"),
                }
                for s, v in by_style.items()
            },
            "headToHead": report.get("headToHead"),
            "elapsedSeconds": round(time.time() - t0, 1),
        }
        summary = "  ".join(
            f"{s}={by_style[s].get('meanWinRate')}" for s in styles if s in by_style
        )
        print(f"[sweep] {map_id} done in {per_map[map_id]['elapsedSeconds']}s  winRate: {summary}")

    # Cross-map aggregate per seat.
    agg: Dict[str, Dict[str, Any]] = {}
    for style in styles:
        wrs, funs, clashes = [], [], []
        for m in per_map.values():
            row = (m.get("byStyle") or {}).get(style)
            if not row:
                continue
            if row.get("meanWinRate") is not None:
                wrs.append(float(row["meanWinRate"]))
            if row.get("meanFun") is not None:
                funs.append(float(row["meanFun"]))
            if row.get("meanClashEvents") is not None:
                clashes.append(float(row["meanClashEvents"]))
        if wrs:
            agg[style] = {
                "maps": len(wrs),
                "meanWinRate": round(sum(wrs) / len(wrs), 3),
                "minWinRate": round(min(wrs), 3),
                "maxWinRate": round(max(wrs), 3),
                "meanFun": round(sum(funs) / len(funs), 3) if funs else None,
                "meanClashEvents": round(sum(clashes) / len(clashes), 2) if clashes else None,
                "barSeat": proxy.ENEMY_STYLES[style]["bar_controller"],
            }

    return {
        "schemaVersion": "verdance-proxy-seat-sweep/0.1",
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "styles": styles,
        "maps": maps,
        "sorties": sorties,
        "seeds": seeds,
        "baseSeed": base_seed,
        "difficulty": difficulty,
        "ticks": ticks,
        "perMap": per_map,
        "seatAggregate": agg,
        "seatLadder": sorted(agg, key=lambda s: -agg[s]["meanWinRate"]),
        "elapsedSeconds": round(time.time() - started, 1),
    }


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="Proxy campaign seat sweep across maps")
    ap.add_argument("--workspace", default=".")
    ap.add_argument("--maps", default="", help="comma list; default all seven")
    ap.add_argument("--styles", default="", help="comma list; default every ENEMY_STYLES seat")
    ap.add_argument("--sorties", type=int, default=6)
    ap.add_argument("--seeds", type=int, default=3)
    ap.add_argument("--seed", type=int, default=11)
    ap.add_argument("--difficulty", type=float, default=1.0)
    ap.add_argument("--ticks", type=int, default=48)
    ap.add_argument("--out", default="")
    ap.add_argument("--verbose", action="store_true")
    args = ap.parse_args(argv)

    ws = Path(args.workspace).resolve()
    maps = (
        [m.strip() for m in args.maps.split(",") if m.strip()]
        if args.maps
        else list(ALL_MAPS)
    )
    styles = (
        [s.strip() for s in args.styles.split(",") if s.strip()]
        if args.styles
        else list(proxy.ENEMY_STYLES)
    )
    unknown = [s for s in styles if s not in proxy.ENEMY_STYLES]
    if unknown:
        print(f"Unknown style(s): {unknown}; known: {list(proxy.ENEMY_STYLES)}", file=sys.stderr)
        return 2

    report = run_sweep(
        ws,
        maps,
        styles,
        sorties=args.sorties,
        seeds=args.seeds,
        base_seed=args.seed,
        difficulty=args.difficulty,
        ticks=args.ticks,
        verbose=args.verbose,
    )

    out = Path(args.out) if args.out else ws / "reports" / "proxy_seat_sweep.latest.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    with io.open(out, "w", encoding="utf-8") as fh:
        json.dump(report, fh, indent=2)

    print()
    print("=== seat ladder (abstract proxy, mean win rate across maps) ===")
    for style in report["seatLadder"]:
        row = report["seatAggregate"][style]
        print(
            f"  {style:<16} winRate={row['meanWinRate']:<6} "
            f"[{row['minWinRate']}..{row['maxWinRate']}] maps={row['maps']} "
            f"barSeat={row['barSeat']}"
        )
    print(f"Wrote {out}  ({report['elapsedSeconds']}s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
