#!/usr/bin/env python3
"""Human-player telemetry → bar_brain learning tapes.

Dev launch dumps dense samples (VA_DEV_SAMPLE / dense VA_TELEMETRY) from the
BAR infolog. This module:

  1. Parses all samples from an infolog or session JSONL
  2. Infers proxy-style actions from resource/value/zone deltas
  3. Builds a synthetic campaign-report shaped for ``ingest_campaign_report``
  4. Trains bar_brain with **higher weight** than proxy sims (human gold)

Usage:
  python -m quantum_bar_ai.player_telemetry --harvest
  python -m quantum_bar_ai.player_telemetry --harvest --train
  python -m quantum_bar_ai.player_telemetry --from-json path/to/session.json
"""
from __future__ import annotations

import argparse
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .bar_brain import ingest_campaign_report, load_weights, save_weights
from .suite import _workspace_root

SCHEMA = "verdance-player-telemetry/0.1"
HUMAN_WIN_SCALE = 2.4   # human win samples count heavier than proxy
HUMAN_LOSS_SCALE = 1.4  # still learn from losses, a bit more than proxy 0.55


def session_dir(ws: Path | None = None) -> Path:
    return (ws or _workspace_root()) / "headless_runs" / "player_sessions"


def latest_session_path(ws: Path | None = None) -> Path:
    return (ws or _workspace_root()) / "outbox" / "player_telemetry.latest.json"


def _balanced_json_after(text: str, marker: str) -> list[str]:
    """Extract complete JSON objects after each marker occurrence."""
    out: list[str] = []
    start = 0
    while True:
        idx = text.find(marker, start)
        if idx < 0:
            break
        brace = text.find("{", idx + len(marker))
        if brace < 0:
            break
        depth = 0
        in_str = False
        esc = False
        end = -1
        for i in range(brace, len(text)):
            ch = text[i]
            if in_str:
                if esc:
                    esc = False
                elif ch == "\\":
                    esc = True
                elif ch == '"':
                    in_str = False
                continue
            if ch == '"':
                in_str = True
            elif ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    end = i
                    break
        if end < 0:
            break
        out.append(text[brace : end + 1])
        start = end + 1
    return out


def parse_infolog_samples(infolog_text: str) -> list[dict[str, Any]]:
    """Pull VA_DEV_SAMPLE_JSON and VA_TELEMETRY_JSON_COMPACT blobs."""
    samples: list[dict[str, Any]] = []
    for marker in (
        "VA_DEV_SAMPLE_JSON ",
        "VA_TELEMETRY_JSON_COMPACT ",
        "VA_DEV_SAMPLE ",
    ):
        for blob in _balanced_json_after(infolog_text, marker):
            try:
                samples.append(json.loads(blob))
            except json.JSONDecodeError:
                continue
    # Chunked telemetry (fallback)
    for blob in _chunked_json(infolog_text, "VA_TELEMETRY_JSON"):
        try:
            samples.append(json.loads(blob))
        except json.JSONDecodeError:
            continue
    # de-dupe by frame+exportId
    seen: set[str] = set()
    unique: list[dict[str, Any]] = []
    for s in samples:
        key = f"{s.get('frame')}:{s.get('exportId')}:{s.get('seconds')}"
        if key in seen:
            continue
        seen.add(key)
        unique.append(s)
    unique.sort(key=lambda s: (float(s.get("seconds") or 0), int(s.get("frame") or 0)))
    return unique


def _chunked_json(text: str, prefix: str) -> list[str]:
    lines = text.splitlines()
    blocks: list[str] = []
    cur: list[str] | None = None
    begin = re.compile(rf"{re.escape(prefix)}_BEGIN")
    chunk = re.compile(rf"{re.escape(prefix)}_CHUNK\s+\d+/\d+\s+(.*)$")
    end = re.compile(rf"{re.escape(prefix)}_END")
    for line in lines:
        if begin.search(line):
            cur = []
            continue
        m = chunk.search(line)
        if m is not None and cur is not None:
            cur.append(m.group(1))
            continue
        if end.search(line) and cur is not None:
            blocks.append("".join(cur))
            cur = None
    return blocks


