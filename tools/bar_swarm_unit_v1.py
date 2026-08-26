#!/usr/bin/env python3
"""One organic BAR swarm unit — proxy train + residual hose (no spring, no densify).

Used by yurt-swarm bar_swarm_bridge when CPU/GPU is free.
  python tools/bar_swarm_unit_v1.py run --sorties 3 --seeds 1 --difficulty 1.4
  python tools/bar_swarm_unit_v1.py referee
  python tools/bar_swarm_unit_v1.py self-test
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

TOOLS = Path(__file__).resolve().parent
WS = TOOLS.parent
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

UMWELT_SRC = Path(r"C:\Users\Luke Spooner\ws-win\umwelt\src")
UMWELT_PY = Path(r"C:\Users\Luke Spooner\ws-win\umwelt\.venv\Scripts\python.exe")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _python() -> str:
    if UMWELT_PY.is_file():
        return str(UMWELT_PY)
    return sys.executable


def _env() -> Dict[str, str]:
    e = dict(os.environ)
    e["PYTHONPATH"] = f"{TOOLS};{UMWELT_SRC}"
    e["QBAI_NO_LLM"] = "1"
    e["PYTHONIOENCODING"] = "utf-8"
    e["PYTHONUTF8"] = "1"
    return e


def _ran_on_default() -> str:
    for key in ("BAR_MUSCLE_NODE", "YURT_NODE"):
        v = (os.environ.get(key) or "").strip().lower()
        if v:
            return v
    try:
        import hive_bar_residual_v1 as residual_mod

        return residual_mod._detect_ran_on()
    except Exception:
        return "unknown"


def run_unit(
    *,
    sorties: int = 3,
    seeds: int = 1,
    seed: int = 41,
    difficulty: float = 1.4,
    ticks: int = 36,
    enemy: str = "both",
    ran_on: Optional[str] = None,
) -> Dict[str, Any]:
    """Run one player-proxy campaign train+hose unit."""
    node = (ran_on or _ran_on_default()).strip().lower() or "unknown"
    py = _python()
    script = TOOLS / "proxy_campaign_v1.py"
    args = [
        py,
        str(script),
        "--workspace",
        str(WS),
        "--sorties",
        str(sorties),
        "--seeds",
        str(seeds),
        "--seed",
        str(seed),
        "--enemy",
        enemy,
        "--difficulty",
        str(difficulty),
        "--ticks",
        str(ticks),
        "--write",
    ]
    t0 = time.time()
    env = _env()
    env["BAR_MUSCLE_NODE"] = node
    proc = subprocess.run(
        args,
        cwd=str(WS),
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=max(600, sorties * seeds * 180),
    )
    wall = round(time.time() - t0, 2)
    # fruit harvest first so residual can pick up swarmDigest
    fruit_info: Dict[str, Any] | None = None
    try:
        import campaign_fruit_v1 as fruit_mod

        fruit_info = fruit_mod.harvest(workspace=WS, apply_craft=True, also_hive=True)
    except Exception as e:
        fruit_info = {"ok": False, "error": f"{type(e).__name__}:{e}"}

    # adaptive difficulty from latest proxy
    diff_info: Dict[str, Any] | None = None
    try:
        import organic_pathway_v1 as pathway

        proxy_path = WS / "outbox" / "proxy_campaign.latest.json"
        if proxy_path.is_file():
            rep = json.loads(proxy_path.read_text(encoding="utf-8"))
            diff_info = pathway.adapt_difficulty_from_proxy(rep, workspace=WS)
        pathway.write_morning_face(workspace=WS)
    except Exception as e:
        diff_info = {"error": f"{type(e).__name__}:{e}"}

    # hose residual + arena best-effort
    hose_ok = False
    arena_ok = False
    try:
        import hive_bar_residual_v1 as residual_mod

        proxy_path = WS / "outbox" / "proxy_campaign.latest.json"
        if proxy_path.is_file():
            rep = json.loads(proxy_path.read_text(encoding="utf-8"))
            residual = residual_mod.build_residual(
                rep,
                workspace=WS,
                ran_on=node,
                kind="player_proxy",
            )
            residual_mod.write_residual(residual, WS, also_hive=True)
            hose_ok = True
    except Exception as e:
        hose_err = str(e)
    else:
        hose_err = None
    try:
        sys.path.insert(0, str(TOOLS))
        from quantum_bar_ai.hive_gym_arena import run_arena

        ar = run_arena(workspace=WS, write=True)
        arena_ok = bool(ar.get("pass") or not ar.get("fraudFlags"))
    except Exception:
        pass

    out = {
        "schema": "bar-swarm-unit/1.0",
        "kind": "player_proxy",
        "at": _now(),
        "ran_on": node,
        "rc": proc.returncode,
        "wall_s": wall,
        "ok": proc.returncode == 0,
        "hose_ok": hose_ok,
        "hose_err": hose_err,
        "arena_ok": arena_ok,
        "fruit": {
            "ideas": len((fruit_info or {}).get("ideas") or []),
            "craft": (fruit_info or {}).get("craft"),
            "error": (fruit_info or {}).get("error"),
        },
        "difficulty_adapt": diff_info,
        "stdout_tail": (proc.stdout or "")[-1500:],
        "stderr_tail": (proc.stderr or "")[-800:],
        "params": {
            "sorties": sorties,
            "seeds": seeds,
            "seed": seed,
            "difficulty": difficulty,
            "ticks": ticks,
            "enemy": enemy,
            "ran_on": node,
        },
    }
    face = WS / "outbox" / "bar_swarm_unit.latest.json"
    face.parent.mkdir(parents=True, exist_ok=True)
    face.write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")
    return out


def referee_check(*, min_ul_updates: int = 0) -> Dict[str, Any]:
    """Honest residual referee — densify banned, residual present."""
    residual_path = WS / "outbox" / "hive_bar_residual.latest.json"
    hive_path = Path(
        r"C:\Users\Luke Spooner\ws-win\yurt-sync\commons\vitals\bar_proxy_residual.latest.json"
    )
    unit_path = WS / "outbox" / "bar_swarm_unit.latest.json"
    reasons: list[str] = []
    residual: Dict[str, Any] = {}
    if not residual_path.is_file():
        reasons.append("missing_operator_residual")
    else:
        try:
            residual = json.loads(residual_path.read_text(encoding="utf-8"))
        except Exception as e:
            reasons.append(f"residual_parse:{e}")
    honesty = residual.get("honesty") or {}
    if honesty.get("barDensifyBanned") is not True:
        reasons.append("densify_not_banned")
    if honesty.get("nObsWall") is not None and int(honesty.get("nObsWall")) > 15:
        reasons.append("n_obs_wall_raised")
    if honesty.get("godBrainMerge") is True:
        reasons.append("god_brain_merge")
    brain = residual.get("brain") or {}
    ul = int(brain.get("ulUpdateCount") or 0)
    if min_ul_updates and ul < min_ul_updates:
        reasons.append(f"ul_updates_low:{ul}<{min_ul_updates}")
    if not hive_path.is_file():
        reasons.append("missing_hive_residual")
    if not unit_path.is_file():
        reasons.append("missing_unit_face")
    # ran_on is expected on new residuals; missing is a warning (legacy residual OK)
    ran_on = residual.get("ran_on") or residual.get("muscleNode")
    warnings: list[str] = []
    if residual and not ran_on:
        warnings.append("missing_ran_on_legacy")
    ok = len(reasons) == 0
    report = {
        "schema": "bar-swarm-unit-referee/1.0",
        "kind": "player_proxy",
        "at": _now(),
        "ok": ok,
        "reasons": reasons,
        "warnings": warnings,
        "ulUpdateCount": ul,
        "ran_on": ran_on,
        "residual_at": residual.get("at"),
        "honesty": honesty,
    }
    (WS / "outbox" / "bar_swarm_unit_referee.latest.json").write_text(
        json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    return report


def self_test() -> int:
    r = referee_check(min_ul_updates=0)
    # after a real run residual may exist; self-test only checks function runs
    print("bar_swarm_unit self_test referee shape OK", r.get("ok"), r.get("reasons"))
    return 0


def main(argv: Optional[list] = None) -> int:
    ap = argparse.ArgumentParser(description="BAR swarm organic unit")
    sub = ap.add_subparsers(dest="cmd", required=True)

    run_p = sub.add_parser("run", help="run one player-proxy+UL+hose unit")
    run_p.add_argument("--sorties", type=int, default=3)
    run_p.add_argument("--seeds", type=int, default=1)
    run_p.add_argument("--seed", type=int, default=41)
    run_p.add_argument("--difficulty", type=float, default=1.4)
    run_p.add_argument("--ticks", type=int, default=36)
    run_p.add_argument("--enemy", default="both")
    run_p.add_argument("--ran-on", default="", help="muscle node id (wargen|roc|…)")

    ref_p = sub.add_parser("referee", help="check residual honesty")
    ref_p.add_argument("--min-ul", type=int, default=0)

    sub.add_parser("self-test")

    args = ap.parse_args(argv)
    if args.cmd == "run":
        out = run_unit(
            sorties=args.sorties,
            seeds=args.seeds,
            seed=args.seed,
            difficulty=args.difficulty,
            ticks=args.ticks,
            enemy=args.enemy,
            ran_on=(args.ran_on or None),
        )
        print(
            json.dumps(
                {k: out[k] for k in ("ok", "rc", "wall_s", "hose_ok", "arena_ok", "ran_on", "kind") if k in out},
                indent=2,
            )
        )
        return 0 if out.get("ok") else 1
    if args.cmd == "referee":
        r = referee_check(min_ul_updates=args.min_ul)
        print(json.dumps(r, indent=2))
        return 0 if r.get("ok") else 1
    if args.cmd == "self-test":
        return self_test()
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
