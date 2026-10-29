#!/usr/bin/env python3
"""Capture = claim a living shell node (clear pocket + hold under regrow).

Phase D kernel for pkt-bar-capture-node-claims.

Rules
-----
- Capture is **not** empty-grass stand. Pocket must be cleared (shell eco/teeth
  wrecked to CLEAR_FRACTION), then held while regrow pressure pulses.
- Zone flip / hub claim only when ``nodeClaimed`` (clear+hold finished).
- Capture never pays Tenebrium; the company's metal comes home in storage (commerce.py).
- Occupation model remains ``living_shell`` (one model, seven shells).

Surfaces
--------
- Match gadget: ``mod/.../game_verdance_campaign.lua`` (clear → hold → claimed)
- Hub contract: sortie stamps ``captureMode=clear_hold_shell`` for CAPTURE_KINDS
- Campaign advance: ``apply_node_claim`` + commerce settle hook
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from verdance.common import WORKSPACE_ROOT, load_json, utc_now
from verdance.world.offscreen_clash import PLAYER_IMPACT
from verdance.company import quest_generator as qg
from verdance.belief import hub_belief

# Presence / capture objective kinds — claim living shell node, not grass.
CAPTURE_KINDS = frozenset({"seize_lane", "gate_control", "hold_plateau"})
CAPTURE_MODE = "clear_hold_shell"
OCCUPATION_MODEL = "living_shell"
CLEAR_FRACTION = 0.6  # must match gadget CLEAR_FRACTION
HOLD_FRAMES_DEFAULT = 900  # 30s @ 30fps

# The player's own strength when a claim seeds a zone's abstract stats --
# scaled by PLAYER_IMPACT (offscreen_clash_v1) and, during the regression
# window, by claim_rate_mult below. There is no continuous claim/spill rate
# live, so "the player is bigger than modelled" and "the claim presses
# harder once the raid-to-factories transition closes" both have to land
# here, on the one real claim event, rather than as a rate.
BASE_CLAIM_STRENGTH = 0.25


def claim_rate_mult(mission_number: int) -> float:
    """The other half of the player's regression arc: claims sag during the
    raid-to-factories transition and press harder than baseline once it
    closes -- the live analog of the offline tool's PLAYER_ARC.claim_mult."""
    try:
        from verdance.campaign import REGRESSION_START, REGRESSION_END
    except Exception:
        REGRESSION_START, REGRESSION_END = 4, 6
    if REGRESSION_START <= mission_number <= REGRESSION_END:
        return 0.5
    if mission_number > REGRESSION_END:
        return 1.25
    return 1.0


def _player_impact() -> float:
    try:
        return float(PLAYER_IMPACT)
    except Exception:
        return 2.0  # local fallback, matches offscreen_clash_v1's own default


def is_capture_kind(kind: Any) -> bool:
    return str(kind or "").strip() in CAPTURE_KINDS


def is_capture_result(result: Dict[str, Any]) -> bool:
    """True when this sortie result is on the capture claim path."""
    if not isinstance(result, dict):
        return False
    if result.get("captureMode") is True:
        return True
    mode = result.get("captureMode")
    if mode in (CAPTURE_MODE, "true", "1", 1):
        return True
    phase = str(result.get("capturePhase") or "")
    if phase in ("clear", "hold", "claimed"):
        return True
    if result.get("nodeClaimed") is True or result.get("pocketCleared") is True:
        return True
    kind = (
        result.get("objectiveArchetype")
        or result.get("objectiveKind")
        or result.get("kind")
        or (result.get("objective") if isinstance(result.get("objective"), str) else None)
    )
    return is_capture_kind(kind)



def pocket_cleared(destroyed: int, total: int, fraction: float = CLEAR_FRACTION) -> bool:
    """True when enough shell pocket units are wrecked to enter hold phase."""
    import math

    if total <= 0:
        return True
    need = max(1, int(math.ceil(total * fraction)))
    return int(destroyed) >= need


def hold_complete(hold_frames: int, required: int = HOLD_FRAMES_DEFAULT) -> bool:
    return int(hold_frames) >= int(required)


