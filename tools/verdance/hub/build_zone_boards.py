#!/usr/bin/env python3
"""Embed authored zone maps for the C&C deployment board (showoff shell)."""
from __future__ import annotations

import json
import sys
from pathlib import Path

from verdance.common import WORKSPACE_ROOT, edge_score

ROOT = WORKSPACE_ROOT
AUTH = ROOT / "data" / "zone_maps" / "authored"
OUT = ROOT / "app" / "showoff" / "boards.embed.js"
def is_capturable(role: str, tags: list, bounds: dict | None = None) -> bool:
    """Any non-staging zone can take a capture mark (C&C board).
    Preferred objective tags just influence default highlight order in the UI.
    """
    t = set(tags or [])
    # Staging / player start never capturable
    if role == "legion_start" or "staging" in t:
        return False
    if "start" in t and ("legion" in t or "ashwalker" in t):
        return False
    return True


def is_preferred_objective(role: str, tags: list) -> bool:
    t = set(tags or [])
    if t & {"objective", "economy", "armada", "cortex", "fortress", "relay", "hive"}:
        return True
    if role in (
        "defender_start",
        "armada_start",
        "cortex_start",
        "main_field",
        "energy_edge",
        "raptor_hazard",
        "fortress",
    ):
        return True
    return False


def is_edge_zone(bounds: dict, *, threshold: float = 0.28) -> bool:
    """Quiet-rim geometry helper (edgeScore ≤ threshold). Not a hard LZ lock —
    inland Ashwalker bases are also legal landings at stamp/hub time."""
    return edge_score(bounds) <= threshold


def is_deploy_candidate(role: str, tags: list, bounds: dict | None = None) -> bool:
    """Authored start/staging/muster pads — rim preferred for defaults, but
    midfield starts are not stripped (owned inland FOBs land here later)."""
    t = set(tags or [])
    if role == "legion_start":
        return True
    if "staging" in t or "start" in t or "muster" in t:
        return True
    if "start" in t and ("legion" in t or "ashwalker" in t):
        return True
    if role in ("start", "reserve") and ("green" in t or "muster" in str(role)):
        return True
    if role == "start":
        return True
    return False


def is_inter_map_lane(zone_id: str, role: str, tags: list, bounds: dict) -> bool:
    """Theater corridor endpoints (rim muster / lane / staging)."""
    if not is_edge_zone(bounds):
        return False
    blob = f"{zone_id or ''} {role or ''} {' '.join(tags or [])}".lower()
    keys = ("muster", "lane", "staging", "causeway", "shelf", "start", "camp", "approach")
    return any(k in blob for k in keys)


def build_boards() -> dict:
    boards = {}
    for path in sorted(AUTH.glob("*.authored.zone_map.json")):
        data = json.loads(path.read_text(encoding="utf-8-sig"))
        map_id = data.get("mapId") or path.stem.split(".")[0]
        zones = []
        for z in data.get("zones") or []:
            b = z.get("bounds") or {}
            tags = list(z.get("tags") or [])
            role = z.get("role") or ""
            zid = z.get("zoneId")
            bounds = {
                "xMin": float(b.get("xMin", 0)),
                "xMax": float(b.get("xMax", 1)),
                "zMin": float(b.get("zMin", 0)),
                "zMax": float(b.get("zMax", 1)),
            }
            es = round(edge_score(bounds), 4)
            hydro = z.get("hydrology") or {}
            try:
                resting = float(hydro.get("restingSubmerged") or 0.0)
                floods_at = float(hydro.get("floodsAt") or 2.0)
            except (TypeError, ValueError):
                resting, floods_at = 0.0, 2.0
            anchor = z.get("anchor") or {}
            try:
                ax = float(anchor.get("x"))
                az = float(anchor.get("z"))
            except (TypeError, ValueError):
                ax = (bounds["xMin"] + bounds["xMax"]) / 2.0
                az = (bounds["zMin"] + bounds["zMax"]) / 2.0
            dry = bool(z.get("campEligible", True)) and resting < 0.35 and floods_at > 0.0
            zones.append(
                {
                    "zoneId": zid,
                    "label": z.get("label") or zid,
                    "role": role,
                    "tags": tags,
                    "bounds": bounds,
                    "anchor": {"x": round(ax, 4), "z": round(az, 4)},
                    "dry": dry,
                    "edgeScore": es,
                    # Quiet-rim corridor hint — hub still unlocks Ashwalker inland pads.
                    "interMapLane": is_inter_map_lane(str(zid or ""), role, tags, bounds),
                    "capturable": is_capturable(role, tags, bounds),
                    "preferredObjective": is_preferred_objective(role, tags),
                    "deployDefault": False,  # set after ranking (rim preferred, not required)
                    "extractDefault": False,
                }
            )
        # Prefer quiet-rim / inter-map lanes for *defaults*; midfield starts stay eligible.
        rim = [z for z in zones if is_edge_zone(z["bounds"])]
        lane_rim = [z for z in rim if z.get("interMapLane")]
        deployish = [
            z for z in zones
            if is_deploy_candidate(z["role"], z["tags"], z["bounds"]) or z.get("interMapLane")
        ]
        candidates = [
            z for z in (lane_rim or rim or deployish)
            if is_deploy_candidate(z["role"], z["tags"], z["bounds"]) or z.get("interMapLane")
        ]
        if not candidates:
            candidates = [z for z in rim if not z["capturable"]]
        if not candidates:
            candidates = deployish[:1] or sorted(
                zones, key=lambda z: (0 if z.get("interMapLane") else 1, z["edgeScore"])
            )[:1]
        if candidates:
            # Prefer true edge, then inter-map lanes — never hard-exclude midfield pads.
            best = min(
                candidates,
                key=lambda z: (
                    0 if is_edge_zone(z["bounds"]) else 1,
                    z["edgeScore"],
                    0 if z.get("interMapLane") else 1,
                ),
            )
            best["deployDefault"] = True
            best["extractDefault"] = True
            best["capturable"] = False  # never capture your own LZ
            alts = sorted(
                [z for z in candidates if z is not best],
                key=lambda z: (
                    0 if is_edge_zone(z["bounds"]) else 1,
                    z["edgeScore"],
                    0 if z.get("interMapLane") else 1,
                ),
            )
            if alts:
                alts[0]["extractDefault"] = True
            else:
                for z in zones:
                    if z is not best and is_edge_zone(z["bounds"]) and not z["preferredObjective"]:
                        z["extractDefault"] = True
                        break
        if zones and not any(z["capturable"] for z in zones):
            for z in zones:
                if not z["deployDefault"]:
                    z["capturable"] = True
        boards[map_id] = {
            "mapId": map_id,
            "mapName": data.get("mapName") or map_id,
            "zones": zones,
        }
    return boards


def main() -> int:
    if not AUTH.is_dir():
        print(f"missing {AUTH}", file=sys.stderr)
        return 1
    boards = build_boards()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(
        "window.ZONE_BOARDS = " + json.dumps(boards, separators=(",", ":")) + ";\n",
        encoding="utf-8",
    )
    print(f"wrote {OUT} maps={len(boards)}")
    for mid, b in boards.items():
        print(f"  {mid}: {len(b['zones'])} zones capturable={sum(1 for z in b['zones'] if z['capturable'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
