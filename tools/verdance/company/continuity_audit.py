#!/usr/bin/env python3
"""Continuity Membrane Inspector (Phase 0).

Diffs three layers of the in↔out seam so discontinuous / "magic" rebakes
are measurable before Universal Architect owns reinduction:

  WITNESS  — campaign_state scars/claims + last VA result
  BELIEF   — fieldPool homes, marks/attention, zoneMemory stacks, belief scores
  REINDUCE — compiled mission livingShell + fieldRecruits

Exit codes:
  0 = clean (no high/medium findings)
  1 = medium findings (continuity smell)
  2 = high findings (would have felt like magic in play)
  3 = missing inputs / hard failure
"""
from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple

from verdance.common import load_json, utc_now

from verdance.company import company as company

ASHWALKER_ALIASES = frozenset({"ashwalkers", "nullmercs", "legion"})
HV_DEF_TOKENS = ("fus", "fusion", "afus", "cafus")
# Beamers sit on fusion vaults in GF templates; destroy-ledger often records
# them without the fusion maker. Treat as HV-adjacent for *audit* (not bake).
HV_ADJACENT_TOKENS = ("beamer", "annihilator", "anni")


@dataclass
class Finding:
    severity: str  # high | medium | low | info
    code: str
    message: str
    mapId: Optional[str] = None
    zoneId: Optional[str] = None
    pocketId: Optional[str] = None
    heroId: Optional[str] = None
    evidence: Dict[str, Any] = field(default_factory=dict)


def mission_base(mission: Dict[str, Any]) -> Dict[str, Any]:
    mb = mission.get("missionBase")
    if isinstance(mb, dict):
        return mb
    return mission if isinstance(mission, dict) else {}


def _map_id_from_value(value: Any) -> Optional[str]:
    """Accept a bare map id string or a {id|mapId: ...} map object."""
    if isinstance(value, str) and value.strip():
        return value.strip()
    if isinstance(value, dict):
        for key in ("id", "mapId"):
            v = value.get(key)
            if isinstance(v, str) and v.strip():
                return v.strip()
    return None


def resolve_map_id(
    state: Dict[str, Any],
    result: Dict[str, Any],
    mission: Dict[str, Any],
    override: Optional[str] = None,
) -> str:
    """Prefer the *sortie* map (mission / result) over session home.

    Playable packets often stash the map at mission.map.id and
    missionBase.deploymentMapId while leaving missionBase.mapId empty.
    Falling through to sessionHomeMap (e.g. the_rock_jungle camp) while
    auditing a greenest_fields livingShell caused cross-map false positives
    like fusion_witness_gap (TRJ scars vs GF fusion vaults).
    """
    if override:
        return str(override)
    mb = mission_base(mission)
    ls = mb.get("livingShell") if isinstance(mb.get("livingShell"), dict) else {}
    for candidate in (
        result.get("mapId"),
        result.get("deploymentMapId"),
        mb.get("mapId"),
        mb.get("deploymentMapId"),
        mb.get("map"),
        mission.get("mapId"),
        mission.get("map"),
        ls.get("mapId"),
        state.get("currentMapId"),
        state.get("sessionHomeMap"),
    ):
        mid = _map_id_from_value(candidate)
        if mid:
            return mid
    return ""


