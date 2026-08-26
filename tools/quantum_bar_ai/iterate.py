#!/usr/bin/env python3
"""Iterate quantum-BAR-AI: multi-seed policy sweeps + optional LLM A/B.

Usage:
  python -m quantum_bar_ai.iterate --seeds 3 --missions 5
  python -m quantum_bar_ai.iterate --seeds 2 --missions 3 --llm --llm-every 6
"""
from __future__ import annotations

import argparse
import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .seat import PlayerProxySeat, SeatConfig
from .sim import EARLY_ARC
from .suite import _hist, _iteration_hints, _workspace_root
from .bar_map import plan_from_action_histogram


def _play_seed(
    seed: int,
    *,
    use_llm: bool,
    llm_every: int,
    max_missions: int,
    verbose: bool,
) -> dict[str, Any]:
    seat = PlayerProxySeat(
        config=SeatConfig(
            use_llm=use_llm,
            llm_every_n=llm_every,
            seed=seed,
            verbose=verbose,
        )
    )
    results = seat.play_arc(EARLY_ARC, max_missions=max_missions)
    rows = []
    for r in results:
        card = next((c for c in EARLY_ARC if c.id == r.mission_id), None)
        kind = card.kind if card else "sortie"
        rows.append(
            {
                "mission_id": r.mission_id,
                "verdict": r.verdict,
                "progress": r.progress,
                "ticks": r.ticks,
                "heroes_alive_frac": r.heroes_alive_frac,
                "brain_source_counts": r.brain_source_counts,
                "action_histogram": _hist(r.actions),
                "bar_seat_plan": plan_from_action_histogram(r.actions, mission_kind=kind).as_dict(),
            }
        )
    hard = sum(1 for r in results if r.verdict in ("extracted", "objective_complete"))
    return {
        "seed": seed,
        "hard_wins": hard,
        "missions": len(results),
        "verdicts": [r.verdict for r in results],
        "progress": [r.progress for r in results],
        "llm_calls": seat.brain.call_count if seat.brain else 0,
        "llm_error": seat.brain.last_error if seat.brain else None,
        "rows": rows,
        "hints": _iteration_hints(rows),
        "seat_summary": seat.summary(),
    }


def run_iterate(
    *,
    seeds: int = 3,
    base_seed: int = 7,
    missions: int = 5,
    use_llm: bool = False,
    llm_every: int = 6,
    verbose: bool = False,
    workspace: Path | None = None,
) -> dict[str, Any]:
    ws = workspace or _workspace_root()
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    out = ws / "headless_runs" / f"quantum_bar_ai_iter_{stamp}"
    out.mkdir(parents=True, exist_ok=True)

    t0 = time.time()
    runs = []
    for i in range(seeds):
        seed = base_seed + i * 17
        if verbose:
            print(f"\n----- seed {seed} llm={use_llm} -----")
        runs.append(
            _play_seed(
                seed,
                use_llm=use_llm,
                llm_every=llm_every,
                max_missions=missions,
                verbose=verbose,
            )
        )

    hard_rates = [r["hard_wins"] / max(1, r["missions"]) for r in runs]
    report = {
        "schemaVersion": "quantum-bar-ai-iterate/0.1",
        "stamp": stamp,
        "elapsed_s": round(time.time() - t0, 3),
        "use_llm": use_llm,
        "llm_every": llm_every,
        "missions_per_seed": missions,
        "seeds": [r["seed"] for r in runs],
        "hard_win_rate_mean": round(sum(hard_rates) / max(1, len(hard_rates)), 4),
        "hard_win_rates": [round(x, 4) for x in hard_rates],
        "runs": runs,
        "aggregate_hints": sorted(
            {h for r in runs for h in r["hints"]}
        ),
        "out_dir": str(out),
    }
    path = out / "iterate_report.json"
    path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    latest = ws / "outbox" / "quantum_bar_ai_iterate.latest.json"
    latest.parent.mkdir(parents=True, exist_ok=True)
    latest.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")

    print("\n=== quantum-BAR-AI iterate ===")
    print(f"seeds={seeds} missions={missions} llm={use_llm}")
    print(f"hard_win_rate_mean={report['hard_win_rate_mean']:.0%}")
    for r in runs:
        print(f"  seed={r['seed']}: {r['hard_wins']}/{r['missions']} {r['verdicts']}")
    print(f"report: {path}")
    return report


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--seeds", type=int, default=3)
    p.add_argument("--base-seed", type=int, default=7)
    p.add_argument("--missions", type=int, default=5)
    p.add_argument("--llm", action="store_true")
    p.add_argument("--llm-every", type=int, default=6)
    p.add_argument("--verbose", action="store_true")
    args = p.parse_args()
    run_iterate(
        seeds=args.seeds,
        base_seed=args.base_seed,
        missions=args.missions,
        use_llm=args.llm,
        llm_every=args.llm_every,
        verbose=args.verbose,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
