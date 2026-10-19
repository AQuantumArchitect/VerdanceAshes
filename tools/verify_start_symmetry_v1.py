#!/usr/bin/env python3
"""Check that a scenario starts its teams on symmetric ground.

Every authored scenario hardcodes a diagonal start pair -- team 0 at
(0.16, 0.16), team 1 at (0.84, 0.84). That is only a fair pairing on a map whose
symmetry group actually contains a diagonal or 180-degree rotation. On a map whose
accepted symmetry is a north-south mirror, the counterpart of the northwest corner
is the SOUTHWEST corner, and the diagonal placement drops the two teams on
completely different ground.

Greenest Fields is the worst case found: team 0 starts in GF_NW_MUSTER (symmetry
family F1, 392 cells, relative height 0.22) while team 1 starts in GF_SE_PLATEAU
(family F2, 1740 cells, relative height 0.72) -- 4.4x the area, on high ground.
Measured consequence, three AI mirror matches on that map with identical AI on
both sides and a fixed RNG seed: BARb aggressive 1.014 (they never fight),
BARb hard 0.430, SimpleAI 0.000 (team 0 annihilated). The more the two sides
actually engage, the worse the disadvantaged start does.

The zone cartographer already records everything needed to catch this: each map's
accepted symmetry group, and a symmetryFamily tag pairing each zone with its
counterpart. Two teams start fairly when their start zones share a family.

Exit 1 if any scenario starts its teams in different symmetry families.

Usage:
  python tools/verify_start_symmetry_v1.py --workspace .
  python tools/verify_start_symmetry_v1.py --workspace . --dirs data/scenarios/authored
"""
from __future__ import annotations

import argparse
import io
import json
import math
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


def load_json(path: Path) -> Any:
    with io.open(path, encoding="utf-8-sig") as fh:
        return json.load(fh)


def nearest_zone(zones: List[Dict[str, Any]], x: float, z: float) -> Tuple[Optional[Dict], float]:
    best, best_d = None, float("inf")
    for zone in zones:
        anchor = zone.get("anchor") or {}
        if anchor.get("x") is None:
            continue
        d = math.hypot(float(anchor["x"]) - x, float(anchor["z"]) - z)
        if d < best_d:
            best_d, best = d, zone
    return best, best_d


def check_scenario(ws: Path, path: Path) -> Optional[Dict[str, Any]]:
    scenario = load_json(path)
    layout = scenario.get("layout") or {}
    teams = [t for t in (layout.get("teams") or [])]
    # Wild/raptor teams are not duelling sides; they are meant to be asymmetric.
    playable = [
        t
        for t in teams
        if not (
            str(t.get("label") or "").find("RaptorsAI") >= 0
            or str(t.get("side") or "").find("Raptor") >= 0
        )
    ]
    if len(playable) < 2:
        return None

    map_id = str((scenario.get("map") or {}).get("id") or "")
    zm_path = ws / "data" / "zone_maps" / "authored" / f"{map_id}.authored.zone_map.json"
    if not zm_path.exists():
        return None
    zone_map = load_json(zm_path)
    zones = zone_map.get("zones") or []
    symmetry = (zone_map.get("symmetry") or {}).get("accepted") or []

    found = []
    for team in playable[:2]:
        base = team.get("base") or [0.5, 0.5]
        zone, dist = nearest_zone(zones, float(base[0]), float(base[1]))
        if not zone:
            return None
        ev = zone.get("evidence") or {}
        found.append(
            {
                "teamId": team.get("id"),
                "side": team.get("side"),
                "base": base,
                "zoneId": zone.get("zoneId"),
                "symmetryFamily": zone.get("symmetryFamily"),
                "cellCount": ev.get("cellCount"),
                "relativeHeight": round(float(ev.get("relativeHeight") or 0.0), 3),
                "anchorDistance": round(dist, 4),
            }
        )

    a, b = found
    fair = a["symmetryFamily"] == b["symmetryFamily"]
    cells_a = float(a["cellCount"] or 0) or 1.0
    cells_b = float(b["cellCount"] or 0) or 1.0
    ratio = max(cells_a, cells_b) / min(cells_a, cells_b)

    return {
        "scenario": path.name,
        "scenarioDir": path.parent.name,
        "mapId": map_id,
        "acceptedSymmetry": symmetry,
        "teams": found,
        "sameFamily": fair,
        "areaRatio": round(ratio, 2),
        "heightDelta": round(abs(a["relativeHeight"] - b["relativeHeight"]), 3),
    }


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="Verify scenario start symmetry")
    ap.add_argument("--workspace", default=".")
    ap.add_argument(
        "--dirs",
        default="data/scenarios/authored,data/scenarios/campaign_ai,data/scenarios/ai_duel",
    )
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args(argv)

    ws = Path(args.workspace).resolve()
    results = []
    for rel in [d.strip() for d in args.dirs.split(",") if d.strip()]:
        d = ws / rel
        if not d.is_dir():
            continue
        for path in sorted(d.glob("*.json")):
            try:
                r = check_scenario(ws, path)
            except Exception as exc:
                print(f"  ! {path.name}: {exc}", file=sys.stderr)
                continue
            if r:
                results.append(r)

    bad = [r for r in results if not r["sameFamily"]]

    if not args.quiet:
        print(f"Checked {len(results)} scenario(s) with two playable starts.")
        print()
        for r in results:
            mark = "ok  " if r["sameFamily"] else "FAIL"
            a, b = r["teams"]
            print(
                f"{mark} {r['scenario']:<42} symmetry={','.join(r['acceptedSymmetry']) or 'none'}"
            )
            print(
                f"       team {a['teamId']} -> {a['zoneId']:<22} fam={a['symmetryFamily']:<5}"
                f" cells={a['cellCount']:<7} relH={a['relativeHeight']}"
            )
            print(
                f"       team {b['teamId']} -> {b['zoneId']:<22} fam={b['symmetryFamily']:<5}"
                f" cells={b['cellCount']:<7} relH={b['relativeHeight']}"
            )
            if not r["sameFamily"]:
                print(
                    f"       -> different symmetry families; area ratio {r['areaRatio']}x,"
                    f" height delta {r['heightDelta']}"
                )
        print()
        print(f"{len(bad)} scenario(s) start their teams on non-corresponding ground.")

    out = ws / "reports" / "start_symmetry_check.latest.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    with io.open(out, "w", encoding="utf-8") as fh:
        json.dump(
            {
                "schemaVersion": "verdance-start-symmetry-check/0.1",
                "checked": len(results),
                "failures": len(bad),
                "results": results,
            },
            fh,
            indent=2,
        )
    if not args.quiet:
        print(f"Report: {out}")

    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
