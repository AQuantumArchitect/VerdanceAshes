"""The living shell: scars, the player's footprint, surviving installs and abstract regrowth between sorties.

Split out of the single-file story engine in pass ten; the public names are re-exported by
``verdance.campaign`` so ``from verdance.campaign import <name>`` keeps working.
"""
from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Optional, Tuple

from verdance.common import WORKSPACE_ROOT, canonical_map_id, utc_now
from verdance.company import capture_node_claims as cnc

def _is_hv_unit_def(def_name: str, *, adjacent: bool = False) -> bool:
    n = str(def_name or "").lower()
    if not n:
        return False
    if any(tok in n for tok in ("fus", "fusion", "afus", "cafus")):
        return True
    if adjacent and any(tok in n for tok in ("beamer", "annihilator", "cordoom")):
        return True
    return False


def apply_shell_scars(state: Dict[str, Any], result: Dict[str, Any], map_id: str) -> Dict[str, Any]:
    """Merge living-shell damage into campaign scar ledger (occupation model lock).

    Scars persist per map; wrath is never recorded here. Re-entry templates should
    subtract these units / raise damageFrac on matching pocket/zone.
    """
    mid = canonical_map_id(map_id)
    if not mid:
        return {"applied": 0}
    ledger = state.setdefault("shellScars", {})
    bucket = ledger.setdefault(mid, {"units": [], "byZone": {}, "updatedAt": None})
    incoming = result.get("shellScars")
    if not isinstance(incoming, list):
        incoming = []
    # Also accept destroyedObjectives as soft scars on target zone.
    target = result.get("targetZoneId")
    applied = 0
    for item in incoming:
        if not isinstance(item, dict):
            continue
        defn = item.get("unitDefName")
        hv = bool(item.get("highValue")) or _is_hv_unit_def(str(defn or ""), adjacent=True)
        rec = {
            "zoneId": item.get("zoneId") or target,
            "pocketId": item.get("pocketId"),
            "unitDefName": defn,
            "destroyed": bool(item.get("destroyed", True)),
            "damageFrac": float(item.get("damageFrac") or 1.0),
            "highValue": hv,
            "at": utc_now(),
            "resultKey": result.get("resultKey"),
        }
        bucket["units"].append(rec)
        zid = str(rec.get("zoneId") or "")
        if zid:
            z = bucket["byZone"].setdefault(zid, {"destroyedCount": 0, "damageSum": 0.0})
            if rec["destroyed"]:
                z["destroyedCount"] = int(z.get("destroyedCount") or 0) + 1
            z["damageSum"] = float(z.get("damageSum") or 0.0) + float(rec["damageFrac"])
            # Mirror into zoneMemory abstract scar pressure.
            zm = (state.get("zoneMemory") or {}).get(mid, {}).get(zid)
            if isinstance(zm, dict):
                absr = zm.setdefault("abstract", {})
                absr["shellScar"] = round(min(1.0, float(absr.get("shellScar") or 0.0) + 0.15), 4)
        applied += 1
    # Cap unit list growth
    if len(bucket.get("units") or []) > 400:
        bucket["units"] = bucket["units"][-300:]
    bucket["updatedAt"] = utc_now()
    return {"applied": applied, "mapId": mid}


_CENTER_SNAP_OFFSETS = (0.007, 0.021)
_CENTER_SNAP_TOL = 0.002


def _authored_map_size(map_id: str) -> Optional[Tuple[float, float]]:
    """Spring elmo size of an authored map, or None when the baseline is missing."""
    path = (
        WORKSPACE_ROOT
        / "data"
        / "scenarios"
        / "authored"
        / f"{map_id}.authored_baseline.json"
    )
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return None
    mp = data.get("map") if isinstance(data, dict) else None
    if not isinstance(mp, dict):
        return None
    try:
        sx = float(mp.get("sizeX") or 0)
        sz = float(mp.get("sizeZ") or 0)
    except (TypeError, ValueError):
        return None
    if sx < 512 or sz < 512:
        return None
    return sx, sz


