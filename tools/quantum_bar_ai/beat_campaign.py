#!/usr/bin/env python3
"""Beat the full three-arc Verdance campaign under the fair proxy contract.

Also trains bar_brain weights from the resulting tapes (umwelt + manifold).

Usage:
  python -m quantum_bar_ai.beat_campaign --once
  python -m quantum_bar_ai.beat_campaign --once --arcs 1,2,3
  python -m quantum_bar_ai.beat_campaign --once --ant --ant-every 6
  python -m quantum_bar_ai.beat_campaign --once --train
"""
from __future__ import annotations

import argparse
import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .ant_agent import AntToolAgent
from .bar_brain import BarBrain, ingest_campaign_report, load_weights, save_weights
from .beat_first_arc import _publish_story
from .fair_sim import play_campaign, play_missions
from .campaign import build_full_campaign
from .suite import _workspace_root
from .tool_agent import GrokToolAgent, LocalToolAgent


def _make_agent(*, use_ant: bool, use_llm: bool, ant_every_n: int = 4) -> Any:
    if use_ant:
        return AntToolAgent(every_n=ant_every_n)
    if use_llm:
        return GrokToolAgent()
    return LocalToolAgent()


def _parse_arcs(s: str) -> tuple[int, ...]:
    parts = [p.strip() for p in s.split(",") if p.strip()]
    arcs = tuple(int(p) for p in parts)
    for a in arcs:
        if a not in (1, 2, 3):
            raise SystemExit(f"bad arc {a}; use 1,2,3")
    return arcs or (1, 2, 3)


def run_once(
    *,
    difficulty: float,
    seed: int,
    arcs: tuple[int, ...],
    use_ant: bool,
    use_llm: bool,
    ant_every_n: int,
    train: bool,
    verbose: bool,
    use_craft: bool = True,
) -> dict[str, Any]:
    ws = _workspace_root()
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    agent = _make_agent(use_ant=use_ant, use_llm=use_llm, ant_every_n=ant_every_n)

    t0 = time.time()
    if len(arcs) == 1:
        missions = build_full_campaign(
            difficulty=difficulty, arcs=arcs, use_craft=use_craft
        )
        rep = play_missions(
            missions,
            agent=agent,
            difficulty=difficulty,
            seed=seed,
            verbose=verbose,
            use_llm=use_llm,
            use_ant=use_ant,
            ant_every_n=ant_every_n,
            schema="quantum-bar-ai-fair-arc/0.2",
            label=f"arc_{arcs[0]}",
        )
    else:
        rep = play_campaign(
            agent=agent,
            difficulty=difficulty,
            seed=seed,
            verbose=verbose,
            use_llm=use_llm,
            use_ant=use_ant,
            ant_every_n=ant_every_n,
            arcs=arcs,
            use_craft=use_craft,
        )
    rep["elapsed_s"] = round(time.time() - t0, 2)
    rep["arcs"] = list(arcs)

    out = ws / "headless_runs" / f"quantum_bar_ai_campaign_{stamp}"
    out.mkdir(parents=True, exist_ok=True)
    (out / "report.json").write_text(
        json.dumps(rep, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    latest = ws / "outbox" / "quantum_bar_ai_campaign.latest.json"
    latest.parent.mkdir(parents=True, exist_ok=True)
    latest.write_text(json.dumps(rep, indent=2, ensure_ascii=False), encoding="utf-8")

    story_paths = {}
    try:
        story_paths = _publish_story(rep, ws, stamp=stamp)
    except Exception as e:  # noqa: BLE001
        rep["story_error"] = f"{type(e).__name__}: {e}"

    train_info = None
    if train:
        w = ingest_campaign_report(rep, load_weights())
        path = save_weights(w)
        brain = BarBrain(w)
        train_info = {
            "weights_path": str(path),
            "samples": w.samples,
            "wins": w.wins,
            "losses": w.losses,
            "seat_hint": brain.bar_seat_hint(kind="eco_expand"),
        }
        (out / "bar_brain_train.json").write_text(
            json.dumps(train_info, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    craft_info = None
    try:
        from .craft_apply import load_recipe

        r = load_recipe(ws)
        if r.get("knobs"):
            craft_info = {
                "stamp": r.get("stamp"),
                "craft_score": r.get("craft_score"),
                "knobs": r.get("knobs"),
                "use_craft": use_craft,
            }
    except Exception:
        pass

    summary = {
        "cleared": rep.get("cleared"),
        "cleared_all_arcs": rep.get("cleared_all_arcs", rep.get("cleared")),
        "hard_wins": rep.get("hard_wins"),
        "missions": rep.get("missions"),
        "verdicts": rep.get("verdicts"),
        "by_arc": rep.get("by_arc"),
        "difficulty": difficulty,
        "seed": seed,
        "arcs": list(arcs),
        "agent": rep.get("agent"),
        "use_ant": use_ant,
        "llm_calls": rep.get("llm_calls"),
        "elapsed_s": rep.get("elapsed_s"),
        "story": story_paths,
        "report_dir": str(out),
        "train": train_info,
        "craft": craft_info,
    }
    (out / "summary.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    print(json.dumps(summary, indent=2))
    if verbose:
        print(f"\nCampaign report: {out}")
        if story_paths:
            print(f"Story: {story_paths.get('latest_dir')}")
        if train_info:
            print(f"BAR brain weights: {train_info.get('weights_path')} samples={train_info.get('samples')}")
    return summary


def main() -> int:
    p = argparse.ArgumentParser(description="Beat full Verdance campaign (3 arcs)")
    p.add_argument(
        "--difficulty",
        type=float,
        default=None,
        help="Base difficulty (default: craft recipe difficulty, else 1.0)",
    )
    p.add_argument("--base-seed", type=int, default=11)
    p.add_argument("--arcs", type=str, default="1,2,3", help="Comma arcs e.g. 1,2,3 or 2")
    p.add_argument("--ant", action="store_true")
    p.add_argument("--llm", action="store_true")
    p.add_argument("--ant-every", type=int, default=6)
    p.add_argument("--train", action="store_true", default=True, help="Train bar_brain (default on)")
    p.add_argument("--no-train", action="store_true")
    p.add_argument("--no-craft", action="store_true", help="Skip champion craft stamp")
    p.add_argument("--quiet", action="store_true")
    p.add_argument("--once", action="store_true", default=True, help="Single run (default)")
    args = p.parse_args()

    arcs = _parse_arcs(args.arcs)
    train = args.train and not args.no_train
    if args.difficulty is None:
        from .craft_apply import recipe_difficulty

        difficulty = recipe_difficulty(1.0)
    else:
        difficulty = float(args.difficulty)
    summary = run_once(
        difficulty=difficulty,
        seed=args.base_seed,
        arcs=arcs,
        use_ant=args.ant,
        use_llm=args.llm and not args.ant,
        ant_every_n=args.ant_every,
        train=train,
        verbose=not args.quiet,
        use_craft=not args.no_craft,
    )
    ok = bool(summary.get("cleared") or summary.get("cleared_all_arcs"))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