def marked_zone_ids(
    result: Dict[str, Any],
    mission: Dict[str, Any],
    extra: Optional[Sequence[str]] = None,
) -> List[str]:
    """Player-attention marks only (hub / Drop target) — not bake remaps.

    Living-shell requested/primary and storyIntent secondary targets are
    derived structure, not attention collapse. Mixing them in caused false
    recruit_mark_miss findings for every scarred pad on the map.
    """
    mb = mission_base(mission)
    out: List[str] = []
    seen: Set[str] = set()

    def add(z: Any) -> None:
        s = str(z or "").strip()
        if s and s not in seen:
            seen.add(s)
            out.append(s)

    # Explicit CLI / hub mark lists win.
    if extra:
        for z in extra:
            add(z)

    for src in (result, mb, mission):
        if not isinstance(src, dict):
            continue
        for key in ("markedZoneIds", "targetZoneIds", "markedZones", "hubMarkedZoneIds"):
            raw = src.get(key)
            if isinstance(raw, list):
                for z in raw:
                    add(z)

    # Sortie attention: where the player aimed / dropped.
    if isinstance(result, dict):
        for key in ("targetZoneId", "deploymentZoneId"):
            add(result.get(key))
    if isinstance(mb, dict):
        add(mb.get("targetZoneId"))
        obj = mb.get("objective")
        if isinstance(obj, dict):
            add(obj.get("targetZoneId"))
        # Hub seal often stamps chosen target here without a list.
        sortie = mb.get("sortie") if isinstance(mb.get("sortie"), dict) else {}
        add(sortie.get("targetZoneId"))

    return out


def is_hv_unit_def(def_name: str, *, adjacent: bool = False) -> bool:
    n = str(def_name or "").lower()
    if not n:
        return False
    tokens = HV_DEF_TOKENS + (HV_ADJACENT_TOKENS if adjacent else ())
    return any(tok in n for tok in tokens)


def scarred_zone_set(state: Dict[str, Any], map_id: str) -> Dict[str, Dict[str, Any]]:
    """Python twin of build_next_mission_v1.ps1 Get-ScarredZoneSet."""
    mid = str(map_id or "")
    scarred: Dict[str, Dict[str, Any]] = {}
    if not mid:
        return scarred

    claimed = (state.get("claimedNodes") or {}).get(mid) or {}
    if isinstance(claimed, dict):
        for zid, rec in claimed.items():
            if not isinstance(rec, dict):
                continue
            if rec.get("pocketCleared") or rec.get("nodeClaimed"):
                scarred[str(zid)] = {"reason": "claimed", "scar": 1.0}

    zm = (state.get("zoneMemory") or {}).get(mid) or {}
    if isinstance(zm, dict):
        for zid, mem in zm.items():
            if not isinstance(mem, dict):
                continue
            ctrl = str(mem.get("controllingFaction") or "")
            absr = mem.get("abstract") if isinstance(mem.get("abstract"), dict) else {}
            try:
                scar = float(absr.get("shellScar") or 0.0)
            except (TypeError, ValueError):
                scar = 0.0
            if ctrl.lower() in ASHWALKER_ALIASES or scar >= 0.25:
                z = str(zid)
                if z not in scarred:
                    reason = "player_bloc" if ctrl.lower() in ASHWALKER_ALIASES else "shell_scar"
                    scarred[z] = {"reason": reason, "scar": max(scar, 0.25)}

    bucket = (state.get("shellScars") or {}).get(mid) or {}
    by_zone = bucket.get("byZone") if isinstance(bucket, dict) else None
    if isinstance(by_zone, dict):
        for zid, z in by_zone.items():
            if not isinstance(z, dict):
                continue
            destroyed = int(z.get("destroyedCount") or 0)
            # Twin of Get-ScarredZoneSet: ambient thin only. Exact unitDef|pocket
            # suppress is scar_suppress_set() / Get-ScarSuppressSet.
            if destroyed >= 3:
                scarred[str(zid)] = {
                    "reason": "destroyed_ledger",
                    "scar": min(1.0, 0.2 * destroyed),
                    "destroyedCount": destroyed,
                }
    return scarred


def scar_suppress_set(state: Dict[str, Any], map_id: str) -> Dict[str, bool]:
    """Python twin of Get-ScarSuppressSet — exact unitDef|pocket (or |zone) keys."""
    mid = str(map_id or "")
    out: Dict[str, bool] = {}
    if not mid:
        return out
    bucket = (state.get("shellScars") or {}).get(mid) or {}
    units = bucket.get("units") if isinstance(bucket, dict) else None
    if not isinstance(units, list):
        return out
    for rec in units:
        if not isinstance(rec, dict):
            continue
        if rec.get("destroyed") is False:
            continue
        def_name = str(rec.get("unitDefName") or "").strip().lower()
        if not def_name:
            continue
        pocket = str(rec.get("pocketId") or "").strip()
        zone = str(rec.get("zoneId") or "").strip()
        if pocket:
            out[f"{def_name}|{pocket}"] = True
        elif zone:
            out[f"{def_name}|{zone}"] = True
    return out


