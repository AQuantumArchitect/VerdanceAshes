#!/usr/bin/env python3
"""human_play_telemetry_v1 — harvest Luke's BAR play session for hive/Grok.

Separate from player_proxy residuals. Law:
  - kind = human_player (never silently train UL from this without seal)
  - writes workspace outbox + yurt-sync commons/vitals when present
  - best-effort: missing infolog/result still writes an honest face

CLI:
  python tools/human_play_telemetry_v1.py harvest
  python tools/human_play_telemetry_v1.py status
  python tools/human_play_telemetry_v1.py open-scorecard
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_TOOLS = Path(__file__).resolve().parent
_WS = _TOOLS.parent
_OUTBOX = _WS / "outbox"
_FACE = _OUTBOX / "human_playthrough.latest.json"
_TAPE = _OUTBOX / "human_playthrough_tape.jsonl"
_SCORECARD = _WS / "docs" / "HUMAN_PLAY_SCORECARD.md"
_BRIEF = _WS / "docs" / "LUKE_PLAYTEST_TODAY.md"

# mesh faces (optional)
_SYNC_CANDIDATES = [
    Path(r"C:\Users\Luke Spooner\ws-win\yurt-sync"),
    Path(r"C:\Users\Luke\yurt-sync"),
    Path(os.environ.get("SYNC_ROOT") or ""),
]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _sync_root() -> Path | None:
    for p in _SYNC_CANDIDATES:
        try:
            if p and p.is_dir() and (p / "commons" / "vitals").is_dir():
                return p
        except OSError:
            continue
    return None


def _load_json(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else None
    except (OSError, json.JSONDecodeError):
        return None


def _write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def _append_tape(row: dict[str, Any]) -> None:
    _TAPE.parent.mkdir(parents=True, exist_ok=True)
    with _TAPE.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")


def _version() -> str:
    p = _WS / "VERSION"
    try:
        return p.read_text(encoding="utf-8").strip() if p.is_file() else "unknown"
    except OSError:
        return "unknown"


def _infolog_path() -> Path | None:
    cfg = _load_json(_WS / "verdance_config.json") or {}
    # optional explicit
    for key in ("infolog", "infologPath"):
        raw = cfg.get(key)
        if raw and Path(str(raw)).is_file():
            return Path(str(raw))
    bar_root = cfg.get("barDataRoot") or r"C:\Users\Luke Spooner\AppData\Local\Programs\Beyond-All-Reason\data"
    candidates = [
        Path(bar_root) / "infolog.txt",
        Path(bar_root) / "infolog.txt.txt",
        Path.home() / "Documents" / "My Games" / "Spring" / "infolog.txt",
    ]
    for c in candidates:
        if c.is_file():
            return c
    return None


def _extract_va_markers(text: str) -> dict[str, Any]:
    """Pull useful VA_* signal counts + last result blob hints from infolog."""
    markers = [
        "VA_RESULT",
        "VA_RESULT_JSON_BEGIN",
        "VA_RESULT_JSON_COMPACT",
        "VA_TENEBRIUM_",
        "VA_TENEBRIUM_BPCAP",
        "VA_CAPTURE_",
        "VA_NODE_CLAIMED",
        "VA_POCKET_CLEARED",
        "VA_NEXT_SORTIE_CHOICE",
        "VA_TELEMETRY_JSON",
    ]
    counts: dict[str, int] = {}
    for m in markers:
        counts[m] = len(re.findall(re.escape(m), text))
    # last few interesting lines
    lines = [ln.strip() for ln in text.splitlines() if "VA_" in ln]
    tail = lines[-40:] if lines else []
    return {"marker_counts": counts, "va_line_tail": tail}


def _try_ps_extract() -> dict[str, Any]:
    """Best-effort call existing extract_latest_result.ps1 (does not fail harvest)."""
    script = _WS / "scripts" / "extract_latest_result.ps1"
    if not script.is_file():
        return {"ok": False, "error": "extract_script_missing"}
    try:
        proc = subprocess.run(
            [
                "powershell",
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                str(script),
                "-Workspace",
                str(_WS),
            ],
            capture_output=True,
            text=True,
            timeout=120,
            cwd=str(_WS),
        )
        return {
            "ok": proc.returncode == 0,
            "rc": proc.returncode,
            "stdout_tail": (proc.stdout or "")[-800:],
            "stderr_tail": (proc.stderr or "")[-800:],
        }
    except Exception as e:
        return {"ok": False, "error": f"{type(e).__name__}:{e}"}


def _try_telemetry_extract() -> dict[str, Any]:
    script = _WS / "scripts" / "extract_latest_telemetry.ps1"
    if not script.is_file():
        return {"ok": False, "error": "telemetry_script_missing"}
    try:
        proc = subprocess.run(
            [
                "powershell",
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                str(script),
                "-Workspace",
                str(_WS),
            ],
            capture_output=True,
            text=True,
            timeout=120,
            cwd=str(_WS),
        )
        return {"ok": proc.returncode == 0, "rc": proc.returncode}
    except Exception as e:
        return {"ok": False, "error": f"{type(e).__name__}:{e}"}


def _scorecard_snippet() -> dict[str, Any]:
    if not _SCORECARD.is_file():
        return {"present": False}
    try:
        text = _SCORECARD.read_text(encoding="utf-8")
    except OSError:
        return {"present": False}
    filledish = any(
        x in text
        for x in (
            "blocker",
            "Win",
            "felt",
            "1–5",
            "1-5",
        )
    ) and not text.count("_______________") > 8
    # crude: any non-template content under Notes
    notes = ""
    if "## Notes for retune" in text:
        notes = text.split("## Notes for retune", 1)[-1][:1200]
    return {
        "present": True,
        "path": str(_SCORECARD),
        "bytes": len(text),
        "maybe_filled": filledish,
        "notes_tail": notes.strip()[:600],
    }


def harvest(*, note: str = "") -> dict[str, Any]:
    session_id = f"human-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}-{uuid.uuid4().hex[:6]}"
    extract = _try_ps_extract()
    telem = _try_telemetry_extract()

    infolog = _infolog_path()
    va: dict[str, Any] = {}
    infolog_meta: dict[str, Any] = {"path": str(infolog) if infolog else None, "found": bool(infolog)}
    if infolog:
        try:
            # tail-heavy read for large logs
            raw = infolog.read_text(encoding="utf-8", errors="ignore")
            if len(raw) > 2_000_000:
                raw = raw[-2_000_000:]
            infolog_meta["bytes_read"] = len(raw)
            infolog_meta["mtime"] = datetime.fromtimestamp(
                infolog.stat().st_mtime, tz=timezone.utc
            ).isoformat()
            va = _extract_va_markers(raw)
        except OSError as e:
            infolog_meta["error"] = str(e)

    # companion faces
    companions = {
        "proxy_residual": _load_json(_OUTBOX / "hive_bar_residual.latest.json")
        or _load_json(_OUTBOX / "proxy_campaign.latest.json"),
        "campaign_fruit": _load_json(_OUTBOX / "campaign_fruit.latest.json"),
        "zone_telemetry": _load_json(_OUTBOX / "bar_zone_telemetry.latest.json"),
        "play_session_status": _load_json(_OUTBOX / "play_session.status.json"),
        "result_harvest_fail": _load_json(_OUTBOX / "result_harvest_fail.latest.json"),
        "hub_state": _load_json(_OUTBOX / "hub_state.latest.json")
        or _load_json(_OUTBOX / "hub_result.latest.json"),
    }
    # strip huge companions to summary
    companion_summary: dict[str, Any] = {}
    for k, v in companions.items():
        if not v:
            companion_summary[k] = None
            continue
        companion_summary[k] = {
            "schema": v.get("schema") or v.get("schemaVersion"),
            "at": v.get("at") or v.get("generatedAt"),
            "keys": list(v.keys())[:24],
        }

    # latest archived human-ish result if extract wrote inbox
    result_inbox = None
    for cand in (
        _WS / "inbox" / "latest_result.json",
        _WS / "inbox" / "result.latest.json",
        _OUTBOX / "latest_result.json",
    ):
        if cand.is_file():
            result_inbox = _load_json(cand)
            if result_inbox:
                break

    face: dict[str, Any] = {
        "schema": "human-playthrough/1.0",
        "kind": "human_player",
        "player": "luke",
        "node": "wargen",
        "at": _now(),
        "session_id": session_id,
        "workspace": str(_WS),
        "workspace_version": _version(),
        "law": [
            "human_player != player_proxy",
            "do not auto-train UL from this face without human seal open",
            "scorecard prose is first-class evidence",
            "VA_RESULT extract is best-effort",
        ],
        "note": note or None,
        "extract_result": extract,
        "extract_telemetry": telem,
        "infolog": infolog_meta,
        "va": va,
        "scorecard": _scorecard_snippet(),
        "companions": companion_summary,
        "result_inbox_present": result_inbox is not None,
        "result_summary": None,
        "proxy_contrast": {
            "proxy_simple_win": None,
            "proxy_barb_win": None,
            "note": "Human feel may diverge hard from proxy win rates; bank feel gates in scorecard.",
        },
        "paths": {
            "brief": str(_BRIEF),
            "scorecard": str(_SCORECARD),
            "face": str(_FACE),
            "tape": str(_TAPE),
        },
    }

    if result_inbox:
        face["result_summary"] = {
            k: result_inbox.get(k)
            for k in (
                "resultKey",
                "verdict",
                "outcome",
                "map",
                "mapName",
                "missionId",
                "tnb",
                "fun",
                "win",
            )
            if k in result_inbox
        } or {"keys": list(result_inbox.keys())[:20]}

    residual = companions.get("proxy_residual") or {}
    by = residual.get("byStyle") if isinstance(residual, dict) else None
    if isinstance(by, dict):
        face["proxy_contrast"]["proxy_simple_win"] = (by.get("simple") or {}).get("meanWinRate")
        face["proxy_contrast"]["proxy_barb_win"] = (by.get("barbarian") or {}).get("meanWinRate")

    _write_json(_FACE, face)
    _append_tape({"ts": _now(), "event": "harvest", "session_id": session_id, "face_path": str(_FACE)})

    sync = _sync_root()
    vitals_paths: list[str] = []
    if sync:
        vitals = sync / "commons" / "vitals"
        dest = vitals / "human_playthrough.latest.json"
        tape = vitals / "human_playthrough_tape.jsonl"
        try:
            _write_json(dest, face)
            with tape.open("a", encoding="utf-8") as f:
                f.write(json.dumps({"ts": _now(), "event": "harvest", "session_id": session_id}, ensure_ascii=False) + "\n")
            # also copy scorecard snapshot for hive
            sc_dest = vitals / "human_play_scorecard.latest.md"
            if _SCORECARD.is_file():
                shutil.copy2(_SCORECARD, sc_dest)
            vitals_paths = [str(dest), str(tape), str(sc_dest)]
            face["mesh_published"] = True
            face["mesh_paths"] = vitals_paths
            _write_json(_FACE, face)  # refresh with mesh paths
            _write_json(dest, face)
        except OSError as e:
            face["mesh_published"] = False
            face["mesh_error"] = str(e)
            _write_json(_FACE, face)
    else:
        face["mesh_published"] = False
        face["mesh_error"] = "yurt-sync vitals not found"
        _write_json(_FACE, face)

    return face


def status() -> dict[str, Any]:
    face = _load_json(_FACE)
    return {
        "face": face,
        "scorecard": str(_SCORECARD) if _SCORECARD.is_file() else None,
        "brief": str(_BRIEF) if _BRIEF.is_file() else None,
        "sync": str(_sync_root()) if _sync_root() else None,
    }


def open_scorecard() -> dict[str, Any]:
    path = _SCORECARD if _SCORECARD.is_file() else _BRIEF
    if not path.is_file():
        return {"ok": False, "error": "no_scorecard"}
    try:
        os.startfile(str(path))  # type: ignore[attr-defined]
        return {"ok": True, "path": str(path)}
    except Exception as e:
        return {"ok": False, "error": str(e), "path": str(path)}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("cmd", choices=("harvest", "status", "open-scorecard"))
    ap.add_argument("--note", default="", help="optional free-text note on harvest")
    args = ap.parse_args()
    if args.cmd == "harvest":
        face = harvest(note=args.note)
        print(json.dumps(face, indent=2, default=str)[:6000])
        print(f"\n[human_play] wrote {_FACE}", file=sys.stderr)
        if face.get("mesh_published"):
            print(f"[human_play] mesh {face.get('mesh_paths')}", file=sys.stderr)
        return 0
    if args.cmd == "status":
        print(json.dumps(status(), indent=2, default=str)[:4000])
        return 0
    print(json.dumps(open_scorecard(), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