def parse_result_from_infolog(infolog_text: str) -> dict[str, Any] | None:
    for marker in ("VA_RESULT_JSON_COMPACT ", "VA_RESULT_JSON "):
        blobs = _balanced_json_after(infolog_text, marker)
        if blobs:
            try:
                return json.loads(blobs[-1])
            except json.JSONDecodeError:
                continue
    for blob in _chunked_json(infolog_text, "VA_RESULT_JSON"):
        try:
            return json.loads(blob)
        except json.JSONDecodeError:
            continue
    return None


def _balance(sample: dict[str, Any]) -> dict[str, Any]:
    b = sample.get("balance") or {}
    if isinstance(b, dict):
        return b
    return {}


def _eco_feel(metal_income: float, energy_income: float) -> str:
    m = float(metal_income or 0)
    e = float(energy_income or 0)
    score = m * 2.0 + e * 0.05
    if score < 8:
        return "dry"
    if score < 20:
        return "thin"
    if score < 45:
        return "steady"
    return "fat"


def _phase(seconds: float, value_ratio: float, player_units: int) -> str:
    if seconds < 60:
        return "APPROACH"
    if value_ratio >= 1.2:
        return "PUSH"
    if value_ratio <= 0.55:
        return "DEFEND"
    if player_units <= 3:
        return "SURVIVE"
    return "ENGAGE"


def _contact(value_ratio: float, enemy_units: int) -> str:
    if enemy_units <= 0:
        return "none"
    if value_ratio >= 1.25:
        return "light"
    if value_ratio <= 0.55:
        return "heavy"
    return "medium"


def _objective_bar(verdict: str, progress_hint: float) -> str:
    if verdict in ("player_clear", "victory"):
        return "full"
    if progress_hint >= 0.7:
        return "high"
    if progress_hint >= 0.4:
        return "mid"
    if progress_hint >= 0.15:
        return "low"
    return "empty"


def infer_action(prev: dict[str, Any] | None, cur: dict[str, Any]) -> str:
    """Map telemetry deltas → fair-sim action vocabulary."""
    cb = _balance(cur)
    pb = _balance(prev) if prev else {}
    p_val = float(cb.get("playerValue") or 0)
    e_val = float(cb.get("enemyValue") or 0)
    prev_p = float(pb.get("playerValue") or p_val)
    prev_e = float(pb.get("enemyValue") or e_val)
    ratio = float(cb.get("valueRatio") or (p_val / e_val if e_val > 0 else p_val))
    p_units = int(cb.get("playerUnitCount") or 0)
    e_units = int(cb.get("enemyUnitCount") or 0)
    cmds = cur.get("playerCommands") or {}
    build_cmds = int(cmds.get("build") or 0) + int(cmds.get("reclaim") or 0)
    fight_cmds = int(cmds.get("fight") or 0) + int(cmds.get("attack") or 0) + int(cmds.get("patrol") or 0)
    move_cmds = int(cmds.get("move") or 0)
    dev = cur.get("dev") or {}
    metal_inc = float(dev.get("metalIncome") or 0)
    energy_inc = float(dev.get("energyIncome") or 0)

    # building dominates
    if build_cmds >= 2 and (metal_inc < 12 or energy_inc < 80):
        if energy_inc < metal_inc * 8:
            return "BUILD_ENERGY"
        return "BUILD_MEX"
    if build_cmds >= 2:
        return "BUILD_CON"

    d_p = p_val - prev_p
    d_e = prev_e - e_val  # enemy lost value = good

    if p_units <= 0:
        return "FALLBACK"
    if ratio <= 0.5 and e_units > p_units:
        return "HOLD_AND_HEAL" if d_p >= -50 else "FALLBACK"
    if fight_cmds >= 2 or (d_e > 80 and ratio >= 0.9):
        return "PUSH_OBJECTIVE" if ratio >= 0.85 else "FLANK"
    if move_cmds >= 3 and fight_cmds == 0:
        return "PROBE" if ratio < 1.1 else "EXPAND_FRONT"
    if d_p > 100 and d_e < 30:
        return "EXPAND_FRONT"
    if ratio >= 1.3 and e_units > 0:
        return "PUSH_OBJECTIVE"
    if ratio < 0.75:
        return "RALLY"
    return "HOLD_AND_HEAL" if fight_cmds == 0 else "PUSH_OBJECTIVE"