def destroyed_hv_pockets(
    state: Dict[str, Any],
    map_id: str,
    *,
    adjacent: bool = False,
) -> Dict[str, Dict[str, Any]]:
    """Python twin of Get-DestroyedHighValuePockets (+ optional beamer adjacency)."""
    mid = str(map_id or "")
    dead: Dict[str, Dict[str, Any]] = {}
    if not mid:
        return dead
    bucket = (state.get("shellScars") or {}).get(mid) or {}
    units = bucket.get("units") if isinstance(bucket, dict) else None
    if isinstance(units, list):
        for rec in units:
            if not isinstance(rec, dict):
                continue
            if rec.get("destroyed") is False:
                continue
            defn = str(rec.get("unitDefName") or "")
            if not is_hv_unit_def(defn, adjacent=adjacent):
                continue
            pid = str(rec.get("pocketId") or "")
            if not pid:
                continue
            dead[pid] = {
                "unitDefName": defn,
                "zoneId": rec.get("zoneId"),
                "adjacentMatch": is_hv_unit_def(defn, adjacent=True)
                and not is_hv_unit_def(defn, adjacent=False),
            }
    held = (state.get("heldInstallations") or {}).get(mid) or {}
    if isinstance(held, dict):
        for key, rec in held.items():
            if not isinstance(rec, dict):
                continue
            if str(rec.get("status") or "") != "destroyed":
                continue
            pid = str(rec.get("pocketId") or key)
            if pid:
                dead[pid] = {"unitDefName": rec.get("unitDefName"), "zoneId": rec.get("zoneId"), "source": "heldInstallations"}
    return dead


def living_shell_hv_pockets(mission: Dict[str, Any]) -> List[Dict[str, Any]]:
    mb = mission_base(mission)
    ls = mb.get("livingShell") if isinstance(mb.get("livingShell"), dict) else {}
    pockets = ls.get("pockets") if isinstance(ls, dict) else None
    out: List[Dict[str, Any]] = []
    if not isinstance(pockets, list):
        return out
    for pk in pockets:
        if not isinstance(pk, dict):
            continue
        kind = str(pk.get("kind") or "")
        optional = bool(pk.get("optionalTarget") or pk.get("highValue") or kind == "fusion_fort")
        if not optional and kind != "fusion_fort":
            continue
        out.append(
            {
                "pocketId": str(pk.get("pocketId") or ""),
                "zoneId": str(pk.get("zoneId") or ""),
                "kind": kind,
                "scarred": bool(pk.get("scarred")),
                "optionalTarget": bool(pk.get("optionalTarget")),
                "highValue": bool(pk.get("highValue")),
            }
        )
    return out


def living_shell_hv_units(mission: Dict[str, Any]) -> List[Dict[str, Any]]:
    mb = mission_base(mission)
    ls = mb.get("livingShell") if isinstance(mb.get("livingShell"), dict) else {}
    units = ls.get("units") if isinstance(ls, dict) else None
    out: List[Dict[str, Any]] = []
    if not isinstance(units, list):
        return out
    for u in units:
        if not isinstance(u, dict):
            continue
        defn = str(u.get("unitDef") or u.get("unitDefName") or "")
        pocket = str(u.get("pocketId") or "")
        if is_hv_unit_def(defn, adjacent=True) or u.get("highValue") or u.get("optionalTarget"):
            out.append(
                {
                    "pocketId": pocket,
                    "zoneId": u.get("zoneId"),
                    "unitDef": defn,
                }
            )
    return out


