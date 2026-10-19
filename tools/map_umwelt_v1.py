#!/usr/bin/env python3
"""L2 map umwelt — mapPressure loader + hero×map fit.

SSOT: data/story/map_umwelt.json
Hero molecules: data/story/hero_umwelt.json

Usage:
  python tools/map_umwelt_v1.py list
  python tools/map_umwelt_v1.py pressure --map the_rock_jungle
  python tools/map_umwelt_v1.py fit --map eye_of_horus
  python tools/map_umwelt_v1.py fit --map greenest_fields --zone GF_NE_PLATEAU
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
MAP_PATH = ROOT / "data" / "story" / "map_umwelt.json"
HERO_PATH = ROOT / "data" / "story" / "hero_umwelt.json"

AXES = [
    "energy",
    "offense",
    "mobility",
    "sight",
    "pad",
    "craft",
    "heat",
    "fog",
    "sky",
    "ledger",
]

_ALIASES = {
    "rock_jungle": "the_rock_jungle",
    "rj": "the_rock_jungle",
    "gf": "greenest_fields",
    "eoh": "eye_of_horus",
    "ab": "ancient_bastion",
    "ats": "all_that_simmers",
    "kv": "koom_valley",
}


def load_map_umwelt(path: Path | None = None) -> dict[str, Any]:
    p = path or MAP_PATH
    return json.loads(p.read_text(encoding="utf-8-sig"))


def normalize_map_id(map_id: str) -> str:
    mid = str(map_id or "").strip()
    return _ALIASES.get(mid, mid)


def _clamp(v: float, lo: float = -1.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, v))


def maps_by_id(doc: dict[str, Any] | None = None) -> dict[str, dict[str, Any]]:
    doc = doc or load_map_umwelt()
    out: dict[str, dict[str, Any]] = {}
    for row in doc.get("maps") or []:
        if isinstance(row, dict) and row.get("mapId"):
            out[str(row["mapId"])] = row
    return out


def pressure_for(
    map_id: str,
    zone_id: str | None = None,
    *,
    doc: dict[str, Any] | None = None,
) -> dict[str, float]:
    """Resolved mapPressure vector (axes → float), optional zone delta."""
    doc = doc or load_map_umwelt()
    mid = normalize_map_id(map_id)
    by = maps_by_id(doc)
    row = by.get(mid)
    if not row:
        # honest empty pressure — caller can treat as dark/unknown map
        return {a: 0.0 for a in (doc.get("axes") or AXES)}
    base = {a: float((row.get("mapPressure") or {}).get(a, 0.0)) for a in AXES}
    zid = str(zone_id or "").strip()
    if zid:
        z = (doc.get("zones") or {}).get(zid)
        if isinstance(z, dict):
            # if zone declares mapId, prefer that base when caller map blank/mismatch
            zmap = str(z.get("mapId") or "")
            if zmap and zmap != mid and zmap in by:
                base = {
                    a: float((by[zmap].get("mapPressure") or {}).get(a, 0.0))
                    for a in AXES
                }
            delta = z.get("mapPressureDelta") or {}
            for a, dv in delta.items():
                if a in base:
                    base[a] = _clamp(base[a] + float(dv))
    return base


def fit_score(hero_axes: dict[str, Any], map_pressure: dict[str, float]) -> float:
    return sum(float(hero_axes.get(a, 0.0)) * float(map_pressure.get(a, 0.0)) for a in AXES)


def rank_heroes_for_map(
    map_id: str,
    zone_id: str | None = None,
    *,
    hero_doc: dict[str, Any] | None = None,
    map_doc: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    if hero_doc is None:
        hero_doc = json.loads(HERO_PATH.read_text(encoding="utf-8-sig"))
    pressure = pressure_for(map_id, zone_id, doc=map_doc)
    ranked = []
    for h in hero_doc.get("heroes") or []:
        if not isinstance(h, dict):
            continue
        hid = str(h.get("heroId") or "")
        ax = h.get("axes") or {}
        ranked.append(
            {
                "heroId": hid,
                "name": h.get("name"),
                "glyph": h.get("glyph"),
                "score": fit_score(ax, pressure),
            }
        )
    ranked.sort(key=lambda r: -r["score"])
    return ranked


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    sp = ap.add_subparsers(dest="cmd", required=True)

    sp.add_parser("list", help="List maps + glyphs")
    p_press = sp.add_parser("pressure", help="Print resolved pressure")
    p_press.add_argument("--map", required=True)
    p_press.add_argument("--zone", default="")
    p_fit = sp.add_parser("fit", help="Rank heroes for a map")
    p_fit.add_argument("--map", required=True)
    p_fit.add_argument("--zone", default="")
    p_fit.add_argument("--top", type=int, default=8)

    args = ap.parse_args()
    doc = load_map_umwelt()

    if args.cmd == "list":
        for row in doc.get("maps") or []:
            print(f"{row['mapId']:20} {row.get('glyphs','')}  {row.get('biomeCue','')}")
        return 0

    if args.cmd == "pressure":
        p = pressure_for(args.map, args.zone or None, doc=doc)
        print(json.dumps({"mapId": normalize_map_id(args.map), "zoneId": args.zone or None, "mapPressure": p}, indent=2))
        return 0

    if args.cmd == "fit":
        ranked = rank_heroes_for_map(args.map, args.zone or None, map_doc=doc)
        print(f"map={normalize_map_id(args.map)} zone={args.zone or '-'}")
        for r in ranked[: max(1, args.top)]:
            print(f"  {r['score']:+.3f}  {r['heroId']:12}  {r.get('glyph','')}")
        return 0

    return 1


if __name__ == "__main__":
    raise SystemExit(main())