def capture_phase(
    *,
    destroyed: int,
    total: int,
    hold_frames: int,
    required_hold: int = HOLD_FRAMES_DEFAULT,
    fraction: float = CLEAR_FRACTION,
) -> str:
    """Return clear | hold | claimed for a capture sortie snapshot."""
    if not pocket_cleared(destroyed, total, fraction):
        return "clear"
    if not hold_complete(hold_frames, required_hold):
        return "hold"
    return "claimed"


def node_claim_result(
    *,
    destroyed: int,
    total: int,
    hold_frames: int,
    required_hold: int = HOLD_FRAMES_DEFAULT,
    patron: str = "nullmercs",
    target_zone_id: str = "",
    map_id: str = "",
) -> Dict[str, Any]:
    """Pure claim evaluation — never awards Tnb."""
    phase = capture_phase(
        destroyed=destroyed,
        total=total,
        hold_frames=hold_frames,
        required_hold=required_hold,
    )
    claimed = phase == "claimed"
    return {
        "captureMode": CAPTURE_MODE,
        "capturePhase": phase,
        "pocketCleared": phase in ("hold", "claimed"),
        "nodeClaimed": claimed,
        "zoneFlipped": claimed,
        "targetZoneId": target_zone_id,
        "mapId": map_id,
        "patron": patron,
        "tenebriumFromClaim": 0,
        "clearFraction": CLEAR_FRACTION,
        "holdFrames": hold_frames,
        "requiredHoldFrames": required_hold,
    }


def node_claim_complete(result: Dict[str, Any]) -> bool:
    """Clear pocket + hold finished → node claimed."""
    if result.get("nodeClaimed") is True or result.get("nodeClaimed") == 1:
        return True
    if str(result.get("capturePhase") or "") == "claimed":
        return True
    how = str(result.get("objectiveCompleteHow") or result.get("terminalReason") or "")
    return how in ("node_claimed", "zone_held") and bool(result.get("pocketCleared"))


def stamp_sortie_capture(order: Dict[str, Any]) -> Dict[str, Any]:
    """Hub contract: stamp captureMode onto sortie / objective for CAPTURE_KINDS."""
    out = dict(order or {})
    arch = (
        out.get("objectiveArchetype")
        or out.get("kind")
        or out.get("objective")
        or out.get("contractKind")
    )
    caps = list(out.get("captureZoneIds") or [])
    target = out.get("targetZoneId")
    if not caps and target:
        caps = [str(target)]
        out["captureZoneIds"] = caps
    if is_capture_kind(arch) or out.get("captureMode") in (True, CAPTURE_MODE):
        out["captureMode"] = CAPTURE_MODE
        out["occupationModel"] = out.get("occupationModel") or OCCUPATION_MODEL
        out["sessionMode"] = out.get("sessionMode") or "same_map"
        out.setdefault("captureRules", {
            "model": CAPTURE_MODE,
            "clearFraction": CLEAR_FRACTION,
            "holdUnderRegrow": True,
            "emptyGrassClaim": False,
        })
    return out


