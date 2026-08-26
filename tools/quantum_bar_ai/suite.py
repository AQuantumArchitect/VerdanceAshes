"""Iteration suite for quantum-BAR-AI — early arc sim + optional BAR plan.

Writes tapes under headless_runs/quantum_bar_ai_<stamp>/ for review.
"""
from __future__ import annotations

import json
import time
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .bar_map import plan_from_action_histogram, plan_from_mood
from .mood import read_mood
from .seat import PlayerProxySeat, SeatConfig
from .sim import EARLY_ARC, MissionCard


def _workspace_root() -> Path:
    # tools/quantum_bar_ai/suite.py → workspace root
    return Path(__file__).resolve().parents[2]


def run_early_arc_suite(
    *,
    workspace: Path | str | None = None,
    use_llm: bool = True,
    llm_every_n: int = 4,
    max_missions: int = 5,
    seed: int = 7,
    verbose: bool = True,
    out_dir: Path | str | None = None,
) -> dict[str, Any]:
    """Play the early no-base arc; return summary + paths."""
    ws = Path(workspace) if workspace else _workspace_root()
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    if out_dir is None:
        out = ws / "headless_runs" / f"quantum_bar_ai_{stamp}"
    else:
        out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)

    seat = PlayerProxySeat(
        config=SeatConfig(
            use_llm=use_llm,
            llm_every_n=llm_every_n,
            seed=seed,
            verbose=verbose,
        )
    )

    t0 = time.time()
    results = seat.play_arc(EARLY_ARC, max_missions=max_missions)
    elapsed = time.time() - t0

    mission_rows = []
    for r in results:
        card = next((c for c in EARLY_ARC if c.id == r.mission_id), None)
        kind = card.kind if card else "sortie"
        bar_plan = plan_from_action_histogram(r.actions, mission_kind=kind)
        row = {
            "mission_id": r.mission_id,
            "verdict": r.verdict,
            "ticks": r.ticks,
            "progress": r.progress,
            "heroes_alive_frac": r.heroes_alive_frac,
            "brain_source_counts": r.brain_source_counts,
            "action_histogram": _hist(r.actions),
            "bar_seat_plan": bar_plan.as_dict(),
            "notes": r.notes,
        }
        mission_rows.append(row)
        # per-mission tape
        tape_path = out / f"{r.mission_id}_tape.jsonl"
        with tape_path.open("w", encoding="utf-8") as fh:
            for line in r.tape:
                fh.write(json.dumps(line, ensure_ascii=False) + "\n")
        (out / f"{r.mission_id}_result.json").write_text(
            json.dumps(r.as_dict(), indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    mood = seat.mood_now()
    summary = {
        "schemaVersion": "quantum-bar-ai-suite/0.1",
        "stamp": stamp,
        "elapsed_s": round(elapsed, 3),
        "seed": seed,
        "use_llm": use_llm,
        "llm_every_n": llm_every_n,
        "seat": seat.summary(),
        "missions": mission_rows,
        "mood_final": mood.as_dict(),
        "bar_plan_from_final_mood": plan_from_mood(mood).as_dict(),
        "out_dir": str(out),
        "iteration_hints": _iteration_hints(mission_rows),
    }

    # field snapshot for comprehension inheritance (hive lesson)
    field_path = out / "proxy_field.pkl"
    try:
        seat.save_field(str(field_path))
        summary["field_path"] = str(field_path)
    except Exception as e:  # noqa: BLE001
        summary["field_save_error"] = str(e)

    summary_path = out / "suite_summary.json"
    summary_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    latest = ws / "outbox" / "quantum_bar_ai_suite.latest.json"
    latest.parent.mkdir(parents=True, exist_ok=True)
    latest.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")

    if verbose:
        print("\n=== quantum-BAR-AI suite ===")
        print(f"out: {out}")
        print(f"elapsed: {elapsed:.2f}s  llm_calls: {summary['seat'].get('llm_calls')}")
        for m in mission_rows:
            print(
                f"  {m['mission_id']}: {m['verdict']:18s} prog={m['progress']:.2f} "
                f"bar={m['bar_seat_plan']['player_controller']}"
            )
        print("hints:", "; ".join(summary["iteration_hints"]) or "(none)")

    return summary


def _hist(actions: list[str]) -> dict[str, int]:
    h: dict[str, int] = {}
    for a in actions:
        h[a] = h.get(a, 0) + 1
    return dict(sorted(h.items(), key=lambda kv: -kv[1]))


def _iteration_hints(rows: list[dict[str, Any]]) -> list[str]:
    hints: list[str] = []
    fails = [r for r in rows if r["verdict"] in ("heroes_dead", "timeout_fail", "defeat")]
    if fails:
        hints.append(f"{len(fails)} fail(s) — tighten caution under high threat")
    for r in rows:
        hist = r.get("action_histogram") or {}
        total = sum(hist.values()) or 1
        push = hist.get("PUSH_OBJECTIVE", 0) / total
        if push > 0.7 and r["verdict"] in ("heroes_dead", "timeout_fail"):
            hints.append(f"{r['mission_id']}: over-pushing ({push:.0%}) — boost HOLD/FALLBACK weight")
        if hist.get("HOLD_AND_HEAL", 0) / total > 0.5 and r["progress"] < 0.5:
            hints.append(f"{r['mission_id']}: over-holding — clock/pressure should force probe")
        if r["progress"] >= 0.9 and r["verdict"] == "timeout_partial":
            hints.append(f"{r['mission_id']}: finished obj but no extract — weight EXTRACT higher")
    if not hints:
        hints.append("arc stable enough for BAR headless A/B via bar_seat_plan controllers")
    return hints


def run_policy_only_smoke(seed: int = 1) -> dict[str, Any]:
    """Fast offline smoke (no LLM) for CI / bat file."""
    return run_early_arc_suite(
        use_llm=False,
        max_missions=3,
        seed=seed,
        verbose=True,
    )


if __name__ == "__main__":
    import argparse

    p = argparse.ArgumentParser(description="quantum-BAR-AI early arc suite")
    p.add_argument("--no-llm", action="store_true", help="policy only")
    p.add_argument("--llm-every", type=int, default=4, help="LLM every N ticks")
    p.add_argument("--missions", type=int, default=5)
    p.add_argument("--seed", type=int, default=7)
    p.add_argument("--quiet", action="store_true")
    args = p.parse_args()
    run_early_arc_suite(
        use_llm=not args.no_llm,
        llm_every_n=args.llm_every,
        max_missions=args.missions,
        seed=args.seed,
        verbose=not args.quiet,
    )
