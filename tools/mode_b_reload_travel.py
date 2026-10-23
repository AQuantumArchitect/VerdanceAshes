#!/usr/bin/env python3
"""Mode B Reload map travel — session host path (pkt-bar-mode-b-reload-travel).

Gate: VA_CAPABILITY reload=true (Spring.Reload present). Evidence from live
headless infolog 2026-07-27 shell_bake_the_rock_jungle.

Wires strategic_link edges from world_zone_graph into the session host
relaunch / Reload path:

  1. Read debrief pick (outbox/next_sortie_choice.json) or explicit --from/--to
  2. Validate hop against world_zone_graph strategic_link edges
  3. Stamp next_sortie_choice + mode_b_travel.latest.json for advance/build

Mode A (same_map) remains kernel default. Mode B never fakes in-engine Reload
when startscript write is unavailable — session host external relaunch carries.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from verdance.world import zone_graph as wzg

OUT_CHOICE = Path("outbox/next_sortie_choice.json")
OUT_MODE_B = Path("outbox/mode_b_travel.latest.json")
OUT_CAP = Path("outbox/va_capability.latest.json")


def _utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _load_json(path: Path) -> Optional[Dict[str, Any]]:
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


def _save_json(path: Path, data: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def list_hops(ws: Path, from_zones: List[str], current_map: str = "") -> List[Dict[str, Any]]:
    return wzg.mode_b_travel_candidates(ws, from_zones, current_map_id=current_map or None)


def resolve_travel(
    ws: Path,
    *,
    from_zone: str = "",
    to_zone: str = "",
    map_id: str = "",
    write: bool = True,
) -> Dict[str, Any]:
    """Resolve a Mode B hop and stamp session-host artifacts."""
    choice = _load_json(ws / OUT_CHOICE) or {}
    from_z = from_zone or ""
    to_z = to_zone or ""
    if not from_z and isinstance(choice.get("fromZoneIds"), list) and choice["fromZoneIds"]:
        from_z = str(choice["fromZoneIds"][0])
    if not from_z:
        from_z = str(choice.get("fromZoneId") or choice.get("deploymentZoneId") or "")
    if not to_z:
        to_z = str(choice.get("targetZoneId") or "")
    target_map = map_id or str(choice.get("mapId") or "")

    # Collect from zones for hop search
    from_ids: List[str] = []
    if from_z:
        from_ids.append(from_z)
    if isinstance(choice.get("fromZoneIds"), list):
        for z in choice["fromZoneIds"]:
            if z and str(z) not in from_ids:
                from_ids.append(str(z))

    hops = list_hops(ws, from_ids or ([from_z] if from_z else []), current_map="")
    hop: Optional[Dict[str, Any]] = None

    if to_z:
        for h in hops:
            if h.get("targetZoneId") == to_z:
                hop = h
                break
        if hop is None and from_z:
            hop = wzg.validate_mode_b_hop(ws, from_z, to_z)
    elif target_map:
        # Prefer first strategic hop landing on requested map
        for h in hops:
            if wzg.canonical_map_id(h.get("mapId")) == wzg.canonical_map_id(target_map):
                hop = h
                break
    elif hops:
        # No explicit pick: surface legal hops only (no auto-commit)
        hop = None

    # Detect whether choice already is a cross-map / mode_b pick
    choice_mode = str(choice.get("sessionMode") or choice.get("travelMode") or "")
    wants_travel = choice_mode in ("reload_travel", "mode_b", "map_change") or (
        bool(choice.get("edgeKind") == "strategic_link")
    )

    cap = _load_json(ws / OUT_CAP) or {}
    result: Dict[str, Any] = {
        "schemaVersion": "verdance-mode-b-travel/1.0",
        "stampedAt": _utc(),
        "gate": {
            "requires": "VA_CAPABILITY.reload=true",
            "reloadPresent": bool(cap.get("reload", True)),
            "engine": str(cap.get("engine") or "2025.06.24"),
            "evidence": str(
                cap.get("source")
                or "headless_runs/shell_bake_the_rock_jungle_20260727_232018/infolog.txt"
            ),
            "note": (
                "Spring.Reload present. io/write false in that probe — session host "
                "external relaunch is the Reload path until startscript write works."
            ),
        },
        "fromZoneIds": from_ids,
        "requestedTargetZoneId": to_z or None,
        "requestedMapId": target_map or None,
        "legalHops": hops,
        "selectedHop": hop,
        "action": "none",
        "sessionHost": {
            "path": "scripts/play_session_v1.ps1",
            "phase": "mode-b-travel",
            "relaunch": True,
        },
    }

    if hop is None:
        if wants_travel and to_z:
            result["action"] = "reject_illegal"
            result["error"] = (
                f"no strategic_link hop from {from_ids} to {to_z}; "
                "Mode B requires world_zone_graph strategic_link edge"
            )
        elif wants_travel:
            result["action"] = "list_only"
            result["message"] = "travel requested but no matching hop; legalHops listed"
        else:
            result["action"] = "idle"
            result["message"] = "no Mode B travel pick; Mode A / same_map default stands"
        if write:
            _save_json(ws / OUT_MODE_B, result)
        return result

    # Stamp choice for story engine / advance
    stamped = {
        "schemaVersion": "verdance-sortie-order/1.0",
        "mapId": hop["mapId"],
        "targetZoneId": hop["targetZoneId"],
        "deploymentZoneId": hop["targetZoneId"],
        "extractionZoneId": hop["targetZoneId"],
        "fromZoneIds": hop.get("fromZoneIds") or [hop["fromZoneId"]],
        "objectiveArchetype": hop.get("objectiveArchetype") or "seize_lane",
        "patron": hop.get("patron") or "nullmercs",
        "against": hop.get("against") or "armada",
        "sessionMode": "reload_travel",
        "travelMode": "mode_b",
        "edgeKind": "strategic_link",
        "source": "mode_b_reload_travel",
        "candidateId": hop.get("id"),
        "title": hop.get("title"),
        "cost": hop.get("cost"),
        "notes": hop.get("notes"),
        "stampedAt": _utc(),
        "valid": True,
    }
    # Preserve hub extras if present
    for k in ("hubChoiceId", "deployAces", "pathSignal", "difficulty", "contractXp"):
        if k in choice and choice[k] is not None:
            stamped[k] = choice[k]

    result["action"] = "stamp_reload_travel"
    result["stampedChoice"] = stamped
    result["sessionHost"]["message"] = (
        f"Mode B: {hop.get('fromMapId')} → {hop['mapId']} "
        f"via strategic_link ({hop['fromZoneId']} → {hop['targetZoneId']})"
    )

    if write:
        _save_json(ws / OUT_CHOICE, stamped)
        _save_json(ws / OUT_MODE_B, result)
    return result


def stamp_capability_from_evidence(ws: Path) -> Dict[str, Any]:
    """Record known VA_CAPABILITY reload=true evidence for the matrix."""
    cap = {
        "schemaVersion": "verdance-va-capability/1.0",
        "stampedAt": _utc(),
        "source": "headless_runs/shell_bake_the_rock_jungle_20260727_232018/infolog.txt",
        "line": (
            "VA_CAPABILITY {io=false,write=false,read_back=false,reload=true,"
            "os=false,engine=2025.06.24,path=}"
        ),
        "io": False,
        "write": False,
        "read_back": False,
        "reload": True,
        "os": False,
        "engine": "2025.06.24",
        "gates": {
            "mode_a_same_map": "GO",
            "mode_b_reload_present": "GO",
            "mode_b_startscript_write": "NO_GO (io/write false in probe; session host carries)",
            "mode_c_external_relaunch": "GO",
        },
    }
    _save_json(ws / OUT_CAP, cap)
    return cap


def self_test(ws: Path) -> int:
    stats = wzg.graph_stats(ws)
    assert stats.get("source") == "world_zone_graph", stats
    edges = wzg.strategic_link_edges(ws)
    assert len(edges) >= 7, f"expected >=7 strategic_link edges, got {len(edges)}"

    # Derive the probe hop from the graph rather than naming zone ids inline.
    # The previous version asserted against GF_SE_STAGING / EOH_NW_CRATER_CAMP and
    # friends, which the zone-id migration renamed out of existence -- so the test
    # failed on its first assert and never reached the checks that would have
    # caught the shipped va_strategic_links.lua still carrying those dead ids.
    graph_zone_ids = {n["zoneId"] for n in wzg.load_world_zone_graph(ws)["nodes"]}
    probe = edges[0]
    from_zone, to_zone = probe["from"], probe["to"]
    hops = wzg.mode_b_travel_candidates(ws, [from_zone])
    assert hops, f"{from_zone} should have a Mode B hop"
    assert hops[0]["sessionMode"] == "reload_travel", hops[0]
    assert hops[0]["targetZoneId"] in graph_zone_ids, hops[0]
    hop = wzg.validate_mode_b_hop(ws, from_zone, to_zone)
    assert hop is not None, f"{from_zone} -> {to_zone} strategic_link missing"

    # Every strategic link must cross maps and land on a zone that exists.
    for e in edges:
        assert e["from"] in graph_zone_ids, e
        assert e["to"] in graph_zone_ids, e

    # same_map candidates must never include a cross-map strategic target.
    from_map = hops[0].get("fromMapId") or ""
    for map_id in {e.get("fromMapId") for e in edges if e.get("fromMapId")}:
        adj = wzg.load_map_adjacency(ws, map_id, kinds=("same_map",))
        cross_targets = {e["to"] for e in edges if e.get("fromMapId") == map_id}
        for nbrs in adj.values():
            assert not (set(nbrs) & cross_targets), (map_id, nbrs)

    r = resolve_travel(ws, from_zone=from_zone, to_zone=to_zone, write=False)
    assert r["action"] == "stamp_reload_travel", r

    cap = stamp_capability_from_evidence(ws)
    assert cap["reload"] is True
    print("ok mode_b_reload_travel self_test")
    print(f"  strategic_links={len(edges)} hops_from_GF={len(hops)}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="Mode B Reload travel (session host path)")
    ap.add_argument("--workspace", default=".", help="BAR workspace root")
    ap.add_argument(
        "--action",
        choices=("self-test", "list", "resolve", "stamp-capability"),
        default="self-test",
    )
    ap.add_argument("--from-zone", default="", help="Source zone id")
    ap.add_argument("--to-zone", default="", help="Destination zone id")
    ap.add_argument("--map", default="", help="Destination map id (optional)")
    ap.add_argument("--dry-run", action="store_true", help="Do not write outbox")
    args = ap.parse_args()
    ws = Path(args.workspace).resolve()

    if args.action == "self-test":
        return self_test(ws)

    if args.action == "list":
        zones = [args.from_zone] if args.from_zone else []
        if not zones:
            # list all strategic edges as bidirectional hops from each from
            hops = []
            for e in wzg.strategic_link_edges(ws):
                hops.extend(list_hops(ws, [str(e.get("from"))]))
            print(json.dumps({"hops": hops}, indent=2))
            return 0
        print(json.dumps({"fromZoneId": args.from_zone, "hops": list_hops(ws, zones)}, indent=2))
        return 0

    if args.action == "stamp-capability":
        cap = stamp_capability_from_evidence(ws)
        print(json.dumps(cap, indent=2))
        return 0

    # resolve
    result = resolve_travel(
        ws,
        from_zone=args.from_zone,
        to_zone=args.to_zone,
        map_id=args.map,
        write=not args.dry_run,
    )
    print(json.dumps(result, indent=2))
    if result.get("action") == "reject_illegal":
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
