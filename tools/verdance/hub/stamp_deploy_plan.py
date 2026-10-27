#!/usr/bin/env python3
"""Stamp a hub deploy_plan.v1 into sortie order + outbox artifacts (G2 glue).

Reads a C&C board plan (from the HTML hub) and writes:
  - outbox/hub_deploy_plan.latest.json   (raw plan echo)
  - outbox/next_sortie_order.json        (VA-SORTIE/1 contract the engine reads)
  - outbox/hub_deploy_stamp.latest.json  (report)

Seed mapping (docs/hub_state_v1.md):
  captureZoneIds[0]  → targetZoneId (primary objective)
  captureZoneIds[1:] → secondaryCaptureZoneIds
  deployZoneId       → fromZoneIds[0] + deploymentZoneId
  extractZoneId      → extractionZoneId

Usage:
  python -m verdance.hub.stamp_deploy_plan --plan path/to/plan.json
  python -m verdance.hub.stamp_deploy_plan --plan plan.json --workspace .
  type plan.json | python -m verdance.hub.stamp_deploy_plan --stdin
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from verdance.common import load_json, save_json, utc_now
from verdance.world import zone_graph as wzg, landing_zones as lz, roads as _roads
from verdance.world.graph_collapse import snapshot_graph, pressure_brief
from verdance.company.company import ensure_company, sortie_roster
from verdance.belief import hub_belief

SORTIE_SCHEMA = "verdance-sortie-order/1.0"
PLAN_SCHEMA = "verdance-deploy-plan/1.0"
def zone_meta_lookup(ws: Path, map_id: str) -> dict[str, dict]:
    """zoneId → {bounds, tags, role} from authored zone map."""
    if not map_id:
        return {}
    authored = ws / "data" / "zone_maps" / "authored"
    candidates = list(authored.glob(f"{map_id}*.json")) if authored.is_dir() else []
    if not candidates:
        return {}
    try:
        data = load_json(candidates[0], {})
    except Exception:  # noqa: BLE001
        return {}
    out: dict[str, dict] = {}
    for z in data.get("zones") or []:
        zid = z.get("zoneId")
        if not zid:
            continue
        out[str(zid)] = {
            "bounds": z.get("bounds") if isinstance(z.get("bounds"), dict) else None,
            "tags": list(z.get("tags") or []),
            "role": str(z.get("role") or ""),
        }
    return out


def zone_bounds_lookup(ws: Path, map_id: str) -> dict[str, dict]:
    """zoneId → bounds from authored zone map."""
    return {
        zid: meta["bounds"]
        for zid, meta in zone_meta_lookup(ws, map_id).items()
        if meta.get("bounds")
    }


def normalize_plan(raw: dict) -> dict:
    """Accept hub plan or already-normalized shape."""
    marks = raw.get("marks") or {}
    caps = list(marks.get("captureZoneIds") or raw.get("captureZoneIds") or [])
    deploy = marks.get("deployZoneId") or raw.get("deployZoneId") or raw.get("deploymentZoneId")
    extract = marks.get("extractZoneId") or raw.get("extractZoneId") or raw.get("extractionZoneId")
    # Pass six: raiders land and lift from the same pad. The extract mark is accepted for
    # schema compatibility but always equals the pad.
    extract = deploy
    map_id = raw.get("mapId") or raw.get("map")
    return {
        "schemaVersion": raw.get("schemaVersion") or PLAN_SCHEMA,
        "mapId": map_id,
        "contractKind": raw.get("contractKind") or raw.get("objectiveArchetype") or "seize_lane",
        "deployAces": list(raw.get("deployAces") or []),
        "crewBand": list(raw.get("crewBand") or raw.get("crew_band") or []),
        "choiceId": raw.get("choiceId") or raw.get("hubChoiceId"),
        "repDelta": raw.get("repDelta") or {},
        "arcId": raw.get("arcId"),
        "maxCaptureMarks": raw.get("maxCaptureMarks"),
        "marks": {
            "deployZoneId": deploy,
            "extractZoneId": extract,
            "captureZoneIds": caps,
        },
        "patron": raw.get("patron") or "nullmercs",
        "against": raw.get("against") or "armada",
        "pathSignal": raw.get("pathSignal"),
        "sessionMode": raw.get("sessionMode") or "same_map",
        "occupationModel": raw.get("occupationModel") or "living_shell",
    }


def choice_pads(ws: Path, choice_id: str | None, map_id: str | None = None) -> set[str]:
    """Pads the active hub sortie already named.

    Those pads are the route on the seal. The quiet-rim rule still applies to
    a freehand mark; it does not veto the sortie the player just confirmed.
    If the choice id has been refreshed out of the hub, pads named by the
    current sorties on the same map still count.
    """
    hub = load_json(ws / "app" / "showoff" / "hub_state.json", {})
    choices = ((hub.get("node") or {}).get("choices")) or []
    keys = (
        "preferredDeployZoneId",
        "deploymentZoneId",
        "preferredExtractionZoneId",
        "extractionZoneId",
    )

    def take(effect: dict) -> set[str]:
        return {str(effect[k]) for k in keys if effect.get(k)}

    matched: set[str] = set()
    same_map: set[str] = set()
    for ch in choices:
        if not isinstance(ch, dict):
            continue
        effect = ch.get("effect") or {}
        if choice_id and ch.get("id") == choice_id:
            matched = take(effect)
        if map_id and effect.get("mapId") == map_id and ch.get("kind") == "deploy":
            same_map |= take(effect)
    return matched or same_map


def lz_zone_id(warning: str) -> str:
    bits = str(warning).split()
    if len(bits) < 2:
        return ""
    return bits[1].rstrip(":")


def blocking_lz_warnings(warns: list[str], pads: set[str]) -> list[str]:
    blocked: list[str] = []
    for raw in warns:
        warning = str(raw)
        if not warning.startswith("LZ_"):
            continue
        if lz_zone_id(warning) in pads:
            continue
        blocked.append(warning)
    return blocked


def soft_validate(plan: dict, ws: Path, state: dict | None = None) -> list[str]:
    """Warnings + hard LZ errors (LZ_* → stamp still writes but valid may fail).

    Legal pad: a door the company holds, ground believed ours, or the camp's next pad.
    Legacy RIM_* codes are no longer emitted; midfield is fine when owned.
    """
    warns: list[str] = []
    map_id = plan.get("mapId")
    marks = plan.get("marks") or {}
    caps = marks.get("captureZoneIds") or []
    if not map_id:
        warns.append("NO_MAP: mapId missing")
    if not caps:
        warns.append("NO_CAPTURE: need at least one captureZoneId")
    if not marks.get("deployZoneId"):
        warns.append("NO_DEPLOY: deployZoneId missing (will fall back in materialize)")

    if state is None:
        state = load_json(ws / "state" / "campaign_state.json", {})
    meta_by_id = zone_meta_lookup(ws, str(map_id or ""))
    deploy = marks.get("deployZoneId")
    extract = marks.get("extractZoneId") or deploy

    def _lz_warn(kind: str, zone_id: str) -> None:
        meta = meta_by_id.get(str(zone_id)) or {}
        bounds = meta.get("bounds")
        if bounds is None and str(zone_id) not in meta_by_id:
            warns.append(f"UNKNOWN_{kind}_ZONE: {zone_id}")
            return
        # Legality is judged on what the company knows, never on the truth: a pad is ground we
        # believe is ours, a door our ledger says we hold, or the pad the last manifest set.
        if _roads.held(state, str(zone_id)):
            return
        bel = None
        try:
            bel = (hub_belief.belief_surface(ws, state, str(map_id or "")).get("zones") or {}).get(str(zone_id))
        except Exception:  # noqa: BLE001
            bel = None
        camp = state.get("camp") or {}
        if str(camp.get("nextPadZoneId") or "") == str(zone_id):
            return
        if bel is not None and bel.get("believed") == "ours":
            return
        if bel is None:
            ok, reason = lz.legal_landing_reason(state, str(map_id or ""), str(zone_id), bounds,
                                                 tags=meta.get("tags"), role=str(meta.get("role") or ""))
            if ok:
                return
        conf = int(float((bel or {}).get("confidence") or 0) * 100)
        why = {"held": f"believed held by {(bel or {}).get('faction') or 'someone'} ({conf}%)",
               "empty": "believed empty, not ours", "dark": "nobody has looked; not ours",
               "unsure": "not ours"}.get((bel or {}).get("believed") or "dark", "not ours")
        warns.append(f"LZ_{kind}: {zone_id} illegal ({why}); a pad is ground we believe is ours, or a door we hold")

    if deploy:
        _lz_warn("DEPLOY", str(deploy))
    if extract and extract != deploy:
        _lz_warn("EXTRACT", str(extract))

    try:
        adj = wzg.load_full_adjacency(ws, kinds=("same_map",))
    except Exception as e:  # noqa: BLE001
        warns.append(f"ADJ_LOAD: {e}")
        return warns
    if map_id and map_id not in adj:
        warns.append(f"UNKNOWN_MAP: {map_id} not in world zone graph")
        return warns
    map_adj = adj.get(map_id) or {}
    primary = caps[0] if caps else None
    if primary and primary not in map_adj:
        warns.append(f"UNKNOWN_ZONE: {primary}")
    if primary and deploy and map_adj:
        neighbors = set(map_adj.get(primary) or [])
        # Soft: warn if deploy is neither the target nor a neighbor (still stamp)
        if deploy != primary and deploy not in neighbors and deploy not in map_adj:
            warns.append(f"DEPLOY_OFF_GRAPH: {deploy}")
        elif deploy != primary and deploy not in neighbors:
            warns.append(
                f"DEPLOY_NOT_ADJACENT: {deploy} does not border primary {primary} "
                f"(neighbors={sorted(neighbors)})"
            )
    return warns


def plan_to_sortie(plan: dict, state: dict | None = None) -> dict:
    marks = plan["marks"]
    caps = list(marks.get("captureZoneIds") or [])
    primary = caps[0] if caps else None
    secondary = caps[1:]
    deploy = marks.get("deployZoneId")
    extract = marks.get("extractZoneId") or deploy
    from_zones = [z for z in [deploy] if z]
    # Prefer patron footholds from state if deploy missing
    graph = (state or {}).get("graph") or {}
    path = plan.get("pathSignal") or (state or {}).get("pathSignal") or "B"
    q6 = float(graph.get("q6_contested", 0.85) or 0.85)
    q7 = float(graph.get("q7_resource_scarcity", 0.98) or 0.98)
    map_id = plan.get("mapId")
    home = str((state or {}).get("sessionHomeMap") or (state or {}).get("homeMapId") or "")
    home = home.lower().replace(" ", "_") if home else ""
    plan_mid = str(map_id or "").lower().replace(" ", "_")
    # Leaving session home via the theater board is intentional travel, not Mode A.
    if plan.get("sessionMode"):
        session_mode = plan.get("sessionMode")
    elif home and plan_mid and plan_mid != home:
        session_mode = "reload_travel"
    else:
        session_mode = (state or {}).get("sessionMode") or "same_map"

    # Full G snapshot for the measurement apparatus (hub prepares; BAR does not own G).
    try:

        graph_snap = snapshot_graph(graph)
        graph_pressure = pressure_brief(graph)
    except Exception:
        graph_snap = {
            "q6_contested": round(q6, 4),
            "q7_resource_scarcity": round(q7, 4),
        }
        graph_pressure = f"contested={q6:.2f} scarcity={q7:.2f}"
    # Legacy compact keys kept for older gadget readers
    graph_snap.setdefault("q6", round(q6, 3))
    graph_snap.setdefault("q7", round(q7, 4))

    return {
        "schemaVersion": SORTIE_SCHEMA,
        "campaignId": (state or {}).get("campaignId") or "verdance_ashes",
        "mapId": map_id,
        "targetZoneId": primary,
        "secondaryCaptureZoneIds": secondary,
        "captureZoneIds": caps,
        "deploymentZoneId": deploy,
        "extractionZoneId": extract,
        "patron": plan.get("patron") or "nullmercs",
        "patronBloc": "nullmercs",
        "against": plan.get("against") or "armada",
        "fromZoneIds": from_zones,
        "objectiveArchetype": plan.get("contractKind") or "seize_lane",
        "difficulty": 3,
        "targetDuration": "10min",
        "contractXp": 280 + 40 * len(secondary),
        "pathSignal": path,
        "namedDefender": None,
        "hubChoiceId": plan.get("choiceId"),
        "deployAces": list(plan.get("deployAces") or []),
        "crewBand": list(plan.get("crewBand") or []),
        "repDelta": plan.get("repDelta") or {},
        "sessionMode": session_mode,
        "occupationModel": plan.get("occupationModel")
        or (state or {}).get("occupationModel")
        or "living_shell",
        "graphSnapshot": graph_snap,
        "graphPressure": graph_pressure,
        "source": "hub_deploy_plan",
        "derived": {
            "source": "hub_deploy_plan",
            "arcId": plan.get("arcId"),
            "maxCaptureMarks": plan.get("maxCaptureMarks"),
            "graphPressure": graph_pressure,
        },
        "valid": bool(primary and plan.get("mapId")),
        "stampedAt": utc_now(),
    }


def stamp(plan_raw: dict, workspace: Path) -> dict:
    ws = workspace.resolve()
    plan = normalize_plan(plan_raw)
    state = load_json(ws / "state" / "campaign_state.json", {})
    # Hub Dropping list wins. Core is added in sortie_roster. Missing list = everyone living.
    try:

        ensure_company(state, ws)
        if (state.get("company") or {}).get("sealed"):
            requested = plan.get("crewBand")
            if requested is None:
                requested = plan.get("deployAces")
            band, aces = sortie_roster(state, requested)
            plan["crewBand"] = band
            plan["deployAces"] = aces
    except Exception:
        pass
    warns = soft_validate(plan, ws, state)
    sortie = plan_to_sortie(plan, state)
    # Freehand midfield pads still fail the drop. The sortie's own infil does not.
    pads = choice_pads(ws, plan.get("choiceId"), plan.get("mapId"))
    lz_hard = blocking_lz_warnings(warns, pads)
    if lz_hard:
        sortie["valid"] = False
        sortie["errors"] = lz_hard

    outbox = ws / "outbox"
    plan_path = outbox / "hub_deploy_plan.latest.json"
    order_path = outbox / "next_sortie_order.json"
    report_path = outbox / "hub_deploy_stamp.latest.json"

    save_json(plan_path, {**plan, "stampedAt": utc_now()})
    save_json(order_path, sortie)
    # Story engine prefers next_sortie_choice.json over next_sortie_order.
    # Hub commit must win: overwrite choice with the same contract (or clear it).
    choice_path = outbox / "next_sortie_choice.json"
    save_json(choice_path, {
        **sortie,
        "source": "hub_deploy_plan",
        "note": "Written by stamp_deploy_plan_v1 so hub C&C marks beat stale debrief picks.",
    })

    # Soft Mode A lock: remember home map so hub + quest walk stay on theater after play.
    # Does not mutate campaign_state.json (process_result owns that on advance).
    home_hint = {
        "schemaVersion": "verdance-session-home/1.0",
        "sessionHomeMap": sortie.get("mapId"),
        "sessionMode": sortie.get("sessionMode") or "same_map",
        "occupationModel": sortie.get("occupationModel") or "living_shell",
        "hubChoiceId": sortie.get("hubChoiceId"),
        "stampedAt": utc_now(),
        "source": "hub_deploy_plan",
    }
    save_json(outbox / "session_home.latest.json", home_hint)

    report = {
        "schemaVersion": "verdance-hub-deploy-stamp/1.0",
        "ok": bool(sortie.get("valid")),
        "stampedAt": utc_now(),
        "planPath": str(plan_path),
        "sortieOrderPath": str(order_path),
        "sortieChoicePath": str(choice_path),
        "mapId": sortie.get("mapId"),
        "targetZoneId": sortie.get("targetZoneId"),
        "secondaryCaptureZoneIds": sortie.get("secondaryCaptureZoneIds"),
        "deploymentZoneId": sortie.get("deploymentZoneId"),
        "extractionZoneId": sortie.get("extractionZoneId"),
        "hubChoiceId": sortie.get("hubChoiceId"),
        "deployAces": sortie.get("deployAces"),
        "crewBand": sortie.get("crewBand"),
        "sessionMode": sortie.get("sessionMode"),
        "occupationModel": sortie.get("occupationModel"),
        "warnings": warns,
        "error": lz_hard[0] if lz_hard else None,
        "next": [
            "python -m verdance.campaign.engine intent --workspace .",
            "powershell -File scripts/build_next_mission_v1.ps1",
            "Or: python -m verdance_kernel serve  (POST /api/deploy with launch=true)",
        ],
    }
    save_json(report_path, report)
    return report


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Stamp hub deploy_plan → next_sortie_order")
    ap.add_argument("--plan", default="", help="Path to deploy_plan JSON")
    ap.add_argument("--stdin", action="store_true", help="Read plan JSON from stdin")
    ap.add_argument("--workspace", default=".", help="Workspace root")
    args = ap.parse_args(argv)

    if args.stdin:
        plan = json.loads(sys.stdin.read())
    elif args.plan:
        plan = load_json(Path(args.plan), {})
    else:
        print("ERROR: pass --plan <file> or --stdin", file=sys.stderr)
        return 2

    report = stamp(plan, Path(args.workspace))
    print(json.dumps(report, indent=2))
    return 0 if report.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
