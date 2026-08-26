#!/usr/bin/env python3
"""Digest manifold gym reports into a short morning brief.

Usage:
  python -m quantum_bar_ai.gym_digest
  python -m quantum_bar_ai.gym_digest --path headless_runs/manifold_gym_.../gym_report.json
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from .suite import _workspace_root


def find_latest_report(ws: Path) -> Path | None:
    latest = ws / "outbox" / "manifold_gym.latest.json"
    if latest.is_file():
        return latest
    runs = sorted(
        (ws / "headless_runs").glob("manifold_gym_*/gym_report.json"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    return runs[0] if runs else None


def digest(report: dict) -> str:
    best = report.get("best") or {}
    lines = [
        "=== Manifold gym morning digest ===",
        f"stamp: {report.get('stamp')}",
        f"gens: {report.get('generations_run')}  elapsed_s: {report.get('elapsed_s')}",
        f"best craft_score: {best.get('craft_score')}",
        f"best overall: {best.get('overall_win_rate')}",
        f"best arcs: {best.get('arc_rates')}",
        f"best diversity: {best.get('diversity_mean')}  pathH: {best.get('path_entropy')}",
        f"best knobs: {json.dumps(report.get('best_knobs'), indent=2)}",
        f"mechanisms: {', '.join(report.get('novel_mechanisms') or [])}",
        f"out: {report.get('out_dir')}",
    ]
    hist = report.get("history") or []
    if hist:
        lines.append("--- last 5 gens ---")
        for h in hist[-5:]:
            lines.append(
                f"  g{h.get('gen')}: win={h.get('overall_win_rate')} "
                f"arcs={h.get('arc_rates')} score={h.get('craft_score')} "
                f"pathH={h.get('path_entropy')}"
            )
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--path", type=str, default=None)
    args = ap.parse_args()
    ws = _workspace_root()
    path = Path(args.path) if args.path else find_latest_report(ws)
    if path is None or not path.is_file():
        # fall back to champion-only mid-run
        champs = sorted(
            (ws / "headless_runs").glob("manifold_gym_*/champion_knobs.json"),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
        if not champs:
            print("no gym report or champion found")
            return 1
        knobs = json.loads(champs[0].read_text(encoding="utf-8-sig"))
        print("=== mid-run champion (no full report yet) ===")
        print("path:", champs[0])
        print(json.dumps(knobs, indent=2))
        return 0
    report = json.loads(path.read_text(encoding="utf-8-sig"))
    print(digest(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