def field_recruits_from_mission(mission: Dict[str, Any]) -> List[Dict[str, Any]]:
    mb = mission_base(mission)
    raw = mb.get("fieldRecruits") or mission.get("fieldRecruits") or []
    if not isinstance(raw, list):
        return []
    return [r for r in raw if isinstance(r, dict)]


def audit_field_recruits(
    state: Dict[str, Any],
    mission: Dict[str, Any],
    map_id: str,
    marks: Sequence[str],
    *,
    workspace: Optional[Path] = None,
    limit: int = 2,
) -> Tuple[List[Finding], Dict[str, Any]]:
    findings: List[Finding] = []
    expected = company.field_recruits_for_map(
        state,
        map_id,
        workspace=workspace,
        limit=limit,
        marked_zone_ids=list(marks),
    )
    actual = field_recruits_from_mission(mission)
    exp_ids = [str(r.get("heroId") or "") for r in expected]
    act_ids = [str(r.get("heroId") or r.get("id") or "") for r in actual]
    act_by_id = {str(r.get("heroId") or r.get("id") or ""): r for r in actual}

    detail = {
        "marks": list(marks),
        "expected": expected,
        "actual": actual,
        "expectedIds": exp_ids,
        "actualIds": act_ids,
    }

    # Attention collapse: any belief-ranked expected hero whose home is marked
    # must appear in the bake (cap already applied in expected).
    exp_by_id = {str(r.get("heroId") or ""): r for r in expected}
    for hid in exp_ids:
        erow = exp_by_id.get(hid) or {}
        zone = str(erow.get("zoneId") or "")
        mode = str(erow.get("recruitMode") or "wreck_rez")
        row = act_by_id.get(hid)
        if zone and zone in marks and not row:
            findings.append(
                Finding(
                    severity="high",
                    code="recruit_mark_miss",
                    message=(
                        f"Marked zone {zone} collapsed belief onto {hid}, but mission "
                        f"fieldRecruits omitted them (cap/rank/magic gap)."
                    ),
                    mapId=map_id,
                    zoneId=zone,
                    heroId=hid,
                    evidence={"expectedTop": exp_ids, "actual": act_ids, "recruitMode": mode},
                )
            )
            continue
        if not row:
            continue
        if mode in ("wreck_rez", "retrieve_stash") and row.get("spawnAsWreck") is False:
            findings.append(
                Finding(
                    severity="high",
                    code="recruit_live_poof",
                    message=f"{hid} is {mode} but spawnAsWreck is false — would poof live.",
                    mapId=map_id,
                    zoneId=zone or None,
                    heroId=hid,
                    evidence={"row": row},
                )
            )
        elif mode in ("wreck_rez", "retrieve_stash") and row.get("spawnAsWreck") is not True:
            findings.append(
                Finding(
                    severity="medium",
                    code="recruit_wreck_unspecified",
                    message=f"{hid} {mode} row lacks spawnAsWreck=true.",
                    mapId=map_id,
                    zoneId=zone or None,
                    heroId=hid,
                    evidence={"row": row},
                )
            )

    # Also flag baked wreck-rez rows that forgot spawnAsWreck even if ranking drifted.
    for hid, row in act_by_id.items():
        mode = str(row.get("recruitMode") or row.get("type") or "")
        if mode in ("wreck_rez", "retrieve_stash") and row.get("spawnAsWreck") is False:
            if not any(f.heroId == hid and f.code == "recruit_live_poof" for f in findings):
                findings.append(
                    Finding(
                        severity="high",
                        code="recruit_live_poof",
                        message=f"{hid} is {mode} but spawnAsWreck is false — would poof live.",
                        mapId=map_id,
                        zoneId=str(row.get("zoneId") or "") or None,
                        heroId=hid,
                        evidence={"row": row},
                    )
                )

    if exp_ids and act_ids and set(exp_ids) != set(act_ids):
        # Marked hero in expected but missing from bake is already high via recruit_mark_miss.
        only_rank = not any(f.code == "recruit_mark_miss" for f in findings)
        findings.append(
            Finding(
                severity="medium" if marks and only_rank else ("low" if not marks else "medium"),
                code="recruit_rank_drift",
                message=f"Belief-ranked recruits {exp_ids} != baked {act_ids}.",
                mapId=map_id,
                evidence=detail,
            )
        )
    elif not act_ids and any(
        str((e.get("recruit") or {}).get("mapId") or ((e.get("home") or [None])[0] if isinstance(e.get("home"), list) else None) or "")
        == map_id
        for e in (state.get("fieldPool") or {}).values()
        if isinstance(e, dict) and str(e.get("status") or "") == "wild"
    ):
        findings.append(
            Finding(
                severity="medium",
                code="recruit_empty_bake",
                message="Wild fieldPool heroes exist on this map but mission has no fieldRecruits.",
                mapId=map_id,
                evidence=detail,
            )
        )

    return findings, detail


