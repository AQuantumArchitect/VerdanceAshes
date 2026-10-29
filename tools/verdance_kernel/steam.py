"""Phase 3 — Steam cloud + achievements (stub / freeze).

Real Steamworks binds later (SteamworksPy / godot-steam / native plugin).
Until then we:
  - Mirror campaign_state into state/steam/cloud/ for future Cloud sync
  - Append achievement unlocks to state/steam/achievements.jsonl
  - Expose a read-only status for the shell
"""
from __future__ import annotations

import json
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any

from verdance.common import utc_now

from verdance_kernel.paths import state_path, steam_dir


# Catalog of achievement IDs the kernel may fire (Steam AppID TBD).
ACHIEVEMENT_CATALOG: dict[str, dict[str, str]] = {
    "FIRST_SORTIE": {
        "display": "First Scar",
        "desc": "Complete your first sortie on Verdance's Ashes.",
    },
    "CLEAN_EXTRACT": {
        "display": "Clean Boots",
        "desc": "Extract clean after taking the objective.",
    },
    "ARC_1_CLEAR": {
        "display": "First Scar Healed",
        "desc": "Clear the First Scar arc.",
    },
    "SAME_MAP_CHAIN": {
        "display": "Press the Line",
        "desc": "Continue into a second pocket without leaving the map.",
    },
    "BROKER_DEAL": {
        "display": "Coin and Ash",
        "desc": "Complete a broker purchase.",
    },
}


def ensure_layout(ws: Path) -> Path:
    root = steam_dir(ws)
    (root / "cloud").mkdir(parents=True, exist_ok=True)
    (root / "stats").mkdir(parents=True, exist_ok=True)
    return root


def cloud_mirror(ws: Path) -> dict[str, Any]:
    """Copy campaign_state into the cloud mirror folder."""
    root = ensure_layout(ws)
    src = state_path(ws)
    if not src.is_file():
        return {"ok": False, "reason": "no campaign_state"}
    dest = root / "cloud" / "campaign_state.json"
    shutil.copy2(src, dest)
    meta = {
        "schemaVersion": "verdance-steam-cloud-mirror/1.0",
        "at": utc_now(),
        "source": str(src),
        "dest": str(dest),
        "steamworks": False,
        "note": "Mirror only — wire FileWriteAsync when AppID is live.",
    }
    (root / "cloud" / "mirror_meta.json").write_text(
        json.dumps(meta, indent=2) + "\n", encoding="utf-8"
    )
    return {"ok": True, **meta}


def unlock_achievement(ws: Path, achievement_id: str, *, detail: str | None = None) -> dict[str, Any]:
    root = ensure_layout(ws)
    cat = ACHIEVEMENT_CATALOG.get(achievement_id, {})
    rec = {
        "at": utc_now(),
        "id": achievement_id,
        "display": cat.get("display") or achievement_id,
        "detail": detail,
        "steamworks": False,
    }
    log = root / "achievements.jsonl"
    with log.open("a", encoding="utf-8") as f:
        f.write(json.dumps(rec) + "\n")
    # Also maintain a set of unlocked ids
    unlocked_path = root / "unlocked.json"
    unlocked: list[str] = []
    if unlocked_path.is_file():
        try:
            unlocked = list(json.loads(unlocked_path.read_text(encoding="utf-8-sig")))
        except Exception:  # noqa: BLE001
            unlocked = []
    if achievement_id not in unlocked:
        unlocked.append(achievement_id)
        unlocked_path.write_text(json.dumps(unlocked, indent=2) + "\n", encoding="utf-8")
    return {"ok": True, "achievement": rec, "firstUnlock": achievement_id in unlocked[-1:]}


def maybe_achievements_from_result(ws: Path, apply_report: dict[str, Any]) -> list[dict[str, Any]]:
    """Fire stub achievements based on hub apply / tokens."""
    fired: list[dict[str, Any]] = []
    tokens = []
    lr = apply_report.get("lastResult") or {}
    if isinstance(lr, dict):
        tokens = list(lr.get("tokens") or [])
    text = " ".join(str(t) for t in tokens).lower()
    mission_n = apply_report.get("missionNumber")
    try:
        mission_n = int(mission_n) if mission_n is not None else None
    except (TypeError, ValueError):
        mission_n = None

    if mission_n == 2 or "first" in text:
        fired.append(unlock_achievement(ws, "FIRST_SORTIE", detail=f"mission→{mission_n}"))
    if "clean" in text or "extractionclean" in text.replace(" ", ""):
        fired.append(unlock_achievement(ws, "CLEAN_EXTRACT", detail="from result tokens"))
    if mission_n is not None and mission_n >= 6:
        fired.append(unlock_achievement(ws, "ARC_1_CLEAR", detail=f"mission={mission_n}"))
    if "same_map" in text or "mode_a" in text or "continue" in text:
        fired.append(unlock_achievement(ws, "SAME_MAP_CHAIN", detail="continue tokens"))
    return fired


def status(ws: Path) -> dict[str, Any]:
    root = ensure_layout(ws)
    unlocked: list[str] = []
    up = root / "unlocked.json"
    if up.is_file():
        try:
            unlocked = list(json.loads(up.read_text(encoding="utf-8-sig")))
        except Exception:  # noqa: BLE001
            pass
    return {
        "schemaVersion": "verdance-steam-status/1.0",
        "steamworksBound": False,
        "appId": None,
        "cloudMirror": str(root / "cloud"),
        "unlocked": unlocked,
        "catalog": list(ACHIEVEMENT_CATALOG.keys()),
        "note": "Stub until Steam AppID + partner depot. Cloud = local mirror only.",
    }
