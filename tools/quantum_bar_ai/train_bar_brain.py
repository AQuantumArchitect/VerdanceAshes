#!/usr/bin/env python3
"""Train / inspect the super quantum BAR brain from campaign tapes.

  python -m quantum_bar_ai.train_bar_brain
  python -m quantum_bar_ai.train_bar_brain --from outbox/quantum_bar_ai_campaign.latest.json
  python -m quantum_bar_ai.train_bar_brain --seed-only
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from .bar_brain import (
    BarBrain,
    ingest_campaign_report,
    load_weights,
    save_weights,
    seed_manifold_priors,
    weights_path,
)
from .suite import _workspace_root


def main() -> int:
    p = argparse.ArgumentParser(description="Train verdance BAR brain (umwelt + manifold)")
    p.add_argument("--from", dest="src", type=str, default="", help="Campaign report JSON")
    p.add_argument("--seed-only", action="store_true", help="Write manifold priors only")
    p.add_argument("--show", action="store_true", help="Print current weights summary")
    args = p.parse_args()
    ws = _workspace_root()

    if args.seed_only:
        w = seed_manifold_priors()
        path = save_weights(w)
        print(json.dumps({"seeded": str(path), "samples": w.samples}, indent=2))
        return 0

    if args.show:
        w = load_weights()
        brain = BarBrain(w)
        print(
            json.dumps(
                {
                    "path": str(weights_path()),
                    "samples": w.samples,
                    "wins": w.wins,
                    "losses": w.losses,
                    "top_global": sorted(w.action_counts.items(), key=lambda kv: -kv[1])[:10],
                    "seat": brain.bar_seat_hint(kind="eco_expand"),
                },
                indent=2,
            )
        )
        return 0

    src = Path(args.src) if args.src else ws / "outbox" / "quantum_bar_ai_campaign.latest.json"
    if not src.is_file():
        # fall back to beat first arc latest
        alt = ws / "outbox" / "quantum_bar_ai_beat.latest.json"
        if alt.is_file():
            src = alt
        else:
            print(f"no report at {src}; run beat_campaign first or --seed-only")
            return 2

    report = json.loads(src.read_text(encoding="utf-8"))
    # unwrap multi-seed / champion shells
    if "results" not in report:
        if report.get("runs"):
            report = report["runs"][0]
        elif report.get("champion") and report["champion"].get("runs"):
            # champion may only store verdicts
            hist = report.get("history_tail") or []
            for batch in reversed(hist):
                if batch.get("runs") and batch["runs"][0].get("results"):
                    report = batch["runs"][0]
                    break

    w = ingest_campaign_report(report, load_weights())
    path = save_weights(w)
    brain = BarBrain(w)
    print(
        json.dumps(
            {
                "trained_from": str(src),
                "weights": str(path),
                "samples": w.samples,
                "wins": w.wins,
                "losses": w.losses,
                "seat_hint": brain.bar_seat_hint(kind="eco_expand"),
                "seat_siege": brain.bar_seat_hint(kind="siege"),
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