def stamp_objective_capture(objective: Dict[str, Any], order: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Stamp mission.objective capture fields for compiler / gadget seed."""
    obj = dict(objective or {})
    order = order or {}
    kind = obj.get("kind") or order.get("objectiveArchetype") or order.get("kind")
    if is_capture_kind(kind) or order.get("captureMode") == CAPTURE_MODE:
        zid = obj.get("targetZoneId") or order.get("targetZoneId") or ""
        obj["captureMode"] = CAPTURE_MODE
        obj["kind"] = kind or obj.get("kind")
        obj["description"] = (
            obj.get("description")
            or f"Clear pocket + hold under regrow to claim {zid}"
        )
        obj.setdefault("clearFraction", CLEAR_FRACTION)
        obj.setdefault("requiredHoldFrames", obj.get("requiredHoldFrames") or 600)
    return obj


# Every contract is territory: the company takes a zone (2026-10-27). An empty zone is taken by
# establishing presence there (the compiler turns it into fortify_zone); a zone with something in it
# by clearing it and holding. Whatever the Null Mercs were hired to do there is the reason the zone
# is worth taking; it rides along as contractKind. Rescues are never the job: they are bonus marks.
# Kept as they are: the finales, the Rock Jungle's own home jobs, and ground already being fortified.
KEEP_KINDS = frozenset({"kings_showdown", "jump_gate", "hive_clear_or_bypass", "home_founding",
                        "fortify_zone", "survive_wilds", "seize_lane"})


def as_territory_capture(objective: Dict[str, Any], zone_label: Optional[str] = None) -> Dict[str, Any]:
    """The objective as a capture of its target zone (seize_lane), unless its kind is kept."""
    obj = dict(objective or {})
    kind = str(obj.get("kind") or "")
    zid = obj.get("targetZoneId")
    if not zid or kind in KEEP_KINDS:
        return obj
    from verdance.common import ARCHETYPE_VERB
    label = str(obj.get("label") or "")
    verb = ARCHETYPE_VERB.get(kind)
    if verb and label.startswith(verb + " "):
        label = label[len(verb) + 1:]
    place = zone_label or label or str(zid)
    obj["contractKind"] = kind
    obj["kind"] = "seize_lane"
    obj["label"] = place if place.startswith("Take ") else f"Take {place}"
    obj.pop("description", None)
    return stamp_objective_capture(obj, {"captureMode": CAPTURE_MODE})


def apply_node_claim(
    state: Dict[str, Any],
    result: Dict[str, Any],
    *,
    map_id: Optional[str] = None,
    success: Optional[bool] = None,
) -> Dict[str, Any]:
    """Apply capture claim to campaign state.

    Returns report:
      claimed, zoneFlipped, reason, zoneId, mapId
    """
    mid = str(
        map_id
        or result.get("mapId")
        or result.get("deploymentMapId")
        or ""
    )
    zid = str(
        result.get("targetZoneId")
        or (result.get("objectiveTarget") or {}).get("targetZoneId")
        or ""
    )
    report: Dict[str, Any] = {
        "claimed": False,
        "zoneFlipped": False,
        "reason": "idle",
        "zoneId": zid,
        "mapId": mid,
        "capturePath": is_capture_result(result),
        "pocketCleared": bool(result.get("pocketCleared")),
        "nodeClaimed": bool(result.get("nodeClaimed")),
        "regrowWaves": int(result.get("regrowWaves") or 0),
        "capturePhase": result.get("capturePhase") or "idle",
    }

    if success is None:
        # Credit-table aligned: claim only when nodeClaimed (or explicit success
        # passed by process_result from zoneFlip decision). Partial alone is not enough.
        success = bool(result.get("nodeClaimed")) or (
            result.get("capturePhase") == "claimed"
        ) or (
            result.get("status") in ("victory", "victoryClean")
            and bool(result.get("nodeClaimed"))
        ) or bool(result.get("success") and result.get("nodeClaimed"))

    # Non-capture: do not force claim here (legacy process_result owns flip).
    if not is_capture_result(result):
        report["reason"] = "not_capture_path"
        return report

    if not success:
        report["reason"] = "sortie_not_success"
        return report

    if not node_claim_complete(result):
        report["reason"] = "hold_incomplete_or_empty_grass"
        return report

    if not mid or not zid:
        report["reason"] = "missing_map_or_zone"
        return report

    zm_root = state.setdefault("zoneMemory", {})
    map_zones = zm_root.setdefault(mid, {})
    zone_mem = map_zones.get(zid)
    if not isinstance(zone_mem, dict):
        zone_mem = {
            "zoneId": zid,
            "mapId": mid,
            "controllingFaction": "wild",
            "abstract": {"control": "wild"},
        }
        map_zones[zid] = zone_mem

    patron = result.get("patron") or "nullmercs"
    patron_bloc = "nullmercs" if patron in ("nullmercs", "ashwalkers") else str(patron)
    prev = zone_mem.get("controllingFaction") or (zone_mem.get("abstract") or {}).get("control")
    zone_mem["controllingFaction"] = patron_bloc
    absr = zone_mem.setdefault("abstract", {})
    absr["control"] = patron_bloc
    absr["claimedNode"] = True
    absr["claimMethod"] = CAPTURE_MODE
    absr["shellScar"] = round(min(1.0, float(absr.get("shellScar") or 0.0) + 0.2), 4)
    # When the player takes a zone, they really take it -- seed (never
    # lower) its combat stats so it holds and presses in future offscreen
    # clashes, scaled by how impactful the player is modelled to be and by
    # where they stand in the raid-to-factories transition.
    mission_number = int(state.get("missionNumber", 1) or 1)
    seed = BASE_CLAIM_STRENGTH * _player_impact() * claim_rate_mult(mission_number)
    absr["baseStrength"] = round(max(float(absr.get("baseStrength") or 0.0), seed), 4)
    absr["fortification"] = round(max(float(absr.get("fortification") or 0.0), seed * 0.8), 4)
    zone_mem["lastClaimedAt"] = utc_now()
    zone_mem["lastClaimRegrowWaves"] = int(result.get("regrowWaves") or 0)

    claimed = state.setdefault("claimedNodes", {})
    by_map = claimed.setdefault(mid, {})
    by_map[zid] = {
        "zoneId": zid,
        "mapId": mid,
        "claimedAt": utc_now(),
        "method": CAPTURE_MODE,
        "occupationModel": result.get("occupationModel") or OCCUPATION_MODEL,
        "regrowWaves": int(result.get("regrowWaves") or 0),
        "pocketCleared": True,
        "nodeClaimed": True,
        "patron": patron_bloc,
        "resultKey": result.get("resultKey"),
        "previousControl": prev,
    }
    state["occupationModel"] = OCCUPATION_MODEL
    state.setdefault("sessionMode", result.get("sessionMode") or "same_map")

    report["claimed"] = True
    report["zoneFlipped"] = prev != patron_bloc
    report["reason"] = "node_claimed_clear_hold"
    report["previousControl"] = prev
    report["newControl"] = patron_bloc
    return report


def hub_claim_surface(state: Dict[str, Any], map_id: Optional[str] = None) -> Dict[str, Any]:
    """Projection for hub_state: claimed living-shell nodes (no free Tnb)."""
    claimed = state.get("claimedNodes") or {}
    rows: List[Dict[str, Any]] = []
    for mid, zones in claimed.items():
        if map_id and mid != map_id:
            continue
        if not isinstance(zones, dict):
            continue
        for zid, rec in zones.items():
            if isinstance(rec, dict):
                rows.append({**rec, "mapId": mid, "zoneId": zid})
    # Also fold list-form nodeClaims ledger if present.
    for mid, items in (state.get("nodeClaims") or {}).items():
        if map_id and mid != map_id:
            continue
        if not isinstance(items, list):
            continue
        for rec in items:
            if isinstance(rec, dict):
                rows.append({**rec, "mapId": mid})
    return {
        "occupationModel": state.get("occupationModel") or OCCUPATION_MODEL,
        "captureMode": CAPTURE_MODE,
        "clearFraction": CLEAR_FRACTION,
        "nodes": rows,
        "count": len(rows),
    }


# Believed holders that leave nothing to fight: ours, the Mercs', and ground seen empty (or neutral).
NO_FIGHT_HOLDERS = ("ashwalkers", "nullmercs", "empty", "neutral")


def hub_capture_contracts(
    workspace: Any,
    state: Dict[str, Any],
    limit: int = 6,
    *,
    map_id: Optional[str] = None,
    patron: str = "nullmercs",
    from_zone_ids: Optional[List[str]] = None,
) -> List[Dict[str, Any]]:
    """Hub board contracts: seize/hold living shell nodes (not empty grass).

    PLAYER-FACING (pass 8B): everything here rides into hub_state.json, so who holds a target is the
    company's BELIEF (hub_belief), never zoneMemory.controllingFaction. `against` is the believed
    holder or "unknown"; the engine re-derives the real opponent when it builds the match.

    Prefer quest_generator same_map candidates when available; else a belief scan of known zones.
    Each contract stamps clear_hold_shell for deploy compile.
    """
    from pathlib import Path as _Path

    ws = _Path(workspace) if workspace is not None else None
    contracts: List[Dict[str, Any]] = []

    def _believed(mid: str, zid: str) -> str:
        try:
            rows = hub_belief.belief_surface(ws or WORKSPACE_ROOT, state, mid).get("zones") or {}
            return hub_belief.believed_holder(rows.get(str(zid)))
        except Exception:
            return "unknown"

    def _against_word(holder: str) -> str:
        return holder if holder not in ("ashwalkers", "nullmercs", "neutral", "empty", "unknown", "held") else "unknown"

    # Prefer graph-legal quest candidates (Mode A hub contracts).
    try:

        if ws is not None:
            raw = qg.generate_quests(
                ws,
                state,
                map_id=map_id,
                patron=patron,
                limit=max(limit * 2, 8),
                from_zone_ids=from_zone_ids,
                perspective="belief",
            )
            for c in raw:
                arch = c.get("objectiveArchetype") or "seize_lane"
                # Vivarium: no contract against nobody. Ground the company saw empty, or holds
                # (with the Mercs), offers no fight; dark ground stays open (nobody has looked).
                if _believed(str(c.get("mapId")), str(c.get("targetZoneId"))) in NO_FIGHT_HOLDERS:
                    continue
                c = dict(c)
                c["against"] = _against_word(str(c.get("against") or "unknown"))
                stamped = stamp_sortie_capture(dict(c))
                mode = stamped.get("captureMode") or (
                    CAPTURE_MODE if is_capture_kind(arch) else ("raid_scar" if arch == "eco_raid" else "other")
                )
                contracts.append({
                    "schemaVersion": "verdance-hub-capture-contract/1.0",
                    "contractId": f"capture:{c.get('mapId')}:{c.get('targetZoneId')}",
                    "mapId": c.get("mapId"),
                    "targetZoneId": c.get("targetZoneId"),
                    "fromZoneIds": list(c.get("fromZoneIds") or []),
                    "label": c.get("label") or c.get("targetZoneId"),
                    "objectiveArchetype": arch,
                    "captureMode": mode if mode != "other" else CAPTURE_MODE,
                    "occupationModel": OCCUPATION_MODEL,
                    "sessionMode": "same_map",
                    "clearFraction": CLEAR_FRACTION,
                    "holdUnderRegrow": True,
                    "emptyGrassClaim": False,
                    "score": c.get("score"),
                    "against": c.get("against") or "unknown",
                    "believedHolder": _believed(str(c.get("mapId")), str(c.get("targetZoneId"))),
                    "patron": patron,
                    "sortie": stamped,
                    "source": "capture_node_claims+quest_gen",
                })
            if contracts:
                contracts.sort(
                    key=lambda x: (
                        -float(x.get("score") or 0),
                        x.get("mapId") or "",
                        x.get("targetZoneId") or "",
                    )
                )
                return contracts[:limit]
    except Exception:
        pass

    zm = state.get("zoneMemory") or {}
    # Fallback scan: zoneMemory only NAMES the zones; who holds each is the company's belief.
    # Zones we believe are ours are not targets; dark zones are offered as "unknown".
    for mid, zones in zm.items():
        if map_id and mid != map_id:
            continue
        if not isinstance(zones, dict):
            continue
        for zid, zrec in zones.items():
            if not isinstance(zrec, dict):
                continue
            holder = _believed(str(mid), str(zid))
            if holder in NO_FIGHT_HOLDERS:
                continue
            against = _against_word(holder)
            order = stamp_sortie_capture({
                "mapId": mid,
                "targetZoneId": zid,
                "objectiveArchetype": "seize_lane",
                "patron": patron,
                "against": against,
                "sessionMode": state.get("sessionMode") or "same_map",
                "occupationModel": OCCUPATION_MODEL,
            })
            contracts.append({
                "schemaVersion": "verdance-hub-capture-contract/1.0",
                "contractId": f"capture:{mid}:{zid}",
                "mapId": mid,
                "targetZoneId": zid,
                "label": zrec.get("label") or f"Claim {zid}",
                "objectiveArchetype": "seize_lane",
                "captureMode": CAPTURE_MODE,
                "occupationModel": OCCUPATION_MODEL,
                "clearFraction": CLEAR_FRACTION,
                "holdUnderRegrow": True,
                "emptyGrassClaim": False,
                "against": against,
                "believedHolder": holder,
                "sortie": order,
                "source": "capture_node_claims",
            })
            if len(contracts) >= limit:
                return contracts
    # Fallback: emit a generic capture shell if no enemy zones known.
    if not contracts and ws is not None:
        mid = map_id or "koom_valley"
        contracts.append({
            "schemaVersion": "verdance-hub-capture-contract/1.0",
            "contractId": f"capture:{mid}:KOOM_CENTRAL_FLUID_SCAR",
            "mapId": mid,
            "targetZoneId": "KOOM_CENTRAL_FLUID_SCAR",
            "label": "Claim Central Fluid Scar",
            "objectiveArchetype": "seize_lane",
            "captureMode": CAPTURE_MODE,
            "occupationModel": OCCUPATION_MODEL,
            "clearFraction": CLEAR_FRACTION,
            "holdUnderRegrow": True,
            "emptyGrassClaim": False,
            "sortie": stamp_sortie_capture({
                "mapId": mid,
                "targetZoneId": "KOOM_CENTRAL_FLUID_SCAR",
                "objectiveArchetype": "seize_lane",
            }),
            "source": "capture_node_claims_fallback",
        })
    return contracts[:limit]


def apply_abstract_regrow(
    state: Dict[str, Any],
    map_id: str,
    elapsed_minutes: float,
) -> Dict[str, Any]:
    """Partial heal of shell scars between sorties (campaign-time regrow pressure).

    Capture holds under *live* regrow in-match; offline scars recover so re-entry
    is not permanent empty grass — occupation remains a living shell node.
    """
    mid = str(map_id or "")
    if not mid or float(elapsed_minutes or 0) <= 0:
        return {"regrown": 0, "mapId": mid, "healFrac": 0.0}
    hours = float(elapsed_minutes) / 60.0
    heal = min(0.85, 0.12 * hours)
    ledger = (state.get("shellScars") or {}).get(mid) or {}
    by_zone = ledger.get("byZone") if isinstance(ledger, dict) else None
    if not isinstance(by_zone, dict):
        return {"regrown": 0, "mapId": mid, "healFrac": heal}
    n = 0
    for _zid, z in list(by_zone.items()):
        if not isinstance(z, dict):
            continue
        dmg = float(z.get("damageSum") or 0.0)
        if dmg <= 0:
            continue
        z["damageSum"] = round(max(0.0, dmg * (1.0 - heal)), 4)
        dc = int(z.get("destroyedCount") or 0)
        if dc > 0 and heal >= 0.25:
            z["destroyedCount"] = max(0, dc - 1)
        n += 1
        # Mirror abstract scar pressure down.
        zm = (state.get("zoneMemory") or {}).get(mid, {}).get(_zid)
        if isinstance(zm, dict):
            absr = zm.setdefault("abstract", {})
            scar = float(absr.get("shellScar") or 0.0)
            absr["shellScar"] = round(max(0.0, scar * (1.0 - heal)), 4)
            absr["regrowPressure"] = round(heal, 4)
    if isinstance(ledger, dict):
        ledger["regrowAt"] = utc_now()
        ledger["lastHealFrac"] = round(heal, 4)
    return {"regrown": n, "mapId": mid, "healFrac": round(heal, 4)}


def main() -> int:
    ap = argparse.ArgumentParser(description="Capture node claim probe / apply")
    ap.add_argument("--workspace", default=".")
    ap.add_argument("--result", default="inbox/latest_va_result.json")
    ap.add_argument("--state", default="state/campaign_state.json")
    ap.add_argument("--write-state", action="store_true")
    ap.add_argument("--self-test", action="store_true")
    args = ap.parse_args()

    if args.self_test:
        return _self_test()

    ws = Path(args.workspace).resolve()
    result = load_json(ws / args.result, {})
    state = load_json(ws / args.state, {})
    report = apply_node_claim(state, result)
    report["hub"] = hub_claim_surface(state, report.get("mapId") or None)
    if args.write_state and report.get("claimed"):
        out = ws / args.state
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")
        report["wroteState"] = True
    print(json.dumps(report, indent=2))
    return 0 if report.get("reason") != "missing_map_or_zone" else 2


def _self_test() -> int:
    """Mechanical referee for capture claim rules (no BAR runtime)."""
    fails: List[str] = []

    # 1) empty grass / hold incomplete → no claim
    state: Dict[str, Any] = {
        "zoneMemory": {
            "koom_valley": {
                "KOOM_CENTRAL_FLUID_SCAR": {
                    "controllingFaction": "armada",
                    "abstract": {"control": "armada"},
                }
            }
        }
    }
    r1 = {
        "mapId": "koom_valley",
        "targetZoneId": "KOOM_CENTRAL_FLUID_SCAR",
        "status": "victory",
        "captureMode": CAPTURE_MODE,
        "capturePhase": "hold",
        "pocketCleared": True,
        "nodeClaimed": False,
        "patron": "nullmercs",
    }
    rep1 = apply_node_claim(state, r1, success=True)
    if rep1["claimed"]:
        fails.append("empty-grass/hold incomplete should not claim")

    # 2) clear + hold complete → claim, no free Tnb
    r2 = {
        **r1,
        "nodeClaimed": True,
        "capturePhase": "claimed",
        "regrowWaves": 2,
        "resultKey": "selftest-claim-1",
    }
    rep2 = apply_node_claim(state, r2, success=True)
    if not rep2["claimed"]:
        fails.append(f"node_claimed should claim: {rep2}")
    ctrl = state["zoneMemory"]["koom_valley"]["KOOM_CENTRAL_FLUID_SCAR"]["controllingFaction"]
    if ctrl != "nullmercs":
        fails.append(f"control should flip to nullmercs, got {ctrl}")
    if "KOOM_CENTRAL_FLUID_SCAR" not in (state.get("claimedNodes") or {}).get("koom_valley", {}):
        fails.append("claimedNodes ledger missing")

    # 3) hub sortie stamp
    s = stamp_sortie_capture({
        "mapId": "koom_valley",
        "targetZoneId": "KOOM_CENTRAL_FLUID_SCAR",
        "objectiveArchetype": "seize_lane",
    })
    if s.get("captureMode") != CAPTURE_MODE:
        fails.append(f"sortie stamp failed: {s}")

    # 4) eco_raid is not capture path
    r_raid = {
        "mapId": "greenest_fields",
        "targetZoneId": "GF_SE_ENERGY_WORKS",
        "status": "victory",
        "objectiveArchetype": "eco_raid",
    }
    if is_capture_result(r_raid):
        fails.append("eco_raid must not be capture path")

    # 5) pure pocket math
    if pocket_cleared(5, 10):
        fails.append("5/10 should not clear at 0.6")
    if not pocket_cleared(6, 10):
        fails.append("6/10 should clear")
    if capture_phase(destroyed=6, total=10, hold_frames=0) != "hold":
        fails.append("phase should be hold after clear")
    if capture_phase(destroyed=6, total=10, hold_frames=900) != "claimed":
        fails.append("phase should be claimed after hold")
    nr = node_claim_result(destroyed=6, total=10, hold_frames=900)
    if nr.get("tenebriumFromClaim") != 0:
        fails.append("claim must not mint Tnb")

    # 6) abstract regrow
    st_r: Dict[str, Any] = {
        "shellScars": {
            "koom_valley": {
                "byZone": {"KOOM_CENTRAL_FLUID_SCAR": {"destroyedCount": 10, "damageSum": 10.0}},
                "units": [],
            }
        },
        "zoneMemory": {
            "koom_valley": {
                "KOOM_CENTRAL_FLUID_SCAR": {"abstract": {"shellScar": 0.8, "control": "armada"}}
            }
        },
    }
    rg = apply_abstract_regrow(st_r, "koom_valley", 120.0)
    if rg.get("regrown", 0) < 1:
        fails.append(f"regrow should heal: {rg}")

    if fails:
        print("SELFTEST FAIL")
        for f in fails:
            print(" -", f)
        return 1
    print("SELFTEST OK capture_node_claims")
    print(json.dumps({"claimed": True, "mode": CAPTURE_MODE}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
