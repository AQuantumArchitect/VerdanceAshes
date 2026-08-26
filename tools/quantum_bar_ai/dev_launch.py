#!/usr/bin/env python3
"""Dev launch — champion craft campaign + dense human telemetry learning.

Rolls overnight craft into the live campaign, arms high-frequency player
telemetry, rebuilds the next mission seed with ``devTelemetry=true``, and
(optionally) launches the playable BAR session.

After you play, harvest+train:

  python -m quantum_bar_ai.dev_launch --harvest
  # or
  app\\bin\\DEV_HARVEST.bat

Usage:
  python -m quantum_bar_ai.dev_launch              # roll-in + arm + rebuild seed
  python -m quantum_bar_ai.dev_launch --launch     # also start play session
  python -m quantum_bar_ai.dev_launch --harvest    # parse infolog → bar_brain
  python -m quantum_bar_ai.dev_launch --status
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .craft_apply import knobs_from_recipe, load_recipe, roll_into_campaign
from .suite import _workspace_root


DEV_MODE_SCHEMA = "verdance-dev-mode/0.1"


def dev_mode_path(ws: Path | None = None) -> Path:
    return (ws or _workspace_root()) / "app" / "brain" / "dev_mode.json"


def write_dev_mode(
    ws: Path | None = None,
    *,
    enabled: bool = True,
    sample_period_frames: int = 150,
    learn_weight: float = 2.4,
) -> Path:
    ws = ws or _workspace_root()
    recipe = load_recipe(ws)
    knobs = knobs_from_recipe(ws, recipe)
    payload = {
        "schemaVersion": DEV_MODE_SCHEMA,
        "enabled": enabled,
        "armedAt": datetime.now(timezone.utc).isoformat(),
        "telemetry": {
            "dense": True,
            "samplePeriodFrames": sample_period_frames,  # 150 ≈ 5s @ 30fps
            "trackPlayerCommands": True,
            "includeArmyComposition": True,
            "includeZoneCentroid": True,
            "includeResourceIncome": True,
            "echoCompactEverySample": True,
        },
        "learning": {
            "humanWeight": learn_weight,
            "autoHarvestOnSessionEnd": True,
            "trainBarBrain": True,
            "notes": "Human gold samples count ~2.4× vs proxy sims.",
        },
        "craft": {
            "stamp": recipe.get("stamp"),
            "craft_score": recipe.get("craft_score"),
            "knobs": knobs.as_dict() if knobs else None,
        },
        "notes": (
            "DEV LAUNCH — high telemetry on the human player. "
            "Not for customer export. Disarm with --disarm."
        ),
    }
    p = dev_mode_path(ws)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return p


def disarm_dev_mode(ws: Path | None = None) -> Path:
    p = write_dev_mode(ws, enabled=False)
    data = json.loads(p.read_text(encoding="utf-8"))
    data["enabled"] = False
    data["disarmedAt"] = datetime.now(timezone.utc).isoformat()
    p.write_text(json.dumps(data, indent=2), encoding="utf-8")
    return p


def load_dev_mode(ws: Path | None = None) -> dict[str, Any]:
    p = dev_mode_path(ws)
    if not p.is_file():
        return {"enabled": False}
    return json.loads(p.read_text(encoding="utf-8-sig"))


def _stamp_dev_on_seed(ws: Path) -> dict[str, Any]:
    """Patch generated va_current.lua / va seed JSON if present with devTelemetry."""
    # Prefer JSON seed if build pipeline wrote one; also patch lua via rebuild.
    seed_json = ws / "mod" / "VerdanceAshes.sdd" / "singleplayer" / "verdance_ashes" / "generated" / "va_current.json"
    # Common path: only .lua exists. Write companion flag file the gadget can VFS.Include.
    flag = (
        ws
        / "mod"
        / "VerdanceAshes.sdd"
        / "singleplayer"
        / "verdance_ashes"
        / "generated"
        / "dev_telemetry_flag.lua"
    )
    dev = load_dev_mode(ws)
    period = int((dev.get("telemetry") or {}).get("samplePeriodFrames") or 150)
    enabled = bool(dev.get("enabled"))
    flag.parent.mkdir(parents=True, exist_ok=True)
    flag.write_text(
        "return {\n"
        f"  enabled = {'true' if enabled else 'false'},\n"
        f"  samplePeriodFrames = {period},\n"
        "  trackPlayerCommands = true,\n"
        "  schemaVersion = 'verdance-dev-telemetry-flag/0.1',\n"
        "}\n",
        encoding="utf-8",
    )
    # Also write workspace outbox marker
    outbox = ws / "outbox" / "dev_mode.latest.json"
    outbox.write_text(json.dumps(dev, indent=2), encoding="utf-8")
    return {"flag": str(flag), "enabled": enabled, "period": period, "seed_json": str(seed_json)}


def rebuild_mission(ws: Path) -> dict[str, Any]:
    """Invoke build_next_mission_v1.ps1 so craft scales land in the seed."""
    script = ws / "scripts" / "build_next_mission_v1.ps1"
    if not script.is_file():
        return {"ok": False, "reason": "build_next_mission_v1.ps1 missing"}
    cmd = [
        "powershell",
        "-NoProfile",
        "-ExecutionPolicy",
        "Bypass",
        "-File",
        str(script),
        "-Workspace",
        str(ws),
    ]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
        return {
            "ok": r.returncode == 0,
            "returncode": r.returncode,
            "stdout_tail": (r.stdout or "")[-1500:],
            "stderr_tail": (r.stderr or "")[-800:],
        }
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "reason": f"{type(e).__name__}: {e}"}


def launch_play_session(ws: Path) -> dict[str, Any]:
    script = ws / "scripts" / "play_session_v1.ps1"
    if not script.is_file():
        return {"ok": False, "reason": "play_session_v1.ps1 missing"}
    # Non-blocking start so the CLI returns; user plays in BAR.
    cmd = [
        "powershell",
        "-NoProfile",
        "-ExecutionPolicy",
        "Bypass",
        "-File",
        str(script),
        "-Workspace",
        str(ws),
        "-MaxMissions",
        "1",
    ]
    try:
        # Use Start-Process style via Popen
        proc = subprocess.Popen(
            cmd,
            cwd=str(ws),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        return {"ok": True, "pid": proc.pid, "note": "play_session started in background"}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "reason": f"{type(e).__name__}: {e}"}


def arm_dev_launch(
    ws: Path | None = None,
    *,
    launch: bool = False,
    rebuild: bool = True,
    sample_period_frames: int = 150,
) -> dict[str, Any]:
    ws = ws or _workspace_root()
    roll = roll_into_campaign(ws)
    dev_path = write_dev_mode(ws, enabled=True, sample_period_frames=sample_period_frames)
    stamp = _stamp_dev_on_seed(ws)
    rebuild_info: dict[str, Any] = {"skipped": True}
    if rebuild:
        rebuild_info = rebuild_mission(ws)
        # re-stamp flag after rebuild (build may wipe generated/)
        stamp = _stamp_dev_on_seed(ws)
    launch_info: dict[str, Any] = {"skipped": True}
    if launch:
        launch_info = launch_play_session(ws)

    report = {
        "ok": bool(roll.get("ok")),
        "schemaVersion": DEV_MODE_SCHEMA,
        "armedAt": datetime.now(timezone.utc).isoformat(),
        "craft_roll_in": roll,
        "dev_mode": str(dev_path),
        "seed_stamp": stamp,
        "rebuild": rebuild_info,
        "launch": launch_info,
        "next": [
            "Play the mission in BAR (dev telemetry samples every ~5s).",
            "When done: python -m quantum_bar_ai.dev_launch --harvest",
            "Or: app\\bin\\DEV_HARVEST.bat",
        ],
    }
    out = ws / "outbox" / "dev_launch.latest.json"
    out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    return report


def harvest_and_train(ws: Path | None = None, *, train: bool = True) -> dict[str, Any]:
    from .player_telemetry import harvest_infolog

    return harvest_infolog(ws=ws or _workspace_root(), train=train)


def main() -> int:
    ap = argparse.ArgumentParser(description="Dev launch: craft campaign + dense player telemetry")
    ap.add_argument("--launch", action="store_true", help="Also start play_session_v1")
    ap.add_argument("--no-rebuild", action="store_true", help="Skip mission rebuild")
    ap.add_argument("--period", type=int, default=150, help="Sample period frames (default 150≈5s)")
    ap.add_argument("--harvest", action="store_true", help="Harvest infolog → bar_brain")
    ap.add_argument("--no-train", action="store_true", help="With --harvest, skip training")
    ap.add_argument("--disarm", action="store_true", help="Disable dev telemetry mode")
    ap.add_argument("--status", action="store_true")
    ap.add_argument("--roll-in-only", action="store_true", help="Only roll craft into campaign")
    args = ap.parse_args()

    ws = _workspace_root()

    if args.status:
        dev = load_dev_mode(ws)
        recipe = load_recipe(ws)
        print(
            json.dumps(
                {
                    "dev_mode": dev,
                    "craft_stamp": recipe.get("stamp"),
                    "craft_score": recipe.get("craft_score"),
                    "knobs": recipe.get("knobs"),
                },
                indent=2,
            )
        )
        return 0

    if args.disarm:
        p = disarm_dev_mode(ws)
        _stamp_dev_on_seed(ws)
        print(json.dumps({"ok": True, "disarmed": str(p)}, indent=2))
        return 0

    if args.harvest:
        summary = harvest_and_train(ws, train=not args.no_train)
        print(json.dumps(summary, indent=2))
        return 0 if summary.get("ok") else 1

    if args.roll_in_only:
        report = roll_into_campaign(ws)
        print(json.dumps(report, indent=2))
        return 0 if report.get("ok") else 1

    report = arm_dev_launch(
        ws,
        launch=args.launch,
        rebuild=not args.no_rebuild,
        sample_period_frames=args.period,
    )
    print(json.dumps(report, indent=2))
    if not report.get("ok"):
        return 1
    print("\n=== DEV LAUNCH ARMED ===", file=sys.stderr)
    print("Craft rolled in. Dense player telemetry ON.", file=sys.stderr)
    if args.launch:
        print("Play session starting…", file=sys.stderr)
    else:
        print("Rebuild mission seed done. Launch BAR when ready, then --harvest.", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