def audit_fusion_continuity(
    state: Dict[str, Any],
    mission: Dict[str, Any],
    map_id: str,
) -> Tuple[List[Finding], Dict[str, Any]]:
    findings: List[Finding] = []
    bake_dead = destroyed_hv_pockets(state, map_id, adjacent=False)
    audit_dead = destroyed_hv_pockets(state, map_id, adjacent=True)
    hv_pockets = living_shell_hv_pockets(mission)
    hv_units = living_shell_hv_units(mission)
    present_pids = {p["pocketId"] for p in hv_pockets if p.get("pocketId")}
    unit_pids = {u["pocketId"] for u in hv_units if u.get("pocketId")}

    detail = {
        "bakeDestroyedHvPockets": bake_dead,
        "auditDestroyedHvPocketsAdjacent": audit_dead,
        "livingShellHvPockets": hv_pockets,
        "livingShellHvUnitCount": len(hv_units),
        "livingShellHvUnitPockets": sorted(unit_pids),
    }

    for pid, meta in bake_dead.items():
        if pid in unit_pids or pid in present_pids:
            # Present in shell listing; check units actually spawn.
            if pid in unit_pids:
                findings.append(
                    Finding(
                        severity="high",
                        code="fusion_regen_despite_hv_scar",
                        message=(
                            f"HV pocket {pid} has destroyed fusion scar evidence but "
                            f"livingShell still spawns HV units there."
                        ),
                        mapId=map_id,
                        pocketId=pid,
                        zoneId=str(meta.get("zoneId") or "") or None,
                        evidence={"scar": meta, "hvUnitsOnPocket": [u for u in hv_units if u.get("pocketId") == pid]},
                    )
                )

    for pid, meta in audit_dead.items():
        if pid in bake_dead:
            continue
        if pid in unit_pids:
            findings.append(
                Finding(
                    severity="high",
                    code="fusion_regen_beamer_scar_ignored",
                    message=(
                        f"HV-adjacent destroys (e.g. beamer) recorded on pocket {pid}, but "
                        f"bake only suppresses on fusion-maker defs — vault reinduced."
                    ),
                    mapId=map_id,
                    pocketId=pid,
                    zoneId=str(meta.get("zoneId") or "") or None,
                    evidence={"scar": meta, "bakeUsesFusionMakerOnly": True},
                )
            )

    # Witness gap: fusion fully present, zero HV scars on map, but player scarred nearby combat.
    scarred = scarred_zone_set(state, map_id)
    if not hv_units and bake_dead:
        findings.append(
            Finding(
                severity="info",
                code="fusion_suppressed_ok",
                message="Destroyed HV pockets suppressed — no fusion units in livingShell.",
                mapId=map_id,
                evidence={"destroyedHv": sorted(bake_dead.keys())},
            )
        )
    if hv_units and not bake_dead and not audit_dead:
        fus_zones = {str(p.get("zoneId") or "") for p in hv_pockets if p.get("zoneId")}
        nearby = sorted(z for z in scarred if z and z not in fus_zones)
        if nearby:
            findings.append(
                Finding(
                    severity="medium",
                    code="fusion_witness_gap",
                    message=(
                        "Fusion/beamer vaults fully reinduced while combat scars exist on "
                        "other pads and no HV unit scars were stored — cleaned vaults can "
                        "poof back (witness→store gap)."
                    ),
                    mapId=map_id,
                    evidence={
                        "scarredCombatZones": nearby,
                        "fusionZones": sorted(fus_zones),
                        "hvUnitCount": len(hv_units),
                    },
                )
            )
        elif hv_units:
            findings.append(
                Finding(
                    severity="info",
                    code="fusion_present_no_hv_scar",
                    message="Optional fusion vaults present; no HV destroy ledger entries (fresh or unwitnessed).",
                    mapId=map_id,
                    evidence=detail,
                )
            )

    for p in hv_pockets:
        if p.get("scarred") and p.get("pocketId") in unit_pids:
            findings.append(
                Finding(
                    severity="medium",
                    code="fusion_scarred_flag_but_spawned",
                    message=(
                        f"Pocket {p.get('pocketId')} marked scarred=true in livingShell "
                        f"meta but HV units still listed."
                    ),
                    mapId=map_id,
                    pocketId=p.get("pocketId"),
                    zoneId=p.get("zoneId"),
                    evidence={"pocket": p},
                )
            )

    return findings, detail


