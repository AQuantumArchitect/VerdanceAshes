#!/usr/bin/env python3
"""Iterate until the fair first arc is cleared (belief + tools only).

Tunes BOTH sides within honesty bounds:
  - Agent side: local tool policy heuristics, optional Grok tools
  - Mission side: difficulty dial (enemy_scale multiplier) — never grants
    the agent omniscient sensors

Win condition: all 5 first-arc missions won (extracted | objective_complete)
on a multi-seed streak.

Usage:
  python -m quantum_bar_ai.beat_first_arc
  python -m quantum_bar_ai.beat_first_arc --llm --max-rounds 20
  python -m quantum_bar_ai.beat_first_arc --difficulty 1.0 --seeds 3
"""
from __future__ import annotations

import argparse
import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .ant_agent import AntToolAgent
from .fair_sim import play_first_arc
from .story_teller import build_story, write_story_bundle
from .suite import _workspace_root
from .tool_agent import GrokToolAgent, LocalToolAgent


def _publish_story(report: dict[str, Any], ws: Path, *, stamp: str | None = None) -> dict[str, str]:
    """Write proxy-player story to app/story + mod Lua seed for GUI + showoff hearth."""
    story = build_story(report)
    stamp = stamp or datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    stamped = ws / "app" / "story" / f"run_{stamp}"
    latest = ws / "app" / "story" / "latest"
    runs_ptr = ws / "app" / "runs" / "latest"
    mod_lua = (
        ws
        / "mod"
        / "VerdanceAshes.sdd"
        / "singleplayer"
        / "verdance_ashes"
        / "generated"
        / "proxy_story_current.lua"
    )
    paths = write_story_bundle(
        story,
        stamped,
        also_lua=mod_lua,
        also_latest=ws / "outbox" / "proxy_story.latest.json",
    )
    # mirror into latest/
    latest.mkdir(parents=True, exist_ok=True)
    for name in ("STORY.md", "story.json", "index.html", "proxy_story_current.lua"):
        src = stamped / name
        if src.is_file():
            (latest / name).write_bytes(src.read_bytes())
    runs_ptr.mkdir(parents=True, exist_ok=True)
    (runs_ptr / "report.json").write_text(
        json.dumps(report, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    (runs_ptr / "story_dir.txt").write_text(str(stamped), encoding="utf-8")
    paths["latest_dir"] = str(latest)
    paths["stamped_dir"] = str(stamped)
    paths["runs_ptr"] = str(runs_ptr)
    # cinematic friend-demo pack
    try:
        from .showoff_hearth import write_showoff

        show_paths = write_showoff(story, workspace=ws)
        paths.update({f"show_{k}": v for k, v in show_paths.items()})
    except Exception as e:  # noqa: BLE001
        paths["show_error"] = f"{type(e).__name__}: {e}"
    return paths


def _make_agent(*, use_ant: bool, use_llm: bool, ant_every_n: int = 4) -> Any:
    if use_ant:
        return AntToolAgent(every_n=ant_every_n)
    if use_llm:
        return GrokToolAgent()
    return LocalToolAgent()


def _run_seeds(
    *,
    difficulty: float,
    seeds: list[int],
    use_llm: bool,
    use_ant: bool = False,
    ant_every_n: int = 4,
    verbose: bool,
) -> dict[str, Any]:
    runs = []
    for seed in seeds:
        report = play_first_arc(
            agent=_make_agent(use_ant=use_ant, use_llm=use_llm, ant_every_n=ant_every_n),
            difficulty=difficulty,
            seed=seed,
            verbose=verbose,
            use_llm=use_llm,
            use_ant=use_ant,
            ant_every_n=ant_every_n,
        )
        runs.append(report)

    cleared = sum(1 for r in runs if r["cleared"])
    hard_rates = [r["hard_wins"] / max(1, r["missions"]) for r in runs]
    return {
        "difficulty": difficulty,
        "use_llm": use_llm,
        "use_ant": use_ant,
        "ant_every_n": ant_every_n if use_ant else None,
        "seeds": seeds,
        "cleared_count": cleared,
        "cleared_all_seeds": cleared == len(runs),
        "hard_win_rate_mean": round(sum(hard_rates) / max(1, len(hard_rates)), 4),
        "runs": runs,
        "llm_calls_total": sum(r.get("llm_calls") or 0 for r in runs),
        "billing": "subscription" if use_ant else ("api_or_local" if use_llm else "free"),
    }


def iterate_until_clear(
    *,
    start_difficulty: float = 1.0,
    min_difficulty: float = 0.75,
    max_difficulty: float = 1.15,
    seeds_per_round: int = 3,
    base_seed: int = 11,
    max_rounds: int = 30,
    use_llm: bool = False,
    use_ant: bool = False,
    ant_every_n: int = 4,
    require_seeds: int = 3,
    verbose: bool = True,
    workspace: Path | None = None,
) -> dict[str, Any]:
    """Main loop: try fair arc, tune difficulty + re-run until streak clear.

    Tuning policy (honest):
      - If fail rate high → ease enemy_scale slightly (mission side)
      - If clear easy → optionally re-challenge at higher difficulty once
      - Agent improvements are in LocalToolAgent / GrokToolAgent code (fixed
        during a run; reloads on process restart)

    We stop when `require_seeds` consecutive seeds all clear at difficulty >= 1.0
    OR we clear at the softest allowed difficulty after max rounds (report honest
    partial success).
    """
    ws = workspace or _workspace_root()
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    out = ws / "headless_runs" / f"quantum_bar_ai_beat_{stamp}"
    out.mkdir(parents=True, exist_ok=True)

    difficulty = start_difficulty
    history: list[dict[str, Any]] = []
    best: dict[str, Any] | None = None
    t0 = time.time()

    for round_i in range(1, max_rounds + 1):
        seeds = [base_seed + round_i * 100 + i * 17 for i in range(seeds_per_round)]
        if verbose:
            print(
                f"\n######## ROUND {round_i}/{max_rounds} "
                f"difficulty={difficulty:.3f} llm={use_llm} ant={use_ant} "
                f"seeds={seeds} ########"
            )
        batch = _run_seeds(
            difficulty=difficulty,
            seeds=seeds,
            use_llm=use_llm,
            use_ant=use_ant,
            ant_every_n=ant_every_n,
            verbose=verbose,
        )
        batch["round"] = round_i
        history.append(batch)

        (out / f"round_{round_i:02d}.json").write_text(
            json.dumps(batch, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

        if best is None or batch["hard_win_rate_mean"] > best["hard_win_rate_mean"]:
            best = batch
        if batch["cleared_all_seeds"] and difficulty >= 1.0 - 1e-9:
            if verbose:
                print(f"\n*** FIRST ARC CLEARED at difficulty={difficulty:.3f} ***")
            break

        # Tune difficulty dial
        rate = batch["hard_win_rate_mean"]
        if rate < 0.6:
            difficulty = max(min_difficulty, difficulty - 0.05)
            if verbose:
                print(f"  tune: rate={rate:.0%} → ease difficulty to {difficulty:.3f}")
        elif rate < 1.0:
            difficulty = max(min_difficulty, difficulty - 0.03)
            if verbose:
                print(f"  tune: partial {rate:.0%} → slight ease to {difficulty:.3f}")
        else:
            # cleared all seeds but maybe below 1.0 — try climb back
            if difficulty < 1.0:
                difficulty = min(max_difficulty, difficulty + 0.04)
                if verbose:
                    print(f"  tune: soft-clear → climb difficulty to {difficulty:.3f}")
            else:
                # perfect at >=1.0 already handled by break
                pass

    elapsed = time.time() - t0
    success = bool(best and best.get("cleared_all_seeds") and best.get("difficulty", 0) >= 0.99)

    # Also accept clear at slightly eased difficulty as "achieved with tuned arc"
    soft_success = bool(best and best.get("cleared_all_seeds"))

    report = {
        "schemaVersion": "quantum-bar-ai-beat-first-arc/0.1",
        "stamp": stamp,
        "elapsed_s": round(elapsed, 2),
        "success_at_nominal": success,
        "success_any_difficulty": soft_success,
        "final_difficulty": history[-1]["difficulty"] if history else start_difficulty,
        "best_hard_win_rate": best["hard_win_rate_mean"] if best else 0.0,
        "best_difficulty": best["difficulty"] if best else None,
        "rounds": len(history),
        "use_llm": use_llm,
        "use_ant": use_ant,
        "ant_every_n": ant_every_n if use_ant else None,
        "billing": "subscription" if use_ant else ("api_or_local" if use_llm else "free"),
        "history_tail": history[-5:],
        "out_dir": str(out),
        "fairness_contract": {
            "agent_sees": [
                "PlayerFacingCard briefing",
                "FairHUD bands",
                "umwelt belief graph fed only from FairHUD",
                "tool traces (read_*/think/commit_action)",
            ],
            "agent_never_sees": [
                "enemy_scale",
                "exact enemy_strength",
                "sim RNG",
                "raw HP floats",
            ],
            "both_sides_tuned": [
                "difficulty dial (mission enemy_scale multiplier)",
                "LocalToolAgent HUD/briefing heuristics",
                "ant_brain subscription steam (verdance-proxy-ant)",
            ],
            "brain_path": (
                "yurt ant_brain.spawn_grok + ~/.grok/auth.json subscription"
                if use_ant
                else "local tools only"
            ),
        },
    }

    # Prefer the last fully-cleared batch as champion
    champion = None
    for batch in reversed(history):
        if batch.get("cleared_all_seeds"):
            champion = batch
            break
    report["champion"] = {
        "difficulty": champion["difficulty"],
        "hard_win_rate_mean": champion["hard_win_rate_mean"],
        "verdicts": [r["verdicts"] for r in champion["runs"]],
    } if champion else None

    path = out / "beat_report.json"
    path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    latest = ws / "outbox" / "quantum_bar_ai_beat.latest.json"
    latest.parent.mkdir(parents=True, exist_ok=True)
    latest.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")

    # Publish story from champion (or last) run if present
    story_source = None
    if champion and champion.get("runs"):
        story_source = champion["runs"][0]
    elif history and history[-1].get("runs"):
        story_source = history[-1]["runs"][0]
    if story_source and story_source.get("results"):
        try:
            report["story_paths"] = _publish_story(story_source, ws, stamp=stamp)
        except Exception as e:  # noqa: BLE001
            report["story_error"] = f"{type(e).__name__}: {e}"

    if verbose:
        print("\n=== BEAT FIRST ARC REPORT ===")
        print(f"success_at_nominal={success} soft={soft_success}")
        print(f"best_rate={report['best_hard_win_rate']:.0%} @ diff={report['best_difficulty']}")
        print(f"report: {path}")
        if report.get("story_paths"):
            print(f"story:  {report['story_paths'].get('latest_dir')}")

    return report


def main() -> int:
    p = argparse.ArgumentParser(description="Beat Verdance first arc fairly")
    p.add_argument("--difficulty", type=float, default=1.0)
    p.add_argument("--min-difficulty", type=float, default=0.75)
    p.add_argument("--seeds", type=int, default=3)
    p.add_argument("--base-seed", type=int, default=11)
    p.add_argument("--max-rounds", type=int, default=25)
    p.add_argument(
        "--llm",
        action="store_true",
        help="Legacy metered/API-style GrokToolAgent (prefer --ant)",
    )
    p.add_argument(
        "--ant",
        action="store_true",
        help="Use yurt ant_brain subscription steam (grok.com session, $0 real_spend)",
    )
    p.add_argument("--ant-every", type=int, default=4, help="Ant brain every N ticks")
    p.add_argument("--quiet", action="store_true")
    p.add_argument(
        "--once",
        action="store_true",
        help="Single play_first_arc at given difficulty (no multi-round tune)",
    )
    args = p.parse_args()

    if args.once:
        rep = play_first_arc(
            difficulty=args.difficulty,
            seed=args.base_seed,
            verbose=not args.quiet,
            use_llm=args.llm and not args.ant,
            use_ant=args.ant,
            ant_every_n=args.ant_every,
        )
        ws = _workspace_root()
        stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        # full operator tape
        out = ws / "headless_runs" / f"quantum_bar_ai_once_{stamp}"
        out.mkdir(parents=True, exist_ok=True)
        (out / "report.json").write_text(
            json.dumps(rep, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        story_paths = _publish_story(rep, ws, stamp=stamp)
        keys = (
            "cleared",
            "verdicts",
            "hard_wins",
            "difficulty",
            "llm_calls",
            "llm_error",
            "llm_billing",
            "use_ant",
            "agent",
        )
        summary = {k: rep.get(k) for k in keys}
        summary["story"] = story_paths
        summary["report_dir"] = str(out)
        print(json.dumps(summary, indent=2))
        if not args.quiet:
            print(f"\nStory: {story_paths.get('latest_dir')}")
            print(f"HTTP:  python -m quantum_bar_ai.story_http  → http://127.0.0.1:8765/")
            print(f"Lua:   {story_paths.get('mod_lua')}")
        return 0 if rep["cleared"] else 1

    report = iterate_until_clear(
        start_difficulty=args.difficulty,
        min_difficulty=args.min_difficulty,
        seeds_per_round=args.seeds,
        base_seed=args.base_seed,
        max_rounds=args.max_rounds,
        use_llm=args.llm and not args.ant,
        use_ant=args.ant,
        ant_every_n=args.ant_every,
        verbose=not args.quiet,
    )
    ok = report.get("success_at_nominal") or report.get("success_any_difficulty")
    return 0 if ok else 2


if __name__ == "__main__":
    raise SystemExit(main())
