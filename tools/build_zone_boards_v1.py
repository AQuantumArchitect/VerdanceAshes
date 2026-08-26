#!/usr/bin/env python3
"""Embed authored zone maps for the C&C deployment board (showoff shell)."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
AUTH = ROOT / "data" / "zone_maps" / "authored"
OUT = ROOT / "app" / "showoff" / "boards.embed.js"


def edge_score(bounds: dict) -> float:
    """Distance from map rim in normalized coords (0 = on edge, 0.5 = dead center)."""
    xmin = float(bounds.get("xMin", 0) or 0)
    xmax = float(bounds.get("xMax", 1) or 1)
    zmin = float(bounds.get("zMin", 0) or 0)
    zmax = float(bounds.get("zMax", 1) or 1)
    cx = (xmin + xmax) * 0.5
    cz = (zmin + zmax) * 0.5
    return min(cx, 1.0 - cx, cz, 1.0 - cz)


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
    """Enfil / exfil belong on the rim of the map, not the middle."""
    return edge_score(bounds) <= threshold


def is_deploy_candidate(role: str, tags: list, bounds: dict) -> bool:
    """Player landing candidates: start/staging only if also near the map edge."""
    if not is_edge_zone(bounds):
        return False
    t = set(tags or [])
    if role == "legion_start":
        return True
    if "staging" in t or "start" in t:
        return True
    if "start" in t and ("legion" in t or "ashwalker" in t):
        return True
    if role in ("reserve",) and "green" in t:
        return True
    return False


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
            bounds = {
                "xMin": float(b.get("xMin", 0)),
                "xMax": float(b.get("xMax", 1)),
                "zMin": float(b.get("zMin", 0)),
                "zMax": float(b.get("zMax", 1)),
            }
            es = round(edge_score(bounds), 4)
            zones.append(
                {
                    "zoneId": z.get("zoneId"),
                    "label": z.get("label") or z.get("zoneId"),
                    "role": role,
                    "tags": tags,
                    "bounds": bounds,
                    "edgeScore": es,
                    "capturable": is_capturable(role, tags, bounds),
                    "preferredObjective": is_preferred_objective(role, tags),
                    "deployDefault": False,  # set after edge ranking
                    "extractDefault": False,
                }
            )
        # Prefer true rim landings: lowest edgeScore among deploy candidates.
        candidates = [z for z in zones if is_deploy_candidate(z["role"], z["tags"], z["bounds"])]
        if not candidates:
            # Fallback: any non-capturable edge zone, else lowest edgeScore overall.
            candidates = [z for z in zones if is_edge_zone(z["bounds"]) and not z["capturable"]]
        if not candidates:
            candidates = sorted(zones, key=lambda z: z["edgeScore"])[:1]
        if candidates:
            best = min(candidates, key=lambda z: z["edgeScore"])
            best["deployDefault"] = True
            best["extractDefault"] = True
            best["capturable"] = False  # never capture your own LZ
            # Second-best edge zone as alternate extract if available
            alts = sorted(
                [z for z in candidates if z is not best],
                key=lambda z: z["edgeScore"],
            )
            if alts:
                alts[0]["extractDefault"] = True
            else:
                # Mark other edge non-objectives as extract-friendly
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