def audit_zone_remap(mission: Dict[str, Any], marks: Sequence[str]) -> Tuple[List[Finding], Dict[str, Any]]:
    findings: List[Finding] = []
    mb = mission_base(mission)
    ls = mb.get("livingShell") if isinstance(mb.get("livingShell"), dict) else {}
    requested = str(ls.get("requestedZoneId") or "")
    primary = str(ls.get("primaryZoneId") or "")
    detail = {"requestedZoneId": requested, "primaryZoneId": primary, "marks": list(marks)}
    if requested and primary and requested != primary:
        sev = "high" if requested in marks else "medium"
        findings.append(
            Finding(
                severity=sev,
                code="objective_zone_remap",
                message=(
                    f"Living shell remapped objective {requested} → {primary}. "
                    f"Quiet-rim / hero pads with no shell pocket lose sortie fiction."
                ),
                zoneId=requested,
                evidence=detail,
            )
        )
    # Attention pad abandoned when the raid pocket (primary) is elsewhere.
    # Ignore deploy/muster/extract marks — those are logistics, not hero fiction.
    # Do NOT ignore `requested`: a remapped requested hero pad is exactly the bug.
    ignore_suffixes = ("_MUSTER", "_START", "_EXTRACT", "_RIM", "_SHELF")
    ignore_exact: Set[str] = set()
    mb = mission_base(mission)
    for key in ("deploymentZoneId", "extractionZoneId"):
        v = str(mb.get(key) or "")
        if v:
            ignore_exact.add(v)
    if primary:
        for z in marks:
            if not z or z == primary or z in ignore_exact:
                continue
            if any(z.endswith(suf) for suf in ignore_suffixes):
                continue
            findings.append(
                Finding(
                    severity="high",
                    code="attention_zone_abandoned",
                    message=(
                        f"Attention mark {z} is not the livingShell primary {primary} "
                        f"(requested {requested or '—'}). Hero wreck fiction on that "
                        f"pad can desync from the raid pocket."
                    ),
                    zoneId=z,
                    evidence=detail,
                )
            )
    return findings, detail


