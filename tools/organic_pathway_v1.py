#!/usr/bin/env python3
"""organic_pathway_v1 — free-CPU training pathway helpers (bots only).

Cadences: adaptive difficulty, curriculum slots, mission learn tape,
morning scorecard. No densify. No god-brain. Luke does not run this.
"""
from __future__ import annotations

import argparse
import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

TOOLS = Path(__file__).resolve().parent
WS_DEFAULT = TOOLS.parent

DIFF_PATH_REL = Path("app") / "brain" / "organic_difficulty.json"
CURR_PATH_REL = Path("app") / "brain" / "organic_curriculum_state.json"
MISSION_TAPE_REL = Path("app") / "brain" / "mission_learn_tape.jsonl"
MORNING_REL = Path("outbox") / "training_pathway_morning.json"

HIVE_VITALS = Path(r"C:\Users\Luke Spooner\ws-win\yurt-sync\commons\vitals")

DIFF_FLOOR = 1.0
DIFF_CAP = 2.2
DIFF_DEFAULT = 1.4
BUMP = 0.10
EASE = 0.05
SIMPLE_SATURATED = 0.95
SIMPLE_STRUGGLING = 0.35


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _workspace(ws: Optional[Path] = None) -> Path:
    if ws is not None:
        return Path(ws)
    env = (os.environ.get("BAR_WORKSPACE") or os.environ.get("VERDANCE_WORKSPACE") or "").strip()
    if env:
        p = Path(env)
        if p.is_dir():
            return p.resolve()
    return WS_DEFAULT.resolve()


def load_json(path: Path, default: Any = None) -> Any:
    if not path.is_file():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default


def write_json(path: Path, data: Any) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    return path


# ---------------------------------------------------------------------------
# Adaptive difficulty
# ---------------------------------------------------------------------------

def load_difficulty(workspace: Optional[Path] = None) -> float:
    ws = _workspace(workspace)
    data = load_json(ws / DIFF_PATH_REL, {}) or {}
    try:
        d = float(data.get("difficulty") or DIFF_DEFAULT)
    except (TypeError, ValueError):
        d = DIFF_DEFAULT
    return max(DIFF_FLOOR, min(DIFF_CAP, d))


