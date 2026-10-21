#!/usr/bin/env python3
"""Hive <-> BAR residual hose (file vitals dialect).

Thin bidirectional residual — NOT a god-brain merge.
BAR densify remains BANNED (honesty.nObsWall = 15).

Usage:
  python tools/hive_bar_residual_v1.py --from outbox/proxy_campaign.latest.json --write
  python tools/hive_bar_residual_v1.py --self-test
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence


SCHEMA = "hive-bar-residual/1.1"
SCHEMA_LEGACY = "hive-bar-residual/1.0"
N_OBS_WALL = 15


def _workspace_from_arg(path: Path) -> Path:
    p = path.resolve()
    if (p / "tools").is_dir() and (p / "VERSION").is_file():
        return p
    if p.parent.name == "outbox":
        return p.parent.parent
    return p if p.is_dir() else p.parent


def read_version(workspace: Path) -> str:
    vf = workspace / "VERSION"
    if vf.is_file():
        return vf.read_text(encoding="utf-8").strip()
    return "0.0.0"


def load_brain_summary(workspace: Path) -> Dict[str, Any]:
    out: Dict[str, Any] = {
        "samples": 0,
        "wins": 0,
        "losses": 0,
        "ulFamily": "width_action+eco_action",
        "ulUpdateCount": 0,
        "ulMeanSigma": 0.0,
        "ulMissions": 0,
        "ulWidthUpdates": 0,
        "ulEcoUpdates": 0,
        "ulFamilies": ["width_action", "eco_action"],
    }
    weights = workspace / "app" / "brain" / "bar_brain_weights.json"
    if weights.is_file():
        try:
            w = json.loads(weights.read_text(encoding="utf-8"))
            out["samples"] = int(w.get("samples") or 0)
            out["wins"] = int(w.get("wins") or 0)
            out["losses"] = int(w.get("losses") or 0)
        except Exception:
            pass
    ul_path = workspace / "app" / "brain" / "bar_brain_ul_state.json"
    if ul_path.is_file():
        try:
            ul = json.loads(ul_path.read_text(encoding="utf-8"))
            summary = ul.get("summary") or {}
            out["ulFamily"] = str(ul.get("family") or summary.get("ulFamily") or "width_action")
            out["ulUpdateCount"] = int(summary.get("ulUpdateCount") or ul.get("total_reinforces") or 0)
            out["ulMeanSigma"] = float(summary.get("ulMeanSigma") or 0.0)
            out["ulMissions"] = int(summary.get("ulMissions") or ul.get("missions") or 0)
            if summary.get("ulWidthUpdates") is not None:
                out["ulWidthUpdates"] = int(summary.get("ulWidthUpdates") or 0)
            if summary.get("ulEcoUpdates") is not None:
                out["ulEcoUpdates"] = int(summary.get("ulEcoUpdates") or 0)
            if ul.get("families"):
                out["ulFamilies"] = ul.get("families")
        except Exception:
            pass
    return out


def load_doctrine_hints(workspace: Path) -> Dict[str, Any]:
    hints: Dict[str, Any] = {
        "patrolVsPush": "rest",
        "note": "soft prior only — never command fair agent",
        "source": None,
    }
    candidates = [
        workspace / "outbox" / "bar_swarm_doctrine_soft.json",
        Path(r"C:\Users\Luke Spooner\ws-win\yurt-sync\commons\vitals\bar_swarm_doctrine_soft.json"),
        Path(r"C:\Users\Luke Spooner\ws-win\yurt-sync\commons\vitals\hive_rts_state.json"),
        Path.home() / "ws-win" / "yurt-sync" / "commons" / "vitals" / "hive_rts_state.json",
    ]
    for p in candidates:
        if not p.is_file():
            continue
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
            posture = (
                data.get("posture")
                or data.get("soft_doctrine")
                or (data.get("swarm_digest") or {}).get("soft_doctrine")
                or data.get("missionPosture")
                or (data.get("mission") or {}).get("posture")
                or data.get("mode")
                or "rest"
            )
            hints["patrolVsPush"] = str(posture)
            hints["source"] = str(p)
            if data.get("learned_bias"):
                hints["learned_bias"] = data.get("learned_bias")
            break
        except Exception:
            continue
    return hints


def _detect_ran_on() -> str:
    """Host-agnostic muscle tag for residual producers."""
    import os
    import socket

    for key in ("BAR_MUSCLE_NODE", "YURT_NODE", "YURT_SEAT_NODE"):
        v = (os.environ.get(key) or "").strip().lower()
        if v:
            return v
    host = socket.gethostname().strip().lower()
    if "wargen" in host:
        return "wargen"
    if "roc" in host:
        return "roc"
    if "oa2it77" in host:
        return "oa2it77"
    return host or "unknown"


def _load_swarm_digest(workspace: Path) -> Optional[Dict[str, Any]]:
    candidates = [
        workspace / "outbox" / "campaign_fruit.latest.json",
        Path(r"C:\Users\Luke Spooner\ws-win\yurt-sync\commons\vitals\bar_campaign_fruit.latest.json"),
        workspace / "outbox" / "bar_swarm_doctrine_soft.json",
    ]
    for p in candidates:
        if not p.is_file():
            continue
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            continue
        if "swarm_digest" in data and isinstance(data["swarm_digest"], dict):
            return data["swarm_digest"]
        if data.get("schema") == "bar-swarm-doctrine-soft/1.0":
            return {
                "soft_doctrine": data.get("posture") or "rest",
                "note": data.get("note"),
                "learned_bias": data.get("learned_bias") or [],
            }
    return None


def build_residual(
    proxy_report: Dict[str, Any],
    *,
    workspace: Path,
    source: str = "proxy_campaign_v1",
    doctrine: Optional[Dict[str, Any]] = None,
    ran_on: Optional[str] = None,
    kind: str = "player_proxy",
    swarm_digest: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    by_style = dict(proxy_report.get("byStyle") or {})
    # normalize style rows
    norm_styles: Dict[str, Any] = {}
    for style, row in by_style.items():
        if not isinstance(row, dict):
            continue
        norm_styles[style] = {
            "meanWinRate": float(row.get("meanWinRate") or 0),
            "meanFun": float(row.get("meanFun") or 0),
            "meanTnb": float(row.get("meanTnb") or 0),
            "meanClashEvents": float(row.get("meanClashEvents") or 0),
            "n": int(row.get("runs") or 0),
            "barEnemy": row.get("barEnemy"),
            "playerControllerHist": row.get("playerControllerHist") or {},
        }

    h2h = proxy_report.get("headToHead")
    if h2h is None and "simple" in norm_styles and "barbarian" in norm_styles:
        h2h = {
            "winRateDelta_barb_minus_simple": round(
                norm_styles["barbarian"]["meanWinRate"] - norm_styles["simple"]["meanWinRate"],
                3,
            ),
            "funDelta_barb_minus_simple": round(
                norm_styles["barbarian"]["meanFun"] - norm_styles["simple"]["meanFun"],
                3,
            ),
        }

    muscle = (ran_on or _detect_ran_on()).strip().lower() or "unknown"
    train = proxy_report.get("train") or {}
    mission_count = (
        train.get("nMissions")
        or (proxy_report.get("fairTrainReport") or {}).get("nMissions")
        or proxy_report.get("sorties")
    )
    digest = swarm_digest if swarm_digest is not None else _load_swarm_digest(workspace)
    residual: Dict[str, Any] = {
        "schema": SCHEMA,
        "at": datetime.now(timezone.utc).isoformat(),
        "source": source,
        "kind": kind,
        "ran_on": muscle,
        "muscleNode": muscle,
        "workspaceVersion": read_version(workspace),
        "proxyMeta": {
            "sorties": proxy_report.get("sorties"),
            "seeds": proxy_report.get("seeds"),
            "difficulty": proxy_report.get("difficulty"),
            "durationTicks": proxy_report.get("durationTicks"),
            "homeMap": proxy_report.get("homeMap"),
            "generatedAt": proxy_report.get("generatedAt"),
            "playerProxy": True,
        },
        "byStyle": norm_styles,
        "headToHead": h2h,
        "brain": load_brain_summary(workspace),
        "missionCountThisUnit": mission_count,
        "doctrineHints": doctrine or load_doctrine_hints(workspace),
        "honesty": {
            "barDensifyBanned": True,
            "fairRoomOnly": True,
            "nObsWall": N_OBS_WALL,
            "godBrainMerge": False,
            "humanSealBotClearForbidden": True,
        },
    }
    if digest:
        residual["swarmDigest"] = digest
    return residual


def residual_write_paths(workspace: Path) -> Dict[str, Path]:
    return {
        "operator": workspace / "outbox" / "hive_bar_residual.latest.json",
        "hive": Path(r"C:\Users\Luke Spooner\ws-win\yurt-sync\commons\vitals\bar_proxy_residual.latest.json"),
        "vitals": workspace / "outbox" / "playtest_infra_vitals.latest.json",
    }


def map_residual_to_project_posts(residual: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Map residual signals → project-membrane style posts (η-tiered, dark-safe).

    Returns a list of dicts: {project, kind, polarity, note, eta_hint}
    polarity is +1 / -1 for warm/cold health-momentum language.
    Does not require umweltd; callers may no-op when dark.
    """
    posts: List[Dict[str, Any]] = []
    by = residual.get("byStyle") or {}
    simple = by.get("simple") or {}
    barb = by.get("barbarian") or {}
    simple_win = float(simple.get("meanWinRate") or 0.0)
    simple_fun = float(simple.get("meanFun") or 0.0)
    barb_win = float(barb.get("meanWinRate") or 0.0)
    brain = residual.get("brain") or {}
    ul_n = int(brain.get("ulUpdateCount") or 0)

    # unit ran at all
    posts.append(
        {
            "project": "bar",
            "kind": "referee",
            "polarity": +1.0,
            "note": f"residual unit ok ran_on={residual.get('ran_on')} ul={ul_n}",
            "eta_hint": 0.92,
            "binding_hint": "bar_referee",
        }
    )
    if simple_win >= 0.95 and simple_fun < 0.45:
        posts.append(
            {
                "project": "bar",
                "kind": "wall",
                "polarity": -1.0,
                "note": f"simple saturated soft fun simpleWin={simple_win} fun={simple_fun}",
                "eta_hint": 0.40,
                "binding_hint": "bar_wall",
            }
        )
    if barb_win < simple_win:
        posts.append(
            {
                "project": "bar",
                "kind": "claim",
                "polarity": +1.0,
                "note": "barb harder than simple (expected proxy pressure)",
                "eta_hint": 0.25,
                "binding_hint": "bar_momentum",
            }
        )
    if ul_n > 0:
        posts.append(
            {
                "project": "bar",
                "kind": "claim",
                "polarity": +1.0,
                "note": f"UL updates present count={ul_n}",
                "eta_hint": 0.25,
                "binding_hint": "bar_momentum",
            }
        )
    return posts


