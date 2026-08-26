#!/usr/bin/env python3
"""Lane-war stress bench — proxy line orders vs enemy line AI on Koom 3–5.

Produces diversity of line outcomes (breakthrough vs hold) without full campaign.
Useful overnight sanity that the quantum membrane + enemy AI actually fight.

Usage:
  python -m quantum_bar_ai.lane_stress --lanes 4 --ticks 40 --seeds 5
"""
from __future__ import annotations

import argparse
import json
import random
from datetime import datetime, timezone
from pathlib import Path

from .enemy_line_ai import apply_enemy_plan, plan_enemy_line
from .campaign_manifold import CampaignRho
from .lane_war import (
    LineFront,
    apply_line_order,
    decide_line,
    koom_geometry,
    lane_objective_progress,
    tick_lane_combat,
)
from .quantum_membrane import CampaignDensity
from .suite import _workspace_root


def run_bout(
    *,
    lanes: int,
    ticks: int,
    seed: int,
    player_str: float = 0.72,
    enemy_str: float = 0.58,
    width: float = 0.55,
    fortified: bool = False,
) -> dict:
    rng = random.Random(seed)
    geo = koom_geometry(lanes)
    front = LineFront(geometry=geo)
    rho = CampaignRho(arm_cor=0.5 + 0.3 * rng.random())
    density = CampaignDensity.from_path_weights(0.4, 0.35, 0.25, purity=0.75)
    orders_p: list[str] = []
    orders_e: list[str] = []

    for t in range(ticks):
        # competent player line doctrine: push primary early, dress when ragged
        if front.coherence < 0.4:
            agg, caut, coh_b = 0.15, 0.45, 0.7
        elif front.primary_hold() < 0.55:
            agg, caut, coh_b = 0.65, 0.1, 0.4
        else:
            agg, caut, coh_b = 0.45, 0.25, 0.55
        # late multipath spice
        if width >= 0.55 and t > ticks // 2 and rng.random() < 0.25:
            agg = 0.7
        po = decide_line(front, aggression=agg, caution=caut, cohesion=coh_b, width=width, rng=rng)
        apply_line_order(front, po, dt=1.0)
        orders_p.append(po.order)
        ep = plan_enemy_line(front, rho=rho, density=density, width=width, rng=rng)
        apply_enemy_plan(front, ep, dt=0.55)
        orders_e.append(ep.order.order)
        tick_lane_combat(
            front,
            player_strength=player_str,
            enemy_strength=enemy_str * 0.92,  # player doctrine edge
            fortified=fortified,
            rng=rng,
            dt=1.0,
        )
        # mild strength drift
        player_str = max(0.3, min(0.95, player_str + rng.uniform(-0.008, 0.012)))
        enemy_str = max(0.25, min(0.9, enemy_str + rng.uniform(-0.01, 0.008)))

    prog = lane_objective_progress(front, width=width)
    return {
        "seed": seed,
        "lanes": lanes,
        "progress": round(prog, 4),
        "mean_hold": round(front.mean_hold(), 4),
        "primary_hold": round(front.primary_hold(), 4),
        "coherence": round(front.coherence, 4),
        "purity": round(front.density.purity, 4) if front.density else None,
        "mean_coh": round(front.density.mean_coherence(), 4) if front.density else None,
        "player_orders": {o: orders_p.count(o) for o in set(orders_p)},
        "enemy_orders": {o: orders_e.count(o) for o in set(orders_e)},
        "fair_bands": front.fair_bands(),
        "won_lane": prog >= 0.68,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--lanes", type=int, default=4)
    ap.add_argument("--ticks", type=int, default=40)
    ap.add_argument("--seeds", type=int, default=5)
    ap.add_argument("--base-seed", type=int, default=9)
    args = ap.parse_args()
    rows = []
    for i in range(args.seeds):
        for n in ([args.lanes] if args.lanes else [3, 4, 5]):
            rows.append(
                run_bout(lanes=n, ticks=args.ticks, seed=args.base_seed + i * 11 + n)
            )
    wins = sum(1 for r in rows if r["won_lane"])
    report = {
        "schemaVersion": "lane-stress/0.1",
        "stamp": datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S"),
        "win_rate": round(wins / max(1, len(rows)), 4),
        "rows": rows,
    }
    ws = _workspace_root()
    out = ws / "headless_runs" / f"lane_stress_{report['stamp']}"
    out.mkdir(parents=True, exist_ok=True)
    (out / "report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"lane stress win_rate={report['win_rate']:.0%} n={len(rows)}")
    for r in rows:
        print(
            f"  seed={r['seed']} L{r['lanes']} prog={r['progress']:.2f} "
            f"coh={r['coherence']:.2f} pur={r['purity']} won={r['won_lane']}"
        )
    print("report:", out / "report.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
