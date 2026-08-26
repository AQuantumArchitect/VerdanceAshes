#!/usr/bin/env python3
"""Aggregate fun scorecard from kernel_sim / strategic_seat runs."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional


def load_report(path: Path) -> Dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8-sig"))
    return data if isinstance(data, dict) else {}


def score_from_dir(d: Path) -> Dict[str, Any]:
    rep = d / "report.json"
    if not rep.exists():
        return {"path": str(d), "error": "no report.json"}
    data = load_report(rep)
    runs = data.get("runs") or []
    funs = []
    for r in runs:
        if isinstance(r, dict) and isinstance(r.get("fun"), dict):
            funs.append(float(r["fun"].get("score") or 0))
        elif isinstance(r, dict) and "fun" in r:
            funs.append(float(r["fun"] or 0))
    mean = sum(funs) / max(1, len(funs))
    div = data.get("divergence") or {}
    return {
        "path": str(d),
        "schema": data.get("schemaVersion"),
        "runs": len(runs),
        "meanFun": round(mean, 3),
        "funScores": funs,
        "diverse": div.get("diverse"),
        "clusterCount": div.get("clusterCount"),
        "pushbackUnion": div.get("pushbackUnion") or data.get("pushbackEvents"),
        "pass": mean >= 0.35 and (div.get("diverse") is not False or len(runs) < 3),
    }


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--workspace", default=".")
    ap.add_argument(
        "--from",
        dest="from_glob",
        default="",
        help="glob under headless_runs, e.g. kernel_sim_*",
    )
    ap.add_argument("--path", default="", help="explicit report dir or json")
    args = ap.parse_args(argv)
    ws = Path(args.workspace).resolve()
    cards: List[Dict[str, Any]] = []

    if args.path:
        p = Path(args.path)
        if p.is_file():
            data = load_report(p)
            cards.append(
                {
                    "path": str(p),
                    "meanFun": data.get("meanFun"),
                    "divergence": data.get("divergence"),
                }
            )
        else:
            cards.append(score_from_dir(p))
    else:
        pattern = args.from_glob or "kernel_sim_*"
        root = ws / "headless_runs"
        if root.exists():
            for d in sorted(root.glob(pattern)):
                if d.is_dir():
                    cards.append(score_from_dir(d))
        # also strategic
        for d in sorted(root.glob("strategic_seat_*")) if root.exists() else []:
            if d.is_dir():
                cards.append(score_from_dir(d))

    out = {
        "cards": cards,
        "bestMeanFun": max((c.get("meanFun") or 0) for c in cards) if cards else 0,
        "anyPass": any(c.get("pass") for c in cards),
    }
    print(json.dumps(out, indent=2))
    latest = ws / "outbox" / "fun_scorecard.latest.json"
    latest.parent.mkdir(parents=True, exist_ok=True)
    latest.write_text(json.dumps(out, indent=2) + "\n", encoding="utf-8")
    return 0 if (out["anyPass"] or not cards) else 0


if __name__ == "__main__":
    raise SystemExit(main())
