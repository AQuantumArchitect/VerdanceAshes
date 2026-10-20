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
  python tools/stamp_deploy_plan_v1.py --plan path/to/plan.json
  python tools/stamp_deploy_plan_v1.py --plan plan.json --workspace .
  type plan.json | python tools/stamp_deploy_plan_v1.py --stdin
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_TOOLS = Path(__file__).resolve().parent
if str(_TOOLS) not in sys.path:
    sys.path.insert(0, str(_TOOLS))

try:
    import world_zone_graph as wzg  # noqa: E402
except Exception:  # noqa: BLE001
    wzg = None  # type: ignore

try:
    import landing_zones_v1 as lz  # noqa: E402
except Exception:  # noqa: BLE001
    lz = None  # type: ignore

SORTIE_SCHEMA = "verdance-sortie-order/1.0"
PLAN_SCHEMA = "verdance-deploy-plan/1.0"
RIM_EDGE_THRESHOLD = getattr(lz, "RIM_EDGE_THRESHOLD", 0.28) if lz else 0.28


def load_json(path: Path) -> dict:
    if not path.is_file():
        return {}
    return json.loads(path.read_text(encoding="utf-8-sig"))


def save_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def edge_score(bounds: dict) -> float:
    """Distance from map rim in normalized coords (0 = on edge, 0.5 = dead center)."""
    if lz is not None:
        return lz.edge_score(bounds)
    xmin = float(bounds.get("xMin", 0) or 0)
    xmax = float(bounds.get("xMax", 1) or 1)
    zmin = float(bounds.get("zMin", 0) or 0)
    zmax = float(bounds.get("zMax", 1) or 1)
    cx = (xmin + xmax) * 0.5
    cz = (zmin + zmax) * 0.5
    return min(cx, 1.0 - cx, cz, 1.0 - cz)


def is_rim_zone(bounds: dict, *, threshold: float = RIM_EDGE_THRESHOLD) -> bool:
    if lz is not None:
        return lz.is_rim_zone(bounds, threshold=threshold)
    return edge_score(bounds) <= threshold


def zone_meta_lookup(ws: Path, map_id: str) -> dict[str, dict]:
    """zoneId → {bounds, tags, role} from authored zone map."""
    if not map_id:
        return {}
    authored = ws / "data" / "zone_maps" / "authored"
    candidates = list(authored.glob(f"{map_id}*.json")) if authored.is_dir() else []
    if not candidates:
        return {}
    try:
        data = load_json(candidates[0])
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
    # A mouth card's doors win over a board mark that snapped inland.
    infil = raw.get("infilZoneId") or (marks.get("infilZoneId") if isinstance(marks, dict) else None)
    exfil = raw.get("exfilZoneId") or (marks.get("exfilZoneId") if isinstance(marks, dict) else None)
    if infil:
        deploy = infil
    # Pass six: raiders land and lift from the same pad. The exfil/extract mark is accepted for
    # schema compatibility but always equals the pad.
    exfil = None
    extract = deploy
    map_id = raw.get("mapId") or raw.get("map")
    wet = bool(raw.get("wetReach") or infil)
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
        "wetReach": wet,
        "infilZoneId": infil or deploy,
        "exfilZoneId": exfil or extract,
        "headingMapId": raw.get("headingMapId"),
        "headingZoneId": raw.get("headingZoneId"),
        "alongTheWay": list(raw.get("alongTheWay") or []),
    }


