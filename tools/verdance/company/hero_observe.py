#!/usr/bin/env python3
"""L3 hero observe — append-only stamps for co-deploy / camp-talk / Drop settle.

Schema: verdance-hero-observe/0.1
Tape:   outbox/hero_observe_tape.jsonl
Face:   outbox/hero_observe.latest.json

Best-effort: never raise into settle / camp-talk callers.

Usage:
  python -m verdance.company.hero_observe status
  python -m verdance.company.hero_observe smoke
"""
from __future__ import annotations

import argparse
import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from verdance.common import WORKSPACE_ROOT
from verdance.world.map_umwelt import pressure_for

ROOT = WORKSPACE_ROOT
SCHEMA = "verdance-hero-observe/0.1"
DEFAULT_TAPE = ROOT / "outbox" / "hero_observe_tape.jsonl"
DEFAULT_FACE = ROOT / "outbox" / "hero_observe.latest.json"

# recent-key window for cheap idempotency (proxy/sim double settle)
_RECENT_SCAN = 40


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def observe_tape(workspace: Path | None = None) -> Path:
    ws = workspace or ROOT
    return ws / "outbox" / "hero_observe_tape.jsonl"


def observe_face(workspace: Path | None = None) -> Path:
    ws = workspace or ROOT
    return ws / "outbox" / "hero_observe.latest.json"


def _stamp_key(stamp: dict[str, Any]) -> str | None:
    if stamp.get("resultKey"):
        return f"result:{stamp['resultKey']}"
    if stamp.get("talkId"):
        return f"talk:{stamp['talkId']}"
    return None


def _recent_keys(path: Path, limit: int = _RECENT_SCAN) -> set[str]:
    if not path.is_file():
        return set()
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return set()
    keys: set[str] = set()
    for line in lines[-limit:]:
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        k = _stamp_key(row) if isinstance(row, dict) else None
        if k:
            keys.add(k)
    return keys


