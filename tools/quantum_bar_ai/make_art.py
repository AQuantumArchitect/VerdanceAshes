#!/usr/bin/env python3
"""Ceremony: clear campaign · train brain · publish gallery · lock multi-seed · export notes.

  python -m quantum_bar_ai.make_art
  python -m quantum_bar_ai.make_art --seeds 11,28,45
  python -m quantum_bar_ai.make_art --export
"""
from __future__ import annotations

import argparse
import json
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .bar_brain import BarBrain, ingest_campaign_report, load_weights, save_weights
from .beat_first_arc import _publish_story
from .fair_sim import play_campaign
from .suite import _workspace_root
from .tool_agent import LocalToolAgent


def _run_seed(seed: int, *, difficulty: float, verbose: bool) -> dict[str, Any]:
    agent = LocalToolAgent(use_bar_brain=True)
    return play_campaign(
        agent=agent,
        difficulty=difficulty,
        seed=seed,
        verbose=verbose,
        use_llm=False,
        use_ant=False,
        arcs=(1, 2, 3),
    )


def main() -> int:
    p = argparse.ArgumentParser(description="Verdance campaign art ceremony")
    p.add_argument("--seeds", default="11,28,45", help="comma seeds for lock")
    p.add_argument("--difficulty", type=float, default=1.0)
    p.add_argument("--export", action="store_true", help="run EXPORT_CUSTOMER after")
    p.add_argument("--quiet", action="store_true")
    args = p.parse_args()

    ws = _workspace_root()
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    out = ws / "headless_runs" / f"quantum_bar_ai_art_{stamp}"
    out.mkdir(parents=True, exist_ok=True)
    seeds = [int(s.strip()) for s in args.seeds.split(",") if s.strip()]
    verbose = not args.quiet

    t0 = time.time()
    runs: list[dict[str, Any]] = []
    weights = load_weights()

    for seed in seeds:
        if verbose:
            print(f"\n######## ART SEED {seed} ########")
        rep = _run_seed(seed, difficulty=args.difficulty, verbose=verbose)
        runs.append(rep)
        weights = ingest_campaign_report(rep, weights)

    save_weights(weights)
    # champion = first full clear, else last
    champion = next((r for r in runs if r.get("cleared")), runs[-1] if runs else {})
    story_paths = {}
    if champion.get("results"):
        story_paths = _publish_story(champion, ws, stamp=stamp)

    brain = BarBrain(weights)
    seat = brain.bar_seat_hint(kind="eco_expand")
    seat_siege = brain.bar_seat_hint(kind="siege")

    cleared_seeds = [r.get("seed") for r in runs if r.get("cleared")]
    art = {
        "schemaVersion": "verdance-art-ceremony/0.1",
        "stamp": stamp,
        "elapsed_s": round(time.time() - t0, 2),
        "difficulty": args.difficulty,
        "seeds": seeds,
        "cleared_seeds": cleared_seeds,
        "all_cleared": len(cleared_seeds) == len(seeds),
        "per_seed": [
            {
                "seed": r.get("seed"),
                "cleared": r.get("cleared"),
                "hard_wins": r.get("hard_wins"),
                "missions": r.get("missions"),
                "by_arc": r.get("by_arc"),
                "verdicts": r.get("verdicts"),
            }
            for r in runs
        ],
        "brain": {
            "samples": weights.samples,
            "wins": weights.wins,
            "losses": weights.losses,
            "win_rate": round(
                weights.wins / max(1, weights.wins + weights.losses), 4
            ),
            "seat_eco": seat,
            "seat_siege": seat_siege,
            "weights": str(ws / "app" / "brain" / "bar_brain_weights.json"),
        },
        "story": story_paths,
        "tagline": "A mind that commits under fog — and walks the campaign home.",
        "fairness": "card · HUD · eco bands · belief · tools — never SimTruth",
    }

    (out / "art_report.json").write_text(
        json.dumps(art, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    manifesto = _manifesto(art)
    (out / "MANIFESTO.md").write_text(manifesto, encoding="utf-8")
    (ws / "app" / "story" / "latest" / "MANIFESTO.md").write_text(manifesto, encoding="utf-8")
    (ws / "outbox" / "quantum_bar_ai_art.latest.json").write_text(
        json.dumps(art, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    # also mirror manifesto into outbound art brief
    (ws / "outbound" / "24_CAMPAIGN_ART.md").write_text(manifesto, encoding="utf-8")

    if verbose:
        print("\n=== ART CEREMONY ===")
        print(json.dumps({k: art[k] for k in (
            "all_cleared", "cleared_seeds", "elapsed_s", "brain", "story"
        ) if k in art}, indent=2))
        print(f"\nManifesto: {out / 'MANIFESTO.md'}")
        print(f"Hearth:    {story_paths.get('latest_dir')}")
        print("Serve:     python -m quantum_bar_ai.story_http")

    if args.export:
        if verbose:
            print("\n=== EXPORT CUSTOMER v0.5.0 ===")
        ps1 = ws / "scripts" / "export_customer_release.ps1"
        if ps1.is_file():
            subprocess.run(
                [
                    "powershell",
                    "-NoProfile",
                    "-ExecutionPolicy",
                    "Bypass",
                    "-File",
                    str(ps1),
                    "-Version",
                    "0.5.0",
                ],
                cwd=str(ws),
                check=False,
            )

    return 0 if art.get("all_cleared") else 1


def _manifesto(art: dict[str, Any]) -> str:
    # ASCII-friendly for Windows consoles / Notepad defaults
    tag = (art.get("tagline") or "").replace("—", "-").replace("–", "-")
    fair = (art.get("fairness") or "").replace("—", "-").replace("·", "|")
    lines = [
        "# Verdance's Ashes - Campaign Art",
        "",
        f"*{tag}*",
        "",
        f"Generated `{art.get('stamp')}` | difficulty `{art.get('difficulty')}` | "
        f"elapsed `{art.get('elapsed_s')}s`",
        "",
        "## Multi-seed lock",
        "",
        f"Seeds: `{', '.join(str(s) for s in art.get('seeds') or [])}`",
        f"Cleared: `{', '.join(str(s) for s in art.get('cleared_seeds') or [])}`",
        f"**All cleared:** `{art.get('all_cleared')}`",
        "",
        "| Seed | Wins | Arc1 | Arc2 | Arc3 |",
        "|------|------|------|------|------|",
    ]
    for row in art.get("per_seed") or []:
        ba = row.get("by_arc") or {}

        def arc_s(k: str) -> str:
            b = ba.get(k) or {}
            return f"{b.get('wins', '?')}/{b.get('total', '?')}"

        lines.append(
            f"| {row.get('seed')} | {row.get('hard_wins')}/{row.get('missions')} | "
            f"{arc_s('1')} | {arc_s('2')} | {arc_s('3')} |"
        )
    br = art.get("brain") or {}
    lines += [
        "",
        "## Super quantum BAR brain",
        "",
        f"- Samples trained: **{br.get('samples')}**",
        f"- Win rate (tape missions): **{br.get('win_rate')}**",
        f"- Weights: `{br.get('weights')}`",
        f"- Eco seat hint: `{(br.get('seat_eco') or {}).get('style')}` / "
        f"controller `{(br.get('seat_eco') or {}).get('player_controller')}`",
        f"- Siege seat hint: `{(br.get('seat_siege') or {}).get('style')}`",
        "",
        "## Fairness (the aesthetic constraint)",
        "",
        fair,
        "",
        "The proxy never gets the hidden sim. The art is *commitment under fog* -",
        "briefing, coarse HUD, eco bands, belief graph, tools - then extract or die trying.",
        "",
        "## How to witness",
        "",
        "```",
        "app\\bin\\SERVE_STORY.bat          -> http://127.0.0.1:8765/",
        "In BAR: /vastory                 -> Lua campaign hearth",
        "Customer: My Games\\VerdanceAshes -> WATCH_STORY.bat",
        "```",
        "",
        "## Three scars",
        "",
        "1. **First Scar** - strike team, no base, five raids",
        "2. **Second Scar** - expand, converters, tempo",
        "3. **Third Scar** - bastion siege, wild corridor, simmer multipressure",
        "",
        "- end of manifesto -",
        "",
    ]
    return "\n".join(lines)


if __name__ == "__main__":
    raise SystemExit(main())
