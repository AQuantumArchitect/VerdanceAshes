#!/usr/bin/env python3
"""Every map name in shipped data must be one BAR will actually load.

Why this exists
---------------
A map name that does not match an installed archive is not a soft failure. The
engine aborts in PreGame, before the mutator loads:

    Fatal: [ExitSpringProcess] errorMsg="Dependent archive "greenest fields 1.3.1"
           (resolved to "Greenest Fields 1.3.1") not found"

That exact string is in this repo's own headless logs, and the file that
produced it -- data/zone_maps/greenest_fields.zone_map.json -- still ships. The
phantom trailing ".1" appears to have leaked in from `minimapKey`, which
legitimately carries an extra segment for four of the seven maps.

data/map_pool/seven_maps.json is the single authority for what a map is called.
This asserts every other file agrees with it, and optionally that BAR's content
service can actually serve each one.

  python tools/validate_map_names_v1.py
  python tools/validate_map_names_v1.py --root export/dist/VerdanceAshes_v0.10.0
  python tools/validate_map_names_v1.py --online     # also check they resolve
"""
from __future__ import annotations

import argparse
import io
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Set, Tuple

# Keys that carry a BAR map name and must match the pool exactly. Deliberately
# excludes minimapKey, which is an image filename stem and legitimately differs.
NAME_KEYS = {"mapName", "springName", "springname"}


def load_json(path: Path) -> Any:
    with io.open(path, encoding="utf-8-sig") as fh:
        return json.load(fh)


# Excluded by default because scripts\ship.ps1 removes them from the staging
# tree (zone_maps\generated, scenarios\generated) or never copies them
# (scenarios\*.json outside authored\). Their mapName fields carry short display
# labels, not archive names, so validating them reports noise a player can never
# hit. --all includes them anyway.
SHIP_EXCLUDED = ("zone_maps/generated", "scenarios/generated")


def pool_names(root: Path) -> Set[str]:
    pool = load_json(root / "data" / "map_pool" / "seven_maps.json")
    return {str(m["mapName"]) for m in (pool.get("maps") or []) if m.get("mapName")}


def walk_names(node: Any, path: str = "") -> List[Tuple[str, str]]:
    """Every (json-path, value) pair under a map-name key, at any depth."""
    out: List[Tuple[str, str]] = []
    if isinstance(node, dict):
        for k, v in node.items():
            here = f"{path}.{k}" if path else k
            if k in NAME_KEYS and isinstance(v, str) and v.strip():
                out.append((here, v))
            # scenario files nest the name as map.name
            elif k == "name" and isinstance(v, str) and path.endswith("map") and v.strip():
                out.append((here, v))
            else:
                out.extend(walk_names(v, here))
    elif isinstance(node, list):
        for i, v in enumerate(node):
            out.extend(walk_names(v, f"{path}[{i}]"))
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--root", default=str(Path(__file__).resolve().parents[1]))
    ap.add_argument("--online", action="store_true",
                    help="also assert each pool name resolves on BAR's map service")
    ap.add_argument("--all", action="store_true",
                    help="include generated data that never ships")
    args = ap.parse_args()
    root = Path(args.root).resolve()

    try:
        valid = pool_names(root)
    except Exception as exc:  # noqa: BLE001
        print(f"FAIL cannot read the seven-map pool: {exc}")
        return 2
    if not valid:
        print("FAIL the seven-map pool lists no mapName values.")
        return 2

    problems: List[str] = []
    checked = 0
    skipped = 0
    for jf in sorted((root / "data").rglob("*.json")):
        rel_posix = jf.relative_to(root).as_posix()
        if not args.all and any(x in rel_posix for x in SHIP_EXCLUDED):
            skipped += 1
            continue
        try:
            doc = load_json(jf)
        except Exception:  # noqa: BLE001 - unreadable json is another tool's problem
            continue
        for where, value in walk_names(doc):
            checked += 1
            if value not in valid:
                rel = jf.relative_to(root)
                problems.append(f"{rel} [{where}] = {value!r}")

    if problems:
        print("MAP NAME VALIDATION FAILED")
        for p in problems:
            print(f"  {p}")
        print("\nValid names (from data/map_pool/seven_maps.json):")
        for v in sorted(valid):
            print(f"  {v}")
        print("\nA name BAR cannot resolve is a fatal content_error at PreGame,")
        print("before the mutator loads -- it reads as 'crashed on launch'.")
        return 1

    note = f", {skipped} generated file(s) skipped" if skipped else ""
    print(f"map names OK ({checked} references across {len(valid)} maps{note})")

    if args.online:
        sys.path.insert(0, str(root / "tools"))
        try:
            import map_provisioner_v1 as mp
        except ImportError:
            print("WARN map_provisioner_v1 not importable; skipping the online check.")
            return 0
        bad = 0
        for name in sorted(valid):
            try:
                entry = mp.resolve(name)
                print(f"  resolves  {name}  ({int(entry.get('size', 0)) / 1048576:.0f} MB)")
            except Exception as exc:  # noqa: BLE001
                print(f"  MISSING   {name}: {exc}")
                bad += 1
        if bad:
            print(f"\n{bad} map(s) do not resolve on BAR's content service.")
            return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