def append_observe(
    stamp: dict[str, Any],
    *,
    workspace: Path | None = None,
    skip_dup: bool = True,
) -> dict[str, Any]:
    """Append one JSONL stamp. Returns {ok, path, skipped?} — never raises."""
    try:
        ws = workspace or ROOT
        path = observe_tape(ws)
        face = observe_face(ws)
        row = dict(stamp)
        row.setdefault("schemaVersion", SCHEMA)
        row.setdefault("ts", _now_iso())
        row.setdefault("unix", int(time.time()))

        key = _stamp_key(row)
        if skip_dup and key:
            if key in _recent_keys(path):
                return {"ok": True, "skipped": True, "reason": "duplicate_key", "key": key, "path": str(path)}

        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
        try:
            face.write_text(json.dumps(row, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        except OSError:
            pass
        return {"ok": True, "skipped": False, "path": str(path), "key": key}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": f"{type(e).__name__}: {e}"}


def _outcome_tags(result: dict[str, Any], *, success: bool, zone_flipped: bool) -> list[str]:
    tags: list[str] = []
    status = str(result.get("status") or result.get("verdict") or "")
    if success:
        tags.append("success")
    else:
        tags.append("failure")
    if status:
        tags.append(f"status:{status}")
    if zone_flipped:
        tags.append("zone_flip")
    # wounds / deaths from named outcomes
    named = result.get("namedOutcomes") or []
    if isinstance(named, list):
        for o in named:
            if not isinstance(o, dict):
                continue
            hid = str(o.get("charId") or o.get("heroId") or "")
            outcome = str(o.get("outcome") or "")
            if outcome == "dead" and hid:
                tags.append(f"dead:{hid}")
            elif outcome in ("wounded", "recovered") and hid:
                tags.append(f"wound:{hid}")
    if status in ("extracted", "partial"):
        tags.append("extract")
    return tags


def stamp_from_sortie(
    state: dict[str, Any],
    result: dict[str, Any],
    *,
    success: bool,
    zone_flipped: bool = False,
    pair_delta: dict[str, Any] | None = None,
    map_pressure: dict[str, float] | None = None,
    ran_on: str = "player",
    eta: float = 0.4,
) -> dict[str, Any]:
    pair_delta = pair_delta or {}
    deployed = list(pair_delta.get("deployed") or [])
    if not deployed:
        # best-effort without importing attachments (avoid cycles); result keys only
        for key in ("deployAces", "deployedHeroes", "sortieHeroes"):
            raw = result.get(key)
            if isinstance(raw, list):
                for x in raw:
                    if isinstance(x, dict):
                        hid = x.get("id") or x.get("heroId")
                        if hid:
                            deployed.append(str(hid))
                    elif x:
                        deployed.append(str(x))
    heroes = list(dict.fromkeys(deployed))  # stable dedup

    events: list[dict[str, Any]] = []
    pairs = pair_delta.get("pairs") or {}
    if pairs:
        events.append(
            {
                "kind": "co_deploy",
                "delta": pair_delta.get("bump"),
                "pairCount": len(pairs),
                "pairIds": list(pairs.keys()),
            }
        )
    events.append(
        {
            "kind": "outcome",
            "tags": _outcome_tags(result, success=success, zone_flipped=zone_flipped),
        }
    )

    map_id = str(result.get("mapId") or result.get("deploymentMapId") or "")
    zone_id = str(result.get("targetZoneId") or result.get("deploymentZoneId") or "")
    result_key = str(
        result.get("resultKey")
        or result.get("id")
        or result.get("sortieId")
        or f"{map_id}:{zone_id}:{result.get('status') or result.get('verdict') or ''}:{int(time.time())}"
    )

    stamp: dict[str, Any] = {
        "schemaVersion": SCHEMA,
        "kind": "sortie_settle",
        "ran_on": ran_on,
        "eta": float(eta),
        "umweltd_dark": False,
        "heroes": heroes,
        "mapId": map_id,
        "zoneId": zone_id,
        "mapPressure": map_pressure or {},
        "events": events,
        "resultKey": result_key,
        "success": bool(success),
    }
    # fit glance if pressure + heroes present
    if map_pressure and heroes:
        try:
            hero_path = ROOT / "data" / "story" / "hero_umwelt.json"
            if hero_path.is_file():
                hdoc = json.loads(hero_path.read_text(encoding="utf-8-sig"))
                by = {h["heroId"]: h for h in (hdoc.get("heroes") or []) if isinstance(h, dict)}
                fits = []
                for hid in heroes:
                    ax = (by.get(hid) or {}).get("axes") or {}
                    score = sum(float(ax.get(a, 0.0)) * float(map_pressure.get(a, 0.0)) for a in map_pressure)
                    fits.append({"heroId": hid, "fit": round(score, 4)})
                stamp["heroFit"] = fits
        except Exception:  # noqa: BLE001
            pass
    return stamp


def stamp_from_camp_talk(
    talk: dict[str, Any],
    receipt: dict[str, Any],
    *,
    map_id: str = "",
    zone_id: str = "",
    map_pressure: dict[str, float] | None = None,
    ran_on: str = "player",
    eta: float = 0.5,
) -> dict[str, Any]:
    a = str(talk.get("a") or "")
    b = str(talk.get("b") or "")
    return {
        "schemaVersion": SCHEMA,
        "kind": "camp_talk",
        "ran_on": ran_on,
        "eta": float(eta),
        "umweltd_dark": False,
        "heroes": [h for h in (a, b) if h],
        "mapId": map_id or "camp",
        "zoneId": zone_id or "hearth",
        "mapPressure": map_pressure or {},
        "events": [
            {
                "kind": "pair_talk",
                "rank": talk.get("rank"),
                "talkId": talk.get("id"),
                "title": talk.get("title"),
                "polarity": talk.get("polarity"),
                "after": receipt.get("after"),
                "pointsDelta": receipt.get("delta"),
            }
        ],
        "talkId": str(talk.get("id") or ""),
        "receiptOk": bool(receipt.get("ok")),
    }


def try_append_sortie(
    state: dict[str, Any],
    result: dict[str, Any],
    *,
    success: bool,
    zone_flipped: bool = False,
    pair_delta: dict[str, Any] | None = None,
    workspace: Path | None = None,
    ran_on: str = "player",
) -> dict[str, Any]:
    """Resolve mapPressure + append sortie stamp. Best-effort."""
    try:

        map_id = str(result.get("mapId") or result.get("deploymentMapId") or "")
        zone_id = str(result.get("targetZoneId") or result.get("deploymentZoneId") or "")
        pressure = pressure_for(map_id, zone_id or None) if map_id else {}
    except Exception:  # noqa: BLE001
        pressure = {}
    stamp = stamp_from_sortie(
        state,
        result,
        success=success,
        zone_flipped=zone_flipped,
        pair_delta=pair_delta,
        map_pressure=pressure,
        ran_on=ran_on,
    )
    return append_observe(stamp, workspace=workspace)


def try_append_camp_talk(
    talk: dict[str, Any],
    receipt: dict[str, Any],
    *,
    workspace: Path | None = None,
    ran_on: str = "player",
    home_map_id: str = "the_rock_jungle",
) -> dict[str, Any]:
    try:

        # Hearth talks happen at home — soft home pressure for context
        pressure = pressure_for(home_map_id, "TRJ_C_SPILLWAY")
    except Exception:  # noqa: BLE001
        pressure = {}
    stamp = stamp_from_camp_talk(
        talk,
        receipt,
        map_id=home_map_id,
        zone_id="hearth",
        map_pressure=pressure,
        ran_on=ran_on,
    )
    return append_observe(stamp, workspace=workspace)


def status(workspace: Path | None = None) -> dict[str, Any]:
    tape = observe_tape(workspace)
    face = observe_face(workspace)
    n = 0
    if tape.is_file():
        try:
            n = sum(1 for line in tape.read_text(encoding="utf-8").splitlines() if line.strip())
        except OSError:
            n = -1
    latest = None
    if face.is_file():
        try:
            latest = json.loads(face.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            latest = {"error": "unreadable"}
    return {
        "ok": True,
        "tape": str(tape),
        "face": str(face),
        "rows": n,
        "latestKind": (latest or {}).get("kind"),
        "latestHeroes": (latest or {}).get("heroes"),
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    sp = ap.add_subparsers(dest="cmd", required=True)
    sp.add_parser("status")
    sp.add_parser("smoke")
    args = ap.parse_args()

    if args.cmd == "status":
        print(json.dumps(status(), indent=2))
        return 0

    if args.cmd == "smoke":
        # synthetic sortie + talk
        r1 = try_append_sortie(
            {},
            {
                "mapId": "greenest_fields",
                "targetZoneId": "GF_NE_PLATEAU",
                "status": "extracted",
                "resultKey": f"smoke-sortie-{int(time.time())}",
                "deployAces": ["vane", "ketha", "hearth"],
            },
            success=True,
            zone_flipped=False,
            pair_delta={
                "deployed": ["vane", "ketha", "hearth"],
                "bump": 4.0,
                "pairs": {"ketha|vane": {"a": "ketha", "b": "vane", "delta": 4.0}},
            },
            ran_on="smoke",
        )
        r2 = try_append_camp_talk(
            {
                "id": f"smoke-talk-{int(time.time())}",
                "a": "vane",
                "b": "ketha",
                "rank": "C",
                "title": "Smoke hearth",
                "polarity": "bond",
            },
            {"ok": True, "after": 12.0, "delta": 8.0},
            ran_on="smoke",
        )
        print(json.dumps({"sortie": r1, "camp_talk": r2, "status": status()}, indent=2))
        return 0 if r1.get("ok") and r2.get("ok") else 1

    return 1


if __name__ == "__main__":
    raise SystemExit(main())