def save_difficulty(
    difficulty: float,
    *,
    workspace: Optional[Path] = None,
    reason: str = "",
    signals: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    ws = _workspace(workspace)
    d = max(DIFF_FLOOR, min(DIFF_CAP, float(difficulty)))
    face = {
        "schema": "organic-difficulty/1.0",
        "at": _now(),
        "difficulty": round(d, 3),
        "reason": reason or "set",
        "signals": signals or {},
        "floor": DIFF_FLOOR,
        "cap": DIFF_CAP,
    }
    write_json(ws / DIFF_PATH_REL, face)
    return face


def adapt_difficulty_from_proxy(
    proxy_report: Dict[str, Any],
    *,
    workspace: Optional[Path] = None,
) -> Dict[str, Any]:
    """Bump/ease organic difficulty from latest proxy A/B (simple win rate)."""
    ws = _workspace(workspace)
    cur = load_difficulty(ws)
    by = proxy_report.get("byStyle") or {}
    simple = by.get("simple") or {}
    barb = by.get("barbarian") or {}
    try:
        sw = float(simple.get("meanWinRate") if simple.get("meanWinRate") is not None else -1)
    except (TypeError, ValueError):
        sw = -1.0
    try:
        bw = float(barb.get("meanWinRate") if barb.get("meanWinRate") is not None else -1)
    except (TypeError, ValueError):
        bw = -1.0

    new = cur
    reason = "hold"
    if sw >= SIMPLE_SATURATED:
        new = min(DIFF_CAP, cur + BUMP)
        reason = "simple_saturated_bump"
    elif 0 <= sw <= SIMPLE_STRUGGLING:
        new = max(DIFF_FLOOR, cur - EASE)
        reason = "simple_struggling_ease"

    face = save_difficulty(
        new,
        workspace=ws,
        reason=reason,
        signals={
            "prev": cur,
            "simpleWin": sw if sw >= 0 else None,
            "barbWin": bw if bw >= 0 else None,
        },
    )
    face["changed"] = abs(new - cur) > 1e-9
    return face


# ---------------------------------------------------------------------------
# Curriculum
# ---------------------------------------------------------------------------

# slot -> unit params
_SLOTS = {
    "C0_smoke": {"sorties": 2, "ticks": 28, "enemy": "both", "note": "health smoke"},
    "C1_ladder": {"sorties": 2, "ticks": 36, "enemy": "both", "note": "A/B ladder"},
    "C2_eco": {"sorties": 3, "ticks": 48, "enemy": "both", "note": "eco stress longer ticks"},
    "C3_width": {"sorties": 2, "ticks": 40, "enemy": "both", "note": "width stress"},
    "C4_manifold_snack": {
        "sorties": 0,
        "ticks": 0,
        "enemy": "both",
        "note": "manifold_gym snack (optional)",
        "manifold_gens": 3,
    },
}


def load_curriculum(workspace: Optional[Path] = None) -> Dict[str, Any]:
    ws = _workspace(workspace)
    data = load_json(ws / CURR_PATH_REL, {}) or {}
    if not isinstance(data, dict):
        data = {}
    data.setdefault("schema", "organic-curriculum/1.0")
    data.setdefault("tick_index", 0)
    data.setdefault("armed", False)
    data.setdefault("last_slot", None)
    return data


def save_curriculum(state: Dict[str, Any], workspace: Optional[Path] = None) -> Path:
    ws = _workspace(workspace)
    state = dict(state)
    state["at"] = _now()
    state["schema"] = "organic-curriculum/1.0"
    return write_json(ws / CURR_PATH_REL, state)


def curriculum_next(
    *,
    workspace: Optional[Path] = None,
    manifold_gym_path: Optional[Path] = None,
    force_slot: Optional[str] = None,
) -> Dict[str, Any]:
    """Pick next curriculum slot for an organic tick."""
    ws = _workspace(workspace)
    st = load_curriculum(ws)
    idx = int(st.get("tick_index") or 0)

    if force_slot and force_slot in _SLOTS:
        slot = force_slot
    elif not st.get("armed"):
        slot = "C0_smoke"
        st["armed"] = True
    else:
        # rotation: C1 most often, C2 every 3, C3 every 4, C4 if gym stale
        slot = "C1_ladder"
        if idx > 0 and idx % 3 == 0:
            slot = "C2_eco"
        if idx > 0 and idx % 4 == 0:
            slot = "C3_width"
        # manifold snack if gym face older than 12h and CPU path allows (caller decides run)
        gym = manifold_gym_path or (ws / "outbox" / "manifold_gym.latest.json")
        if gym.is_file():
            age_h = (time.time() - gym.stat().st_mtime) / 3600.0
            if age_h >= 12.0 and idx > 0 and idx % 6 == 0:
                slot = "C4_manifold_snack"
        else:
            if idx > 0 and idx % 8 == 0:
                slot = "C4_manifold_snack"

    params = dict(_SLOTS[slot])
    difficulty = load_difficulty(ws)
    # width stress: slight difficulty nudge so open scars meet harder room
    if slot == "C3_width":
        difficulty = min(DIFF_CAP, difficulty + 0.05)

    st["tick_index"] = idx + 1
    st["last_slot"] = slot
    st["last_difficulty"] = difficulty
    save_curriculum(st, ws)

    return {
        "schema": "organic-curriculum-pick/1.0",
        "at": _now(),
        "slot": slot,
        "difficulty": round(difficulty, 3),
        "sorties": int(params.get("sorties") or 2),
        "ticks": int(params.get("ticks") or 36),
        "enemy": str(params.get("enemy") or "both"),
        "note": params.get("note"),
        "manifold_gens": params.get("manifold_gens"),
        "state": {"tick_index": st["tick_index"], "armed": st.get("armed")},
    }


# ---------------------------------------------------------------------------
# Mission learn tape
# ---------------------------------------------------------------------------

def append_mission_learn_rows(
    rows: List[Dict[str, Any]],
    *,
    workspace: Optional[Path] = None,
    also_hive: bool = True,
) -> Dict[str, Any]:
    """Append bar-mission-learn/1.0 rows to workspace + optional hive tape."""
    ws = _workspace(workspace)
    tape = ws / MISSION_TAPE_REL
    tape.parent.mkdir(parents=True, exist_ok=True)
    n = 0
    with tape.open("a", encoding="utf-8") as f:
        for row in rows:
            r = dict(row)
            r.setdefault("schema", "bar-mission-learn/1.0")
            r.setdefault("at", _now())
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
            n += 1

    hive_n = 0
    if also_hive:
        try:
            HIVE_VITALS.mkdir(parents=True, exist_ok=True)
            ht = HIVE_VITALS / "bar_mission_learn_tape.jsonl"
            with ht.open("a", encoding="utf-8") as f:
                for row in rows:
                    r = dict(row)
                    r.setdefault("schema", "bar-mission-learn/1.0")
                    r.setdefault("at", _now())
                    f.write(json.dumps(r, ensure_ascii=False) + "\n")
                    hive_n += 1
        except OSError:
            pass

    return {"ok": True, "appended": n, "hive_appended": hive_n, "path": str(tape)}


def mission_rows_from_train(
    train_info: Dict[str, Any],
    *,
    proxy_report: Optional[Dict[str, Any]] = None,
    ran_on: str = "unknown",
) -> List[Dict[str, Any]]:
    """Build mission learn rows from train_report_with_ul missionLogs + proxy meta."""
    logs = train_info.get("missionLogs") or []
    meta = proxy_report or {}
    difficulty = meta.get("difficulty")
    rows: List[Dict[str, Any]] = []
    for i, log in enumerate(logs):
        if not isinstance(log, dict):
            continue
        rows.append(
            {
                "schema": "bar-mission-learn/1.0",
                "at": _now(),
                "i": i,
                "won": bool(log.get("won")),
                "width_band": log.get("width_band"),
                "surprise": log.get("surprise"),
                "progress": log.get("progress"),
                "nTouched": log.get("nTouched"),
                "ul_deltas_sample": log.get("deltas") or {},
                "difficulty": difficulty,
                "ran_on": ran_on,
                "source": "train_report_with_ul",
                "ulFamily": "width_action+eco_action",
            }
        )
    return rows


# ---------------------------------------------------------------------------
# Morning pathway face
# ---------------------------------------------------------------------------

def write_morning_face(*, workspace: Optional[Path] = None) -> Dict[str, Any]:
    ws = _workspace(workspace)
    residual = load_json(ws / "outbox" / "hive_bar_residual.latest.json", {}) or {}
    fruit = load_json(ws / "outbox" / "campaign_fruit.latest.json", {}) or {}
    proxy = load_json(ws / "outbox" / "proxy_campaign.latest.json", {}) or {}
    diff = load_json(ws / DIFF_PATH_REL, {}) or {}
    curr = load_json(ws / CURR_PATH_REL, {}) or {}
    unit = load_json(ws / "outbox" / "bar_swarm_unit.latest.json", {}) or {}
    brain = residual.get("brain") or {}

    tape = ws / MISSION_TAPE_REL
    mission_lines = 0
    if tape.is_file():
        try:
            mission_lines = sum(1 for _ in tape.open("r", encoding="utf-8") if _.strip())
        except OSError:
            mission_lines = 0

    face = {
        "schema": "training-pathway-morning/1.0",
        "version": "0.9.0",
        "at": _now(),
        "primaryMission": "umwelt+cognifold skill (BAR is a gym)",
        "dualTrack": {
            "swarmIntelligence": "residual + soft doctrine + cognifold",
            "barCampaign": "fruit ideas + craft band + proxy A/B",
            "umweltSpine": "dual_farm lease + umweltPost + skill morning",
        },
        "brain": {
            "samples": brain.get("samples"),
            "wins": brain.get("wins"),
            "losses": brain.get("losses"),
            "ulFamily": brain.get("ulFamily"),
            "ulUpdateCount": brain.get("ulUpdateCount"),
            "ulMissions": brain.get("ulMissions"),
            "ulWidthUpdates": brain.get("ulWidthUpdates"),
            "ulEcoUpdates": brain.get("ulEcoUpdates"),
        },
        "organicDifficulty": diff.get("difficulty"),
        "curriculum": {
            "tick_index": curr.get("tick_index"),
            "last_slot": curr.get("last_slot"),
        },
        "missionLearnTapeLines": mission_lines,
        "fruitIdeaCount": len(fruit.get("ideas") or []),
        "lastUnit": {
            "ok": unit.get("ok"),
            "ran_on": unit.get("ran_on"),
            "at": unit.get("at"),
            "wall_s": unit.get("wall_s"),
        },
        "proxyHeadToHead": proxy.get("headToHead"),
        "law": [
            "human seal sacred",
            "no densify",
            "no god-brain",
            "learn every written unit",
            "fruit proposes; craft auto only in band",
            "umwelt primary; exclusive dual_farm slot",
        ],
        "read": [
            "outbox/hive_bar_residual.latest.json",
            "outbox/campaign_fruit.latest.json",
            "app/brain/bar_brain_ul_state.json",
            "app/brain/craft_recipe.json",
            "app/brain/organic_difficulty.json",
            "docs/UMWELT_GYM_PATHWAY.md",
            "hive commons/vitals/dual_farm_supervisor.json",
            "hive commons/vitals/umwelt_skill_morning.json",
        ],
    }
    write_json(ws / MORNING_REL, face)
    try:
        HIVE_VITALS.mkdir(parents=True, exist_ok=True)
        write_json(HIVE_VITALS / "training_pathway_morning.json", face)
    except OSError:
        pass
    return face


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="Organic training pathway helpers")
    ap.add_argument("--workspace", default=str(WS_DEFAULT))
    sub = ap.add_subparsers(dest="cmd", required=True)

    sub.add_parser("difficulty-show")
    sub.add_parser("curriculum-next")
    sub.add_parser("morning")
    ad = sub.add_parser("adapt-from-proxy")
    ad.add_argument("--from", dest="proxy_path", default="")

    args = ap.parse_args(argv)
    ws = Path(args.workspace).resolve()

    if args.cmd == "difficulty-show":
        print(json.dumps({"difficulty": load_difficulty(ws)}, indent=2))
        return 0
    if args.cmd == "curriculum-next":
        print(json.dumps(curriculum_next(workspace=ws), indent=2))
        return 0
    if args.cmd == "morning":
        print(json.dumps(write_morning_face(workspace=ws), indent=2))
        return 0
    if args.cmd == "adapt-from-proxy":
        path = Path(args.proxy_path) if args.proxy_path else ws / "outbox" / "proxy_campaign.latest.json"
        rep = load_json(path, {}) or {}
        print(json.dumps(adapt_difficulty_from_proxy(rep, workspace=ws), indent=2))
        return 0
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