def try_umwelt_post(residual: Dict[str, Any]) -> Dict[str, Any]:
    """Best-effort observe into umweltd / project-membrane. Never raises out.

    When :7073 is down, returns umweltd_dark=True — farm unit must still succeed.
    """
    import os
    import urllib.error
    import urllib.request

    posts = map_residual_to_project_posts(residual)
    base = (os.environ.get("UMWELTD_URL") or "http://127.0.0.1:7073").rstrip("/")
    key = (os.environ.get("UMWELTD_API_KEY") or "").strip()
    world = os.environ.get("PROJECT_WORLD", "project-membrane")
    attempted = 0
    appended = 0
    errors: List[str] = []
    dark = False

    # cheap liveness probe
    try:
        req = urllib.request.Request(f"{base}/docs", method="GET")
        with urllib.request.urlopen(req, timeout=1.5) as resp:
            if resp.status >= 400:
                dark = True
    except Exception:
        dark = True

    if dark:
        return {
            "umweltd_dark": True,
            "attempted": 0,
            "appended": 0,
            "posts_planned": posts,
            "errors": ["umweltd_unreachable"],
            "note": "file residual remains authority; field post deferred",
        }

    headers = {"Content-Type": "application/json"}
    if key:
        headers["X-API-Key"] = key

    for p in posts:
        attempted += 1
        # Prefer project-membrane post.py shape if present; else HTTP event best-effort
        try:
            # Lightweight: try ingest via common umweltd path (may 404 — then record)
            payload = {
                "world": world,
                "sensor": p.get("binding_hint") or f"{p['project']}_{p['kind']}",
                "value": float(p["polarity"]),
                "meta": json.dumps(
                    {"note": p.get("note"), "source": "hive_bar_residual_v1", "eta_hint": p.get("eta_hint")},
                    ensure_ascii=False,
                ),
            }
            data = json.dumps(payload).encode("utf-8")
            for path in (
                f"/worlds/{world}/ingest",
                f"/v1/worlds/{world}/ingest",
                "/ingest",
            ):
                try:
                    req = urllib.request.Request(
                        f"{base}{path}", data=data, method="POST", headers=headers
                    )
                    with urllib.request.urlopen(req, timeout=3.0) as resp:
                        raw = resp.read()
                        if resp.status < 300:
                            appended += 1
                            break
                except urllib.error.HTTPError as e:
                    if e.code == 404:
                        continue
                    errors.append(f"{path}:HTTP{e.code}")
                    break
                except Exception as e:
                    errors.append(f"{path}:{type(e).__name__}")
                    break
        except Exception as e:
            errors.append(f"{type(e).__name__}:{e}")

    return {
        "umweltd_dark": False,
        "attempted": attempted,
        "appended": appended,
        "posts_planned": posts,
        "errors": errors[:8],
        "world": world,
        "base": base,
    }