def choice_pads(ws: Path, choice_id: str | None, map_id: str | None = None) -> set[str]:
    """Infil/exfil the active hub sortie already named.

    Those pads are the route on the seal. The quiet-rim rule still applies to
    a freehand mark; it does not veto the sortie the player just confirmed.
    If the choice id has been refreshed out of the hub, pads named by the
    current sorties on the same map still count.
    """
    hub = load_json(ws / "app" / "showoff" / "hub_state.json")
    choices = ((hub.get("node") or {}).get("choices")) or []
    keys = (
        "preferredDeployZoneId",
        "deploymentZoneId",
        "preferredExtractionZoneId",
        "extractionZoneId",
        "infilZoneId",
        "exfilZoneId",
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

    Legal infil/exfil: quiet rim OR Ashwalker-majority established base.
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
        state = load_json(ws / "state" / "campaign_state.json")
    meta_by_id = zone_meta_lookup(ws, str(map_id or ""))
    deploy = marks.get("deployZoneId")
    extract = marks.get("extractZoneId") or deploy

    def _lz_warn(kind: str, zone_id: str) -> None:
        meta = meta_by_id.get(str(zone_id)) or {}
        bounds = meta.get("bounds")
        if bounds is None and str(zone_id) not in meta_by_id:
            warns.append(f"UNKNOWN_{kind}_ZONE: {zone_id}")
            return
        if lz is None:
            # Fallback without landing_zones_v1: cannot see Ashwalker ownership,
            # so only quiet-rim geometry is accepted (never a permanent hard lock).
            if bounds is not None and not is_rim_zone(bounds):
                warns.append(
                    f"LZ_{kind}: {zone_id} is midfield (edgeScore={edge_score(bounds):.2f}); "
                    f"need quiet rim or Ashwalker base (landing_zones_v1 missing)"
                )
            return
        # Pass six: legality is judged on what the COMPANY BELIEVES, never on the truth.
        # legal = believed ours · a rim we believe empty / nobody has looked at, with low believed
        # threat · the pad the last manifest said we would land on.
        bel = None
        try:
            import hub_belief_v1  # type: ignore
            bel = (hub_belief_v1.belief_surface(ws, state, str(map_id or "")).get("zones") or {}).get(str(zone_id))
        except Exception:  # noqa: BLE001
            bel = None
        if bel is not None:
            camp = state.get("camp") or {}
            if str(camp.get("nextPadZoneId") or "") == str(zone_id):
                return
            if bel.get("believed") == "ours":
                return
            rim = bounds is not None and is_rim_zone(bounds)
            threat = float(bel.get("threat") or 0.0)
            if bel.get("believed") in ("empty", "dark", "unsure") and rim and threat <= 0.4:
                return
            why = {"held": f"believed held by {bel.get('faction') or 'someone'} ({int(float(bel.get('confidence') or 0) * 100)}%)",
                   "empty": "believed empty but not a rim", "dark": "nobody has looked and it is not a rim",
                   "unsure": "not a rim", "ours": "ours"}.get(bel.get("believed") or "dark", "not a legal pad")
            if threat > 0.4 and bel.get("believed") in ("empty", "dark", "unsure"):
                why = f"believed threat too high ({threat:.2f})"
            warns.append(f"LZ_{kind}: {zone_id} illegal ({why}); a pad is ground we believe is ours, or a quiet rim")
            return
        ok, reason = lz.legal_landing_reason(
            state,
            str(map_id or ""),
            str(zone_id),
            bounds,
            tags=meta.get("tags"),
            role=str(meta.get("role") or ""),
        )
        if ok:
            return
        score = edge_score(bounds) if bounds else 0.5
        warns.append(
            f"LZ_{kind}: {zone_id} illegal ({reason}, edgeScore={score:.2f}); "
            f"infil/exfil need quiet rim or Ashwalker-majority base"
        )

    if deploy and (meta_by_id or lz is not None):
        _lz_warn("DEPLOY", str(deploy))
    if extract and extract != deploy and (meta_by_id or lz is not None):
        _lz_warn("EXTRACT", str(extract))

    if wzg is None:
        return warns
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
        from graph_collapse_v1 import snapshot_graph, pressure_brief

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
        "wetReach": bool(plan.get("wetReach")),
        "infilZoneId": plan.get("infilZoneId") or deploy,
        "exfilZoneId": plan.get("exfilZoneId") or extract,
        "headingMapId": plan.get("headingMapId"),
        "headingZoneId": plan.get("headingZoneId"),
        "alongTheWay": list(plan.get("alongTheWay") or []),
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
        "missionCallIns": list(plan.get("missionCallIns") or []),
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
        "stampedAt": _now(),
    }


def stamp(plan_raw: dict, workspace: Path) -> dict:
    ws = workspace.resolve()
    plan = normalize_plan(plan_raw)
    state = load_json(ws / "state" / "campaign_state.json")
    # Hub Dropping list wins. Core is added in sortie_roster. Missing list = everyone living.
    try:
        from company_v1 import ensure_company, sortie_roster  # type: ignore

        ensure_company(state, ws)
        if (state.get("company") or {}).get("sealed"):
            requested = plan.get("crewBand")
            if requested is None:
                requested = plan.get("deployAces")
            band, aces = sortie_roster(state, requested)
            plan["crewBand"] = band
            plan["deployAces"] = aces
        # Prefer call-ins already on the plan (commit_deploy consumed them into plan).
        if not plan.get("missionCallIns"):
            from company_v1 import peek_mission_call_ins  # type: ignore

            pending = peek_mission_call_ins(state)
            if pending:
                plan["missionCallIns"] = pending
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

    save_json(plan_path, {**plan, "stampedAt": _now()})
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
        "stampedAt": _now(),
        "source": "hub_deploy_plan",
    }
    save_json(outbox / "session_home.latest.json", home_hint)

    report = {
        "schemaVersion": "verdance-hub-deploy-stamp/1.0",
        "ok": bool(sortie.get("valid")),
        "stampedAt": _now(),
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
            "python tools/verdance_story_engine_v1.py intent --workspace .",
            "powershell -File scripts/build_next_mission_v1.ps1",
            "Or: python tools/hub_host_v1.py  (POST /api/deploy with launch=true)",
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
        plan = load_json(Path(args.plan))
    else:
        print("ERROR: pass --plan <file> or --stdin", file=sys.stderr)
        return 2

    report = stamp(plan, Path(args.workspace))
    print(json.dumps(report, indent=2))
    return 0 if report.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
