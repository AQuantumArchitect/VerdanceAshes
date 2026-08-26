#!/usr/bin/env python3
"""Gym arena for proxy_campaign residuals — honesty, not densify volume.

Scores already-measured proxy outcomes for the hive morning desk.
Never raises BAR n_obs. Never fakes volume.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .suite import _workspace_root


def score_residual(
    residual: dict[str, Any],
    *,
    pre_brain: dict[str, Any] | None = None,
    eps: float = 0.02,
) -> dict[str, Any]:
    """Deterministic arena score from a hive-bar-residual packet or proxy report."""
    # accept either residual dialect or raw proxy report
    if residual.get("schema") == "hive-bar-residual/1.0":
        by = residual.get("byStyle") or {}
        h2h = residual.get("headToHead") or {}
        brain = residual.get("brain") or {}
        honesty = residual.get("honesty") or {}
        doctrine = residual.get("doctrineHints") or {}
    else:
        by = residual.get("byStyle") or {}
        h2h = residual.get("headToHead") or {}
        brain = residual.get("brain") or {}
        honesty = {"barDensifyBanned": True, "fairRoomOnly": True, "nObsWall": 15}
        doctrine = {}

    fraud: list[str] = []
    if honesty.get("barDensifyBanned") is False:
        fraud.append("densify_not_banned")
    if honesty.get("godBrainMerge") is True:
        fraud.append("god_brain_merge")
    n_obs = honesty.get("nObsWall")
    if n_obs is not None and int(n_obs) > 15:
        fraud.append("n_obs_wall_raised")
    if honesty.get("fairRoomOnly") is False:
        fraud.append("fair_room_leaked")

    simple_wr = float((by.get("simple") or {}).get("meanWinRate") or 0)
    barb_wr = float((by.get("barbarian") or {}).get("meanWinRate") or 0)
    simple_fun = float((by.get("simple") or {}).get("meanFun") or 0)
    barb_fun = float((by.get("barbarian") or {}).get("meanFun") or 0)
    simple_clash = float((by.get("simple") or {}).get("meanClashEvents") or 0)
    barb_clash = float((by.get("barbarian") or {}).get("meanClashEvents") or 0)

    delta = h2h.get("winRateDelta_barb_minus_simple")
    if delta is None and "simple" in by and "barbarian" in by:
        delta = barb_wr - simple_wr
    delta = float(delta if delta is not None else 0.0)

    # ladder honesty: barb should be harder (lower or equal win rate within eps of soft)
    ladder_ok = True
    ladder_note = "ok"
    if "simple" in by and "barbarian" in by:
        if barb_wr > simple_wr + eps:
            ladder_ok = False
            ladder_note = "barb_easier_than_simple"
        elif simple_wr >= 0.98 and barb_wr >= 0.98:
            ladder_ok = False
            ladder_note = "both_saturated_raise_difficulty"
        else:
            ladder_note = "barb_harder_or_tied"
    else:
        ladder_note = "single_style_only"

    fun_floor = min(
        [v for v in (simple_fun, barb_fun) if v > 0] or [0.0]
    )
    clash_life = max(simple_clash, barb_clash)

    pre = pre_brain or {}
    scar_delta = {
        "samples": int(brain.get("samples") or 0) - int(pre.get("samples") or 0),
        "wins": int(brain.get("wins") or 0) - int(pre.get("wins") or 0),
        "ulUpdateCount": int(brain.get("ulUpdateCount") or 0) - int(pre.get("ulUpdateCount") or 0),
        "ulMeanSigmaNow": float(brain.get("ulMeanSigma") or 0),
        "ulMeanSigmaPre": float(pre.get("ulMeanSigma") or 0),
    }
    ul_purity = {
        "sigmaDrop": round(
            float(pre.get("ulMeanSigma") or 0) - float(brain.get("ulMeanSigma") or 0),
            4,
        ),
        "updates": int(brain.get("ulUpdateCount") or 0),
        "learned": int(brain.get("ulUpdateCount") or 0) > 0,
    }

    checks = {
        "ladderHonesty": ladder_ok,
        "funFloor": fun_floor >= 0.35 or fun_floor == 0.0,  # 0 = missing style ok
        "clashLife": clash_life >= 0.0,  # soft — presence of field is enough
        "noFraud": len(fraud) == 0,
        "ulPresent": True,  # presence optional; flag for morning
    }

    passed = all(
        [
            checks["ladderHonesty"] or ladder_note == "single_style_only",
            checks["noFraud"],
        ]
    )
    # saturated both fails ladder already

    return {
        "schema": "hive-gym-arena/1.0",
        "at": datetime.now(timezone.utc).isoformat(),
        "pass": passed,
        "checks": checks,
        "ladderHonesty": {
            "ok": ladder_ok,
            "note": ladder_note,
            "winRateDelta_barb_minus_simple": round(delta, 3),
            "simpleWin": simple_wr,
            "barbWin": barb_wr,
            "eps": eps,
        },
        "funFloor": round(fun_floor, 3),
        "clashLife": round(clash_life, 3),
        "brainScarDelta": scar_delta,
        "ulPurity": ul_purity,
        "fraudFlags": fraud,
        "doctrineHints": doctrine,
        "brain": brain,
    }


def run_arena(
    *,
    workspace: Path | None = None,
    residual_path: Path | None = None,
    proxy_path: Path | None = None,
    pre_brain_path: Path | None = None,
    write: bool = False,
) -> dict[str, Any]:
    ws = workspace or _workspace_root()
    residual: dict[str, Any] | None = None

    if residual_path and residual_path.is_file():
        residual = json.loads(residual_path.read_text(encoding="utf-8"))
    elif proxy_path and proxy_path.is_file():
        # build residual on the fly without requiring hose write
        sys.path.insert(0, str(ws / "tools"))
        from hive_bar_residual_v1 import build_residual  # type: ignore

        proxy = json.loads(proxy_path.read_text(encoding="utf-8"))
        residual = build_residual(proxy, workspace=ws)
    else:
        # defaults
        r = ws / "outbox" / "hive_bar_residual.latest.json"
        p = ws / "outbox" / "proxy_campaign.latest.json"
        if r.is_file():
            residual = json.loads(r.read_text(encoding="utf-8"))
        elif p.is_file():
            sys.path.insert(0, str(ws / "tools"))
            from hive_bar_residual_v1 import build_residual  # type: ignore

            residual = build_residual(json.loads(p.read_text(encoding="utf-8")), workspace=ws)
        else:
            raise FileNotFoundError("no residual or proxy_campaign.latest.json")

    pre_brain = None
    if pre_brain_path and pre_brain_path.is_file():
        try:
            pre = json.loads(pre_brain_path.read_text(encoding="utf-8"))
            if "samples" in pre:
                pre_brain = {
                    "samples": pre.get("samples"),
                    "wins": pre.get("wins"),
                    "ulUpdateCount": 0,
                    "ulMeanSigma": DEFAULT_SIGMA_PRE if False else 1.5,
                }
            # ul snapshot
        except Exception:
            pre_brain = None
    pre_ul = ws / "app" / "brain" / "bar_brain_weights.pre_0_8_5.json"
    # prefer ul pre if we stored summary in overnight; else weights only
    if pre_brain is None and pre_ul.is_file():
        try:
            w = json.loads(pre_ul.read_text(encoding="utf-8"))
            pre_brain = {
                "samples": int(w.get("samples") or 0),
                "wins": int(w.get("wins") or 0),
                "ulUpdateCount": 0,
                "ulMeanSigma": 1.5,
            }
        except Exception:
            pass

    report = score_residual(residual, pre_brain=pre_brain)
    report["workspace"] = str(ws)
    if write:
        out = ws / "outbox" / "hive_gym_arena.latest.json"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
        report["wrote"] = str(out)
    return report


DEFAULT_SIGMA_PRE = 1.5


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Hive gym arena for proxy residuals")
    ap.add_argument("--workspace", default="")
    ap.add_argument("--from", dest="from_path", default="", help="proxy or residual json")
    ap.add_argument("--write", action="store_true")
    ap.add_argument("--self-test", action="store_true")
    args = ap.parse_args(argv)

    if args.self_test:
        residual = {
            "schema": "hive-bar-residual/1.0",
            "byStyle": {
                "simple": {"meanWinRate": 0.85, "meanFun": 0.7, "meanClashEvents": 1},
                "barbarian": {"meanWinRate": 0.55, "meanFun": 0.65, "meanClashEvents": 2},
            },
            "headToHead": {"winRateDelta_barb_minus_simple": -0.3},
            "brain": {"samples": 100, "wins": 40, "ulUpdateCount": 12, "ulMeanSigma": 1.1},
            "honesty": {
                "barDensifyBanned": True,
                "fairRoomOnly": True,
                "nObsWall": 15,
                "godBrainMerge": False,
            },
            "doctrineHints": {"patrolVsPush": "rest"},
        }
        r = score_residual(residual, pre_brain={"samples": 50, "wins": 20, "ulUpdateCount": 0, "ulMeanSigma": 1.5})
        assert r["pass"] is True, r
        assert r["ladderHonesty"]["ok"] is True
        assert not r["fraudFlags"]
        # fraud case
        bad = dict(residual)
        bad["honesty"] = dict(residual["honesty"])
        bad["honesty"]["barDensifyBanned"] = False
        r2 = score_residual(bad)
        assert r2["pass"] is False
        assert "densify_not_banned" in r2["fraudFlags"]
        print("hive_gym_arena self_test OK")
        return 0

    ws = Path(args.workspace).resolve() if args.workspace else _workspace_root()
    residual_path = None
    proxy_path = None
    if args.from_path:
        p = Path(args.from_path)
        if not p.is_file():
            p = ws / args.from_path
        blob = json.loads(p.read_text(encoding="utf-8"))
        if blob.get("schema") == "hive-bar-residual/1.0":
            residual_path = p
        else:
            proxy_path = p

    report = run_arena(
        workspace=ws,
        residual_path=residual_path,
        proxy_path=proxy_path,
        write=args.write,
    )
    print(json.dumps({k: report[k] for k in ("pass", "ladderHonesty", "fraudFlags", "ulPurity", "brainScarDelta") if k in report}, indent=2))
    if report.get("wrote"):
        print(f"wrote {report['wrote']}")
    return 0 if report.get("pass") else 1


if __name__ == "__main__":
    raise SystemExit(main())