def audit_result_witness(
    result: Dict[str, Any],
    state: Dict[str, Any],
    map_id: str,
) -> Tuple[List[Finding], Dict[str, Any]]:
    findings: List[Finding] = []
    raw_scars = result.get("shellScars")
    detail = {
        "resultShellScarsType": type(raw_scars).__name__,
        "resultDestroyedObjectiveIds": result.get("destroyedObjectiveIds"),
        "resultRecruitedHeroIds": result.get("recruitedHeroIds"),
        "resultTargetZoneId": result.get("targetZoneId") or result.get("deploymentZoneId"),
        "resultNodeClaimed": result.get("nodeClaimed"),
        "resultPocketCleared": result.get("pocketCleared"),
    }
    empty_scars = raw_scars in (None, [], {}, "")
    state_units = ((state.get("shellScars") or {}).get(map_id) or {}).get("units") or []
    if empty_scars and isinstance(state_units, list) and len(state_units) == 0:
        # Neither result nor state has scars — fine for a scrubbed raid.
        findings.append(
            Finding(
                severity="info",
                code="witness_no_scars",
                message="Last result and state carry no shellScar units for this map.",
                mapId=map_id,
                evidence=detail,
            )
        )
    elif empty_scars and isinstance(state_units, list) and len(state_units) > 0:
        findings.append(
            Finding(
                severity="low",
                code="result_scar_payload_empty",
                message=(
                    "latest_va_result.shellScars is empty while campaign_state still holds "
                    "scar units — extract may have dropped the witness payload."
                ),
                mapId=map_id,
                evidence={**detail, "stateScarUnitCount": len(state_units)},
            )
        )
    return findings, detail


def audit_player_footprint(
    state: Dict[str, Any],
    mission: Dict[str, Any],
    map_id: str,
) -> Tuple[List[Finding], Dict[str, Any]]:
    """Company pads in state must land on the compiled livingShell (or be empty)."""
    findings: List[Finding] = []
    bag = ((state.get("playerFootprints") or {}).get(map_id) or {})
    units = bag.get("units") if isinstance(bag, dict) else None
    n_state = len(units) if isinstance(units, list) else 0
    shell = (mission or {}).get("livingShell") or {}
    shell_units = shell.get("units") if isinstance(shell, dict) else None
    fp_on_shell = 0
    if isinstance(shell_units, list):
        for u in shell_units:
            if not isinstance(u, dict):
                continue
            role = str(u.get("forceRole") or u.get("role") or "")
            if role == "player_footprint" or u.get("heldByPlayer") in (True, 1, "1"):
                # Count only explicit footprint rows (held HV is a different SoT).
                if role == "player_footprint":
                    fp_on_shell += 1
    detail = {
        "stateFootprintUnits": n_state,
        "shellFootprintUnits": fp_on_shell,
        "shellEnabled": bool(isinstance(shell, dict) and shell.get("enabled")),
        "shellUnitCount": len(shell_units) if isinstance(shell_units, list) else 0,
    }
    if n_state > 0 and fp_on_shell == 0:
        findings.append(
            Finding(
                severity="high",
                code="footprint_missing_from_shell",
                message=(
                    f"campaign_state.playerFootprints[{map_id}] has {n_state} units but "
                    "compiled livingShell has no forceRole=player_footprint rows — "
                    "Merge-PlayerFootprintIntoShell / Ensure-PlayerFootprintShell missed."
                ),
                mapId=map_id,
                evidence=detail,
            )
        )
    elif n_state > 0 and fp_on_shell < n_state:
        findings.append(
            Finding(
                severity="medium",
                code="footprint_partial_on_shell",
                message=(
                    f"Footprint bag has {n_state} units; shell only rehydrates {fp_on_shell} "
                    "(cap 64 or merge truncation)."
                ),
                mapId=map_id,
                evidence=detail,
            )
        )
    elif n_state == 0:
        findings.append(
            Finding(
                severity="info",
                code="footprint_empty",
                message="No playerFootprints bag for this map (expected on first Drop).",
                mapId=map_id,
                evidence=detail,
            )
        )
    return findings, detail