def write_residual(
    residual: Dict[str, Any],
    workspace: Path,
    *,
    also_hive: bool = True,
    umwelt_post: bool = True,
) -> Dict[str, Any]:
    paths = residual_write_paths(workspace)
    written: List[str] = []
    skipped: List[str] = []

    # promote residual with umweltPost before first write
    if umwelt_post and "umweltPost" not in residual:
        try:
            residual = dict(residual)
            residual["umweltPost"] = try_umwelt_post(residual)
            honesty = dict(residual.get("honesty") or {})
            honesty["umweltd_dark"] = bool((residual["umweltPost"] or {}).get("umweltd_dark"))
            residual["honesty"] = honesty
        except Exception as e:
            residual = dict(residual)
            residual["umweltPost"] = {
                "umweltd_dark": True,
                "error": f"{type(e).__name__}:{e}",
                "attempted": 0,
                "appended": 0,
            }

    op = paths["operator"]
    op.parent.mkdir(parents=True, exist_ok=True)
    op.write_text(json.dumps(residual, indent=2, ensure_ascii=False), encoding="utf-8")
    written.append(str(op))

    if also_hive:
        hive = paths["hive"]
        try:
            hive.parent.mkdir(parents=True, exist_ok=True)
            hive.write_text(json.dumps(residual, indent=2, ensure_ascii=False), encoding="utf-8")
            written.append(str(hive))
        except Exception as e:
            skipped.append(f"hive:{e}")

    # extend playtest vitals without wiping kernel fields
    vitals_path = paths["vitals"]
    vitals: Dict[str, Any] = {}
    if vitals_path.is_file():
        try:
            vitals = json.loads(vitals_path.read_text(encoding="utf-8"))
        except Exception:
            vitals = {}
    vitals["at"] = residual["at"]
    vitals["proxy_residual_schema"] = SCHEMA
    by = residual.get("byStyle") or {}
    if "simple" in by:
        vitals["proxy_simple_meanWinRate"] = by["simple"].get("meanWinRate")
        vitals["proxy_simple_meanFun"] = by["simple"].get("meanFun")
    if "barbarian" in by:
        vitals["proxy_barb_meanWinRate"] = by["barbarian"].get("meanWinRate")
        vitals["proxy_barb_meanFun"] = by["barbarian"].get("meanFun")
    h2h = residual.get("headToHead") or {}
    if h2h:
        vitals["proxy_h2h_winRateDelta"] = h2h.get("winRateDelta_barb_minus_simple")
    brain = residual.get("brain") or {}
    vitals["proxy_brain_samples"] = brain.get("samples")
    vitals["proxy_ul_updateCount"] = brain.get("ulUpdateCount")
    vitals["proxy_ul_meanSigma"] = brain.get("ulMeanSigma")
    vitals["barDensifyBanned"] = True
    vitals["player_proxy"] = True
    vitals["proxy_ran_on"] = residual.get("ran_on")
    vitals["proxy_kind"] = residual.get("kind") or "player_proxy"
    vitals_path.parent.mkdir(parents=True, exist_ok=True)
    vitals_path.write_text(json.dumps(vitals, indent=2, ensure_ascii=False), encoding="utf-8")
    written.append(str(vitals_path))

    return {"written": written, "skipped": skipped, "residual": residual}


