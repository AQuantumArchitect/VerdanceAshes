#!/usr/bin/env python3
"""Continuity store helpers — single writer surface for scar / HV / claim seams.

Phase 1: mark destroyed high-value pockets so reinduction and story marks
stop highlighting blown fusion vaults.
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence

# Known GF optional fusion vaults (bake_recipe pocket ids).
GF_FUSION_POCKETS = (
    ("gf_c_gate_fus", "GF_C_GATE"),
    ("gf_c_inner_fus", "GF_C_INNER_GATE"),
)


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def load_json(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    data = json.loads(path.read_text(encoding="utf-8-sig"))
    return data if isinstance(data, dict) else {}


def mark_hv_pockets_destroyed(
    state: Dict[str, Any],
    map_id: str,
    pockets: Sequence[tuple[str, str] | str],
    *,
    reason: str = "continuity_repair",
) -> Dict[str, Any]:
    """Stamp heldInstallations + scar ledger so bake suppresses these vaults."""
    mid = str(map_id or "")
    if not mid:
        return {"ok": False, "error": "missing mapId", "marked": []}
    held = state.setdefault("heldInstallations", {})
    map_held = held.setdefault(mid, {})
    if not isinstance(map_held, dict):
        map_held = {}
        held[mid] = map_held
    ledger = state.setdefault("shellScars", {})
    bucket = ledger.setdefault(mid, {"units": [], "byZone": {}, "updatedAt": None})
    units = bucket.setdefault("units", [])
    if not isinstance(units, list):
        units = []
        bucket["units"] = units
    marked: List[str] = []
    for entry in pockets:
        if isinstance(entry, (tuple, list)) and len(entry) >= 1:
            pid = str(entry[0])
            zid = str(entry[1]) if len(entry) > 1 else ""
        else:
            pid = str(entry)
            zid = ""
        if not pid:
            continue
        rec = map_held.get(pid) if isinstance(map_held.get(pid), dict) else {}
        rec.update(
            {
                "pocketId": pid,
                "zoneId": zid or rec.get("zoneId") or "",
                "installationId": rec.get("installationId") or f"{mid}::{pid}",
                "owner": rec.get("owner") or "enemy",
                "status": "destroyed",
                "highValue": True,
                "destroyedAt": utc_now(),
                "reason": reason,
            }
        )
        map_held[pid] = rec
        units.append(
            {
                "zoneId": zid or rec.get("zoneId") or "",
                "pocketId": pid,
                "unitDefName": "armfus",
                "destroyed": True,
                "damageFrac": 1.0,
                "highValue": True,
                "at": utc_now(),
                "resultKey": reason,
            }
        )
        if zid:
            zm = (state.get("zoneMemory") or {}).setdefault(mid, {}).setdefault(zid, {})
            if isinstance(zm, dict):
                absr = zm.setdefault("abstract", {})
                if isinstance(absr, dict):
                    absr["shellScar"] = round(min(1.0, max(float(absr.get("shellScar") or 0.0), 0.55)), 4)
                    absr["hvDestroyed"] = True
            by = bucket.setdefault("byZone", {})
            z = by.setdefault(zid, {"destroyedCount": 0, "damageSum": 0.0})
            z["destroyedCount"] = int(z.get("destroyedCount") or 0) + 1
            z["damageSum"] = float(z.get("damageSum") or 0.0) + 1.0
        marked.append(pid)
    bucket["updatedAt"] = utc_now()
    if len(units) > 400:
        bucket["units"] = units[-300:]
    return {"ok": True, "mapId": mid, "marked": marked, "reason": reason}


def repair_greenest_fields_fusion(state: Dict[str, Any]) -> Dict[str, Any]:
    """Player-witnessed: GF fusion vaults already exploded — stop reinducing/highlighting."""
    return mark_hv_pockets_destroyed(
        state,
        "greenest_fields",
        GF_FUSION_POCKETS,
        reason="player_witness_fusion_cleared",
    )


def main() -> int:
    ap = argparse.ArgumentParser(description="Continuity store repair / HV destroy stamp")
    ap.add_argument("--workspace", default=".")
    ap.add_argument("--state", default="state/campaign_state.json")
    ap.add_argument("--write-state", action="store_true")
    ap.add_argument(
        "--repair-gf-fusion",
        action="store_true",
        help="Mark both Greenest Fields fusion vaults destroyed (player witness).",
    )
    ap.add_argument("--map-id", default=None)
    ap.add_argument(
        "--destroy-pocket",
        action="append",
        default=[],
        help="pocketId or pocketId:zoneId (repeatable)",
    )
    args = ap.parse_args()
    ws = Path(args.workspace).resolve()
    path = ws / args.state
    state = load_json(path)
    reports: List[Dict[str, Any]] = []
    if args.repair_gf_fusion:
        reports.append(repair_greenest_fields_fusion(state))
    if args.destroy_pocket:
        mid = args.map_id or str(state.get("sessionHomeMap") or "greenest_fields")
        pockets = []
        for raw in args.destroy_pocket:
            if ":" in raw:
                pid, zid = raw.split(":", 1)
                pockets.append((pid.strip(), zid.strip()))
            else:
                pockets.append(raw.strip())
        reports.append(mark_hv_pockets_destroyed(state, mid, pockets))
    if args.write_state and reports and all(r.get("ok") for r in reports):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")
        for r in reports:
            r["wroteState"] = True
            r["statePath"] = str(path)
    print(json.dumps({"ok": True, "reports": reports}, indent=2))
    return 0 if reports and all(r.get("ok") for r in reports) else 2


if __name__ == "__main__":
    raise SystemExit(main())