def run_audit(
    workspace: Path,
    *,
    state: Optional[Dict[str, Any]] = None,
    result: Optional[Dict[str, Any]] = None,
    mission: Optional[Dict[str, Any]] = None,
    map_id: Optional[str] = None,
    marked: Optional[Sequence[str]] = None,
    recruit_limit: int = 2,
) -> Dict[str, Any]:
    ws = workspace.resolve()
    state = state if state is not None else load_json(ws / "state" / "campaign_state.json", {})
    result = result if result is not None else load_json(ws / "inbox" / "latest_va_result.json", {})
    mission = (
        mission
        if mission is not None
        else load_json(ws / "data" / "scenarios" / "generated" / "next_mission_intent.playable.json", {})
    )
    mid = resolve_map_id(state, result, mission, map_id)
    marks = marked_zone_ids(result, mission, marked)

    findings: List[Finding] = []
    sections: Dict[str, Any] = {"mapId": mid, "marks": marks}

    if not mid:
        findings.append(
            Finding(
                severity="high",
                code="missing_map_id",
                message="Could not resolve mapId from state/result/mission.",
            )
        )
    else:
        f1, d1 = audit_result_witness(result, state, mid)
        findings.extend(f1)
        sections["witness"] = d1

        sections["scarredZones"] = scarred_zone_set(state, mid)

        f2, d2 = audit_field_recruits(
            state, mission, mid, marks, workspace=ws, limit=recruit_limit
        )
        findings.extend(f2)
        sections["fieldRecruits"] = d2

        f3, d3 = audit_fusion_continuity(state, mission, mid)
        findings.extend(f3)
        sections["fusion"] = d3

        f4, d4 = audit_zone_remap(mission, marks)
        findings.extend(f4)
        sections["zoneRemap"] = d4

        f5, d5 = audit_player_footprint(state, mission or {}, mid)
        findings.extend(f5)
        sections["playerFootprint"] = d5

    # Severity rollup
    counts = {"high": 0, "medium": 0, "low": 0, "info": 0}
    for f in findings:
        counts[f.severity] = counts.get(f.severity, 0) + 1

    if counts["high"]:
        exit_hint = 2
        verdict = "broken"
    elif counts["medium"]:
        exit_hint = 1
        verdict = "smelly"
    else:
        exit_hint = 0
        verdict = "continuous"

    return {
        "ok": True,
        "at": utc_now(),
        "workspace": str(ws),
        "verdict": verdict,
        "exitHint": exit_hint,
        "counts": counts,
        "findings": [asdict(f) for f in findings],
        "sections": sections,
        "laws": [
            "High-η witness beats low-η template.",
            "Marks collapse recruit ranking; they do not invent structure.",
            "Wreck-rez must spawnAsWreck.",
            "Fusion vaults suppress only when HV destroy evidence exists (today: fusion-maker defs only).",
        ],
    }


def write_outbox(ws: Path, report: Dict[str, Any]) -> Path:
    out_dir = ws / "outbox"
    out_dir.mkdir(parents=True, exist_ok=True)
    latest = out_dir / "continuity_audit.latest.json"
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    stamped = out_dir / f"continuity_audit_{stamp}.json"
    text = json.dumps(report, indent=2) + "\n"
    latest.write_text(text, encoding="utf-8")
    stamped.write_text(text, encoding="utf-8")
    return latest


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="Verdance continuity membrane inspector")
    ap.add_argument("--workspace", default=".")
    ap.add_argument("--state", default="state/campaign_state.json")
    ap.add_argument("--result", default="inbox/latest_va_result.json")
    ap.add_argument(
        "--mission",
        default="data/scenarios/generated/next_mission_intent.playable.json",
    )
    ap.add_argument("--map-id", default=None)
    ap.add_argument("--mark", action="append", default=[], help="Extra marked zone id (repeatable)")
    ap.add_argument("--recruit-limit", type=int, default=2)
    ap.add_argument("--write-outbox", action="store_true")
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args(list(argv) if argv is not None else None)

    ws = Path(args.workspace).resolve()
    report = run_audit(
        ws,
        state=load_json(ws / args.state, {}),
        result=load_json(ws / args.result, {}),
        mission=load_json(ws / args.mission, {}),
        map_id=args.map_id,
        marked=args.mark,
        recruit_limit=args.recruit_limit,
    )
    if args.write_outbox:
        path = write_outbox(ws, report)
        report["outbox"] = str(path)

    if not args.quiet:
        print(json.dumps(report, indent=2))
    else:
        print(report.get("verdict"), report.get("counts"))

    return int(report.get("exitHint") or 0)


if __name__ == "__main__":
    raise SystemExit(main())
