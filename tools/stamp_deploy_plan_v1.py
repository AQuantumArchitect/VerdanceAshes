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

SORTIE_SCHEMA = "verdance-sortie-order/1.0"
PLAN_SCHEMA = "verdance-deploy-plan/1.0"
RIM_EDGE_THRESHOLD = 0.28


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
    xmin = float(bounds.get("xMin", 0) or 0)
    xmax = float(bounds.get("xMax", 1) or 1)
    zmin = float(bounds.get("zMin", 0) or 0)
    zmax = float(bounds.get("zMax", 1) or 1)
    cx = (xmin + xmax) * 0.5
    cz = (zmin + zmax) * 0.5
    return min(cx, 1.0 - cx, cz, 1.0 - cz)


def is_rim_zone(bounds: dict, *, threshold: float = RIM_EDGE_THRESHOLD) -> bool:
    return edge_score(bounds) <= threshold


def zone_bounds_lookup(ws: Path, map_id: str) -> dict[str, dict]:
    """zoneId → bounds from authored zone map."""
    if not map_id:
        return {}
    authored = ws / "data" / "zone_maps" / "authored"
    # greenest_fields.authored.zone_map.json etc.
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
        if zid and isinstance(z.get("bounds"), dict):
            out[str(zid)] = z["bounds"]
    return out


def normalize_plan(raw: dict) -> dict:
    """Accept hub plan or already-normalized shape."""
    marks = raw.get("marks") or {}
    caps = list(marks.get("captureZoneIds") or raw.get("captureZoneIds") or [])
    deploy = marks.get("deployZoneId") or raw.get("deployZoneId") or raw.get("deploymentZoneId")
    extract = marks.get("extractZoneId") or raw.get("extractZoneId") or raw.get("extractionZoneId")
    if not extract:
        extract = deploy
    map_id = raw.get("mapId") or raw.get("map")
    return {
        "schemaVersion": raw.get("schemaVersion") or PLAN_SCHEMA,
        "mapId": map_id,
        "contractKind": raw.get("contractKind") or raw.get("objectiveArchetype") or "seize_lane",
        "deployAces": list(raw.get("deployAces") or []),
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


def soft_validate(plan: dict, ws: Path) -> list[str]:
    """Warnings + hard rim errors (RIM_* → stamp still writes but valid may fail)."""
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

    # Hard rim rule: infil / exfil must sit on the map edge.
    bounds_by_id = zone_bounds_lookup(ws, str(map_id or ""))
    deploy = marks.get("deployZoneId")
    extract = marks.get("extractZoneId") or deploy
    if deploy and bounds_by_id:
        b = bounds_by_id.get(str(deploy))
        if b is not None and not is_rim_zone(b):
            warns.append(
                f"RIM_DEPLOY: {deploy} is midfield (edgeScore={edge_score(b):.2f}); "
                f"infil must be on the rim (≤{RIM_EDGE_THRESHOLD})"
            )
        elif b is None:
            warns.append(f"UNKNOWN_DEPLOY_ZONE: {deploy}")
    if extract and bounds_by_id and extract != deploy:
        b = bounds_by_id.get(str(extract))
        if b is not None and not is_rim_zone(b):
            warns.append(
                f"RIM_EXTRACT: {extract} is midfield (edgeScore={edge_score(b):.2f}); "
                f"exfil must be on the rim (≤{RIM_EDGE_THRESHOLD})"
            )

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

    return {
        "schemaVersion": SORTIE_SCHEMA,
        "campaignId": (state or {}).get("campaignId") or "verdance_ashes",
        "mapId": plan.get("mapId"),
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
        "repDelta": plan.get("repDelta") or {},
        "sessionMode": plan.get("sessionMode") or (state or {}).get("sessionMode") or "same_map",
        "occupationModel": plan.get("occupationModel")
        or (state or {}).get("occupationModel")
        or "living_shell",
        "graphSnapshot": {"q6": round(q6, 3), "q7": round(q7, 4)},
        "source": "hub_deploy_plan",
        "derived": {
            "source": "hub_deploy_plan",
            "arcId": plan.get("arcId"),
            "maxCaptureMarks": plan.get("maxCaptureMarks"),
        },
        "valid": bool(primary and plan.get("mapId")),
        "stampedAt": _now(),
    }


def stamp(plan_raw: dict, workspace: Path) -> dict:
    ws = workspace.resolve()
    plan = normalize_plan(plan_raw)
    state = load_json(ws / "state" / "campaign_state.json")
    warns = soft_validate(plan, ws)
    sortie = plan_to_sortie(plan, state)
    # Hard fail rim violations so the hub cannot drop a midfield landing.
    rim_hard = [w for w in warns if w.startswith("RIM_")]
    if rim_hard:
        sortie["valid"] = False
        sortie["errors"] = rim_hard

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
        "sessionMode": sortie.get("sessionMode"),
        "occupationModel": sortie.get("occupationModel"),
        "warnings": warns,
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