def _center_snap_hit(v: float, size: float) -> bool:
    if size < 512 or v < 1.5:
        return False
    d = abs(v / size - 0.5)
    return any(abs(d - off) < _CENTER_SNAP_TOL for off in _CENTER_SNAP_OFFSETS)


def _is_center_snap_artifact(x: float, z: float, size: Optional[Tuple[float, float]]) -> bool:
    """True when both axes sit on the old four-point map-center lattice.

    shellCoord used to treat elmos as broken normalized coords and park every
    pad on 0.5 ± 0.007 and ± 0.021. Those points are not where the player built.
    """
    if not size:
        return False
    return _center_snap_hit(x, size[0]) and _center_snap_hit(z, size[1])


# Structures a map keeps between drops (the gadget sends at most as many). Was 64: the wind farm
# filled it and the converters and storage built after were dropped.
FOOTPRINT_CAP = 400


def apply_player_footprint(state: Dict[str, Any], result: Dict[str, Any], map_id: str) -> Dict[str, Any]:
    """Persist player-built structures so the next Drop rehydrates them.

    Living-shell occupation stays on the scar/heldInstall path. This is the
    single concrete SoT for company-built pads (labs, solars, LLTs, factories).
    Last extract wins per map — no merge with approximate baseSnapshot counts.

    Absent key = keep prior bag (truncated/legacy results must not wipe pads).
    Explicit [] = intentional clear.
    Units parked on the old map-center lattice (0.5 ± 0.007 / ± 0.021 on both
    axes) are a teleport artifact. A result that contains any of those points
    keeps this map's real pads and drops the lattice, instead of last-extract
    wins. A clean result still replaces the bag.
    """
    mid = canonical_map_id(map_id)
    if not mid:
        return {"kept": 0}
    footprints = state.setdefault("playerFootprints", {})
    has_key = ("playerFootprint" in result) or ("zoneFootprint" in result)
    if not has_key:
        prior = ((footprints.get(mid) or {}).get("units") or [])
        return {"kept": len(prior) if isinstance(prior, list) else 0, "skipped": "absent", "mapId": mid}
    incoming = result.get("playerFootprint")
    if not isinstance(incoming, list):
        incoming = result.get("zoneFootprint") if isinstance(result.get("zoneFootprint"), list) else []
    units: List[Dict[str, Any]] = []
    for item in incoming:
        if not isinstance(item, dict):
            continue
        defn = str(item.get("unitDefName") or item.get("def") or "").strip()
        if not defn:
            continue
        try:
            x = float(item.get("x") or 0)
            z = float(item.get("z") or 0)
        except (TypeError, ValueError):
            continue
        try:
            facing = int(item.get("facing") or 0)
        except (TypeError, ValueError):
            facing = 0
        try:
            hp = float(item.get("hpFrac") or 1.0)
        except (TypeError, ValueError):
            hp = 1.0
        units.append({
            "unitDefName": defn,
            "x": x,
            "z": z,
            "facing": facing,
            "hpFrac": max(0.05, min(1.0, hp)),
            "zoneId": str(item.get("zoneId") or result.get("deploymentZoneId") or ""),
            "owner": "player",
            "role": str(item.get("role") or "player_footprint"),
        })
        if len(units) >= FOOTPRINT_CAP:
            break
    size = _authored_map_size(mid)
    prior_bag = footprints.get(mid) if isinstance(footprints.get(mid), dict) else {}
    prior_units = prior_bag.get("units") if isinstance(prior_bag.get("units"), list) else []

    def _without_lattice(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        kept_rows: List[Dict[str, Any]] = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            try:
                rx = float(row.get("x") or 0)
                rz = float(row.get("z") or 0)
            except (TypeError, ValueError):
                continue
            if _is_center_snap_artifact(rx, rz, size):
                continue
            kept_rows.append(row)
        return kept_rows

    lattice_hits = sum(
        1
        for row in units
        if _is_center_snap_artifact(float(row["x"]), float(row["z"]), size)
    )
    # A center-snap extract is the teleported pile. Keep the pads that were
    # actually built on this map, and do not let an all-lattice list wipe them.
    # A clean extract (no lattice signature) still replaces the bag, so
    # buildings the player destroyed stay gone.
    if lattice_hits:
        merged = _without_lattice(prior_units)
        for row in _without_lattice(units):
            defn = str(row.get("unitDefName") or "")
            rx = float(row["x"])
            rz = float(row["z"])
            duplicate = False
            for old in merged:
                if str(old.get("unitDefName") or "") != defn:
                    continue
                try:
                    ox = float(old.get("x") or 0)
                    oz = float(old.get("z") or 0)
                except (TypeError, ValueError):
                    continue
                if abs(ox - rx) <= 80 and abs(oz - rz) <= 80:
                    duplicate = True
                    break
            if not duplicate:
                merged.append(row)
        if not merged and prior_units:
            return {
                "kept": len(prior_units),
                "skipped": "center_snap_kept_prior",
                "latticeHits": lattice_hits,
                "mapId": mid,
            }
        units = merged[:FOOTPRINT_CAP]
    footprints[mid] = {
        "mapId": mid,
        "updatedAt": utc_now(),
        "resultKey": result.get("resultKey"),
        "deploymentZoneId": result.get("deploymentZoneId"),
        "units": units,
    }
    report: Dict[str, Any] = {"kept": len(units), "mapId": mid}
    if lattice_hits:
        report["latticeHits"] = lattice_hits
        report["merged"] = True
    return report


def apply_surviving_installs(state: Dict[str, Any], result: Dict[str, Any], map_id: str) -> Dict[str, Any]:
    """Persist standing fusion vaults so they remain when the player returns.

    Contested vaults stay enemy-owned. Player-owned / held vaults schedule a
    defend threat — aggression that would wipe the pad becomes a defend sortie
    instead of a silent offscreen delete.
    """
    mid = canonical_map_id(map_id)
    if not mid:
        return {"kept": 0}
    incoming = result.get("survivingInstalls") or result.get("survivingInstallations") or []
    if not isinstance(incoming, list):
        incoming = []
    held = state.setdefault("heldInstallations", {})
    map_held = held.setdefault(mid, {})
    if not isinstance(map_held, dict):
        map_held = {}
        held[mid] = map_held
    kept = 0
    standing_pockets = set()
    for item in incoming:
        if not isinstance(item, dict):
            continue
        pocket = str(item.get("pocketId") or "")
        if not pocket:
            continue
        standing_pockets.add(pocket)
        owner = str(item.get("owner") or "enemy")
        zone = str(item.get("zoneId") or "")
        # Zone flip this sortie upgrades contested prize → company held.
        flipped = bool(result.get("zoneFlipped"))
        target = str(result.get("targetZoneId") or "")
        if flipped and zone and zone == target:
            owner = "player"
        rec = {
            "pocketId": pocket,
            "zoneId": zone,
            "installationId": str(item.get("installationId") or f"{mid}::{pocket}"),
            "owner": owner,
            "status": "standing",
            "highValue": True,
            "units": item.get("units") if isinstance(item.get("units"), list) else [],
            "updatedAt": utc_now(),
            "resultKey": result.get("resultKey"),
        }
        map_held[pocket] = rec
        kept += 1
    # Mark held installs absent from this snapshot as destroyed if we fought
    # their zone hard (scar ledger killed the vault).
    scars = ((state.get("shellScars") or {}).get(mid) or {}).get("units") or []
    dead_hv: set[str] = set()
    adjacent_hits: Dict[str, int] = {}
    for s in scars:
        if not isinstance(s, dict) or not s.get("destroyed"):
            continue
        defn = str(s.get("unitDefName") or "")
        pid = str(s.get("pocketId") or "")
        if not pid:
            continue
        if _is_hv_unit_def(defn, adjacent=False) or s.get("highValue"):
            if _is_hv_unit_def(defn, adjacent=False):
                dead_hv.add(pid)
            else:
                adjacent_hits[pid] = adjacent_hits.get(pid, 0) + 1
        elif _is_hv_unit_def(defn, adjacent=True):
            adjacent_hits[pid] = adjacent_hits.get(pid, 0) + 1
    for pid, hits in adjacent_hits.items():
        if hits >= 3:
            dead_hv.add(pid)
    # Completed bonus_fus_* secondaries are hard vault-death witnesses.
    secs = result.get("secondaryResults") or []
    if isinstance(secs, list):
        for sr in secs:
            if not isinstance(sr, dict):
                continue
            sid = str(sr.get("id") or sr.get("objectiveId") or "")
            if not sid.startswith("bonus_fus_"):
                continue
            done = bool(sr.get("completed")) or int(sr.get("destroyed") or sr.get("destroyedCount") or 0) > 0
            if not done:
                continue
            pid = str(sr.get("pocketId") or sid.replace("bonus_fus_", "", 1))
            if pid:
                dead_hv.add(pid)
    for pid in dead_hv:
        rec = map_held.get(pid) if isinstance(map_held.get(pid), dict) else {
            "pocketId": pid,
            "zoneId": "",
            "installationId": f"{mid}::{pid}",
            "owner": "enemy",
            "highValue": True,
        }
        rec["status"] = "destroyed"
        rec["destroyedAt"] = utc_now()
        rec["highValue"] = True
        map_held[pid] = rec
    for pid, rec in list(map_held.items()):
        if not isinstance(rec, dict):
            continue
        if pid in dead_hv:
            continue
        if pid not in standing_pockets and str(rec.get("status") or "") == "standing":
            # Still believed standing if we simply weren't on that pad this sortie.
            pass
    return {"kept": kept, "mapId": mid, "destroyedHv": sorted(dead_hv)}


def apply_abstract_regrow(state: Dict[str, Any], map_id: str, elapsed_minutes: float) -> Dict[str, Any]:
    """Partial heal of shell scars between sorties (campaign-time regrow pressure).

    Capture holds under live regrow; offline, scars slowly recover so re-entry
    is not permanent empty grass. Delegates to capture_node_claims when present.
    """
    try:

        return cnc.apply_abstract_regrow(state, map_id, elapsed_minutes)
    except Exception:
        # Lightweight inline fallback (same shape).
        mid = canonical_map_id(map_id)
        if not mid or elapsed_minutes <= 0:
            return {"regrown": 0, "mapId": mid}
        hours = float(elapsed_minutes) / 60.0
        heal = min(0.85, 0.12 * hours)
        ledger = (state.get("shellScars") or {}).get(mid) or {}
        by_zone = ledger.get("byZone") or {}
        n = 0
        for zid, z in list(by_zone.items()):
            if not isinstance(z, dict):
                continue
            dmg = float(z.get("damageSum") or 0.0)
            if dmg <= 0:
                continue
            z["damageSum"] = round(max(0.0, dmg * (1.0 - heal)), 4)
            dc = int(z.get("destroyedCount") or 0)
            z["destroyedCount"] = max(0, int(round(dc * (1.0 - heal * 0.5))))
            n += 1
            zm = (state.get("zoneMemory") or {}).get(mid, {}).get(zid)
            if isinstance(zm, dict):
                absr = zm.setdefault("abstract", {})
                scar = float(absr.get("shellScar") or 0.0)
                absr["shellScar"] = round(max(0.0, scar * (1.0 - heal)), 4)
                absr["regrowPressure"] = round(min(1.0, heal + scar * 0.3), 4)
        return {"regrown": n, "mapId": mid, "heal": round(heal, 4)}


__all__ = [
    "_CENTER_SNAP_OFFSETS",
    "_CENTER_SNAP_TOL",
    "_authored_map_size",
    "_center_snap_hit",
    "_is_center_snap_artifact",
    "_is_hv_unit_def",
    "apply_abstract_regrow",
    "apply_player_footprint",
    "apply_shell_scars",
    "apply_surviving_installs",
]