def build_and_write_from_proxy_file(
    proxy_path: Path,
    *,
    workspace: Optional[Path] = None,
    also_hive: bool = True,
) -> Dict[str, Any]:
    proxy_path = proxy_path.resolve()
    ws = workspace or _workspace_from_arg(proxy_path)
    report = json.loads(proxy_path.read_text(encoding="utf-8"))
    residual = build_residual(report, workspace=ws)
    return write_residual(residual, ws, also_hive=also_hive)


def self_test(workspace: Path) -> int:
    fixture = {
        "schemaVersion": "verdance-proxy-campaign/1.0",
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "sorties": 2,
        "seeds": 1,
        "difficulty": 1.2,
        "durationTicks": 24,
        "homeMap": "the_rock_jungle",
        "byStyle": {
            "simple": {
                "runs": 1,
                "meanWinRate": 0.8,
                "meanFun": 0.7,
                "meanTnb": 2.0,
                "meanClashEvents": 1.0,
                "barEnemy": "simple",
            },
            "barbarian": {
                "runs": 1,
                "meanWinRate": 0.5,
                "meanFun": 0.65,
                "meanTnb": 1.0,
                "meanClashEvents": 2.0,
                "barEnemy": "barbarian_aggressive",
            },
        },
        "headToHead": {"winRateDelta_barb_minus_simple": -0.3},
    }
    residual = build_residual(
        fixture, workspace=workspace, source="self_test", ran_on="wargen"
    )
    assert residual["schema"] == SCHEMA
    assert residual["honesty"]["barDensifyBanned"] is True
    assert residual["honesty"]["nObsWall"] == N_OBS_WALL
    assert residual["honesty"]["godBrainMerge"] is False
    assert residual["kind"] == "player_proxy"
    assert residual["ran_on"] == "wargen"
    assert "simple" in residual["byStyle"]
    assert residual["byStyle"]["barbarian"]["meanWinRate"] == 0.5
    posts = map_residual_to_project_posts(residual)
    assert posts and posts[0]["project"] == "bar"
    # dry mapping never requires umweltd
    dry = try_umwelt_post(residual)
    assert "umweltd_dark" in dry
    assert "posts_planned" in dry
    # write to temp-like outbox only (still real workspace outbox is ok for self-test)
    result = write_residual(residual, workspace, also_hive=True, umwelt_post=True)
    assert result["written"], result
    written_res = result.get("residual") or residual
    assert "umweltPost" in (result.get("residual") or {})
    # re-read operator face
    op = residual_write_paths(workspace)["operator"]
    on_disk = json.loads(op.read_text(encoding="utf-8"))
    assert "umweltPost" in on_disk
    print("hive_bar_residual_v1 self_test OK")
    print(f"  written={len(result['written'])} skipped={result.get('skipped')} umweltPost={on_disk.get('umweltPost', {}).get('umweltd_dark')}")
    return 0


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="Hive-BAR residual hose")
    ap.add_argument("--workspace", default=".")
    ap.add_argument("--from", dest="from_path", default="", help="proxy_campaign.latest.json")
    ap.add_argument("--write", action="store_true")
    ap.add_argument("--no-hive", action="store_true", help="skip yurt-sync vitals write")
    ap.add_argument("--self-test", action="store_true")
    args = ap.parse_args(list(argv) if argv is not None else None)

    ws = Path(args.workspace).resolve()
    if args.self_test:
        return self_test(ws)

    if not args.from_path:
        # default latest
        args.from_path = str(ws / "outbox" / "proxy_campaign.latest.json")
    src = Path(args.from_path)
    if not src.is_file():
        print(f"missing proxy report: {src}", file=sys.stderr)
        return 2

    report = json.loads(src.read_text(encoding="utf-8"))
    residual = build_residual(report, workspace=ws)
    if args.write:
        result = write_residual(residual, ws, also_hive=not args.no_hive)
        for w in result["written"]:
            print(f"wrote {w}")
        for s in result.get("skipped") or []:
            print(f"skip {s}")
    else:
        print(json.dumps(residual, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