def samples_to_tape(
    samples: list[dict[str, Any]],
    *,
    result: dict[str, Any] | None = None,
    mission_card: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build one fair-mission-result shaped dict from dense samples."""
    tape: list[dict[str, Any]] = []
    actions: list[str] = []
    prev = None
    for i, s in enumerate(samples):
        action = infer_action(prev, s)
        actions.append(action)
        bal = _balance(s)
        dev = s.get("dev") or {}
        seconds = float(s.get("seconds") or 0)
        ratio = float(bal.get("valueRatio") or 0)
        eco = _eco_feel(float(dev.get("metalIncome") or 0), float(dev.get("energyIncome") or 0))
        verdict_hint = str(bal.get("verdict") or "active")
        # soft progress from value ratio + time
        progress = min(1.0, max(0.0, 0.35 * min(1.5, ratio) + 0.02 * (seconds / 60.0)))
        if verdict_hint in ("player_clear",):
            progress = max(progress, 0.9)
        hud = {
            "phase": _phase(seconds, ratio, int(bal.get("playerUnitCount") or 0)),
            "contact": _contact(ratio, int(bal.get("enemyUnitCount") or 0)),
            "objective_bar": _objective_bar(verdict_hint, progress),
            "eco_feel": eco,
            "width_band": (mission_card or {}).get("width_band") or "open",
        }
        tape.append(
            {
                "tick": i,
                "frame": s.get("frame"),
                "seconds": seconds,
                "action": action,
                "hud": hud,
                "backend": "human_player",
                "_truth": {
                    "eco": {"dry": 0.15, "thin": 0.35, "steady": 0.55, "fat": 0.8}.get(eco, 0.4),
                    "player_value": bal.get("playerValue"),
                    "enemy_value": bal.get("enemyValue"),
                    "value_ratio": ratio,
                    "source": "player_telemetry",
                },
                "player_commands": s.get("playerCommands"),
            }
        )
        prev = s

    status = "unknown"
    won = False
    if result:
        term = result.get("terminal") or result.get("status") or result.get("resultStatus")
        if isinstance(term, dict):
            status = str(term.get("status") or "unknown")
        else:
            status = str(term or result.get("status") or "unknown")
        won = status.lower() in ("victory", "win", "extracted", "objective_complete", "player_clear")
    elif samples:
        last_v = str(_balance(samples[-1]).get("verdict") or "")
        if last_v == "player_clear":
            won = True
            status = "victory"
        elif last_v == "player_dead":
            won = False
            status = "defeat"

    card = mission_card or {
        "id": (samples[0].get("missionId") if samples else None) or "human_play",
        "kind": "seize_lane",
        "title": "Human play session",
        "width_band": "open",
    }
    progress = 0.0
    if tape:
        progress = float(tape[-1].get("_truth", {}).get("value_ratio") or 0)
        progress = min(1.0, max(0.0, progress / 1.4 if not won else max(0.85, progress)))

    return {
        "mission_id": card.get("id") or "human_play",
        "verdict": "extracted" if won else status,
        "won": won,
        "ticks": len(tape),
        "progress": round(progress, 4),
        "heroes_alive_frac": 1.0 if won else 0.6,
        "actions": actions,
        "tape": tape,
        "player_card": card,
        "difficulty_label": "human",
        "notes": "human_player_telemetry",
        "source": "player_telemetry",
        "sample_count": len(samples),
    }


def build_human_report(
    samples: list[dict[str, Any]],
    *,
    result: dict[str, Any] | None = None,
    mission_card: dict[str, Any] | None = None,
) -> dict[str, Any]:
    mission = samples_to_tape(samples, result=result, mission_card=mission_card)
    # Human samples get heavier training weight via duplicate scale in ingest —
    # we also annotate for ingest_human_report.
    return {
        "schemaVersion": SCHEMA,
        "label": "human_player",
        "source": "dev_launch",
        "cleared": bool(mission.get("won")),
        "hard_wins": 1 if mission.get("won") else 0,
        "missions": 1,
        "results": [mission],
        "human": True,
        "human_weight": HUMAN_WIN_SCALE if mission.get("won") else HUMAN_LOSS_SCALE,
    }


def ingest_human_report(report: dict[str, Any], weights: Any | None = None) -> Any:
    """Train bar_brain from human report with elevated sample weight."""
    from .bar_brain import BarBrainWeights

    w = weights or load_weights()
    # Amplify by replaying tape with scaled wins/losses via multiple ingests
    weight = float(report.get("human_weight") or HUMAN_WIN_SCALE)
    # First pass: normal ingest
    w = ingest_campaign_report(report, w)
    # Extra passes for human gold (ceil weight - 1)
    extra = max(0, int(round(weight)) - 1)
    for _ in range(extra):
        w = ingest_campaign_report(report, w)
    if isinstance(w, BarBrainWeights):
        w.version = w.version or "0.3"
    return w


def harvest_infolog(
    infolog: Path | None = None,
    *,
    ws: Path | None = None,
    train: bool = False,
) -> dict[str, Any]:
    ws = ws or _workspace_root()
    if infolog is None:
        # common BAR locations
        candidates = [
            ws / "logs" / "infolog.txt",
            Path.home() / "Documents" / "My Games" / "Beyond All Reason" / "infolog.txt",
            Path(os.environ.get("LOCALAPPDATA", ""))
            / "Programs"
            / "Beyond-All-Reason"
            / "data"
            / "infolog.txt",
        ]
        # also read from verdance_config
        cfg = ws / "verdance_config.json"
        if cfg.is_file():
            try:
                data = json.loads(cfg.read_text(encoding="utf-8-sig"))
                if data.get("infolog"):
                    candidates.insert(0, Path(data["infolog"]))
            except Exception:
                pass
        infolog = next((p for p in candidates if p and Path(p).is_file()), None)
        if infolog is None:
            return {"ok": False, "reason": "infolog not found", "tried": [str(c) for c in candidates]}
    text = Path(infolog).read_text(encoding="utf-8", errors="replace")
    samples = parse_infolog_samples(text)
    result = parse_result_from_infolog(text)
    if not samples and not result:
        return {"ok": False, "reason": "no telemetry samples in infolog", "infolog": str(infolog)}

    report = build_human_report(samples, result=result)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    out = session_dir(ws) / f"player_{stamp}"
    out.mkdir(parents=True, exist_ok=True)
    (out / "samples.json").write_text(json.dumps(samples, indent=2), encoding="utf-8")
    (out / "report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    if result:
        (out / "result.json").write_text(json.dumps(result, indent=2), encoding="utf-8")

    train_info = None
    if train and report.get("results"):
        w = ingest_human_report(report, load_weights())
        path = save_weights(w)
        train_info = {
            "weights_path": str(path),
            "samples": w.samples,
            "wins": w.wins,
            "losses": w.losses,
            "human_weight": report.get("human_weight"),
        }
        (out / "bar_brain_train.json").write_text(
            json.dumps(train_info, indent=2), encoding="utf-8"
        )

    summary = {
        "ok": True,
        "schemaVersion": SCHEMA,
        "infolog": str(infolog),
        "sample_count": len(samples),
        "won": report.get("cleared"),
        "actions_hist": _hist((report["results"][0].get("actions") or []) if report.get("results") else []),
        "session_dir": str(out),
        "train": train_info,
    }
    latest_session_path(ws).write_text(json.dumps(summary, indent=2), encoding="utf-8")
    (out / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    return summary


def _hist(actions: list[str]) -> dict[str, int]:
    h: dict[str, int] = {}
    for a in actions:
        h[a] = h.get(a, 0) + 1
    return h


def main() -> int:
    ap = argparse.ArgumentParser(description="Harvest human BAR telemetry → bar_brain")
    ap.add_argument("--harvest", action="store_true", help="Parse infolog + write session")
    ap.add_argument("--train", action="store_true", help="Train bar_brain from harvest (default with --harvest)")
    ap.add_argument("--no-train", action="store_true", help="Harvest only, do not train")
    ap.add_argument("--infolog", type=str, default="", help="Path to BAR infolog.txt")
    ap.add_argument("--from-json", type=str, default="", help="Load samples JSON directly")
    args = ap.parse_args()

    if args.from_json:
        samples = json.loads(Path(args.from_json).read_text(encoding="utf-8-sig"))
        if isinstance(samples, dict) and "samples" in samples:
            samples = samples["samples"]
        report = build_human_report(list(samples))
        if args.train and not args.no_train:
            w = ingest_human_report(report, load_weights())
            path = save_weights(w)
            print(json.dumps({"ok": True, "samples": w.samples, "weights": str(path)}, indent=2))
        else:
            print(json.dumps(report, indent=2)[:3000])
        return 0

    if args.harvest or args.train:
        do_train = (args.train or args.harvest) and not args.no_train
        summary = harvest_infolog(
            Path(args.infolog) if args.infolog else None,
            train=do_train,
        )
        print(json.dumps(summary, indent=2))
        return 0 if summary.get("ok") else 1

    ap.print_help()
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
